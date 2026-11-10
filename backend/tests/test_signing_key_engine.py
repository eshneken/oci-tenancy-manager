"""Recoverable signing transitions use independent local provider facts and private custody."""

import json
import os
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from test_signing_key_rotation import rotation_case

from otm.providers.administrator_access_simulator import configured_administrator_capture
from otm.providers.automation_keys import ObservedAutomationKey
from otm.providers.automation_keys_simulator import SimulatedAutomationKeys
from otm.providers.signing_key_rotation import SigningKeyMaterial, SigningKeyMutation
from otm.providers.signing_key_rotation_simulator import SimulatedSigningKeys
from otm.tenancies.signing_key_engine import (
    SigningKeyRotationEngine,
    SigningRotationBlocked,
    SigningRotationState,
)


# Actual private records and public inventory remain separate; synthetic material cannot log in.
@pytest.fixture
def simulation(tmp_path):
    c = rotation_case()
    c.a = c.a.model_copy(update={"tenancy_ocid": "ocid1.tenancy.oc1..otmsimunit"})
    c.target = c.a
    c.context = c.command.context
    c.inventory = SimulatedAutomationKeys(tmp_path / "inventory", c.clock)
    c.inventory.configure(
        c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation, empty=True
    )
    directory = tmp_path / "custody"
    directory.mkdir(mode=0o700)
    c.provider = SimulatedSigningKeys(directory, c.inventory, c.clock)
    c.capture = configured_administrator_capture(c.a.domain_ocid, c.a.scim_resource_id, "unit")
    c.enrollment_id = uuid4()
    c.credential_id = uuid4()
    c.old = c.provider.enroll(c.a, c.credential_id, c.enrollment_id, c.capture, c.context)
    c.clock.return_value += timedelta(seconds=1)
    c.machine = SigningKeyRotationEngine(c.provider, c.provider, c.clock)
    c.saved = []

    # The engine only proceeds after its host durably accepts a checkpoint.
    def checkpoint(value):
        c.saved.append(value)
        return True

    c.checkpoint = checkpoint
    c.activation = Mock(side_effect=checkpoint)
    c.state = SigningRotationState(old=c.old)
    return c


# Repeat stage/setup after a lost response preserves exact material and its original age.
def test_durable_material_and_original_deadline(simulation):
    c = simulation
    candidate = c.provider.stage(c.old, c.context)
    material = c.provider.material(candidate)
    c.clock.return_value += timedelta(minutes=2)
    assert c.provider.stage(c.old, c.context) == candidate
    assert c.provider.material(candidate) == material
    assert "simulated-key-material" not in repr(material)
    original = c.provider.enroll(c.a, c.credential_id, c.enrollment_id, c.capture, c.context)
    assert original == c.old
    assert original.retire_at == c.old.retire_at
    with pytest.raises(ValueError, match="CUSTODY_CHANGED"):
        c.provider.material(candidate.model_copy(update={"fingerprint": ":".join(["ef"] * 16)}))
    changed = SigningKeyMaterial(candidate, SecretStr("changed"), material.public_pem)
    with pytest.raises(ValueError, match="CUSTODY_CHANGED"):
        c.provider.require_material(changed, c.context)
    with pytest.raises(ValueError, match="SCOPE_INVALID"):
        c.provider.scope(c.a.model_copy(update={"purpose": "recovery"}))


# Full execution separately proves upload, activation, old absence and replacement capability.
def test_complete_rotation_and_repeated_retirement(simulation):
    c = simulation
    for _ in range(8):
        c.state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    assert c.state.phase == "complete"
    assert c.state.upload_dispatched and c.state.retire_dispatched
    assert c.activation.call_count == 1
    material = c.provider.material(c.state.candidate)
    c.provider.retire(c.old, material, c.context)
    facts = c.provider.inventory(material, c.context)
    assert [key.fingerprint for key in facts.keys] == [c.state.candidate.fingerprint]
    with pytest.raises(ValueError, match="CURRENT_UNVERIFIED"):
        c.provider.inventory(c.provider.material(c.old.version), c.context)
    assert c.machine.step(c.state, c.context, c.checkpoint, c.activation) == c.state
    assert all("simulated-key-material" not in value.model_dump_json() for value in c.saved)


# Lost upload responses reconcile the already uploaded fingerprint instead of another pair/write.
def test_lost_upload_response_reconciles_candidate(simulation, monkeypatch):
    c = simulation
    state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    original = c.provider.upload

    # The provider commits its effect before the caller loses acknowledgement.
    def lose_response(*args):
        original(*args)
        raise OSError("synthetic transport loss")

    monkeypatch.setattr(c.provider, "upload", lose_response)
    with pytest.raises(OSError):
        c.machine.step(state, c.context, c.checkpoint, c.activation)
    held = c.saved[-1]
    assert held.upload_dispatched
    monkeypatch.setattr(c.provider, "upload", Mock(side_effect=AssertionError("must not reupload")))
    reconciled = c.machine.step(held, c.context, c.checkpoint, c.activation)
    assert reconciled.phase == "verify" and reconciled.candidate == state.candidate


