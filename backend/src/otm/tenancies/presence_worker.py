"""Fenced user-presence reads release database locks before any provider work."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update

from otm.providers.required_user import paired_observation
from otm.providers.required_user_contracts import (
    InspectRequiredUser,
    RequiredUserReadContext,
)
from otm.storage.tables import administrator, operation, org_workspace, tenancy
from otm.storage.tables import user_presence_check as checks
from otm.tenancies.presence_context import capture_snapshot
from otm.tenancies.presence_records import decode_intent, operation_rows, seal, unknown

# Post-return freshness budget; this does not cancel I/O or configure an OCI SDK timeout.
READ_WINDOW = timedelta(seconds=30)


# The explicit adapter factory consumes authenticated producer facts; no live/fake fallback exists.
class UserPresenceWorker:
    # Deployment scope, policy, UTC and selected adapter are all host-owned dependencies.
    def __init__(
        self,
        engine,
        workspace,
        clock,
        policy_loader,
        policy,
        inspection_factory,
        *,
        notifications=None,
        recovery_console_loader=None,
        recovery_inspection_factory=None,
        administrator_inspection_factory=None,
        key_inspection_factory=None,
        signing_dispatch=None,
    ):
        self.administrator_inspection_factory = administrator_inspection_factory
        self.key_inspection_factory = key_inspection_factory
        self.signing_dispatch = signing_dispatch
        self.engine, self.workspace, self.clock = engine, workspace, clock
        self.notifications = notifications
        self.recovery_console_loader = recovery_console_loader
        self.recovery_inspection_factory = recovery_inspection_factory
        self.policy_loader, self.policy, self.inspection_factory = (
            policy_loader,
            policy,
            inspection_factory,
        )

    # A new attempt fences interrupted workers; only its callback may publish a terminal result.
    def run(self, identifier):
        ticket = self.begin(identifier)
        if ticket is None:
            return
        frozen, check, commands, source = ticket
        results = []
        inspection = None
        if source is not None:
            try:
                inspection = self.inspection_factory(frozen.intent.snapshot, source, self.clock)
            except Exception:
                inspection = None
        for command in commands:
            try:
                started = self.clock()
                result = (
                    paired_observation(command, inspection.inspect(command), started, self.clock())
                    if inspection
                    else unknown(command, self.clock())
                )
            except Exception:
                result = unknown(command, self.clock())
            results.append(result)
        console = self.read_console(commands[1], source, frozen.intent.snapshot)
        assignments = self.read_administrator(commands[0], source)
        recovery_assignments = self.read_administrator(commands[1], source)
        keys = self.read_keys(commands[0], source)
        self.finish(
            identifier,
            check["attempt_id"],
            tuple(commands),
            tuple(results),
            console,
            assignments,
            recovery_assignments,
            keys=keys,
        )

    # Inventory failures remain independent of presence and never become known zero-key reads.
    def read_keys(self, command, source):
        from otm.providers.automation_keys import AutomationKeyCheck, InspectAutomationKeys

        if self.key_inspection_factory is None:
            return None
        fallback = AutomationKeyCheck(
            context=command.context,
            target=command.target,
            checked_at=self.clock(),
            state="unavailable",
        )
        if source is None:
            return fallback
        try:
            request = InspectAutomationKeys(context=command.context, target=command.target)
            started = self.clock()
            result = AutomationKeyCheck.model_validate(
                self.key_inspection_factory(request, source, self.clock).inspect(request)
            )
            finished = self.clock()
            if (
                result.context != request.context
                or result.target != request.target
                or not started <= result.checked_at <= finished <= started + READ_WINDOW
            ):
                return fallback
            return result
        except Exception:
            return fallback

    # Missing legacy capture, failed reads and substituted subjects never gain inferred assignments.
    def read_administrator(self, subject_command, source):
        from otm.providers.administrator_access import (
            AdministratorCheck,
            AdministratorResult,
            InspectAdministratorAccess,
        )

        unknown_result = AdministratorResult(group="unknown", domain_role="unknown")
        fallback = AdministratorCheck(
            context=subject_command.context,
            target=subject_command.target,
            checked_at=self.clock(),
            result=unknown_result,
        )
        capture = (
            getattr(source, subject_command.target.purpose + "_administrator") if source else None
        )
        if capture is None or self.administrator_inspection_factory is None:
            return fallback
        try:
            command = InspectAdministratorAccess(
                context=subject_command.context,
                target=subject_command.target,
                binding=capture.binding,
            )
            started = self.clock()
            observed = AdministratorCheck.model_validate(
                self.administrator_inspection_factory(command, source, self.clock).inspect(command)
            )
            ended = self.clock()
            if (
                observed.context != command.context
                or observed.target != command.target
                or not started <= observed.checked_at <= ended
                or ended - started > READ_WINDOW
            ):
                return fallback
            return observed
        except Exception:
            return fallback

    # A missing legacy capture or unqualified policy read stays Unknown independently of presence.
    def read_console(self, subject_command, source, snapshot):
        from otm.providers.recovery_console import (
            InspectRecoveryConsole,
            RecoveryConsoleCheck,
            RecoveryConsoleResult,
        )

        desired = snapshot.recovery_console_fingerprint
        if desired is None:
            return None
        unverified = RecoveryConsoleResult(
            state="unknown",
            mfa_exemption="unknown",
            network_boundary="unknown",
            desired_fingerprint=desired,
            safe_code="RECOVERY_CONSOLE_UNVERIFIED",
        )
        result = unverified
        try:
            policy = self.recovery_console_loader() if self.recovery_console_loader else None
            capture = source.recovery_console if source else None
            if (
                policy is not None
                and policy.fingerprint == desired
                and capture is not None
                and self.recovery_inspection_factory is not None
            ):
                command = InspectRecoveryConsole(
                    context=subject_command.context,
                    target=subject_command.target,
                    binding=capture.binding,
                    desired=policy,
                )
                observed = self.recovery_inspection_factory(command, source, self.clock).inspect(
                    command
                )
                observed = RecoveryConsoleResult.model_validate(observed)
                if observed.desired_fingerprint == desired:
                    result = observed
        except Exception:
            # Malformed/failed reads publish only the original safe Unknown result.
            result = unverified
        return RecoveryConsoleCheck(
            context=subject_command.context,
            target=subject_command.target,
            checked_at=self.clock(),
            result=result,
        )

    # Serialize the same anchor/workspace/operation/child order as existing lifecycle mutations.
    def locked(self, connection, identifier):
        if (
            connection.scalar(
                select(administrator.c.id)
                .where(
                    administrator.c.workspace_id == self.workspace,
                    administrator.c.identity_kind == "local_recovery",
                    administrator.c.status == "active",
                )
                .with_for_update()
            )
            is None
        ):
            return None
        connection.execute(
            select(org_workspace.c.id).where(org_workspace.c.id == self.workspace).with_for_update()
        ).scalar_one()
        connection.execute(
            select(operation.c.id)
            .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
            .with_for_update()
        ).scalar_one_or_none()
        rows = operation_rows(connection, self.workspace, identifier)
        if not rows or rows[0]["state"] not in {"queued", "running"}:
            return None
        row = rows[0]
        frozen = decode_intent(row)
        child = (
            connection.execute(
                select(tenancy)
                .where(
                    tenancy.c.workspace_id == self.workspace,
                    tenancy.c.id == frozen.intent.snapshot.tenancy_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        check = (
            connection.execute(
                select(checks)
                .where(checks.c.workspace_id == self.workspace, checks.c.operation_id == identifier)
                .with_for_update()
            )
            .mappings()
            .one()
        )
        return row, frozen, child, check

    # Current admin grant and all selected context facts must agree before and after I/O.
    def current(self, connection, frozen, child):
        intent = frozen.intent
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
        if (
            grant is None
            or grant["status"] != "active"
            or grant["authorization_revision"] != intent.authorization_revision
            or (grant["issuer"], grant["subject"]) != (frozen.actor.issuer, frozen.actor.subject)
        ):
            return False
        policy = self.policy_loader()
        if policy.execution_paused or policy.policy != self.policy:
            return False
        console = self.recovery_console_loader() if self.recovery_console_loader else None
        return (
            capture_snapshot(connection, self.workspace, child, policy.policy, console)
            == intent.snapshot
        )

    # Shared source authentication preserves exact setup/repair evidence for every read and repair.
    def source(self, connection, snapshot):
        from otm.tenancies.presence_source import load_presence_source

        return load_presence_source(connection, snapshot)

    # Persist attempt identity before dispatch, then release the transaction and all row locks.
    def begin(self, identifier):
        with self.engine.begin() as connection:
            locked = self.locked(connection, identifier)
            if locked is None:
                return None
            row, frozen, child, stored = locked
            if stored["state"] not in {"queued", "reading"}:
                return None
            check = dict(stored)
            check.update(
                state="reading",
                attempt_number=stored["attempt_number"] + 1,
                attempt_id=uuid4(),
                started_at=self.clock(),
            )
            connection.execute(
                update(checks)
                .where(checks.c.workspace_id == self.workspace, checks.c.operation_id == identifier)
                .values(
                    **{k: check[k] for k in ("state", "attempt_number", "attempt_id", "started_at")}
                )
            )
            connection.execute(
                update(operation)
                .where(operation.c.workspace_id == self.workspace, operation.c.id == identifier)
                .values(
                    state="running",
                    stage="Reading required-user presence",
                    updated_at=check["started_at"],
                    revision=operation.c.revision + 1,
                )
            )
            commands = tuple(
                InspectRequiredUser(
                    target=target,
                    context=RequiredUserReadContext(
                        workspace_id=self.workspace,
                        operation_id=identifier,
                        step_key="required_users:" + str(child["id"]),
                        attempt_id=check["attempt_id"],
                        execution_generation=check["attempt_number"],
                        intent_revision=row["current_intent_revision"],
                        connection_id=frozen.intent.snapshot.connection_id,
                        connection_revision=frozen.intent.snapshot.connection_revision,
                    ),
                )
                for target in frozen.intent.snapshot.subjects
            )
            source = None
            try:
                if self.current(connection, frozen, child) and (
                    self.signing_dispatch is None
                    or self.signing_dispatch(connection, self.workspace, child["id"], self.clock())
                ):
                    source = self.source(connection, frozen.intent.snapshot)
            except (ValueError, RuntimeError):
                source = None
            return frozen, check, commands, source

    # Late/replayed callbacks never replace a newer attempt or a terminal result.
    def finish(
        self,
        identifier,
        attempt,
        commands,
        results,
        console=None,
        assignments=None,
        recovery_assignments=None,
        keys=None,
    ):
        with self.engine.begin() as connection:
            locked = self.locked(connection, identifier)
            if locked is None:
                return
            row, frozen, child, check = locked
            if check["state"] != "reading" or check["attempt_id"] != attempt:
                return
            at = self.clock()
            clock_invalid = at < check["started_at"]
            at = max(at, check["started_at"])
            try:
                current = self.current(connection, frozen, child)
            except (ValueError, RuntimeError):
                current = False
            if not current:
                results = tuple(unknown(c, at) for c in commands)
                state = "superseded"
            elif clock_invalid or at - check["started_at"] > READ_WINDOW:
                # A read that returned too late cannot establish current presence or absence.
                at = max(at, check["started_at"])
                results = tuple(unknown(c, at, "READ_TIMEOUT") for c in commands)
                state = "unavailable"
            else:
                state = "complete" if all(r.state != "unknown" for r in results) else "unavailable"
            if (
                console is not None
                and state in {"superseded", "unavailable"}
                and (not current or clock_invalid or at - check["started_at"] > READ_WINDOW)
            ):
                from otm.providers.recovery_console import RecoveryConsoleResult

                console = console.model_copy(
                    update={
                        "checked_at": at,
                        "result": RecoveryConsoleResult(
                            state="unknown",
                            mfa_exemption="unknown",
                            network_boundary="unknown",
                            desired_fingerprint=console.result.desired_fingerprint,
                            safe_code="RECOVERY_CONSOLE_UNVERIFIED",
                        ),
                    }
                )
            if (assignments is not None or recovery_assignments is not None) and (
                not current or clock_invalid or at - check["started_at"] > READ_WINDOW
            ):
                from otm.providers.administrator_access import AdministratorResult

                assignments, recovery_assignments = (
                    item.model_copy(
                        update={
                            "checked_at": at,
                            "result": AdministratorResult(group="unknown", domain_role="unknown"),
                        }
                    )
                    if item is not None
                    else None
                    for item in (assignments, recovery_assignments)
                )
            if keys is not None and (
                not current
                or clock_invalid
                or at - check["started_at"] > READ_WINDOW
                or not check["started_at"] <= keys.checked_at <= at
            ):
                keys = keys.model_copy(
                    update={"checked_at": at, "state": "unavailable", "keys": ()}
                )
            episodes, opened = None, ()
            if frozen.intent.notice_policy_version == 1:
                from otm.tenancies.presence_alerts import advance_episodes

                episodes, opened = advance_episodes(
                    connection, row, check, frozen.intent.snapshot, results
                )
            seal(
                connection,
                row,
                check,
                results,
                state,
                at,
                notice_episodes=episodes,
                recovery_console=console,
                administrator_access=assignments,
                recovery_administrator_access=recovery_assignments,
                automation_keys=keys,
            )
            if opened and self.notifications is not None:
                from otm.tenancies.presence_alerts import stage_missing

                stage_missing(
                    self.notifications,
                    connection,
                    row,
                    check,
                    frozen.intent.snapshot,
                    episodes,
                    opened,
                    at,
                )
