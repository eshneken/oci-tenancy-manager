"""Read canonical identity records without inventing current OCI presence or access authority."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select

from otm.contracts import Contract, Text, UtcInstant
from otm.providers.required_user_contracts import DomainOcid, UserOcid
from otm.storage.tables import managed_object_binding as binding
from otm.tenancies.automation_keys import AutomationKeysView
from otm.tenancies.presence_contracts import (
    AdministratorAccessView,
    RecoveryConsoleView,
    UserPresenceView,
)


# Expose only useful account/provenance facts; no credentials, internal heads or readiness claims.
class RequiredUserIdentity(Contract):
    user_name: Text
    user_ocid: UserOcid
    scim_resource_id: Text
    domain_ocid: DomainOcid
    recorded_at: UtcInstant
    retired_at: UtcInstant | None
    source_operation_id: UUID


# Missing registration is distinct from a missing OCI account; retirement is a local record state.
class RequiredUserRecord(Contract):
    purpose: Literal["automation", "recovery"]
    identity_state: Literal["recorded", "not_recorded", "retired"]
    identity: RequiredUserIdentity | None
    presence: UserPresenceView = Field(default_factory=UserPresenceView)
    administrator_access: AdministratorAccessView = Field(default_factory=AdministratorAccessView)

    # An absent record cannot carry invented identity details or a retirement timestamp.
    @model_validator(mode="after")
    def identity_pairing(self):
        if (self.identity_state == "not_recorded") != (self.identity is None):
            raise ValueError("REQUIRED_USER_RECORD_MISMATCH")
        if self.identity is not None and (
            (self.identity_state == "retired") != (self.identity.retired_at is not None)
        ):
            raise ValueError("REQUIRED_USER_RETIREMENT_MISMATCH")
        return self


# The read-only view always names both supported purposes, with independent identity records.
class RequiredUsersDirectory(Contract):
    tenancy_id: UUID
    tenancy_status: Literal["pending", "active", "terminating", "terminated", "failed", "cancelled"]
    provider_mode: Literal["simulated"]
    check_available: bool = False
    check_unavailable_reason: (
        Literal["not_configured", "tenancy_inactive", "tenancy_busy", "provider_unavailable"] | None
    ) = "not_configured"
    pending_operation_id: UUID | None = None
    recovery_console: RecoveryConsoleView = Field(default_factory=RecoveryConsoleView)
    automation_keys: AutomationKeysView = Field(default_factory=AutomationKeysView)
    users: Annotated[tuple[RequiredUserRecord, ...], Field(min_length=2, max_length=2)]

    # The API cannot accidentally omit, duplicate or reorder a required purpose.
    @model_validator(mode="after")
    def independent_purposes(self):
        if tuple(user.purpose for user in self.users) != ("automation", "recovery"):
            raise ValueError("REQUIRED_USER_PURPOSES_REQUIRED")
        return self


# Project the latest bound identity per purpose from one scoped snapshot; never call a provider.
def required_user_records(connection, workspace, child):
    rows = connection.execute(
        select(binding)
        .where(
            binding.c.workspace_id == workspace,
            binding.c.tenancy_id == child["id"],
            binding.c.logical_key.in_(
                ("identity/domain", "identity/user/automation", "identity/user/recovery")
            ),
        )
        .order_by(binding.c.generation.desc())
    ).mappings()
    latest = {}
    for row in rows:
        latest.setdefault(row["logical_key"], row)
    records = []
    domain = latest.get("identity/domain")
    for purpose in ("automation", "recovery"):
        user = latest.get("identity/user/" + purpose)
        if user is None:
            records.append(
                RequiredUserRecord(purpose=purpose, identity_state="not_recorded", identity=None)
            )
            continue
        # Broken persisted references are an unavailable read, never a successful empty inventory.
        if (
            domain is None
            or domain["kind"] != "identity_domain"
            or domain["ownership_mode"] != "observed_reference"
            or user["kind"] != "managed_user"
            or user["ownership_mode"] != "managed"
            or user["identity_domain_binding_id"] != domain["id"]
            or user["state"] not in {"active", "retired"}
            or user["state"] != domain["state"]
            or user["source_evidence_event_id"] != domain["source_evidence_event_id"]
        ):
            raise RuntimeError("REQUIRED_USER_RECORDS_UNAVAILABLE")
        records.append(
            RequiredUserRecord(
                purpose=purpose,
                identity_state="recorded" if user["state"] == "active" else "retired",
                identity=RequiredUserIdentity(
                    user_name=user["user_name"],
                    user_ocid=user["provider_ocid"],
                    scim_resource_id=user["scim_resource_id"],
                    domain_ocid=domain["provider_ocid"],
                    recorded_at=user["created_at"],
                    retired_at=user["updated_at"] if user["state"] == "retired" else None,
                    source_operation_id=user["created_operation_id"],
                ),
            )
        )
    return RequiredUsersDirectory(
        tenancy_id=child["id"],
        tenancy_status=child["status"],
        provider_mode=child["provider_mode"],
        users=tuple(records),
    )