# An absent candidate after an uncertain upload is not proof of no effect or permission to resend.
@pytest.mark.parametrize("effect", ["none", "unknown"])
def test_no_effect_and_unknown_absence_differ(simulation, monkeypatch, effect):
    c = simulation
    state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    upload = Mock(return_value=SigningKeyMutation(effect=effect))
    monkeypatch.setattr(c.provider, "upload", upload)
    if effect == "none":
        with pytest.raises(SigningRotationBlocked, match="UPLOAD_UNRECONCILED"):
            c.machine.step(state, c.context, c.checkpoint, c.activation)
        assert not c.saved[-1].upload_dispatched
    else:
        state = c.machine.step(state, c.context, c.checkpoint, c.activation)
        with pytest.raises(SigningRotationBlocked, match="UPLOAD_UNRECONCILED"):
            c.machine.step(state, c.context, c.checkpoint, c.activation)
    assert upload.call_count == 1


# Unknown public slots require human review; no unrelated key is deleted to obtain capacity.
def test_unknown_slots_are_preserved(simulation):
    c = simulation
    state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    extra = ObservedAutomationKey(
        provider_key_id="unmanaged",
        fingerprint=":".join(["ef"] * 16),
        created_at=c.clock(),
        state="active",
    )
    c.provider.mutate(c.a, lambda keys: (*keys, extra))
    with pytest.raises(SigningRotationBlocked, match="SLOT_REVIEW"):
        c.machine.step(state, c.context, c.checkpoint, c.activation)
    facts = c.provider.inventory(c.provider.material(c.old.version), c.context)
    assert extra in facts.keys and len(facts.keys) == 2


# Changed capabilities fail exact candidate qualification even when the public key is present.
@pytest.mark.parametrize("damage", ["group", "root", "target"])
def test_probe_rejects_changed_profile(simulation, damage):
    c = simulation
    name = c.credential_id.hex + ".profile.json"
    with c.provider.records.locked(name) as directory:
        value = c.provider.records.read(directory, name)
        if damage == "group":
            value["administrator"]["facts"]["group_members"] = []
        elif damage == "root":
            value["root_configuration"] = False
        else:
            value["target"]["user_name"] = "other"
        c.provider.records.write(directory, name, value, replace=True)
    with pytest.raises((SigningRotationBlocked, ValueError)):
        c.machine.probe(c.old.version, c.context)


# Persistence refusal and a lost activation CAS cannot advance provider state or retire the old key.
def test_host_fences_and_expired_material(simulation):
    c = simulation
    with pytest.raises(SigningRotationBlocked, match="CONTEXT_CHANGED"):
        c.machine.step(c.state, c.context, lambda state: False, c.activation)
    for _ in range(4):
        c.state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    assert c.state.phase == "activate"
    with pytest.raises(SigningRotationBlocked, match="CONTEXT_CHANGED"):
        c.machine.step(c.state, c.context, c.checkpoint, lambda state: False)
    c.clock.return_value = c.state.candidate.material_created_at + timedelta(days=30)
    with pytest.raises(SigningRotationBlocked, match="PROBE_FAILED"):
        c.machine.probe(c.state.candidate, c.context)


# Custody rejects substituted reference locations and invalid or overbroad file permissions.
def test_private_record_boundary(simulation, tmp_path):
    c = simulation
    from otm.secrets.private_json import PrivateJsonRecords

    records = c.provider.records
    for invalid in ["../key", "KEY", "a/b", "", 1]:
        with pytest.raises(ValueError, match="NAME_INVALID"):
            records.name(invalid)
    with records.locked("unit.json") as directory:
        records.write(directory, "unit.json", {"known": True})
        with pytest.raises(FileExistsError):
            records.write(directory, "unit.json", {"known": False})
        assert records.read(directory, "unit.json") == {"known": True}
        with pytest.raises(ValueError, match="TOO_LARGE"):
            records.write(directory, "large.json", {"large": "x" * 16385})
    path = (
        c.provider.records.guard.directory / "unit.json"
        if hasattr(c.provider.records.guard, "directory")
        else tmp_path / "custody" / "unit.json"
    )
    path.chmod(0o644)
    with records.locked("unit.json") as directory:
        with pytest.raises(ValueError, match="FILE_INVALID"):
            records.read(directory, "unit.json")
    path.chmod(0o600)
    path.write_text(json.dumps([]))
    with records.locked("unit.json") as directory:
        with pytest.raises(ValueError, match="RECORD_INVALID"):
            records.read(directory, "unit.json")
    path.write_text(" " * 16385)
    with records.locked("unit.json") as directory:
        with pytest.raises(ValueError, match="TOO_LARGE"):
            records.read(directory, "unit.json")
    path.unlink()
    os.symlink(tmp_path / "not-present", path)
    with records.locked("unit.json") as directory:
        with pytest.raises(OSError):
            records.read(directory, "unit.json")
    with pytest.raises((OSError, ValueError)):
        PrivateJsonRecords(path)


