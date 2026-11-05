"""Authorized, scoped organization snapshots; no tenancy actions or prototype shortcuts."""

import json
import re
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from otm.auth.service import AdminPrincipal, SessionFailure, SessionService
from otm.contracts import UtcInstant
from otm.operations.contracts import canonical_hash
from otm.organization.contracts import Configuration, Diagnostic, Intake, PersonState, Revision
from otm.organization.persistence_contracts import (
    ORGANIZATION_SERVICE_ACTOR,
    OrganizationEvidence,
    OrganizationOutcome,
)
from otm.organization.reconcile import prepare
from otm.organization.review_rules import canonical_email
from otm.storage.admin_authority import authorize_administrator
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    audit_event,
    org_feed,
    org_member,
    org_person,
    org_version,
    org_workspace,
)
from otm.storage.transaction import require_transaction


# Conflicting deliveries, configuration or publication heads require a fresh intentional command.
class OrganizationConflict(ValueError):
    pass


# Keep readable columns and full canonical PersonState evidence derived from the same values.
def member_values(person: PersonState, identities, supplied):
    return dict(
        person_id=person.id,
        email=person.email,
        full_name=person.full_name,
        manager_person_id=identities[person.manager_email] if person.manager_email else None,
        manager_email=person.manager_email,
        profile=person.profile,
        evidence="feed_row"
        if person.email in supplied
        else "retained"
        if person.profile == "employee"
        else person.profile,
        lob_id=person.lob_id,
        accountable_leader_email=person.accountable_leader_email,
        designee_emails=list(person.designee_emails),
        ancestry=person.ancestry,
        absence_review=person.absence_review,
        data=person.model_dump(mode="json"),
    )


# Reconstruct only immutable typed results, never return an unbounded private database row.
def outcome(row, *, duplicate=False):
    return OrganizationOutcome(
        snapshot_id=row["id"],
        state="duplicate" if duplicate else row["state"],
        original_state=row["state"] if duplicate else None,
        proposed_version_id=row["proposed_version_id"],
        revision_id=row["applied_version_id"],
        diagnostics=tuple(
            OrganizationOutcome.model_validate_json(
                json.dumps(
                    {
                        "snapshot_id": str(row["id"]),
                        "state": row["state"],
                        "diagnostics": row["diagnostics"],
                    }
                )
            ).diagnostics
        ),
    )


# Validate canonical source data against the separate readable receipt metadata and pinned scope.
def source_intake(feed, config):
    if canonical_hash(feed["data"]) != feed["digest"]:
        raise ValueError("INVALID_ORGANIZATION_FEED_EVIDENCE")
    intake = Intake.model_validate_json(json.dumps(feed["data"]))
    value = intake.envelope
    if (feed["source_id"], feed["population_id"], feed["external_id"], feed["captured_at"]) != (
        value.source_id,
        value.population_id,
        value.external_snapshot_id,
        value.captured_at,
    ) or (value.source_id, value.population_id) != (
        config.policy.source_id,
        config.policy.population_id,
    ):
        raise ValueError("INVALID_ORGANIZATION_FEED_SCOPE")
    return intake


