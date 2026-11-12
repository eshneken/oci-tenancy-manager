"""Bounded owner-only JSON records for explicitly selected local custody and simulator adapters."""

import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from uuid import uuid4

from otm.secrets.directory import DirectorySecrets


# No default path or implicit directory creation can become a live-provider custody fallback.
class PrivateJsonRecords:
    # Require a private root; descriptor traversal rejects redirected ancestors.
    def __init__(self, directory):
        self.guard = DirectorySecrets(directory)

    # The caller constructs bounded names, never a URL, relative path or browser-supplied filename.
    def name(self, name):
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,159}", name):
            raise ValueError("PRIVATE_RECORD_NAME_INVALID")
        return name

    # Bound reads/locks to unshared regular files, even if an operator replaced a path with a link.
    def regular(self, descriptor):
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("PRIVATE_RECORD_FILE_INVALID")

    # Hold one record lock without another secret lock. Live custody paths stay outside DB
    # transactions; the explicit laptop bootstrap simulation permits bounded local preparation.
    @contextmanager
    def locked(self, name):
        directory = self.guard._directory()
        descriptor = None
        try:
            descriptor = os.open(
                self.name(name) + ".lock",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory,
            )
            self.regular(descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield directory
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)

    # Corrupt, oversized or absent content never becomes an empty record or a new secret.
    def read(self, directory, name):
        descriptor = os.open(
            self.name(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as stream:
            self.regular(stream.fileno())
            content = stream.read(16385)
        if len(content) > 16384:
            raise ValueError("PRIVATE_RECORD_TOO_LARGE")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("PRIVATE_RECORD_INVALID")
        return value

    # New versions are atomically linked exactly once; mutable simulated provider rows use replace.
    def write(self, directory, name, value, *, replace=False):
        name = self.name(name)
        content = json.dumps(value, separators=(",", ":")).encode()
        if len(content) > 16384:
            raise ValueError("PRIVATE_RECORD_TOO_LARGE")
        temporary = name + "." + uuid4().hex
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
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
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
