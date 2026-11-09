"""Synthetic console boundaries reject permissive unions and never infer policy from presence."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_admission_service import NOW

from otm.providers.inspection import ProviderContractError
from otm.providers.recovery_console import (
    ConsolePolicyFacts,
    ConsolePolicyObservation,
    InspectRecoveryConsole,
    RecoveryConsoleInspection,
    evaluate_console,
)
from otm.providers.recovery_console_simulator import SimulatedRecoveryConsoleProvider
from otm.recovery_console import RecoveryConsoleSettings, parse_release_cidrs
from otm.settings import ConfigurationError, load_settings


# Public fixtures use documentation ranges; operational inputs never enter repository evidence.
@pytest.fixture
def policy_case():
    target = dict(
        workspace_id="test",
        tenancy_id=uuid4(),
        purpose="recovery",
        subject_binding_id=uuid4(),
        binding_generation=1,
        identity_domain_binding_id=uuid4(),
        domain_ocid="ocid1.domain.oc1..synthetic",
        scim_resource_id="recovery-id",
        provider_ocid="ocid1.user.oc1..synthetic",
        user_name="otm-recovery",
        tenancy_ocid="ocid1.tenancy.oc1..child",
        parent_tenancy_ocid="ocid1.tenancy.oc1..parent",
        organization_id="org",
    )
    context = dict(
        workspace_id="test",
        operation_id=uuid4(),
        step_key="console",
        attempt_id=uuid4(),
        intent_revision=1,
        execution_generation=1,
        connection_id=uuid4(),
        connection_revision=1,
    )
    binding = dict(
        application_id="console",
        policy_id="policy",
        perimeter_id="perimeter",
        group_id="recovery-only",
        allow_rule_id="inside",
        deny_rule_id="outside",
    )
    desired = RecoveryConsoleSettings(allowed_cidrs=["198.51.100.0/24", "2001:db8::/32"])
    command = InspectRecoveryConsole(
        context=context, target=target, binding=binding, desired=desired
    )
    allow = dict(
        id="inside",
        enabled=True,
        subjects=("recovery-id",),
        effect="allow",
        mfa="exempt",
        perimeter_id="perimeter",
        group_id="recovery-only",
        supported=True,
    )
    deny = dict(
        id="outside",
        enabled=True,
        subjects=("recovery-id",),
        effect="deny",
        mfa="not_applicable",
        perimeter_id=None,
        group_id="recovery-only",
        supported=True,
    )
    fallback = dict(
        id="fallback",
        enabled=True,
        subjects=None,
        effect="allow",
        mfa="required",
        perimeter_id=None,
        group_id=None,
        supported=True,
    )
    facts = ConsolePolicyFacts(
        domain_ocid=target["domain_ocid"],
        application_id="console",
        policy_id="policy",
        assigned=True,
        enabled=True,
        authorized=True,
        complete=True,
        rules=(allow, deny, fallback),
        perimeter_id="perimeter",
        perimeter=desired,
    )
    return command, facts


# Canonicalization accepts both address families, stable order and deduplication without widening.
def test_canonical_multiple_ranges_and_effective_fingerprint():
    policy = parse_release_cidrs(" 2001:DB8::/32,198.51.100.0/24,198.51.100.0/24 ")
    assert policy.allowed_cidrs == ("198.51.100.0/24", "2001:db8::/32")
    redundant = RecoveryConsoleSettings(allowed_cidrs=[*policy.allowed_cidrs, "198.51.100.0/25"])
    assert redundant.fingerprint == policy.fingerprint
    assert "198.51" not in repr(policy)


# Split universal ranges are as unsafe as /0; a single bad entry rejects the entire candidate.
@pytest.mark.parametrize(
    "values",
    [
        [],
        [""],
        ["garbage"],
        ["198.51.100.1/24"],
        ["0.0.0.0/0"],
        ["::/0"],
        ["0.0.0.0/1", "128.0.0.0/1"],
        ["::/1", "8000::/1"],
        ["198.51.100.0/24", "invalid"],
        [1],
        ["198.51.100.0/24"] * 65,
        [" " * 4096],
        "198.51.100.0/24",
        None,
    ],
)
def test_invalid_policy_is_wholly_rejected(values):
    with pytest.raises(ValidationError):
        RecoveryConsoleSettings(allowed_cidrs=values)


# Release inputs are bounded before splitting and cannot hide empty elements.
@pytest.mark.parametrize("value", [None, 1, "", "198.51.100.0/24,", ",198.51.100.0/24", "x" * 4097])
def test_release_input_rejects_invalid_data(value):
    with pytest.raises(ValueError):
        parse_release_cidrs(value)


# Invalid TOML ranges produce the existing fixed configuration diagnostic without value leakage.
def test_settings_error_is_sanitized(tmp_path):
    path = tmp_path / "application.toml"
    path.write_text('[recovery_console]\nallowed_cidrs=["198.51.100.1/24"]\n')
    with pytest.raises(ConfigurationError, match="^INVALID_APPLICATION_SETTINGS$") as error:
        load_settings(path)
    assert "198.51" not in str(error.value)


# The complete qualified pair blocks broad fallback while restricting only the exact identity.
def test_complete_pair_and_broad_fallback(policy_case):
    command, facts = policy_case
    result = evaluate_console(command, facts)
    assert result.state == result.mfa_exemption == result.network_boundary == "verified"
    assert result.observed_fingerprint and result.desired_fingerprint != result.observed_fingerprint
    assert "198.51" not in result.model_dump_json()
    assert facts.rules[-1].mfa == "required" and facts.rules[-1].subjects is None


# Policy drift is independent of identity existence and cannot report verified readiness.
@pytest.mark.parametrize(
    "damage",
    [
        "mfa",
        "disabled_allow",
        "disabled_deny",
        "order",
        "broad_first",
        "no_deny",
        "extra_member",
        "wrong_group",
        "wrong_perimeter",
        "deny_perimeter",
        "deny_allow",
        "allow_deny",
        "unassigned",
        "disabled_policy",
        "changed_cidrs",
    ],
)
def test_effective_rule_drift(policy_case, damage):
    command, original = policy_case
    values = deepcopy(original.model_dump())
    rules = list(values["rules"])
    if damage == "mfa":
        rules[0]["mfa"] = "required"
    elif damage == "disabled_allow":
        rules[0]["enabled"] = False
    elif damage == "disabled_deny":
        rules[1]["enabled"] = False
    elif damage == "order":
        rules.reverse()
    elif damage == "broad_first":
        rules.insert(0, rules.pop())
    elif damage == "no_deny":
        rules.pop(1)
    elif damage == "extra_member":
        rules[0]["subjects"] = ("recovery-id", "owner-id")
    elif damage == "wrong_group":
        rules[0]["group_id"] = "Administrators"
    elif damage == "wrong_perimeter":
        rules[0]["perimeter_id"] = "other"
    elif damage == "deny_perimeter":
        rules[1]["perimeter_id"] = "perimeter"
    elif damage == "deny_allow":
        rules[1]["effect"] = "allow"
    elif damage == "allow_deny":
        rules[0]["effect"] = "deny"
    elif damage == "unassigned":
        values["assigned"] = False
    elif damage == "disabled_policy":
        values["enabled"] = False
    elif damage == "changed_cidrs":
        values["perimeter"] = {"allowed_cidrs": ["203.0.113.0/24"]}
    values["rules"] = tuple(rules)
    result = evaluate_console(command, ConsolePolicyFacts.model_validate(values))
    assert result.state == "drift"
    assert result.observed_fingerprint != evaluate_console(command, original).observed_fingerprint
    assert original == policy_case[1]
    if damage == "mfa":
        assert result.network_boundary == "verified"
    if damage == "changed_cidrs":
        assert result.mfa_exemption == "verified"


# Permission gaps, unsupported shapes and wrong scope remain unverified rather than compliant.
@pytest.mark.parametrize(
    "damage",
    [
        "denied",
        "incomplete",
        "unsupported",
        "duplicate",
        "domain",
        "application",
        "policy",
        "perimeter",
    ],
)
def test_unknown_policy_cannot_verify(policy_case, damage):
    command, original = policy_case
    values = deepcopy(original.model_dump())
    if damage == "denied":
        values["authorized"] = False
    elif damage == "incomplete":
        values["complete"] = False
    elif damage == "unsupported":
        values["rules"] = (
            original.rules[0].model_copy(update={"supported": False}),
            *original.rules[1:],
        )
    elif damage == "duplicate":
        values["rules"] = (*original.rules, original.rules[0])
    else:
        values[
            {
                "domain": "domain_ocid",
                "application": "application_id",
                "policy": "policy_id",
                "perimeter": "perimeter_id",
            }[damage]
        ] = "other"
    assert evaluate_console(command, ConsolePolicyFacts.model_validate(values)).state == "unknown"


# Wrong-purpose, cross-workspace and aliased rule targets fail before provider dispatch.
@pytest.mark.parametrize("damage", ["purpose", "workspace", "rules"])
def test_invalid_command_never_dispatches(policy_case, damage):
    command, facts = policy_case
    values = command.model_dump()
    if damage == "purpose":
        values["target"]["purpose"] = "automation"
    elif damage == "workspace":
        values["context"]["workspace_id"] = "other"
    else:
        values["binding"]["deny_rule_id"] = values["binding"]["allow_rule_id"]
    provider = Mock()
    with pytest.raises(ValidationError):
        RecoveryConsoleInspection(provider, lambda: NOW).inspect(values)
    provider.inspect_recovery_console.assert_not_called()


# Independent retained simulator facts do not track a new desired list automatically.
def test_simulator_read_and_desired_change(policy_case):
    command, facts = policy_case
    provider = SimulatedRecoveryConsoleProvider(command.target, command.context, facts, lambda: NOW)
    inspection = RecoveryConsoleInspection(provider, lambda: NOW)
    assert inspection.inspect(command).state == "verified"
    changed = command.model_copy(update={"desired": parse_release_cidrs("203.0.113.0/24")})
    assert inspection.inspect(changed).state == "drift"
    assert provider.facts == facts
    with pytest.raises(ValueError):
        provider.inspect_recovery_console(
            command.model_copy(
                update={"context": command.context.model_copy(update={"attempt_id": uuid4()})}
            )
        )


# Failed clocks/adapters, stale timestamps and wrong attempts cannot publish qualified controls.
@pytest.mark.parametrize(
    "damage", ["error", "invalid", "stale", "future", "context", "target", "clock"]
)
def test_inspection_rejects_unqualified_response(policy_case, damage):
    command, facts = policy_case
    observation = ConsolePolicyObservation(
        context=command.context, target=command.target, captured_at=NOW, facts=facts
    )
    provider = Mock()
    if damage == "error":
        provider.inspect_recovery_console.side_effect = RuntimeError("private payload")
    elif damage == "invalid":
        provider.inspect_recovery_console.return_value = {}
    else:
        updates = {}
        if damage == "stale":
            updates["captured_at"] = NOW - timedelta(seconds=1)
        if damage == "future":
            updates["captured_at"] = NOW + timedelta(seconds=1)
        if damage == "context":
            updates["context"] = command.context.model_copy(update={"attempt_id": uuid4()})
        if damage == "target":
            updates["target"] = command.target.model_copy(update={"user_name": "other"})
        provider.inspect_recovery_console.return_value = observation.model_copy(update=updates)
    with pytest.raises(ProviderContractError, match="^RECOVERY_CONSOLE_READ_UNVERIFIED$") as error:
        RecoveryConsoleInspection(
            provider, lambda: NOW if damage != "clock" else "invalid"
        ).inspect(command)
    assert "private payload" not in str(error.value)


# Rule normalization coverage must be explicit, and state labels must agree with control evidence.
def test_explicit_support_and_result_contract(policy_case):
    from otm.providers.recovery_console import ConsoleRule, RecoveryConsoleResult

    command, facts = policy_case
    rule = facts.rules[0].model_dump()
    del rule["supported"]
    with pytest.raises(ValidationError):
        ConsoleRule.model_validate(rule)
    result = evaluate_console(command, facts).model_dump()
    for changed in (
        {"state": "unknown"},
        {"safe_code": "RECOVERY_CONSOLE_DRIFT"},
        {"observed_fingerprint": None},
        {"mfa_exemption": "drift"},
    ):
        with pytest.raises(ValidationError):
            RecoveryConsoleResult.model_validate({**result, **changed})


# CIDR syntax is mandatory, including for single hosts; scoped IPv6 addresses are not networks.
@pytest.mark.parametrize("value", ["198.51.100.1", "2001:db8::1", "fe80::%eth0/64"])
def test_explicit_network_syntax(value):
    with pytest.raises(ValueError):
        parse_release_cidrs(value)


# Total acquisition delay beyond the bounded read interval is unverified even with a recent capture.
def test_delayed_read_fails_closed(policy_case):
    command, facts = policy_case
    clock = Mock(side_effect=[NOW, NOW + timedelta(seconds=31)])
    provider = Mock()
    provider.inspect_recovery_console.return_value = ConsolePolicyObservation(
        context=command.context, target=command.target, captured_at=NOW, facts=facts
    )
    with pytest.raises(ProviderContractError):
        RecoveryConsoleInspection(provider, clock).inspect(command)
