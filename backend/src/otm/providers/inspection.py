"""Validate a provider's read result against the original attempt, target and capture window."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import ValidationError

from otm.providers.inspection_contracts import (
    RESULT_ADAPTER,
    InspectionConfirmed,
    InspectionResult,
    InspectTenancy,
)


# One explicit read capability shared by the simulator and a future qualified OCI adapter.
class InspectionProvider(Protocol):
    # Return normalized observation evidence for precisely this attempt, never raw SDK data.
    def inspect_tenancy(self, command: InspectTenancy) -> InspectionResult: ...


# Reject unusable provider output with a fixed diagnostic, without reflecting its contents.
class ProviderContractError(ValueError):
    pass


# Pair request/result evidence; this is not the operation store, SSO or dispatch authority.
class TenancyInspection:
    # Inject the adapter and clock for deterministic capture-window checks.
    def __init__(self, provider: InspectionProvider, clock: Callable[[], datetime]):
        self.provider, self.clock = provider, clock

    # Require a fresh exact-target result before any caller may consume confirmed facts.
    #
    # The durable simulated worker checks current intent/attempt generations and injected
    # authority. Real credential resolution is future work; pairing does not authorize access.
    def inspect(self, command: InspectTenancy) -> InspectionResult:
        command = InspectTenancy.model_validate(command)
        started_at = self.clock()
        try:
            raw = self.provider.inspect_tenancy(command)
        except Exception:
            # An adapter must normalize its own errors. Fail closed if it violates that
            # contract; never reflect an exception that could contain raw provider material.
            raise ProviderContractError("INSPECTION_PROVIDER_FAILED") from None
        completed_at = self.clock()
        try:
            result = RESULT_ADAPTER.validate_python(raw)
        except ValidationError:
            # Never chain raw validation details, which can contain inappropriate provider text.
            raise ProviderContractError("INVALID_INSPECTION_RESULT") from None
        if result.attempt_id != command.context.attempt_id:
            raise ProviderContractError("INSPECTION_ATTEMPT_MISMATCH")
        times = [result.observed_at, *(item.observed_at for item in result.evidence)]
        if isinstance(result, InspectionConfirmed):
            facts, target = result.tenancy, command.payload
            if (
                facts.tenancy_ocid != target.tenancy_ocid
                or facts.parent_tenancy_ocid != target.parent_tenancy_ocid
                or facts.organization_id != target.organization_id
                or facts.tenancy_ocid == facts.parent_tenancy_ocid
            ):
                raise ProviderContractError("INSPECTION_TARGET_MISMATCH")
            times.append(facts.observed_at)
        # This first capability performs a fresh read. Cached observations are not silently
        # relabeled as current; future cached-read support needs an explicit freshness policy.
        if any(not started_at <= instant <= completed_at for instant in times):
            raise ProviderContractError("INSPECTION_CAPTURE_OUTSIDE_ATTEMPT")
        return result
