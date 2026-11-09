"""Perimeter repair remains scoped, conditional and independently verified with synthetic facts."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from test_admission_service import NOW
from test_recovery_console import policy_case as policy_case

from otm.providers.inspection import ProviderContractError
from otm.providers.recovery_console import RecoveryConsoleCapture, evaluate_console
from otm.providers.recovery_network import RecoveryNetworkOutcome, RecoveryNetworkRepair
from otm.providers.recovery_network_simulator import (
    SimulatedRecoveryNetworkProvider,
    simulated_network_repair,
)
from otm.recovery_console import RecoveryConsoleSettings


# Desired settings and actual producer facts intentionally differ before every repair.
@pytest.fixture
def network_case(policy_case):
    command, facts = policy_case
    command = command.model_copy(
        update={
            "target": command.target.model_copy(
                update={"tenancy_ocid": "ocid1.tenancy.oc1..otmsimnetwork"}
            ),
            "desired": RecoveryConsoleSettings(allowed_cidrs=["203.0.113.0/24"]),
        }
    )
    capture = RecoveryConsoleCapture(
        binding=command.binding, scim_resource_id=command.target.scim_resource_id, facts=facts
    )
    provider = SimulatedRecoveryNetworkProvider(command, capture, lambda: NOW)
    return command, capture, provider, RecoveryNetworkRepair(provider, lambda: NOW)


# A successful repair preserves all unrelated policy facts and requires a separate post-write read.
def test_conditional_repair_preserves_rules(network_case):
    command, before, provider, boundary = network_case
    authority = boundary.preview(command)
    assert evaluate_console(command, authority.facts).network_boundary == "drift"
    outcome = boundary.apply(authority)
    assert outcome.effect == "known"
    assert outcome.capture.facts.rules == before.facts.rules
    assert outcome.capture.facts.perimeter == command.desired
    assert evaluate_console(command, outcome.capture.facts).state == "verified"
    with pytest.raises(ProviderContractError):
        boundary.preview(command)
    with pytest.raises(ProviderContractError):
        provider.inspect_network_authority(command.model_copy(update={"binding": None}))


# No read, group membership or desired state can stand in for conditional-write authorization.
@pytest.mark.parametrize("field", ["can_replace_perimeter", "conditional_update", "owns_perimeter"])
def test_missing_authority_blocks_before_write(network_case, field):
    command, _, provider, boundary = network_case
    original = provider.inspect_network_authority(command)
    provider.inspect_network_authority = Mock(
        return_value=original.model_copy(update={field: False})
    )
    provider.replace_network = Mock()
    with pytest.raises(ProviderContractError):
        boundary.preview(command)
    provider.replace_network.assert_not_called()


# A stale or wrong-context authority cannot be reused even when the desired union is unchanged.
@pytest.mark.parametrize("change", ["time", "command", "expired", "exception"])
def test_authority_context_and_time(network_case, change):
    command, _, provider, boundary = network_case
    authority = provider.inspect_network_authority(command)
    if change == "exception":
        provider.inspect_network_authority = Mock(side_effect=RuntimeError("private details"))
    else:
        updates = {"captured_at": NOW - timedelta(seconds=1)} if change == "time" else {}
        if change == "command":
            updates["command"] = command.model_copy(
                update={"desired": RecoveryConsoleSettings(allowed_cidrs=["192.0.2.0/24"])}
            )
        if change == "expired":
            boundary.clock = Mock(side_effect=[NOW, NOW + timedelta(seconds=31)])
        provider.inspect_network_authority = Mock(return_value=authority.model_copy(update=updates))
    with pytest.raises(ProviderContractError, match="RECOVERY_NETWORK_REPAIR_BLOCKED"):
        boundary.preview(command)


# Changing actual state after preview requires a new reviewed plan rather than a broader write.
def test_changed_before_state_blocks_write(network_case):
    command, _, provider, boundary = network_case
    authority = boundary.preview(command)
    provider.capture = provider.capture.model_copy(
        update={
            "facts": provider.capture.facts.model_copy(
                update={"perimeter": RecoveryConsoleSettings(allowed_cidrs=["192.0.2.0/24"])}
            )
        }
    )
    assert boundary.apply(authority).effect == "none"
    result = provider.replace_network(type("Command", (), {"authority": authority})())
    assert result.effect == "none"
    altered = authority.model_copy(update={"compare_token": "obsolete"})
    assert provider.replace_network(type("Command", (), {"authority": altered})()).effect == "none"


# An opaque provider version may change despite identical normalized facts; never send a new token.
def test_same_facts_changed_compare_token_blocks_send(network_case):
    command, _, provider, boundary = network_case
    authority = boundary.preview(command)
    provider.inspect_network_authority = Mock(
        return_value=authority.model_copy(update={"compare_token": "changed-version"})
    )
    provider.replace_network = Mock()
    assert boundary.apply(authority).effect == "none"
    provider.replace_network.assert_not_called()


# A policy/identity change during preflight can stop dispatch without any external effect.
def test_prewrite_context_guard_blocks_send(network_case):
    command, _, provider, boundary = network_case
    authority = boundary.preview(command)
    provider.replace_network = Mock()
    assert boundary.apply(authority, before_write=lambda: False).effect == "none"
    provider.replace_network.assert_not_called()


# Unknown effects, failed reads and altered unrelated objects never become verified.
@pytest.mark.parametrize("fault", ["unknown", "none", "exception", "readback", "scope", "time"])
def test_uncertain_write_or_readback_remains_unverified(network_case, fault):
    command, _, provider, boundary = network_case
    authority = boundary.preview(command)
    if fault in {"unknown", "none"}:
        provider.replace_network = Mock(return_value=RecoveryNetworkOutcome(effect=fault))
    elif fault == "exception":
        provider.replace_network = Mock(side_effect=RuntimeError("private provider payload"))
    else:
        replace = provider.replace_network

        # Faults happen only after the write could have taken effect.
        def broken_write(value):
            result = replace(value)
            if fault == "readback":
                provider.inspect_network_authority = Mock(side_effect=RuntimeError("denied"))
            elif fault == "scope":
                result = result.model_copy(
                    update={
                        "capture": result.capture.model_copy(update={"scim_resource_id": "other"})
                    }
                )
            elif fault == "time":
                boundary.clock = Mock(side_effect=[NOW, NOW + timedelta(seconds=31)])
            return result

        provider.replace_network = broken_write
    result = boundary.apply(authority)
    assert result.effect == (fault if fault in {"none", "unknown"} else "unknown")
    assert result.capture is None


# Broken or shared rules require manual handling; this capability changes only a perimeter.
@pytest.mark.parametrize("fault", ["members", "mfa", "disabled", "denied", "partial"])
def test_unsafe_surrounding_policy_is_not_repaired(network_case, fault):
    command, capture, provider, boundary = network_case
    facts = capture.facts
    if fault in {"members", "mfa", "disabled"}:
        first, *remaining = facts.rules
        changes = {
            "members": {"subjects": (command.target.scim_resource_id, "unexpected")},
            "mfa": {"mfa": "required"},
            "disabled": {"enabled": False},
        }[fault]
        facts = facts.model_copy(update={"rules": (first.model_copy(update=changes), *remaining)})
    else:
        facts = facts.model_copy(update={"authorized" if fault == "denied" else "complete": False})
    provider.capture = capture.model_copy(update={"facts": facts})
    with pytest.raises(ProviderContractError):
        boundary.preview(command)


# Explicit simulation rejects real-looking targets and never reads a live tenancy as a fallback.
def test_simulator_scope_and_factory(network_case):
    command, capture, _, _ = network_case
    assert simulated_network_repair(command, capture, lambda: NOW).preview(command)
    for changed in (
        command.model_copy(
            update={
                "target": command.target.model_copy(
                    update={"tenancy_ocid": "ocid1.tenancy.oc1..real"}
                )
            }
        ),
        command.model_copy(
            update={"binding": command.binding.model_copy(update={"policy_id": "other"})}
        ),
        command.model_copy(
            update={"target": command.target.model_copy(update={"scim_resource_id": "other"})}
        ),
        command.model_copy(
            update={
                "target": command.target.model_copy(
                    update={"domain_ocid": "ocid1.domain.oc1..other"}
                )
            }
        ),
    ):
        with pytest.raises(ProviderContractError):
            SimulatedRecoveryNetworkProvider(changed, capture, lambda: NOW)
