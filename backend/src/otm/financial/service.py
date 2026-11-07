"""Authorize cost refresh, join compatible work and atomically record each command."""

import json
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select

from otm.configuration.drift_context import capture_target
from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.financial.context import failure_source, source_context, target_source
from otm.financial.contracts import (
    CostIntent,
    CostPolicy,
    CostRefreshReceipt,
    CostTarget,
    CostView,
)
from otm.financial.normalization import month_bounds, project
from otm.financial.records import current_records, decode_collection
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import administrator, audit_event, financial_collection, operation, tenancy


# Financial context errors expose fixed codes only, not SDK/SQL text or private source
# configuration.
class CostConflict(OrganizationConflict):
    pass


# Database projections and read admission share current source keys but never perform provider GETs.
class CostCollections:
    # All authority comes from existing session/store/policy dependencies, never a client workspace.
    def __init__(self, store, *, policy, policy_loader, enqueuer, profile=None):
        self.store, self.policy, self.policy_loader, self.enqueuer = (
            store,
            policy,
            policy_loader,
            enqueuer,
        )
        self.profile = profile or CostPolicy()

    # A changed or paused deployment disables new reads without pretending old observations are
    # fresh.
    def available(self):
        if not self.policy or not self.enqueuer:
            return False
        current = self.policy_loader() if self.policy_loader else None
        return current is None or (not current.execution_paused and current.policy == self.policy)

    # Two bounded financial queries supplement the registry before global monetary sorting/paging.
    def summaries(self, connection, workspace, rows):
        sources = {}
        policy = self.policy
        if self.policy_loader and self.policy_loader().policy != policy:
            policy = None
        available = self.available()
        for row in rows:
            context = source_context(row, policy, self.profile)
            if context is not None:
                sources[row["id"]] = context
        observations, heads = current_records(connection, workspace, sources)
        now = self.store.clock()
        views = {}
        for row in rows:
            key = row["id"]
            head = heads.get(key)
            record = observations.get(key)
            pending = bool(head and head["state"] in {"queued", "reading", "retry"})
            failure = (
                head["safe_code"]
                if head
                and (
                    head["state"] in {"failed", "superseded"}
                    or head["safe_code"] == "COST_READ_UNAVAILABLE"
                )
                else None
            )
            if head and head.get("continuing_outcome") in {
                "COST_READ_UNAVAILABLE",
                "COST_RETRIES_EXHAUSTED",
                "COST_SOURCE_UNQUALIFIED",
            }:
                failure = head["continuing_outcome"]
            if head and head["safe_code"] == "COST_SOURCE_UNQUALIFIED":
                failure = "COST_SOURCE_UNQUALIFIED"
            desired = row.get("monthly_budget_override_amount")
            views[key] = (
                project(
                    record[1] if record else None,
                    self.profile,
                    now,
                    pending=pending,
                    failure=failure,
                    operation_id=head["operation_id"] if head else None,
                    can_refresh=key in sources and available and not row["operation_id"],
                    desired_budget=f"{Decimal(desired):.4f}" if desired is not None else None,
                )
                if key in sources
                else CostView()
            )
        return views

    # Workspace lock serializes duplicate commands; one active compatible source is joined.
    def start(self, principal, command):
        digest = canonical_hash(command.model_dump(mode="json"))
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            receipt_id = uuid5(
                NAMESPACE_URL,
                canonical_hash(
                    {
                        "workspace": workspace,
                        "actor": principal.actor.key,
                        "request": str(command.client_request_key),
                        "kind": "cost_refresh",
                    }
                ),
            )
            previous = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.workspace_id == workspace,
                        audit_event.c.id == receipt_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if previous:
                data = previous["data"]
                if canonical_hash(data) != previous["data_hash"]:
                    raise ValueError("INVALID_COST_RECEIPT")
                if data["request_hash"] != digest:
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                return CostRefreshReceipt.model_validate_json(json.dumps(data["receipt"]))
            collision = connection.scalar(
                select(operation.c.id).where(
                    operation.c.workspace_id == workspace,
                    operation.c.initiating_actor_subject == principal.actor.key,
                    operation.c.client_request_key == command.client_request_key,
                )
            )
            if collision:
                raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
            if not self.available() or self.policy.workspace_id != workspace:
                raise CostConflict("COST_CONTEXT_UNAVAILABLE")
            query = select(tenancy).where(
                tenancy.c.workspace_id == workspace, tenancy.c.status == "active"
            )
            if command.tenancy_id:
                query = query.where(tenancy.c.id == command.tenancy_id)
            rows = connection.execute(query.order_by(tenancy.c.id)).mappings().all()
            if command.tenancy_id and not rows:
                raise CostConflict("COST_TARGET_NOT_FOUND")
            targets, joined, skipped = [], set(), 0
            start, end = month_bounds(at)
            for row in rows:
                context = source_context(row, self.policy, self.profile)
                if context is None or row["operation_id"]:
                    skipped += 1
                    continue
                target = CostTarget(
                    configuration=capture_target(connection, workspace, row, self.policy),
                    budget_ocid=context["budget_ocid"],
                    source_access_binding_id=self.policy.access_binding_id,
                    profile=self.profile,
                    period_start=start,
                    period_end=end,
                )
                hashed = canonical_hash(target.model_dump(mode="json"))
                active = (
                    connection.execute(
                        select(financial_collection).where(
                            financial_collection.c.workspace_id == workspace,
                            financial_collection.c.tenancy_id == row["id"],
                            financial_collection.c.context_hash == hashed,
                            financial_collection.c.state.in_(("queued", "reading", "retry")),
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if active:
                    decode_collection(active)
                    joined.add(active["operation_id"])
                else:
                    targets.append(target)
            if not targets and not joined:
                raise CostConflict("NO_COST_REFRESH_TARGETS")
            operation_id = None
            if targets:
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
                intent = CostIntent(
                    workspace_id=workspace,
                    administrator_id=grant["id"],
                    authorization_revision=grant["authorization_revision"],
                    targets=tuple(targets),
                    target=ConfigurationOperationTarget(
                        tenancy_ocid=targets[0].configuration.tenancy_ocid
                        if len(targets) == 1
                        else None,
                        display_name=targets[0].configuration.tenancy_name
                        if len(targets) == 1
                        else f"{len(targets)} tenancies",
                    ),
                )
                operation_id, event = uuid4(), uuid4()
                frozen = IntentEventData(intent=intent, actor=principal.actor).model_dump(
                    mode="json"
                )
                connection.execute(
                    operation.insert().values(
                        id=operation_id,
                        workspace_id=workspace,
                        kind="cost_collection",
                        initiating_actor_subject=principal.actor.key,
                        initiating_actor_snapshot=principal.actor.model_dump(mode="json"),
                        responsible_actor_subject=principal.actor.key,
                        client_request_key=command.client_request_key,
                        request_digest=digest,
                        current_intent_revision=1,
                        current_intent_event_id=event,
                        state="queued",
                        stage="Read current month costs",
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
                        operation_id=operation_id,
                        actor=principal.actor.key,
                        actor_subject=principal.actor.key,
                        actor_snapshot=principal.actor.model_dump(mode="json"),
                        kind="operation_intent",
                        intent_revision=1,
                        at=at,
                        contract_version="cost-collection-1",
                        data=frozen,
                        data_hash=canonical_hash(frozen),
                    )
                )
                for target in targets:
                    data = target.model_dump(mode="json")
                    connection.execute(
                        financial_collection.insert().values(
                            id=uuid4(),
                            workspace_id=workspace,
                            tenancy_id=target.configuration.tenancy_id,
                            operation_id=operation_id,
                            context=data,
                            context_hash=canonical_hash(data),
                            source_hash=target_source(target),
                            failure_scope_hash=failure_source(target),
                            state="queued",
                            attempts=0,
                            created_at=at,
                            updated_at=at,
                        )
                    )
                self.enqueuer.enqueue(connection, operation_id)
            for joined_id in sorted(joined, key=str):
                self.enqueuer.enqueue(connection, joined_id)
            receipt = CostRefreshReceipt(
                operation_ids=tuple(
                    ([operation_id] if operation_id else []) + sorted(joined, key=str)
                ),
                accepted_count=len(targets),
                joined_count=len(rows) - skipped - len(targets),
                skipped_count=skipped,
                accepted_at=at,
            )
            data = {
                "request_key": str(command.client_request_key),
                "request_hash": digest,
                "receipt": receipt.model_dump(mode="json"),
            }
            connection.execute(
                audit_event.insert().values(
                    id=receipt_id,
                    workspace_id=workspace,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="cost_refresh_requested",
                    at=at,
                    contract_version="cost-refresh-1",
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            return receipt
