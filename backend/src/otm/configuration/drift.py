"""Authenticated reference-only check admission and current read projections."""

import json
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import and_, select

from otm.configuration.drift_context import capture_target, registered_child, same_assignment
from otm.configuration.drift_contracts import ConfigurationCheckIntent
from otm.configuration.drift_records import check_history
from otm.configuration.drift_views import check_summary, drift_directory
from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    administrator,
    audit_event,
    baseline_version,
    operation,
    tenancy,
    tenancy_configuration,
)
from otm.tenancies.contracts import ActionReceipt


# Read original stored JSON/hash before exposing any queued check's target scope.
def check_intent(row):
    if canonical_hash(row["intent_data"]) != row["intent_hash"]:
        raise ValueError("INVALID_CHECK_INTENT_HASH")
    frozen = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
    if (
        not isinstance(frozen.intent, ConfigurationCheckIntent)
        or frozen.intent.workspace_id != row["workspace_id"]
        or frozen.actor.key != row["initiating_actor_subject"]
    ):
        raise ValueError("INVALID_CHECK_INTENT_SCOPE")
    return frozen


# Operation ownership and current intent pointers are joined exactly, never by a browser label.
def check_operation(connection, workspace, identifier=None, pending=False):
    query = select(
        operation,
        audit_event.c.data.label("intent_data"),
        audit_event.c.data_hash.label("intent_hash"),
    ).join(
        audit_event,
        and_(
            audit_event.c.workspace_id == operation.c.workspace_id,
            audit_event.c.operation_id == operation.c.id,
            audit_event.c.id == operation.c.current_intent_event_id,
            audit_event.c.intent_revision == operation.c.current_intent_revision,
            audit_event.c.kind == "operation_intent",
        ),
    )
    query = query.where(
        operation.c.workspace_id == workspace, operation.c.kind == "configuration_check"
    )
    if identifier:
        query = query.where(operation.c.id == identifier)
    if pending:
        query = query.where(operation.c.state.in_(("queued", "running")))
    return connection.execute(query).mappings().all()


# One scoped registry query retrieves baseline labels/override categories without per-row API reads.
def check_rows(connection, workspace, identifier=None):
    query = (
        select(
            tenancy,
            operation.c.state.label("reserved_operation_state"),
            baseline_version.c.version_number.label("assigned_version"),
            tenancy_configuration.c.policy_override_statements,
            tenancy_configuration.c.quota_override_statements,
            tenancy_configuration.c.monthly_budget_override_amount,
        )
        .outerjoin(
            operation,
            and_(
                operation.c.workspace_id == tenancy.c.workspace_id,
                operation.c.id == tenancy.c.operation_id,
            ),
        )
        .outerjoin(
            baseline_version,
            and_(
                baseline_version.c.workspace_id == tenancy.c.workspace_id,
                baseline_version.c.id == tenancy.c.baseline_version_id,
            ),
        )
        .outerjoin(
            tenancy_configuration,
            and_(
                tenancy_configuration.c.workspace_id == tenancy.c.workspace_id,
                tenancy_configuration.c.tenancy_id == tenancy.c.id,
                tenancy_configuration.c.id == tenancy.c.desired_configuration_id,
            ),
        )
    )
    query = query.where(tenancy.c.workspace_id == workspace, tenancy.c.status == "active")
    if identifier:
        query = query.where(tenancy.c.id == identifier)
    rows = [dict(row) for row in connection.execute(query).mappings()]
    for row in rows:
        row["override_categories"] = tuple(
            category
            for category, key in (
                ("policy", "policy_override_statements"),
                ("quota", "quota_override_statements"),
                ("budget", "monthly_budget_override_amount"),
            )
            if row[key] is not None
        )
    return rows


