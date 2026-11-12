"""Private local custody preserves exact references, CURRENT semantics and independent effects."""

import json
import os
import stat
from uuid import uuid4

import pytest
from pydantic import SecretStr

from otm.providers.recovery_password import PasswordLocation, PasswordMaterial
from otm.providers.recovery_password_simulator import (
    PasswordCustodyUnavailable,
    SimulatedRecoveryPasswords,
)
from otm.providers.required_user_contracts import RequiredUserReadContext, RequiredUserTarget


# Each case owns its private local custody and exact synthetic recovery identity.
@pytest.fixture
def custody(tmp_path):
    directory = tmp_path.resolve() / "passwords"
    directory.mkdir(mode=0o700)
    location = PasswordLocation(
        credential_id=(identifier := uuid4()),
        secret_reference="sim-recovery:" + identifier.hex,
        target=RequiredUserTarget(
            workspace_id="password-lab",
            tenancy_id=uuid4(),
            purpose="recovery",
            subject_binding_id=uuid4(),
            binding_generation=1,
            identity_domain_binding_id=uuid4(),
            domain_ocid="ocid1.domain.oc1..otmsimpassword",
            scim_resource_id="recovery-scim",
            provider_ocid="ocid1.user.oc1..otmsimrecovery",
            user_name="otm-recovery",
            organization_id="password-org",
            parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
            tenancy_ocid="ocid1.tenancy.oc1..otmsimpasswordchild",
        ),
    )
    return SimulatedRecoveryPasswords(directory), location, directory


# Staging is idempotent and private; independent child verification precedes CURRENT promotion.
def test_private_candidate_current_and_independent_child(custody):
    vault, location, directory = custody
    operation = uuid4()
    first = vault.stage(location, operation)
    assert vault.stage(location, operation) == first
    material = vault.candidate(first)
    assert isinstance(material.password, SecretStr)
    assert len(material.password.get_secret_value()) == 32
    assert material.password.get_secret_value() not in repr(material)
    assert material.password.get_secret_value() not in first.model_dump_json()
    with pytest.raises(PasswordCustodyUnavailable):
        vault.current(location)
    with pytest.raises(PasswordCustodyUnavailable):
        verify(vault, material)
    assert change(vault, material).effect == "known"
    assert verify(vault, material)
    vault.promote(first, None)
    vault.promote(first, None)
    assert vault.current(location).reference == first
    second = vault.stage(location, uuid4())
    assert vault.current(location).reference == first
    newer = vault.candidate(second)
    assert not verify(vault, newer)
    change(vault, newer)
    assert verify(vault, newer) and not verify(vault, material)
    vault.promote(second, first.version)
    assert vault.current(location).reference == second
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in directory.iterdir())


# Each credential has independent material even when one operation provisions several children.
def test_unique_locations_and_conditional_promotion(custody):
    vault, location, _ = custody
    operation = uuid4()
    first = vault.stage(location, operation)
    other_id = uuid4()
    other = location.model_copy(
        update={
            "credential_id": other_id,
            "secret_reference": "sim-recovery:" + other_id.hex,
            "target": location.target.model_copy(update={"tenancy_id": uuid4()}),
        }
    )
    second = vault.stage(other, operation)
    assert vault.candidate(first).password != vault.candidate(second).password
    vault.promote(first, None)
    future = vault.stage(location, uuid4())
    with pytest.raises(PasswordCustodyUnavailable):
        vault.promote(future, "unrelated-version")
    assert vault.current(location).reference == first


# Neither a different user nor a substituted transient password may reuse an existing secret.
def test_exact_scope_and_candidate_guards(custody):
    vault, location, _ = custody
    ref = vault.stage(location, uuid4())
    changed = location.model_copy(
        update={"target": location.target.model_copy(update={"scim_resource_id": "someone-else"})}
    )
    with pytest.raises(PasswordCustodyUnavailable):
        vault.stage(changed, ref.operation_id)
    with pytest.raises(PasswordCustodyUnavailable):
        vault.candidate(ref.model_copy(update={"location": changed}))
    material = PasswordMaterial(ref, SecretStr("not-the-staged-password"))
    assert change(vault, material).effect == "none"
    with pytest.raises(PasswordCustodyUnavailable):
        vault.candidate(ref.model_copy(update={"operation_id": uuid4()}))
    with pytest.raises(PasswordCustodyUnavailable):
        vault.candidate(ref.model_copy(update={"version": "../outside"}))


