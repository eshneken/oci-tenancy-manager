"""Authorized organization decisions and atomic lifecycle handoff to the native worker queue."""

import json
import re
from datetime import UTC
from uuid import uuid4

from sqlalchemy import select, update

from otm.configuration.service import current_baseline
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.organization.contracts import Configuration, IdentityMerge, ReviewDecision
from otm.organization.reconcile import prepare
from otm.organization.review_rules import has_valid_accountability, issue_basis
from otm.organization.reviews import reconcile_reviews
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict, source_intake
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    audit_event,
    operation,
    org_feed,
    org_person,
    org_recommendation,
    org_workspace,
    tenancy,
    tenancy_membership,
)
from otm.tenancies.contracts import (
    ActionReceipt,
    AssociationChoice,
    FrozenAssociation,
    LifecycleTarget,
    OrganizationIntent,
)
from otm.tenancies.directory import (
    association_view,
    person_workflow,
    registry_state,
    review_directory,
    tenancy_directory,
    tenancy_view,
)
from otm.tenancies.views import TenancyDetail


# A stale preview is a recoverable conflict; it cannot silently retarget the administrator's
# decision.
def require_context(state, expected):
    if state.context != expected:
        raise OrganizationConflict("ORGANIZATION_PREVIEW_CHANGED")


