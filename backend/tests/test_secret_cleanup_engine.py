"""Guarded cleanup executes only fresh eligible metadata plans and verifies independent readback."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import ValidationError

from otm.providers.secret_versions import (
    ManagedSecretBinding,
    SecretVersionConflict,
    SecretVersionFacts,
    SecretVersionInventory,
)
from otm.providers.secret_versions_simulator import SimulatedSecretVersions
from otm.tenancies.secret_cleanup import SecretCleanupState
from otm.tenancies.secret_cleanup_engine import SecretCleanupEngine, verified_deletion_schedule

NOW = datetime(2026, 11, 13, tzinfo=UTC)


# The fake host supplies fresh evidence while recording ownership of its serialization scope.
class Authority:
    # Snapshots can change between planning and dispatch to exercise real host-fence requirements.
    def __init__(self, evidence):
        self.evidence = [evidence]
        self.reads = 0
        self.active = False
        self.binding = evidence.binding

    # Reject another credential and release the host fence on success, hold or exception.
    @contextmanager
    def serialized(self, binding):
        assert binding == self.binding and not self.active
        self.active = True
        try:
            yield self
        finally:
            self.active = False

    # Each observation obtains current evidence rather than retaining the first plan's pins.
    def snapshot(self):
        assert self.active
        result = self.evidence[min(self.reads, len(self.evidence) - 1)]
        self.reads += 1
        return result


# This provider asserts every effect/read occurs within the trusted host's serialization scope.
class FencedProvider(SimulatedSecretVersions):
    # Retain the fake authority only to verify its fence is held; it grants no provider permissions.
    def __init__(self, inventory, authority):
        super().__init__([inventory], lambda: NOW)
        self.authority = authority
        self.writes = []

    # Reads outside the future worker's credential fence must not be hidden by this test harness.
    def inventory(self, binding):
        assert self.authority.active
        return super().inventory(binding)

    # Preserve the conditional revision and original deletion time for replay assertions.
    def schedule_version_deletion(self, binding, number, deletion_at, expected_revision):
        assert self.authority.active
        self.writes.append((number, deletion_at, expected_revision))
        return super().schedule_version_deletion(binding, number, deletion_at, expected_revision)


# All fixtures are metadata-only, with real application-style string workspace scope.
@pytest.fixture
def case():
    binding = ManagedSecretBinding(
        workspace_id="cleanup-workspace",
        credential_id=UUID(int=1),
        secret_reference="synthetic-secret",
        purpose="automation-key",
    )
    inventory = SecretVersionInventory(
        binding=binding,
        revision="revision-one",
        complete=True,
        versions=(
            SecretVersionFacts(number=1, stages=frozenset({"DEPRECATED"})),
            SecretVersionFacts(number=3, stages=frozenset({"DEPRECATED"})),
            SecretVersionFacts(number=4, stages=frozenset({"DEPRECATED"})),
            SecretVersionFacts(number=5, stages=frozenset({"DEPRECATED"})),
            SecretVersionFacts(number=6, stages=frozenset({"PREVIOUS"})),
            SecretVersionFacts(number=7, stages=frozenset({"CURRENT", "LATEST"})),
        ),
    )
    evidence = SecretCleanupState(
        binding=binding,
        protected_versions=frozenset(),
        rotation_resolved=True,
    )
    authority = Authority(evidence)
    provider = FencedProvider(inventory, authority)
    engine = SecretCleanupEngine(provider, authority, lambda: NOW)
    return binding, inventory, evidence, authority, provider, engine


# Schedule/readback is serialized and replay performs no second write or deletion-time extension.
def test_verified_batch_and_replay(case):
    binding, _, _, authority, provider, engine = case
    result = engine.run(binding)
    assert result.state == "complete" and result.scheduled_versions == (1,)
    assert len(provider.writes) == 1 and not authority.active
    first_write = provider.writes[0]
    replay = engine.run(binding)
    assert replay.state == "complete" and not replay.scheduled_versions
    assert provider.writes == [first_write] and not authority.active


# A newly protected historical consumer invalidates the earlier deletion candidate before dispatch.
def test_fresh_consumer_pin_prevents_write(case):
    binding, _, evidence, authority, provider, engine = case
    authority.evidence.append(evidence.model_copy(update={"protected_versions": frozenset({1})}))
    result = engine.run(binding)
    assert result.state == "complete" and not result.scheduled_versions
    assert authority.reads == 2 and not provider.writes and not authority.active


# Unresolved rotations stop the run without acquiring any provider mutation authority.
def test_held_initial_plan(case):
    binding, _, evidence, authority, provider, engine = case
    authority.evidence = [evidence.model_copy(update={"rotation_resolved": False})]
    result = engine.run(binding)
    assert result.state == "held" and not provider.writes and not authority.active


# Each next candidate is rechecked; earlier known scheduling remains visible if later work is held.
def test_partial_batch_stops_on_new_hold(case):
    binding, inventory, evidence, authority, _, _ = case
    inventory = inventory.model_copy(
        update={
            "versions": inventory.versions
            + (SecretVersionFacts(number=2, stages=frozenset({"DEPRECATED"})),)
        }
    )
    authority.evidence = [
        evidence,
        evidence,
        evidence.model_copy(update={"rotation_resolved": False}),
    ]
    provider = FencedProvider(inventory, authority)
    result = SecretCleanupEngine(provider, authority, lambda: NOW).run(binding)
    assert result.state == "held" and result.scheduled_versions == (1,)
    assert len(provider.writes) == 1 and not authority.active


# Each eligible version uses the latest provider revision, never a stale first token.
def test_multiple_candidates_refresh_revision(case):
    binding, inventory, evidence, _, _, _ = case
    inventory = inventory.model_copy(
        update={
            "versions": inventory.versions
            + (SecretVersionFacts(number=2, stages=frozenset({"DEPRECATED"})),)
        }
    )
    authority = Authority(evidence)
    provider = FencedProvider(inventory, authority)
    result = SecretCleanupEngine(provider, authority, lambda: NOW).run(binding)
    assert result.state == "complete" and result.scheduled_versions == (1, 2)
    assert provider.writes[0][2] != provider.writes[1][2]
    assert authority.reads == 3 and not authority.active


# A provider-side concurrency rejection is bounded and never retried unconditionally in place.
def test_conflict_is_not_blindly_retried(case):
    binding, _, _, authority, provider, engine = case
    provider.schedule_version_deletion = Mock(side_effect=SecretVersionConflict("private-detail"))
    result = engine.run(binding)
    assert result.state == "conflict" and not result.scheduled_versions
    assert provider.schedule_version_deletion.call_count == 1 and not authority.active
    assert "private-detail" not in result.model_dump_json()


# Read failure before dispatch is unavailable; possible write effects are explicitly unverified.
@pytest.mark.parametrize(
    "method,state", [("inventory", "unavailable"), ("schedule_version_deletion", "unverified")]
)
def test_private_provider_errors_are_normalized(case, method, state):
    binding, _, _, authority, provider, engine = case
    setattr(provider, method, Mock(side_effect=RuntimeError("private-provider-detail")))
    result = engine.run(binding)
    assert result.state == state and not result.scheduled_versions and not authority.active
    assert "private-provider-detail" not in result.model_dump_json()


# A lost scheduling response is reconciled by fresh metadata on replay without extending its time.
def test_lost_response_reconciles_without_reschedule(case):
    binding, _, _, authority, provider, engine = case
    original = provider.schedule_version_deletion

    # Model a committed provider mutation followed by transport loss.
    def lost_response(*args):
        original(*args)
        raise TimeoutError("private-transport-detail")

    provider.schedule_version_deletion = lost_response
    first = engine.run(binding)
    assert first.state == "unverified" and len(provider.writes) == 1 and not authority.active
    provider.schedule_version_deletion = original
    replay = engine.run(binding)
    assert (
        replay.state == "complete" and not replay.scheduled_versions and len(provider.writes) == 1
    )


# Boundaries never turn mismatched evidence or inventory into writes to a different secret.
@pytest.mark.parametrize("source", ["evidence", "inventory"])
def test_mismatched_scope_is_unavailable(case, source):
    binding, inventory, evidence, authority, provider, engine = case
    other = binding.model_copy(update={"workspace_id": "other-workspace"})
    if source == "evidence":
        authority.evidence = [evidence.model_copy(update={"binding": other})]
    else:
        provider.inventory = Mock(return_value=inventory.model_copy(update={"binding": other}))
    result = engine.run(binding)
    assert result.state == "unavailable" and not provider.writes and not authority.active


# A malformed mutation response cannot become verified success or leak raw provider payloads.
def test_invalid_response_is_unverified(case):
    binding, _, _, authority, provider, engine = case
    provider.schedule_version_deletion = Mock(return_value={"private_data": "synthetic"})
    result = engine.run(binding)
    assert result.state == "unverified" and not result.scheduled_versions and not authority.active


# Scheduling acceptance alone is insufficient when independent metadata readback shows no effect.
def test_no_readback_effect_is_unverified(case):
    binding, inventory, _, authority, provider, engine = case
    provider.schedule_version_deletion = Mock(return_value=inventory)
    result = engine.run(binding)
    assert result.state == "unverified" and not result.scheduled_versions and not authority.active


# A successful-looking response for another target must not be accepted as the requested mutation.
def test_wrong_response_binding_is_unverified(case):
    binding, inventory, _, authority, provider, engine = case
    other = inventory.model_copy(
        update={"binding": binding.model_copy(update={"secret_reference": "other-secret"})}
    )
    provider.schedule_version_deletion = Mock(return_value=other)
    result = engine.run(binding)
    assert result.state == "unverified" and not result.scheduled_versions and not authority.active


# Reject changed stages/targets/revisions, missing versions and collateral readback changes.
@pytest.mark.parametrize(
    "mutation", ["partial", "scope", "revision", "missing", "stage", "time", "other"]
)
def test_readback_rejects_inconsistent_observations(case, mutation):
    binding, before, _, _, _, _ = case
    deletion_at = NOW + timedelta(days=2)
    versions = (
        before.versions[0].model_copy(update={"deletion_at": deletion_at}),
    ) + before.versions[1:]
    after = before.model_copy(update={"revision": "revision-two", "versions": versions})
    if mutation == "partial":
        after = after.model_copy(update={"complete": False})
    if mutation == "scope":
        after = after.model_copy(
            update={"binding": binding.model_copy(update={"workspace_id": "other"})}
        )
    if mutation == "revision":
        after = after.model_copy(update={"revision": before.revision})
    if mutation == "missing":
        after = after.model_copy(update={"versions": versions[1:]})
    if mutation == "stage":
        after = after.model_copy(
            update={
                "versions": (versions[0].model_copy(update={"stages": frozenset({"CURRENT"})}),)
                + versions[1:]
            }
        )
    if mutation == "time":
        after = after.model_copy(
            update={
                "versions": (
                    versions[0].model_copy(update={"deletion_at": deletion_at + timedelta(days=1)}),
                )
                + versions[1:]
            }
        )
    if mutation == "other":
        after = after.model_copy(
            update={
                "versions": versions[:1]
                + (versions[1].model_copy(update={"stages": frozenset({"PENDING"})}),)
                + versions[2:]
            }
        )
    assert not verified_deletion_schedule(before, after, 1, deletion_at)


# Real application workspace scope is a string and must not be silently coerced from another type.
def test_workspace_scope_uses_application_contract(case):
    binding, _, _, _, _, _ = case
    assert binding.workspace_id == "cleanup-workspace"
    with pytest.raises(ValidationError):
        ManagedSecretBinding.model_validate(
            binding.model_copy(update={"workspace_id": UUID(int=7)})
        )
