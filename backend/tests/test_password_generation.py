"""Default-compatible recovery candidates preserve entropy, explicit classes and old custody."""

import secrets
from unittest.mock import patch
from uuid import uuid4

from test_recovery_password_custody import custody

from otm.providers.password_generation import (
    ALPHABET,
    GROUPS,
    generate_recovery_password,
    valid_generated_password,
)

__all__ = ["custody"]


# Repeated real generation always satisfies length, four character classes and the safe alphabet.
def test_generated_password_template():
    for _ in range(32):
        value = generate_recovery_password("otm-recovery")
        valid = valid_generated_password(value, "otm-recovery")
        assert valid and len(value) == 32
        assert all(any(character in group for character in value) for group in GROUPS)
        assert set(value) <= set(ALPHABET)
    assert not valid_generated_password("x" * 32, "otm-recovery")
    assert not valid_generated_password(None, "otm-recovery")


# Fisher-Yates uses every bounded cryptographic draw; exclusion failure has a fixed diagnostic.
def test_shuffle_bounds_and_exclusion():
    with patch(
        "otm.providers.password_generation.secrets.randbelow", side_effect=lambda bound: bound - 1
    ) as draw:
        value = generate_recovery_password("")
    assert valid_generated_password(value, "")
    assert [call.args[0] for call in draw.call_args_list] == list(range(32, 1, -1))
    with (
        patch(
            "otm.providers.password_generation.secrets.choice", side_effect=lambda group: group[0]
        ),
        patch(
            "otm.providers.password_generation.secrets.randbelow",
            side_effect=lambda bound: bound - 1,
        ),
    ):
        import pytest

        with pytest.raises(ValueError, match="RECOVERY_PASSWORD_GENERATION_UNAVAILABLE"):
            generate_recovery_password("aA")


# Previously issued 54-character simulator versions remain byte-stable on replay/current reads.
def test_legacy_candidate_current_and_new_rotation(custody):
    vault, location, _ = custody
    operation = uuid4()
    reference = vault.stage(location, operation)
    with vault.locked(location) as (directory, name):
        filename = name + ".version." + operation.hex
        value = vault.read(directory, filename)
        value["password"] = "aA1!" + secrets.token_urlsafe(37)
        vault.write(directory, filename, value, replace=True)
    legacy = vault.candidate(reference)
    assert len(legacy.password.get_secret_value()) == 54
    assert vault.stage(location, operation) == reference
    vault.promote(reference, None)
    assert vault.current(location).password == legacy.password
    newer = vault.stage(location, uuid4())
    assert len(vault.candidate(newer).password.get_secret_value()) == 32
