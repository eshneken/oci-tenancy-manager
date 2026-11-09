"""Offline application/configuration release gate using an independently selected target profile."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from otm.settings import load_settings


# The trusted deployment target, not the submitted TOML, selects staging versus production rules.
def validate_release(path, expected_environment, release_kind):
    settings = load_settings(path)
    validate_release_settings(settings, expected_environment, release_kind)
    return {
        "environment": settings.environment,
        "release_kind": release_kind,
        "recovery_console_fingerprint": settings.recovery_console.fingerprint
        if settings.recovery_console
        else None,
        "settings_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "email_policy_hash": settings.mail_policy().fingerprint,
        "email_redirected": settings.testing is not None
        and settings.testing.email_override is not None,
    }


# Reject full candidates before creating private output or requesting any deployment authority.
def validate_release_settings(settings, expected_environment, release_kind):
    if expected_environment not in {"local", "staging", "production"} or release_kind not in {
        "application",
        "configuration",
    }:
        raise ValueError("INVALID_RELEASE_TARGET")
    if settings.environment != expected_environment:
        raise ValueError("RELEASE_ENVIRONMENT_MISMATCH")
    if expected_environment != "local" and settings.local_server is not None:
        raise ValueError("LOCAL_SERVER_FORBIDDEN_IN_HOSTED_RELEASE")
    if (
        expected_environment != "local"
        and settings.notifications.enabled
        and settings.notifications.tls_mode == "local"
    ):
        raise ValueError("HOSTED_SMTP_REQUIRES_TLS")
    if expected_environment != "local" and settings.recovery_console is None:
        raise ValueError("RECOVERY_CONSOLE_POLICY_REQUIRED")


# Both deployment paths run this fail-closed command before cloud credentials or apply are
# available.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--expected-environment", choices=["local", "staging", "production"], required=True
    )
    parser.add_argument("--release-kind", choices=["application", "configuration"], required=True)
    parser.add_argument("--render-recovery-console-from-env", type=Path, metavar="PRIVATE_OUTPUT")
    options = parser.parse_args(argv)
    try:
        path = options.config
        if options.render_recovery_console_from_env is not None:
            from otm.recovery_release import render_candidate

            path = options.render_recovery_console_from_env
            render_candidate(
                options.config,
                path,
                os.environ.get("OTM_RECOVERY_CONSOLE_ALLOWED_CIDRS"),
                validate=lambda candidate: validate_release_settings(
                    candidate, options.expected_environment, options.release_kind
                ),
            )
        result = validate_release(path, options.expected_environment, options.release_kind)
    except Exception:
        print("RELEASE_SETTINGS_REJECTED")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