# Lost retirement acknowledgement completes from independent absence without another delete.
def test_retire_unknown_effect_reconciles_original(simulation, monkeypatch):
    c = simulation
    for _ in range(5):
        c.state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    assert c.state.phase == "retire"
    original = c.provider.retire

    # A committed deletion with a lost response must remain recoverable from public inventory.
    def lost(*args):
        original(*args)
        raise OSError("synthetic lost reply")

    monkeypatch.setattr(c.provider, "retire", lost)
    with pytest.raises(OSError):
        c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    held = c.saved[-1]
    monkeypatch.setattr(c.provider, "retire", Mock(side_effect=AssertionError("must not resend")))
    assert c.machine.step(held, c.context, c.checkpoint, c.activation).phase == "complete"


# Contract-violating custody, incomplete inventory and changed authority fail before unsafe writes.
@pytest.mark.parametrize(
    "damage",
    [
        "workspace",
        "candidate_missing",
        "candidate_future",
        "custody",
        "partial",
        "old_absent",
        "inactive_candidate",
        "retire_no_effect",
    ],
)
def test_provider_contract_negative_paths(simulation, monkeypatch, damage):
    c = simulation
    if damage == "workspace":
        with pytest.raises(SigningRotationBlocked):
            c.machine.step(
                c.state,
                c.context.model_copy(update={"workspace_id": "different"}),
                c.checkpoint,
                c.activation,
            )
    elif damage == "candidate_missing":
        with pytest.raises(SigningRotationBlocked):
            c.machine.replacement(c.state, c.context)
    elif damage == "candidate_future":
        candidate = c.provider.stage(c.old, c.context).model_copy(
            update={"material_created_at": c.clock() + timedelta(seconds=1)}
        )
        monkeypatch.setattr(c.provider, "stage", Mock(return_value=candidate))
        with pytest.raises(SigningRotationBlocked):
            c.machine.step(c.state, c.context, c.checkpoint, c.activation)
    elif damage == "custody":
        other = c.provider.material(c.old.version)
        candidate = c.provider.stage(c.old, c.context)
        monkeypatch.setattr(c.provider, "material", Mock(return_value=other))
        with pytest.raises(SigningRotationBlocked):
            c.machine.probe(candidate, c.context)
    else:
        c.state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
        if damage == "partial":
            facts = c.provider.inventory(c.provider.material(c.old.version), c.context).model_copy(
                update={"complete": False}
            )
            monkeypatch.setattr(c.provider, "inventory", Mock(return_value=facts))
        elif damage == "old_absent":
            facts = c.provider.inventory(c.provider.material(c.old.version), c.context).model_copy(
                update={"keys": ()}
            )
            monkeypatch.setattr(c.provider, "inventory", Mock(return_value=facts))
        elif damage == "inactive_candidate":
            c.provider.upload(
                c.provider.material(c.state.candidate),
                c.provider.material(c.old.version),
                c.context,
            )
            c.provider.mutate(
                c.a,
                lambda keys: tuple(
                    key.model_copy(update={"state": "inactive"})
                    if key.fingerprint == c.state.candidate.fingerprint
                    else key
                    for key in keys
                ),
            )
        elif damage == "retire_no_effect":
            for _ in range(4):
                c.state = c.machine.step(c.state, c.context, c.checkpoint, c.activation)
            monkeypatch.setattr(
                c.provider, "retire", Mock(return_value=SigningKeyMutation(effect="none"))
            )
        with pytest.raises(SigningRotationBlocked):
            c.machine.step(c.state, c.context, c.checkpoint, c.activation)


# Incomplete or substituted persisted phase records cannot acquire meaning from field defaults.
def test_invalid_persisted_phase_and_enrollment_profile(simulation):
    c = simulation
    for data in [dict(old=c.old, phase="upload"), dict(old=c.old, uploaded=c.old)]:
        with pytest.raises(ValueError):
            SigningRotationState(**data)
    invalid = c.capture.model_copy(
        update={"binding": c.capture.binding.model_copy(update={"scim_resource_id": "different"})}
    )
    with pytest.raises(ValueError):
        c.provider.enroll(c.a, uuid4(), uuid4(), invalid, c.context)
    with pytest.raises(ValueError):
        c.provider.material(c.old.version.model_copy(update={"secret_reference": "other"}))
    with pytest.raises(ValueError):
        c.provider.allocate(c.a, c.credential_id, 2, c.enrollment_id)
