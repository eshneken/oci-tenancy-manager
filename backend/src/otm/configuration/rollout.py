"""Baseline/override preview, admission and progress on existing durable operation records."""

import json
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from otm.configuration.override_contracts import (
    OverrideEditor,
    OverridePreviewRequest,
    OverrideValues,
)
from otm.configuration.revisions import (
    accept_configuration,
    configuration_is_verified,
    load_configuration,
    override_conflict,
)
from otm.configuration.rollout_contracts import (
    ConfigurationBlocker,
    ConfigurationIntent,
    ConfigurationOperationTarget,
    ConfigurationOutcome,
    ConfigurationPreview,
    ConfigurationProgress,
    ConfigurationRetryEvidence,
    ConfigurationTarget,
    ConfigurationTargetProgress,
    ConfigurationUpdate,
)
from otm.configuration.service import current_baseline, published_baseline
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    operation_step,
    org_workspace,
    tenancy,
)
from otm.tenancies.contracts import ActionReceipt


# Determine the complete baseline-only candidate set without hiding busy or invalid child targets.
def plan_rows(rows, baseline, policy, scope):
    candidates, blockers = [], []
    pending = sum(r["status"] == "pending" for r in rows)
    for row in sorted(rows, key=lambda r: str(r["id"])):
        if row["status"] != "active" or not baseline:
            continue
        if configuration_is_verified(row, baseline) and not row.get("override_edit"):
            continue
        candidate = ConfigurationTarget(
            tenancy_id=row["id"],
            name=row["name"],
            tenancy_ocid=row["tenancy_ocid"],
            parent_tenancy_ocid=row["parent_tenancy_ocid"],
            organization_id=row["organization_id"],
            revision=row["revision"],
            source_baseline_id=row["baseline_version_id"],
            source_verified_id=row.get("verified_baseline_version_id"),
            source_configuration_id=row.get("desired_configuration_id"),
            source_verified_configuration_id=row.get("last_verified_configuration_id"),
            overrides=row.get("planned_overrides", OverrideValues()),
        )
        candidates.append(candidate)
        code = (
            "PROVIDER_UNAVAILABLE"
            if policy is None
            else (
                "REGISTERED_CHILD_REQUIRED"
                if row["provider_mode"] != "simulated"
                or row["parent_tenancy_ocid"] != policy.parent_tenancy_ocid
                or row["organization_id"] != policy.organization_id
                or row["tenancy_ocid"] == policy.parent_tenancy_ocid
                or not row["tenancy_ocid"].startswith("ocid1.tenancy.oc1..otmsim")
                else "TENANCY_BUSY"
                if row["operation_id"]
                else None
            )
        )
        if code is None and row.get("override_conflict"):
            code = "OVERRIDE_REVIEW_REQUIRED"
        if code:
            blockers.append(
                ConfigurationBlocker(
                    tenancy_id=row["id"],
                    name=row["name"],
                    code=code,
                    operation_id=row["operation_id"],
                )
            )
    return tuple(candidates), tuple(blockers), pending


# Intent reads validate original JSON hashes before parsing optional future-compatible projections.
def update_intent(row):
    if canonical_hash(row["intent_data"]) != row["intent_hash"]:
        raise ValueError("INVALID_CONFIGURATION_EVIDENCE")
    frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
    if (
        not isinstance(frozen.intent, ConfigurationIntent)
        or frozen.intent.workspace_id != row["workspace_id"]
        or frozen.actor.key != row["initiating_actor_subject"]
    ):
        raise ValueError("INVALID_CONFIGURATION_SCOPE")
    return frozen


