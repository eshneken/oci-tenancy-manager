"""Stateful, clock-controlled child inspection with no SDK, network, database or secret access."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from otm.providers.inspection_contracts import (
    Contract,
    Generation,
    InspectionConfirmed,
    InspectionResult,
    InspectionUnobservable,
    InspectionUnsupported,
    InspectTenancy,
    ReadBackEvidence,
    TenancyFacts,
    TenancyOcid,
    Text,
    UtcInstant,
)


# Freeze or advance simulator time explicitly; no background sleeps or timers are used.
class ManualClock:
    # Start at a validated UTC instant rather than silently accepting local/naive time.
    def __init__(self, now: datetime):
        self._now = TypeAdapter(UtcInstant).validate_python(now)

    # Read the current instant without advancing it as a side effect.
    def now(self) -> datetime:
        return self._now

    # Advance monotonically so delayed-read scenarios remain repeatable.
    def advance(self, elapsed: timedelta) -> None:
        if elapsed < timedelta(0):
            raise ValueError("Simulator time cannot move backwards")
        self._now += elapsed


# Test-only binding state; it models loss/rotation without holding an API key or password.
class SimulatedAccess(Contract):
    workspace_id: Text
    access_binding_id: UUID
    credential_generation: Generation
    permitted: bool
    tenancy_ocids: frozenset[TenancyOcid]


# Provider-side state that persists across reads independently of application operations.
class SimulatedTenancy(Contract):
    workspace_id: Text
    facts: TenancyFacts
    visible_at: UtcInstant
    fault: Literal["denied", "timeout", "unsupported"] | None = None


# Implement one facade capability honestly; unsupported write capabilities are not exposed.
class SimulatedInspectionProvider:
    # Keep provider fixture state separate from the caller and its future operation store.
    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock
        self._access: dict[tuple[str, UUID], SimulatedAccess] = {}
        self._tenancies: dict[tuple[str, str], SimulatedTenancy] = {}
        self._evidence: dict[UUID, tuple[UUID, TenancyFacts]] = {}

    # Change a test binding to exercise revocation and credential rotation.
    def set_access(self, access: SimulatedAccess) -> None:
        access = SimulatedAccess.model_validate(access)
        self._access[(access.workspace_id, access.access_binding_id)] = access

    # Seed or change independent provider facts, visibility time and a named read fault.
    def set_tenancy(self, tenancy: SimulatedTenancy) -> None:
        tenancy = SimulatedTenancy.model_validate(tenancy)
        self._tenancies[(tenancy.workspace_id, tenancy.facts.tenancy_ocid)] = tenancy

    # Resolve an immutable simulated observation; no durable application audit is implied.
    def read_evidence(self, reference: UUID) -> tuple[UUID, TenancyFacts]:
        return self._evidence[reference]

    # Read the exact binding and child; unavailable evidence never proves absence.
    def inspect_tenancy(self, command: InspectTenancy) -> InspectionResult:
        command = InspectTenancy.model_validate(command)
        now, context = self.clock(), command.context
        common = {
            "contract_version": "execution-1-draft",
            "attempt_id": context.attempt_id,
            "observed_at": now,
            "provider_request_id": "sim-" + str(uuid4()),
            "provider_operation_id": None,
        }

        # Return a closed safe outcome without exposing state from a different scope.
        def unavailable(code, continuation="manual"):
            return InspectionUnobservable(
                kind="unobservable",
                safe_code=code,
                continuation=continuation,
                evidence=(),
                **common,
            )

        access = self._access.get((context.workspace_id, context.access_binding_id))
        if not access or access.credential_generation != context.credential_generation:
            return unavailable("ACCESS_UNVERIFIED")
        if not access.permitted or command.payload.tenancy_ocid not in access.tenancy_ocids:
            return unavailable("ACCESS_DENIED")
        tenancy = self._tenancies.get((context.workspace_id, command.payload.tenancy_ocid))
        if not tenancy:
            return unavailable("TENANCY_UNOBSERVABLE", "observe")
        if tenancy.fault == "denied":
            return unavailable("ACCESS_DENIED")
        if tenancy.fault == "timeout":
            return unavailable("READ_TIMEOUT", "observe")
        if tenancy.fault == "unsupported":
            return InspectionUnsupported(
                kind="unsupported",
                safe_code="UNSUPPORTED_CAPABILITY",
                continuation="manual",
                evidence=(),
                **common,
            )
        if now < tenancy.visible_at:
            return unavailable("READ_DELAYED", "observe")
        # Return actual provider facts, including a potentially wrong parent. The shared
        # pairing service must reject a mismatch rather than trusting the requested target.
        facts = tenancy.facts.model_copy(update={"observed_at": now})
        reference = uuid4()
        self._evidence[reference] = (context.attempt_id, facts)
        return InspectionConfirmed(
            kind="confirmed",
            safe_code="TENANCY_INSPECTED",
            milestone="tenancy_inspected",
            tenancy=facts,
            identity=None,
            evidence=(ReadBackEvidence(code="READ_BACK", evidence_ref=reference, observed_at=now),),
            **common,
        )
