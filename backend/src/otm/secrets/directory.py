"""Explicit laptop-only immutable secret files; no automatic fallback from a production Vault."""

import hashlib
import hmac
import os
import re
import stat
from pathlib import Path
from typing import Protocol
from uuid import uuid4


# The local authenticator depends on immutable custody, not a particular cloud provider API.
class MfaSecrets(Protocol):
    # Create an immutable seed version and return only its opaque reference.
    def put(self, seed: str) -> str: ...

    # Retrieve the exact immutable version, failing closed on unavailable or altered custody.
    def get(self, reference: str) -> str: ...


# Require a precreated owner-only directory and refuse symlinks along its entire absolute path.
class DirectorySecrets:
    # Resolve no links and create no directory implicitly; callers explicitly select private
    # custody.
    def __init__(self, directory: Path):
        if not directory.is_absolute() or ".." in directory.parts:
            raise ValueError("PRIVATE_SECRET_DIRECTORY_REQUIRED")
        self.directory = directory
        descriptor = self._directory()
        os.close(descriptor)

    # Use descriptor-relative traversal so a path substitution cannot redirect a secret write.
    def _directory(self):
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.directory.parts[1:]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = child
            value = os.fstat(descriptor)
            if value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) != 0o700:
                raise ValueError("PRIVATE_SECRET_DIRECTORY_REQUIRED")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    # Persist one random-named immutable file; never replace a prior reference or print its
    # contents.
    def put(self, seed: str) -> str:
        if not isinstance(seed, str) or not re.fullmatch("[A-Z2-7]{32}", seed):
            raise ValueError("INVALID_MFA_SECRET")
        name = uuid4().hex
        directory = self._directory()
        try:
            descriptor = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(seed.encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
        finally:
            os.close(directory)
        return "local-secret:" + name + ":" + hashlib.sha256(seed.encode("ascii")).hexdigest()

    # Bound reads and validate the inode, permissions, ownership and contents before using a seed.
    def get(self, reference: str) -> str:
        if not isinstance(reference, str) or not re.fullmatch(
            "local-secret:[0-9a-f]{32}:[0-9a-f]{64}", reference
        ):
            raise ValueError("INVALID_MFA_REFERENCE")
        directory = self._directory()
        try:
            descriptor = os.open(
                reference.split(":")[1],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "rb") as stream:
                value = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(value.st_mode)
                    or value.st_uid != os.geteuid()
                    or stat.S_IMODE(value.st_mode) != 0o600
                    or value.st_nlink != 1
                ):
                    raise ValueError("PRIVATE_SECRET_FILE_REQUIRED")
                seed = stream.read(65).decode("ascii")
                if not re.fullmatch("[A-Z2-7]{32}", seed):
                    raise ValueError("INVALID_MFA_SECRET")
                # Bind immutable content to the DB-held reference, including validly encoded edits.
                digest = hashlib.sha256(seed.encode("ascii")).hexdigest()
                if not hmac.compare_digest(digest, reference.split(":")[2]):
                    raise ValueError("MFA_SECRET_CONTENT_CHANGED")
                return seed
        finally:
            os.close(directory)