# Exact persisted intent ownership is shared by read, retry and worker execution.
def operation_row(connection, workspace, identifier):
    return (
        connection.execute(
            select(
                operation,
                audit_event.c.data.label("intent_data"),
                audit_event.c.data_hash.label("intent_hash"),
            )
            .join(
                audit_event,
                (audit_event.c.workspace_id == operation.c.workspace_id)
                & (audit_event.c.id == operation.c.current_intent_event_id)
                & (audit_event.c.operation_id == operation.c.id)
                & (audit_event.c.intent_revision == operation.c.current_intent_revision)
                & (audit_event.c.kind == "operation_intent"),
            )
            .where(
                operation.c.workspace_id == workspace,
                operation.c.id == identifier,
                operation.c.kind == "configuration_update",
            )
        )
        .mappings()
        .one_or_none()
    )


# Persist one safe event and one reusable target step, keeping earlier attempts in immutable audit.
def save_target_result(connection, row, target, baseline, at, *, code, category=None):
    outcome = ConfigurationOutcome(
        tenancy_id=target.tenancy_id,
        baseline_id=baseline.id,
        configuration_id=target.configuration.id if target.configuration else None,
        safe_code=code,
        category=category,
        verified_at=at if code == "CONFIGURATION_VERIFIED" else None,
    )
    payload = outcome.model_dump(mode="json")
    event = uuid4()
    connection.execute(
        audit_event.insert().values(
            id=event,
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            actor="otm-worker:configuration",
            actor_subject="otm-worker:configuration",
            actor_snapshot={"kind": "worker", "subject": "configuration"},
            kind="configuration_outcome",
            at=at,
            contract_version="configuration-update-1",
            data=payload,
            data_hash=canonical_hash(payload),
        )
    )
    statement = insert(operation_step).values(
        workspace_id=row["workspace_id"],
        operation_id=row["id"],
        intent_revision=1,
        step_key="configuration:" + str(target.tenancy_id),
        intent_event_id=row["current_intent_event_id"],
        command_kind="configuration_update",
        contract_version="configuration-update-1",
        inputs={},
        state="verified" if outcome.verified_at else "needs_attention",
        execution_generation=1,
        attempt_number=1,
        current_attempt_id=uuid4(),
        effect_knowledge="known",
        last_outcome=payload,
        verified_at=outcome.verified_at,
        evidence_event_id=event,
    )
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=[
                operation_step.c.workspace_id,
                operation_step.c.operation_id,
                operation_step.c.intent_revision,
                operation_step.c.step_key,
            ],
            set_={
                "state": statement.excluded.state,
                "last_outcome": payload,
                "verified_at": outcome.verified_at,
                "evidence_event_id": event,
                "attempt_number": operation_step.c.attempt_number + 1,
                "current_attempt_id": statement.excluded.current_attempt_id,
            },
        )
    )


