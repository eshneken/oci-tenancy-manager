"""Workspace-scoped, read-only views over existing operation, intent and step authorities."""

import json
from datetime import UTC
from uuid import UUID

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.engine import Engine

from otm.configuration.drift_contracts import ConfigurationCheckEvidence
from otm.configuration.rollout_contracts import ConfigurationOutcome, ConfigurationRetryEvidence
from otm.financial.contracts import CostEvidence
from otm.notifications.contracts import NotificationEvidence
from otm.notifications.service import list_for_operation
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.operations.execution_contracts import InspectionOutcome
from otm.operations.responsibility import ResponsibilityEvidence, eligible, execution_authority
from otm.operations.views import (
    OperationDetail,
    OperationDirectory,
    OperationEventView,
    OperationQuery,
    OperationStepView,
    OperationSummary,
    RecoveryPasswordProgress,
    UserCheckFact,
    UserCheckSection,
)
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    operation_step,
    org_person,
    recovery_grant,
    tenancy,
)
from otm.tenancies.automation_keys import inventory_view
from otm.tenancies.contracts import OrganizationActionOutcome
from otm.tenancies.labels import ACTION_LABELS
from otm.tenancies.onboarding_contracts import OnboardingEvidence
from otm.tenancies.presence_contracts import PresenceCheckEvidence
from otm.tenancies.recovery_network_contracts import RecoveryNetworkEvidence
from otm.tenancies.recovery_password_contracts import (
    RecoveryDisclosureEvidence,
    RecoveryPasswordEvidence,
)
from otm.tenancies.signing_key_contracts import (
    SigningKeyEvidence,
    SigningKeyRequestEvidence,
    signing_event_summary,
)


# Reconstruct only the five historical check summaries from validated immutable event evidence.
def user_check_sections(evidence):
    sections = []
    for observation, assignment in zip(
        evidence.results,
        (evidence.administrator_access, evidence.recovery_administrator_access),
        strict=True,
    ):
        purpose = observation.target.purpose
        sections.append(
            UserCheckSection(
                anchor=f"{purpose}-presence",
                checked_at=observation.captured_at,
                facts=(UserCheckFact(label="Presence", state=observation.state),),
            )
        )
        sections.append(
            UserCheckSection(
                anchor=f"{purpose}-assignment",
                checked_at=assignment.checked_at if assignment else None,
                facts=tuple(
                    UserCheckFact(
                        label=label,
                        state=getattr(assignment.result, key) if assignment else "not_checked",
                    )
                    for label, key in (
                        ("Administrators group", "group"),
                        ("Domain administrator role", "domain_role"),
                    )
                ),
            )
        )
    policy = evidence.recovery_console
    sections.append(
        UserCheckSection(
            anchor="recovery-policy",
            checked_at=policy.checked_at if policy else None,
            facts=tuple(
                UserCheckFact(
                    label=label, state=getattr(policy.result, key) if policy else "not_checked"
                )
                for label, key in (
                    ("Console MFA exemption", "mfa_exemption"),
                    ("Approved-network restriction", "network_boundary"),
                )
            ),
        )
    )
    return tuple(sections)


# Read the original window; later rotations and current heads cannot rewrite its history.
def password_progress(connection, row, intent):
    if intent.kind != "recovery_password" or row["kind"] != intent.kind:
        raise ValueError("INVALID_RECOVERY_PROGRESS")
    first = None
    count = 0
    if intent.phase == "rotation":
        count, first, last, earliest_due, latest_due = connection.execute(
            select(
                func.count(),
                func.min(recovery_grant.c.first_disclosure_attempt_at),
                func.max(recovery_grant.c.first_disclosure_attempt_at),
                func.min(recovery_grant.c.due_at),
                func.max(recovery_grant.c.due_at),
            ).where(
                recovery_grant.c.workspace_id == row["workspace_id"],
                recovery_grant.c.accepted_operation_id == row["id"],
                recovery_grant.c.credential_id == intent.credential_id,
                recovery_grant.c.tenancy_id == intent.location.target.tenancy_id,
                recovery_grant.c.exposure_generation == intent.exposure_generation,
            )
        ).one()
        if first != last or earliest_due != intent.due_at or latest_due != intent.due_at:
            raise ValueError("INVALID_RECOVERY_PROGRESS")
    return RecoveryPasswordProgress(
        phase=intent.phase,
        tenancy_id=intent.location.target.tenancy_id,
        user_name=intent.location.target.user_name,
        first_request_at=utc(first),
        rotation_due_at=intent.due_at,
        request_count=count,
    )


