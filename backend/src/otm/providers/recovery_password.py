"""Implementation-neutral secret custody and exact-subject password-change capabilities."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import SecretStr, model_validator

from otm.contracts import Contract, Text
from otm.providers.required_user_contracts import RequiredUserReadContext, RequiredUserTarget


# A secret location is inseparable from its exact recovery identity, never an arbitrary caller URL.
class PasswordLocation(Contract):
    credential_id: UUID
    secret_reference: Text | None = None
    target: RequiredUserTarget

    # Password custody cannot become an automation credential or another user's password reset.
    @model_validator(mode="after")
    def recovery_only(self):
        if self.target.purpose != "recovery":
            raise ValueError("RECOVERY_PASSWORD_SCOPE_INVALID")
        return self


# Immutable references may enter operation evidence; secret content cannot enter this contract.
class PasswordVersion(Contract):
    location: PasswordLocation
    version: Text
    operation_id: UUID

    # Only stage allocation may begin without a provider reference; no usable version is unbound.
    @model_validator(mode="after")
    def bound_secret(self):
        if self.location.secret_reference is None:
            raise ValueError("RECOVERY_PASSWORD_SECRET_UNALLOCATED")
        return self


# Password material stays transient and redacted, with no generic JSON or database representation.
@dataclass(frozen=True, repr=False)
class PasswordMaterial:
    reference: PasswordVersion
    password: SecretStr


# Child writes have explicit effect knowledge; exceptions are not permission to retry a reset.
class PasswordChange(Contract):
    effect: Literal["none", "known", "unknown"]


# The Vault boundary always selects CURRENT for normal disclosure and exact candidates for writes.
class RecoveryPasswordVault(Protocol):
    # Persist a recoverable immutable candidate before any corresponding child password change.
    def stage(self, location: PasswordLocation, operation_id: UUID) -> PasswordVersion: ...

    # Return only the exact staged version, never silently substitute CURRENT or LATEST.
    def candidate(self, reference: PasswordVersion) -> PasswordMaterial: ...

    # Resolve the stable secret's CURRENT stage and return its actual immutable version identity.
    def current(self, location: PasswordLocation) -> PasswordMaterial: ...

    # Conditionally publish only a separately verified candidate; preserve newer external pointers.
    def promote(self, reference: PasswordVersion, expected_current: str | None) -> None: ...


# Machine authority and conditional writes are independent of the human's application session.
class RecoveryPasswordTarget(Protocol):
    # Set only the bound existing recovery user's password using independently held authority.
    def change(
        self, material: PasswordMaterial, context: RequiredUserReadContext
    ) -> PasswordChange: ...

    # Qualify that exact candidate against the child; an existence read alone is insufficient.
    def verify(self, material: PasswordMaterial, context: RequiredUserReadContext) -> bool: ...


# Reject unnormalized provider objects before any secret can reach a response or child SDK call.
def require_password_material(value):
    if not isinstance(value, PasswordMaterial) or not isinstance(value.password, SecretStr):
        raise ValueError("RECOVERY_PASSWORD_MATERIAL_INVALID")
    PasswordVersion.model_validate(value.reference)
    password = value.password.get_secret_value()
    if not 32 <= len(password) <= 256 or any(char in password for char in "\x00\r\n"):
        raise ValueError("RECOVERY_PASSWORD_MATERIAL_INVALID")
    return value
