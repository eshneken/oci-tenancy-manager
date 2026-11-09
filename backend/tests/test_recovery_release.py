"""Private release candidates preserve model semantics and never echo operational CIDRs."""

import stat
import tomllib
from pathlib import Path

import pytest

from otm.recovery_release import render_candidate, settings_toml, toml_value
from otm.release_validation import main, validate_release
from otm.settings import ApplicationSettings, load_settings

CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"


# Rendering all existing optional sections retains exact settings semantics and safe permissions.
def test_render_round_trip_and_private_mode(tmp_path):
    path = tmp_path / "candidate.toml"
    result = render_candidate(CONFIG, path, "198.51.100.0/24,2001:db8::/32")
    assert load_settings(path) == result
    before = load_settings(CONFIG).model_dump(exclude={"recovery_console"})
    assert result.model_dump(exclude={"recovery_console"}) == before
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text().endswith("\n\n")
    assert "# Approved recovery-only" in path.read_text()
    assert "allowed_cidrs" in tomllib.loads(path.read_text())["recovery_console"]


# Existing candidates and symlinks are never followed or replaced, including valid policy changes.
def test_existing_output_and_symlink_stay_untouched(tmp_path):
    path = tmp_path / "candidate.toml"
    path.write_text("preserve")
    with pytest.raises(FileExistsError):
        render_candidate(CONFIG, path, "198.51.100.0/24")
    alias = tmp_path / "alias.toml"
    alias.symlink_to(path)
    with pytest.raises(FileExistsError):
        render_candidate(CONFIG, alias, "198.51.100.0/24")
    assert path.read_text() == "preserve"


# Invalid whole candidates fail before creating any file and preserve an existing valid config.
def test_invalid_policy_never_creates_candidate(tmp_path):
    path = tmp_path / "candidate.toml"
    with pytest.raises(ValueError):
        render_candidate(CONFIG, path, "0.0.0.0/1,128.0.0.0/1")
    assert not path.exists()
    with pytest.raises(ValueError):
        render_candidate(tmp_path / "absent.toml", path, "198.51.100.0/24")
    assert not path.exists()


# Both release kinds require hosted networks; unrelated local functions remain available.
@pytest.mark.parametrize("kind", ["application", "configuration"])
def test_hosted_gate_requires_explicit_boundary(kind):
    path = CONFIG.with_name("production.application.toml")
    assert load_settings(path).recovery_console is None
    with pytest.raises(ValueError, match="RECOVERY_CONSOLE_POLICY_REQUIRED"):
        validate_release(path, "production", kind)
    assert validate_release(CONFIG, "local", kind)["recovery_console_fingerprint"] is None


# The CLI treats variables as data, prints only hashes and performs no deployment.
@pytest.mark.parametrize("kind", ["application", "configuration"])
def test_cli_render_and_safe_receipt(tmp_path, monkeypatch, capsys, kind):
    path = tmp_path / "candidate.toml"
    monkeypatch.setenv("OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS", "198.51.100.0/24,2001:db8::/32")
    assert (
        main(
            [
                "--config",
                str(CONFIG.with_name("production.application.toml")),
                "--expected-environment",
                "production",
                "--release-kind",
                kind,
                "--render-recovery-console-from-env",
                str(path),
            ]
        )
        == 0
    )
    receipt = capsys.readouterr().out
    assert "recovery_console_fingerprint" in receipt
    assert "198.51" not in receipt and "2001:" not in receipt
    assert load_settings(path).environment == "production"


# Missing/malicious inputs and mismatched trusted environments produce fixed errors, never output.
@pytest.mark.parametrize(
    "value", [None, "$(touch /tmp/never)", "198.51.100.1/24", "198.51.100.0/24,"]
)
def test_cli_rejects_private_input_safely(tmp_path, monkeypatch, capsys, value):
    path = tmp_path / "candidate.toml"
    if value is None:
        monkeypatch.delenv("OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS", raising=False)
    else:
        monkeypatch.setenv("OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS", value)
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--expected-environment",
                "local",
                "--release-kind",
                "configuration",
                "--render-recovery-console-from-env",
                str(path),
            ]
        )
        == 1
    )
    assert capsys.readouterr().out == "RELEASE_SETTINGS_REJECTED\n"
    assert not path.exists()


# Rendering text escapes quotes and preserves booleans/numbers rather than injecting TOML tables.
def test_strict_toml_encoder():
    assert toml_value(True) == "true" and toml_value(False) == "false"
    assert toml_value(1) == "1" and toml_value(1.5) == "1.5"
    assert toml_value(['quoted"value', "[not-a-table]"]) == '["quoted\\"value", "[not-a-table]"]'
    with pytest.raises(ValueError):
        toml_value(object())
    settings = load_settings(CONFIG)
    assert ApplicationSettings.model_validate(tomllib.loads(settings_toml(settings))) == settings


# The trusted environment is checked before candidate creation, not after a partial release effect.
def test_cli_wrong_environment_creates_no_file(tmp_path, monkeypatch, capsys):
    path = tmp_path / "candidate.toml"
    monkeypatch.setenv("OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS", "198.51.100.0/24")
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--expected-environment",
                "production",
                "--release-kind",
                "configuration",
                "--render-recovery-console-from-env",
                str(path),
            ]
        )
        == 1
    )
    assert not path.exists()
    assert capsys.readouterr().out == "RELEASE_SETTINGS_REJECTED\n"
