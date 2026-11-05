"""Interactive operator-only recovery enrollment/reset; never accept factor values as arguments."""

import argparse
import getpass
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pyotp

from otm.auth.local import LocalAuthFailure, password_verifier, totp_step
from otm.maintenance import maintenance_engine
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings
from otm.storage.local_auth import SqlLocalAuth


# Avoid argparse echoing accidentally supplied passwords or seeds in an invalid command line.
class PrivateParser(argparse.ArgumentParser):
    # Discard parser detail; operator errors must never reflect arbitrary argument values.
    def error(self, message):
        raise ValueError("INVALID_ADMINISTRATOR_ARGUMENTS")


# Require a real interactive terminal, explicit operator credentials and verified MFA before commit.
def main(argv=None) -> int:
    engine = None
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument("operation", choices=["bootstrap", "reset-local"])
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument("--secret-directory", type=Path, required=True)
        args = parser.parse_args(argv)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError("INTERACTIVE_TERMINAL_REQUIRED")
        settings = load_settings(args.config)
        if settings.local_auth is None:
            raise ValueError("LOCAL_AUTH_CONFIGURATION_REQUIRED")
        engine = maintenance_engine(
            os.environ["OTM_DATABASE_URL"], os.environ.get("OTM_DATABASE_CA_FILE")
        )

        # Use aware server UTC for enrollment proof and persisted credential timestamps.
        def clock():
            return datetime.now(UTC)

        repository = SqlLocalAuth(engine, settings, clock)
        existing, operator = repository.operator_status(reset=args.operation == "reset-local")
        # Validate access/existing state before prompting or staging any secret material.
        custody = DirectorySecrets(args.secret_directory)
        password = getpass.getpass("New recovery password (15–128 characters): ")
        if password != getpass.getpass("Confirm recovery password: "):
            raise LocalAuthFailure(400, "INVALID_LOCAL_CREDENTIALS")
        verifier = password_verifier(password)
        seed = pyotp.random_base32()
        reference = custody.put(seed)
        print(
            "Enroll this TOTP secret in your authenticator; do not record or share this terminal:"
        )
        print(seed)
        code = getpass.getpass("Current authenticator code: ")
        step = totp_step(seed, code, clock(), -1)
        if step is None:
            raise LocalAuthFailure(400, "INVALID_LOCAL_CREDENTIALS")
        identifier = repository.enroll(verifier, reference, step, operator, expected=existing)
        print(
            json.dumps(
                {
                    "status": "reset" if existing else "initialized",
                    "administrator_id": str(identifier),
                }
            )
        )
        return 0
    except Exception as error:
        code = (
            error.code
            if isinstance(error, LocalAuthFailure)
            else "LOCAL_ADMINISTRATOR_OPERATION_FAILED"
        )
        print(json.dumps({"code": code}), file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
