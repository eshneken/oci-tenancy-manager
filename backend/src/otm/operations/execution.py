"""Execute one simulated read with current authority before dispatch and publication."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from otm.operations.execution_contracts import (
    ClaimedInspection,
    CommittedInspection,
    DispatchGrant,
    InspectionOutcome,
)
from otm.providers.inspection import ProviderContractError, TenancyInspection
from otm.providers.inspection_contracts import InspectTenancy


# Resolve current entitlement, execution fence and scoped access; no permissive defaults.
class DispatchAuthority(Protocol):
    # Deny revoked actors, paused execution or invalid bindings; return current generations.
    def require_inspection(self, committed: CommittedInspection) -> DispatchGrant: ...


# Own short claim/publication transactions, never a transaction around a provider read.
class ExecutionStore(Protocol):
    # Validate current immutable intent; return none when work is absent or not runnable.
    def load(self, operation_id: UUID) -> CommittedInspection | None: ...

    # Commit one generation-owned step and dispatch audit or lose the revision race.
    def claim(
        self, committed: CommittedInspection, grant: DispatchGrant, at: datetime
    ) -> ClaimedInspection | None: ...

    # Publish outcome/audit/state atomically only for the still-current revision and claim.
    def finish(
        self,
        committed: CommittedInspection,
        attempt: ClaimedInspection | None,
        outcome: InspectionOutcome,
        at: datetime,
    ) -> bool: ...


# Revalidate trusted output and prohibit silent policy, actor or binding retargeting.
def current_grant(authority: DispatchAuthority, committed: CommittedInspection) -> DispatchGrant:
    grant = DispatchGrant.model_validate(authority.require_inspection(committed))
    intent = committed.intent
    if (
        grant.workspace_id != intent.workspace_id
        or grant.actor_key != committed.actor.key
        or grant.policy_revision != intent.policy_revision
        or grant.access_binding_id != intent.access_binding_id
    ):
        raise PermissionError("DISPATCH_CONTEXT_CHANGED")
    return grant


# Implement only simulated inspection; real OCI composition is deliberately unavailable.
class SimulatedInspectionWorker:
    # Require explicit authority and provider composition; no credential defaults.
    def __init__(
        self,
        store: ExecutionStore,
        authority: DispatchAuthority,
        inspection: TenancyInspection,
        clock: Callable[[], datetime],
    ):
        self.store, self.authority, self.inspection, self.clock = (
            store,
            authority,
            inspection,
            clock,
        )

    # Read committed intent, inspect outside transactions, then guard publication.
    def run(self, operation_id: UUID) -> None:
        if not isinstance(operation_id, UUID):
            raise ValueError("INVALID_OPERATION_REFERENCE")
        committed = self.store.load(operation_id)
        if committed is None:
            return
        try:
            grant = current_grant(self.authority, committed)
        except Exception:
            # Authority implementations must fail closed. Raw entitlement/provider errors can
            # contain private material; persist only the fixed diagnostic, never exception text.
            outcome = InspectionOutcome(
                context=None,
                intent_event_id=committed.intent_event_id,
                safe_code="DISPATCH_NOT_AUTHORIZED",
                result=None,
            )
            self.store.finish(committed, None, outcome, self.clock())
            return
        attempt = self.store.claim(committed, grant, self.clock())
        if attempt is None:
            return
        try:
            # Claim is committed and its DB connection released before any adapter execution.
            # Recheck after claim as well, so delayed claim does not use the earlier grant.
            if current_grant(self.authority, committed) != grant:
                raise PermissionError("DISPATCH_CONTEXT_CHANGED")
            result = self.inspection.inspect(
                InspectTenancy(
                    contract_version="execution-1-draft",
                    kind="inspect_tenancy",
                    context=attempt.context,
                    payload=committed.intent.target,
                )
            )
            if current_grant(self.authority, committed) != grant:
                raise PermissionError("DISPATCH_CONTEXT_CHANGED")
            outcome = InspectionOutcome(
                context=attempt.context,
                intent_event_id=committed.intent_event_id,
                safe_code=result.safe_code,
                result=result,
            )
        except ProviderContractError:
            outcome = InspectionOutcome(
                context=attempt.context,
                intent_event_id=committed.intent_event_id,
                safe_code="INSPECTION_PROVIDER_REJECTED",
                result=None,
            )
        except Exception:
            outcome = InspectionOutcome(
                context=attempt.context,
                intent_event_id=committed.intent_event_id,
                safe_code="DISPATCH_CONTEXT_CHANGED",
                result=None,
            )
        self.store.finish(committed, attempt, outcome, self.clock())
