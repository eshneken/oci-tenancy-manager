"""Per-child simulation with immutable targets, fresh authority and verified prefixes."""

from sqlalchemy import select, update

from otm.configuration.override_contracts import effective_content
from otm.configuration.revisions import load_configuration
from otm.configuration.rollout import operation_row, save_target_result, update_intent
from otm.configuration.service import published_baseline
from otm.providers.configuration import configure_target
from otm.storage.tables import administrator, operation, operation_step, org_workspace, tenancy
from otm.storage.transaction import require_transaction


# Keep dispatch guards independently testable; no mutable latest lookup can retarget accepted work.
def target_is_current(row, target, intent, identifier):
    return bool(
        row
        and row["workspace_id"] == intent.workspace_id
        and row["id"] == target.tenancy_id
        and row["status"] == "active"
        and row["provider_mode"] == "simulated"
        and row["operation_id"] == identifier
        and row["revision"] == target.revision + 1
        and row["baseline_version_id"] == intent.baseline.id
        and row.get("desired_configuration_id")
        == (target.configuration.id if target.configuration else None)
        and row.get("last_verified_configuration_id") == target.source_verified_configuration_id
        and row.get("verified_baseline_version_id") == target.source_verified_id
        and row["tenancy_ocid"] == target.tenancy_ocid
        and row["parent_tenancy_ocid"] == target.parent_tenancy_ocid
        and row["organization_id"] == target.organization_id
    )


# Authority is checked again for every child, not merely once at the beginning of a long batch.
def dispatch_code(intent, actor, grant, policy):
    if (
        not grant
        or grant["status"] != "active"
        or grant["authorization_revision"] != intent.authorization_revision
        or (grant["issuer"], grant["subject"]) != (actor.issuer, actor.subject)
    ):
        return "AUTHORIZATION_CHANGED"
    if policy.execution_paused:
        return "LIFECYCLE_UNAVAILABLE"
    current = policy.policy
    if (
        current.workspace_id,
        current.policy_revision,
        current.organization_id,
        current.parent_tenancy_ocid,
    ) != (
        intent.workspace_id,
        intent.policy_revision,
        intent.organization_id,
        intent.parent_tenancy_ocid,
    ):
        return "TARGET_CHANGED"
    return None


