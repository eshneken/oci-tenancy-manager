"""Explicit laptop-only RSA handoff material; no OCI credentials are installed or tested here."""

import hashlib
import json
import shutil

# Local adapter runs fixed OpenSSL argv without a shell, secrets only through captured pipes.
import subprocess  # nosec B404
from uuid import UUID

from pydantic import Field, SecretStr, model_validator

from otm.contracts import Contract, Text
from otm.providers.bootstrap_keys import BootstrapKeys
from otm.secrets.private_json import PrivateJsonRecords


# The public projection cannot carry private material or select another operation's key.
class PublicBootstrapKey(Contract):
    workspace: Text
    operation_id: UUID
    public_pem: str = Field(min_length=100, max_length=2048)

    # Reject private/SSH text before any browser response can expose malformed custody content.
    @model_validator(mode="after")
    def public_only(self):
        if (
            not self.public_pem.startswith("-----BEGIN PUBLIC KEY-----\n")
            or not self.public_pem.endswith("-----END PUBLIC KEY-----\n")
            or "PRIVATE" in self.public_pem
        ):
            raise ValueError("BOOTSTRAP_PUBLIC_KEY_INVALID")
        return self


# Private JSON is bounded, redacted in representations, and never returned through the API.
class PrivateBootstrapKey(Contract):
    workspace: Text
    operation_id: UUID
    private_pem: SecretStr = Field(min_length=100, max_length=8192, repr=False)


# This adapter is explicitly selected by laptop composition, not a production Vault fallback.
class LocalBootstrapKeys(BootstrapKeys):
    # The host must precreate owner-only custody; no default directory or implicit fallback exists.
    def __init__(self, directory):
        self.records = PrivateJsonRecords(directory)
        self.executable = shutil.which("openssl")
        if not self.executable:
            raise ValueError("BOOTSTRAP_OPENSSL_UNAVAILABLE")

    # Exact server identities form bounded names; neither employee input nor paths reach OpenSSL.
    def name(self, workspace, operation_id):
        if not isinstance(workspace, str) or not workspace or not isinstance(operation_id, UUID):
            raise ValueError("BOOTSTRAP_SCOPE_INVALID")
        return hashlib.sha256(workspace.encode()).hexdigest()[:32] + "-" + operation_id.hex

    # Fixed argv and stdin-only material prevent shell/argument leakage; all errors are normalized.
    def openssl(self, arguments, material=None):
        try:
            result = subprocess.run(  # nosec B603
                [self.executable, *arguments],
                input=material,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            if result.returncode or not 0 < len(result.stdout) <= 16384:
                raise ValueError("BOOTSTRAP_KEY_PREPARATION_FAILED")
            return result.stdout.decode("ascii")
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise ValueError("BOOTSTRAP_KEY_PREPARATION_FAILED") from None

    # Explicit retry derives missing public metadata from the retained private key.
    def prepare(self, workspace, operation_id):
        name = self.name(workspace, operation_id)
        with self.records.locked(name) as directory:
            try:
                key = PrivateBootstrapKey.model_validate_json(
                    json.dumps(self.records.read(directory, name + ".private.json"))
                )
            except FileNotFoundError:
                # An orphan public record cannot authorize replacement of a lost private key.
                try:
                    self.records.read(directory, name + ".public.json")
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("BOOTSTRAP_KEY_CUSTODY_CHANGED") from None
                key = PrivateBootstrapKey(
                    workspace=workspace,
                    operation_id=operation_id,
                    private_pem=self.openssl(
                        ["genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"]
                    ),
                )
                self.records.write(
                    directory,
                    name + ".private.json",
                    {
                        "workspace": workspace,
                        "operation_id": str(operation_id),
                        "private_pem": key.private_pem.get_secret_value(),
                    },
                )
            if key.workspace != workspace or key.operation_id != operation_id:
                raise ValueError("BOOTSTRAP_KEY_SCOPE_CHANGED")
            public = self.openssl(["pkey", "-pubout"], key.private_pem.get_secret_value().encode())
            details = self.openssl(["pkey", "-pubin", "-text", "-noout"], public.encode())
            if "(2048 bit)" not in details or "Modulus:" not in details:
                raise ValueError("BOOTSTRAP_RSA_KEY_REQUIRED")
            value = PublicBootstrapKey(
                workspace=workspace, operation_id=operation_id, public_pem=public
            )
            try:
                retained = PublicBootstrapKey.model_validate_json(
                    json.dumps(self.records.read(directory, name + ".public.json"))
                )
            except FileNotFoundError:
                self.records.write(directory, name + ".public.json", value.model_dump(mode="json"))
            else:
                if retained != value:
                    raise ValueError("BOOTSTRAP_KEY_CUSTODY_CHANGED")

    # Public GETs touch only public JSON, never private JSON or the allocation/generation path.
    def public(self, workspace, operation_id):
        name = self.name(workspace, operation_id)
        with self.records.locked(name + ".public") as directory:
            try:
                value = PublicBootstrapKey.model_validate_json(
                    json.dumps(self.records.read(directory, name + ".public.json"))
                )
            except FileNotFoundError:
                return None
        if value.workspace != workspace or value.operation_id != operation_id:
            raise ValueError("BOOTSTRAP_KEY_SCOPE_CHANGED")
        return value.public_pem
