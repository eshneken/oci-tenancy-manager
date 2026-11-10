"""Read-only signing-key evidence stays scoped, dated and independent of private credentials."""

import os
from datetime import timedelta
from functools import partial
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_user_presence_check_units import case

from otm.operations.contracts import canonical_hash
from otm.providers.automation_keys import (
    AutomationKeyCheck,
    AutomationKeyFacts,
    AutomationKeyInspection,
    AutomationKeyObservation,
    InspectAutomationKeys,
    ObservedAutomationKey,
    key_age,
)
from otm.providers.automation_keys_simulator import (
    SimulatedAutomationKeys,
    simulated_key_inspection,
)
from otm.providers.lifecycle import OnboardingUsers
from otm.tenancies.automation_keys import AutomationKeysView, inventory_view
from otm.tenancies.presence import automation_keys_view
from otm.tenancies.presence_contracts import PresenceCheckEvidence


# Reuse independently produced exact-user facts, without a database or usable key pair.
def fixture():
    c = case()
    c.command = InspectAutomationKeys(context=c.commands[0].context, target=c.commands[0].target)
    c.key = ObservedAutomationKey(
        provider_key_id="synthetic-key",
        fingerprint=":".join(["ab"] * 16),
        created_at=c.clock() - timedelta(days=2),
        state="active",
    )
    c.facts = AutomationKeyFacts(
        user=c.source.automation, authorized=True, complete=True, supported=True, keys=(c.key,)
    )
    c.observed = AutomationKeyObservation(
        context=c.command.context, target=c.command.target, captured_at=c.clock(), facts=c.facts
    )
    c.provider = Mock()
    c.provider.inspect_automation_keys.return_value = c.observed
    c.inspection = AutomationKeyInspection(c.provider, c.clock)
    c.keys = c.inspection.inspect(c.command)
    return c


# One authorized complete read can prove zero keys, unlike incomplete or denied enumeration.
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "authorized",
        "complete",
        "supported",
        "user",
        "context",
        "target",
        "past",
        "future",
        "slow",
    ],
)
def test_qualified_inventory(damage):
    c = fixture()
    if damage in {"authorized", "complete", "supported"}:
        c.observed = c.observed.model_copy(
            update={"facts": c.facts.model_copy(update={damage: False})}
        )
    if damage == "user":
        c.observed = c.observed.model_copy(
            update={"facts": c.facts.model_copy(update={"user": c.source.recovery})}
        )
    if damage == "context":
        c.observed = c.observed.model_copy(
            update={"context": c.command.context.model_copy(update={"connection_revision": 2})}
        )
    if damage == "target":
        c.observed = c.observed.model_copy(
            update={"target": c.command.target.model_copy(update={"user_name": "other"})}
        )
    if damage in {"past", "future"}:
        c.observed = c.observed.model_copy(
            update={"captured_at": c.clock() + timedelta(seconds=1 if damage == "future" else -1)}
        )
    c.provider.inspect_automation_keys.return_value = c.observed
    if damage == "slow":
        c.clock.side_effect = [c.clock.return_value, c.clock.return_value + timedelta(seconds=31)]
    result = c.inspection.inspect(c.command)
    assert result.state == ("known" if damage is None else "unavailable")
    assert bool(result.keys) == (damage is None)
    if damage is None:
        c.provider.inspect_automation_keys.return_value = c.observed.model_copy(
            update={"facts": c.facts.model_copy(update={"keys": ()})}
        )
        assert c.inspection.inspect(c.command).keys == ()


# Ages use original creation time and exact 29/30-day boundaries; unsupported dates stay unknown.
@pytest.mark.parametrize(
    "days,state",
    [
        (0, "within_limit"),
        (28.999, "within_limit"),
        (29, "due_soon"),
        (29.999, "due_soon"),
        (30, "overdue"),
        (45, "overdue"),
        (-1, "unknown"),
    ],
)
def test_age_boundaries(days, state):
    c = fixture()
    key = c.key.model_copy(update={"created_at": c.clock() - timedelta(days=days)})
    assert key_age(key, c.clock())[0] == state
    assert key_age(key.model_copy(update={"created_at": None}), c.clock()) == ("unknown", None)
    assert key_age(key.model_copy(update={"state": "inactive"}), c.clock()) == ("inactive", None)
    assert key_age(key.model_copy(update={"state": "unknown"}), c.clock()) == ("unknown", None)


