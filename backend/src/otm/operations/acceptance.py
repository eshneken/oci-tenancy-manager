"""Authorize internal inspection admission and freeze trusted policy before atomic persistence."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from otm.operations.contracts import (
    Acceptance,
    ActorIdentity,
    InspectImportRequest,
    InspectionIntent,
    InspectionPolicy,
)
from otm.providers.inspection_contracts import InspectionTarget


# Resolve current admin entitlement from a server principal, never command-provided claims.
class Authorizer(Protocol):
    # Deny unauthorized callers and return only verified, allowlisted actor identity.
    def require_admin(self, principal: object, workspace_id: str) -> ActorIdentity: ...


# Keep idempotent lookup and atomic persistence behind a database adapter contract.
class AdmissionStore(Protocol):
    # Return only this actor/workspace/key's compatible accepted intent, or raise conflict.
    def find(self, request: InspectImportRequest, actor: ActorIdentity) -> Acceptance | None: ...

    # Commit operation, immutable intent and queue reference together, or fail.
    def insert(
        self,
        request: InspectImportRequest,
        actor: ActorIdentity,
        intent: InspectionIntent,
        at: datetime,
    ) -> Acceptance: ...


# Require authorization without a permissive default or public route.
class AcceptInspection:
    # Inject real boundaries; tests supply fakes outside the production package.
    def __init__(
        self,
        store: AdmissionStore,
        authorizer: Authorizer,
        resolve_policy: Callable[[str], InspectionPolicy],
        clock: Callable[[], datetime],
    ):
        self.store, self.authorizer, self.resolve_policy, self.clock = (
            store,
            authorizer,
            resolve_policy,
            clock,
        )

    # Authorize replay first, then freeze policy outside the short database transaction.
    def accept(self, request: InspectImportRequest, principal: object) -> Acceptance:
        request = InspectImportRequest.model_validate(request)
        actor = ActorIdentity.model_validate(
            self.authorizer.require_admin(principal, request.workspace_id)
        )
        existing = self.store.find(request, actor)
        if existing:
            return existing
        # A committed replay precedes fresh policy resolution so configuration changes cannot
        # transform the original accepted intent. Actor entitlement is always checked first.
        policy = InspectionPolicy.model_validate(self.resolve_policy(request.workspace_id))
        if policy.workspace_id != request.workspace_id:
            raise ValueError("POLICY_SCOPE_MISMATCH")
        if policy.parent_tenancy_ocid == request.tenancy_ocid:
            raise ValueError("PARENT_IS_NOT_AN_INSPECTION_CHILD")
        intent = InspectionIntent(
            contract_version="inspect-import-1",
            kind="inspect_import",
            workspace_id=request.workspace_id,
            policy_revision=policy.policy_revision,
            access_binding_id=policy.access_binding_id,
            target=InspectionTarget(
                organization_id=policy.organization_id,
                parent_tenancy_ocid=policy.parent_tenancy_ocid,
                tenancy_ocid=request.tenancy_ocid,
            ),
        )
        return self.store.insert(request, actor, intent, self.clock())
