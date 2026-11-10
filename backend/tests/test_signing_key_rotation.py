"""Exact private-version authority and independent retirement evidence stay separate."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from test_automation_keys import fixture

from otm.providers.signing_key_rotation import (
    ManagedSigningKey,
    SigningKeyMaterial,
    SigningKeyProbe,
    SigningKeyReplacement,
    SigningKeyVersion,
    inventory_matches,
    qualified_signer,
    retired_inventory,
)


# Only synthetic references and redacted nonusable material enter these no-provider unit cases.
def rotation_case():
    c = fixture()
    c.version = SigningKeyVersion(
        credential_id=uuid4(),
        created_operation_id=uuid4(),
        generation=1,
        target=c.a,
        secret_reference="simulated-custody-reference",
        secret_version="original-version",
        fingerprint=c.key.fingerprint,
        material_created_at=c.key.created_at,
    )
    c.old = ManagedSigningKey(
        version=c.version,
        provider_key_id=c.key.provider_key_id,
        uploaded_at=c.key.created_at + timedelta(seconds=1),
    )
    c.candidate = c.version.model_copy(
        update={
            "generation": 2,
            "created_operation_id": c.command.context.operation_id,
            "secret_version": "candidate-version",
            "fingerprint": ":".join(["cd"] * 16),
            "material_created_at": c.clock(),
        }
    )
    c.replacement = SigningKeyReplacement(
        context=c.command.context, old=c.old, candidate=c.candidate
    )
    c.probe = SigningKeyProbe(
        context=c.command.context,
        version=c.candidate,
        checked_at=c.clock(),
        complete=True,
        oci_identity=True,
        identity_domain_administration=True,
        root_configuration=True,
    )
    return c


# Upload, discovery and later retries cannot renew the original private material's retirement time.
def test_original_deadline_and_redaction():
    c = rotation_case()
    assert c.old.retire_at == c.version.material_created_at + timedelta(days=30)
    earlier = c.old.model_copy(
        update={"uploaded_at": c.version.material_created_at - timedelta(days=1)}
    )
    assert earlier.retire_at == c.version.material_created_at + timedelta(days=29)
    material = SigningKeyMaterial(
        version=c.candidate,
        private_pem=SecretStr("synthetic-private"),
        public_pem=SecretStr("synthetic-public"),
    )
    assert "synthetic-private" not in repr(material) and not hasattr(material, "model_dump")
    with pytest.raises(ValueError):
        SigningKeyVersion.model_validate(
            c.version.model_copy(update={"target": c.commands[1].target})
        )


# A replacement must be a distinct exact-version successor of this principal and credential.
@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 1),
        ("credential_id", uuid4()),
        ("secret_reference", "different"),
        ("secret_version", "original-version"),
        ("fingerprint", ":".join(["ab"] * 16)),
        ("material_created_at", None),
        ("target", None),
    ],
)
def test_replacement_scope(field, value):
    c = rotation_case()
    if field == "material_created_at":
        value = c.version.material_created_at - timedelta(seconds=1)
    if field == "target":
        value = c.candidate.target.model_copy(update={"user_name": "someone-else"})
    candidate = c.candidate.model_copy(update={field: value})
    with pytest.raises(ValueError):
        SigningKeyReplacement(context=c.command.context, old=c.old, candidate=candidate)
    with pytest.raises(ValueError):
        SigningKeyReplacement(
            context=c.command.context.model_copy(update={"workspace_id": "other"}),
            old=c.old,
            candidate=c.candidate,
        )


# Every required capability is independently qualified; no old version or stale connection suffices.
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "version",
        "context",
        "complete",
        "oci_identity",
        "identity_domain_administration",
        "root_configuration",
        "old_time",
        "future_time",
        "slow",
        "expired_material",
    ],
)
def test_independent_probe(damage):
    c = rotation_case()
    probe = c.probe
    at = c.clock()
    end = at
    if damage in {
        "complete",
        "oci_identity",
        "identity_domain_administration",
        "root_configuration",
    }:
        probe = probe.model_copy(update={damage: False})
    if damage == "version":
        probe = probe.model_copy(update={"version": c.version})
    if damage == "context":
        probe = probe.model_copy(
            update={"context": c.command.context.model_copy(update={"connection_revision": 2})}
        )
    if damage in {"old_time", "future_time"}:
        probe = probe.model_copy(
            update={"checked_at": at + timedelta(seconds=-1 if damage == "old_time" else 1)}
        )
    if damage == "slow":
        end += timedelta(seconds=31)
    if damage == "expired_material":
        at += timedelta(days=30)
        end = at
        probe = probe.model_copy(update={"checked_at": at})
    assert qualified_signer(probe, c.candidate, c.command.context, at, end) == (damage is None)


# Complete actual-subject enumeration is mandatory even when proving old-key absence.
@pytest.mark.parametrize("damage", [None, "authorized", "complete", "supported", "user"])
def test_inventory_scope(damage):
    c = rotation_case()
    facts = c.facts
    if damage in {"authorized", "complete", "supported"}:
        facts = facts.model_copy(update={damage: False})
    if damage == "user":
        facts = facts.model_copy(update={"user": c.source.recovery})
    assert inventory_matches(facts, c.a) == (damage is None)


# A current-pointer switch alone, an absent replacement or uncertain enumeration is not retirement.
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "old_id",
        "old_fingerprint",
        "replacement_absent",
        "inactive",
        "unknown_time",
        "future",
        "before_material",
        "partial",
    ],
)
def test_retirement_evidence(damage):
    c = rotation_case()
    candidate = c.key.model_copy(
        update={
            "provider_key_id": "replacement-key",
            "fingerprint": c.candidate.fingerprint,
            "created_at": c.clock(),
        }
    )
    keys = (candidate,)
    if damage == "old_id":
        keys += (c.key.model_copy(update={"fingerprint": ":".join(["ef"] * 16)}),)
    if damage == "old_fingerprint":
        keys += (c.key.model_copy(update={"provider_key_id": "old-alias"}),)
    if damage == "replacement_absent":
        keys = ()
    if damage == "inactive":
        keys = (candidate.model_copy(update={"state": "inactive"}),)
    if damage in {"unknown_time", "future", "before_material"}:
        date = (
            None
            if damage == "unknown_time"
            else c.clock() + timedelta(seconds=1 if damage == "future" else -1)
        )
        keys = (candidate.model_copy(update={"created_at": date}),)
    facts = c.facts.model_copy(update={"keys": keys, "complete": damage != "partial"})
    assert retired_inventory(facts.model_dump(), c.replacement, c.clock()) == (damage is None)


# Historical labels distinguish intent-to-dispatch fences from observed and completed effects.
@pytest.mark.parametrize(
    "phase,upload_sent,retire_sent,expected",
    [
        ("stage", False, False, "Replacement preparation recorded"),
        ("upload", False, False, "Replacement key staged"),
        ("upload", True, False, "Public-key upload authorized; verification pending"),
        ("verify", True, False, "Replacement public key observed"),
        ("activate", True, False, "Replacement signer verified"),
        ("retire", True, False, "Replacement activated; old-key retirement pending"),
        ("retire", True, True, "Old-key removal authorized; verification pending"),
        ("complete", True, True, "Old key absent; replacement access verified"),
    ],
)
def test_checkpoint_descriptions(phase, upload_sent, retire_sent, expected):
    from otm.operations.contracts import canonical_hash
    from otm.storage.operation_directory import SqlOperationDirectory
    from otm.tenancies.signing_key_contracts import SigningKeyEvidence
    from otm.tenancies.signing_key_engine import SigningRotationState

    c = rotation_case()
    uploaded = ManagedSigningKey(
        version=c.candidate, provider_key_id="replacement-id", uploaded_at=c.clock()
    )
    checkpoint = SigningRotationState(
        old=c.old,
        phase=phase,
        candidate=c.candidate if phase != "stage" else None,
        uploaded=uploaded if phase in {"verify", "activate", "retire", "complete"} else None,
        upload_dispatched=upload_sent,
        retire_dispatched=retire_sent,
    )
    proof = SigningKeyEvidence(
        operation_id=c.command.context.operation_id,
        credential_id=c.version.credential_id,
        tenancy_id=c.a.tenancy_id,
        phase="rotation",
        state="progress",
        safe_code="SIGNING_KEY_PROGRESS",
        checkpoint=checkpoint,
        checked_at=c.clock(),
    )
    data = proof.model_dump(mode="json")
    projected = SqlOperationDirectory(None).event(
        dict(kind="signing_key_outcome", at=c.clock(), data=data, data_hash=canonical_hash(data))
    )
    assert projected.summary == expected
    assert "secret_reference" not in projected.model_dump_json()


# Terminal, held and old sparse records remain readable without inventing a successful checkpoint.
@pytest.mark.parametrize(
    "state,phase,expected",
    [
        ("verified", "setup", "Automation signer prepared"),
        ("verified", "rotation", "Key rotation completed"),
        ("attention", "setup", "Signing-key setup needs attention"),
        ("attention", "rotation", "Key rotation needs attention"),
        ("cancelled", "rotation", "Signing-key operation cancelled"),
        ("progress", "rotation", "Signing-key progress recorded"),
    ],
)
def test_sparse_signing_event_descriptions(state, phase, expected):
    from otm.tenancies.signing_key_contracts import SigningKeyEvidence, signing_event_summary

    c = rotation_case()
    evidence = SigningKeyEvidence(
        operation_id=uuid4(),
        credential_id=c.version.credential_id,
        tenancy_id=c.a.tenancy_id,
        phase=phase,
        state=state,
        safe_code="SIGNING_KEY_PROGRESS",
        checked_at=c.clock(),
    )
    assert signing_event_summary(evidence) == expected
