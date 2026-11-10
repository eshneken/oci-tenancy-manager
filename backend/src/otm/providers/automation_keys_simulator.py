"""Explicit synthetic public-key inventory; no PEM, signer, Vault or real OCI calls."""

import hashlib
import os
import stat
from pathlib import Path
from uuid import UUID

from otm.contracts import Contract, Text
from otm.providers.automation_keys import (
    AutomationKeyCapture,
    AutomationKeyFacts,
    AutomationKeyInspection,
    AutomationKeyObservation,
    ObservedAutomationKey,
)
from otm.providers.required_user_contracts import ObservedRequiredUser


# Retain the fixture's exact owner/scope beside its independently produced public metadata.
class KeyFixture(Contract):
    workspace_id: Text
    tenancy_id: UUID
    tenancy_ocid: Text
    facts: AutomationKeyFacts


# Only explicit simulated configure creates inventory; read/capture never backfill a missing file.
class SimulatedAutomationKeys:
    # The local host chooses a private directory and UTC clock, never a browser request.
    def __init__(self, directory, clock):
        self.directory, self.clock = Path(directory), clock
        if any(path.is_symlink() for path in (self.directory, *self.directory.parents)):
            raise ValueError("SIMULATED_KEY_DIRECTORY_INVALID")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.guard()

    # Reject redirected or shared roots before resolving any child fixture name.
    def guard(self):
        if self.directory.is_symlink() or any(p.is_symlink() for p in self.directory.parents):
            raise ValueError("SIMULATED_KEY_DIRECTORY_INVALID")
        info = self.directory.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("SIMULATED_KEY_DIRECTORY_INVALID")

    # Read bounded private regular files; filenames alone never prove subject scope.
    def read(self, workspace, identifier, tenancy_ocid, user):
        self.guard()
        if not isinstance(identifier, UUID):
            raise ValueError("SIMULATED_KEY_TARGET_INVALID")
        path = self.directory / (identifier.hex + ".json")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
                or info.st_size > 16384
            ):
                raise ValueError("SIMULATED_KEY_FILE_INVALID")
            record = KeyFixture.model_validate_json(stream.read(16385))
        if (record.workspace_id, record.tenancy_id, record.tenancy_ocid, record.facts.user) != (
            workspace,
            identifier,
            tenancy_ocid,
            user,
        ):
            raise ValueError("SIMULATED_KEY_SCOPE_INVALID")
        return AutomationKeyCapture(facts=record.facts)

    # O_EXCL preserves the original creation time across retries and restarts.
    def configure(self, workspace, identifier, tenancy_ocid, user):
        self.guard()
        if not isinstance(identifier, UUID):
            raise ValueError("SIMULATED_KEY_TARGET_INVALID")
        digest = hashlib.sha256(
            (workspace + ":automation-key:" + identifier.hex).encode()
        ).hexdigest()[:32]
        key = ObservedAutomationKey(
            provider_key_id="simulated-api-key-" + identifier.hex,
            fingerprint=":".join(digest[i : i + 2] for i in range(0, 32, 2)),
            created_at=self.clock(),
            state="active",
        )
        record = KeyFixture(
            workspace_id=workspace,
            tenancy_id=identifier,
            tenancy_ocid=tenancy_ocid,
            facts=AutomationKeyFacts(
                user=user, authorized=True, complete=True, supported=True, keys=(key,)
            ),
        )
        try:
            fd = os.open(
                self.directory / (identifier.hex + ".json"),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
        except FileExistsError:
            return self.read(workspace, identifier, tenancy_ocid, user)
        with os.fdopen(fd, "wb") as stream:
            stream.write(record.model_dump_json().encode())
            stream.flush()
            os.fsync(stream.fileno())
        return self.read(workspace, identifier, tenancy_ocid, user)


# The simulator reads retained fixture facts, independently of command expectations.
class SimulatedAutomationKeyProvider:
    # No default store is invented when composition has not selected this simulator.
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    # Missing retained facts are an unavailable read, never permission to recreate a key.
    def inspect_automation_keys(self, command):
        target = command.target
        user = ObservedRequiredUser(
            domain_ocid=target.domain_ocid,
            scim_resource_id=target.scim_resource_id,
            provider_ocid=target.provider_ocid,
            user_name=target.user_name,
        )
        capture = self.store.read(target.workspace_id, target.tenancy_id, target.tenancy_ocid, user)
        return AutomationKeyObservation(
            context=command.context, target=target, captured_at=self.clock(), facts=capture.facts
        )


# Legacy setup without an explicit key capture never gains simulated keys during a refresh.
def simulated_key_inspection(store, command, source, clock):
    if source.automation_keys is None:
        raise ValueError("AUTOMATION_KEY_CAPTURE_UNAVAILABLE")
    return AutomationKeyInspection(SimulatedAutomationKeyProvider(store, clock), clock)
