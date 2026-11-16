"""Guarded per-secret execution; host supplies current rotation state and existing serialization."""

from contextlib import AbstractContextManager
from typing import Literal, Protocol

from otm.contracts import Contract
from otm.providers.secret_versions import (
    ManagedSecretBinding,
    SecretVersionConflict,
    SecretVersionInventory,
)
from otm.tenancies.secret_cleanup import (
    SecretCleanupPolicy,
    SecretCleanupState,
    plan_secret_cleanup,
)


# The trusted host derives fresh state from current credential/operation records, not a request.
class CleanupStateReader(Protocol):
    # Read current pins and resolved rotation state; do not reconstruct historical retirement proof.
    def snapshot(self) -> SecretCleanupState: ...


# The host uses the same credential serialization as rotations, without a SQL transaction over I/O.
# This interface grants no authority by itself; production repository/queue composition is pending.
class CleanupAuthority(Protocol):
    # Retain the host's credential fence through each observation and conditional provider mutation.
    def serialized(
        self, binding: ManagedSecretBinding
    ) -> AbstractContextManager[CleanupStateReader]: ...


# Fixed metadata outcomes let the future worker persist/retry separately from successful rotation.
class SecretCleanupRun(Contract):
    binding: ManagedSecretBinding
    state: Literal["complete", "held", "conflict", "unavailable", "unverified"]
    scheduled_versions: tuple[int, ...]
    pressure: Literal["unknown", "ok", "warning", "critical"]


# Readback must confirm only the requested version changed, without losing live or unknown versions.
def verified_deletion_schedule(before, after, number, deletion_at):
    before = SecretVersionInventory.model_validate(before)
    after = SecretVersionInventory.model_validate(after)
    original = {item.number: item for item in before.versions}
    observed = {item.number: item for item in after.versions}
    return (
        after.complete
        and before.binding == after.binding
        and before.revision != after.revision
        and original.keys() == observed.keys()
        and number in original
        and original[number].stages == {"DEPRECATED"}
        and original[number].deletion_at is None
        and observed[number].stages == original[number].stages
        and observed[number].deletion_at == deletion_at
        and all(original[key] == observed[key] for key in original if key != number)
    )


# No automatic provider fallback, unbounded retry or whole-secret deletion exists in this engine.
class SecretCleanupEngine:
    # Explicit dependencies select one custody facade, host authority, clock and validated policy.
    def __init__(self, provider, authority, clock, policy=None):
        self.provider, self.authority, self.clock = provider, authority, clock
        self.policy = SecretCleanupPolicy.model_validate(
            policy if policy is not None else SecretCleanupPolicy()
        )

    # Normalize inventory and current host state before every conditional schedule.
    def observe(self, binding, reader):
        inventory = SecretVersionInventory.model_validate(self.provider.inventory(binding))
        host_state = SecretCleanupState.model_validate(reader.snapshot())
        if inventory.binding != binding or host_state.binding != binding:
            raise ValueError("SECRET_CLEANUP_SCOPE_INVALID")
        return inventory, plan_secret_cleanup(inventory, host_state, self.clock(), self.policy)

    # Bounded initial scope, fresh pins and conditional writes make replay resume without extension.
    def run(self, binding):
        binding = ManagedSecretBinding.model_validate(binding)
        scheduled, pressure, dispatching = [], "unknown", False
        try:
            with self.authority.serialized(binding) as reader:
                _, initial = self.observe(binding, reader)
                pressure = initial.pressure
                if initial.held:
                    state = "held"
                else:
                    state = "complete"
                    for number in initial.schedule_versions:
                        before, current = self.observe(binding, reader)
                        pressure = current.pressure
                        if current.held:
                            state = "held"
                            break
                        if number not in current.schedule_versions:
                            continue
                        dispatching = True
                        response = self.provider.schedule_version_deletion(
                            binding, number, current.deletion_at, current.revision
                        )
                        response = SecretVersionInventory.model_validate(response)
                        after = self.provider.inventory(binding)
                        if response.binding != binding or not verified_deletion_schedule(
                            before, after, number, current.deletion_at
                        ):
                            state = "unverified"
                            break
                        dispatching = False
                        scheduled.append(number)
        except SecretVersionConflict:
            state = "conflict"
        except Exception:
            # Provider errors can contain secret/transport details; never carry their text onward.
            state = "unverified" if dispatching else "unavailable"
        return SecretCleanupRun(
            binding=binding, state=state, scheduled_versions=tuple(scheduled), pressure=pressure
        )