# Closed boundaries reject recovery subjects, duplicate/oversized rows and unqualified projections.
def test_contract_rejections():
    c = fixture()
    for payload in [
        dict(c.command.model_dump(), target=c.commands[1].target),
        dict(
            c.command.model_dump(),
            context=c.command.context.model_copy(update={"workspace_id": "other"}),
        ),
    ]:
        with pytest.raises(ValueError):
            InspectAutomationKeys(**payload)
    for keys in [(c.key, c.key), tuple(c.key for _ in range(17))]:
        with pytest.raises(ValueError):
            AutomationKeyFacts(**{**c.facts.model_dump(), "keys": keys})
        with pytest.raises(ValueError):
            AutomationKeyCheck(**{**c.keys.model_dump(), "keys": keys})
    with pytest.raises(ValueError):
        AutomationKeyCheck(**{**c.keys.model_dump(), "state": "unavailable"})
    with pytest.raises(ValueError):
        AutomationKeysView(state="known")
    with pytest.raises(ValueError):
        AutomationKeysView(
            state="unavailable", keys=inventory_view(c.keys, uuid4(), c.clock()).keys
        )
    with pytest.raises(ValueError):
        ObservedAutomationKey(**{**c.key.model_dump(), "fingerprint": "malformed"})
    with pytest.raises(ValueError):
        ObservedAutomationKey(**{**c.key.model_dump(), "private_key": "not allowed"})
    assert "automation_keys" not in c.source.model_dump()
    assert OnboardingUsers.model_validate_json(c.source.model_dump_json()) == c.source


# Retained original metadata survives process restarts/retries; GETs never populate missing files.
def test_simulator_persistence_and_scope(tmp_path):
    c = fixture()
    path = tmp_path / "keys"
    store = SimulatedAutomationKeys(path, c.clock)
    with pytest.raises(FileNotFoundError):
        store.read(c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation)
    assert not list(path.iterdir())
    capture = store.configure(
        c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation
    )
    c.clock.return_value += timedelta(days=5)
    restarted = SimulatedAutomationKeys(path, c.clock)
    assert (
        restarted.configure(c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation)
        == capture
    )
    c.source = c.source.model_copy(update={"automation_keys": capture})
    result = simulated_key_inspection(restarted, c.command, c.source, c.clock).inspect(c.command)
    assert result.state == "known" and result.keys[0].created_at == capture.facts.keys[0].created_at
    for scope in [
        ("other", c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation),
        (c.a.workspace_id, c.a.tenancy_id, "other", c.source.automation),
        (c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.recovery),
    ]:
        with pytest.raises(ValueError, match="SCOPE"):
            store.read(*scope)
    for method in [store.read, store.configure]:
        with pytest.raises(ValueError, match="TARGET"):
            method(c.a.workspace_id, "../bad", c.a.tenancy_ocid, c.source.automation)
    with pytest.raises(ValueError):
        simulated_key_inspection(
            store, c.command, c.source.model_copy(update={"automation_keys": None}), c.clock
        )
    with pytest.raises(ValueError):
        OnboardingUsers.model_validate(
            c.source.model_copy(
                update={
                    "automation_keys": capture.model_copy(
                        update={
                            "facts": capture.facts.model_copy(update={"user": c.source.recovery})
                        }
                    )
                }
            )
        )


# Shared, redirected, oversized and hardlinked fixture files cannot become authoritative inventory.
@pytest.mark.parametrize(
    "damage",
    ["permissions", "symlink", "hardlink", "oversized", "root-permissions", "root-symlink"],
)
def test_simulator_file_guards(tmp_path, damage):
    c = fixture()
    root = tmp_path / "keys"
    store = SimulatedAutomationKeys(root, c.clock)
    store.configure(c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation)
    path = root / (c.a.tenancy_id.hex + ".json")
    if damage == "permissions":
        path.chmod(0o644)
    if damage in {"symlink", "hardlink"}:
        copy = tmp_path / "copy"
        path.rename(copy)
        if damage == "symlink":
            path.symlink_to(copy)
        else:
            os.link(copy, path)
    if damage == "oversized":
        path.write_bytes(b" " * 16385)
    if damage == "root-permissions":
        root.chmod(0o755)
    if damage == "root-symlink":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        with pytest.raises(ValueError):
            SimulatedAutomationKeys(link, c.clock)
        return
    with pytest.raises((OSError, ValueError)):
        store.read(c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation)


