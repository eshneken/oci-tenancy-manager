"""Exact required administrator assignments, independently scoped from account existence."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal, Protocol

from pydantic import Field, model_validator

from otm.contracts import Contract, Text, UtcInstant
from otm.providers.inspection import ProviderContractError
from otm.providers.required_user_contracts import RequiredUserReadContext, RequiredUserTarget


# Resource IDs are identity-domain SCIM IDs, never OCI IAM group OCIDs or display names.
class AdministratorBinding(Contract):
    domain_ocid: Text
    scim_resource_id: Text
    group_id: Text
    application_id: Text
    role_id: Text


# Complete direct and supported group grants are separate from expected assignment references.
class AdministratorFacts(Contract):
    binding: AdministratorBinding
    authorized: bool
    complete: bool
    supported: bool
    builtin_group: bool
    group_enabled: bool
    role_enabled: bool
    user_enabled: bool
    group_members: tuple[Text, ...] = Field(max_length=2048)
    role_users: tuple[Text, ...] = Field(max_length=2048)
    role_groups: tuple[Text, ...] = Field(max_length=2048)


# Legacy onboarding lacks these facts and must not acquire fabricated expected resource IDs.
class AdministratorCapture(Contract):
    binding: AdministratorBinding
    facts: AdministratorFacts = Field(repr=False)

    # An authenticated capture must identify the same domain, exact subject and resources.
    @model_validator(mode="after")
    def scope(self):
        if self.facts.binding != self.binding:
            raise ValueError("ADMINISTRATOR_CAPTURE_SCOPE_INVALID")
        return self


# Callers cannot use the recovery account or another child as an automatic alternate signer.
class InspectAdministratorAccess(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    binding: AdministratorBinding

    # Subject identity is exact; inspecting recovery grants never selects a recovery signer.
    @model_validator(mode="after")
    def scope(self):
        if (
            self.context.workspace_id != self.target.workspace_id
            or self.binding.domain_ocid != self.target.domain_ocid
            or self.binding.scim_resource_id != self.target.scim_resource_id
        ):
            raise ValueError("ADMINISTRATOR_COMMAND_SCOPE_INVALID")
        return self


# Independent reads carry provenance even when authorization or pagination is incomplete.
class AdministratorObservation(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    captured_at: UtcInstant
    facts: AdministratorFacts


# Only closed assignment statuses cross the boundary; member lists never reach the browser.
class AdministratorResult(Contract):
    group: Literal["verified", "missing", "unknown"]
    domain_role: Literal["verified", "missing", "unknown"]


# Presence evidence owns the attempt fence and seals this separately dated assignment read.
class AdministratorCheck(Contract):
    context: RequiredUserReadContext
    target: RequiredUserTarget
    checked_at: UtcInstant
    result: AdministratorResult

    # The sealed evidence additionally pairs this result with its exact ordered subject.
    @model_validator(mode="after")
    def scope(self):
        if self.context.workspace_id != self.target.workspace_id:
            raise ValueError("ADMINISTRATOR_CHECK_SCOPE_INVALID")
        return self


# Partial, denied or unsupported reads cannot prove either presence or absence of assignments.
def assess_assignments(binding, facts):
    facts = AdministratorFacts.model_validate(facts)
    if (
        facts.binding != binding
        or not facts.authorized
        or not facts.complete
        or not facts.supported
        or not facts.builtin_group
    ):
        return AdministratorResult(group="unknown", domain_role="unknown")
    member = (
        facts.user_enabled
        and facts.group_enabled
        and binding.scim_resource_id in facts.group_members
    )
    role = (
        facts.user_enabled
        and facts.role_enabled
        and (
            binding.scim_resource_id in facts.role_users
            or member
            and binding.group_id in facts.role_groups
        )
    )
    return AdministratorResult(
        group="verified" if member else "missing", domain_role="verified" if role else "missing"
    )


# Real adapters implement this read-only capability without importing simulation or mutation code.
class AdministratorAccessProvider(Protocol):
    # Read both assignment families with exact scope and complete pagination or declare uncertainty.
    def inspect_administrator_access(
        self, command: InspectAdministratorAccess
    ) -> AdministratorObservation: ...


# Fixed errors and exact provenance prevent accepting another principal's assignment read.
class AdministratorAccessInspection:
    # An explicitly selected provider and UTC clock are the only boundary dependencies.
    def __init__(self, provider: AdministratorAccessProvider, clock: Callable[[], datetime]):
        self.provider, self.clock = provider, clock

    # Require a bounded read with exact resources and admitted attempt/connection context.
    def inspect(self, command):
        try:
            command = InspectAdministratorAccess.model_validate(command)
            started = self.clock()
            observed = AdministratorObservation.model_validate(
                self.provider.inspect_administrator_access(command)
            )
            ended = self.clock()
            if (
                observed.context != command.context
                or observed.target != command.target
                or observed.facts.binding != command.binding
                or not started <= observed.captured_at <= ended
                or ended - started > timedelta(seconds=30)
            ):
                raise ValueError("ADMINISTRATOR_READ_SCOPE_INVALID")
            return AdministratorCheck(
                context=command.context,
                target=command.target,
                checked_at=observed.captured_at,
                result=assess_assignments(command.binding, observed.facts),
            )
        except Exception:
            raise ProviderContractError("ADMINISTRATOR_ACCESS_UNVERIFIED") from None
