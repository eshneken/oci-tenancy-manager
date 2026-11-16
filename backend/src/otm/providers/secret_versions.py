"""Metadata-only secret-version boundary; contracts contain no passwords or private key material."""

from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract, Text, UtcInstant

VersionNumber = Annotated[int, Field(ge=1)]
ManagedSecretPurpose = Literal["automation-key", "recovery-password", "bootstrap-key"]


# Bind custody to an exact registered credential; names alone never authorize secret access.
class ManagedSecretBinding(Contract):
    workspace_id: Text
    credential_id: UUID
    secret_reference: Text
    purpose: ManagedSecretPurpose


# Rotation labels and deletion timing are provider metadata, never the secret content itself.
class SecretVersionFacts(Contract):
    number: VersionNumber
    stages: frozenset[Text]
    deletion_at: UtcInstant | None = None


# Complete paginated observations carry a conditional-write revision to reject concurrent changes.
class SecretVersionInventory(Contract):
    binding: ManagedSecretBinding
    revision: Text
    complete: bool
    versions: Annotated[tuple[SecretVersionFacts, ...], Field(max_length=1024)]

    # Duplicate version identities make counts/eligibility ambiguous and must not reach a writer.
    @model_validator(mode="after")
    def unique_versions(self):
        if len({version.number for version in self.versions}) != len(self.versions):
            raise ValueError("SECRET_VERSION_INVENTORY_INVALID")
        return self


# Adapters normalize failures; arbitrary SDK exceptions or credential values must not escape.
class SecretVersionUnavailable(ValueError):
    pass


# Revision conflicts require fresh inventory/protection checks, not an unconditional retry.
class SecretVersionConflict(ValueError):
    pass


# Real adapters must authorize the exact binding and support conditional version-level deletion.
# Whole-secret bootstrap disposal is deliberately a separate future lifecycle operation.
class SecretVersionFacade(Protocol):
    # Return metadata for the bound secret, marking partial pagination incomplete.
    def inventory(self, binding: ManagedSecretBinding) -> SecretVersionInventory: ...

    # Schedule one deprecated version only; do not delete the parent secret or bypass OCI's delay.
    def schedule_version_deletion(
        self,
        binding: ManagedSecretBinding,
        number: int,
        deletion_at: UtcInstant,
        expected_revision: str,
    ) -> SecretVersionInventory: ...
