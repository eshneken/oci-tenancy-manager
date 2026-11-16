"""In-memory metadata simulator; no credentials, OCI SDK calls, queue or saved-app mutations."""

from datetime import timedelta
from threading import RLock
from uuid import uuid4

from otm.contracts import utc_only
from otm.providers.secret_versions import (
    ManagedSecretBinding,
    SecretVersionConflict,
    SecretVersionInventory,
    SecretVersionUnavailable,
)


# Explicit registrations prevent implicit creation and cross-credential lookups.
class SimulatedSecretVersions:
    # An injected clock distinguishes scheduling from eventual service-owned hard deletion.
    def __init__(self, inventories, clock, pending_limit=30):
        # Per-secret pending-deletion capacity, integer1-1024; default matches the paid service.
        if type(pending_limit) is not int or not 1 <= pending_limit <= 1024:
            raise ValueError("SECRET_VERSION_CAPACITY_INVALID")
        self.pending_limit = pending_limit
        # Model service-side atomic metadata changes, not the future worker/SQL credential lock.
        self._lock = RLock()
        self.clock = clock
        self.inventories = {}
        for raw in inventories:
            inventory = SecretVersionInventory.model_validate(raw)
            key = inventory.binding.secret_reference
            if key in self.inventories:
                raise ValueError("SECRET_VERSION_REGISTRATION_INVALID")
            self.inventories[key] = inventory

    # Every metadata lookup must match the full registered binding, not just a guessed secret name.
    def inventory(self, binding):
        with self._lock:
            binding = ManagedSecretBinding.model_validate(binding)
            value = self.inventories.get(binding.secret_reference)
            if value is None or value.binding != binding:
                raise SecretVersionUnavailable("SECRET_VERSION_UNAVAILABLE")
            return value

    # Enforce revision, deprecated-only eligibility and service delay before changing any metadata.
    def schedule_version_deletion(self, binding, number, deletion_at, expected_revision):
        with self._lock:
            binding = ManagedSecretBinding.model_validate(binding)
            inventory = self.inventory(binding)
            if inventory.revision != expected_revision:
                raise SecretVersionConflict("SECRET_VERSION_CONFLICT")
            now = utc_only(self.clock())
            deletion_at = utc_only(deletion_at)
            version = next((item for item in inventory.versions if item.number == number), None)
            if (
                type(number) is not int
                or number < 1
                or sum(item.deletion_at is not None for item in inventory.versions)
                >= self.pending_limit
                or not inventory.complete
                or version is None
                or version.stages != {"DEPRECATED"}
                or version.deletion_at is not None
                or not now + timedelta(days=1) <= deletion_at <= now + timedelta(days=30)
            ):
                raise SecretVersionUnavailable("SECRET_VERSION_DELETE_UNSAFE")
            updated = inventory.model_copy(
                update={
                    "revision": str(uuid4()),
                    "versions": tuple(
                        item.model_copy(update={"deletion_at": deletion_at})
                        if item.number == number
                        else item
                        for item in inventory.versions
                    ),
                }
            )
            self.inventories[binding.secret_reference] = updated
            return updated

    # Model OCI's elapsed-time purge only for scheduled versions; this is not an OTM delete command.
    def reap_due_versions(self):
        with self._lock:
            now = utc_only(self.clock())
            for key, inventory in tuple(self.inventories.items()):
                versions = tuple(
                    item
                    for item in inventory.versions
                    if item.deletion_at is None
                    or item.deletion_at > now
                    or item.stages != {"DEPRECATED"}
                )
                if versions != inventory.versions:
                    self.inventories[key] = inventory.model_copy(
                        update={"revision": str(uuid4()), "versions": versions}
                    )