# Local simulation cannot be pointed at real tenancy references or arbitrary secret paths.
@pytest.mark.parametrize("fault", ["real", "reference", "kind"])
def test_wrong_location_is_rejected(custody, fault):
    vault, location, _ = custody
    if fault == "real":
        location = location.model_copy(
            update={
                "target": location.target.model_copy(
                    update={"tenancy_ocid": "ocid1.tenancy.oc1..real"}
                )
            }
        )
    elif fault == "reference":
        location = location.model_copy(update={"secret_reference": "../../outside"})
    else:
        with pytest.raises(ValueError):
            location.model_copy(
                update={"target": location.target.model_copy(update={"purpose": "automation"})}
            ).__class__.model_validate(
                location.model_copy(
                    update={"target": location.target.model_copy(update={"purpose": "automation"})}
                )
            )
        return
    with pytest.raises(PasswordCustodyUnavailable):
        vault.stage(location, uuid4())


# Immutable version contents are bounded and must retain their original exact scope and shape.
@pytest.mark.parametrize("fault", ["scope", "shape", "password", "version", "oversize", "array"])
def test_corrupted_private_version_is_unavailable(custody, fault):
    vault, location, directory = custody
    ref = vault.stage(location, uuid4())
    path = directory / (location.credential_id.hex + ".version." + ref.version)
    data = json.loads(path.read_text())
    if fault == "scope":
        data["scope"] = "wrong"
    elif fault == "shape":
        data["extra"] = "not-allowed"
    elif fault == "password":
        data["password"] = "short"
    elif fault == "version":
        data["version"] = uuid4().hex
    elif fault == "oversize":
        path.write_text(" " * 16385)
    else:
        data = []
    if fault != "oversize":
        path.write_text(json.dumps(data))
    with pytest.raises(PasswordCustodyUnavailable):
        vault.candidate(ref)


# Unsafe file metadata never authorizes following links, reading devices or exposing credentials.
@pytest.mark.parametrize("fault", ["mode", "symlink", "hardlink", "lock_mode"])
def test_private_file_and_lock_custody(custody, fault):
    vault, location, directory = custody
    ref = vault.stage(location, uuid4())
    path = directory / (location.credential_id.hex + ".version." + ref.version)
    if fault == "mode":
        path.chmod(0o644)
    elif fault == "symlink":
        target = directory / "original"
        path.rename(target)
        path.symlink_to(target)
    elif fault == "hardlink":
        os.link(path, directory / "second-link")
    else:
        (directory / (location.credential_id.hex + ".lock")).chmod(0o644)
    with pytest.raises(PasswordCustodyUnavailable):
        vault.candidate(ref)


# CURRENT corruption never falls back to an older immutable candidate or manufactures a stage.
@pytest.mark.parametrize("fault", ["scope", "shape", "uuid", "missing_version"])
def test_invalid_current_has_no_historical_fallback(custody, fault):
    vault, location, directory = custody
    ref = vault.stage(location, uuid4())
    vault.promote(ref, None)
    pointer = directory / (location.credential_id.hex + ".current")
    data = json.loads(pointer.read_text())
    if fault == "scope":
        data["scope"] = "wrong"
    elif fault == "shape":
        data["extra"] = True
    elif fault == "uuid":
        data["version"] = "invalid"
    else:
        data["version"] = uuid4().hex
    pointer.write_text(json.dumps(data))
    with pytest.raises(PasswordCustodyUnavailable):
        vault.current(location)
    if fault in {"scope", "shape"}:
        with pytest.raises(PasswordCustodyUnavailable):
            vault.promote(ref, None)


# A missing or permissive directory is never created or adopted by a read/write adapter.
def test_directory_must_be_explicit_and_private(tmp_path):
    root = tmp_path.resolve() / "private"
    with pytest.raises(FileNotFoundError):
        SimulatedRecoveryPasswords(root)
    root.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        SimulatedRecoveryPasswords(root)


# Synthetic target calls use explicit nonsecret operation/connection context, never a password
# signer.
def context_for(material):
    reference = material.reference
    return RequiredUserReadContext(
        workspace_id=reference.location.target.workspace_id,
        operation_id=reference.operation_id,
        step_key="recovery_password:" + str(reference.location.credential_id),
        attempt_id=reference.operation_id,
        intent_revision=1,
        execution_generation=1,
        connection_id=reference.location.target.subject_binding_id,
        connection_revision=1,
    )


# Keep target-write tests explicit about the independently supplied machine context.
def change(vault, material):
    return vault.change(material, context_for(material))


# Readback must use the same exact dispatch context rather than a current or unrelated signer.
def verify(vault, material):
    return vault.verify(material, context_for(material))
