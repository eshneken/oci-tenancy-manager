"""Exact-version signing-key custody and replacement boundaries, independent of OCI adapters."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Protocol
from uuid import UUID

from pydantic import SecretStr, model_validator

from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.providers.automation_keys import MAXIMUM_AGE, AutomationKeyFacts, Fingerprint
from otm.providers.required_user_contracts import RequiredUserReadContext, RequiredUserTarget


# Immutable private-version references are nonsecret; they never carry PEM or select Vault CURRENT.
class SigningKeyVersion(Contract):
    credential_id: UUID
    created_operation_id: UUID
    generation: Generation
    target: RequiredUserTarget
    secret_reference: Text
    secret_version: Text
    fingerprint: Fingerprint
    material_created_at: UtcInstant

    # Only the exact managed automation identity can own this signing authority.
    @model_validator(mode="after")
    def automation_only(self):
        if self.target.purpose != "automation":
            raise ValueError("SIGNING_KEY_SCOPE_INVALID")
        return self


# Provider upload evidence stays distinct from a staged secret and its original creation time.
class ManagedSigningKey(Contract):
    version: SigningKeyVersion
    provider_key_id: Text
    uploaded_at: UtcInstant

    # Earlier material creation is the original deadline source; later upload never renews it.
    @property
    def retire_at(self):
        return min(self.uploaded_at, self.version.material_created_at) + MAXIMUM_AGE


# Material is transient, redacted and deliberately outside JSON/database contract types.
@dataclass(frozen=True, repr=False)
class SigningKeyMaterial:
    version: SigningKeyVersion
    private_pem: SecretStr
    public_pem: SecretStr


# Each attempt binds its old authority, candidate and exact existing connection/attempt fences.
class SigningKeyReplacement(Contract):
    context: RequiredUserReadContext
    old: ManagedSigningKey
    candidate: SigningKeyVersion

    # Replacement cannot change principal, reuse key material or silently jump a generation.
    @model_validator(mode="after")
    def exact_successor(self):
        a, b = self.old.version, self.candidate
        if (
            self.context.workspace_id != a.target.workspace_id
            or a.target != b.target
            or b.created_operation_id != self.context.operation_id
            or a.created_operation_id == b.created_operation_id
            or a.credential_id != b.credential_id
            or b.generation != a.generation + 1
            or a.secret_reference != b.secret_reference
            or a.secret_version == b.secret_version
            or a.fingerprint == b.fingerprint
            or b.material_created_at < a.material_created_at
        ):
            raise ValueError("SIGNING_KEY_REPLACEMENT_INVALID")
        return self


# Safe capability results must come from a signer built only from this exact staged version.
class SigningKeyProbe(Contract):
    context: RequiredUserReadContext
    version: SigningKeyVersion
    checked_at: UtcInstant
    complete: bool
    oci_identity: bool
    identity_domain_administration: bool
    root_configuration: bool


# Effect uncertainty requires read-back reconciliation, never another pair or an unrelated deletion.
class SigningKeyMutation(Contract):
    # None means qualified proof that the mutation was not sent/applied, not an absent response.
    effect: Literal["none", "known", "unknown"]


# Exact staged references remain recoverable across crashes and lost stage/upload responses.
class SigningKeyCustody(Protocol):
    # Same operation/old generation must return the same candidate, even after an uncertain reply.
    def stage(
        self, old: ManagedSigningKey, context: RequiredUserReadContext
    ) -> SigningKeyVersion: ...

    # Resolve only the requested immutable version; CURRENT/LATEST and old-version fallback forbid.
    def material(self, version: SigningKeyVersion) -> SigningKeyMaterial: ...


# These capabilities authorize only a bound automation principal; discovery is a separate contract.
class SigningKeyReplacementProvider(Protocol):
    # List all pages with independent actual-user identity and coverage; no expected-user echo.
    def inventory(
        self, authority: SigningKeyMaterial, context: RequiredUserReadContext
    ) -> AutomationKeyFacts: ...

    # Upload only the candidate public half; reconcile its fingerprint after any uncertain result.
    def upload(
        self,
        candidate: SigningKeyMaterial,
        authority: SigningKeyMaterial,
        context: RequiredUserReadContext,
    ) -> SigningKeyMutation: ...

    # No old signer may satisfy this exact-version probe, even if another credential still works.
    def probe(
        self, candidate: SigningKeyMaterial, context: RequiredUserReadContext
    ) -> SigningKeyProbe: ...

    # Delete only the frozen managed old key using the verified replacement, never an unknown key.
    def retire(
        self,
        old: ManagedSigningKey,
        authority: SigningKeyMaterial,
        context: RequiredUserReadContext,
    ) -> SigningKeyMutation: ...


# Capability checks cannot renew material age or accept proof from another connection/version.
def qualified_signer(probe, version, context, started_at, finished_at):
    probe = SigningKeyProbe.model_validate(probe)
    return (
        probe.version == version
        and probe.context == context
        and context.workspace_id == version.target.workspace_id
        and started_at <= probe.checked_at <= finished_at <= started_at + timedelta(seconds=30)
        and version.material_created_at <= started_at < version.material_created_at + MAXIMUM_AGE
        and probe.complete
        and probe.oci_identity
        and probe.identity_domain_administration
        and probe.root_configuration
    )


# Independently returned identity and full enumeration qualify both positive and negative facts.
def inventory_matches(facts, target):
    facts = AutomationKeyFacts.model_validate(facts)
    return (
        facts.authorized
        and facts.complete
        and facts.supported
        and facts.user.domain_ocid == target.domain_ocid
        and facts.user.scim_resource_id == target.scim_resource_id
        and facts.user.provider_ocid == target.provider_ocid
        and facts.user.user_name == target.user_name
    )


# Pointer publication never proves retirement: old absence and new active presence both matter.
def retired_inventory(facts, replacement, at):
    facts = AutomationKeyFacts.model_validate(facts)
    replacement = SigningKeyReplacement.model_validate(replacement)
    if not inventory_matches(facts, replacement.old.version.target):
        return False
    old = replacement.old
    candidate = replacement.candidate
    return (
        old.provider_key_id not in {key.provider_key_id for key in facts.keys}
        and old.version.fingerprint not in {key.fingerprint for key in facts.keys}
        and any(
            key.fingerprint == candidate.fingerprint
            and key.state == "active"
            and key.created_at is not None
            and candidate.material_created_at <= key.created_at <= at
            for key in facts.keys
        )
    )
