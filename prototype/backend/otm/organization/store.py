"""Source-bound staging, automatic application and audited exception correction."""

import hashlib
import json
import re
from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url

from otm.organization.contracts import (
    Candidate,
    Configuration,
    Contract,
    Diagnostic,
    Envelope,
    Record,
    Revision,
    require_aware,
)
from otm.organization.reconcile import prepare
from otm.organization.review_rules import ACTIONABLE, canonical_email, suppressed
from otm.organization.schema import install_guards, schema_tables


# Displayed or staged inputs changed; rebuild rather than overwrite newer state.
class PublicationConflict(RuntimeError):
    pass


# Processing result with independent proposed and applied version identifiers.
class Outcome(Contract):
    snapshot_id: UUID
    state: str
    revision_id: UUID | None = None
    proposed_version_id: UUID | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    original_state: str | None = None


# Validate an explicit clock and normalize it to UTC, defaulting to current time.
def utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)
    require_aware(value)
    return value.astimezone(UTC)


# Return readable person/field deltas, excluding observation-only timestamp refreshes.
def compare_organizations(previous: Revision | None, people) -> list[dict]:
    old = {person.email: person for person in previous.people} if previous else {}
    old_ids = {person.id: person for person in previous.people} if previous else {}
    fields = (
        "email",
        "full_name",
        "manager_email",
        "profile",
        "lob_id",
        "accountable_leader_email",
        "designee_emails",
        "absence_review",
        "ancestry",
        "territory",
        "known_manager",
        "manager_provenance",
    )
    changes = []
    for person in people:
        before = old_ids.get(person.id) or old.get(person.email)
        for field in fields:
            original = getattr(before, field) if before else None
            after = getattr(person, field)
            if before is None or original != after:
                changes.append(
                    {
                        "person_id": str(person.id),
                        "email": person.email,
                        "field": field,
                        "before": original,
                        "after": after,
                    }
                )
    return changes


