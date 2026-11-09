"""Validate exact-subject presence against attempt, authority references and capture time."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from otm.contracts import UtcInstant
from otm.providers.inspection import ProviderContractError
from otm.providers.required_user_contracts import InspectRequiredUser, RequiredUserObservation


# Adapters expose only one read capability; no creation, repair, secret retrieval or fallback
# exists.
class RequiredUserProvider(Protocol):
    # Observe exactly the bound SCIM user in its verified domain, with explicit coverage.
    def inspect_required_user(self, command: InspectRequiredUser) -> RequiredUserObservation: ...


# Pairing validates evidence provenance but cannot replace live entitlement or credential
# resolution.
class RequiredUserInspection:
    # The host selects an adapter and aware UTC clock explicitly; importing this module performs no
    # I/O.
    def __init__(self, provider: RequiredUserProvider, clock: Callable[[], datetime]):
        self.provider, self.clock = provider, clock

    # Require a valid clock without exposing malformed clock or provider contents in error text.
    def _now(self):
        try:
            return TypeAdapter(UtcInstant).validate_python(self.clock(), strict=True)
        except Exception:
            raise ProviderContractError("REQUIRED_USER_CLOCK_INVALID") from None

    # Reject stale/cross-subject facts, wrong-domain404s and changed generations before consumption.
    def inspect(self, command: InspectRequiredUser) -> RequiredUserObservation:
        command = InspectRequiredUser.model_validate(command)
        started = self._now()
        try:
            raw = self.provider.inspect_required_user(command)
        except Exception:
            raise ProviderContractError("REQUIRED_USER_PROVIDER_FAILED") from None
        completed = self._now()
        return paired_observation(command, raw, started, completed)


# Reuse exact-subject/time validation at adapter and worker boundaries without trusting factories.
def paired_observation(command, raw, started, completed):
    command = InspectRequiredUser.model_validate(command)
    try:
        result = RequiredUserObservation.model_validate(raw)
    except (ValidationError, TypeError):
        raise ProviderContractError("INVALID_REQUIRED_USER_RESULT") from None
    if result.context != command.context or result.target != command.target:
        raise ProviderContractError("REQUIRED_USER_CONTEXT_MISMATCH")
    if not started <= result.captured_at <= completed:
        raise ProviderContractError("REQUIRED_USER_CAPTURE_WINDOW_MISMATCH")
    target = command.target
    if (
        result.checked_domain_ocid is not None
        and result.checked_domain_ocid != target.domain_ocid
        or result.checked_scim_resource_id is not None
        and result.checked_scim_resource_id != target.scim_resource_id
    ):
        raise ProviderContractError("REQUIRED_USER_CHECKED_IDENTITY_MISMATCH")
    if result.observed and (
        result.observed.domain_ocid,
        result.observed.scim_resource_id,
        result.observed.provider_ocid,
    ) != (target.domain_ocid, target.scim_resource_id, target.provider_ocid):
        raise ProviderContractError("REQUIRED_USER_OBSERVED_IDENTITY_MISMATCH")
    return result