# Reuse native job identity and per-target steps; no second coordinator or queue is introduced.
class ConfigurationUpdateWorker:
    # This worker is qualified for pure local simulation only, with explicit policy and facade.
    def __init__(self, engine, workspace, clock, policy_loader, facade):
        self.engine, self.workspace, self.clock, self.policy_loader, self.facade = (
            engine,
            workspace,
            clock,
            policy_loader,
            facade,
        )

    # One native delivery may finish several children; each commit releases locks between children.
    def run(self, identifier):
        try:
            with self.engine.connect() as connection:
                row = operation_row(connection, self.workspace, identifier)
                if row is None or row["state"] not in {"queued", "running"}:
                    return
                targets = update_intent(row).intent.targets
            for target in targets:
                self._target(identifier, target.tenancy_id)
            self._finish(identifier)
        except Exception:
            # A failed local transaction has no external OCI effects; retain reservations for retry.
            # A real adapter needs split dispatch/reconciliation before it can replace this worker.
            with self.engine.begin() as connection:
                connection.execute(
                    update(operation)
                    .where(
                        operation.c.workspace_id == self.workspace,
                        operation.c.id == identifier,
                        operation.c.kind == "configuration_update",
                        operation.c.state.in_(["queued", "running"]),
                    )
                    .values(
                        state="needs_attention",
                        stage="Configuration execution unavailable; retry incomplete targets",
                        updated_at=self.clock(),
                        revision=operation.c.revision + 1,
                    )
                )

    # Lock in the same administrator→workspace→operation order as all admission and revoke paths.
    def _locked(self, connection, identifier):
        require_transaction(connection)
        anchor = connection.execute(
            select(administrator.c.id)
            .where(
                administrator.c.workspace_id == self.workspace,
                administrator.c.identity_kind == "local_recovery",
                administrator.c.status == "active",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if anchor is None:
            return None
        connection.execute(
            select(org_workspace.c.id).where(org_workspace.c.id == self.workspace).with_for_update()
        ).scalar_one_or_none()
        connection.execute(
            select(operation.c.id)
            .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
            .with_for_update()
        ).scalar_one_or_none()
        row = operation_row(connection, self.workspace, identifier)
        return row if row and row["state"] in {"queued", "running"} else None

    # Verified children are skipped even after a later independent update changes their
    # registry pin.
    def _target(self, identifier, target_id):
        with self.engine.begin() as connection:
            row = self._locked(connection, identifier)
            if row is None:
                return
            frozen = update_intent(row)
            intent = frozen.intent
            target = next(t for t in intent.targets if t.tenancy_id == target_id)
            step = (
                connection.execute(
                    select(operation_step).where(
                        operation_step.c.workspace_id == self.workspace,
                        operation_step.c.operation_id == identifier,
                        operation_step.c.intent_revision == 1,
                        operation_step.c.step_key == "configuration:" + str(target_id),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if step and step["state"] == "verified":
                return
            grant = (
                connection.execute(
                    select(administrator).where(
                        administrator.c.workspace_id == self.workspace,
                        administrator.c.id == intent.administrator_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            code = dispatch_code(intent, frozen.actor, grant, self.policy_loader())
            registered = (
                connection.execute(
                    select(tenancy)
                    .where(tenancy.c.workspace_id == self.workspace, tenancy.c.id == target_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if not target_is_current(registered, target, intent, identifier):
                code = "TARGET_CHANGED"
            if (
                not code
                and published_baseline(connection, self.workspace, intent.baseline.id)
                != intent.baseline
            ):
                code = "TARGET_CHANGED"
            if (
                not code
                and target.configuration
                and load_configuration(
                    connection, self.workspace, target_id, target.configuration.id
                )
                != target.configuration
            ):
                code = "TARGET_CHANGED"
            at = self.clock()
            category = None
            if not code:
                objects, category = configure_target(
                    target,
                    intent.baseline.model_copy(
                        update={"content": effective_content(intent.baseline, target.configuration)}
                    )
                    if target.configuration
                    else intent.baseline,
                    self.facade,
                    registered["configuration_observation"],
                )
                code = "CONFIGURATION_UNVERIFIED" if category else "CONFIGURATION_VERIFIED"
                # Persist partial fake-cloud state, but advance verification
                # only after every readback.
                connection.execute(
                    update(tenancy)
                    .where(tenancy.c.workspace_id == self.workspace, tenancy.c.id == target_id)
                    .values(
                        configuration_observation=objects,
                        updated_at=at,
                        **(
                            {
                                "verified_baseline_version_id": intent.baseline.id,
                                "last_verified_configuration_id": target.configuration.id
                                if target.configuration
                                else None,
                                "configuration_verified_at": at,
                                "operation_id": None,
                                "revision": registered["revision"] + 1,
                            }
                            if not category
                            else {}
                        ),
                    )
                )
                connection.execute(
                    update(operation)
                    .where(operation.c.id == identifier, operation.c.workspace_id == self.workspace)
                    .values(effect_knowledge="known")
                )
            save_target_result(
                connection, row, target, intent.baseline, at, code=code, category=category
            )
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier, operation.c.workspace_id == self.workspace)
                .values(
                    state="running",
                    stage="Updating " + target.name,
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
            connection.execute(
                update(org_workspace)
                .where(org_workspace.c.id == self.workspace)
                .values(registry_revision=org_workspace.c.registry_revision + 1)
            )

    # The batch is successful only when every accepted child has an independently verified result.
    def _finish(self, identifier):
        with self.engine.begin() as connection:
            row = self._locked(connection, identifier)
            if row is None:
                return
            intent = update_intent(row).intent
            verified = set(
                connection.execute(
                    select(operation_step.c.step_key).where(
                        operation_step.c.workspace_id == self.workspace,
                        operation_step.c.operation_id == identifier,
                        operation_step.c.intent_revision == 1,
                        operation_step.c.state == "verified",
                    )
                )
                .scalars()
                .all()
            )
            complete = all("configuration:" + str(t.tenancy_id) in verified for t in intent.targets)
            at = self.clock()
            connection.execute(
                update(operation)
                .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                .values(
                    state="succeeded" if complete else "needs_attention",
                    stage="Baseline update verified locally"
                    if complete
                    else "Some tenancy updates need attention",
                    completed_at=at if complete else None,
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
