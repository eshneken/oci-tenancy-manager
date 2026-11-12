"""Prepare-once local RSA custody, public-only reads and safe retry/failure behavior."""

import hashlib
import json
import stat
import subprocess
from unittest.mock import patch
from uuid import uuid4

import pytest

from otm.providers.bootstrap_keys_local import LocalBootstrapKeys, PublicBootstrapKey


# Each test explicitly selects a disposable owner-only root, never the saved application.
@pytest.fixture
def keys(tmp_path):
    directory = tmp_path / "keys"
    directory.mkdir(mode=0o700)
    return LocalBootstrapKeys(directory), directory


# A read-only public GET cannot allocate material; preparation produces stable matching RSA PEM.
def test_public_only_preparation_and_restart(keys):
    store, directory = keys
    operation = uuid4()
    assert store.public("workspace", operation) is None
    store.prepare("workspace", operation)
    public = store.public("workspace", operation)
    assert public.startswith("-----BEGIN PUBLIC KEY-----\n")
    assert "PRIVATE" not in public
    store.prepare("workspace", operation)
    assert LocalBootstrapKeys(directory).public("workspace", operation) == public
    assert store.public("other-workspace", operation) is None
    assert store.public("workspace", uuid4()) is None
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())
    # Public lookup reads only the public record, even when private material cannot be accessed.
    with patch.object(store.records, "read", wraps=store.records.read) as read:
        assert store.public("workspace", operation) == public
    assert all(call.args[1].endswith(".public.json") for call in read.call_args_list)


# If a process stops between writes, explicit retry derives the public half from retained custody.
def test_private_first_crash_recovery_and_orphan_rejection(keys):
    store, directory = keys
    operation = uuid4()
    store.prepare("workspace", operation)
    name = store.name("workspace", operation)
    original = store.public("workspace", operation)
    private_hash = hashlib.sha256((directory / (name + ".private.json")).read_bytes()).hexdigest()
    (directory / (name + ".public.json")).unlink()
    assert store.public("workspace", operation) is None
    store.prepare("workspace", operation)
    assert store.public("workspace", operation) == original
    assert (
        hashlib.sha256((directory / (name + ".private.json")).read_bytes()).hexdigest()
        == private_hash
    )
    (directory / (name + ".private.json")).unlink()
    with pytest.raises(ValueError, match="BOOTSTRAP_KEY_CUSTODY_CHANGED"):
        store.prepare("workspace", operation)
    assert not (directory / (name + ".private.json")).exists()


# Scope/content substitution fails closed rather than replacing an existing key or reflecting it.
@pytest.mark.parametrize(
    "damage",
    [
        "private_scope",
        "public_scope",
        "public_changed",
        "private_corrupt",
        "permissions",
        "symlink",
    ],
)
def test_custody_tampering_is_rejected(keys, damage):
    store, directory = keys
    operation = uuid4()
    store.prepare("workspace", operation)
    name = store.name("workspace", operation)
    target = directory / (
        name
        + (".private.json" if damage in {"private_scope", "private_corrupt"} else ".public.json")
    )
    if damage == "permissions":
        target.chmod(0o644)
    elif damage == "symlink":
        linked = directory / "retained.json"
        target.rename(linked)
        target.symlink_to(linked)
    else:
        value = json.loads(target.read_text())
        if damage in {"private_scope", "public_scope"}:
            value["workspace"] = "foreign"
        elif damage == "private_corrupt":
            value["private_pem"] = "invalid" * 30
        else:
            value["public_pem"] = value["public_pem"].replace("M", "N", 1)
        target.write_text(json.dumps(value))
    with pytest.raises((ValueError, OSError)):
        if damage in {"permissions", "symlink", "public_scope"}:
            store.public("workspace", operation)
        else:
            store.prepare("workspace", operation)


# An unavailable tool, unsafe root or failed/oversized process output never leaks private bytes.
def test_tool_and_input_guards(keys):
    store, directory = keys
    with (
        patch("otm.providers.bootstrap_keys_local.shutil.which", return_value=None),
        pytest.raises(ValueError, match="BOOTSTRAP_OPENSSL_UNAVAILABLE"),
    ):
        LocalBootstrapKeys(directory)
    with pytest.raises(ValueError):
        store.name("", uuid4())
    with pytest.raises(ValueError):
        store.name("workspace", "not-uuid")
    for result in [
        subprocess.CompletedProcess([], 1, b"redacted"),
        subprocess.CompletedProcess([], 0, b""),
        subprocess.CompletedProcess([], 0, b"x" * 16385),
        subprocess.CompletedProcess([], 0, b"\xff"),
    ]:
        with (
            patch("otm.providers.bootstrap_keys_local.subprocess.run", return_value=result),
            pytest.raises(ValueError, match="BOOTSTRAP_KEY_PREPARATION_FAILED"),
        ):
            store.openssl(["pkey"])
    with (
        patch(
            "otm.providers.bootstrap_keys_local.subprocess.run",
            side_effect=subprocess.TimeoutExpired("openssl", 10),
        ),
        pytest.raises(ValueError, match="BOOTSTRAP_KEY_PREPARATION_FAILED"),
    ):
        store.openssl(["pkey"])
    with pytest.raises(ValueError):
        PublicBootstrapKey(workspace="w", operation_id=uuid4(), public_pem="not-public" * 20)
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        LocalBootstrapKeys(directory)
