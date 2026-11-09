"""Exact assignment reads, legacy safety and sealed UI projection without external resources."""

import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from test_user_presence_check_units import case

from otm.operations.contracts import canonical_hash
from otm.providers.administrator_access import (
    AdministratorAccessInspection,
    AdministratorCapture,
    AdministratorCheck,
    AdministratorObservation,
    AdministratorResult,
    InspectAdministratorAccess,
    assess_assignments,
)
from otm.providers.administrator_access_simulator import (
    SimulatedAdministratorAccessProvider,
    configured_administrator_capture,
    simulated_administrator_inspection,
)
from otm.providers.inspection import ProviderContractError
from otm.providers.lifecycle import OnboardingUsers
from otm.tenancies.presence import administrator_view
from otm.tenancies.presence_contracts import AdministratorAccessView, PresenceCheckEvidence
from otm.tenancies.presence_records import decode_result


# Fixtures represent independently retained setup facts rather than inferred expected membership.
def configured():
    c = case()
    capture = configured_administrator_capture(
        c.source.domain_ocid, c.source.automation.scim_resource_id, "synthetic"
    )
    c.source = c.source.model_copy(update={"automation_administrator": capture})
    c.worker.administrator_inspection_factory = simulated_administrator_inspection
    c.command = InspectAdministratorAccess(
        context=c.commands[0].context, target=c.commands[0].target, binding=capture.binding
    )
    return c


# Both complete direct grants and explicit grants via the exact built-in group are supported.
@pytest.mark.parametrize("direct", [False, True])
def test_supported_assignments(direct):
    c = configured()
    capture = c.source.automation_administrator
    facts = (
        capture.facts.model_copy(
            update={"role_users": (capture.binding.scim_resource_id,), "role_groups": ()}
        )
        if direct
        else capture.facts
    )
    result = assess_assignments(capture.binding, facts)
    assert result == AdministratorResult(group="verified", domain_role="verified")
    read = c.worker.read_administrator(c.commands[0], c.source)
    assert read.target == c.commands[0].target and read.result.group == "verified"
    assert OnboardingUsers.model_validate_json(c.source.model_dump_json()) == c.source
    assert "group_members" not in repr(c.source)


# Complete negative evidence is distinct from incomplete, denied and unsupported evidence.
@pytest.mark.parametrize(
    "damage,group,role",
    [
        ({"group_members": ()}, "missing", "missing"),
        ({"role_groups": ()}, "verified", "missing"),
        ({"group_enabled": False}, "missing", "missing"),
        ({"role_enabled": False}, "verified", "missing"),
        ({"user_enabled": False}, "missing", "missing"),
        ({"authorized": False}, "unknown", "unknown"),
        ({"complete": False}, "unknown", "unknown"),
        ({"supported": False}, "unknown", "unknown"),
        ({"builtin_group": False}, "unknown", "unknown"),
    ],
)
def test_independent_assignment_results(damage, group, role):
    c = configured()
    capture = c.source.automation_administrator
    facts = capture.facts.model_copy(update=damage)
    assert assess_assignments(capture.binding, facts) == AdministratorResult(
        group=group, domain_role=role
    )


# Wrong application, role, group, domain or account cannot satisfy a requested assignment read.
@pytest.mark.parametrize(
    "field", ["domain_ocid", "scim_resource_id", "group_id", "application_id", "role_id"]
)
def test_wrong_resource_scope(field):
    c = configured()
    capture = c.source.automation_administrator
    facts = capture.facts.model_copy(
        update={"binding": capture.binding.model_copy(update={field: "different"})}
    )
    assert assess_assignments(capture.binding, facts).group == "unknown"
    inspection = AdministratorAccessInspection(
        SimulatedAdministratorAccessProvider(facts, c.clock), c.clock
    )
    with pytest.raises(ProviderContractError, match="ADMINISTRATOR_ACCESS_UNVERIFIED"):
        inspection.inspect(c.command)
    with pytest.raises(ValueError):
        AdministratorCapture(binding=capture.binding, facts=facts)


# Malformed/cross-attempt/late provider facts produce only fixed boundary failures.
@pytest.mark.parametrize(
    "damage", ["context", "target", "past", "future", "slow", "malformed", "exception"]
)
def test_boundary_provenance(damage):
    c = configured()
    observation = AdministratorObservation(
        context=c.command.context,
        target=c.command.target,
        captured_at=c.clock(),
        facts=c.source.automation_administrator.facts,
    )
    provider = Mock()
    if damage == "context":
        observation = observation.model_copy(
            update={"context": observation.context.model_copy(update={"connection_revision": 2})}
        )
    if damage == "target":
        observation = observation.model_copy(update={"target": c.commands[1].target})
    if damage == "past":
        observation = observation.model_copy(
            update={"captured_at": c.clock() - timedelta(seconds=1)}
        )
    if damage == "future":
        observation = observation.model_copy(
            update={"captured_at": c.clock() + timedelta(seconds=1)}
        )
    if damage == "malformed":
        observation = {"secret": "never print provider errors"}
    provider.inspect_administrator_access.return_value = observation
    if damage == "exception":
        provider.inspect_administrator_access.side_effect = RuntimeError("sensitive-provider-text")
    clock = (
        Mock(side_effect=[c.clock(), c.clock() + timedelta(seconds=31)])
        if damage == "slow"
        else c.clock
    )
    with pytest.raises(ProviderContractError, match="^ADMINISTRATOR_ACCESS_UNVERIFIED$"):
        AdministratorAccessInspection(provider, clock).inspect(c.command)


