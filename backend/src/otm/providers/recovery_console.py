"""Closed recovery-console evidence and conservative verification, independent of adapters."""

import hashlib
import json
from datetime import timedelta
from typing import Annotated, Literal, Protocol

from pydantic import Field, model_validator

from otm.contracts import Contract, Text, UtcInstant
from otm.providers.inspection import ProviderContractError
from otm.providers.required_user_contracts import RequiredUserReadContext, RequiredUserTarget
from otm.recovery_console import RecoveryConsoleSettings


# Exact owned policy resources are discovered/bound separately from mutable names.
class RecoveryConsoleBinding(Contract):
    application_id: Text
    policy_id: Text
    perimeter_id: Text
    group_id: Text
    allow_rule_id: Text
    deny_rule_id: Text


# The adapter resolves selectors and precedence; unsupported conditions cannot be guessed.
class ConsoleRule(Contract):
    id: Text
    enabled: bool
    # None selects all users; an exact tuple is the complete resolved selector membership.
    subjects: tuple[Text, ...] | None
    effect: Literal["allow", "deny"]
    mfa: Literal["required", "exempt", "not_applicable"]
    # None means every source; a perimeter identifies the complete scoped approved-network set.
    perimeter_id: Text | None
    group_id: Text | None
    supported: bool


# Raw normalized evidence is internal only; public results contain no configured CIDRs.
class ConsolePolicyFacts(Contract):
    domain_ocid: Text
    application_id: Text
    policy_id: Text
    assigned: bool
    enabled: bool
    authorized: bool
    complete: bool
    # Provider-normalized first-match order, including all earlier and fallback rules.
    rules: Annotated[tuple[ConsoleRule, ...], Field(max_length=256)]
    perimeter_id: Text
    perimeter: RecoveryConsoleSettings


