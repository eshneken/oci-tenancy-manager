"""Exact-subject read pairing and independent fake domain facts, without claiming usable access."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from otm.providers.inspection import ProviderContractError
from otm.providers.inspection_simulator import ManualClock
from otm.providers.required_user import RequiredUserInspection
from otm.providers.required_user_contracts import (
    InspectRequiredUser,
    RequiredUserObservation,
    RequiredUserReadContext,
    RequiredUserTarget,
)
from otm.providers.required_user_simulator import (
    SimulatedDomainUser,
    SimulatedIdentityDomain,
    SimulatedRequiredUserProvider,
    SimulatedUserReadAccess,
)

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)


# Each scenario separates expected application bindings from authority, domain and actual user
# state.
def case(*, with_user=True):
    clock = ManualClock(NOW)
    target = RequiredUserTarget(
        workspace_id="presence-test",
        tenancy_id=uuid4(),
        purpose="automation",
        subject_binding_id=uuid4(),
        binding_generation=1,
        identity_domain_binding_id=uuid4(),
        domain_ocid="ocid1.domain.oc1..otmsimdomain",
        scim_resource_id="scim-automation",
        provider_ocid="ocid1.user.oc1..otmsimautomation",
        user_name="otm_automation",
        organization_id="test-org",
        parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        tenancy_ocid="ocid1.tenancy.oc1..otmsimchild",
    )
    context = RequiredUserReadContext(
        workspace_id=target.workspace_id,
        operation_id=uuid4(),
        step_key="inspect_automation",
        attempt_id=uuid4(),
        intent_revision=1,
        execution_generation=1,
        connection_id=uuid4(),
        connection_revision=1,
    )
    command = InspectRequiredUser(context=context, target=target)
    access = SimulatedUserReadAccess(
        workspace_id=target.workspace_id,
        connection_id=context.connection_id,
        connection_revision=1,
        permitted=True,
        tenancy_ocids=frozenset({target.tenancy_ocid}),
    )
    domain = SimulatedIdentityDomain(
        workspace_id=target.workspace_id,
        domain_ocid=target.domain_ocid,
        organization_id=target.organization_id,
        parent_tenancy_ocid=target.parent_tenancy_ocid,
        tenancy_ocid=target.tenancy_ocid,
        visible_at=NOW,
        complete=True,
    )
    user = SimulatedDomainUser(
        workspace_id=target.workspace_id,
        tenancy_ocid=target.tenancy_ocid,
        domain_ocid=target.domain_ocid,
        scim_resource_id=target.scim_resource_id,
        provider_ocid=target.provider_ocid,
        user_name=target.user_name,
        visible_at=NOW,
    )
    provider = SimulatedRequiredUserProvider(clock.now)
    provider.set_access(access)
    provider.set_domain(domain)
    if with_user:
        provider.set_user(user)
    return SimpleNamespace(
        clock=clock,
        target=target,
        context=context,
        command=command,
        access=access,
        domain=domain,
        user=user,
        provider=provider,
        service=RequiredUserInspection(provider, clock.now),
    )


# Absence is confirmed only inside a configured complete authorized domain, not from missing
# metadata.
@pytest.mark.parametrize("with_user,state", [(True, "present"), (False, "missing")])
def test_exact_presence_and_absence(with_user, state):
    c = case(with_user=with_user)
    result = c.service.inspect(c.command)
    assert result.state == state and result.authorized and result.complete and result.read_id
    assert (result.observed is not None) == with_user
    assert result.target == c.target and result.context == c.context
    assert result.checked_scim_resource_id == c.target.scim_resource_id
    assert not hasattr(result, "can_repair") and not hasattr(result, "privileges")


# Failed authority/domain/user reads are unknown; none may become a fabricated empty successful
# read.
@pytest.mark.parametrize(
    "scenario,code",
    [
        ("no_access", "ACCESS_UNVERIFIED"),
        ("revision", "ACCESS_UNVERIFIED"),
        ("denied", "ACCESS_DENIED"),
        ("child", "ACCESS_DENIED"),
        ("domain", "DOMAIN_UNVERIFIED"),
        ("parent", "DOMAIN_UNVERIFIED"),
        ("organization", "DOMAIN_UNVERIFIED"),
        ("incomplete", "INCOMPLETE_READ"),
        ("delayed_domain", "READ_DELAYED"),
        ("delayed_user", "READ_DELAYED"),
        ("domain_denied", "ACCESS_DENIED"),
        ("domain_timeout", "READ_TIMEOUT"),
        ("domain_unsupported", "UNSUPPORTED_CAPABILITY"),
        ("user_denied", "ACCESS_DENIED"),
        ("user_timeout", "READ_TIMEOUT"),
        ("user_unsupported", "UNSUPPORTED_CAPABILITY"),
    ],
)
def test_unknown_read_matrix(scenario, code):
    c = case()
    command = c.command
    if scenario == "no_access":
        command = command.model_copy(
            update={"context": c.context.model_copy(update={"connection_id": uuid4()})}
        )
    elif scenario == "revision":
        command = command.model_copy(
            update={"context": c.context.model_copy(update={"connection_revision": 2})}
        )
    elif scenario == "denied":
        c.provider.set_access(c.access.model_copy(update={"permitted": False}))
    elif scenario == "child":
        c.provider.set_access(c.access.model_copy(update={"tenancy_ocids": frozenset()}))
    elif scenario == "domain":
        command = command.model_copy(
            update={
                "target": c.target.model_copy(
                    update={"domain_ocid": "ocid1.domain.oc1..otmsimother"}
                )
            }
        )
    elif scenario == "parent":
        c.provider.set_domain(
            c.domain.model_copy(update={"parent_tenancy_ocid": "ocid1.tenancy.oc1..otmsimother"})
        )
    elif scenario == "organization":
        c.provider.set_domain(c.domain.model_copy(update={"organization_id": "other"}))
    elif scenario == "incomplete":
        c.provider.set_domain(c.domain.model_copy(update={"complete": False}))
    elif scenario == "delayed_domain":
        c.provider.set_domain(
            c.domain.model_copy(update={"visible_at": NOW + timedelta(seconds=1)})
        )
    elif scenario == "delayed_user":
        c.provider.set_user(c.user.model_copy(update={"visible_at": NOW + timedelta(seconds=1)}))
    elif scenario.startswith("domain_"):
        c.provider.set_domain(
            c.domain.model_copy(update={"fault": scenario.removeprefix("domain_")})
        )
    else:
        c.provider.set_user(c.user.model_copy(update={"fault": scenario.removeprefix("user_")}))
    result = c.service.inspect(command)
    assert result.state == "unknown" and result.safe_code == code
    assert not result.complete and result.observed is None


# A same-name user is never adopted as the bound subject; a renamed exact ID remains the same
# identity.
def test_identity_is_not_name_lookup():
    c = case(with_user=False)
    c.provider.set_user(
        c.user.model_copy(
            update={
                "scim_resource_id": "someone-else",
                "provider_ocid": "ocid1.user.oc1..otmsimother",
            }
        )
    )
    assert c.service.inspect(c.command).state == "missing"
    c.provider.set_user(c.user.model_copy(update={"user_name": "renamed-account"}))
    result = c.service.inspect(c.command)
    assert result.state == "present" and result.observed.user_name == "renamed-account"


# Recovery and automation reads own different subjects; one successful observation cannot cover
# both.
def test_coverage_subject_isolation():
    c = case()
    automation = c.service.inspect(c.command)
    recovery = c.target.model_copy(
        update={
            "purpose": "recovery",
            "subject_binding_id": uuid4(),
            "scim_resource_id": "scim-recovery",
            "provider_ocid": "ocid1.user.oc1..otmsimrecovery",
            "user_name": "otm_recovery",
        }
    )
    request = c.command.model_copy(update={"target": recovery})
    assert c.service.inspect(request).state == "missing"
    assert c.service.inspect(c.command).state == "present"
    paired = RequiredUserInspection(
        Mock(inspect_required_user=Mock(return_value=automation)), c.clock.now
    )
    with pytest.raises(ProviderContractError, match="REQUIRED_USER_CONTEXT_MISMATCH"):
        paired.inspect(request)


# Every changed execution or connection reference invalidates returned facts from another read.
@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", uuid4()),
        ("operation_id", uuid4()),
        ("intent_revision", 2),
        ("execution_generation", 2),
        ("connection_id", uuid4()),
        ("connection_revision", 2),
    ],
)
def test_returned_context_fences(field, value):
    c = case()
    original = c.service.inspect(c.command)
    result = original.model_copy(update={"context": c.context.model_copy(update={field: value})})
    service = RequiredUserInspection(
        Mock(inspect_required_user=Mock(return_value=result)), c.clock.now
    )
    with pytest.raises(ProviderContractError, match="REQUIRED_USER_CONTEXT_MISMATCH"):
        service.inspect(c.command)


# Binding identities and generations are paired independently from execution attempts.
@pytest.mark.parametrize(
    "field,value",
    [
        ("subject_binding_id", uuid4()),
        ("binding_generation", 2),
        ("identity_domain_binding_id", uuid4()),
        ("tenancy_id", uuid4()),
    ],
)
def test_returned_subject_fences(field, value):
    c = case()
    original = c.service.inspect(c.command)
    result = original.model_copy(update={"target": c.target.model_copy(update={field: value})})
    service = RequiredUserInspection(
        Mock(inspect_required_user=Mock(return_value=result)), c.clock.now
    )
    with pytest.raises(ProviderContractError, match="REQUIRED_USER_CONTEXT_MISMATCH"):
        service.inspect(c.command)


# Actual checked and returned IDs must match; a wrong-domain404 cannot prove this user missing.
@pytest.mark.parametrize(
    "field,value,code",
    [
        (
            "checked_domain_ocid",
            "ocid1.domain.oc1..otmsimwrong",
            "REQUIRED_USER_CHECKED_IDENTITY_MISMATCH",
        ),
        ("checked_scim_resource_id", "other-scim", "REQUIRED_USER_CHECKED_IDENTITY_MISMATCH"),
        (
            "domain_ocid",
            "ocid1.domain.oc1..otmsimwrong",
            "REQUIRED_USER_OBSERVED_IDENTITY_MISMATCH",
        ),
        ("scim_resource_id", "other-scim", "REQUIRED_USER_OBSERVED_IDENTITY_MISMATCH"),
        (
            "provider_ocid",
            "ocid1.user.oc1..otmsimwrong",
            "REQUIRED_USER_OBSERVED_IDENTITY_MISMATCH",
        ),
    ],
)
def test_observed_and_checked_identity_fences(field, value, code):
    c = case()
    original = c.service.inspect(c.command)
    result = (
        original.model_copy(update={field: value})
        if field.startswith("checked_")
        else original.model_copy(
            update={"observed": original.observed.model_copy(update={field: value})}
        )
    )
    service = RequiredUserInspection(
        Mock(inspect_required_user=Mock(return_value=result)), c.clock.now
    )
    with pytest.raises(ProviderContractError, match=code):
        service.inspect(c.command)
    if field == "checked_domain_ocid":
        missing = result.model_copy(
            update={"state": "missing", "safe_code": "USER_MISSING", "observed": None}
        )
        service.provider.inspect_required_user.return_value = missing
        with pytest.raises(ProviderContractError, match=code):
            service.inspect(c.command)


# Invalid/incomplete result models never escape as confirmed or reflect raw provider material.
@pytest.mark.parametrize(
    "changes",
    [
        dict(authorized=False),
        dict(complete=False),
        dict(read_id=None),
        dict(checked_domain_ocid=None),
        dict(checked_scim_resource_id=None),
        dict(observed=None),
        dict(safe_code="USER_MISSING"),
        dict(state="unknown"),
        dict(password="do-not-echo"),
    ],
)
def test_result_validation_closed(changes):
    c = case()
    data = c.service.inspect(c.command).model_dump()
    data.update(changes)
    service = RequiredUserInspection(
        Mock(inspect_required_user=Mock(return_value=data)), c.clock.now
    )
    with pytest.raises(ProviderContractError, match="INVALID_REQUIRED_USER_RESULT") as error:
        service.inspect(c.command)
    assert "do-not-echo" not in str(error.value)


# Unknown states cannot carry presence/absence codes, full coverage or partial identity facts.
@pytest.mark.parametrize(
    "changes", [dict(safe_code="USER_PRESENT"), dict(safe_code="USER_MISSING"), dict(complete=True)]
)
def test_unknown_cannot_invent_facts(changes):
    c = case(with_user=False)
    c.provider.set_domain(c.domain.model_copy(update={"complete": False}))
    raw = c.service.inspect(c.command).model_dump()
    raw.update(changes)
    with pytest.raises(ValidationError):
        RequiredUserObservation.model_validate(raw)


# A result outside its actual call window, including a backward clock, is stale evidence.
@pytest.mark.parametrize("elapsed", [-1, 1])
def test_capture_window(elapsed):
    c = case()
    original = c.service.inspect(c.command)
    result = original.model_copy(update={"captured_at": NOW + timedelta(seconds=elapsed)})
    service = RequiredUserInspection(
        Mock(inspect_required_user=Mock(return_value=result)), c.clock.now
    )
    with pytest.raises(ProviderContractError, match="REQUIRED_USER_CAPTURE_WINDOW_MISMATCH"):
        service.inspect(c.command)


# Clock faults and unnormalized provider exceptions yield fixed diagnostics, not sensitive errors.
@pytest.mark.parametrize("which", ["clock", "clock_type", "clock_naive", "provider"])
def test_closed_dependency_failures(which):
    c = case()
    clock = Mock(return_value=NOW)
    provider = Mock(inspect_required_user=Mock(return_value=c.service.inspect(c.command)))
    if which == "clock":
        clock.side_effect = RuntimeError("do-not-echo")
    if which == "clock_type":
        clock.return_value = NOW.isoformat()
    if which == "clock_naive":
        clock.return_value = NOW.replace(tzinfo=None)
    if which == "provider":
        provider.inspect_required_user.side_effect = TimeoutError("do-not-echo")
    with pytest.raises(ProviderContractError) as error:
        RequiredUserInspection(provider, clock).inspect(c.command)
    assert "do-not-echo" not in str(error.value)


# Input scope and deferred audit-user purpose fail before an adapter is called.
@pytest.mark.parametrize("change", ["workspace", "parent", "purpose", "secret"])
def test_input_boundaries(change):
    c = case()
    raw = c.command.model_dump()
    if change == "workspace":
        raw["context"]["workspace_id"] = "other"
    if change == "parent":
        raw["target"]["tenancy_ocid"] = raw["target"]["parent_tenancy_ocid"]
    if change == "purpose":
        raw["target"]["purpose"] = "audit"
    if change == "secret":
        raw["private_key"] = "do-not-echo"
    with pytest.raises(ValidationError):
        InspectRequiredUser.model_validate(raw)


# Only the simulator rejects real-looking identities; neutral contracts remain
# implementation-agnostic.
@pytest.mark.parametrize(
    "fixture,field,value",
    [
        ("domain", "tenancy_ocid", "ocid1.tenancy.oc1..realchild"),
        ("domain", "domain_ocid", "ocid1.domain.oc1..realdomain"),
        ("domain", "tenancy_ocid", "ocid1.tenancy.oc1..otmsimparent"),
        ("user", "tenancy_ocid", "ocid1.tenancy.oc1..realchild"),
        ("user", "domain_ocid", "ocid1.domain.oc1..realdomain"),
        ("user", "provider_ocid", "ocid1.user.oc1..realuser"),
    ],
)
def test_simulator_identity_guards(fixture, field, value):
    c = case()
    changed = getattr(c, fixture).model_copy(update={field: value})
    with pytest.raises(ValueError, match="SIMULATED_"):
        getattr(c.provider, "set_" + fixture)(changed)


# Unmapped OCI IDs are not invented, and an authority without a version reference has no fallback.
def test_explicit_nullable_identity_and_authority_references():
    c = case()
    target = c.target.model_copy(update={"provider_ocid": None})
    c.provider.set_user(c.user.model_copy(update={"provider_ocid": None}))
    assert c.service.inspect(c.command.model_copy(update={"target": target})).state == "present"
    # Obsolete credential/profile bookkeeping is rejected, never silently accepted as authority.
    for field in ("credential_version_id", "credential_generation", "context_generation"):
        with pytest.raises(ValidationError):
            RequiredUserReadContext.model_validate({**c.context.model_dump(), field: None})
    for field in ("access_assignment_id", "access_generation"):
        with pytest.raises(ValidationError):
            RequiredUserTarget.model_validate({**c.target.model_dump(), field: uuid4()})


# Accept non-synthetic identity shapes without granting authority or choosing an adapter.
def test_neutral_target_has_no_simulator_prefix_requirement():
    c = case()
    raw = c.target.model_dump()
    raw.update(
        tenancy_ocid="ocid1.tenancy.oc1..examplechild",
        domain_ocid="ocid1.domain.oc1..exampledomain",
        provider_ocid="ocid1.user.oc1..exampleuser",
    )
    target = RequiredUserTarget.model_validate(raw)
    assert target.scim_resource_id == c.target.scim_resource_id


# Authorized but incomplete reads remain unknown; partial identity facts are forbidden.
def test_partial_authorized_read_does_not_establish_presence():
    c = case()
    raw = c.service.inspect(c.command).model_dump()
    raw.update(state="unknown", safe_code="INCOMPLETE_READ", complete=False, observed=None)
    assert RequiredUserObservation.model_validate(raw).state == "unknown"
    raw["observed"] = c.service.inspect(c.command).observed
    with pytest.raises(ValidationError):
        RequiredUserObservation.model_validate(raw)