# Store scoped immutable organizations using the current administrator/session authority.
class SqlOrganizationStore:
    # A real session service and server clock are mandatory; there is no default actor/authorizer.
    def __init__(self, engine: Engine, sessions: SessionService, clock: Callable[[], datetime]):
        self.engine, self.sessions, self.clock = engine, sessions, clock

    # Derive scope from a verified session, independently of the source population namespace.
    def _principal(self, principal):
        if not isinstance(principal, AdminPrincipal):
            raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
        self.sessions.require_admin(principal, principal.session.workspace_id)
        return principal.session.workspace_id

    # Administrator anchor/session locks precede workspace locks in every mutating transaction.
    @contextmanager
    def _write(self, principal):
        workspace = self._principal(principal)
        with self.engine.begin() as connection:
            require_transaction(connection)
            authorize_administrator(connection, principal, self.clock)
            yield connection, workspace, TypeAdapter(UtcInstant).validate_python(self.clock())

    # Lock one exact workspace; no source field or caller-selected table can select another scope.
    def _workspace(self, connection, workspace, *, lock=False):
        query = select(org_workspace).where(org_workspace.c.id == workspace)
        row = (
            connection.execute(query.with_for_update() if lock else query).mappings().one_or_none()
        )
        if row is None:
            raise OrganizationConflict("ORGANIZATION_NOT_CONFIGURED")
        return row

    # Append only closed correlation/count evidence; automatic metadata uses an explicit
    # service actor.
    def _audit(self, connection, workspace, actor, kind, at, config, **values):
        evidence = OrganizationEvidence(
            source_id=config.policy.source_id,
            population_id=config.policy.population_id,
            configuration_id=config.id,
            **values,
        ).model_dump(mode="json")
        connection.execute(
            audit_event.insert().values(
                id=uuid4(),
                workspace_id=workspace,
                operation_id=None,
                administrator_id=None,
                intent_revision=None,
                actor=actor.key,
                actor_subject=actor.key,
                actor_snapshot=actor.model_dump(mode="json"),
                kind=kind,
                at=at,
                contract_version="organization-1",
                data=evidence,
                data_hash=canonical_hash(evidence),
            )
        )

    # Initialize once under current authority; existing configuration cannot be
    # overwritten by seeding.
    def configure_initial(self, principal, configuration: Configuration):
        content = configuration.model_dump_json()
        if len(content.encode()) > 65536:
            raise ValueError("INVALID_ORGANIZATION_CONFIGURATION")
        configuration = Configuration.model_validate_json(content)
        TypeAdapter(OrganizationEvidence).validate_python(
            OrganizationEvidence(
                source_id=configuration.policy.source_id,
                population_id=configuration.policy.population_id,
                configuration_id=configuration.id,
            )
        )
        with self._write(principal) as (connection, workspace, at):
            inserted = connection.execute(
                insert(org_workspace)
                .values(
                    id=workspace,
                    configuration_id=configuration.id,
                    configuration=configuration.model_dump(mode="json"),
                )
                .on_conflict_do_nothing()
                .returning(org_workspace.c.id)
            ).scalar_one_or_none()
            row = self._workspace(connection, workspace, lock=True)
            if canonical_hash(row["configuration"]) != canonical_hash(
                configuration.model_dump(mode="json")
            ):
                raise OrganizationConflict("ORGANIZATION_ALREADY_CONFIGURED")
            if inserted:
                self._audit(
                    connection,
                    workspace,
                    principal.actor,
                    "organization_configured",
                    at,
                    configuration,
                )

    # Reconstruct a sealed same-workspace version and ensure readable columns match full
    # person evidence.
    @staticmethod
    def _revision(connection, workspace, identifier):
        row = (
            connection.execute(
                select(org_version).where(
                    org_version.c.workspace_id == workspace,
                    org_version.c.id == identifier,
                    org_version.c.sealed.is_(True),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OrganizationConflict("ORGANIZATION_VERSION_NOT_FOUND")
        config = Configuration.model_validate_json(json.dumps(row["configuration"]))
        feed = (
            connection.execute(
                select(org_feed).where(
                    org_feed.c.workspace_id == workspace,
                    org_feed.c.id == row["feed_id"],
                )
            )
            .mappings()
            .one()
        )
        supplied = {record.email for record in source_intake(feed, config).records}
        members = (
            connection.execute(
                select(org_member)
                .where(
                    org_member.c.workspace_id == workspace,
                    org_member.c.version_id == identifier,
                )
                .order_by(org_member.c.email)
            )
            .mappings()
            .all()
        )
        people = tuple(
            PersonState.model_validate_json(json.dumps(member["data"])) for member in members
        )
        if len(people) != row["member_count"]:
            raise ValueError("INVALID_ORGANIZATION_MEMBER_COUNT")
        identities = {person.email: person.id for person in people}
        for member, person in zip(members, people, strict=True):
            expected = member_values(person, identities, supplied)
            if any(member[key] != value for key, value in expected.items()):
                raise ValueError("INVALID_ORGANIZATION_MEMBER_EVIDENCE")
        revision = Revision.model_validate_json(
            json.dumps({**row["data"], "people": [p.model_dump(mode="json") for p in people]})
        )
        if (
            revision.id,
            revision.configuration_id,
            revision.snapshot_id,
            revision.predecessor_id,
        ) != (
            row["id"],
            row["configuration_id"],
            row["feed_id"],
            row["base_version_id"],
        ):
            raise ValueError("INVALID_ORGANIZATION_VERSION_EVIDENCE")
        if (
            revision.population_id != config.policy.population_id
            or revision.source_captured_at != feed["captured_at"]
        ):
            raise ValueError("INVALID_ORGANIZATION_SOURCE_PROVENANCE")
        return revision

    # Head reads do not infer source population from auth scope or refresh session activity.
    def head(self, principal, *, proposed=False):
        workspace = self._principal(principal)
        with read_snapshot(self.engine) as connection:
            row = self._workspace(connection, workspace)
            identifier = row["proposed_version_id" if proposed else "applied_version_id"]
            return self._revision(connection, workspace, identifier) if identifier else None

    # Read configuration, verified heads and latest receipt in one coherent scoped snapshot.
    # The API receives typed revisions, never raw SQL, credentials or another workspace's data.
    def inspection(self, principal):
        workspace = self._principal(principal)
        with read_snapshot(self.engine) as connection:
            state = (
                connection.execute(select(org_workspace).where(org_workspace.c.id == workspace))
                .mappings()
                .one_or_none()
            )
            if state is None:
                return None, None, None, None, ()
            config = Configuration.model_validate_json(json.dumps(state["configuration"]))
            current = (
                self._revision(connection, workspace, state["applied_version_id"])
                if state["applied_version_id"]
                else None
            )
            previous = (
                self._revision(connection, workspace, current.predecessor_id)
                if current and current.predecessor_id
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
            )
            issues = ()
            if current:
                # Display labels and decisions from the same frozen configuration as the head.
                version = connection.execute(
                    select(org_version.c.configuration).where(
                        org_version.c.workspace_id == workspace, org_version.c.id == current.id
                    )
                ).scalar_one()
                config = Configuration.model_validate_json(json.dumps(version))
                feed = (
                    connection.execute(
                        select(org_feed).where(
                            org_feed.c.workspace_id == workspace,
                            org_feed.c.id == current.snapshot_id,
                        )
                    )
                    .mappings()
                    .one()
                )
                source = source_intake(feed, config)
                # Read current settled evidence without replaying the predecessor census.
                issues = prepare(
                    source.records,
                    source.envelope,
                    config,
                    current.model_copy(update={"source_captured_at": None}),
                    current.published_at,
                    trusted_reapply=True,
                    configuration_only=True,
                ).issues
            return config, current, previous, latest, issues

    # Preserve original identity anchors, including explicit merge survivors in this exact
    # workspace.
    @staticmethod
    def _persist(connection, workspace, feed, config, candidate, kind):
        rows = (
            connection.execute(select(org_person).where(org_person.c.workspace_id == workspace))
            .mappings()
            .all()
        )
        identities = {row["email"]: row["id"] for row in rows}
        existing_ids = set(identities.values())
        for merge in config.identity_merges:
            if merge.person_id not in existing_ids or merge.retired_person_id not in existing_ids:
                raise OrganizationConflict("INVALID_ORGANIZATION_MERGE_SCOPE")
            identities[canonical_email(config, merge.new_email)] = merge.person_id
        for person in candidate.people:
            if person.email not in identities:
                connection.execute(
                    org_person.insert().values(
                        id=person.id, workspace_id=workspace, email=person.email
                    )
                )
                identities[person.email] = person.id
        people = tuple(
            person.model_copy(update={"id": identities[person.email]})
            for person in candidate.people
        )
        revision = Revision(
            id=uuid4(),
            predecessor_id=candidate.expected_head_id,
            configuration_id=config.id,
            snapshot_id=feed["id"],
            population_id=config.policy.population_id,
            published_at=candidate.observed_at,
            source_captured_at=candidate.envelope.captured_at,
            declared_completeness=candidate.envelope.declared_completeness,
            assessed_coverage=candidate.assessed_coverage,
            absence_eligible=candidate.absence_eligible,
            people=people,
        )
        connection.execute(
            org_version.insert().values(
                id=revision.id,
                workspace_id=workspace,
                kind=kind,
                base_version_id=revision.predecessor_id,
                feed_id=feed["id"],
                configuration_id=config.id,
                configuration=config.model_dump(mode="json"),
                data=revision.model_dump(mode="json", exclude={"people"}),
                sealed=False,
                member_count=len(people),
            )
        )
        supplied = {record["email"] for record in feed["data"]["records"]}
        if people:
            connection.execute(
                org_member.insert(),
                [
                    dict(
                        workspace_id=workspace,
                        version_id=revision.id,
                        **member_values(person, identities, supplied),
                    )
                    for person in people
                ],
            )
        connection.execute(
            update(org_version)
            .where(org_version.c.id == revision.id, org_version.c.workspace_id == workspace)
            .values(sealed=True)
        )
        return revision

    # Stage only trusted source-bound candidates; fatal raw graphs cannot be repaired
    # invisibly by overrides.
    def _stage(self, connection, workspace, feed, config, state, at):
        intake = source_intake(feed, config)
        previous = (
            self._revision(connection, workspace, state["applied_version_id"])
            if state["applied_version_id"]
            else None
        )
        latest = (
            self._revision(connection, workspace, state["proposed_version_id"])
            if state["proposed_version_id"]
            else None
        )
        raw = prepare(
            intake.records,
            intake.envelope,
            config.model_copy(update={"overrides": ()}),
            previous,
            at,
        )
        effective = prepare(intake.records, intake.envelope, config, previous, at)
        diagnostics = tuple(dict.fromkeys((*raw.diagnostics, *effective.diagnostics)))
        superseded = bool(
            latest
            and latest.source_captured_at
            and intake.envelope.captured_at
            and intake.envelope.captured_at <= latest.source_captured_at
        )
        if superseded and not any(d.code == "SUPERSEDED_CAPTURE" for d in diagnostics):
            diagnostics += (Diagnostic(code="SUPERSEDED_CAPTURE", fatal=True),)
        if raw.rejected or effective.rejected or superseded:
            code = (
                "superseded"
                if superseded or any(d.code == "SUPERSEDED_CAPTURE" for d in diagnostics)
                else "rejected"
            )
            connection.execute(
                update(org_feed)
                .where(org_feed.c.id == feed["id"], org_feed.c.workspace_id == workspace)
                .values(state=code, diagnostics=[d.model_dump(mode="json") for d in diagnostics])
            )
            self._audit(
                connection,
                workspace,
                ORGANIZATION_SERVICE_ACTOR,
                "organization_feed_rejected",
                at,
                config,
                feed_id=feed["id"],
                diagnostic_count=len(diagnostics),
            )
            return
        proposed = self._persist(connection, workspace, feed, config, raw, "proposed")
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == workspace)
            .values(proposed_version_id=proposed.id)
        )
        connection.execute(
            update(org_feed)
            .where(org_feed.c.id == feed["id"], org_feed.c.workspace_id == workspace)
            .values(
                state="staged",
                proposed_version_id=proposed.id,
                diagnostics=[d.model_dump(mode="json") for d in diagnostics],
            )
        )

    # Apply only the exact still-current proposal/configuration/base, recomputing from
    # immutable source.
    def _apply(self, connection, workspace, proposal_id, state, config, at):
        proposal = self._revision(connection, workspace, proposal_id)
        if (
            state["proposed_version_id"],
            state["applied_version_id"],
            state["configuration_id"],
        ) != (
            proposal.id,
            proposal.predecessor_id,
            proposal.configuration_id,
        ):
            raise OrganizationConflict("ORGANIZATION_PUBLICATION_CHANGED")
        if at < proposal.published_at:
            raise OrganizationConflict("ORGANIZATION_CLOCK_REVERSED")
        feed = (
            connection.execute(
                select(org_feed).where(
                    org_feed.c.workspace_id == workspace, org_feed.c.id == proposal.snapshot_id
                )
            )
            .mappings()
            .one()
        )
        intake = source_intake(feed, config)
        previous = (
            self._revision(connection, workspace, state["applied_version_id"])
            if state["applied_version_id"]
            else None
        )
        candidate = prepare(intake.records, intake.envelope, config, previous, at)
        if candidate.rejected:
            raise OrganizationConflict("ORGANIZATION_SOURCE_NO_LONGER_ELIGIBLE")
        from otm.organization.reviews import qualified_return_history, reconcile_reviews

        history = qualified_return_history(
            connection, workspace, previous, candidate, {record.email for record in intake.records}
        )
        if history is not previous:
            candidate = prepare(intake.records, intake.envelope, config, history, at)
        applied = self._persist(connection, workspace, feed, config, candidate, "applied")

        reconcile_reviews(
            connection,
            workspace,
            applied,
            previous,
            candidate,
            config,
            supplied={record.email for record in intake.records},
            at=at,
        )
        self._audit(
            connection,
            workspace,
            ORGANIZATION_SERVICE_ACTOR,
            "organization_published",
            at,
            config,
            feed_id=feed["id"],
            proposed_version_id=proposal.id,
            applied_version_id=applied.id,
            person_count=len(applied.people),
            diagnostic_count=len(candidate.diagnostics),
        )
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == workspace)
            .values(applied_version_id=applied.id)
        )
        connection.execute(
            update(org_feed)
            .where(org_feed.c.id == feed["id"], org_feed.c.workspace_id == workspace)
            .values(state="published", applied_version_id=applied.id)
        )

    # Each delivery is distinct; exact transport replay returns its outcome without new
    # versions/audit.
    def ingest(self, principal, intake: Intake, *, raw_digest=None, stage_only=False):
        content = intake.model_dump_json()
        if len(content.encode()) > 4 * 1024 * 1024 or not 1 <= len(intake.records) <= 5000:
            raise ValueError("INVALID_ORGANIZATION_INTAKE")
        intake = Intake.model_validate_json(content)
        if raw_digest is not None and re.fullmatch(r"[0-9a-f]{64}", raw_digest) is None:
            raise ValueError("INVALID_ORGANIZATION_RAW_DIGEST")
        if (
            max(len(intake.envelope.source_id), len(intake.envelope.population_id)) > 256
            or len(intake.envelope.external_snapshot_id) > 512
        ):
            raise ValueError("INVALID_ORGANIZATION_DELIVERY_ID")
        data = intake.model_dump(mode="json")
        digest = canonical_hash(data)
        with self._write(principal) as (connection, workspace, at):
            state = self._workspace(connection, workspace, lock=True)
            config = Configuration.model_validate_json(json.dumps(state["configuration"]))
            if (intake.envelope.source_id, intake.envelope.population_id) != (
                config.policy.source_id,
                config.policy.population_id,
            ):
                raise OrganizationConflict("ORGANIZATION_SOURCE_SCOPE_MISMATCH")
            prior = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace,
                        org_feed.c.source_id == intake.envelope.source_id,
                        org_feed.c.external_id == intake.envelope.external_snapshot_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if prior:
                if prior["digest"] != digest or prior["raw_digest"] != raw_digest:
                    raise OrganizationConflict("ORGANIZATION_DELIVERY_CHANGED")
                return outcome(prior, duplicate=True)
            identifier = uuid4()
            connection.execute(
                org_feed.insert().values(
                    id=identifier,
                    workspace_id=workspace,
                    source_id=intake.envelope.source_id,
                    population_id=intake.envelope.population_id,
                    external_id=intake.envelope.external_snapshot_id,
                    received_at=at,
                    captured_at=intake.envelope.captured_at,
                    digest=digest,
                    raw_digest=raw_digest,
                    data=data,
                    state="received",
                    diagnostics=[],
                )
            )
            feed = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace, org_feed.c.id == identifier
                    )
                )
                .mappings()
                .one()
            )
            self._audit(
                connection,
                workspace,
                principal.actor,
                "organization_feed_received",
                at,
                config,
                feed_id=identifier,
            )
            self._stage(connection, workspace, feed, config, state, at)
            state = self._workspace(connection, workspace)
            feed = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace, org_feed.c.id == identifier
                    )
                )
                .mappings()
                .one()
            )
            if feed["state"] == "staged" and not stage_only:
                self._apply(connection, workspace, feed["proposed_version_id"], state, config, at)
            feed = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace, org_feed.c.id == identifier
                    )
                )
                .mappings()
                .one()
            )
            return outcome(feed)

    # Explicit staged publication is still guarded and cannot submit a client-constructed candidate.
    def apply(self, principal, proposed_version_id: UUID):
        with self._write(principal) as (connection, workspace, at):
            state = self._workspace(connection, workspace, lock=True)
            prior = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace,
                        org_feed.c.proposed_version_id == proposed_version_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if prior and prior["state"] == "published":
                return outcome(prior, duplicate=True)
            config = Configuration.model_validate_json(json.dumps(state["configuration"]))
            self._apply(connection, workspace, proposed_version_id, state, config, at)
            feed = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace,
                        org_feed.c.proposed_version_id == proposed_version_id,
                    )
                )
                .mappings()
                .one()
            )
            return outcome(feed)