# Missing, wrong-scope, malformed and delayed factories fail closed without leaking provider text.
@pytest.mark.parametrize(
    "damage", ["none", "legacy", "exception", "malformed", "target", "context", "slow", "good"]
)
def test_worker_reads(damage, tmp_path):
    c = fixture()
    store = SimulatedAutomationKeys(tmp_path / "keys", c.clock)
    capture = store.configure(
        c.a.workspace_id, c.a.tenancy_id, c.a.tenancy_ocid, c.source.automation
    )
    c.source = c.source.model_copy(update={"automation_keys": capture})
    c.worker.key_inspection_factory = partial(simulated_key_inspection, store)
    if damage == "none":
        c.worker.key_inspection_factory = None
    if damage == "legacy":
        c.source = c.source.model_copy(update={"automation_keys": None})
    if damage == "exception":
        c.worker.key_inspection_factory = Mock(side_effect=RuntimeError("private error"))
    if damage in {"malformed", "target", "context", "slow"}:
        value = c.keys
        if damage == "target":
            value = value.model_copy(
                update={"target": c.command.target.model_copy(update={"user_name": "other"})}
            )
        if damage == "context":
            value = value.model_copy(
                update={"context": c.command.context.model_copy(update={"connection_revision": 2})}
            )
        if damage == "malformed":
            value = {"secret": "not returned"}
        c.worker.key_inspection_factory = Mock(return_value=Mock(inspect=Mock(return_value=value)))
        if damage == "slow":
            c.clock.side_effect = [
                c.clock.return_value,
                c.clock.return_value,
                c.clock.return_value + timedelta(seconds=31),
            ]
    result = c.worker.read_keys(c.commands[0], c.source)
    assert (
        result is None
        if damage == "none"
        else result.state == ("known" if damage == "good" else "unavailable")
    )
    c.clock.side_effect = None
    if damage != "none":
        assert c.worker.read_keys(c.commands[0], None).state == "unavailable"


# Sealed observations preserve legacy bytes and current-versus-historical age semantics.
def test_sealed_projection():
    c = fixture()
    evidence = c.evidence.model_copy(update={"automation_keys": c.keys})
    payload = evidence.model_dump(mode="json")
    event = {"data": payload, "data_hash": canonical_hash(payload)}
    view = automation_keys_view(c.snapshot, c.check, event, c.clock())
    assert view.state == "known" and view.keys[0].age_days == 2
    later = c.clock() + timedelta(days=28)
    assert automation_keys_view(c.snapshot, c.check, event, later).keys[0].age_state == "overdue"
    assert automation_keys_view(c.snapshot, c.check, event, later).state == "stale"
    assert (
        inventory_view(c.keys, c.row["id"], c.keys.checked_at).keys[0].age_state == "within_limit"
    )
    bad = c.keys.model_copy(
        update={"keys": (c.key.model_copy(update={"created_at": c.clock() + timedelta(days=1)}),)}
    )
    assert inventory_view(bad, c.row["id"], later).keys[0].age_state == "unknown"
    fresh = bad.model_copy(update={"checked_at": later})
    assert inventory_view(fresh, c.row["id"], later).keys[0].age_state == "within_limit"
    assert inventory_view(None, c.row["id"], later).state == "not_checked"
    assert (
        inventory_view(
            c.keys.model_copy(update={"state": "unavailable", "keys": ()}), c.row["id"], later
        ).state
        == "unavailable"
    )
    assert automation_keys_view(c.snapshot, None, None, c.clock()).state == "not_checked"
    legacy = {
        "data": c.evidence.model_dump(mode="json"),
        "data_hash": canonical_hash(c.evidence.model_dump(mode="json")),
    }
    assert automation_keys_view(c.snapshot, c.check, legacy, c.clock()).state == "unavailable"
    different = c.snapshot.model_copy(update={"connection_revision": 2})
    assert automation_keys_view(different, c.check, event, c.clock()).state == "unavailable"
    for update in [
        {"context": c.keys.context.model_copy(update={"connection_revision": 2})},
        {"checked_at": c.clock() + timedelta(seconds=1)},
    ]:
        with pytest.raises(ValueError):
            PresenceCheckEvidence.model_validate(
                evidence.model_copy(update={"automation_keys": c.keys.model_copy(update=update)})
            )


# Changed authority and expired attempts discard observed key rows before sealing publication.
@pytest.mark.parametrize("fault", ["changed", "slow", "clock", "future", "good"])
def test_publication_fences(fault):
    c = fixture()
    check = c.check | {"state": "reading"}
    c.worker.locked = Mock(return_value=(c.row, c.frozen, c.child, check))
    c.worker.current = Mock(return_value=fault != "changed")
    keys = c.keys
    if fault == "slow":
        c.clock.return_value += timedelta(seconds=31)
    if fault == "clock":
        c.clock.return_value -= timedelta(seconds=1)
    if fault == "future":
        keys = keys.model_copy(update={"checked_at": c.clock() + timedelta(seconds=1)})
    with patch("otm.tenancies.presence_worker.seal") as seal:
        c.worker.finish(c.row["id"], check["attempt_id"], c.commands, c.results, keys=keys)
        result = seal.call_args.kwargs["automation_keys"]
        assert result.state == ("known" if fault == "good" else "unavailable")
        assert bool(result.keys) == (fault == "good")
    c.worker.begin = Mock(return_value=(c.frozen, c.check, c.commands, c.source))
    c.worker.finish = Mock()
    c.worker.run(c.row["id"])
    assert "keys" in c.worker.finish.call_args.kwargs
