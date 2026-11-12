"""Public-only bootstrap handoff port; private custody never crosses the application boundary."""

from typing import Protocol
from uuid import UUID


# Explicit composition chooses local custody now and a qualified Vault implementation later.
class BootstrapKeys(Protocol):
    # Prepare once for the exact operation; retries cannot replace an existing private key.
    def prepare(self, workspace: str, operation_id: UUID) -> None: ...

    # Read only separately stored public metadata; no key generation or private reads on GET.
    def public(self, workspace: str, operation_id: UUID) -> str | None: ...