# Freeze one exact identity/read attempt and desired policy; neither grants provider authority.
class InspectRecoveryConsole(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    binding: RecoveryConsoleBinding
    desired: RecoveryConsoleSettings

    # Wrong-purpose and cross-workspace requests fail before any adapter is called.
    @model_validator(mode="after")
    def scope(self):
        if (
            self.target.purpose != "recovery"
            or self.target.workspace_id != self.context.workspace_id
        ):
            raise ValueError("RECOVERY_CONSOLE_TARGET_INVALID")
        ids = (self.binding.allow_rule_id, self.binding.deny_rule_id)
        if ids[0] == ids[1]:
            raise ValueError("RECOVERY_CONSOLE_RULE_BINDING_INVALID")
        return self


# A safe independent control result can travel alongside presence without redefining it.
class RecoveryConsoleResult(Contract):
    state: Literal["verified", "drift", "unknown"]
    mfa_exemption: Literal["verified", "drift", "unknown"]
    network_boundary: Literal["verified", "drift", "unknown"]
    desired_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    observed_fingerprint: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    safe_code: Literal[
        "RECOVERY_CONSOLE_VERIFIED", "RECOVERY_CONSOLE_DRIFT", "RECOVERY_CONSOLE_UNVERIFIED"
    ]

    # Contradictory safe labels cannot be persisted or accepted as recovery readiness.
    @model_validator(mode="after")
    def coherent_controls(self):
        controls = (self.mfa_exemption, self.network_boundary)
        expected = (
            "verified"
            if controls == ("verified", "verified")
            else "drift"
            if "drift" in controls
            else "unknown"
        )
        code = {
            "verified": "RECOVERY_CONSOLE_VERIFIED",
            "drift": "RECOVERY_CONSOLE_DRIFT",
            "unknown": "RECOVERY_CONSOLE_UNVERIFIED",
        }[expected]
        if (
            self.state != expected
            or self.safe_code != code
            or self.state != "unknown"
            and self.observed_fingerprint is None
            or self.state == "unknown"
            and controls != ("unknown", "unknown")
        ):
            raise ValueError("RECOVERY_CONSOLE_RESULT_INVALID")
        return self


# The producer reports its actual read scope and capture instant independently of expected facts.
class ConsolePolicyObservation(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    captured_at: UtcInstant
    facts: ConsolePolicyFacts


# A provider reports complete facts rather than evaluating policy using the caller's expectations.
class RecoveryConsoleProvider(Protocol):
    # Read exact effective console configuration; no repair, password retrieval or sign-in occurs.
    def inspect_recovery_console(
        self, command: InspectRecoveryConsole
    ) -> ConsolePolicyObservation: ...


# Recognize the qualified exact-user allow/deny shape, never interpret arbitrary SCIM expressions.
def evaluate_console(command: InspectRecoveryConsole, facts: ConsolePolicyFacts):
    command = InspectRecoveryConsole.model_validate(command)
    return assess_policy(
        command.binding,
        command.target.domain_ocid,
        command.target.scim_resource_id,
        command.desired,
        facts,
    )


# Setup can assess exact provider identities before permanent database binding IDs exist.
def assess_policy(binding, domain_ocid, scim_id, desired_policy, facts):
    binding = RecoveryConsoleBinding.model_validate(binding)
    desired_policy = RecoveryConsoleSettings.model_validate(desired_policy)
    facts = ConsolePolicyFacts.model_validate(facts)
    desired = desired_policy.fingerprint
    status, mfa, network = "unknown", "unknown", "unknown"
    ids = [rule.id for rule in facts.rules]
    scoped = (
        facts.domain_ocid == domain_ocid
        and facts.application_id == binding.application_id
        and facts.policy_id == binding.policy_id
        and facts.perimeter_id == binding.perimeter_id
    )
    qualified = scoped and facts.authorized and facts.complete and len(ids) == len(set(ids))
    if qualified and all(rule.supported for rule in facts.rules):
        effective = [rule for rule in facts.rules if rule.enabled]
        relevant = [r for r in effective if r.subjects is None or scim_id in r.subjects]
        allow = next((r for r in facts.rules if r.id == binding.allow_rule_id), None)
        deny = next((r for r in facts.rules if r.id == binding.deny_rule_id), None)
        exact = (scim_id,)
        ordered = (
            facts.enabled
            and facts.assigned
            and allow is not None
            and deny is not None
            and relevant[:2] == [allow, deny]
            and allow.enabled
            and deny.enabled
            and allow.subjects == exact
            and deny.subjects == exact
            and allow.group_id == binding.group_id
            and deny.group_id == binding.group_id
            and allow.effect == "allow"
            and deny.effect == "deny"
            and allow.perimeter_id == binding.perimeter_id
            and deny.perimeter_id is None
        )
        # Earlier broad allows, selector expansion and ineffective denies fail both controls.
        mfa = "verified" if ordered and allow.mfa == "exempt" else "drift"
        network = "verified" if ordered and facts.perimeter.fingerprint == desired else "drift"
        status = "verified" if mfa == network == "verified" else "drift"
    return RecoveryConsoleResult(
        state=status,
        mfa_exemption=mfa,
        network_boundary=network,
        desired_fingerprint=desired,
        observed_fingerprint=observed_fingerprint(facts) if qualified else None,
        safe_code={
            "verified": "RECOVERY_CONSOLE_VERIFIED",
            "drift": "RECOVERY_CONSOLE_DRIFT",
            "unknown": "RECOVERY_CONSOLE_UNVERIFIED",
        }[status],
    )


# Fingerprint all effective-policy inputs; unchanged CIDRs cannot hide MFA/ordering/scope drift.
def observed_fingerprint(facts):
    values = facts.model_dump(mode="json", exclude={"perimeter"})
    values["perimeter_fingerprint"] = facts.perimeter.fingerprint
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# Scope and per-read time checks wrap every adapter; failures never expose provider exceptions.
class RecoveryConsoleInspection:
    # Composition supplies the adapter and aware UTC clock; importing performs no I/O.
    def __init__(self, provider: RecoveryConsoleProvider, clock):
        self.provider, self.clock = provider, clock

    # Read one bound policy and reject stale facts before computing a usable control result.
    def inspect(self, command: InspectRecoveryConsole) -> RecoveryConsoleResult:
        from pydantic import TypeAdapter

        command = InspectRecoveryConsole.model_validate(command)
        try:
            started = TypeAdapter(UtcInstant).validate_python(self.clock(), strict=True)
            raw = self.provider.inspect_recovery_console(command)
            observation = ConsolePolicyObservation.model_validate(raw)
            completed = TypeAdapter(UtcInstant).validate_python(self.clock(), strict=True)
            captured = observation.captured_at
            if observation.context != command.context or observation.target != command.target:
                raise ValueError("RECOVERY_CONSOLE_CONTEXT_MISMATCH")
            if not started <= captured <= completed or completed - started > timedelta(seconds=30):
                raise ValueError("STALE_RECOVERY_CONSOLE_READ")
            return evaluate_console(command, observation.facts)
        except Exception:
            raise ProviderContractError("RECOVERY_CONSOLE_READ_UNVERIFIED") from None


# Retained producer configuration is private DB evidence, never a browser-facing settings object.
class RecoveryConsoleCapture(Contract):
    binding: RecoveryConsoleBinding
    scim_resource_id: Text
    facts: ConsolePolicyFacts = Field(repr=False)

    # Resource references must identify the same exact normalized policy before persistence.
    @model_validator(mode="after")
    def resources(self):
        if (
            self.facts.application_id != self.binding.application_id
            or self.facts.policy_id != self.binding.policy_id
            or self.facts.perimeter_id != self.binding.perimeter_id
        ):
            raise ValueError("RECOVERY_CONSOLE_CAPTURE_SCOPE_INVALID")
        return self


# Sealed checks retain exact attempt/subject and safe control results without publishing CIDRs.
class RecoveryConsoleCheck(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    checked_at: UtcInstant
    result: RecoveryConsoleResult
