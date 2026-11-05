"""Audited fresh test runs for the CSV lab, preserving immutable evidence and other workspaces."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from otm.organization.contracts import Configuration
from otm.organization.store import PublicationConflict, Store


# Resolve a stable lab name to its current run using append-only reset audit events.
class LocalLab:
    # Restrict reset support to explicitly named, local CSV prototype workspaces.
    def __init__(self, store: Store, base_workspace: str):
        if not base_workspace.startswith(("root-leader-csv-", "ui-test-")):
            raise ValueError("clean is limited to CSV lab workspaces")
        if store.configuration(base_workspace).policy.source_id != "local-csv-demo":
            raise ValueError("clean is limited to the local CSV demo source")
        self.store = store
        self.base_workspace = base_workspace

    # Find the latest reset of this lab; callers serialize writes on its base workspace.
    def _latest_reset(self, connection):
        events = self.store.tables["event"]
        return (
            connection.execute(
                select(events)
                .where(
                    events.c.workspace_id == self.base_workspace,
                    events.c.kind == "local_lab_cleaned",
                )
                .order_by(events.c.at.desc(), events.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )

    # Resolve the current run on each request so resets survive restarts and multiple tabs.
    def active(self) -> str:
        with self.store.engine.connect() as connection:
            latest = self._latest_reset(connection)
            return latest["data"]["next_workspace_id"] if latest else self.base_workspace

    # Atomically archive the visible run and create an empty one with the same configuration.
    #
    # No evidence is deleted, triggers are never bypassed, and global person identities remain
    # untouched. A new workspace resets the baseline and administrator decisions without
    # altering prior snapshots. The base lock serializes resets; the active lock waits for
    # in-flight publication before checking the confirmation's expected pointers/configuration.
    def clean(self, expected: dict) -> str:
        store = self.store
        with store.engine.begin() as connection:
            store._workspace(connection, self.base_workspace, lock=True)
            latest = self._latest_reset(connection)
            active = latest["data"]["next_workspace_id"] if latest else self.base_workspace
            if expected["workspace_id"] != active:
                raise PublicationConflict("Workspace changed. Refresh and confirm again.")
            current = store._workspace(connection, active, lock=True)
            for field in ("applied_version_id", "proposed_version_id", "configuration_id"):
                if current[field] != expected[field]:
                    raise PublicationConflict("Organization changed. Refresh and confirm again.")
            config = Configuration.model_validate(current["configuration"])
            identifier = self.base_workspace + "--run-" + uuid4().hex
            next_config = config.model_copy(
                update={
                    "id": uuid4(),
                    "review_decisions": (),
                    "excluded_emails": (),
                    "identity_merges": (),
                    "managed_exclusions": (),
                    "pending_onboarding_person_ids": (),
                    "registry_initialized": False,
                    "outside_person_ids": (),
                    "policy": config.policy.model_copy(update={"population_id": identifier}),
                }
            )
            connection.execute(
                store.tables["workspace"]
                .insert()
                .values(
                    id=identifier,
                    configuration_id=str(next_config.id),
                    configuration=next_config.model_dump(mode="json"),
                )
            )
            now = datetime.now(UTC)
            # Clock rollback or same-timestamp resets must not make an older run active again.
            if latest:
                now = max(now, latest["at"] + timedelta(microseconds=1))
            store._audit(
                connection,
                identifier,
                "workspace_configured",
                now,
                {"configuration": next_config.model_dump(mode="json")},
                actor="local:admin",
            )
            store._audit(
                connection,
                self.base_workspace,
                "local_lab_cleaned",
                now,
                {
                    "previous_workspace_id": active,
                    "next_workspace_id": identifier,
                    "previous_applied_version_id": current["applied_version_id"],
                    "previous_proposed_version_id": current["proposed_version_id"],
                    "history_preserved": True,
                },
                actor="local:admin",
            )
            return identifier