# Preview/accept/retry use the same live administrator and workspace transaction guards as
# onboarding.
class ConfigurationRollouts:
    # Explicit host composition supplies the guard for versioned signing credentials.
    signing_guard = None

    # An absent provider/queue is explicitly unavailable; no hidden simulation fallback exists.
    def __init__(
        self, store, *, policy=None, policy_loader=None, enqueuer=None, repair_facade=None
    ):
        self.repair_facade = repair_facade
        self.store, self.policy, self.policy_loader, self.enqueuer = (
            store,
            policy,
            policy_loader,
            enqueuer,
        )

    # Reload trusted pause/parent policy; the browser cannot grant itself provider authority.
    def available_policy(self):
        if not self.policy or not self.enqueuer:
            return None
        if self.policy_loader:
            current = self.policy_loader()
            if current.execution_paused or current.policy != self.policy:
                return None
        return self.policy

    # Bind the assigned/latest publication, complete candidates and registry state into one preview
    # fingerprint.
    def _preview(
        self, connection, workspace, identifier, override_request=None, repair_categories=()
    ):
        if repair_categories:
            from otm.configuration.repairs import preview_repair

            return preview_repair(self, connection, workspace, identifier, repair_categories)
        header = (
            connection.execute(select(org_workspace).where(org_workspace.c.id == workspace))
            .mappings()
            .one_or_none()
        )
        if header is None:
            raise OrganizationConflict("ORGANIZATION_NOT_CONFIGURED")
        query = select(tenancy).where(tenancy.c.workspace_id == workspace)
        if identifier:
            query = query.where(tenancy.c.id == identifier)
        rows = [dict(row) for row in connection.execute(query).mappings().all()]
        if identifier and not rows:
            raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
        baseline = current_baseline(connection, workspace)
        if override_request:
            if (
                len(rows) != 1
                or rows[0]["status"] != "active"
                or not rows[0]["baseline_version_id"]
            ):
                raise OrganizationConflict("CONFIGURATION_UPDATE_BLOCKED")
            context = override_request.context
            if (
                rows[0]["revision"],
                rows[0]["baseline_version_id"],
                rows[0].get("desired_configuration_id"),
            ) != (context.tenancy_revision, context.baseline_version_id, context.configuration_id):
                raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
            baseline = published_baseline(connection, workspace, rows[0]["baseline_version_id"])
        conflicts = []
        for row in rows:
            current = load_configuration(
                connection, workspace, row["id"], row.get("desired_configuration_id")
            )
            values = (
                OverrideValues.model_validate(
                    current.model_dump(include=set(OverrideValues.model_fields))
                )
                if current
                else OverrideValues()
            )
            if current and current.baseline_version_id != row["baseline_version_id"]:
                raise OrganizationConflict("CONFIGURATION_CONTEXT_UNAVAILABLE")
            row["planned_overrides"] = override_request.values if override_request else values
            row["override_edit"] = override_request is not None
            if baseline and not override_request and row["status"] == "active":
                conflict = override_conflict(connection, workspace, row, baseline, values)
                if conflict:
                    conflicts.append(conflict)
                    row["override_conflict"] = True
        policy = self.available_policy()
        if policy and policy.workspace_id != workspace:
            policy = None
        targets, blockers, pending = plan_rows(rows, baseline, policy, identifier)
        payload = {
            "workspace": workspace,
            "scope": str(identifier) if identifier else "all",
            "registry_revision": header["registry_revision"],
            "baseline": baseline.model_dump(mode="json") if baseline else None,
            "targets": [t.model_dump(mode="json") for t in targets],
            "blockers": [b.model_dump(mode="json") for b in blockers],
            **(
                {"override_edit": override_request.model_dump(mode="json")}
                if override_request
                else {}
            ),
        }
        return ConfigurationPreview(
            conflicts=tuple(conflicts),
            baseline=baseline,
            tenancy_id=identifier,
            ready_count=len(targets) - len(blockers),
            pending_count=pending,
            blockers=blockers,
            preview_hash=canonical_hash(payload),
        ), targets

    # A preview is a coherent read-only snapshot, never a persisted draft plan or provider mutation.
    def preview(self, principal, identifier=None):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return self._preview(connection, workspace, identifier)[0]

    # Fresh complete evidence and exact bindings gate one explicit selected-object repair preview.
    def preview_repair(self, principal, command):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return self._preview(
                connection, workspace, command.tenancy_id, repair_categories=command.categories
            )[0]

    # A scoped editor reads the assigned publication and immutable current overrides, never latest.
    def override_editor(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            row = (
                connection.execute(
                    select(tenancy).where(
                        tenancy.c.workspace_id == workspace, tenancy.c.id == identifier
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
            if not row["baseline_version_id"]:
                raise OrganizationConflict("CONFIGURATION_CONTEXT_UNAVAILABLE")
            baseline = published_baseline(connection, workspace, row["baseline_version_id"])
            current = load_configuration(
                connection, workspace, identifier, row.get("desired_configuration_id")
            )
            values = (
                OverrideValues.model_validate(
                    current.model_dump(include=set(OverrideValues.model_fields))
                )
                if current
                else OverrideValues()
            )
            policy = self.available_policy()
            if policy and policy.workspace_id != workspace:
                policy = None
            blocked = plan_rows([{**row, "override_edit": True}], baseline, policy, identifier)[1]
            if current and current.baseline_version_id != baseline.id:
                raise OrganizationConflict("CONFIGURATION_CONTEXT_UNAVAILABLE")
            return OverrideEditor(
                tenancy_id=identifier,
                tenancy_name=row["name"],
                tenancy_revision=row["revision"],
                baseline=baseline,
                configuration=current,
                values=values,
                can_edit=row["status"] == "active" and not blocked,
            )

    # Read-only preview fingerprints exact submitted values together with assigned-version context.
    def preview_override(self, principal, command):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return self._preview(connection, workspace, command.tenancy_id, command)[0]

    # Complete admission is atomic: all desired pins/reservations, immutable intent and
    # jobs commit together.
    def start(self, principal, command):
        command = ConfigurationUpdate.model_validate(command)
        payload = command.model_dump(mode="json")
        digest = canonical_hash(
            {
                key: value
                for key, value in payload.items()
                if key in {"client_request_key", "tenancy_id", "preview_hash"}
                or (key == "repair_categories" and bool(value))
                or (key == "plan_id" and value is not None)
                or (
                    key in {"overrides", "override_mode", "override_context"}
                    and command.override_mode
                )
            }
        )
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            old = (
                connection.execute(
                    select(operation).where(
                        operation.c.workspace_id == workspace,
                        operation.c.initiating_actor_subject == principal.actor.key,
                        operation.c.client_request_key == command.client_request_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if old:
                if old["request_digest"] != digest or old["kind"] != "configuration_update":
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                return ActionReceipt(
                    operation_id=old["id"],
                    state=old["state"],
                    provider_mode="simulated",
                    accepted_at=old["accepted_at"],
                )
            if command.plan_id:
                from otm.configuration.plans import accepted_plan

                preview, targets = accepted_plan(
                    self, connection, workspace, principal, command.plan_id
                )
            else:
                override_request = (
                    OverridePreviewRequest(
                        tenancy_id=command.tenancy_id,
                        values=command.overrides,
                        context=command.override_context,
                    )
                    if command.override_mode
                    else None
                )
                preview, targets = self._preview(
                    connection,
                    workspace,
                    command.tenancy_id,
                    override_request,
                    command.repair_categories,
                )
            if preview.tenancy_id != command.tenancy_id:
                raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
            if preview.preview_hash != command.preview_hash:
                raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
            policy = self.available_policy()
            if not preview.baseline or preview.blockers or not targets or policy is None:
                raise OrganizationConflict("CONFIGURATION_UPDATE_BLOCKED")
            admin = (
                connection.execute(
                    select(administrator).where(
                        administrator.c.workspace_id == workspace,
                        administrator.c.issuer == principal.session.issuer,
                        administrator.c.subject == principal.session.subject,
                    )
                )
                .mappings()
                .one()
            )
            key, event = uuid4(), uuid4()
            accepted = []
            for target in targets:
                if self.signing_guard is not None:
                    self.signing_guard(connection, workspace, target.tenancy_id, at)
                registered = {
                    "id": target.tenancy_id,
                    "desired_configuration_id": target.source_configuration_id,
                }
                revision = (
                    load_configuration(
                        connection, workspace, target.tenancy_id, target.source_configuration_id
                    )
                    if command.repair_categories
                    else accept_configuration(
                        connection,
                        workspace,
                        registered,
                        preview.baseline,
                        target.overrides,
                        key,
                        principal.actor.key,
                        at,
                    )
                )
                accepted.append(target.model_copy(update={"configuration": revision}))
            # Deferred scoped operation FK allows the whole accepted revision/intent
            # graph to commit together.
            targets = tuple(accepted)
            intent = ConfigurationIntent(
                change_kind="repair"
                if command.repair_categories
                else "override_change"
                if command.override_mode
                else "baseline_update",
                workspace_id=workspace,
                policy_revision=policy.policy_revision,
                organization_id=policy.organization_id,
                parent_tenancy_ocid=policy.parent_tenancy_ocid,
                administrator_id=admin["id"],
                authorization_revision=admin["authorization_revision"],
                baseline=preview.baseline,
                targets=targets,
                target=ConfigurationOperationTarget(
                    tenancy_ocid=targets[0].tenancy_ocid if len(targets) == 1 else None,
                    display_name=targets[0].name
                    if len(targets) == 1
                    else f"{len(targets)} tenancies",
                ),
            )
            payload = IntentEventData(intent=intent, actor=principal.actor).model_dump(mode="json")
            connection.execute(
                operation.insert().values(
                    id=key,
                    workspace_id=workspace,
                    kind="configuration_update",
                    initiating_actor_subject=principal.actor.key,
                    initiating_actor_snapshot=principal.actor.model_dump(mode="json"),
                    responsible_actor_subject=principal.actor.key,
                    client_request_key=command.client_request_key,
                    request_digest=digest,
                    current_intent_revision=1,
                    current_intent_event_id=event,
                    state="queued",
                    stage="Repair assigned configuration"
                    if command.repair_categories
                    else f"Update baseline v{preview.baseline.version_number}",
                    effect_knowledge="none",
                    revision=1,
                    accepted_at=at,
                    created_at=at,
                    updated_at=at,
                )
            )
            connection.execute(
                audit_event.insert().values(
                    id=event,
                    workspace_id=workspace,
                    operation_id=key,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="operation_intent",
                    intent_revision=1,
                    at=at,
                    contract_version="configuration-update-1",
                    data=payload,
                    data_hash=canonical_hash(payload),
                )
            )
            for target in targets:
                changed = connection.execute(
                    update(tenancy)
                    .where(
                        tenancy.c.workspace_id == workspace,
                        tenancy.c.id == target.tenancy_id,
                        tenancy.c.revision == target.revision,
                        tenancy.c.operation_id.is_(None),
                    )
                    .values(
                        desired_configuration_id=target.configuration.id
                        if target.configuration
                        else None,
                        baseline_version_id=preview.baseline.id,
                        operation_id=key,
                        last_operation_id=key,
                        revision=target.revision
                        if command.repair_categories
                        else target.revision + 1,
                        updated_at=at,
                    )
                )
                if changed.rowcount != 1:
                    raise OrganizationConflict("CONFIGURATION_PREVIEW_CHANGED")
            connection.execute(
                update(org_workspace)
                .where(org_workspace.c.id == workspace)
                .values(registry_revision=org_workspace.c.registry_revision + 1)
            )
            if command.plan_id:
                from otm.configuration.plans import finish_plan

                finish_plan(connection, workspace, command.plan_id, key, targets, at)
            self.enqueuer.enqueue(connection, key)
            return ActionReceipt(
                operation_id=key, state="queued", provider_mode="simulated", accepted_at=at
            )

    # Public progress projects bounded closed target outcomes rather than raw intent/provider JSON.
    def progress(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            row = operation_row(connection, workspace, identifier)
            if row is None:
                raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
            intent = update_intent(row).intent
            steps = {
                s["step_key"]: s
                for s in connection.execute(
                    select(operation_step).where(
                        operation_step.c.workspace_id == workspace,
                        operation_step.c.operation_id == identifier,
                        operation_step.c.intent_revision == 1,
                    )
                )
                .mappings()
                .all()
            }
            targets = []
            for target in intent.targets:
                step = steps.get("configuration:" + str(target.tenancy_id))
                outcome = (
                    ConfigurationOutcome.model_validate_json(json.dumps(step["last_outcome"]))
                    if step
                    else None
                )
                targets.append(
                    ConfigurationTargetProgress(
                        tenancy_id=target.tenancy_id,
                        name=target.name,
                        state=step["state"] if step else "pending",
                        safe_code=outcome.safe_code if outcome else None,
                        verified_at=outcome.verified_at if outcome else None,
                    )
                )
            return ConfigurationProgress(
                change_kind=intent.change_kind,
                operation_id=identifier,
                state=row["state"],
                baseline=intent.baseline,
                targets=tuple(targets),
                can_retry=row["state"] == "needs_attention"
                and self._retryable(connection, row, intent, principal, steps),
            )

    # Badge only supported retries owned by this administrator; historical failures are not tasks.
    def actionable_count(self, principal):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            identifiers = (
                connection.execute(
                    select(operation.c.id).where(
                        operation.c.workspace_id == workspace,
                        operation.c.kind == "configuration_update",
                        operation.c.state == "needs_attention",
                        operation.c.responsible_actor_subject == principal.actor.key,
                    )
                )
                .scalars()
                .all()
            )
            count = 0
            for identifier in identifiers:
                row = operation_row(connection, workspace, identifier)
                if row and self._retryable(connection, row, update_intent(row).intent, principal):
                    count += 1
            return count

    # Retry only this unchanged accepted batch; verified children are never re-applied.
    def retry(self, principal, identifier):
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            row = operation_row(connection, workspace, identifier)
            if row is None:
                raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
            intent = update_intent(row).intent
            if row["responsible_actor_subject"] != principal.actor.key:
                raise OrganizationConflict("CONFIGURATION_UPDATE_BLOCKED")
            if row["state"] in {"queued", "running", "succeeded"}:
                return ActionReceipt(
                    operation_id=identifier,
                    state=row["state"],
                    provider_mode="simulated",
                    accepted_at=row["accepted_at"],
                )
            if row["state"] != "needs_attention" or not self._retryable(
                connection, row, intent, principal
            ):
                raise OrganizationConflict("CONFIGURATION_UPDATE_BLOCKED")
            connection.execute(
                update(operation)
                .where(operation.c.id == identifier, operation.c.workspace_id == workspace)
                .values(
                    state="queued",
                    stage="Retrying incomplete configuration targets",
                    updated_at=at,
                    completed_at=None,
                    revision=operation.c.revision + 1,
                )
            )
            payload = ConfigurationRetryEvidence(baseline_id=intent.baseline.id).model_dump(
                mode="json"
            )
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    operation_id=identifier,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="configuration_retry",
                    at=at,
                    contract_version="configuration-update-1",
                    data=payload,
                    data_hash=canonical_hash(payload),
                )
            )
            self.enqueuer.enqueue(connection, identifier)
            return ActionReceipt(
                operation_id=identifier, state="queued", provider_mode="simulated", accepted_at=at
            )

    # Retryability reflects current authority and supported repair, not a raw needs-attention state.
    def _retryable(self, connection, row, intent, principal, steps=None):
        policy = self.available_policy()
        if (
            row["responsible_actor_subject"] != principal.actor.key
            or policy is None
            or policy.workspace_id != intent.workspace_id
            or (policy.policy_revision, policy.organization_id, policy.parent_tenancy_ocid)
            != (intent.policy_revision, intent.organization_id, intent.parent_tenancy_ocid)
        ):
            return False
        grant = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == intent.workspace_id,
                    administrator.c.id == intent.administrator_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            not grant
            or grant["status"] != "active"
            or grant["authorization_revision"] != intent.authorization_revision
        ):
            return False
        if steps is None:
            steps = {
                s["step_key"]: s
                for s in connection.execute(
                    select(operation_step).where(
                        operation_step.c.workspace_id == intent.workspace_id,
                        operation_step.c.operation_id == row["id"],
                        operation_step.c.intent_revision == 1,
                    )
                )
                .mappings()
                .all()
            }
        return not any(
            s["last_outcome"]
            and ConfigurationOutcome.model_validate_json(json.dumps(s["last_outcome"])).safe_code
            in {"AUTHORIZATION_CHANGED", "TARGET_CHANGED", "LIFECYCLE_UNAVAILABLE"}
            for s in steps.values()
        )
