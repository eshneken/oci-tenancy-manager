"""Preserve the eleven-table inspection prototype in a separate eight-table schema."""

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text, update

from otm.organization.contracts import Candidate, Configuration, Envelope, Revision
from otm.organization.store import Store


# Copy all legacy identities, evidence and history without changing the original schema.
#
# Migrated data is all-or-nothing in the target; empty target DDL is initialized separately
# and rejects partial/repeated destinations.
# A populated migrated destination returns its prior summary only if the marker exists.
# The legacy schema is retained for inspection and rollback; no table is dropped.
def migrate_legacy(store: Store, legacy_schema: str) -> dict:
    if not re.fullmatch(r"otm_[a-z0-9_]+", legacy_schema) or legacy_schema == store.schema:
        raise ValueError("distinct safe source/target schemas required")
    store.initialize()
    with store.engine.begin() as connection:
        existing = (
            connection.execute(
                select(store.tables["event"]).where(
                    store.tables["event"].c.kind == "legacy_schema_migrated"
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["data"]["legacy_schema"] != legacy_schema:
                raise ValueError("migration marker belongs to different source")
            return existing["data"]
        if connection.execute(select(store.tables["workspace"].c.id)).first():
            raise ValueError("target is populated without a migration marker")

        # Read only allowlisted legacy tables; schema names have already been validated.
        def rows(table: str) -> list[dict]:
            allowed = {
                "configuration",
                "population",
                "person",
                "snapshot",
                "result",
                "receipt",
                "revision",
                "state",
                "incident",
                "notification",
                "event",
            }
            if table not in allowed:
                raise ValueError("unknown legacy table")
            return [
                {
                    key: str(value) if isinstance(value, UUID) else value
                    for key, value in row.items()
                }
                for row in connection.execute(
                    text(f'SELECT * FROM "{legacy_schema}".org_{table}')  # nosec B608
                ).mappings()
            ]

        data = {
            name: rows(name)
            for name in (
                "configuration",
                "population",
                "person",
                "snapshot",
                "result",
                "receipt",
                "revision",
                "state",
                "incident",
                "notification",
                "event",
            )
        }
        configurations = {row["id"]: row["data"] for row in data["configuration"]}
        results = {row["snapshot_id"]: row for row in data["result"]}
        snapshots = {row["id"]: row for row in data["snapshot"]}
        revisions = {row["id"]: row for row in data["revision"]}
        for row in data["population"]:
            connection.execute(
                store.tables["workspace"]
                .insert()
                .values(
                    id=row["id"],
                    configuration_id=row["configuration_id"],
                    configuration=configurations[row["configuration_id"]],
                )
            )
        connection.execute(store.tables["person"].insert(), data["person"])
        for row in data["snapshot"]:
            outcome = results[row["id"]]
            connection.execute(
                store.tables["feed"]
                .insert()
                .values(
                    id=row["id"],
                    workspace_id=row["population_id"],
                    source_id=row["source_id"],
                    external_id=row["external_id"],
                    digest=row["digest"],
                    data=row["data"],
                    captured_at=Envelope.model_validate(row["data"]["envelope"]).captured_at,
                    state=outcome["state"],
                    diagnostics=outcome["diagnostics"],
                    applied_version_id=outcome["revision_id"],
                )
            )
        pending = dict(revisions)
        imported = set()
        while pending:
            ready = [
                row
                for row in pending.values()
                if row["predecessor_id"] is None or row["predecessor_id"] in imported
            ]
            if not ready:
                raise ValueError("legacy predecessor graph cannot be migrated")
            for row in ready:
                connection.execute(
                    store.tables["version"]
                    .insert()
                    .values(
                        id=row["id"],
                        workspace_id=row["population_id"],
                        kind="applied",
                        base_version_id=row["predecessor_id"],
                        feed_id=row["snapshot_id"],
                        configuration_id=row["configuration_id"],
                        configuration=configurations[row["configuration_id"]],
                        data=row["data"],
                    )
                )
                states = [state for state in data["state"] if state["revision_id"] == row["id"]]
                supplied = {
                    item["email"] for item in snapshots[row["snapshot_id"]]["data"]["records"]
                }
                for state in states:
                    person = state["data"]
                    connection.execute(
                        store.tables["member"]
                        .insert()
                        .values(
                            version_id=row["id"],
                            person_id=state["person_id"],
                            email=state["email"],
                            manager_person_id=state["manager_person_id"],
                            full_name=person["full_name"],
                            manager_email=person["manager_email"],
                            profile=person["profile"],
                            evidence="feed_row"
                            if state["email"] in supplied
                            else "retained"
                            if person["profile"] == "employee"
                            else person["profile"],
                            lob_id=person["lob_id"],
                            accountable_leader_email=person["accountable_leader_email"],
                            designee_emails=person["designee_emails"],
                            ancestry=person["ancestry"],
                            absence_review=person["absence_review"],
                            data=person,
                        )
                    )
                connection.execute(
                    update(store.tables["version"])
                    .where(store.tables["version"].c.id == row["id"])
                    .values(sealed=True)
                )
                imported.add(row["id"])
                pending.pop(row["id"])
        # Historical proposals are reconstructed copies of accepted state, not new
        # source observations or claims about what was staged by the legacy service.
        proposals = {}
        for row in data["revision"]:
            old = store._revision(connection, row["id"])
            config = Configuration.model_validate(configurations[str(old.configuration_id)])
            feed = store._feed(connection, old.snapshot_id)
            candidate = Candidate(
                envelope=Envelope.model_validate(feed["data"]["envelope"]),
                expected_head_id=old.predecessor_id,
                expected_configuration_id=old.configuration_id,
                observed_at=old.published_at,
                people=old.people,
                diagnostics=(),
                assessed_coverage=old.assessed_coverage,
                absence_eligible=old.absence_eligible,
                issues=(),
                employee_row_emails=tuple(item["email"] for item in feed["data"]["records"]),
            )
            proposal = store._persist_version(connection, feed, config, candidate, "proposed")
            proposals[row["id"]] = proposal.id
        for row in data["population"]:
            if row["head_id"]:
                proposal_id = proposals[row["head_id"]]
                old = revisions[row["head_id"]]
                connection.execute(
                    update(store.tables["workspace"])
                    .where(store.tables["workspace"].c.id == row["id"])
                    .values(applied_version_id=row["head_id"], proposed_version_id=str(proposal_id))
                )
                connection.execute(
                    update(store.tables["feed"])
                    .where(store.tables["feed"].c.id == old["snapshot_id"])
                    .values(proposed_version_id=str(proposal_id))
                )
        # Historical receipts and action events retain their exact IDs and immutable payloads.
        for row in data["receipt"]:
            feed = snapshots[row["snapshot_id"]]
            connection.execute(
                store.tables["event"]
                .insert()
                .values(
                    id=row["id"],
                    workspace_id=feed["population_id"],
                    feed_id=row["snapshot_id"],
                    actor="service:legacy-intake",
                    kind="feed_received",
                    at=row["received_at"],
                    data={"disposition": row["disposition"], "raw_digest": row["raw_digest"]},
                )
            )
        for row in data["event"]:
            original = revisions[row["revision_id"]]
            connection.execute(
                store.tables["event"]
                .insert()
                .values(
                    id=row["id"],
                    workspace_id=original["population_id"],
                    version_id=row["revision_id"],
                    actor=row["actor"],
                    kind=row["kind"],
                    at=row["at"],
                    data=row["data"],
                )
            )
            for change in row["data"].get("changes", []):
                address = next(p["email"] for p in data["person"] if p["id"] == change["person_id"])
                for field, values in change["fields"].items():
                    connection.execute(
                        store.tables["recommendation"]
                        .insert()
                        .values(
                            id=str(uuid4()),
                            workspace_id=original["population_id"],
                            feed_id=original["snapshot_id"],
                            proposed_version_id=str(proposals[row["revision_id"]]),
                            applied_version_id=row["revision_id"],
                            person_id=change["person_id"],
                            category="metadata",
                            kind="legacy_metadata_change",
                            target=address,
                            field=field,
                            before_value=values["before"],
                            after_value=values["after"],
                            status="auto_applied",
                            created_at=row["at"],
                            updated_at=row["at"],
                        )
                    )
        for row in data["incident"]:
            first = revisions[row["first_revision_id"]]
            last = revisions[row["last_revision_id"]]
            person = next(
                (p for p in data["person"] if p["email"] in row["target"].split(":")), None
            )
            connection.execute(
                store.tables["recommendation"]
                .insert()
                .values(
                    id=row["id"],
                    workspace_id=row["population_id"],
                    feed_id=first["snapshot_id"],
                    proposed_version_id=str(proposals[row["first_revision_id"]]),
                    applied_version_id=row["last_revision_id"],
                    person_id=person["id"] if person else None,
                    category="exception",
                    kind=row["kind"],
                    target=row["target"],
                    status="resolved" if row["resolved_at"] else "open",
                    created_at=Revision.model_validate(
                        {**first["data"], "people": ()}
                    ).published_at,
                    updated_at=Revision.model_validate({**last["data"], "people": ()}).published_at,
                    resolved_at=row["resolved_at"],
                )
            )
        for row in data["notification"]:
            connection.execute(
                store.tables["notification"]
                .insert()
                .values(
                    id=row["id"],
                    recommendation_id=row["incident_id"],
                    version_id=row["revision_id"],
                    recipients=row["recipients"],
                    state=row["state"],
                )
            )
        summary = {
            "legacy_schema": legacy_schema,
            "schema": store.schema,
            "people": len(data["person"]),
            "historical_applied_versions": len(data["revision"]),
            "feeds": len(data["snapshot"]),
            "receipts": len(data["receipt"]),
            "audit_events": len(data["event"]),
            "exceptions": len(data["incident"]),
            "notification_intents": len(data["notification"]),
        }
        for row in data["population"]:
            store._audit(
                connection, row["id"], "legacy_schema_migrated", datetime.now(UTC), summary
            )
        # Compare all immutable identity/state/source/event/outbox payloads before committing.
        copied_people = {
            row["email"]: row["id"]
            for row in connection.execute(select(store.tables["person"])).mappings()
        }
        if copied_people != {row["email"]: row["id"] for row in data["person"]}:
            raise ValueError("migrated identities differ from source")
        for row in data["revision"]:
            migrated = store._revision(connection, UUID(row["id"]))
            original_people = sorted(
                (state["data"] for state in data["state"] if state["revision_id"] == row["id"]),
                key=lambda p: p["email"],
            )
            # Database collation can order punctuated emails differently from Python;
            # identity-keyed comparison preserves every field without assuming list order.
            copied_states = {
                person.email: person.model_dump(mode="json") for person in migrated.people
            }
            if copied_states != {person["email"]: person for person in original_people}:
                raise ValueError("migrated historical person state differs from source")
        for row in data["snapshot"]:
            copied = store._feed(connection, row["id"])
            if copied["data"] != row["data"] or copied["digest"] != row["digest"]:
                raise ValueError("migrated source evidence differs")
        for row in data["event"]:
            copied = (
                connection.execute(
                    select(store.tables["event"]).where(store.tables["event"].c.id == row["id"])
                )
                .mappings()
                .one()
            )
            if any(copied[key] != row[key] for key in ("actor", "kind", "at", "data")):
                raise ValueError("migrated audit evidence differs")
        for row in data["notification"]:
            copied = (
                connection.execute(
                    select(store.tables["notification"]).where(
                        store.tables["notification"].c.id == row["id"]
                    )
                )
                .mappings()
                .one()
            )
            if copied["recipients"] != row["recipients"] or copied["state"] != row["state"]:
                raise ValueError("migrated notification evidence differs")
        for row in data["receipt"]:
            copied = (
                connection.execute(
                    select(store.tables["event"]).where(store.tables["event"].c.id == row["id"])
                )
                .mappings()
                .one()
            )
            if copied["at"] != row["received_at"] or copied["data"] != {
                "disposition": row["disposition"],
                "raw_digest": row["raw_digest"],
            }:
                raise ValueError("migrated receipt evidence differs")
        return summary