# Failed or legacy reads cannot infer authority from the already-present account.
@pytest.mark.parametrize(
    "damage", ["legacy", "factory", "wrong_target", "late", "no_source", "no_factory"]
)
def test_worker_fails_closed(damage):
    c = configured()
    if damage == "legacy":
        c.source = c.source.model_copy(update={"automation_administrator": None})
    if damage == "no_source":
        c.source = None
    if damage == "no_factory":
        c.worker.administrator_inspection_factory = None
    if damage == "factory":
        c.worker.administrator_inspection_factory = Mock(side_effect=RuntimeError("private"))
    if damage in {"wrong_target", "late"}:
        observed = c.worker.read_administrator(c.commands[0], c.source)
        changed = (
            {"target": c.commands[1].target}
            if damage == "wrong_target"
            else {"checked_at": c.clock() + timedelta(seconds=1)}
        )
        c.worker.administrator_inspection_factory = Mock(
            return_value=Mock(inspect=Mock(return_value=observed.model_copy(update=changed)))
        )
    observed = c.worker.read_administrator(c.commands[0], c.source)
    assert observed.result == AdministratorResult(group="unknown", domain_role="unknown")


# Existing immutable evidence owns persistence; context compatibility/age never invents proof.
def test_sealed_projection_and_history():
    c = configured()
    read = c.worker.read_administrator(c.commands[0], c.source)
    evidence = c.evidence.model_copy(update={"administrator_access": read})
    payload = evidence.model_dump(mode="json")
    event = {"data": payload, "data_hash": canonical_hash(payload)}
    assert decode_result(c.check, payload, event["data_hash"]).administrator_access == read
    current = administrator_view(c.snapshot, c.check, event, c.clock())
    assert current.group == "verified" and current.domain_role == "verified" and not current.stale
    assert administrator_view(c.snapshot, c.check, event, c.clock() + timedelta(days=1)).stale
    assert (
        administrator_view(
            c.snapshot.model_copy(update={"tenancy_revision": 2}), c.check, event, c.clock()
        ).group
        == "verified"
    )
    assert (
        administrator_view(
            c.snapshot.model_copy(update={"connection_revision": 2}), c.check, event, c.clock()
        ).group
        == "not_checked"
    )
    assert administrator_view(None, c.check, event, c.clock()).group == "not_checked"
    assert administrator_view(c.snapshot, None, None, c.clock()) == AdministratorAccessView()
    legacy = {"data": c.payload, "data_hash": canonical_hash(c.payload)}
    assert administrator_view(c.snapshot, c.check, legacy, c.clock()).group == "not_checked"
    bad = payload | {
        "administrator_access": read.model_copy(
            update={"context": read.context.model_copy(update={"connection_revision": 2})}
        ).model_dump(mode="json")
    }
    with pytest.raises(ValueError):
        PresenceCheckEvidence.model_validate_json(json.dumps(bad))


# Closed models reject cross-subject capture and unproven positive display states.
def test_contract_guards():
    c = configured()
    with pytest.raises(ValueError):
        InspectAdministratorAccess(
            context=c.command.context, target=c.commands[1].target, binding=c.command.binding
        )
    with pytest.raises(ValueError):
        InspectAdministratorAccess(
            context=c.command.context,
            target=c.command.target,
            binding=c.command.binding.model_copy(update={"scim_resource_id": "other"}),
        )
    with pytest.raises(ValueError):
        AdministratorCheck(
            context=c.command.context,
            target=c.commands[1].target,
            checked_at=c.clock(),
            result=AdministratorResult(group="verified", domain_role="verified"),
        )
    with pytest.raises(ValueError):
        AdministratorAccessView(group="verified")
    damaged = c.source.model_dump(mode="json")
    damaged["automation_administrator"]["binding"]["domain_ocid"] = "other"
    with pytest.raises(ValueError):
        OnboardingUsers.model_validate_json(json.dumps(damaged))
    with pytest.raises(ValueError):
        simulated_administrator_inspection(
            c.command, c.source.model_copy(update={"automation_administrator": None}), c.clock
        )


# Dispatcher carries an independent assignment read through its existing terminal publication hook.
def test_worker_dispatches_assignments():
    c = configured()
    c.worker.begin = Mock(return_value=(c.frozen, c.check, c.commands, c.source))
    c.worker.finish = Mock()
    c.worker.run(c.row["id"])
    assert c.worker.finish.call_args.args[-1].result.group == "verified"


# Existing publication fences downgrade assignment proof along with stale read attempts.
@pytest.mark.parametrize("fault", ["changed", "slow"])
def test_publication_fences_assignment_results(fault):
    c = configured()
    observed = c.worker.read_administrator(c.commands[0], c.source)
    check = c.check | {"state": "reading"}
    c.worker.locked = Mock(return_value=(c.row, c.frozen, c.child, check))
    c.worker.current = Mock(return_value=fault != "changed")
    if fault == "slow":
        c.clock.return_value += timedelta(seconds=31)
    with patch("otm.tenancies.presence_worker.seal") as seal:
        c.worker.finish(
            c.row["id"], check["attempt_id"], c.commands, c.results, assignments=observed
        )
        assert seal.call_args.kwargs["administrator_access"].result.group == "unknown"
