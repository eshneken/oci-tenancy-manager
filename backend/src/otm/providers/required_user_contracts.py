"""Exact-subject presence contracts; identity existence does not imply usable access."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import StringConstraints, model_validator

from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.providers.inspection_contracts import InspectionTarget

DomainOcid = Annotated[
    str, StringConstraints(min_length=15, max_length=256, pattern=r"^ocid1\.domain\.[A-Za-z0-9.]+$")
]
UserOcid = Annotated[
    str, StringConstraints(min_length=15, max_length=256, pattern=r"^ocid1\.user\.[A-Za-z0-9.]+$")
]


# Pin the expected child and operational subject; names never select identities.
class RequiredUserTarget(InspectionTarget):
    workspace_id: Text
    tenancy_id: UUID
    purpose: Literal["automation", "recovery"]
    subject_binding_id: UUID
    binding_generation: Generation
    identity_domain_binding_id: UUID
    domain_ocid: DomainOcid
    scim_resource_id: Text
    provider_ocid: UserOcid | None
    user_name: Text

    # Reject a parent used as its own child; live registration remains a caller check.
    @model_validator(mode="after")
    def child_scope(self):
        if self.tenancy_ocid == self.parent_tenancy_ocid:
            raise ValueError("REGISTERED_CHILD_REQUIRED")
        return self


# Freeze the selected automation connection, not an assignment, credential or permission profile.
class RequiredUserReadContext(Contract):
    workspace_id: Text
    operation_id: UUID
    step_key: Text
    attempt_id: UUID
    intent_revision: Generation
    execution_generation: Generation
    connection_id: UUID
    connection_revision: Generation


# An internal capability command freezes one subject and one attempt; it grants no authorization.
class InspectRequiredUser(Contract):
    contract_version: Literal["required-user-presence-2"] = "required-user-presence-2"
    context: RequiredUserReadContext
    target: RequiredUserTarget

    # Independently scoped input cannot cross a workspace before reaching the provider.
    @model_validator(mode="after")
    def workspace_scope(self):
        if self.context.workspace_id != self.target.workspace_id:
            raise ValueError("REQUIRED_USER_SCOPE_MISMATCH")
        return self


# Return actual provider identifiers separately from expected bindings; names are observed metadata.
class ObservedRequiredUser(Contract):
    domain_ocid: DomainOcid
    scim_resource_id: Text
    provider_ocid: UserOcid | None
    user_name: Text


# A complete authorized exact-domain absence is distinct from every kind of unsuccessful read.
class RequiredUserObservation(Contract):
    contract_version: Literal["required-user-presence-2"] = "required-user-presence-2"
    context: RequiredUserReadContext
    target: RequiredUserTarget
    captured_at: UtcInstant
    # Opaque per-read correlation; this is not an audit FK or a permission receipt.
    read_id: UUID | None
    checked_domain_ocid: DomainOcid | None
    checked_scim_resource_id: Text | None
    state: Literal["present", "missing", "unknown"]
    safe_code: Literal[
        "USER_PRESENT",
        "USER_MISSING",
        "ACCESS_UNVERIFIED",
        "ACCESS_DENIED",
        "READ_TIMEOUT",
        "READ_DELAYED",
        "INCOMPLETE_READ",
        "DOMAIN_UNVERIFIED",
        "UNSUPPORTED_CAPABILITY",
    ]
    # Exact-read authorization/coverage evidence does not certify administrative privileges.
    authorized: bool
    complete: bool
    observed: ObservedRequiredUser | None

    # Partial/failed facts cannot masquerade as a positive identity or an authoritative absence.
    @model_validator(mode="after")
    def coverage(self):
        if self.state in {"present", "missing"}:
            if not (
                self.authorized
                and self.complete
                and self.read_id
                and self.checked_domain_ocid
                and self.checked_scim_resource_id
            ):
                raise ValueError("REQUIRED_USER_COMPLETE_READ_REQUIRED")
            expected_code = "USER_PRESENT" if self.state == "present" else "USER_MISSING"
            if self.safe_code != expected_code or (self.observed is not None) != (
                self.state == "present"
            ):
                raise ValueError("REQUIRED_USER_RESULT_MISMATCH")
        elif (
            self.complete
            or self.observed is not None
            or self.safe_code in {"USER_PRESENT", "USER_MISSING"}
        ):
            raise ValueError("REQUIRED_USER_UNKNOWN_HAS_NO_CONFIRMED_FACTS")
        return self
