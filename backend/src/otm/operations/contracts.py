"""Closed inspection-admission inputs and immutable, nonsecret intent/actor snapshots."""

import hashlib
import json
from typing import Literal
from uuid import UUID

from otm.configuration.drift_contracts import ConfigurationCheckIntent
from otm.configuration.rollout_contracts import ConfigurationIntent
from otm.contracts import Contract, Text, UtcInstant
from otm.financial.contracts import CostIntent
from otm.providers.inspection_contracts import InspectionTarget, TenancyOcid
from otm.tenancies.contracts import OrganizationIntent
from otm.tenancies.presence_contracts import PresenceCheckIntent

OperationState = Literal[
    "queued", "running", "waiting", "needs_attention", "succeeded", "cancelled", "failed"
]


# Hash deterministic JSON from closed model data, not raw identity claims.
def canonical_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


# Allowlisted trusted authorization output, never fields accepted from an SPA command.
class ActorIdentity(Contract):
    issuer: Text
    subject: Text
    display_name: Text | None = None

    # Namespace stable subjects by issuer; names do not change request ownership.
    @property
    def key(self) -> str:
        return "actor:" + canonical_hash({"issuer": self.issuer, "subject": self.subject})


# Accept a workspace, request key and target child without admin claims.
class InspectImportRequest(Contract):
    workspace_id: Text
    client_request_key: UUID
    tenancy_ocid: TenancyOcid

    # Fingerprint this bounded command, excluding its separately scoped idempotency key.
    @property
    def digest(self) -> str:
        return canonical_hash(
            {
                "kind": "inspect_import",
                "contract_version": "inspect-import-1",
                **self.model_dump(mode="json", exclude={"client_request_key"}),
            }
        )


# Resolve parent and access binding from trusted server policy.
class InspectionPolicy(Contract):
    # Exact authorized workspace, 1–256 nonblank characters; must match command/dispatch scope.
    workspace_id: Text
    # Trusted policy-version UUID frozen into intent and rechecked against current authority.
    policy_revision: UUID
    # Expected provider organization, 1–256 nonblank characters; paired with parent/child facts.
    organization_id: Text
    # Expected parent tenancy OCID, 15–256 characters; syntax alone does not prove parentage.
    parent_tenancy_ocid: TenancyOcid
    # Selected binding UUID frozen into intent; current credential generation resolves separately.
    access_binding_id: UUID


# Frozen resolved intent; later attempts resolve current credentials on this exact binding.
class InspectionIntent(Contract):
    contract_version: Literal["inspect-import-1"]
    kind: Literal["inspect_import"]
    workspace_id: Text
    policy_revision: UUID
    access_binding_id: UUID
    target: InspectionTarget


# Freeze nonsecret intent and allowlisted actor evidence.
class IntentEventData(Contract):
    intent: (
        InspectionIntent
        | OrganizationIntent
        | ConfigurationIntent
        | ConfigurationCheckIntent
        | CostIntent
        | PresenceCheckIntent
    )
    actor: ActorIdentity


# Return committed identity/state; queued does not mean inspection completed.
class Acceptance(Contract):
    operation_id: UUID
    state: OperationState
    accepted_at: UtcInstant
