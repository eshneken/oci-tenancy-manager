"""Read-only budget capability and normalized failure boundary; no provider selection or I/O."""

from typing import Protocol

from otm.financial.contracts import BudgetReadResult


# A qualified adapter owns SDK timeout/credential resolution and returns one bounded response.
class BudgetFacade(Protocol):
    # Read only the exact retained budget through the captured child/source context.
    def read_managed_budget(self, target, stored, at) -> BudgetReadResult: ...


# Failure codes are closed at the worker boundary; raw provider strings never become audit/UI text.
class BudgetReadUnavailable(ValueError):
    pass
