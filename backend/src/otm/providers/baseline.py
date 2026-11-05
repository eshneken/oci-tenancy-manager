"""Explicit local structure checks; no real OCI qualification or provider writes."""

from typing import Protocol

from otm.configuration.contracts import BaselineContent, SaveBaselineDraft


# A pure qualification boundary is injected by the host; network-backed publication is not composed.
class BaselineQualifier(Protocol):
    # Return a registered evidence version or reject without modifying provider state.
    def qualify(self, content: BaselineContent) -> str: ...


# Missing publication dependencies never fall back to permissive or simulated provider behavior.
class PublicationUnavailable(Exception):
    pass


# The laptop profile checks structure and whole-unit USD, without OCI grammar validation.
class SimulatedBaselineQualifier:
    # USD is a synthetic profile choice, not discovery of a real tenancy's billing currency.
    def qualify(self, content: BaselineContent) -> str:
        SaveBaselineDraft(content=content)
        if content.budget_currency != "USD":
            raise ValueError("SIMULATED_CURRENCY_UNSUPPORTED")
        return "baseline-structure-simulated-1"