# Local-only repository for applied/proposed versions and readable reconciliation.
class Store:
    # Limit this unqualified prototype to local OTM databases and safe schema
    # identifiers.
    def __init__(self, database_url: str, schema: str = "otm_org"):
        url = make_url(database_url)
        # Driver query options can override the parsed host/database or select another service.
        # Local-only safety checks must hold for the effective connection, not just the URL label.
        if url.query:
            raise ValueError("prototype does not allow connection query overrides")
        if url.host not in {"127.0.0.1", "localhost"} or not (url.database or "").startswith(
            "otm_"
        ):
            raise ValueError("prototype requires a loopback otm_* PostgreSQL database")
        if not re.fullmatch(r"otm_[a-z0-9_]+", schema):
            raise ValueError("invalid local schema")
        self.schema = schema
        self.engine = create_engine(database_url)
        self.metadata, self.tables = schema_tables(schema)

    # Create ten tables, evidence guards and inspection views without replacing
    # legacy data.
    def initialize(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))
            legacy = connection.execute(
                text("SELECT to_regclass(:name)"), {"name": self.schema + ".org_snapshot"}
            ).scalar_one()
            if legacy:
                raise ValueError("legacy schema requires the explicit preservation migration")
            self.metadata.create_all(connection)
            install_guards(connection, self.schema)

    # Read the coordination row, locking it when advancing versions or admin settings.
    def _workspace(self, connection, workspace_id: str, *, lock: bool = False):
        statement = select(self.tables["workspace"]).where(
            self.tables["workspace"].c.id == workspace_id
        )
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one()

    # Append immutable evidence in the caller's transaction; no outbound delivery occurs.
    def _audit(
        self,
        connection,
        workspace_id,
        kind,
        now,
        data,
        *,
        actor="service:organization",
        feed_id=None,
        version_id=None,
    ) -> None:
        connection.execute(
            self.tables["event"]
            .insert()
            .values(
                id=str(uuid4()),
                workspace_id=workspace_id,
                actor=actor,
                kind=kind,
                at=now,
                feed_id=str(feed_id) if feed_id else None,
                version_id=str(version_id) if version_id else None,
                data=data,
            )
        )

    # Bootstrap once; future settings changes require an audited expected-version
    # operation.
    def configure_initial(self, config: Configuration) -> None:
        table = self.tables["workspace"]
        with self.engine.begin() as connection:
            existing = (
                connection.execute(select(table).where(table.c.id == config.policy.population_id))
                .mappings()
                .first()
            )
            if existing:
                if Configuration.model_validate(existing["configuration"]) != config:
                    raise PublicationConflict("configuration already bootstrapped; no silent edit")
                return
            connection.execute(
                table.insert().values(
                    id=config.policy.population_id,
                    configuration_id=str(config.id),
                    configuration=config.model_dump(mode="json"),
                )
            )
            self._audit(
                connection,
                config.policy.population_id,
                "workspace_configured",
                utc(),
                {"configuration": config.model_dump(mode="json")},
            )

    # Read trusted settings separately from claims contained in incoming source payloads.
    def configuration(self, population_id: str) -> Configuration:
        with self.engine.connect() as connection:
            return Configuration.model_validate(
                self._workspace(connection, population_id)["configuration"]
            )

    # Read a complete immutable version through a caller-owned connection.
    def _revision(self, connection, revision_id) -> Revision:
        version, member = self.tables["version"], self.tables["member"]
        data = connection.execute(
            select(version.c.data).where(
                version.c.id == str(revision_id), version.c.sealed.is_(True)
            )
        ).scalar_one_or_none()
        if data is None:
            raise KeyError("REVISION_NOT_FOUND")
        people = (
            connection.execute(
                select(member.c.data)
                .where(member.c.version_id == str(revision_id))
                .order_by(member.c.email)
            )
            .scalars()
            .all()
        )
        return Revision.model_validate({**data, "people": people})

    # Load any selected historical applied/proposed version without falling back to
    # latest.
    def revision(self, revision_id: UUID) -> Revision:
        with self.engine.connect() as connection:
            return self._revision(connection, revision_id)

    # Read the applied organization pointer, preserving stable historical read semantics.
    def head(self, population_id: str) -> Revision | None:
        return self._pointer(population_id, "applied_version_id")

    # Read the latest eligible proposed organization independently of applied state.
    def proposed(self, population_id: str) -> Revision | None:
        return self._pointer(population_id, "proposed_version_id")

    # Resolve a trusted pointer column within one connection and immutable version.
    def _pointer(self, workspace_id, column) -> Revision | None:
        with self.engine.connect() as connection:
            identifier = self._workspace(connection, workspace_id)[column]
            return self._revision(connection, identifier) if identifier else None

    # Load canonical stored input; proposals are never constructed from caller-
    # supplied state.
    def _feed(self, connection, identifier):
        table = self.tables["feed"]
        return (
            connection.execute(select(table).where(table.c.id == str(identifier))).mappings().one()
        )

    # Map feed processing columns into the compatibility and staged workflow result.
    def _outcome(self, row) -> Outcome:
        return Outcome(
            snapshot_id=row["id"],
            state=row["state"],
            revision_id=row["applied_version_id"],
            proposed_version_id=row["proposed_version_id"],
            diagnostics=row["diagnostics"],
        )

    # Inspect feed processing without conflating receipt, proposal and application.
    def outcome(self, snapshot_id: UUID) -> Outcome:
        with self.engine.connect() as connection:
            return self._outcome(self._feed(connection, snapshot_id))

    # Persist immutable source input and append one audit receipt for every delivery.
    def register(
        self,
        envelope: Envelope,
        records: tuple[Record, ...],
        received_at: datetime,
        raw_digest: str | None = None,
    ) -> tuple[UUID, bool]:
        now = utc(received_at)
        payload = {
            "envelope": envelope.model_dump(mode="json"),
            "records": [
                row.model_dump(mode="json")
                for row in sorted(records, key=lambda row: (row.email, row.source_record_id))
            ],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        feed = self.tables["feed"]
        identifier = str(uuid4())
        with self.engine.begin() as connection:
            config = Configuration.model_validate(
                self._workspace(connection, envelope.population_id)["configuration"]
            )
            if envelope.source_id != config.policy.source_id:
                raise ValueError("source is not bound to this configured population")
            inserted = connection.execute(
                insert(feed)
                .values(
                    id=identifier,
                    workspace_id=envelope.population_id,
                    source_id=envelope.source_id,
                    external_id=envelope.external_snapshot_id,
                    captured_at=envelope.captured_at,
                    digest=digest,
                    data=payload,
                    state="received",
                    diagnostics=[],
                )
                .on_conflict_do_nothing()
                .returning(feed.c.id)
            ).scalar_one_or_none()
            if inserted:
                matching, disposition = True, "new"
            else:
                row = (
                    connection.execute(
                        select(feed).where(
                            feed.c.workspace_id == envelope.population_id,
                            feed.c.source_id == envelope.source_id,
                            feed.c.external_id == envelope.external_snapshot_id,
                        )
                    )
                    .mappings()
                    .one()
                )
                identifier, matching = row["id"], row["digest"] == digest
                disposition = "duplicate" if matching else "integrity_conflict"
            self._audit(
                connection,
                envelope.population_id,
                "feed_received",
                now,
                {"disposition": disposition, "raw_digest": raw_digest},
                feed_id=identifier,
            )
        return UUID(identifier), matching

    # Build source and effective candidates; only controlled same-feed config edits bypass
    # order.
    def _prepare(self, connection, feed, config, previous, now, *, reapply=False):
        envelope = Envelope.model_validate(feed["data"]["envelope"])
        records = tuple(Record.model_validate(row) for row in feed["data"]["records"])
        baseline = previous
        if reapply and previous and str(previous.snapshot_id) == feed["id"]:
            # Recompute already-published evidence for an explicit admin decision. Preserve
            # its capture time; expired evidence cannot infer any new absence.
            baseline = previous.model_copy(update={"source_captured_at": None})
        # Proposed facts omit person overrides but include trusted supplemental/LOB settings.
        # Applied facts honor overrides; disagreement stays visible as a review condition.
        raw_config = config.model_copy(update={"overrides": ()})
        raw = prepare(records, envelope, raw_config, baseline, now, trusted_reapply=reapply)
        effective = prepare(records, envelope, config, baseline, now, trusted_reapply=reapply)
        return records, raw, effective

    # Write a complete version with readable columns, stable IDs and frozen
    # configuration.
    def _persist_version(self, connection, feed, config, candidate, kind) -> Revision:
        person, member, version = (self.tables[key] for key in ("person", "member", "version"))
        connection.execute(
            insert(person)
            .values([{"id": str(p.id), "email": p.email} for p in candidate.people])
            .on_conflict_do_nothing(index_elements=["email"])
        )
        identities = dict(connection.execute(select(person.c.email, person.c.id)).all())
        # The immutable person email is an original identity anchor after an explicit
        # rename. Current member email changes; survivor UUID/membership references do not.
        for merge in config.identity_merges:
            address = canonical_email(config, merge.new_email)
            if str(merge.person_id) not in identities.values():
                raise ValueError("identity merge survivor does not exist")
            identities[address] = str(merge.person_id)
        people = tuple(
            p.model_copy(update={"id": UUID(identities[p.email])}) for p in candidate.people
        )
        result = Revision(
            id=uuid4(),
            predecessor_id=candidate.expected_head_id,
            configuration_id=config.id,
            snapshot_id=feed["id"],
            population_id=feed["workspace_id"],
            published_at=candidate.observed_at,
            source_captured_at=candidate.envelope.captured_at,
            declared_completeness=candidate.envelope.declared_completeness,
            assessed_coverage=candidate.assessed_coverage,
            absence_eligible=candidate.absence_eligible,
            people=people,
        )
        connection.execute(
            version.insert().values(
                id=str(result.id),
                workspace_id=result.population_id,
                kind=kind,
                base_version_id=str(result.predecessor_id) if result.predecessor_id else None,
                feed_id=feed["id"],
                configuration_id=str(config.id),
                configuration=config.model_dump(mode="json"),
                data=result.model_dump(mode="json", exclude={"people"}),
            )
        )
        supplied = {row["email"] for row in feed["data"]["records"]}
        connection.execute(
            member.insert(),
            [
                {
                    "version_id": str(result.id),
                    "person_id": str(p.id),
                    "email": p.email,
                    "full_name": p.full_name,
                    "manager_person_id": identities[p.manager_email] if p.manager_email else None,
                    "manager_email": p.manager_email,
                    "profile": p.profile,
                    "evidence": "feed_row"
                    if p.email in supplied
                    else "retained"
                    if p.profile == "employee"
                    else p.profile,
                    "lob_id": p.lob_id,
                    "accountable_leader_email": p.accountable_leader_email,
                    "designee_emails": list(p.designee_emails),
                    "ancestry": p.ancestry,
                    "absence_review": p.absence_review,
                    "data": p.model_dump(mode="json"),
                }
                for p in people
            ],
        )
        # Sealing and later pointer movement share the caller's transaction.
        connection.execute(
            update(version).where(version.c.id == str(result.id)).values(sealed=True)
        )
        return result

    # Persist the eligible proposed tree and readable deltas without changing applied
    # metadata.
    def _stage(self, connection, feed_id, now, *, reapply=False) -> Outcome:
        feed = self._feed(connection, feed_id)
        workspace = self._workspace(connection, feed["workspace_id"], lock=True)
        # Another caller can complete this same feed while we wait for the workspace lock.
        # Re-read its outcome before deciding whether to stage or return cached evidence.
        feed = self._feed(connection, feed_id)
        config = Configuration.model_validate(workspace["configuration"])
        if not reapply and feed["state"] in {"published", "rejected", "superseded"}:
            return self._outcome(feed).model_copy(update={"original_state": feed["state"]})
        previous = (
            self._revision(connection, workspace["applied_version_id"])
            if workspace["applied_version_id"]
            else None
        )
        records, raw, effective = self._prepare(
            connection, feed, config, previous, now, reapply=reapply
        )
        latest = (
            self._revision(connection, workspace["proposed_version_id"])
            if workspace["proposed_version_id"]
            else None
        )
        if (
            not reapply
            and latest
            and latest.source_captured_at
            and raw.envelope.captured_at
            and (
                raw.envelope.captured_at < latest.source_captured_at
                or raw.envelope.captured_at == latest.source_captured_at
                and str(latest.snapshot_id) != feed["id"]
            )
        ):
            raw = raw.model_copy(
                update={
                    "diagnostics": (
                        *raw.diagnostics,
                        Diagnostic(code="SUPERSEDED_CAPTURE", fatal=True),
                    )
                }
            )
        diagnostics = tuple(dict.fromkeys((*raw.diagnostics, *effective.diagnostics)))
        # Overrides cannot silently rescue a fatal source graph; repair that input upstream.
        if raw.rejected or effective.rejected:
            status = (
                "superseded"
                if any(d.code == "SUPERSEDED_CAPTURE" for d in diagnostics)
                else "rejected"
            )
            connection.execute(
                update(self.tables["feed"])
                .where(self.tables["feed"].c.id == str(feed_id))
                .values(state=status, diagnostics=[d.model_dump(mode="json") for d in diagnostics])
            )
            self._audit(
                connection,
                feed["workspace_id"],
                "feed_" + status,
                now,
                {"diagnostics": [d.model_dump(mode="json") for d in diagnostics]},
                feed_id=feed_id,
            )
            return Outcome(snapshot_id=feed_id, state=status, diagnostics=diagnostics)
        if (
            feed["state"] == "staged"
            and feed["proposed_version_id"] == workspace["proposed_version_id"]
        ):
            existing = self._revision(connection, feed["proposed_version_id"])
            if (
                existing.predecessor_id == (previous.id if previous else None)
                and existing.configuration_id == config.id
            ):
                return self._outcome(feed)
        proposal = self._persist_version(connection, feed, config, raw, "proposed")
        recommendations = self.tables["recommendation"]
        connection.execute(
            update(recommendations)
            .where(
                recommendations.c.workspace_id == feed["workspace_id"],
                recommendations.c.category == "metadata",
                recommendations.c.status.in_(["ready", "blocked_override"]),
            )
            .values(status="superseded", updated_at=now)
        )
        effective_values = {p.email: p for p in effective.people}
        for change in compare_organizations(previous, proposal.people):
            blocked = change["after"] != getattr(effective_values[change["email"]], change["field"])
            connection.execute(
                recommendations.insert().values(
                    id=str(uuid4()),
                    workspace_id=feed["workspace_id"],
                    feed_id=feed["id"],
                    proposed_version_id=str(proposal.id),
                    person_id=change["person_id"],
                    category="metadata",
                    kind="metadata_change",
                    target=change["email"],
                    field=change["field"],
                    before_value=change["before"],
                    after_value=change["after"],
                    status="blocked_override" if blocked else "ready",
                    created_at=now,
                    updated_at=now,
                )
            )
        connection.execute(
            update(self.tables["workspace"])
            .where(self.tables["workspace"].c.id == feed["workspace_id"])
            .values(proposed_version_id=str(proposal.id))
        )
        connection.execute(
            update(self.tables["feed"])
            .where(self.tables["feed"].c.id == feed["id"])
            .values(
                state="staged",
                proposed_version_id=str(proposal.id),
                diagnostics=[d.model_dump(mode="json") for d in diagnostics],
            )
        )
        self._audit(
            connection,
            feed["workspace_id"],
            "organization_proposed",
            now,
            {"base_version_id": str(previous.id) if previous else None},
            feed_id=feed_id,
            version_id=proposal.id,
        )
        return Outcome(
            snapshot_id=feed_id,
            state="staged",
            proposed_version_id=proposal.id,
            diagnostics=diagnostics,
        )

    # Inspect a persisted proposal before applying; normal ingestion applies
    # automatically.
    def stage(self, feed_id: UUID, observed_at: datetime | None = None) -> Outcome:
        with self.engine.begin() as connection:
            result = self._stage(connection, feed_id, utc(observed_at))
            # A replay describes the existing outcome; staging never reverses publication.
            if result.original_state is not None:
                return result.model_copy(update={"state": "duplicate"})
            return result

    # Refresh exception episodes and create one frozen notification intent per new
    # episode.
    def _incidents(self, connection, revision, candidate, config, proposed_id) -> None:
        table = self.tables["recommendation"]
        rows = (
            connection.execute(
                select(table).where(
                    table.c.workspace_id == revision.population_id,
                    table.c.category == "exception",
                    table.c.status.in_(["open", "acknowledged"]),
                )
            )
            .mappings()
            .all()
        )
        existing = {(row["kind"], row["target"]): row for row in rows}
        wanted = {
            item
            for item in candidate.issues
            if not suppressed(config, item[0], item[1], revision.people)
        }
        people = {p.email: p for p in revision.people}
        for kind, target in wanted:
            if (kind, target) in existing:
                row = existing[(kind, target)]
                connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(updated_at=candidate.observed_at, applied_version_id=str(revision.id))
                )
            else:
                identifier = str(uuid4())
                address = next(
                    (address for address in people if address in target.split(":")), target
                )
                person = people.get(address)
                connection.execute(
                    table.insert().values(
                        id=identifier,
                        workspace_id=revision.population_id,
                        feed_id=str(revision.snapshot_id),
                        proposed_version_id=str(proposed_id),
                        applied_version_id=str(revision.id),
                        person_id=str(person.id) if person else None,
                        category="exception",
                        kind=kind,
                        target=target,
                        status="open",
                        created_at=candidate.observed_at,
                        updated_at=candidate.observed_at,
                    )
                )
                connection.execute(
                    self.tables["notification"]
                    .insert()
                    .values(
                        id=str(uuid4()),
                        recommendation_id=identifier,
                        version_id=str(revision.id),
                        recipients=list(config.policy.administrator_recipients),
                        state="intent_only",
                    )
                )
        for key, row in existing.items():
            if key not in wanted:
                # Actionable episodes require an explicit decision even if source facts
                # improve. Retired/removed identities can close as part of their admin action.
                if (
                    key[0] in ACTIONABLE
                    and not (
                        key[0] == "PERSON_ABSENCE_REVIEW"
                        and key[1] in people
                        and not people[key[1]].absence_review
                    )
                    and any(p.email in key[1].split(":") for p in revision.people)
                    and not suppressed(config, key[0], key[1], revision.people)
                ):
                    continue
                if (
                    key[0] == "MANAGER_PROFILE_MISSING"
                    and key[1] not in candidate.employee_row_emails
                    and not candidate.absence_eligible
                ):
                    continue
                connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(
                        status="ignored"
                        if any(
                            d.kind == key[0] and d.target == key[1] and d.disposition == "ignored"
                            for d in config.review_decisions
                        )
                        else "resolved",
                        resolved_at=candidate.observed_at,
                        updated_at=candidate.observed_at,
                    )
                )
                self._audit(
                    connection,
                    revision.population_id,
                    "exception_resolved",
                    candidate.observed_at,
                    {"recommendation_id": row["id"]},
                    version_id=revision.id,
                )

    # Rebuild from stored input and apply only the current proposal against its exact
    # baseline.
    def _apply(self, connection, proposed_id, now) -> Outcome:
        version = self.tables["version"]
        proposal_row = (
            connection.execute(select(version).where(version.c.id == str(proposed_id)))
            .mappings()
            .one()
        )
        if proposal_row["kind"] != "proposed" or not proposal_row["sealed"]:
            raise ValueError("apply requires a sealed proposed version")
        feed = self._feed(connection, proposal_row["feed_id"])
        if feed["state"] == "published" and feed["proposed_version_id"] == str(proposed_id):
            return self._outcome(feed)
        workspace = self._workspace(connection, feed["workspace_id"], lock=True)
        if (
            workspace["proposed_version_id"] != str(proposed_id)
            or workspace["applied_version_id"] != proposal_row["base_version_id"]
            or workspace["configuration_id"] != proposal_row["configuration_id"]
        ):
            raise PublicationConflict("proposal, applied baseline or settings changed; rebuild")
        config = Configuration.model_validate(workspace["configuration"])
        previous = (
            self._revision(connection, workspace["applied_version_id"])
            if workspace["applied_version_id"]
            else None
        )
        proposal = self._revision(connection, proposed_id)
        if now < proposal.published_at:
            raise ValueError("apply clock predates proposal")
        reapply = bool(
            previous
            and str(previous.snapshot_id) == feed["id"]
            and previous.configuration_id != config.id
        )
        _, _, candidate = self._prepare(connection, feed, config, previous, now, reapply=reapply)
        if candidate.rejected:
            raise PublicationConflict("source no longer eligible; restage with current evidence")
        revision = self._persist_version(connection, feed, config, candidate, "applied")
        self._incidents(connection, revision, candidate, config, proposed_id)
        recommendations = self.tables["recommendation"]
        connection.execute(
            update(recommendations)
            .where(
                recommendations.c.proposed_version_id == str(proposed_id),
                recommendations.c.category == "metadata",
                recommendations.c.status == "ready",
            )
            .values(status="auto_applied", applied_version_id=str(revision.id), updated_at=now)
        )
        self._audit(
            connection,
            revision.population_id,
            "organization_published",
            now,
            {
                "changes": compare_organizations(previous, revision.people),
                "diagnostics": [d.model_dump(mode="json") for d in candidate.diagnostics],
            },
            feed_id=feed["id"],
            version_id=revision.id,
            actor="service:" + config.policy.source_id,
        )
        connection.execute(
            update(self.tables["workspace"])
            .where(self.tables["workspace"].c.id == revision.population_id)
            .values(applied_version_id=str(revision.id))
        )
        connection.execute(
            update(self.tables["feed"])
            .where(self.tables["feed"].c.id == feed["id"])
            .values(state="published", applied_version_id=str(revision.id))
        )
        # Persist feed-driven return eligibility in this same transaction. The follow-up
        # configuration reapply cannot recurse: its managed exclusions no longer contain
        # these people. Stage-only/rejected feeds never reach this boundary.
        from otm.organization.associations import TenancyRegistry

        registry = TenancyRegistry(self, revision.population_id)
        state = registry._state(connection, config)
        returned = {str(i) for i in config.managed_exclusions} - state["hidden"]
        if returned:
            changed = config.model_copy(
                update={
                    "id": uuid4(),
                    "managed_exclusions": tuple(
                        i for i in config.managed_exclusions if str(i) not in returned
                    ),
                    "outside_person_ids": tuple(
                        i for i in config.outside_person_ids if str(i) not in returned
                    ),
                    "pending_onboarding_person_ids": tuple(UUID(i) for i in state["pending"]),
                    "review_decisions": tuple(
                        d
                        for d in config.review_decisions
                        if not (d.kind == "TENANCY_SETUP_REVIEW" and str(d.person_id) in returned)
                    ),
                }
            )
            return self.update_configuration(
                changed,
                expected_version_id=revision.id,
                expected_proposed_id=UUID(str(proposed_id)),
                expected_configuration_id=config.id,
                actor="service:organization",
                reason="Returned employees require tenancy onboarding.",
                observed_at=now,
                connection=connection,
            )
        return Outcome(
            snapshot_id=feed["id"],
            state="published",
            revision_id=revision.id,
            proposed_version_id=proposed_id,
            diagnostics=candidate.diagnostics,
        )

    # Apply a staged source-bound proposal; caller supplies an ID, never candidate
    # contents.
    def apply(self, proposed_version_id: UUID, observed_at: datetime | None = None) -> Outcome:
        with self.engine.begin() as connection:
            return self._apply(connection, proposed_version_id, utc(observed_at))

    # Stage and automatically apply valid metadata in one transaction, leaving exceptions
    # open.
    def reconcile(self, feed_id: UUID, observed_at: datetime | None = None) -> Outcome:
        now = utc(observed_at)
        with self.engine.begin() as connection:
            staged = self._stage(connection, feed_id, now)
            if staged.state == "staged":
                return self._apply(connection, staged.proposed_version_id, now)
            return (
                staged.model_copy(update={"state": "duplicate"})
                if staged.original_state
                else staged
            )

    # Compatibility boundary: verify all semantic inputs before source-bound
    # reconciliation.
    def publish(self, snapshot_id: UUID, candidate: Candidate) -> Outcome:
        with self.engine.begin() as connection:
            feed = self._feed(connection, snapshot_id)
            workspace = self._workspace(connection, feed["workspace_id"], lock=True)
            expected = str(candidate.expected_head_id) if candidate.expected_head_id else None
            if workspace["applied_version_id"] != expected or workspace["configuration_id"] != str(
                candidate.expected_configuration_id
            ):
                raise PublicationConflict("head/configuration changed; rebuild candidate")
            config = Configuration.model_validate(workspace["configuration"])
            previous = self._revision(connection, expected) if expected else None
            _, _, actual = self._prepare(connection, feed, config, previous, candidate.observed_at)

            # Ignore unallocated new UUIDs; compare every source-derived fact and
            # guard input.
            def semantic(value):
                data = value.model_dump(mode="json")
                for person in data["people"]:
                    person.pop("id")
                return data

            if semantic(actual) != semantic(candidate):
                raise ValueError("candidate does not match registered source input")
            staged = self._stage(connection, snapshot_id, candidate.observed_at)
            return (
                self._apply(connection, staged.proposed_version_id, candidate.observed_at)
                if staged.state == "staged"
                else staged
            )

    # Record each delivery, deduplicate input and automatically reconcile valid fresh
    # metadata.
    def ingest(
        self,
        records: tuple[Record, ...],
        envelope: Envelope,
        observed_at: datetime | None = None,
        raw_digest: str | None = None,
    ) -> Outcome:
        now = utc(observed_at)
        feed_id, matching = self.register(envelope, records, now, raw_digest)
        if not matching:
            return Outcome(
                snapshot_id=feed_id,
                state="integrity_conflict",
                diagnostics=(Diagnostic(code="SNAPSHOT_CONTENT_CONFLICT", fatal=True),),
            )
        outcome = self.outcome(feed_id)
        if outcome.state in {"published", "rejected", "superseded"}:
            return outcome.model_copy(
                update={"state": "duplicate", "original_state": outcome.state}
            )
        return self.reconcile(feed_id, now)

    # Atomically audit an admin correction and recompute the same feed under new trusted
    # settings. A supplied connection lets a caller commit registry changes, review closure
    # and audit together; that caller must own the surrounding transaction.
    def update_configuration(
        self,
        config: Configuration,
        *,
        expected_version_id: UUID,
        expected_configuration_id: UUID,
        expected_proposed_id: UUID,
        actor: str,
        reason: str,
        observed_at: datetime | None = None,
        connection=None,
    ) -> Outcome:
        config = Configuration.model_validate(config.model_dump(mode="json"))
        if not actor.strip() or not reason.strip():
            raise ValueError("administrator actor and reason required")
        now = utc(observed_at)
        with (
            nullcontext(connection) if connection is not None else self.engine.begin()
        ) as connection:
            workspace = self._workspace(connection, config.policy.population_id, lock=True)
            if (
                workspace["applied_version_id"] != str(expected_version_id)
                or workspace["configuration_id"] != str(expected_configuration_id)
                or workspace["proposed_version_id"] != str(expected_proposed_id)
            ):
                raise PublicationConflict("admin preview is stale; refresh before correcting")
            old = Configuration.model_validate(workspace["configuration"])
            if config.id == old.id or config.policy != old.policy:
                raise ValueError(
                    "new config ID required; correction cannot change source authority"
                )
            proposal = self._revision(connection, expected_proposed_id)
            connection.execute(
                update(self.tables["workspace"])
                .where(self.tables["workspace"].c.id == workspace["id"])
                .values(
                    configuration_id=str(config.id), configuration=config.model_dump(mode="json")
                )
            )
            self._audit(
                connection,
                workspace["id"],
                "configuration_changed",
                now,
                {
                    "before": old.model_dump(mode="json"),
                    "after": config.model_dump(mode="json"),
                    "reason": reason,
                },
                actor=actor,
            )
            staged = self._stage(connection, proposal.snapshot_id, now, reapply=True)
            if staged.state != "staged":
                raise ValueError("correction does not produce an eligible organization")
            return self._apply(connection, staged.proposed_version_id, now)

    # Audit review acknowledgment without pretending the underlying source issue is
    # fixed.
    def acknowledge(
        self,
        recommendation_id: UUID,
        *,
        expected_version_id: UUID,
        expected_proposed_id: UUID,
        actor: str,
        reason: str,
        observed_at: datetime | None = None,
    ) -> None:
        if not actor.strip() or not reason.strip():
            raise ValueError("administrator actor and reason required")
        now = utc(observed_at)
        table = self.tables["recommendation"]
        with self.engine.begin() as connection:
            row = (
                connection.execute(select(table).where(table.c.id == str(recommendation_id)))
                .mappings()
                .one()
            )
            workspace = self._workspace(connection, row["workspace_id"], lock=True)
            if workspace["applied_version_id"] != str(expected_version_id) or workspace[
                "proposed_version_id"
            ] != str(expected_proposed_id):
                raise PublicationConflict("review context changed; refresh")
            if row["category"] != "exception" or row["status"] not in {"open", "acknowledged"}:
                raise ValueError("only an active exception can be acknowledged")
            connection.execute(
                update(table)
                .where(table.c.id == str(recommendation_id))
                .values(status="acknowledged", actor=actor, reason=reason, updated_at=now)
            )
            self._audit(
                connection,
                row["workspace_id"],
                "exception_acknowledged",
                now,
                {"recommendation_id": str(recommendation_id), "reason": reason},
                actor=actor,
            )

    # Read pointers and explicit proposal status from one consistent database statement.
    #
    # Applied and proposed IDs identify separate records even after convergence.
    # The feed's recorded application link establishes completion; pointer equality does not.
    # Status describes workflow state, not a waiver of freshness checks or open exceptions.
    def workspace_context(self, workspace_id: str) -> dict:
        workspace = self.tables["workspace"]
        proposal = self.tables["version"].alias("context_proposal")
        feed = self.tables["feed"].alias("context_feed")
        statement = (
            select(
                workspace,
                proposal.c.base_version_id.label("proposal_base_id"),
                proposal.c.configuration_id.label("proposal_configuration_id"),
                proposal.c.sealed.label("proposal_sealed"),
                feed.c.state.label("feed_state"),
                feed.c.proposed_version_id.label("feed_proposal_id"),
                feed.c.applied_version_id.label("feed_applied_id"),
            )
            .select_from(
                workspace.outerjoin(
                    proposal, workspace.c.proposed_version_id == proposal.c.id
                ).outerjoin(feed, proposal.c.feed_id == feed.c.id)
            )
            .where(workspace.c.id == workspace_id)
        )
        # One statement prevents a concurrent publication mixing old pointers with new outcomes.
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().one()
        if row["proposed_version_id"] is None:
            status = "no_proposal"
            message = "No organization proposal has been staged yet."
        elif (
            row["proposal_configuration_id"] == row["configuration_id"]
            and row["proposal_sealed"]
            and row["feed_state"] == "published"
            and row["feed_proposal_id"] == row["proposed_version_id"]
            and row["feed_applied_id"] == row["applied_version_id"]
        ):
            status = "already_applied"
            message = (
                "This proposal has already been applied. The version IDs identify separate "
                "proposed and applied records; no application is pending."
            )
        elif (
            row["proposal_configuration_id"] == row["configuration_id"]
            and row["proposal_sealed"]
            and row["feed_state"] == "staged"
            and row["feed_proposal_id"] == row["proposed_version_id"]
            and row["proposal_base_id"] == row["applied_version_id"]
        ):
            status = "pending_application"
            message = "A proposal is staged and has not been applied. Inspect it before applying."
        else:
            status = "stale"
            message = (
                "The proposal no longer matches the applied baseline or configuration. "
                "Refresh and rebuild it before applying."
            )
        return {
            "workspace_id": row["id"],
            "applied_version_id": row["applied_version_id"],
            "proposed_version_id": row["proposed_version_id"],
            "configuration_id": row["configuration_id"],
            "proposal_status": status,
            "message": message,
        }

    # Read one allowlisted inspection view for local CLI/API demonstrations.
    def inspection_rows(self, view: str, workspace_id: str) -> list[dict]:
        if view not in {
            "current_organization",
            "proposed_organization",
            "organization_reconciliation",
            "pending_organization_reviews",
        }:
            raise ValueError("unknown inspection view")
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    text(f'SELECT * FROM "{self.schema}".{view} WHERE workspace_id=:workspace'),  # nosec B608
                    {"workspace": workspace_id},
                ).mappings()
            ]
