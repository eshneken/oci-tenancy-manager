"""Explicit local baseline structure checks; no real OCI grammar qualification or writes."""

from otm.configuration.contracts import BaselineContent, SaveBaselineDraft


# The laptop profile checks structure and whole-unit USD, without OCI grammar validation.
class SimulatedBaselineQualifier:
    # USD is a synthetic profile choice, not discovery of a real tenancy's billing currency.
    def qualify(self, content: BaselineContent) -> str:
        SaveBaselineDraft(content=content)
        if content.budget_currency != "USD":
            raise ValueError("SIMULATED_CURRENCY_UNSUPPORTED")
        return "baseline-structure-simulated-1"
