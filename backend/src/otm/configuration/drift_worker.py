"""Native reference-only, read-only check execution with current authority and immutable results."""

from sqlalchemy import func, select, update

from otm.configuration.drift import check_intent, check_operation
from otm.configuration.drift_context import expected_objects, same_assignment
from otm.configuration.drift_records import save_check
from otm.configuration.observations import inspect_configuration, unavailable_results
from otm.storage.tables import administrator, configuration_check, operation, org_workspace, tenancy
from otm.storage.transaction import require_transaction


# Fake provider reads run inside bounded serialized transactions; no network adapter is composed
# here.
class ConfigurationCheckWorker:
    # Dependencies carry exact deployment scope, fresh authority, server UTC and a read capability.
    def __init__(self, engine, workspace, clock, policy_loader, facade):
        self.engine, self.workspace, self.clock, self.policy_loader, self.facade = (
            engine,
            workspace,
            clock,
            policy_loader,
            facade,
        )

    # Replayed deliveries skip sealed child attempts, retaining one immutable row and one
    # audit event.
    def run(self, identifier):
        with self.engine.begin() as connection:
            row = self._locked(connection, identifier)
            if row is None:
                return
            frozen = check_intent(row)
            targets = frozen.intent.targets
            connection.execute(
                update(operation)
                .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                .values(
                    state="running", stage="Reading assigned configuration", updated_at=self.clock()
                )
            )
        for target in targets:
            self._target(identifier, target.tenancy_id)
        with self.engine.begin() as connection:
            row = self._locked(connection, identifier)
            if row is None:
                return
            count = connection.scalar(
                select(func.count())
                .select_from(configuration_check)
                .where(
                    configuration_check.c.workspace_id == self.workspace,
                    configuration_check.c.operation_id == identifier,
                )
            )
            if count == len(targets):
                at = self.clock()
                connection.execute(
                    update(operation)
                    .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                    .values(
                        state="succeeded",
                        stage="Configuration checks complete",
                        completed_at=at,
                        updated_at=at,
                        revision=operation.c.revision + 1,
                    )
                )

    # The same anchor/workspace ordering as mutations serializes acquisition before all fake reads.
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
        ).scalar_one()
        connection.execute(
            select(operation.c.id)
            .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
            .with_for_update()
        ).scalar_one_or_none()
        rows = check_operation(connection, self.workspace, identifier)
        return rows[0] if rows and rows[0]["state"] in {"queued", "running"} else None

    # Fresh authorization and assignment fences precede reads; only sealed evidence is written.
    def _target(self, identifier, target_id):
        with self.engine.begin() as connection:
            row = self._locked(connection, identifier)
            if row is None:
                return
            if connection.scalar(
                select(configuration_check.c.id).where(
                    configuration_check.c.workspace_id == self.workspace,
                    configuration_check.c.operation_id == identifier,
                    configuration_check.c.tenancy_id == target_id,
                )
            ):
                return
            frozen = check_intent(row)
            intent = frozen.intent
            target = next(item for item in intent.targets if item.tenancy_id == target_id)
            registered = (
                connection.execute(
                    select(tenancy)
                    .where(tenancy.c.workspace_id == self.workspace, tenancy.c.id == target_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
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
            current = self.policy_loader()
            code = None
            if (
                grant is None
                or grant["status"] != "active"
                or grant["authorization_revision"] != intent.authorization_revision
                or (grant["issuer"], grant["subject"])
                != (frozen.actor.issuer, frozen.actor.subject)
            ):
                code = "AUTHORIZATION_CHANGED"
            elif (
                current.execution_paused
                or current.policy != self.facade.policy
                or current.policy.policy_revision != intent.policy_revision
            ):
                code = "PROVIDER_UNAVAILABLE"
            elif not same_assignment(target, registered, current.policy):
                code = "ASSIGNMENT_CHANGED"
            elif registered["operation_id"]:
                code = "TENANCY_BUSY"
            started = self.clock()
            try:
                desired = expected_objects(connection, self.workspace, target)
            except ValueError:
                desired = None
                code = "ASSIGNMENT_CHANGED"
            if code:
                results = unavailable_results(target, desired, code)
                state = "superseded" if code == "ASSIGNMENT_CHANGED" else "unavailable"
            else:
                results, state = inspect_configuration(
                    target, desired, self.facade, registered["configuration_observation"]
                )
            checked = max(started, self.clock())
            save_check(connection, row, target, results, state, started, checked)
