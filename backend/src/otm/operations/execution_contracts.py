"""Closed single-step inspection dispatch and durable simulated observation contracts."""

from typing import Literal
from uuid import UUID

from otm.contracts import Contract, Generation, Text
from otm.operations.contracts import ActorIdentity, InspectionIntent
from otm.providers.inspection_contracts import ExecutionContext, InspectionResult


# Validated immutable intent paired with its current operation revision.
class CommittedInspection(Contract):
    operation_id: UUID
    operation_revision: Generation
    intent_event_id: UUID
    intent_revision: Generation
    actor: ActorIdentity
    intent: InspectionIntent


# Current scoped authority, never a credential or substitute for an authorizer.
class DispatchGrant(Contract):
    workspace_id: Text
    actor_key: Text
    policy_revision: UUID
    runtime_policy_revision: UUID
    access_binding_id: UUID
    credential_generation: Generation


# One generation-owned read attempt; older claims cannot publish over this one.
class ClaimedInspection(Contract):
    committed: CommittedInspection
    operation_revision: Generation
    context: ExecutionContext
    grant: DispatchGrant


# Record a claimed attempt and current grant; no provider call is implied yet.
class DispatchEvent(Contract):
    contract_version: Literal["inspection-worker-1"] = "inspection-worker-1"
    provider_mode: Literal["simulated"] = "simulated"
    context: ExecutionContext
    grant: DispatchGrant
    intent_event_id: UUID


# Persist sanitized results or a fixed local guard diagnostic, never raw exceptions.
class InspectionOutcome(Contract):
    contract_version: Literal["inspection-worker-1"] = "inspection-worker-1"
    provider_mode: Literal["simulated"] = "simulated"
    context: ExecutionContext | None
    intent_event_id: UUID
    safe_code: Literal[
        "TENANCY_INSPECTED",
        "ACCESS_UNVERIFIED",
        "ACCESS_DENIED",
        "READ_TIMEOUT",
        "READ_DELAYED",
        "TENANCY_UNOBSERVABLE",
        "UNSUPPORTED_CAPABILITY",
        "DISPATCH_NOT_AUTHORIZED",
        "DISPATCH_CONTEXT_CHANGED",
        "INSPECTION_PROVIDER_REJECTED",
    ]
    result: InspectionResult | None
