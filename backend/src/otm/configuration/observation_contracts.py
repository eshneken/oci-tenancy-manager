"""Closed simulator binding/observation envelopes; absence is explicit qualified evidence."""

from typing import Literal

from pydantic import model_validator

from otm.configuration.rollout_contracts import ManagedConfigurationObject
from otm.contracts import Contract


# Keep the original managed identity independent of externally changed simulated cloud state.
class ManagedObservation(Contract):
    contract_version: Literal["managed-observation-1"] = "managed-observation-1"
    binding: ManagedConfigurationObject
    state: Literal["present", "missing", "unavailable"]
    observed: ManagedConfigurationObject | None
    complete: bool

    # Missing needs explicit complete absence; failed reads never become a fabricated observation.
    @model_validator(mode="after")
    def coverage(self):
        if self.state == "present" and (not self.complete or self.observed is None):
            raise ValueError("PRESENT_OBSERVATION_REQUIRED")
        if self.state == "missing" and (not self.complete or self.observed is not None):
            raise ValueError("AUTHORIZED_ABSENCE_REQUIRED")
        if self.state == "unavailable" and (self.complete or self.observed is not None):
            raise ValueError("UNAVAILABLE_HAS_NO_OBSERVATION")
        return self
