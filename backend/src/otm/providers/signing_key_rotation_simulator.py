"""Explicit nonusable signing material and independent persistent simulated key inventory."""

import hashlib
import hmac
import json
import secrets
from uuid import UUID

from pydantic import SecretStr

from otm.providers.automation_keys import ObservedAutomationKey
from otm.providers.automation_keys_simulator import KeyFixture
from otm.providers.required_user_contracts import ObservedRequiredUser
from otm.providers.signing_key_rotation import (
    ManagedSigningKey,
    SigningKeyMaterial,
    SigningKeyMutation,
    SigningKeyProbe,
    SigningKeyReplacement,
    SigningKeyVersion,
)
from otm.secrets.private_json import PrivateJsonRecords


# This explicitly selected simulator emits no RSA PEM and cannot authenticate against OCI.
class SimulatedSigningKeys:
    # Private custody and independent provider inventory both survive restarts.
    def __init__(self, directory, inventory, clock):
        self.records = PrivateJsonRecords(directory)
        self.inventory_store = inventory
        self.inventory_records = PrivateJsonRecords(inventory.directory)
        self.clock = clock

    # Validate exact scoped synthetic targets before any private record or provider mutation.
    def scope(self, target, context=None):
        if (
            target.purpose != "automation"
            or not target.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
            or context is not None
            and context.workspace_id != target.workspace_id
        ):
            raise ValueError("SIGNING_KEY_SCOPE_INVALID")

    # Stable immutable operation-scoped allocation preserves the very first material creation time.
    def allocate(self, target, credential_id, generation, operation_id):
        self.scope(target)
        name = credential_id.hex + "-" + operation_id.hex + ".json"
        with self.records.locked(name) as directory:
            try:
                value = self.records.read(directory, name)
            except FileNotFoundError:
                private = "simulated-key-material:" + secrets.token_urlsafe(48)
                public = "simulated-public-key:" + hashlib.sha256(private.encode()).hexdigest()
                raw = hashlib.sha256(public.encode()).hexdigest()[:32]
                version = SigningKeyVersion(
                    credential_id=credential_id,
                    created_operation_id=operation_id,
                    generation=generation,
                    target=target,
                    secret_reference="sim-signing:" + credential_id.hex,
                    secret_version=operation_id.hex,
                    fingerprint=":".join(raw[i : i + 2] for i in range(0, 32, 2)),
                    material_created_at=self.clock(),
                )
                value = {
                    "version": version.model_dump(mode="json"),
                    "private": private,
                    "public": public,
                }
                self.records.write(directory, name, value)
            version = SigningKeyVersion.model_validate_json(json.dumps(value["version"]))
            if (
                version.target != target
                or version.credential_id != credential_id
                or version.generation != generation
                or version.secret_version != operation_id.hex
                or version.created_operation_id != operation_id
            ):
                raise ValueError("SIGNING_KEY_CUSTODY_CHANGED")
            return version

    # Only fresh explicit onboarding may initialize an empty inventory, never adopt an old key.
    def enroll(self, target, credential_id, operation_id, administrator_capture, context):
        from otm.providers.administrator_access import assess_assignments

        if (
            assess_assignments(
                administrator_capture.binding, administrator_capture.facts
            ).model_dump()
            != {"group": "verified", "domain_role": "verified"}
            or administrator_capture.binding.domain_ocid != target.domain_ocid
            or administrator_capture.binding.scim_resource_id != target.scim_resource_id
        ):
            raise ValueError("SIGNING_KEY_ENROLLMENT_UNVERIFIED")
        version = self.allocate(target, credential_id, 1, operation_id)
        name = credential_id.hex + ".profile.json"
        profile = {
            "target": target.model_dump(mode="json"),
            "administrator": administrator_capture.model_dump(mode="json"),
            "root_configuration": True,
        }
        with self.records.locked(name) as directory:
            try:
                retained = self.records.read(directory, name)
            except FileNotFoundError:
                self.records.write(directory, name, profile)
                retained = profile
            if retained != profile:
                raise ValueError("SIGNING_KEY_ENROLLMENT_UNVERIFIED")

        # The initial public key is independent of all earlier inventory-only setup fixtures.
        def initialize(keys):
            if keys:
                if len(keys) == 1 and keys[0].fingerprint == version.fingerprint:
                    return keys
                raise ValueError("SIGNING_KEY_ENROLLMENT_UNVERIFIED")
            return (
                ObservedAutomationKey(
                    provider_key_id="simulated-api-key-" + operation_id.hex,
                    fingerprint=version.fingerprint,
                    created_at=self.clock(),
                    state="active",
                ),
            )

        self.mutate(target, initialize)
        material = self.material(version)
        started = self.clock()
        probe = self.probe(material, context)
        from otm.providers.signing_key_rotation import qualified_signer

        if not qualified_signer(probe, version, context, started, self.clock()):
            raise ValueError("SIGNING_KEY_ENROLLMENT_UNVERIFIED")
        row = next(
            key
            for key in self.inventory(material, context).keys
            if key.fingerprint == version.fingerprint
        )
        return ManagedSigningKey(
            version=version, provider_key_id=row.provider_key_id, uploaded_at=row.created_at
        )

    # A resumed rotation reads the original pair instead of assigning a new timestamp/version.
    def stage(self, old, context):
        self.scope(old.version.target, context)
        version = self.allocate(
            old.version.target,
            old.version.credential_id,
            old.version.generation + 1,
            context.operation_id,
        )
        SigningKeyReplacement(context=context, old=old, candidate=version)
        return version

    # Exact immutable references select files; no CURRENT/LATEST or caller path is accepted.
    def material(self, version):
        version = SigningKeyVersion.model_validate(version)
        self.scope(version.target)
        if version.secret_reference != "sim-signing:" + version.credential_id.hex:
            raise ValueError("SIGNING_KEY_CUSTODY_CHANGED")
        operation = UUID(hex=version.secret_version)
        name = version.credential_id.hex + "-" + operation.hex + ".json"
        with self.records.locked(name) as directory:
            value = self.records.read(directory, name)
        stored = SigningKeyVersion.model_validate_json(json.dumps(value["version"]))
        private, public = value["private"], value["public"]
        raw = hashlib.sha256(public.encode()).hexdigest()[:32]
        fingerprint = ":".join(raw[i : i + 2] for i in range(0, 32, 2))
        if (
            stored != version
            or not private.startswith("simulated-key-material:")
            or not hmac.compare_digest(
                public, "simulated-public-key:" + hashlib.sha256(private.encode()).hexdigest()
            )
            or not hmac.compare_digest(fingerprint, version.fingerprint)
        ):
            raise ValueError("SIGNING_KEY_CUSTODY_CHANGED")
        return SigningKeyMaterial(version, SecretStr(private), SecretStr(public))

    # Provider identity facts come from the retained inventory file, not echoed command identity.
    def inventory(self, authority, context):
        self.require_material(authority, context)
        target = authority.version.target
        user = ObservedRequiredUser(
            domain_ocid=target.domain_ocid,
            scim_resource_id=target.scim_resource_id,
            provider_ocid=target.provider_ocid,
            user_name=target.user_name,
        )
        facts = self.inventory_store.read(
            target.workspace_id, target.tenancy_id, target.tenancy_ocid, user
        ).facts
        if not any(
            key.fingerprint == authority.version.fingerprint and key.state == "active"
            for key in facts.keys
        ):
            raise ValueError("SIGNING_KEY_CURRENT_UNVERIFIED")
        return facts

    # A substituted private token cannot impersonate even a matching public version reference.
    def require_material(self, material, context):
        self.scope(material.version.target, context)
        retained = self.material(material.version)
        if not hmac.compare_digest(
            retained.private_pem.get_secret_value(), material.private_pem.get_secret_value()
        ) or not hmac.compare_digest(
            retained.public_pem.get_secret_value(), material.public_pem.get_secret_value()
        ):
            raise ValueError("SIGNING_KEY_CUSTODY_CHANGED")

    # Inventory, retained material and independent grants qualify only this simulator profile.
    def probe(self, candidate, context):
        facts = self.inventory(candidate, context)
        active = any(
            key.fingerprint == candidate.version.fingerprint and key.state == "active"
            for key in facts.keys
        )
        from otm.providers.administrator_access import AdministratorCapture, assess_assignments

        name = candidate.version.credential_id.hex + ".profile.json"
        with self.records.locked(name) as directory:
            profile = self.records.read(directory, name)
        from otm.providers.required_user_contracts import RequiredUserTarget

        if (
            RequiredUserTarget.model_validate_json(json.dumps(profile["target"]))
            != candidate.version.target
        ):
            raise ValueError("SIGNING_KEY_SCOPE_INVALID")
        capture = AdministratorCapture.model_validate_json(json.dumps(profile["administrator"]))
        if (capture.binding.domain_ocid, capture.binding.scim_resource_id) != (
            candidate.version.target.domain_ocid,
            candidate.version.target.scim_resource_id,
        ):
            raise ValueError("SIGNING_KEY_SCOPE_INVALID")
        grants = assess_assignments(capture.binding, capture.facts)
        privileges = grants.group == "verified" and grants.domain_role == "verified"
        return SigningKeyProbe(
            context=context,
            version=candidate.version,
            checked_at=self.clock(),
            complete=facts.authorized and facts.complete and facts.supported,
            oci_identity=active,
            identity_domain_administration=active and privileges,
            root_configuration=active and profile["root_configuration"] is True,
        )

    # Serialize public inventory writes per child; an unknown key is never deleted to free a slot.
    def mutate(self, target, change):
        name = target.tenancy_id.hex + ".json"
        with self.inventory_records.locked(name) as directory:
            raw = self.inventory_records.read(directory, name)
            record = KeyFixture.model_validate_json(json.dumps(raw))
            actual = record.facts.user
            if (
                record.workspace_id != target.workspace_id
                or record.tenancy_id != target.tenancy_id
                or record.tenancy_ocid != target.tenancy_ocid
                or (
                    actual.domain_ocid,
                    actual.scim_resource_id,
                    actual.provider_ocid,
                    actual.user_name,
                )
                != (
                    target.domain_ocid,
                    target.scim_resource_id,
                    target.provider_ocid,
                    target.user_name,
                )
                or not (
                    record.facts.authorized and record.facts.complete and record.facts.supported
                )
            ):
                raise ValueError("SIGNING_KEY_INVENTORY_UNAVAILABLE")
            facts = record.facts.model_copy(update={"keys": change(record.facts.keys)})
            self.inventory_records.write(
                directory,
                name,
                record.model_copy(update={"facts": facts}).model_dump(mode="json"),
                replace=True,
            )

    # Upload uses only the public half and preserves an already present candidate's original date.
    def upload(self, candidate, authority, context):
        self.require_material(candidate, context)
        self.require_material(authority, context)
        if (
            candidate.version.target != authority.version.target
            or not self.probe(authority, context).oci_identity
        ):
            raise ValueError("SIGNING_KEY_CURRENT_UNVERIFIED")

        # This closure mutates only the exact candidate within this independently verified child.
        def add(keys):
            if any(key.fingerprint == candidate.version.fingerprint for key in keys):
                return keys
            if len(keys) >= 3:
                raise ValueError("SIGNING_KEY_SLOT_REVIEW")
            return (
                *keys,
                ObservedAutomationKey(
                    provider_key_id="simulated-api-key-" + candidate.version.secret_version,
                    fingerprint=candidate.version.fingerprint,
                    created_at=self.clock(),
                    state="active",
                ),
            )

        self.mutate(candidate.version.target, add)
        return SigningKeyMutation(effect="known")

    # Retire only the exact old resource; replacement and unknown resources are protected.
    def retire(self, old, authority, context):
        self.require_material(authority, context)
        SigningKeyReplacement(context=context, old=old, candidate=authority.version)
        if not self.probe(authority, context).oci_identity:
            raise ValueError("SIGNING_KEY_PROBE_FAILED")

        # Provider IDs alone are insufficient if the resource now belongs to another fingerprint.
        def remove(keys):
            matching = [key for key in keys if key.provider_key_id == old.provider_key_id]
            if matching and matching[0].fingerprint != old.version.fingerprint:
                raise ValueError("SIGNING_KEY_RETIREMENT_UNVERIFIED")
            return tuple(key for key in keys if key.provider_key_id != old.provider_key_id)

        self.mutate(old.version.target, remove)
        return SigningKeyMutation(effect="known")