# The existing organization store supplies session/grant locks and one native transaction.
class ConfigurationChecks:
    # Provider/queue availability is explicit; the service cannot invent a fallback cloud context.
    def __init__(self, store, *, policy=None, policy_loader=None, enqueuer=None):
        self.store, self.policy, self.policy_loader, self.enqueuer = (
            store,
            policy,
            policy_loader,
            enqueuer,
        )

    # Reload execution pause and parent authority for every view/admission.
    def available_policy(self):
        if not self.policy or not self.enqueuer:
            return None
        if self.policy_loader:
            current = self.policy_loader()
            if current.execution_paused or current.policy != self.policy:
                return None
        return self.policy

    # Pending reads are progress only; they never alter assigned metadata or count as verification.
    def pending(self, connection, workspace, rows, policy):
        pending = {}
        lookup = {row["id"]: row for row in rows}
        for operation_row in check_operation(connection, workspace, pending=True):
            frozen = check_intent(operation_row)
            for target in frozen.intent.targets:
                if target.tenancy_id in lookup and same_assignment(
                    target, lookup[target.tenancy_id], policy
                ):
                    pending[target.tenancy_id] = operation_row["id"]
        return pending

    # Build both tabs from bounded immutable history, keeping independent last-complete evidence.
    def summaries(self, connection, workspace, identifier=None, *, include_payload=False):
        rows = check_rows(connection, workspace, identifier)
        if identifier and not rows:
            raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
        # An execution pause disables new work, but does not invalidate earlier evidence
        # for the unchanged trusted assignment. A changed parent/policy still invalidates it.
        policy = self.policy
        if self.policy_loader and self.policy_loader().policy != policy:
            policy = None
        available = self.available_policy() is not None
        pending = self.pending(connection, workspace, rows, policy)
        history = check_history(connection, workspace)
        return tuple(
            check_summary(
                row,
                history,
                pending,
                policy,
                SimpleNamespace(version_number=row["assigned_version"])
                if row["assigned_version"]
                else None,
                self.store.clock(),
                include_payload=include_payload,
                read_available=available,
            )
            for row in rows
        )

    # Directory filtering is read-only and never queues a hidden check on page load.
    def directory(self, principal, query):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return drift_directory(self.summaries(connection, workspace), query)

    # Detail returns only the exact authorized child, with payloads verified against sealed
    # evidence.
    def detail(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return self.summaries(connection, workspace, identifier, include_payload=True)[0]

    # Freeze current assigned state and enqueue once atomically; no desired/verified head is
    # updated.
    def start(self, principal, command):
        digest = canonical_hash({"kind": "configuration_check", **command.model_dump(mode="json")})
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            previous = (
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
            if previous:
                if (
                    previous["kind"] != "configuration_check"
                    or previous["request_digest"] != digest
                ):
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                return ActionReceipt(
                    operation_id=previous["id"],
                    state=previous["state"],
                    provider_mode="simulated",
                    accepted_at=previous["accepted_at"],
                )
            policy = self.available_policy()
            if policy is None or policy.workspace_id != workspace:
                raise OrganizationConflict("CONFIGURATION_CONTEXT_UNAVAILABLE")
            rows = check_rows(connection, workspace, command.tenancy_id)
            if command.tenancy_id and not rows:
                raise OrganizationConflict("CONFIGURATION_TARGET_NOT_FOUND")
            selected = [
                row for row in rows if registered_child(row, policy) and not row["operation_id"]
            ]
            pending = self.pending(connection, workspace, selected, policy)
            if command.tenancy_id and (not selected or command.tenancy_id in pending):
                raise OrganizationConflict("CONFIGURATION_CHECK_BUSY")
            selected = [row for row in selected if row["id"] not in pending]
            if not selected:
                raise OrganizationConflict("NO_CONFIGURATION_CHECK_TARGETS")
            targets = tuple(capture_target(connection, workspace, row, policy) for row in selected)
            grant = (
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
            intent = ConfigurationCheckIntent(
                workspace_id=workspace,
                policy_revision=policy.policy_revision,
                organization_id=policy.organization_id,
                parent_tenancy_ocid=policy.parent_tenancy_ocid,
                administrator_id=grant["id"],
                authorization_revision=grant["authorization_revision"],
                targets=targets,
                target=ConfigurationOperationTarget(
                    tenancy_ocid=targets[0].tenancy_ocid if len(targets) == 1 else None,
                    display_name=targets[0].tenancy_name
                    if len(targets) == 1
                    else f"{len(targets)} tenancies",
                ),
            )
            data = IntentEventData(intent=intent, actor=principal.actor).model_dump(mode="json")
            connection.execute(
                operation.insert().values(
                    id=key,
                    workspace_id=workspace,
                    kind="configuration_check",
                    initiating_actor_subject=principal.actor.key,
                    initiating_actor_snapshot=principal.actor.model_dump(mode="json"),
                    responsible_actor_subject=principal.actor.key,
                    client_request_key=command.client_request_key,
                    request_digest=digest,
                    current_intent_revision=1,
                    current_intent_event_id=event,
                    state="queued",
                    stage="Check assigned configuration",
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
                    contract_version="configuration-check-1",
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            self.enqueuer.enqueue(connection, key)
            return ActionReceipt(
                operation_id=key, state="queued", provider_mode="simulated", accepted_at=at
            )