# Convert stored timestamps to UTC without substituting a retrieval time for missing evidence.
def utc(value):
    return value.astimezone(UTC) if value is not None else None


# Read existing authorities without starting jobs, changing status or touching provider credentials.
class SqlOperationDirectory:
    # Use the explicitly injected restricted application engine; construction opens no connection.
    def __init__(self, engine: Engine):
        self.engine = engine

    # Concurrent workers cannot mix an old operation with newer steps or count/page results.
    def snapshot(self):
        return read_snapshot(self.engine)

    # Follow the exact committed intent pointer, including workspace and positive revision.
    def joined(self):
        return operation.join(
            audit_event,
            and_(
                audit_event.c.workspace_id == operation.c.workspace_id,
                audit_event.c.operation_id == operation.c.id,
                audit_event.c.id == operation.c.current_intent_event_id,
                audit_event.c.intent_revision == operation.c.current_intent_revision,
                audit_event.c.kind == "operation_intent",
            ),
        )

    # Select public-source data explicitly; response models never serialize a whole database row.
    def selection(self):
        return select(
            operation,
            audit_event.c.data.label("intent_data"),
            audit_event.c.data_hash.label("intent_hash"),
            tenancy.c.id.label("registered_tenancy_id"),
        ).select_from(
            self.joined().outerjoin(
                tenancy,
                and_(
                    tenancy.c.workspace_id == operation.c.workspace_id,
                    tenancy.c.tenancy_ocid
                    == audit_event.c.data["intent"]["target"]["tenancy_ocid"].astext,
                ),
            )
        )

    # Reject malformed or mismatched immutable data instead of displaying a misleading OCI target.
    def summary(self, row):
        frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
        if (
            canonical_hash(row["intent_data"]) != row["intent_hash"]
            or frozen.intent.workspace_id != row["workspace_id"]
            or frozen.actor.key != row["initiating_actor_subject"]
        ):
            raise ValueError("INVALID_OPERATION_EVIDENCE")
        return OperationSummary(
            id=row["id"],
            kind=row["kind"],
            state=row["state"],
            stage=row["stage"],
            accepted_at=utc(row["accepted_at"]),
            scheduled_for=frozen.intent.due_at
            if frozen.intent.kind == "signing_key"
            and frozen.intent.phase == "rotation"
            and row["state"] == "waiting"
            and row.get("wait_reason") == "signing_rotation_due"
            else None,
            updated_at=utc(row["updated_at"]),
            completed_at=utc(row["completed_at"]),
            initiated_by=frozen.actor.display_name,
            result_tenancy_id=row.get("registered_tenancy_id")
            if (row["state"] == "succeeded" or frozen.intent.kind == "signing_key")
            and frozen.intent.kind
            in {
                "organization_action",
                "configuration_update",
                "configuration_check",
                "cost_collection",
                "required_user_check",
                "recovery_network_repair",
                "recovery_password",
                "signing_key",
            }
            else None,
            guided_onboarding=frozen.intent.kind == "organization_action"
            and frozen.intent.onboarding_version in {1, 2, 3, 4},
            target_tenancy_ocid=frozen.intent.target.tenancy_ocid,
            title=ACTION_LABELS[frozen.intent.action]
            if frozen.intent.kind == "organization_action"
            else (
                "Prepare recovery password"
                if frozen.intent.phase == "setup"
                else "Rotate recovery password"
            )
            if frozen.intent.kind == "recovery_password"
            else "Rotate automation signing key"
            if frozen.intent.kind == "signing_key" and frozen.intent.phase == "rotation"
            else "Prepare automation signing credential"
            if frozen.intent.kind == "signing_key"
            else "Repair approved recovery networks"
            if frozen.intent.kind == "recovery_network_repair"
            else "Check required users"
            if frozen.intent.kind == "required_user_check"
            else "Refresh current month costs"
            if frozen.intent.kind == "cost_collection"
            else "Check configuration"
            if frozen.intent.kind == "configuration_check"
            else "Update tenancy overrides"
            if frozen.intent.kind == "configuration_update"
            and frozen.intent.change_kind == "override_change"
            else "Repair assigned configuration"
            if frozen.intent.kind == "configuration_update"
            and frozen.intent.change_kind == "repair"
            else f"Update baseline v{frozen.intent.baseline.version_number}"
            if frozen.intent.kind == "configuration_update"
            else None,
            target_label=frozen.intent.target.display_name
            if frozen.intent.kind
            in {
                "organization_action",
                "configuration_update",
                "configuration_check",
                "cost_collection",
                "required_user_check",
                "recovery_network_repair",
                "recovery_password",
                "signing_key",
            }
            else None,
        )

    # Count supported human work, not every blocked diagnostic; this never authorizes a command.
    def actionable(self):
        pending = (
            select(1)
            .where(
                org_person.c.workspace_id == operation.c.workspace_id,
                org_person.c.pending_operation_id == operation.c.id,
                cast(org_person.c.id, String)
                == audit_event.c.data["intent"]["target"]["person_id"].astext,
            )
            .correlate(operation, audit_event)
            .exists()
        )
        guided = and_(
            audit_event.c.data["intent"]["onboarding_version"].astext.in_(("1", "2", "3", "4")),
            or_(
                operation.c.state == "needs_attention",
                operation.c.wait_reason.in_(("onboarding_handoff", "onboarding_review")),
            ),
        )
        return and_(
            operation.c.kind == "organization_action",
            audit_event.c.data["intent"]["kind"].astext == "organization_action",
            operation.c.state.in_(("waiting", "needs_attention")),
            pending,
            or_(guided, operation.c.effect_knowledge == "none"),
        )

    # SQL identifiers come from an allowlist; literal search never interprets %, _ or SQL syntax.
    def directory(self, workspace: str, query: OperationQuery):
        query = OperationQuery.model_validate(query)
        where = [operation.c.workspace_id == workspace]
        if query.state:
            where.append(operation.c.state == query.state)
        if query.query:
            target = audit_event.c.data["intent"]["target"]["tenancy_ocid"].astext
            where.append(
                or_(
                    target.icontains(query.query, autoescape=True),
                    cast(operation.c.id, String).icontains(query.query, autoescape=True),
                )
            )
        column = {
            name: operation.c[name] for name in ("accepted_at", "updated_at", "state", "stage")
        }[query.sort]
        order = column.asc() if query.direction == "asc" else column.desc()
        with self.snapshot() as connection:
            # Supported action count remains workspace-wide, independent of list filters.
            attention = connection.scalar(
                select(func.count())
                .select_from(self.joined())
                .where(
                    operation.c.workspace_id == workspace,
                    self.actionable(),
                )
            )
            total = connection.scalar(select(func.count()).select_from(self.joined()).where(*where))
            pages = max(1, (total + query.page_size - 1) // query.page_size)
            page = min(query.page, pages)
            rows = (
                connection.execute(
                    self.selection()
                    .where(*where)
                    .order_by(order, operation.c.id)
                    .offset((page - 1) * query.page_size)
                    .limit(query.page_size)
                )
                .mappings()
                .all()
            )
            return OperationDirectory(
                attention_count=attention,
                items=[self.summary(row) for row in rows],
                total=total,
                page=page,
                page_size=query.page_size,
                pages=pages,
            )

    # Return the same not-found result for an absent ID and an ID in another workspace.
    def detail(self, workspace: str, identifier: UUID, actor_subject=None):
        with self.snapshot() as connection:
            row = (
                connection.execute(
                    self.selection().where(
                        operation.c.workspace_id == workspace, operation.c.id == identifier
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            summary = self.summary(row)
            frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
            if summary.guided_onboarding:
                authority_id, _, authority_actor = execution_authority(connection, row, frozen)
                grant = (
                    connection.execute(
                        select(administrator).where(
                            administrator.c.workspace_id == workspace,
                            administrator.c.id == authority_id,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                summary = summary.model_copy(
                    update={
                        "responsible_administrator_id": authority_id,
                        "responsible_administrator_name": grant["display_name"]
                        if grant
                        else authority_actor.display_name,
                        "responsibility_revision": row["revision"],
                        "can_take_responsibility": bool(
                            actor_subject
                            and eligible(row, frozen.intent)
                            and row["responsible_actor_subject"] != actor_subject
                        ),
                    }
                )
            steps = (
                connection.execute(
                    select(operation_step)
                    .where(
                        operation_step.c.workspace_id == workspace,
                        operation_step.c.operation_id == identifier,
                        operation_step.c.intent_revision == row["current_intent_revision"],
                    )
                    .order_by(operation_step.c.step_key)
                )
                .mappings()
                .all()
            )
            events = (
                connection.execute(
                    select(
                        audit_event.c.kind,
                        audit_event.c.at,
                        audit_event.c.data,
                        audit_event.c.data_hash,
                    )
                    .where(
                        audit_event.c.workspace_id == workspace,
                        audit_event.c.operation_id == identifier,
                    )
                    .order_by(audit_event.c.at.desc(), audit_event.c.id.desc())
                    .limit(51)
                )
                .mappings()
                .all()
            )
            return OperationDetail(
                recovery_password=password_progress(connection, row, frozen.intent)
                if row["kind"] == "recovery_password"
                else None,
                notifications=list_for_operation(connection, workspace, identifier),
                operation=summary,
                steps=[self.step(step) for step in steps],
                events=[self.event(event) for event in events[:50]],
                events_limited=len(events) > 50,
            )

    # Validate versioned outcomes before choosing a safe code; unknown results remain unknown.
    def step(self, row):
        outcome = (
            (
                SigningKeyEvidence
                if row["command_kind"] == "signing_key"
                else RecoveryPasswordEvidence
                if row["command_kind"] == "recovery_password"
                else RecoveryNetworkEvidence
                if row["command_kind"] == "recovery_network_repair"
                else PresenceCheckEvidence
                if row["command_kind"] == "required_user_check"
                else CostEvidence
                if row["command_kind"] == "cost_collection"
                else ConfigurationCheckEvidence
                if row["command_kind"] == "configuration_check"
                else ConfigurationOutcome
                if row["command_kind"] == "configuration_update"
                else OnboardingEvidence
                if row["command_kind"] == "onboarding"
                else OrganizationActionOutcome
                if row["command_kind"] == "organization_action"
                else InspectionOutcome
            ).model_validate_json(json.dumps(row["last_outcome"]))
            if row["last_outcome"] is not None
            else None
        )
        return OperationStepView(
            step_key=row["step_key"],
            state=row["state"],
            attempt_number=row["attempt_number"],
            verified_at=utc(row["verified_at"]),
            safe_code=outcome.safe_code if outcome else None,
        )

    # Expose closed outcome codes only; immutable JSON itself stays private.
    def event(self, row):
        if canonical_hash(row["data"]) != row["data_hash"]:
            raise ValueError("INVALID_OPERATION_EVIDENCE")
        if row["kind"] == "recovery_password_disclosed":
            RecoveryDisclosureEvidence.model_validate_json(json.dumps(row["data"]))
        if row["kind"] == "email_delivery":
            NotificationEvidence.model_validate_json(json.dumps(row["data"]))
        if row["kind"] == "operation_responsibility_changed":
            ResponsibilityEvidence.model_validate_json(json.dumps(row["data"]))
        outcome = (
            (
                SigningKeyEvidence
                if row["kind"] == "signing_key_outcome"
                else SigningKeyRequestEvidence
                if row["kind"] == "signing_key_requested"
                else RecoveryPasswordEvidence
                if row["kind"] == "recovery_password_outcome"
                else RecoveryNetworkEvidence
                if row["kind"] == "recovery_network_outcome"
                else PresenceCheckEvidence
                if row["kind"] == "required_user_check_outcome"
                else CostEvidence
                if row["kind"] == "cost_collection_outcome"
                else ConfigurationCheckEvidence
                if row["kind"] == "configuration_check_outcome"
                else ConfigurationOutcome
                if row["kind"] == "configuration_outcome"
                else ConfigurationRetryEvidence
                if row["kind"] == "configuration_retry"
                else OnboardingEvidence
                if row["kind"] in {"onboarding_action", "onboarding_outcome"}
                else OrganizationActionOutcome
                if row["kind"] == "organization_action_outcome"
                else InspectionOutcome
            ).model_validate_json(json.dumps(row["data"]))
            if row["kind"]
            in {
                "inspection_outcome",
                "configuration_outcome",
                "configuration_check_outcome",
                "cost_collection_outcome",
                "required_user_check_outcome",
                "recovery_network_outcome",
                "recovery_password_outcome",
                "signing_key_outcome",
                "signing_key_requested",
                "configuration_retry",
                "organization_action_outcome",
                "onboarding_action",
                "onboarding_outcome",
            }
            else None
        )
        return OperationEventView(
            summary=signing_event_summary(outcome)
            if isinstance(outcome, SigningKeyEvidence)
            else None,
            automation_keys=inventory_view(
                outcome.automation_keys,
                outcome.operation_id,
                outcome.automation_keys.checked_at
                if outcome.automation_keys
                else outcome.checked_at,
            )
            if isinstance(outcome, PresenceCheckEvidence)
            else None,
            kind=row["kind"],
            at=utc(row["at"]),
            safe_code=outcome.safe_code if outcome else None,
            user_checks=user_check_sections(outcome)
            if isinstance(outcome, PresenceCheckEvidence)
            else (),
        )
