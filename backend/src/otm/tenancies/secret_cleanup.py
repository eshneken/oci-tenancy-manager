"""Pure cleanup decisions and stable secret names; no database, queue, Vault or deletion effects."""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract, UtcInstant
from otm.providers.secret_versions import (
    ManagedSecretBinding,
    SecretVersionInventory,
    VersionNumber,
)


# The host supplies current operation state under its existing per-tenancy rotation serialization.
# This small snapshot contains no historical retirement proofs or restore reconciliation journal.
class SecretCleanupState(Contract):
    binding: ManagedSecretBinding
    protected_versions: frozenset[VersionNumber]
    rotation_resolved: bool


# Approved V1 retention; runtime TOML/worker wiring follows in a separate slice.
class SecretCleanupPolicy(Contract):
    # Keep the newest 1-25 unscheduled versions; protected versions may exceed this target.
    keep_versions: Annotated[int, Field(ge=1, le=25)] = 5
    # Seconds,24h through30days; default adds5minutes to OCI's minimum deletion scheduling delay.
    deletion_delay_seconds: Annotated[int, Field(ge=86400, le=2592000)] = 86700
    # Expected per-secret nonpending/pending pools; qualify actual tenancy quotas before deployment.
    active_limit: Annotated[int, Field(ge=3, le=1024)] = 30
    # Pending-deletion pool capacity,3-1024; scheduled but unpurged versions still consume it.
    pending_limit: Annotated[int, Field(ge=3, le=1024)] = 30
    # Version counts, applied independently to both pools; warn before either pool is exhausted.
    warning_count: Annotated[int, Field(ge=1)] = 20
    # Critical count above warning and below both pool limits; evaluated independently per pool.
    critical_count: Annotated[int, Field(ge=2)] = 25

    # Thresholds cannot invert or reach beyond the configured pools' hard capacities.
    @model_validator(mode="after")
    def ordered_thresholds(self):
        if (
            not 0
            < self.warning_count
            < self.critical_count
            < min(self.active_limit, self.pending_limit)
            or self.keep_versions >= self.active_limit
        ):
            raise ValueError("SECRET_CLEANUP_THRESHOLDS_INVALID")
        return self


# Plans contain metadata only; refresh current state under existing rotation serialization.
class SecretCleanupPlan(Contract):
    binding: ManagedSecretBinding
    revision: str
    held: bool
    active_count: int | None
    pending_count: int | None
    pressure: Literal["unknown", "ok", "warning", "critical"]
    can_create_version: bool
    schedule_versions: tuple[VersionNumber, ...]
    deletion_at: UtcInstant


# UUIDs avoid employee PII, tenancy-name changes and caller-controlled suffixes in secret names.
def managed_secret_name(identity: UUID, purpose: str) -> str:
    if (
        not isinstance(identity, UUID)
        or not isinstance(purpose, str)
        or purpose
        not in {
            "automation-key",
            "recovery-password",
            "bootstrap-key",
        }
    ):
        raise ValueError("MANAGED_SECRET_NAME_INVALID")
    name = f"otm-{identity}-{purpose}"
    return name


# Keep the newest five unscheduled versions plus CURRENT/PREVIOUS/PENDING and explicit pins.
# Older DEPRECATED versions can be scheduled only after rotation is settled; OCI purges later.
def plan_secret_cleanup(inventory, state, at, policy=None):
    inventory = SecretVersionInventory.model_validate(inventory)
    state = SecretCleanupState.model_validate(state)
    policy = SecretCleanupPolicy.model_validate(
        policy if policy is not None else SecretCleanupPolicy()
    )
    if inventory.binding != state.binding:
        raise ValueError("SECRET_CLEANUP_SCOPE_INVALID")
    known = {"CURRENT", "PREVIOUS", "PENDING", "LATEST", "DEPRECATED"}
    healthy = (
        inventory.complete
        and inventory.binding.purpose in {"automation-key", "recovery-password"}
        and state.rotation_resolved
        and state.protected_versions <= {version.number for version in inventory.versions}
        and all(
            version.deletion_at is None
            for version in inventory.versions
            if version.stages & {"CURRENT", "PREVIOUS", "PENDING"}
            or version.number in state.protected_versions
        )
        and all(version.stages and version.stages <= known for version in inventory.versions)
        and sum("CURRENT" in version.stages for version in inventory.versions) == 1
        and sum("PREVIOUS" in version.stages for version in inventory.versions) <= 1
        and all(
            not ("DEPRECATED" in version.stages and len(version.stages) != 1)
            for version in inventory.versions
        )
    )
    active = sum(version.deletion_at is None for version in inventory.versions)
    pending = len(inventory.versions) - active
    pressure = (
        "unknown"
        if not inventory.complete
        else "critical"
        if max(active, pending) >= policy.critical_count
        else "warning"
        if max(active, pending) >= policy.warning_count
        else "ok"
    )
    # Already scheduled versions are not part of the retained five; otherwise a previously
    # scheduled high-numbered version could cause deletion of a needed retention fallback.
    retained = set(
        sorted(
            (version.number for version in inventory.versions if version.deletion_at is None),
            reverse=True,
        )[: policy.keep_versions]
    )
    candidates = sorted(
        version.number
        for version in inventory.versions
        if healthy
        and version.deletion_at is None
        and version.stages == {"DEPRECATED"}
        and version.number not in retained
        and version.number not in state.protected_versions
    )
    # Never overfill pending deletion slots, even if many retained versions need reclamation.
    candidates = candidates[: max(0, policy.pending_limit - pending)]
    return SecretCleanupPlan(
        binding=inventory.binding,
        revision=inventory.revision,
        held=not healthy,
        active_count=active if inventory.complete else None,
        pending_count=pending if inventory.complete else None,
        pressure=pressure,
        can_create_version=healthy
        and active < policy.active_limit
        and pending < policy.pending_limit,
        schedule_versions=tuple(candidates),
        deletion_at=at + timedelta(seconds=policy.deletion_delay_seconds),
    )
