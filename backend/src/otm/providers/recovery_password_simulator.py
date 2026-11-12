"""Explicit owner-only laptop custody and independent simulated child password effects."""

import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import SecretStr

from otm.providers.password_generation import generate_recovery_password, valid_generated_password
from otm.providers.recovery_password import (
    PasswordChange,
    PasswordLocation,
    PasswordMaterial,
    PasswordVersion,
)
from otm.providers.required_user_contracts import RequiredUserReadContext
from otm.secrets.directory import DirectorySecrets

MAX_BYTES = 16384


# Fixed diagnostics never embed secret values, filesystem paths, or provider exception text.
class PasswordCustodyUnavailable(ValueError):
    # Expose one closed capability error regardless of the underlying custody failure.
    def __init__(self):
        super().__init__("RECOVERY_PASSWORD_CUSTODY_UNAVAILABLE")


# This adapter is selected explicitly for local simulation; it is not a production Vault fallback.
class SimulatedRecoveryPasswords:
    # Require precreated private custody; GET or a missing cloud adapter never creates directories.
    def __init__(self, directory: Path):
        self.directory = directory
        self.guard = DirectorySecrets(directory)

    # Validate fixed UUID-derived names so no metadata or caller can select a filesystem path.
    def name(self, location):
        PasswordLocation.model_validate(location)
        if (
            not location.target.tenancy_ocid.startswith("ocid1.tenancy.oc1..otmsim")
            or location.secret_reference != "sim-recovery:" + location.credential_id.hex
        ):
            raise PasswordCustodyUnavailable()
        return location.credential_id.hex

    # Traverse descriptors without following links and serialize private pointer writes per secret.
    @contextmanager
    def locked(self, location):
        name = self.name(location)
        directory = self.guard._directory()
        descriptor = None
        try:
            descriptor = os.open(
                name + ".lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory,
            )
            self.regular(descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield directory, name
        except (OSError, ValueError, TypeError, KeyError):
            raise PasswordCustodyUnavailable() from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)

    # Reads and lock files must remain private single-link regular files owned by this operator.
    def regular(self, descriptor):
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise PasswordCustodyUnavailable()

    # Bound every private JSON read; corrupted files never become an empty new secret.
    def read(self, directory, name):
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "rb") as stream:
            self.regular(stream.fileno())
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise PasswordCustodyUnavailable()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise PasswordCustodyUnavailable()
        return value

    # Persist and fsync a new immutable file, or atomically replace the guarded CURRENT pointer.
    def write(self, directory, name, value, *, replace=False):
        temporary = name + "." + uuid4().hex
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(value, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            else:
                os.link(
                    temporary,
                    name,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
                os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    # Derive a nonsecret binding digest independently from the random credential location.
    def scope(self, location):
        return hashlib.sha256(location.model_dump_json().encode()).hexdigest()

    # Idempotent exact-operation staging never returns a different password after a lost response.
    def stage(self, location, operation_id):
        UUID(str(operation_id))
        if location.secret_reference is None:
            location = location.model_copy(
                update={
                    "secret_reference": "sim-recovery:" + location.credential_id.hex,
                }
            )
        with self.locked(location) as (directory, name):
            version = operation_id.hex
            filename = name + ".version." + version
            try:
                value = self.read(directory, filename)
            except FileNotFoundError:
                value = {
                    "scope": self.scope(location),
                    "version": version,
                    "operation_id": str(operation_id),
                    "password": generate_recovery_password(location.target.user_name),
                }
                self.write(directory, filename, value)
            self.material(location, value)
            return PasswordVersion(location=location, version=version, operation_id=operation_id)

    # Only validated private records may become a transient redacted secret value.
    def material(self, location, value):
        if (
            set(value) != {"scope", "version", "operation_id", "password"}
            or value["scope"] != self.scope(location)
            or not isinstance(value["password"], str)
            # Preserve historical simulated CURRENT/candidates; validate new 32-character records.
            or (
                len(value["password"]) != 54
                and not valid_generated_password(value["password"], location.target.user_name)
            )
            or UUID(value["operation_id"]).hex != value["version"]
        ):
            raise PasswordCustodyUnavailable()
        return PasswordMaterial(
            PasswordVersion(
                location=location,
                version=value["version"],
                operation_id=UUID(value["operation_id"]),
            ),
            SecretStr(value["password"]),
        )

    # Resolve an exact candidate without consulting the mutable CURRENT selector.
    def candidate(self, reference):
        PasswordVersion.model_validate(reference)
        if not re.fullmatch(r"[0-9a-f]{32}", reference.version):
            raise PasswordCustodyUnavailable()
        with self.locked(reference.location) as (directory, name):
            result = self.material(
                reference.location,
                self.read(directory, name + ".version." + reference.version),
            )
            if result.reference != reference:
                raise PasswordCustodyUnavailable()
            return result

    # Normal retrieval always follows CURRENT and validates its exact bound immutable version.
    def current(self, location):
        with self.locked(location) as (directory, name):
            pointer = self.read(directory, name + ".current")
            if set(pointer) != {"scope", "version"} or pointer["scope"] != self.scope(location):
                raise PasswordCustodyUnavailable()
            version = UUID(pointer["version"]).hex
            if version != pointer["version"]:
                raise PasswordCustodyUnavailable()
            return self.material(location, self.read(directory, name + ".version." + version))

    # Per-attempt authority metadata cannot substitute another operation or recovery subject.
    def require_context(self, material, context):
        RequiredUserReadContext.model_validate(context)
        if (
            context.workspace_id != material.reference.location.target.workspace_id
            or context.operation_id != material.reference.operation_id
            or context.step_key
            != "recovery_password:" + str(material.reference.location.credential_id)
        ):
            raise PasswordCustodyUnavailable()

    # Change only the exact simulated existing subject; no account creation or credential fallback.
    def change(self, material, context):
        self.require_context(material, context)
        reference = material.reference
        candidate = self.candidate(reference)
        if not hmac.compare_digest(
            candidate.password.get_secret_value(), material.password.get_secret_value()
        ):
            return PasswordChange(effect="none")
        with self.locked(reference.location) as (directory, name):
            self.write(
                directory,
                name + ".child",
                {
                    "scope": self.scope(reference.location),
                    "context_hash": hashlib.sha256(context.model_dump_json().encode()).hexdigest(),
                    "password_hash": hashlib.sha256(
                        material.password.get_secret_value().encode()
                    ).hexdigest(),
                },
                replace=True,
            )
        return PasswordChange(effect="known")

    # Read independent simulated child state; Vault success alone never certifies the password.
    def verify(self, material, context):
        self.require_context(material, context)
        with self.locked(material.reference.location) as (directory, name):
            value = self.read(directory, name + ".child")
            return (
                set(value) == {"scope", "password_hash", "context_hash"}
                and value["scope"] == self.scope(material.reference.location)
                and value["context_hash"]
                == hashlib.sha256(context.model_dump_json().encode()).hexdigest()
                and hmac.compare_digest(
                    value["password_hash"],
                    hashlib.sha256(material.password.get_secret_value().encode()).hexdigest(),
                )
            )

    # Promotion is conditional and idempotent for this exact verified immutable candidate.
    def promote(self, reference, expected_current):
        self.candidate(reference)
        with self.locked(reference.location) as (directory, name):
            try:
                pointer = self.read(directory, name + ".current")
            except FileNotFoundError:
                pointer = None
            if pointer is not None and (
                set(pointer) != {"scope", "version"}
                or pointer["scope"] != self.scope(reference.location)
            ):
                raise PasswordCustodyUnavailable()
            current = pointer["version"] if pointer else None
            if current != reference.version and current != expected_current:
                raise PasswordCustodyUnavailable()
            self.write(
                directory,
                name + ".current",
                {
                    "scope": self.scope(reference.location),
                    "version": reference.version,
                },
                replace=True,
            )
