"""Baseline-qualification contract and unavailable outcome; no concrete provider imports."""

from typing import Protocol

from otm.configuration.contracts import BaselineContent


# A pure qualification boundary is injected by the host; network-backed publication is not composed.
class BaselineQualifier(Protocol):
    # Return a registered evidence version or reject without modifying provider state.
    def qualify(self, content: BaselineContent) -> str: ...


# Missing publication dependencies never fall back to permissive or simulated provider behavior.
class PublicationUnavailable(Exception):
    pass
