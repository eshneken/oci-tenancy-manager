"""Closed administrator grant/evidence contracts, independent of employee records and secrets."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract, Text, UtcInstant
from otm.operations.contracts import ActorIdentity


# Keep authority and its stable revision after sessions are revoked or cleaned up.
class Administrator(Contract):
    id: UUID
    workspace_id: Text
    identity_kind: Literal["local_recovery", "corporate_sso"]
    issuer: Text
    subject: Text
    display_name: Text
    email: Text | None
    status: Literal["active", "revoked"]
    authorization_revision: UUID
    created_at: UtcInstant
    updated_at: UtcInstant
    revoked_at: UtcInstant | None

    # Fail closed on malformed storage as well as mismatched local identity and timestamps.
    @model_validator(mode="after")
    def consistent(self):
        if (
            (self.status == "active") != (self.revoked_at is None)
            or self.updated_at < self.created_at
            or (self.revoked_at is not None and self.revoked_at < self.created_at)
            or (
                self.identity_kind == "local_recovery"
                and (self.subject != str(self.id) or self.status != "active")
            )
        ):
            raise ValueError("INVALID_ADMINISTRATOR_RECORD")
        return self


# Capture bounded immutable revocation evidence without credentials or attempted login input.
class AdministratorRevoked(Contract):
    contract_version: Literal["administrator-revocation-1"]
    administrator_id: UUID
    prior_revision: UUID
    authorization_revision: UUID
    actor: ActorIdentity


# Report committed grant state without implying a credential or IdP operation occurred.
class AdministratorChange(Contract):
    administrator_id: UUID
    status: Literal["revoked"]
    authorization_revision: UUID
    at: UtcInstant


# Return only fixed public codes, never database values or raw identity-provider errors.
class AdministratorFailure(Exception):
    # Reject arbitrary diagnostics so future HTTP handlers can safely serialize this boundary.
    def __init__(self, status: int, code: str):
        if (status, code) not in {
            (400, "INVALID_ADMINISTRATOR_COMMAND"),
            (403, "ADMINISTRATOR_REQUIRED"),
            (403, "RECOVERY_ADMINISTRATOR_PROTECTED"),
            (404, "ADMINISTRATOR_NOT_FOUND"),
            (409, "ADMINISTRATOR_REVISION_CHANGED"),
            (503, "ADMINISTRATOR_SERVICE_UNAVAILABLE"),
        }:
            raise ValueError("INVALID_ADMINISTRATOR_DIAGNOSTIC") from None
        super().__init__(code)
        self.status, self.code = status, code


# Return only administrator display/management fields; credential/session material never joins
# this DTO.
class AdministratorView(Contract):
    id: UUID
    display_name: Text
    email: Text | None
    identity_kind: Literal["local_recovery", "corporate_sso"]
    status: Literal["active", "revoked"]
    authorization_revision: UUID


# Summarize the whole authorized workspace independently of a filtered page.
class AdministratorStatistics(Contract):
    total: int
    active: int
    protected_recovery: int


# Define bounded directory controls before constructing any SQL identifiers or offsets.
class AdministratorQuery(Contract):
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50, 100] = 10
    sort: Literal["display_name", "email", "identity_kind", "status"] = "display_name"
    direction: Literal["asc", "desc"] = "asc"
    query: Annotated[str, Field(max_length=128)] = ""


# Return a stable sorted page with explicit total scope and zero-result pagination.
class AdministratorDirectory(Contract):
    items: list[AdministratorView]
    total: int
    page: int
    page_size: int
    pages: int
    statistics: AdministratorStatistics


# Compare the exact displayed revision when requesting a privilege-changing operation.
class RevokeAdministrator(Contract):
    expected_revision: UUID