# Compose real application decisions and explicitly simulated provider workflows without prototype
# bypasses.
class OrganizationWorkflows:
    # The store supplies current session authority; provider policy and queue adapter are
    # server-owned.
    def __init__(
        self,
        store,
        *,
        enqueuer=None,
        policy=None,
        facade=None,
        policy_loader=None,
        configuration_checks=None,
        mail_policy=None,
        notifications=None,
    ):
        self.store, self.enqueuer, self.policy, self.facade = store, enqueuer, policy, facade
        self.mail_policy, self.notifications = mail_policy, notifications
        self.configuration_checks = configuration_checks
        self.policy_loader = policy_loader
        self.mode = "simulated" if policy and facade and enqueuer else "unavailable"

    # Read-only previews resolve every label and eligible action from this session's workspace.
    def preview(self, principal, identifier, review_id=None):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            view = person_workflow(
                registry_state(connection, workspace),
                identifier,
                mode=self.mode,
                review_id=review_id,
            )
            return view.model_copy(
                update={
                    "email_contacts": self._email_contacts(
                        connection, principal, view.person.email
                    ),
                    "current_baseline": current_baseline(connection, workspace),
                    "creation_regions": self.facade.creation_regions()
                    if self.mode == "simulated"
                    else (),
                }
            )

    # Operator-owned routing preserves canonical person email and the current admin profile.
    def _email_contacts(self, connection, principal, owner_email, people=None):
        if self.mail_policy is None:
            return None
        from otm.email_policy import EmailContacts
        from otm.storage.tables import administrator

        original = connection.execute(
            select(administrator.c.email).where(
                administrator.c.workspace_id == principal.session.workspace_id,
                administrator.c.issuer == principal.actor.issuer,
                administrator.c.subject == principal.actor.subject,
            )
        ).scalar_one()
        return EmailContacts(
            activation=self.mail_policy.route(original),
            owner=self.mail_policy.route(owner_email),
            people={key: self.mail_policy.route(value) for key, value in (people or {}).items()},
        )

    # The review inbox and dated history share one coherent, bounded server-side projection.
    def reviews(self, principal, query):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            exists = connection.scalar(
                select(org_workspace.c.applied_version_id).where(org_workspace.c.id == workspace)
            )
            if exists is None:
                from otm.tenancies.views import ReviewDirectory

                return ReviewDirectory(
                    items=(),
                    total=0,
                    page=1,
                    pages=1,
                    page_size=query.page_size,
                    actionable_count=0,
                    history_count=0,
                )
            return review_directory(registry_state(connection, workspace), query)

    # Registry visibility never reads unrelated tenants or claims OCI inventory discovery.
    def tenancies(self, principal, query):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            exists = connection.scalar(
                select(org_workspace.c.applied_version_id).where(org_workspace.c.id == workspace)
            )
            if exists is None:
                from otm.tenancies.views import TenancyDirectory

                return TenancyDirectory(
                    items=(),
                    total=0,
                    page=1,
                    pages=1,
                    page_size=query.page_size,
                    total_tenancies=0,
                    individual_count=0,
                    shared_count=0,
                    pending_count=0,
                    issue_count=0,
                )
            directory = tenancy_directory(registry_state(connection, workspace), query)
            if self.configuration_checks:
                checks = {
                    item.tenancy_id: item
                    for item in self.configuration_checks.summaries(connection, workspace)
                }
                directory = directory.model_copy(
                    update={
                        "items": tuple(
                            self._check_view(item, checks.get(item.id)) for item in directory.items
                        )
                    }
                )
            return directory

    # Details retain removed membership/compartment cleanup evidence as well as active
    # relationships.
    def tenancy_detail(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            state = registry_state(connection, workspace)
            row = state.tenancies.get(identifier)
            if row is None:
                raise OrganizationConflict("TENANCY_NOT_FOUND")
            onboarding_id = None
            if row["status"] == "pending" and row["operation_id"]:
                candidate = connection.execute(
                    select(audit_event.c.data).where(
                        audit_event.c.workspace_id == workspace,
                        audit_event.c.operation_id == row["operation_id"],
                        audit_event.c.kind == "operation_intent",
                    )
                ).scalar_one_or_none()
                if candidate and candidate["intent"].get("onboarding_version") in {1, 2}:
                    onboarding_id = row["operation_id"]
            config_operation = row["operation_id"] or row.get("last_operation_id")
            return TenancyDetail(
                configuration_operation_id=config_operation
                if state.operation_kinds.get(config_operation) == "configuration_update"
                else None,
                onboarding_operation_id=onboarding_id,
                tenancy=self._check_view(
                    tenancy_view(state, row),
                    self.configuration_checks.summaries(connection, workspace, identifier)[0]
                    if self.configuration_checks and row["status"] == "active"
                    else None,
                ),
                people=tuple(
                    state.option(a["person_id"])
                    for a in state.associations(tenant=identifier, history=True)
                ),
                memberships=tuple(
                    association_view(state, a)
                    for a in state.associations(tenant=identifier, history=True)
                ),
                compartment_parents=self.facade.compartments(row["tenancy_ocid"])
                if self.facade and row["status"] == "active"
                else (),
            )

    # Supplement inventory with the same immutable evidence projection as Configuration drift.
    def _check_view(self, view, check):
        if check is None:
            return view
        return view.model_copy(
            update={
                "configuration_issue_count": check.issue_count,
                "configuration_confirmed_issue_count": check.confirmed_issue_count,
                "configuration_check_state": check.state,
                "configuration_checked_at": check.checked_at,
                "configuration_check_stale": check.stale,
            }
        )

    # A qualified setup remains attached to its initiating person and trusted parent
    # throughout waits.
    def _require_onboarding_context(self, state, intent):
        person = state.people.get(intent.target.person_id)
        control = state.controls.get(intent.target.person_id)
        current = self.policy_loader() if self.policy_loader else None
        if self.mode != "simulated" or (
            current and (current.execution_paused or current.policy != self.policy)
        ):
            raise OrganizationConflict("LIFECYCLE_PROVIDER_UNAVAILABLE")
        if (
            person is None
            or control is None
            or person.email not in state.supplied
            or person.absence_review
            or control["directory_status"] != "included"
            or intent.parent_tenancy_ocid != self.policy.parent_tenancy_ocid
            or intent.policy_revision != self.policy.policy_revision
        ):
            raise OrganizationConflict("ONBOARDING_CONTEXT_CHANGED")

    # Progress reads one consistent snapshot and never schedules a provider action.
    def onboarding(self, principal, identifier):
        from otm.tenancies.onboarding import progress

        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            row = (
                connection.execute(
                    select(operation).where(
                        operation.c.workspace_id == workspace,
                        operation.c.id == identifier,
                        operation.c.kind == "organization_action",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None or not self.facade:
                raise OrganizationConflict("ONBOARDING_NOT_AVAILABLE")
            view = progress(connection, row, self.facade)
            return (
                view
                if row["responsible_actor_subject"] == principal.actor.key
                else view.model_copy(update={"can_act": False, "available_actions": ()})
            )

    # Handoff and setup commands reuse admission's lock order and commit queue/audit atomically.
    def onboarding_action(self, principal, identifier, command):
        from otm.tenancies.onboarding import submit

        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            row = (
                connection.execute(
                    select(operation)
                    .where(
                        operation.c.workspace_id == workspace,
                        operation.c.id == identifier,
                        operation.c.kind == "organization_action",
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None or not self.facade or not self.enqueuer:
                raise OrganizationConflict("ONBOARDING_NOT_AVAILABLE")
            receipt = submit(
                self, connection, registry_state(connection, workspace), row, principal, command, at
            )
            if self.notifications is not None:
                current = (
                    connection.execute(
                        select(operation).where(
                            operation.c.id == identifier, operation.c.workspace_id == workspace
                        )
                    )
                    .mappings()
                    .one()
                )
                self.notifications.stage(connection, current, at)
            return receipt

    # A tenancy-centric preview enumerates every affected owner/member rather than a person's links.
    def deletion_preview(self, principal, identifier):
        from otm.tenancies.deletion import DeletionPerson, TenancyDeletionPreview, deletion_plan

        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            state = registry_state(connection, workspace)
            plan = deletion_plan(state, identifier, self.policy)
            people = []
            for item in plan:
                person = state.people[item.person_id]
                other = len(state.associations(person=person.id)) - 1
                people.append(
                    DeletionPerson(
                        person_id=person.id,
                        name=person.full_name or person.email,
                        email=person.email,
                        role=item.role,
                        is_manager=person.known_manager,
                        other_tenancy_count=other,
                        leaves_directory=other == 0
                        and person.email != state.config.policy.root_email,
                    )
                )
            return TenancyDeletionPreview(
                context=state.context,
                tenancy=tenancy_view(state, state.tenancies[identifier]),
                people=tuple(people),
                manager_warning=any(p.is_manager for p in people),
                shared_warning=state.tenancies[identifier]["kind"] == "shared",
            )

    # Termination, complete reservations, immutable intent and native job share the
    # admission commit.
    def delete_tenancy(self, principal, command):
        from otm.tenancies.contracts import OrganizationAction
        from otm.tenancies.deletion import deletion_plan

        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            prior = self._replay(connection, workspace, principal.actor, command)
            if prior:
                return prior
            state = registry_state(connection, workspace)
            require_context(state, command.context)
            plan = deletion_plan(state, command.tenancy_id, self.policy)
            if not command.confirm_deletion:
                raise OrganizationConflict("TENANCY_DELETION_CONFIRMATION_REQUIRED")
            if any(a.person_was_manager for a in plan) and not command.confirm_manager:
                raise OrganizationConflict("MANAGER_CONFIRMATION_REQUIRED")
            if (
                state.tenancies[command.tenancy_id]["kind"] == "shared"
                and not command.confirm_shared
            ):
                raise OrganizationConflict("SHARED_CONFIRMATION_REQUIRED")
            owner = next(a.person_id for a in plan if a.role == "owner")
            internal = OrganizationAction(
                client_request_key=command.client_request_key,
                context=command.context,
                person_id=owner,
                action="delete_tenancy",
                tenancy_id=command.tenancy_id,
                confirm_manager=command.confirm_manager,
                confirm_shared=command.confirm_shared,
            )
            return self._admit(
                connection,
                state,
                internal,
                state.people[owner],
                None,
                principal,
                at,
                deletion_plan=plan,
                request_digest=canonical_hash(command.model_dump(mode="json")),
            )

    # Controlled configuration decisions republish the same immutable source; they never
    # refresh its time.
    def _reapply(
        self, connection, state, config, at, *, configuration_only=True, allow_root_change=False
    ):
        # Only the exact-bound mapping Apply may replace the boundary. Source trust, census
        # qualifications and all other policy fields remain identical for every caller.
        expected_policy = (
            state.config.policy.model_copy(update={"root_email": config.policy.root_email})
            if allow_root_change and configuration_only
            else state.config.policy
        )
        if (
            config.policy != expected_policy
            or config.id == state.config.id
            or len(config.model_dump_json().encode()) > 1024 * 1024
        ):
            raise ValueError("INVALID_ORGANIZATION_DECISION_CONFIGURATION")
        feed = (
            connection.execute(
                select(org_feed).where(
                    org_feed.c.workspace_id == state.workspace,
                    org_feed.c.id == state.head.snapshot_id,
                )
            )
            .mappings()
            .one()
        )
        source = source_intake(feed, config)
        # Settle newly recorded decisions only; mapping-only edits preserve every absence flag.
        from otm.organization.reviews import administrative_decision_history

        baseline = administrative_decision_history(
            state.head, state.config, config, {r.email for r in source.records}
        ).model_copy(update={"source_captured_at": None})
        raw = prepare(
            source.records,
            source.envelope,
            config.model_copy(update={"overrides": ()}),
            baseline,
            at,
            trusted_reapply=True,
            configuration_only=configuration_only,
        )
        candidate = prepare(
            source.records,
            source.envelope,
            config,
            baseline,
            at,
            trusted_reapply=True,
            configuration_only=configuration_only,
        )
        if raw.rejected or candidate.rejected:
            raise OrganizationConflict("ORGANIZATION_DECISION_INVALID_GRAPH")
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == state.workspace)
            .values(configuration_id=config.id, configuration=config.model_dump(mode="json"))
        )
        proposal = self.store._persist(connection, state.workspace, feed, config, raw, "proposed")
        applied = self.store._persist(
            connection, state.workspace, feed, config, candidate, "applied"
        )
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == state.workspace)
            .values(proposed_version_id=proposal.id, applied_version_id=applied.id)
        )
        reconcile_reviews(
            connection,
            state.workspace,
            applied,
            state.head,
            candidate,
            config,
            supplied={r.email for r in source.records},
            at=at,
            configuration_only=configuration_only,
        )

    # Refresh derived cases after a directory-only decision without fabricating another source feed.
    def _reconcile_current(self, connection, state, at):
        feed = (
            connection.execute(
                select(org_feed).where(
                    org_feed.c.workspace_id == state.workspace,
                    org_feed.c.id == state.head.snapshot_id,
                )
            )
            .mappings()
            .one()
        )
        source = source_intake(feed, state.config)
        candidate = prepare(
            source.records,
            source.envelope,
            state.config,
            state.head.model_copy(update={"source_captured_at": None}),
            at,
            trusted_reapply=True,
            configuration_only=True,
        )
        reconcile_reviews(
            connection,
            state.workspace,
            state.head,
            state.head,
            candidate,
            state.config,
            supplied={r.email for r in source.records},
            at=at,
            configuration_only=True,
        )

    # Settle only the reviewed condition/episode; permanent ignore is restricted to LOB mapping.
    def _decide(self, config, state, review, person, action, actor, at):
        if review is None or review["kind"] == "TENANCY_SETUP_REVIEW":
            return config
        kind, target = review["kind"], review["target"]
        decision = ReviewDecision(
            kind=kind,
            target=target,
            disposition="ignored" if action == "ignore" else "resolved",
            person_id=person.id,
            basis=issue_basis(kind, target, state.head.people),
            recorded_at=at,
            actor=actor.key,
            reason="Administrator selected " + action + ".",
        )
        decisions = tuple(
            d for d in config.review_decisions if (d.kind, d.target) != (kind, target)
        ) + (decision,)
        return config.model_copy(update={"id": uuid4(), "review_decisions": decisions})

    # Retain the complete request receipt in immutable organization evidence for safe command
    # retries.
    def _replay(self, connection, workspace, actor, command):
        row = (
            connection.execute(
                select(operation).where(
                    operation.c.workspace_id == workspace,
                    operation.c.initiating_actor_subject == actor.key,
                    operation.c.client_request_key == command.client_request_key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row:
            if row["request_digest"] != canonical_hash(command.model_dump(mode="json")):
                raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
            return ActionReceipt(
                operation_id=row["id"],
                state=row["state"],
                provider_mode="simulated",
                accepted_at=row["accepted_at"].astimezone(UTC),
            )
        # Application-only decisions keep their replay receipt in immutable audit data.
        saved = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.workspace_id == workspace,
                audit_event.c.kind == "organization_review_decided",
                audit_event.c.actor_subject == actor.key,
                audit_event.c.data["request_key"].astext == str(command.client_request_key),
            )
        ).scalar_one_or_none()
        if saved:
            if saved["request_digest"] != canonical_hash(command.model_dump(mode="json")):
                raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
            return ActionReceipt.model_validate_json(json.dumps(saved["receipt"]))
        return None

    # All acceptance writes serialize with grant revocation, source import and other registry
    # commands.
    def act(self, principal, command):
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            prior = self._replay(connection, workspace, principal.actor, command)
            if prior:
                return prior
            state = registry_state(connection, workspace)
            require_context(state, command.context)
            preview = person_workflow(
                state, command.person_id, mode=self.mode, review_id=command.review_id
            )
            if command.action not in preview.actions:
                raise OrganizationConflict("ORGANIZATION_ACTION_UNAVAILABLE")
            person = state.people[command.person_id]
            review = next((r for r in state.reviews if r["id"] == command.review_id), None)
            config = state.config
            links = state.associations(person=person.id)
            if command.action == "cancel_simulation":
                return self._cancel_simulation(
                    connection, state, command, person, principal.actor, at
                )
            if command.action == "merge":
                config = self._merge(connection, state, command, principal.actor, at)
            elif command.action in {
                "ignore",
                "resolve",
                "no_tenancy_required",
                "reonboard",
                "mark_returned",
            } or (command.action == "offboard_person" and not links):
                config = self._application_decision(
                    connection, state, command, person, review, principal.actor, at
                )
            else:
                return self._admit(connection, state, command, person, review, principal, at)
            if review:
                connection.execute(
                    update(org_recommendation)
                    .where(
                        org_recommendation.c.workspace_id == workspace,
                        org_recommendation.c.id == review["id"],
                    )
                    .values(
                        status="ignored" if command.action == "ignore" else "resolved",
                        resolved_at=at,
                        resolution=command.action,
                    )
                )
            if config.id != state.config.id:
                self._reapply(connection, state, config, at)
            else:
                self._reconcile_current(connection, state, at)
            connection.execute(
                update(org_workspace)
                .where(org_workspace.c.id == workspace)
                .values(registry_revision=org_workspace.c.registry_revision + 1)
            )
            receipt = ActionReceipt(
                operation_id=None, state="succeeded", provider_mode="application", accepted_at=at
            )
            self._audit_decision(connection, state, command, principal.actor, at, person, receipt)
            return receipt

    # Close related onboarding/absence/LOB cases only for the explicitly decided stable identity.
    def _close_related(
        self, connection, state, identifiers, action, at, operation_id=None, *, include_lob=False
    ):
        connection.execute(
            update(org_recommendation)
            .where(
                org_recommendation.c.workspace_id == state.workspace,
                org_recommendation.c.person_id.in_(identifiers),
                org_recommendation.c.status == "open",
                org_recommendation.c.kind.in_(
                    ("TENANCY_SETUP_REVIEW", "PERSON_ABSENCE_REVIEW")
                    + (("LOB_MAPPING_REVIEW",) if include_lob else ())
                ),
            )
            .values(status="resolved", resolved_at=at, resolution=action, operation_id=operation_id)
        )

    # Metadata-only decisions are real application changes, not simulated OCI completions.
    def _application_decision(self, connection, state, command, person, review, actor, at):
        action = command.action
        links = state.associations(person=person.id)
        # A tenancy exemption preserves the source graph; offboarding the boundary is forbidden.
        if action == "offboard_person" and person.email == state.config.policy.root_email:
            raise OrganizationConflict("ORGANIZATION_ROOT_PROTECTED")
        if action == "ignore" and (review is None or review["kind"] != "LOB_MAPPING_REVIEW"):
            raise OrganizationConflict("IGNORE_REQUIRES_LOB_REVIEW")
        config = (
            self._decide(state.config, state, review, person, action, actor, at)
            if review and review["kind"] != "TENANCY_SETUP_REVIEW"
            else state.config
        )
        values = {}
        if action in {"no_tenancy_required", "offboard_person"}:
            if links or (action == "offboard_person" and not command.confirm_no_associations):
                raise OrganizationConflict("REVIEW_ALL_ASSOCIATIONS")
            values = dict(
                directory_status="exempt" if action == "no_tenancy_required" else "offboarded",
                setup_required=False,
                removed_capture_at=state.head.source_captured_at if person.absence_review else None,
            )
            self._close_related(connection, state, (person.id,), action, at, include_lob=True)
        elif action == "reonboard":
            if (
                links
                or person.email not in state.supplied
                or state.controls[person.id]["directory_status"] not in {"exempt", "offboarded"}
            ):
                raise OrganizationConflict("REONBOARD_REQUIRES_PRESENT_UNASSOCIATED_PERSON")
            values = dict(
                directory_status="included",
                setup_required=True,
                setup_episode_id=uuid4(),
                removed_capture_at=None,
            )
        elif action == "mark_returned":
            if person.email not in state.supplied:
                raise OrganizationConflict("PERSON_NOT_SOURCE_PRESENT")
            absence = next(
                (
                    r
                    for r in state.reviews
                    if r["person_id"] == person.id
                    and r["kind"] == "PERSON_ABSENCE_REVIEW"
                    and r["status"] == "open"
                ),
                None,
            )
            if absence:
                config = self._decide(state.config, state, absence, person, action, actor, at)
                self._close_related(connection, state, (person.id,), action, at)
            values = dict(
                directory_status="included",
                setup_required=not bool(links),
                setup_episode_id=uuid4()
                if not links
                else state.controls[person.id]["setup_episode_id"],
                removed_capture_at=None,
            )
        if values:
            connection.execute(
                update(org_person)
                .where(org_person.c.workspace_id == state.workspace, org_person.c.id == person.id)
                .values(**values)
            )
        return config

    # A deliberately paired identity merge preserves the absent survivor and registered
    # relationships.
    def _merge(self, connection, state, command, actor, at):
        subject = state.people[command.person_id]
        partner = state.people.get(command.partner_person_id)
        if partner is None or partner.id == subject.id:
            raise OrganizationConflict("IDENTITY_MERGE_PAIR_REQUIRED")
        old, new = (subject, partner) if subject.absence_review else (partner, subject)
        if (
            not old.absence_review
            or new.absence_review
            or old.email in state.supplied
            or new.email not in state.supplied
            or state.config.policy.root_email in {old.email, new.email}
        ):
            raise OrganizationConflict("IDENTITY_MERGE_PAIR_INVALID")
        old_case = next(
            (
                r
                for r in state.reviews
                if r["person_id"] == old.id
                and r["kind"] == "PERSON_ABSENCE_REVIEW"
                and r["status"] == "open"
            ),
            None,
        )
        new_case = next(
            (
                r
                for r in state.reviews
                if r["person_id"] == new.id
                and r["kind"] == "TENANCY_SETUP_REVIEW"
                and r["status"] == "open"
            ),
            None,
        )
        if (
            not old_case
            or not new_case
            or any(state.controls[p.id]["pending_operation_id"] for p in (old, new))
        ):
            raise OrganizationConflict("IDENTITY_MERGE_REVIEWS_CHANGED")
        if any(
            a["status"] != "active"
            or a["operation_id"]
            or state.tenancies[a["tenancy_id"]]["operation_id"]
            for p in (old, new)
            for a in state.associations(person=p.id)
        ):
            raise OrganizationConflict("IDENTITY_HAS_PENDING_WORK")

        # Source references are rebased only after the administrator confirms this exact pair.
        def renamed(address):
            return new.email if address == old.email else address

        config = self._decide(state.config, state, old_case, old, "merge", actor, at)
        decisions = tuple(
            d.model_copy(
                update={
                    "target": ":".join(renamed(part) for part in d.target.split(":")),
                    "person_id": old.id if d.person_id == new.id else d.person_id,
                }
            )
            for d in config.review_decisions
        )
        overrides = []
        for override in config.overrides:
            if override.email in {old.email, new.email} and any(
                o.email == new.email for o in overrides
            ):
                raise OrganizationConflict("MERGE_OVERRIDE_CONFLICT")
            overrides.append(
                override.model_copy(
                    update={
                        "email": renamed(override.email),
                        "values": {
                            k: renamed(v) if k == "manager_email" else v
                            for k, v in override.values.items()
                        },
                    }
                )
            )
        config = config.model_copy(
            update={
                "id": uuid4(),
                "identity_merges": (
                    *config.identity_merges,
                    IdentityMerge(
                        old_email=old.email,
                        new_email=new.email,
                        person_id=old.id,
                        retired_person_id=new.id,
                        actor=actor.key,
                        reason="Administrator explicitly paired an absent and new identity.",
                    ),
                ),
                "review_decisions": decisions,
                "overrides": tuple(overrides),
                "lobs": tuple(
                    lob.model_copy(
                        update={
                            "leader_email": renamed(lob.leader_email),
                            "designee_emails": tuple(renamed(e) for e in lob.designee_emails),
                        }
                    )
                    for lob in config.lobs
                ),
                "supplemental_edges": tuple(
                    edge.model_copy(
                        update={
                            "employee_email": renamed(edge.employee_email),
                            "manager_email": renamed(edge.manager_email),
                        }
                    )
                    for edge in config.supplemental_edges
                ),
            }
        )
        config = Configuration.model_validate(config.model_dump(mode="python"))
        old_links = {a["tenancy_id"]: a for a in state.associations(person=old.id)}
        for link in state.associations(person=new.id):
            duplicate = old_links.get(link["tenancy_id"])
            if duplicate and (link["role"] != "owner" or duplicate["role"] == "owner"):
                connection.execute(
                    update(tenancy_membership)
                    .where(
                        tenancy_membership.c.workspace_id == state.workspace,
                        tenancy_membership.c.id == link["id"],
                    )
                    .values(status="removed", updated_at=at, revision=link["revision"] + 1)
                )
            else:
                if duplicate:
                    connection.execute(
                        update(tenancy_membership)
                        .where(
                            tenancy_membership.c.workspace_id == state.workspace,
                            tenancy_membership.c.id == duplicate["id"],
                        )
                        .values(status="removed", updated_at=at, revision=duplicate["revision"] + 1)
                    )
                connection.execute(
                    update(tenancy_membership)
                    .where(
                        tenancy_membership.c.workspace_id == state.workspace,
                        tenancy_membership.c.id == link["id"],
                    )
                    .values(person_id=old.id, updated_at=at, revision=link["revision"] + 1)
                )
        connection.execute(
            update(org_person)
            .where(org_person.c.workspace_id == state.workspace, org_person.c.id == new.id)
            .values(directory_status="merged", setup_required=False)
        )
        connection.execute(
            update(org_person)
            .where(org_person.c.workspace_id == state.workspace, org_person.c.id == old.id)
            .values(
                directory_status="included",
                setup_required=False,
                setup_episode_id=uuid4(),
                removed_capture_at=None,
            )
        )
        self._close_related(connection, state, (old.id, new.id), "merge", at, include_lob=True)
        return config

    # Bind the exact full association plan and refuse parent, shared-owner and recipient mistakes.
    def _plan(self, state, command, person):
        links = state.associations(person=person.id)
        if command.action == "offboard_person":
            if len(command.plan) != len(links) or {p.association_id for p in command.plan} != {
                a["id"] for a in links
            }:
                raise OrganizationConflict("REVIEW_ALL_ASSOCIATIONS")
            choices = command.plan
        else:
            link = next((a for a in links if a["tenancy_id"] == command.tenancy_id), None)
            if not link:
                raise OrganizationConflict("REGISTERED_ASSOCIATION_REQUIRED")
            action = {
                "delete_tenancy": "delete",
                "remove_member": "remove",
                "transfer_owner": "transfer",
            }[command.action]
            choices = (
                AssociationChoice(
                    association_id=link["id"],
                    action=action,
                    recipient_person_id=command.recipient_person_id,
                ),
            )
        frozen = []
        for choice in choices:
            link = next(a for a in links if a["id"] == choice.association_id)
            row = state.tenancies[link["tenancy_id"]]
            allowed = association_view(state, link).actions
            if (
                choice.action not in allowed
                or link["status"] != "active"
                or row["status"] != "active"
                or row["operation_id"]
            ):
                raise OrganizationConflict("ASSOCIATION_PLAN_CHANGED")
            if (
                row["provider_mode"] != "simulated"
                or row["parent_tenancy_ocid"] != self.policy.parent_tenancy_ocid
                or row["organization_id"] != self.policy.organization_id
                or row["tenancy_ocid"] == self.policy.parent_tenancy_ocid
            ):
                raise OrganizationConflict("REGISTERED_CHILD_REQUIRED")
            if choice.action == "transfer" and (
                choice.recipient_person_id == person.id
                or not state.eligible(choice.recipient_person_id)
            ):
                raise OrganizationConflict("CURRENT_TRANSFER_RECIPIENT_REQUIRED")
            if choice.action == "delete" and person.known_manager and not command.confirm_manager:
                raise OrganizationConflict("MANAGER_CONFIRMATION_REQUIRED")
            if row["kind"] == "shared" and choice.action != "keep" and not command.confirm_shared:
                raise OrganizationConflict("SHARED_CONFIRMATION_REQUIRED")
            recipient_link = (
                next(
                    iter(state.associations(person=choice.recipient_person_id, tenant=row["id"])),
                    None,
                )
                if choice.action == "transfer"
                else None
            )
            frozen.append(
                FrozenAssociation(
                    id=link["id"],
                    tenancy_id=row["id"],
                    tenancy_revision=row["revision"],
                    role=link["role"],
                    action=choice.action,
                    tenancy_ocid=row["tenancy_ocid"],
                    parent_tenancy_ocid=row["parent_tenancy_ocid"],
                    recipient_person_id=choice.recipient_person_id,
                    new_association_id=uuid4() if choice.action == "transfer" else None,
                    recipient_user_ocid=recipient_link["user_ocid"] if recipient_link else None,
                    recipient_compartment_ocid=recipient_link["compartment_ocid"]
                    if recipient_link
                    else None,
                    recipient_compartment_name=recipient_link["compartment_name"]
                    if recipient_link
                    else None,
                    recipient_parent_compartment_ocid=recipient_link["parent_compartment_ocid"]
                    if recipient_link
                    else None,
                    user_ocid=link["user_ocid"],
                    compartment_ocid=link["compartment_ocid"],
                )
            )
        return tuple(frozen)

    # Accept mutation intent, pending reservations, review closure and native job atomically.
    def _admit(
        self,
        connection,
        state,
        command,
        person,
        review,
        principal,
        at,
        *,
        deletion_plan=None,
        request_digest=None,
    ):
        if self.mode != "simulated" or self.policy.workspace_id != state.workspace:
            raise OrganizationConflict("LIFECYCLE_PROVIDER_UNAVAILABLE")
        if self.policy_loader is not None:
            current = self.policy_loader()
            if current.execution_paused or current.policy != self.policy:
                raise OrganizationConflict("LIFECYCLE_PROVIDER_UNAVAILABLE")
        key, event_id = uuid4(), uuid4()
        tenant_id, association_id, target_ocid = None, None, None
        plan = ()
        baseline = None
        if command.action in {
            "create_tenancy",
            "import_tenancy",
            "join_shared",
        } and not has_valid_accountability(person, state.config):
            raise OrganizationConflict("ACCOUNTABILITY_MAPPING_REQUIRED")
        if command.action in {"create_tenancy", "import_tenancy"}:
            if command.action == "create_tenancy":
                if not command.name or not re.fullmatch(r"[a-z0-9]{1,200}", command.name):
                    raise OrganizationConflict("VALID_CREATE_NAME_REQUIRED")
                if not command.home_region or command.home_region not in {
                    r.identifier for r in self.facade.creation_regions()
                }:
                    raise OrganizationConflict("PARENT_SUBSCRIBED_REGION_REQUIRED")
            if (command.action == "import_tenancy") != (command.import_ocid is not None):
                raise OrganizationConflict("EXACT_IMPORT_TARGET_REQUIRED")
            name = (
                command.name
                if command.action == "create_tenancy"
                else "Pending setup " + key.hex[:8]
            )
            if not name or any(
                t["status"] not in {"terminated", "cancelled"}
                and t["name"].casefold() == name.casefold()
                for t in state.tenancies.values()
            ):
                raise OrganizationConflict("DISTINCT_TENANCY_NAME_REQUIRED")
            tenant_id, association_id = uuid4(), uuid4()
            target_ocid = command.import_ocid or "ocid1.tenancy.oc1..otmsim" + tenant_id.hex
            if (
                not target_ocid.startswith("ocid1.tenancy.oc1..otmsim")
                or target_ocid == self.policy.parent_tenancy_ocid
            ):
                raise OrganizationConflict("SIMULATED_CHILD_REQUIRED")
            if any(t["tenancy_ocid"] == target_ocid for t in state.tenancies.values()):
                raise OrganizationConflict("TENANCY_ALREADY_REGISTERED")
        elif command.action == "join_shared":
            row = state.tenancies.get(command.tenancy_id)
            if (
                not row
                or row["kind"] != "shared"
                or row["status"] != "active"
                or row["operation_id"]
                or state.associations(person=person.id, tenant=row["id"])
            ):
                raise OrganizationConflict("AVAILABLE_SHARED_TENANCY_REQUIRED")
            choices = {p.ocid: p for p in self.facade.compartments(row["tenancy_ocid"])}
            if command.existing_compartment_ocid is not None:
                if (
                    command.existing_compartment_ocid not in choices
                    or command.existing_compartment_ocid == row["tenancy_ocid"]
                ):
                    raise OrganizationConflict("EXISTING_COMPARTMENT_REQUIRED")
            else:
                if not command.compartment_name or not command.compartment_name.strip():
                    raise OrganizationConflict("SHARED_COMPARTMENT_NAME_REQUIRED")
                if command.parent_compartment_ocid not in choices:
                    raise OrganizationConflict("EXISTING_PARENT_COMPARTMENT_REQUIRED")
            tenant_id, association_id, target_ocid = row["id"], uuid4(), row["tenancy_ocid"]
        else:
            plan = (
                deletion_plan if deletion_plan is not None else self._plan(state, command, person)
            )
            if command.tenancy_id:
                target_ocid = state.tenancies[command.tenancy_id]["tenancy_ocid"]
        if command.action in {"create_tenancy", "import_tenancy"}:
            baseline = current_baseline(connection, state.workspace)
            if baseline is None:
                raise OrganizationConflict("PUBLISHED_BASELINE_REQUIRED")
        grant = connection.execute(
            select(org_person.c.id).where(
                org_person.c.workspace_id == state.workspace, org_person.c.id == person.id
            )
        ).scalar_one()
        if grant != person.id:
            raise OrganizationConflict("ORGANIZATION_PERSON_NOT_FOUND")
        from otm.storage.tables import administrator

        admin = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == state.workspace,
                    administrator.c.issuer == principal.session.issuer,
                    administrator.c.subject == principal.session.subject,
                )
            )
            .mappings()
            .one()
        )
        targets = {person.id: person.email}
        for association in plan:
            if association.recipient_person_id in state.people:
                recipient = state.people[association.recipient_person_id]
                targets[recipient.id] = recipient.email
        contacts = self._email_contacts(connection, principal, person.email, targets)
        if contacts:
            from otm.email_policy import EmailPolicyBlocked

            try:
                if command.action == "create_tenancy":
                    self.mail_policy.guard(contacts.activation)
                if command.action in {
                    "create_tenancy",
                    "import_tenancy",
                    "join_shared",
                    "transfer_owner",
                } or any(a.action == "transfer" for a in plan):
                    self.mail_policy.guard(contacts.owner)
                    for route in contacts.people.values():
                        self.mail_policy.guard(route)
            except EmailPolicyBlocked:
                raise OrganizationConflict("EMAIL_CONTACT_CONFIGURATION_REQUIRED") from None
        intent = OrganizationIntent(
            workspace_id=state.workspace,
            policy_revision=self.policy.policy_revision,
            organization_id=self.policy.organization_id,
            parent_tenancy_ocid=self.policy.parent_tenancy_ocid,
            administrator_id=admin["id"],
            authorization_revision=admin["authorization_revision"],
            action=command.action,
            baseline=baseline,
            whole_tenancy_deletion=deletion_plan is not None,
            onboarding_version=2
            if command.action in {"create_tenancy", "import_tenancy"}
            else None,
            activation_email=contacts.activation.effective_email
            if contacts
            else admin["email"]
            if admin["identity_kind"] == "corporate_sso"
            else None,
            email_contacts=contacts,
            target=LifecycleTarget(
                tenancy_ocid=target_ocid,
                person_id=person.id,
                display_name=state.tenancies[command.tenancy_id]["name"]
                if deletion_plan is not None
                else person.full_name or person.email,
            ),
            person_was_absent=person.absence_review,
            person_was_manager=person.known_manager,
            pending_tenancy_id=tenant_id,
            pending_association_id=association_id,
            name=command.name if command.action == "create_tenancy" else None,
            tenancy_kind=command.tenancy_kind,
            home_region=command.home_region if command.action == "create_tenancy" else None,
            parent_compartment_ocid=command.parent_compartment_ocid,
            compartment_name=command.compartment_name,
            existing_compartment_ocid=command.existing_compartment_ocid,
            associations=plan,
        )
        data = IntentEventData(intent=intent, actor=principal.actor).model_dump(mode="json")
        connection.execute(
            operation.insert().values(
                id=key,
                workspace_id=state.workspace,
                kind="organization_action",
                initiating_actor_subject=principal.actor.key,
                initiating_actor_snapshot=principal.actor.model_dump(mode="json"),
                responsible_actor_subject=principal.actor.key,
                client_request_key=command.client_request_key,
                request_digest=request_digest or canonical_hash(command.model_dump(mode="json")),
                current_intent_revision=1,
                current_intent_event_id=event_id,
                state="queued",
                stage="Waiting for simulated lifecycle worker",
                wait_reason=None,
                effect_knowledge="none",
                revision=1,
                accepted_at=at,
                created_at=at,
                updated_at=at,
            )
        )
        connection.execute(
            audit_event.insert().values(
                id=event_id,
                workspace_id=state.workspace,
                operation_id=key,
                administrator_id=None,
                intent_revision=1,
                actor=principal.actor.key,
                actor_subject=principal.actor.key,
                actor_snapshot=principal.actor.model_dump(mode="json"),
                kind="operation_intent",
                at=at,
                contract_version="organization-action-1",
                data=data,
                data_hash=canonical_hash(data),
            )
        )
        if command.action in {"create_tenancy", "import_tenancy"}:
            connection.execute(
                tenancy.insert().values(
                    id=tenant_id,
                    workspace_id=state.workspace,
                    name=name,
                    baseline_version_id=baseline.id,
                    tenancy_ocid=target_ocid,
                    parent_tenancy_ocid=self.policy.parent_tenancy_ocid,
                    organization_id=self.policy.organization_id,
                    home_region=command.home_region
                    if command.action == "create_tenancy"
                    else "Pending discovery",
                    kind=command.tenancy_kind,
                    status="pending",
                    provider_mode="simulated",
                    origin="create" if command.action == "create_tenancy" else "import",
                    operation_id=key,
                    last_operation_id=key,
                    created_at=at,
                    updated_at=at,
                )
            )
        if association_id:
            connection.execute(
                tenancy_membership.insert().values(
                    id=association_id,
                    workspace_id=state.workspace,
                    tenancy_id=tenant_id,
                    person_id=person.id,
                    role="member" if command.action == "join_shared" else "owner",
                    status="pending",
                    compartment_name=(
                        choices[command.existing_compartment_ocid].name
                        if command.existing_compartment_ocid
                        else command.compartment_name
                    )
                    if command.action == "join_shared"
                    else None,
                    compartment_ocid=command.existing_compartment_ocid,
                    parent_compartment_ocid=command.parent_compartment_ocid,
                    operation_id=key,
                    created_at=at,
                    updated_at=at,
                )
            )
            connection.execute(
                update(tenancy)
                .where(tenancy.c.workspace_id == state.workspace, tenancy.c.id == tenant_id)
                .values(operation_id=key, last_operation_id=key)
            )
        for item in plan:
            if item.action != "keep":
                connection.execute(
                    update(tenancy)
                    .where(
                        tenancy.c.workspace_id == state.workspace, tenancy.c.id == item.tenancy_id
                    )
                    .values(
                        operation_id=key,
                        last_operation_id=key,
                        **({"status": "terminating"} if deletion_plan is not None else {}),
                    )
                )
                connection.execute(
                    update(tenancy_membership)
                    .where(
                        tenancy_membership.c.workspace_id == state.workspace,
                        tenancy_membership.c.id == item.id,
                    )
                    .values(
                        operation_id=key,
                        **({"status": "removing"} if deletion_plan is not None else {}),
                    )
                )
        for recipient_id in {
            item.recipient_person_id for item in plan if item.action == "transfer"
        }:
            connection.execute(
                update(org_person)
                .where(
                    org_person.c.workspace_id == state.workspace, org_person.c.id == recipient_id
                )
                .values(pending_operation_id=key, setup_required=False)
            )
            self._close_related(
                connection, state, (recipient_id,), command.action, at, operation_id=key
            )
        connection.execute(
            update(org_person)
            .where(org_person.c.workspace_id == state.workspace, org_person.c.id == person.id)
            .values(pending_operation_id=key, setup_required=False)
        )
        if deletion_plan is not None:
            connection.execute(
                update(org_person)
                .where(
                    org_person.c.workspace_id == state.workspace,
                    org_person.c.id.in_([a.person_id for a in deletion_plan]),
                )
                .values(pending_operation_id=key)
            )
        else:
            self._close_related(
                connection, state, (person.id,), command.action, at, operation_id=key
            )
        if review and review["kind"] == "PERSON_ABSENCE_REVIEW":
            config = self._decide(
                state.config, state, review, person, command.action, principal.actor, at
            )
            self._reapply(connection, state, config, at)
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == state.workspace)
            .values(registry_revision=org_workspace.c.registry_revision + 1)
        )
        self.enqueuer.enqueue(connection, key)
        receipt = ActionReceipt(
            operation_id=key, state="queued", provider_mode="simulated", accepted_at=at
        )
        self._audit_decision(
            connection,
            state,
            command,
            principal.actor,
            at,
            person,
            receipt,
            request_digest=request_digest,
        )
        return receipt

    # Cancellation is local-simulator-only and serializes with execution; verified effects are
    # never undone.
    def _cancel_simulation(self, connection, state, command, person, actor, at):
        identifier = state.controls[person.id]["pending_operation_id"]
        row = (
            connection.execute(
                select(operation)
                .where(operation.c.workspace_id == state.workspace, operation.c.id == identifier)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            self.mode != "simulated"
            or identifier is None
            or command.operation_id != identifier
            or row is None
            or row["kind"] != "organization_action"
            or row["state"] not in {"queued", "waiting", "needs_attention", "failed"}
            or row["effect_knowledge"] != "none"
        ):
            raise OrganizationConflict("SIMULATION_ALREADY_FINISHED")
        frozen_event = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.workspace_id == state.workspace,
                    audit_event.c.id == row["current_intent_event_id"],
                    audit_event.c.operation_id == identifier,
                )
            )
            .mappings()
            .one()
        )
        if canonical_hash(frozen_event["data"]) != frozen_event["data_hash"]:
            raise ValueError("INVALID_ORGANIZATION_INTENT_EVIDENCE")
        frozen = IntentEventData.model_validate_json(json.dumps(frozen_event["data"]))
        if (
            not isinstance(frozen.intent, OrganizationIntent)
            or frozen.intent.target.person_id != person.id
            or frozen.intent.workspace_id != state.workspace
        ):
            raise OrganizationConflict("ORGANIZATION_PREVIEW_CHANGED")
        intent = frozen.intent
        if any(
            t["provider_mode"] != "simulated"
            for t in state.tenancies.values()
            if t["operation_id"] == identifier
        ):
            raise OrganizationConflict("SIMULATED_CHILD_REQUIRED")
        connection.execute(
            update(tenancy_membership)
            .where(
                tenancy_membership.c.workspace_id == state.workspace,
                tenancy_membership.c.operation_id == identifier,
                tenancy_membership.c.status == "pending",
            )
            .values(
                status="removed",
                operation_id=None,
                updated_at=at,
                revision=tenancy_membership.c.revision + 1,
            )
        )
        connection.execute(
            update(tenancy_membership)
            .where(
                tenancy_membership.c.workspace_id == state.workspace,
                tenancy_membership.c.operation_id == identifier,
            )
            .values(
                operation_id=None, **({"status": "active"} if intent.whole_tenancy_deletion else {})
            )
        )
        for tenant_row in state.tenancies.values():
            if tenant_row["operation_id"] == identifier:
                connection.execute(
                    update(tenancy)
                    .where(
                        tenancy.c.workspace_id == state.workspace, tenancy.c.id == tenant_row["id"]
                    )
                    .values(
                        status="cancelled"
                        if tenant_row["status"] == "pending" and not tenant_row["verified_at"]
                        else "active"
                        if intent.whole_tenancy_deletion
                        else tenant_row["status"],
                        operation_id=None,
                        updated_at=at,
                        revision=tenant_row["revision"] + 1,
                    )
                )
        handed = tuple(
            r
            for r in state.reviews
            if r["operation_id"] == identifier and r["category"] == "actionable"
        )
        setup_ids = {r["person_id"] for r in handed if r["kind"] == "TENANCY_SETUP_REVIEW"}
        affected = (
            {person.id}
            | {a.person_id for a in intent.associations if intent.whole_tenancy_deletion}
            | {a.recipient_person_id for a in intent.associations if a.action == "transfer"}
        )
        for key in affected:
            connection.execute(
                update(org_person)
                .where(
                    org_person.c.workspace_id == state.workspace,
                    org_person.c.id == key,
                    org_person.c.pending_operation_id == identifier,
                )
                .values(pending_operation_id=None, setup_required=key in setup_ids)
            )
        config = state.config
        absence_targets = {r["target"] for r in handed if r["kind"] == "PERSON_ABSENCE_REVIEW"}
        if absence_targets:
            config = config.model_copy(
                update={
                    "id": uuid4(),
                    "review_decisions": tuple(
                        d
                        for d in config.review_decisions
                        if not (d.kind == "PERSON_ABSENCE_REVIEW" and d.target in absence_targets)
                    ),
                }
            )
        for case in handed:
            candidate = state.people.get(case["person_id"])
            if candidate and (
                case["kind"] == "PERSON_ABSENCE_REVIEW" or candidate.email in state.supplied
            ):
                connection.execute(
                    update(org_recommendation)
                    .where(
                        org_recommendation.c.workspace_id == state.workspace,
                        org_recommendation.c.id == case["id"],
                    )
                    .values(
                        status="open",
                        resolved_at=None,
                        resolution=None,
                        operation_id=None,
                        last_seen_at=at,
                    )
                )
        connection.execute(
            update(operation)
            .where(operation.c.workspace_id == state.workspace, operation.c.id == identifier)
            .values(
                state="cancelled",
                stage="Local simulation cancelled by administrator",
                completed_at=at,
                updated_at=at,
                revision=row["revision"] + 1,
            )
        )
        if config.id != state.config.id:
            self._reapply(connection, state, config, at)
        else:
            self._reconcile_current(connection, state, at)
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == state.workspace)
            .values(registry_revision=org_workspace.c.registry_revision + 1)
        )
        receipt = ActionReceipt(
            operation_id=identifier, state="cancelled", provider_mode="application", accepted_at=at
        )
        self._audit_decision(connection, state, command, actor, at, person, receipt)
        return receipt

    # Record bounded identities, action, request digest and committed receipt; never dump
    # source/config.
    def _audit_decision(
        self, connection, state, command, actor, at, person, receipt, *, request_digest=None
    ):
        self.store._audit(
            connection,
            state.workspace,
            actor,
            "organization_review_decided",
            at,
            state.config,
            review_id=command.review_id,
            person_id=person.id,
            action=command.action,
            subject_name=person.full_name or person.email,
            request_key=command.client_request_key,
            request_digest=request_digest or canonical_hash(command.model_dump(mode="json")),
            receipt=receipt,
            applied_version_id=command.context.applied_version_id,
        )

    # Directory rows, association counts and inbox cards share the exact same read-only snapshot.
    def organization_directory(self, principal, query, initial, *, test_reset_enabled=False):
        from otm.organization.views import EmployeeView, OrganizationDirectory
        from otm.storage.organization import outcome

        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            header = (
                connection.execute(select(org_workspace).where(org_workspace.c.id == workspace))
                .mappings()
                .one_or_none()
            )
            current = (
                registry_state(connection, workspace)
                if header and header["applied_version_id"]
                else None
            )
            latest = (
                connection.execute(
                    select(org_feed)
                    .where(org_feed.c.workspace_id == workspace)
                    .order_by(org_feed.c.received_at.desc(), org_feed.c.id.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
                if header
                else None
            )
            rows, all_rows = [], []
            if current:
                by_email = {p.email: p for p in current.head.people}
                lob_names = {lob.id: lob.label for lob in current.config.lobs}
                absence = {
                    r["person_id"]
                    for r in current.reviews
                    if r["kind"] == "PERSON_ABSENCE_REVIEW" and r["status"] == "open"
                }
                for person in current.head.people:
                    if person.profile != "employee":
                        continue
                    control = current.controls[person.id]
                    manager = by_email.get(person.manager_email)
                    leader = by_email.get(person.accountable_leader_email)
                    links = current.associations(person=person.id)
                    row = EmployeeView(
                        id=person.id,
                        full_name=person.full_name or person.email,
                        email=person.email,
                        manager_name=manager.full_name or manager.email
                        if manager
                        else person.manager_email,
                        leader_name=leader.full_name or leader.email
                        if leader
                        else person.accountable_leader_email,
                        lob_name=lob_names.get(person.lob_id),
                        absence_review=person.id in absence,
                        tenancy_count=sum(a["status"] in {"active", "removing"} for a in links),
                        pending_tenancy_count=sum(a["status"] == "pending" for a in links),
                        directory_status=control["directory_status"],
                        pending_operation_id=control["pending_operation_id"],
                    )
                    all_rows.append(row)
                rows = [
                    p
                    for p in all_rows
                    if query.include_removed or p.directory_status in {"included", "outside"}
                ]
            visible = [p for p in all_rows if p.directory_status in {"included", "outside"}]
            filtered = [
                p
                for p in rows
                if query.query.casefold()
                in " ".join(
                    (
                        p.full_name,
                        p.email,
                        p.manager_name or "",
                        p.leader_name or "",
                        p.lob_name or "",
                    )
                ).casefold()
            ]
            filtered.sort(
                key=lambda p: (
                    p.tenancy_count
                    if query.sort == "tenancy_count"
                    else (getattr(p, query.sort) or "").casefold(),
                    p.email,
                ),
                reverse=query.direction == "desc",
            )
            pages = max(1, (len(filtered) + query.page_size - 1) // query.page_size)
            page = min(query.page, pages)
            reviews = current.reviews if current else ()
            return OrganizationDirectory(
                configured=header is not None,
                upload_enabled=bool(header and header["configuration"].get("lobs")),
                server_time=self.store.clock(),
                items=tuple(filtered[(page - 1) * query.page_size : page * query.page_size]),
                total=len(filtered),
                employee_count=len(visible),
                absence_count=sum(p.absence_review for p in visible),
                page=page,
                pages=pages,
                page_size=query.page_size,
                applied_at=current.head.published_at if current else None,
                source_as_of=current.head.source_captured_at if current else None,
                absence_eligible=current.head.absence_eligible if current else False,
                latest=outcome(latest) if latest else None,
                findings=(),
                test_reset_enabled=test_reset_enabled,
                pending_workflows=sum(
                    bool(c["pending_operation_id"]) for c in current.controls.values()
                )
                if current
                else 0,
                workflows_enabled=True,
                provider_mode=self.mode,
                actionable_count=sum(
                    r["category"] == "actionable" and r["status"] == "open" for r in reviews
                ),
                history_count=sum(
                    r["category"] != "actionable" or r["status"] != "open" for r in reviews
                ),
            )
