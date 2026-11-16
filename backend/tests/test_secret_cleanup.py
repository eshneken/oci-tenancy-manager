"""Keep five versions, preserve protected credentials and model safe deferred deletion."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from otm.providers.secret_versions import (
    ManagedSecretBinding,
    SecretVersionConflict,
    SecretVersionFacts,
    SecretVersionInventory,
    SecretVersionUnavailable,
)
from otm.providers.secret_versions_simulator import SimulatedSecretVersions
from otm.tenancies.secret_cleanup import (
    SecretCleanupPolicy,
    SecretCleanupState,
    managed_secret_name,
    plan_secret_cleanup,
)

NOW = datetime(2026, 11, 13, tzinfo=UTC)


# Six synthetic versions leave exactly the oldest deprecated version outside default retention.
@pytest.fixture
def inventory():
    binding = ManagedSecretBinding(
        workspace_id="cleanup-workspace",
        credential_id=UUID(int=2),
        secret_reference="synthetic-secret",
        purpose="automation-key",
    )
    return SecretVersionInventory(
        binding=binding,
        revision="revision-one",
        complete=True,
        versions=tuple(
            SecretVersionFacts(
                number=n,
                stages=frozenset(
                    {"CURRENT", "LATEST"} if n == 6 else {"PREVIOUS"} if n == 5 else {"DEPRECATED"}
                ),
            )
            for n in range(1, 7)
        ),
    )


# The existing host reports settled rotation and any exact versions still needed by operations.
@pytest.fixture
def state(inventory):
    return SecretCleanupState(
        binding=inventory.binding, protected_versions=frozenset(), rotation_resolved=True
    )


# Default retention keeps five; scheduling is delayed and does not itself free pending capacity.
def test_post_rotation_plan(inventory, state):
    result = plan_secret_cleanup(inventory, state, NOW)
    assert result.schedule_versions == (1,)
    assert result.deletion_at == NOW + timedelta(days=1, minutes=5)
    assert result.active_count == 6 and result.pending_count == 0
    assert not result.held and result.pressure == "ok" and result.can_create_version
    assert result.revision == inventory.revision and SecretCleanupPolicy().keep_versions == 5


# Fewer than six retained versions must never trigger pruning, irrespective of version-number gaps.
@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6, 10, 30])
def test_keep_five_boundary(inventory, state, count):
    versions = tuple(
        SecretVersionFacts(
            number=n * 10, stages=frozenset({"CURRENT"} if n == count else {"DEPRECATED"})
        )
        for n in range(1, count + 1)
    )
    result = plan_secret_cleanup(inventory.model_copy(update={"versions": versions}), state, NOW)
    assert result.schedule_versions == tuple(n * 10 for n in range(1, max(1, count - 4)))
    assert not result.held


# Provider iteration order does not determine age or which five versions are kept.
def test_unordered_inventory_uses_version_number(inventory, state):
    shuffled = inventory.model_copy(update={"versions": tuple(reversed(inventory.versions))})
    assert plan_secret_cleanup(shuffled, state, NOW).schedule_versions == (1,)


# A pin outside the retained five is preserved even when this temporarily keeps six versions.
def test_explicit_pin_is_additive(inventory, state):
    state = state.model_copy(update={"protected_versions": frozenset({1})})
    assert plan_secret_cleanup(inventory, state, NOW).schedule_versions == ()


# Old current/previous/pending versions remain protected outside the newest-five retention set.
@pytest.mark.parametrize("stage", ["CURRENT", "PREVIOUS", "PENDING"])
def test_older_protected_stage_is_additive(inventory, state, stage):
    versions = tuple(
        SecretVersionFacts(
            number=n,
            stages=frozenset(
                {stage}
                if n == 1
                else {"CURRENT"}
                if n == 7 and stage != "CURRENT"
                else {"DEPRECATED"}
            ),
        )
        for n in range(1, 8)
    )
    result = plan_secret_cleanup(inventory.model_copy(update={"versions": versions}), state, NOW)
    assert result.schedule_versions == (2,) and not result.held


# An unresolved/failed rotation holds all cleanup without reconstructing historical audit evidence.
def test_unresolved_rotation_holds(inventory, state):
    state = state.model_copy(update={"rotation_resolved": False})
    result = plan_secret_cleanup(inventory, state, NOW)
    assert result.held and not result.can_create_version and not result.schedule_versions


# Partial pagination cannot authorize cleanup or invent definitive capacity counts.
def test_incomplete_inventory_hold(inventory, state):
    result = plan_secret_cleanup(inventory.model_copy(update={"complete": False}), state, NOW)
    assert result.held and result.pressure == "unknown"
    assert result.active_count is None and result.pending_count is None
    assert not result.schedule_versions and not result.can_create_version


# Unknown/contradictory labels and broken CURRENT/PREVIOUS observations fail closed.
@pytest.mark.parametrize("fault", ["unknown", "empty", "mixed", "current", "previous", "missing"])
def test_invalid_stage_observations_hold(inventory, state, fault):
    versions = list(inventory.versions)
    labels = {
        "unknown": {"UNKNOWN_ENUM_VALUE"},
        "empty": set(),
        "mixed": {"DEPRECATED", "LATEST"},
        "current": {"CURRENT"},
        "previous": {"PREVIOUS"},
        "missing": {"LATEST"},
    }
    index = -1 if fault == "missing" else 0
    versions[index] = versions[index].model_copy(update={"stages": frozenset(labels[fault])})
    result = plan_secret_cleanup(
        inventory.model_copy(update={"versions": tuple(versions)}), state, NOW
    )
    assert result.held and not result.schedule_versions and not result.can_create_version


# Pending deletions do not displace the five unscheduled versions retained for ordinary use.
def test_scheduled_versions_do_not_count_as_retained(inventory, state):
    pending = tuple(
        SecretVersionFacts(
            number=n, stages=frozenset({"DEPRECATED"}), deletion_at=NOW - timedelta(days=1)
        )
        for n in range(10, 39)
    )
    result = plan_secret_cleanup(
        inventory.model_copy(update={"versions": inventory.versions + pending}), state, NOW
    )
    assert result.schedule_versions == (1,) and result.pending_count == 29
    assert result.pressure == "critical" and result.can_create_version
    full = pending + (pending[-1].model_copy(update={"number": 39}),)
    result = plan_secret_cleanup(
        inventory.model_copy(update={"versions": inventory.versions + full}), state, NOW
    )
    assert not result.schedule_versions and not result.can_create_version


# Unknown explicit consumers hold cleanup; an empty pin set is valid only from a trusted host.
def test_missing_protected_version_holds(inventory, state):
    state = state.model_copy(update={"protected_versions": frozenset({99})})
    assert plan_secret_cleanup(inventory, state, NOW).held


# Already scheduled protected versions signal unsafe custody rather than permission to prune more.
@pytest.mark.parametrize("index", [-2, -1])
def test_protected_stage_already_scheduled_holds(inventory, state, index):
    versions = list(inventory.versions)
    versions[index] = versions[index].model_copy(update={"deletion_at": NOW + timedelta(days=1)})
    result = plan_secret_cleanup(
        inventory.model_copy(update={"versions": tuple(versions)}), state, NOW
    )
    assert result.held and not result.schedule_versions


# Retention never bypasses real capacity limits, even when many old versions can be scheduled.
@pytest.mark.parametrize(
    "count,pressure,admit",
    [
        (19, "ok", True),
        (20, "warning", True),
        (24, "warning", True),
        (25, "critical", True),
        (29, "critical", True),
        (30, "critical", False),
    ],
)
def test_active_pool_pressure(inventory, state, count, pressure, admit):
    versions = tuple(
        SecretVersionFacts(
            number=n, stages=frozenset({"CURRENT"} if n == count else {"DEPRECATED"})
        )
        for n in range(1, count + 1)
    )
    result = plan_secret_cleanup(inventory.model_copy(update={"versions": versions}), state, NOW)
    assert result.active_count == count and result.pending_count == 0
    assert result.pressure == pressure and result.can_create_version is admit
    assert result.schedule_versions == tuple(range(1, count - 4))


# Cross-workspace/credential/reference/purpose substitution cannot create target authority.
@pytest.mark.parametrize(
    "change",
    [
        {"workspace_id": "other-workspace"},
        {"credential_id": UUID(int=9)},
        {"secret_reference": "other-secret"},
        {"purpose": "recovery-password"},
    ],
)
def test_scope_mismatch_rejected(inventory, state, change):
    state = state.model_copy(update={"binding": state.binding.model_copy(update=change)})
    with pytest.raises(ValueError, match="^SECRET_CLEANUP_SCOPE_INVALID$"):
        plan_secret_cleanup(inventory, state, NOW)


# Duplicate provider identities cannot corrupt age, retention or quota calculations.
def test_duplicate_inventory_versions_rejected(inventory):
    with pytest.raises(ValidationError, match="SECRET_VERSION_INVENTORY_INVALID"):
        SecretVersionInventory.model_validate(
            inventory.model_copy(update={"versions": inventory.versions + (inventory.versions[0],)})
        )


# Configuration keeps retention positive/bounded and below active capacity, with valid delay limits.
@pytest.mark.parametrize(
    "change",
    [
        {"keep_versions": 0},
        {"keep_versions": 26},
        {"keep_versions": True},
        {"deletion_delay_seconds": 86399},
        {"deletion_delay_seconds": 2592001},
        {"warning_count": 25},
        {"critical_count": 30},
        {"pending_limit": 20},
        {"active_limit": 5, "warning_count": 1, "critical_count": 2},
    ],
)
def test_invalid_policy_rejected(change):
    with pytest.raises(ValidationError):
        SecretCleanupPolicy(**change)


# A smaller explicit retention target still respects pending capacity and oldest-first scheduling.
def test_custom_retention_and_capacity(inventory, state):
    policy = SecretCleanupPolicy(
        keep_versions=2, active_limit=4, pending_limit=3, warning_count=1, critical_count=2
    )
    pending = SecretVersionFacts(
        number=10, stages=frozenset({"DEPRECATED"}), deletion_at=NOW + timedelta(days=1)
    )
    result = plan_secret_cleanup(
        inventory.model_copy(update={"versions": inventory.versions + (pending,)}),
        state,
        NOW,
        policy,
    )
    assert result.schedule_versions == (1, 2) and not result.can_create_version


# Names use a full immutable UUID and documented safe characters, within our own64-character cap.
@pytest.mark.parametrize(
    "purpose,length",
    [
        ("automation-key", 55),
        ("recovery-password", 58),
        ("bootstrap-key", 54),
    ],
)
def test_stable_secret_names(purpose, length):
    name = managed_secret_name(UUID(int=7), purpose)
    assert len(name) == length and re.fullmatch(r"[a-z0-9-]+", name)
    assert name == managed_secret_name(UUID(int=7), purpose)
    assert name != managed_secret_name(UUID(int=8), purpose)


# Names do not accept employee emails, caller-controlled paths or unsupported credential suffixes.
@pytest.mark.parametrize(
    "identity,purpose",
    [
        ("user@example.test", "automation-key"),
        (UUID(int=1), "../key"),
        (UUID(int=1), []),
    ],
)
def test_invalid_names_rejected(identity, purpose):
    with pytest.raises(ValueError, match="^MANAGED_SECRET_NAME_INVALID$"):
        managed_secret_name(identity, purpose)


# Metadata scheduling changes the revision immediately but does not hard-delete the version early.
def test_simulated_deferred_deletion(inventory, state):
    clock = {"now": NOW}
    provider = SimulatedSecretVersions([inventory], lambda: clock["now"])
    plan = plan_secret_cleanup(inventory, state, NOW)
    updated = provider.schedule_version_deletion(
        inventory.binding, 1, plan.deletion_at, plan.revision
    )
    assert updated.revision != inventory.revision
    assert updated.versions[0].deletion_at == plan.deletion_at
    assert not plan_secret_cleanup(updated, state, NOW).schedule_versions
    clock["now"] = plan.deletion_at - timedelta(microseconds=1)
    provider.reap_due_versions()
    assert len(provider.inventory(inventory.binding).versions) == 6
    clock["now"] = plan.deletion_at
    provider.reap_due_versions()
    assert [item.number for item in provider.inventory(inventory.binding).versions] == [
        2,
        3,
        4,
        5,
        6,
    ]


# Concurrent changes invalidate deletion; replay cannot extend an existing deadline.
def test_revision_conflict_and_reschedule_rejected(inventory):
    provider = SimulatedSecretVersions([inventory], lambda: NOW)
    updated = provider.schedule_version_deletion(
        inventory.binding, 1, NOW + timedelta(days=2), inventory.revision
    )
    with pytest.raises(SecretVersionConflict, match="^SECRET_VERSION_CONFLICT$"):
        provider.schedule_version_deletion(
            inventory.binding, 1, NOW + timedelta(days=3), inventory.revision
        )
    with pytest.raises(SecretVersionUnavailable, match="^SECRET_VERSION_DELETE_UNSAFE$"):
        provider.schedule_version_deletion(
            inventory.binding, 1, NOW + timedelta(days=3), updated.revision
        )


# Provider simulator rejects unsafe stages/numbers/delays without changing any observed metadata.
@pytest.mark.parametrize(
    "number,delay",
    [
        (5, timedelta(days=2)),
        (6, timedelta(days=2)),
        (99, timedelta(days=2)),
        (True, timedelta(days=2)),
        (1, timedelta(hours=23)),
        (1, timedelta(days=31)),
    ],
)
def test_simulator_rejects_unsafe_schedule(inventory, number, delay):
    provider = SimulatedSecretVersions([inventory], lambda: NOW)
    with pytest.raises(SecretVersionUnavailable, match="^SECRET_VERSION_DELETE_UNSAFE$"):
        provider.schedule_version_deletion(
            inventory.binding, number, NOW + delay, inventory.revision
        )
    assert provider.inventory(inventory.binding) == inventory


# Simulator registration never implicitly provisions a guessed or cross-credential secret.
def test_registration_and_scope_guards(inventory):
    with pytest.raises(ValueError, match="^SECRET_VERSION_REGISTRATION_INVALID$"):
        SimulatedSecretVersions([inventory, inventory], lambda: NOW)
    provider = SimulatedSecretVersions([inventory], lambda: NOW)
    for change in ({"secret_reference": "unregistered"}, {"workspace_id": "other-workspace"}):
        with pytest.raises(SecretVersionUnavailable, match="^SECRET_VERSION_UNAVAILABLE$"):
            provider.inventory(inventory.binding.model_copy(update=change))


# The simulator enforces pending capacity and refuses mutation when provider pagination is partial.
def test_simulator_capacity_and_partial_guard(inventory):
    pending = inventory.versions[-2].model_copy(
        update={"stages": frozenset({"DEPRECATED"}), "deletion_at": NOW + timedelta(days=2)}
    )
    inventory = inventory.model_copy(
        update={"versions": (inventory.versions[0], pending, inventory.versions[-1])}
    )
    provider = SimulatedSecretVersions([inventory], lambda: NOW, pending_limit=1)
    with pytest.raises(SecretVersionUnavailable):
        provider.schedule_version_deletion(
            inventory.binding, 1, NOW + timedelta(days=2), inventory.revision
        )
    partial = inventory.model_copy(update={"complete": False})
    provider = SimulatedSecretVersions([partial], lambda: NOW)
    with pytest.raises(SecretVersionUnavailable):
        provider.schedule_version_deletion(
            partial.binding, 1, NOW + timedelta(days=2), partial.revision
        )


# Capacity is explicit positive integer metadata, never a coerced bool, zero or unbounded allowance.
@pytest.mark.parametrize("limit", [True, 0, 1025])
def test_simulator_capacity_validation(limit):
    with pytest.raises(ValueError, match="^SECRET_VERSION_CAPACITY_INVALID$"):
        SimulatedSecretVersions([], lambda: NOW, pending_limit=limit)


# Invalid policy objects must not silently fall back to default retention/capacity settings.
def test_invalid_policy_does_not_fallback(inventory, state):
    with pytest.raises(ValidationError):
        plan_secret_cleanup(inventory, state, NOW, False)


# No current version means incomplete usable custody, even when a provider labels the list complete.
def test_empty_inventory_holds(inventory, state):
    result = plan_secret_cleanup(inventory.model_copy(update={"versions": ()}), state, NOW)
    assert result.held and not result.can_create_version and not result.schedule_versions


# Even corrupted fixture metadata cannot make the service-purge simulator erase a CURRENT version.
def test_simulator_preserves_protected_stage_on_reap(inventory):
    current = inventory.versions[-1].model_copy(update={"deletion_at": NOW - timedelta(days=1)})
    provider = SimulatedSecretVersions(
        [inventory.model_copy(update={"versions": (current,)})], lambda: NOW
    )
    provider.reap_due_versions()
    assert provider.inventory(inventory.binding).versions == (current,)


# A live consumer already scheduled for loss is an incident; do not admit more credential changes.
def test_explicitly_protected_scheduled_version_holds(inventory, state):
    versions = (
        inventory.versions[0].model_copy(update={"deletion_at": NOW + timedelta(days=1)}),
    ) + inventory.versions[1:]
    state = state.model_copy(update={"protected_versions": frozenset({1})})
    result = plan_secret_cleanup(inventory.model_copy(update={"versions": versions}), state, NOW)
    assert result.held and not result.schedule_versions and not result.can_create_version


# Concurrent requests with the same revision must yield exactly one accepted metadata transition.
def test_simulator_concurrent_conditional_schedule(inventory):
    provider = SimulatedSecretVersions([inventory], lambda: NOW)
    successes, conflicts = [], []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                provider.schedule_version_deletion,
                inventory.binding,
                1,
                NOW + timedelta(days=2),
                inventory.revision,
            )
            for _ in range(2)
        ]
        for future in futures:
            try:
                successes.append(future.result(timeout=5))
            except SecretVersionConflict as conflict:
                conflicts.append(str(conflict))
    assert len(successes) == 1 and conflicts == ["SECRET_VERSION_CONFLICT"]
    assert provider.inventory(inventory.binding).revision == successes[0].revision


# Temporary bootstrap custody has its own whole-secret disposal flow, not permanent retention.
def test_bootstrap_secret_not_pruned(inventory, state):
    binding = inventory.binding.model_copy(update={"purpose": "bootstrap-key"})
    inventory = inventory.model_copy(update={"binding": binding})
    state = state.model_copy(update={"binding": binding})
    result = plan_secret_cleanup(inventory, state, NOW)
    assert result.held and not result.schedule_versions and not result.can_create_version


# In-use PENDING versions already scheduled for deletion hold all additional cleanup.
def test_scheduled_pending_version_holds(inventory, state):
    candidate = SecretVersionFacts(
        number=7, stages=frozenset({"PENDING", "LATEST"}), deletion_at=NOW + timedelta(days=1)
    )
    result = plan_secret_cleanup(
        inventory.model_copy(update={"versions": inventory.versions + (candidate,)}), state, NOW
    )
    assert result.held and not result.schedule_versions
