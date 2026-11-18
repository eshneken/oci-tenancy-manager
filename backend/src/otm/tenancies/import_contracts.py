"""Exact existing-user adoption and independent access observations for shared imports."""

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from otm.contracts import Contract, Text, UtcInstant

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
BoundId = Annotated[str, Field(min_length=1, max_length=256)]


# Compartments express existing resource scope; root is explicit and never personally owned.
class ExistingScope(Contract):
    ocid: BoundId
    name: Text
    kind: Literal["root", "compartment"]


# Provider observations describe exact accounts and grants, never credential material.
class ExistingIdentity(Contract):
    user_ocid: BoundId
    scim_id: BoundId
    user_name: Text
    email: Text
    administrator: bool
    groups: Annotated[tuple[BoundId, ...], Field(max_length=100)] = ()
    roles: Annotated[tuple[BoundId, ...], Field(max_length=100)] = ()
    scopes: Annotated[tuple[ExistingScope, ...], Field(min_length=1, max_length=50)]
    policy_hash: Digest

    # Enumeration order is not a privilege change; retain exact IDs in a deterministic order.
    @field_validator("groups", "roles")
    @classmethod
    def ordered_grants(cls, value):
        return tuple(sorted(value))

    # Put shared root first and stabilize arbitrary provider compartment enumeration order.
    @field_validator("scopes")
    @classmethod
    def ordered_scopes(cls, value):
        return tuple(sorted(value, key=lambda scope: (scope.kind != "root", scope.ocid)))

    # Duplicate provider identifiers cannot masquerade as independent scopes or grants.
    @model_validator(mode="after")
    def unique_grants(self):
        if (
            len(set(self.groups)) != len(self.groups)
            or len(set(self.roles)) != len(self.roles)
            or len({scope.ocid for scope in self.scopes}) != len(self.scopes)
        ):
            raise ValueError("IMPORT_GRANTS_DUPLICATED")
        return self


# A complete bounded inventory is required before absence or adoption can be established.
class ExistingAccessInventory(Contract):
    tenancy_ocid: BoundId
    domain_ocid: BoundId
    complete: bool
    users: Annotated[tuple[ExistingIdentity, ...], Field(max_length=200)]

    # Stable provider ordering keeps harmless enumeration changes out of preview fingerprints.
    @field_validator("users")
    @classmethod
    def ordered_users(cls, value):
        return tuple(sorted(value, key=lambda user: user.user_ocid))

    # Same-name accounts remain distinct, but one provider identity cannot occur twice.
    @model_validator(mode="after")
    def exact_identities(self):
        if len({u.user_ocid for u in self.users}) != len(self.users) or len(
            {u.scim_id for u in self.users}
        ) != len(self.users):
            raise ValueError("IMPORT_IDENTITIES_DUPLICATED")
        for user in self.users:
            if any((s.kind == "root") != (s.ocid == self.tenancy_ocid) for s in user.scopes):
                raise ValueError("IMPORT_ROOT_SCOPE_INVALID")
        return self


# UI choices reference provider inventory and current directory IDs instead of invented accounts.
class ImportMemberChoice(Contract):
    user_ocid: BoundId
    person_id: UUID


# One reviewed fingerprint and explicit consent authorize full lifecycle adoption, not a password
# reset.
class ImportAdoption(Contract):
    inventory_hash: Digest
    members: Annotated[tuple[ImportMemberChoice, ...], Field(min_length=1, max_length=50)]
    lifecycle_confirmed: Literal[True]

    # A person or existing account cannot be claimed by two manifest rows.
    @model_validator(mode="after")
    def unique_people(self):
        if len({m.person_id for m in self.members}) != len(self.members) or len(
            {m.user_ocid for m in self.members}
        ) != len(self.members):
            raise ValueError("IMPORT_MEMBERS_DUPLICATED")
        return self


# Later authorized grants retain their immutable operation anchor and the original imported access.
class OwnerExpectation(Contract):
    operation_id: UUID
    identity: ExistingIdentity


# Registry provenance preserves verified initial scope without changing ordinary removal semantics.
class AdoptedIdentity(Contract):
    expected_owner: OwnerExpectation | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    contract_version: Literal["import-adoption-1"] = "import-adoption-1"
    domain_ocid: BoundId
    identity: ExistingIdentity
    known_user_ocids: Annotated[tuple[BoundId, ...], Field(max_length=200)] = ()


# Immutable accepted evidence owns server-assigned association IDs and exact verified identities.
class AdoptedMember(Contract):
    association_id: UUID
    person_id: UUID
    access: AdoptedIdentity


# This step payload is frozen once, before setup effects, and reused on retries and publication.
class ImportManifest(Contract):
    inventory: ExistingAccessInventory
    members: Annotated[tuple[AdoptedMember, ...], Field(min_length=1, max_length=50)]


# Directory suggestions are eligible employees only; matching remains an explicit administrator
# choice.
class ImportPerson(Contract):
    id: UUID
    name: Text
    email: Text


# Shared-import review exposes typed read-only discovery and a fingerprint for explicit acceptance.
class ImportReview(Contract):
    inventory: ExistingAccessInventory
    inventory_hash: Digest
    people: tuple[ImportPerson, ...]
    owner_person_id: UUID


# Every adopted account has its own result; failure to enumerate never proves an account missing.
class ImportedMemberResult(Contract):
    user_name: Text
    association_id: UUID
    user_ocid: BoundId
    state: Literal["matching", "missing", "different", "unknown"]


# The existing required-user worker captures this context alongside automation and recovery
# subjects.
class ImportedAccessSnapshot(Contract):
    tenancy_ocid: BoundId
    domain_ocid: BoundId
    members: tuple[AdoptedMember, ...]
    known_user_ocids: tuple[BoundId, ...]


# Read-only membership drift remains independent of required automation/recovery health.
class ImportedAccessCheck(Contract):
    checked_at: UtcInstant
    context_hash: Digest
    state: Literal["matching", "drifted", "unavailable"]
    members: tuple[ImportedMemberResult, ...] = ()
    unmanaged_user_ocids: tuple[BoundId, ...] = ()


# Historical or stale check results never imply current imported-member access health.
class ImportedAccessView(Contract):
    state: Literal["not_checked", "matching", "drifted", "unavailable", "stale"] = "not_checked"
    checked_at: UtcInstant | None = None
    operation_id: UUID | None = None
    members: tuple[ImportedMemberResult, ...] = ()
    unmanaged_user_ocids: tuple[BoundId, ...] = ()


# Stable JSON fingerprints bind reviewed provider facts without importing the operation union.
def import_hash(value):
    payload = value.model_dump(mode="json") if isinstance(value, Contract) else value
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# Compare only human inventory; Atlas's own setup users and baseline writes are separate controls.
def compare_imported(snapshot, inventory, at):
    context_hash = import_hash(snapshot)
    if (
        inventory is None
        or not inventory.complete
        or inventory.domain_ocid != snapshot.domain_ocid
        or inventory.tenancy_ocid != snapshot.tenancy_ocid
    ):
        return ImportedAccessCheck(checked_at=at, context_hash=context_hash, state="unavailable")
    observed = {user.user_ocid: user for user in inventory.users}
    results = tuple(
        ImportedMemberResult(
            user_name=member.access.identity.user_name,
            association_id=member.association_id,
            user_ocid=member.access.identity.user_ocid,
            state="missing"
            if member.access.identity.user_ocid not in observed
            else "matching"
            if observed[member.access.identity.user_ocid]
            == (
                member.access.expected_owner.identity
                if member.access.expected_owner
                else member.access.identity
            )
            else "different",
        )
        for member in snapshot.members
    )
    unmanaged = tuple(sorted(set(observed) - set(snapshot.known_user_ocids)))
    return ImportedAccessCheck(
        checked_at=at,
        context_hash=context_hash,
        state="drifted" if unmanaged or any(r.state != "matching" for r in results) else "matching",
        members=results,
        unmanaged_user_ocids=unmanaged,
    )


# Decode persisted JSON using strict JSON semantics for arrays and UUIDs, without scalar coercion.
def stored_import(model, value):
    return model.model_validate_json(json.dumps(value))
