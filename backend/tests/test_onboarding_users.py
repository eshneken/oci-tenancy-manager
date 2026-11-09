"""Permanent-user capture preserves exact identity without upgrading historical onboarding."""

from unittest.mock import MagicMock, patch

import pytest
from test_configuration_updates import update_case
from test_onboarding import case, registry
from test_organization_fixtures import NOW

from otm.providers.lifecycle import OnboardingUsers
from otm.tenancies import onboarding as flow
from otm.tenancies.onboarding_contracts import OnboardingEvidence
from otm.tenancies.onboarding_users import capture_users

__all__ = ["registry", "update_case"]


# Read explicit adapter identities for either origin and preserve them across process-like retries.
@pytest.mark.parametrize("origin", ["create_tenancy", "import_tenancy"])
def test_exact_permanent_users_are_stable_and_not_temporary(registry, origin):
    app, intent, _, _ = case(registry, origin)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    users = capture_users(app.facade, intent, discovery.model_dump(mode="json"))
    assert users == capture_users(app.facade, intent, discovery.model_dump(mode="json"))
    assert users.automation.provider_ocid != users.recovery.provider_ocid
    assert users.automation.provider_ocid != discovery.bootstrap_user_ocid
    assert users.recovery.provider_ocid != discovery.activation_user_ocid
    evidence = OnboardingEvidence(
        step="capture_required_users",
        outcome="verified",
        safe_code="ONBOARDING_VERIFIED",
        required_users=users,
    )
    assert (
        OnboardingEvidence.model_validate_json(evidence.model_dump_json()).required_users == users
    )


# Each returned scope component is independently fenced against the accepted child and discovery.
@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "foreign-workspace"),
        ("tenancy_ocid", "ocid1.tenancy.oc1..otmsimother"),
        ("parent_tenancy_ocid", "ocid1.tenancy.oc1..otmsimotherparent"),
        ("organization_id", "foreign-organization"),
        ("domain_ocid", "ocid1.domain.oc1..otmsimother"),
    ],
)
def test_capture_rejects_foreign_scope(registry, field, value):
    app, intent, _, _ = case(registry)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    result = app.facade.capture_onboarding_users(intent, discovery.model_dump(mode="json"))
    changed = result.model_dump(mode="json")
    changed[field] = value
    if field == "domain_ocid":
        for role in ("automation", "recovery"):
            changed[role]["domain_ocid"] = value
    with patch.object(app.facade, "capture_onboarding_users", return_value=changed):
        with pytest.raises(ValueError, match="REQUIRED_USER_IDENTITIES_UNVERIFIED"):
            capture_users(app.facade, intent, discovery.model_dump(mode="json"))


# Reject bootstrap/activation identities for either permanent role, using both OCI and SCIM IDs.
@pytest.mark.parametrize("role", ["automation", "recovery"])
@pytest.mark.parametrize("temporary", ["bootstrap", "activation"])
@pytest.mark.parametrize("identifier", ["provider_ocid", "scim_resource_id"])
def test_temporary_users_cannot_be_captured_as_permanent(registry, role, temporary, identifier):
    app, intent, _, _ = case(registry)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    result = app.facade.capture_onboarding_users(intent, discovery.model_dump(mode="json"))
    changed = result.model_dump(mode="json")
    source = temporary + ("_user_ocid" if identifier == "provider_ocid" else "_scim_id")
    changed[role][identifier] = getattr(discovery, source)
    with patch.object(app.facade, "capture_onboarding_users", return_value=changed):
        with pytest.raises(ValueError, match="REQUIRED_USER_IDENTITIES_UNVERIFIED"):
            capture_users(app.facade, intent, discovery.model_dump(mode="json"))


# Incomplete, shared or cross-domain identities cannot masquerade as complete permanent bindings.
@pytest.mark.parametrize("fault", ["null_ocid", "same_ocid", "same_scim", "domain", "parent"])
def test_capture_contract_rejects_unidentified_or_conflicting_subjects(registry, fault):
    app, intent, _, _ = case(registry)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    data = app.facade.capture_onboarding_users(
        intent, discovery.model_dump(mode="json")
    ).model_dump()
    if fault == "parent":
        data["tenancy_ocid"] = data["parent_tenancy_ocid"]
    elif fault == "null_ocid":
        data["recovery"]["provider_ocid"] = None
    elif fault == "same_ocid":
        data["recovery"]["provider_ocid"] = data["automation"]["provider_ocid"]
    elif fault == "same_scim":
        data["recovery"]["scim_resource_id"] = data["automation"]["scim_resource_id"]
    else:
        data["recovery"]["domain_ocid"] = "ocid1.domain.oc1..otmsimother"
    with pytest.raises(ValueError, match="REQUIRED_USER_IDENTITIES_UNVERIFIED"):
        OnboardingUsers.model_validate(data)


# Normalize provider faults and reject non-contract secrets instead of retaining raw responses.
def test_capture_faults_and_extra_secret_fields_are_not_evidence(registry):
    app, intent, _, _ = case(registry)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    with patch.object(app.facade, "capture_onboarding_users", side_effect=RuntimeError("private")):
        with pytest.raises(ValueError, match="^REQUIRED_USER_IDENTITIES_UNVERIFIED$") as caught:
            capture_users(app.facade, intent, discovery.model_dump(mode="json"))
        assert caught.value.__suppress_context__
    data = app.facade.capture_onboarding_users(
        intent, discovery.model_dump(mode="json")
    ).model_dump()
    data["password"] = "not-a-credential"
    with pytest.raises(ValueError):
        OnboardingUsers.model_validate(data)
    with pytest.raises(ValueError, match="TARGET_CHANGED"):
        app.facade.capture_onboarding_users(intent, {})


# Only new accepted graphs add capture; old completed/paused graphs retain their exact step set.
@pytest.mark.parametrize("version", [1, 2, 3])
def test_capture_graph_and_pre_retirement_failure_guard(registry, update_case, version):
    app, intent, row, _ = case(registry)
    intent = intent.model_copy(
        update={"onboarding_version": version, "baseline": update_case.baseline}
    )
    keys = [key for key, _ in flow.onboarding_steps(intent)]
    assert ("capture_required_users" in keys) == (version == 3)
    if version != 3:
        return
    assert keys[-3:] == ["verify_configured_access", "capture_required_users", "retire_temporary"]
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    steps = {key: {"state": "verified", "inputs": {}} for key in keys[:-2]}
    steps["handoff"] = {"inputs": {"cleanup_confirmed": True}}
    steps["inspect_bootstrap"]["inputs"] = {"discovery": discovery.model_dump(mode="json")}
    for fail in (False, True):
        with (
            patch.object(flow, "step_rows", return_value=steps),
            patch.object(flow, "save_step") as saved,
            patch("otm.storage.managed_bindings.capture_bindings"),
            patch("otm.storage.user_presence_connections.require_transaction"),
            patch.object(flow, "transition"),
            patch.object(
                app.facade,
                "capture_onboarding_users",
                wraps=app.facade.capture_onboarding_users,
                side_effect=ValueError("private") if fail else None,
            ),
            patch.object(app.facade, "onboarding_step", wraps=app.facade.onboarding_step) as calls,
        ):
            assert flow.advance(MagicMock(), row, intent, app.facade, NOW) is not fail
        assert any(c.args[1] == "retire_temporary" for c in calls.call_args_list) is not fail
        capture = next(
            c.kwargs["payload"]
            for c in saved.call_args_list
            if c.args[2] == "capture_required_users"
        )
        assert (capture.required_users is not None) is not fail
        assert capture.outcome == ("blocked" if fail else "verified")


# Evidence cannot claim a verified capture without facts or attach identities to another outcome.
@pytest.mark.parametrize(
    "step,outcome,with_users",
    [
        ("capture_required_users", "verified", False),
        ("capture_required_users", "blocked", True),
        ("verify_required", "verified", True),
    ],
)
def test_capture_evidence_pairing(registry, step, outcome, with_users):
    app, intent, _, _ = case(registry)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    users = capture_users(app.facade, intent, discovery.model_dump(mode="json"))
    with pytest.raises(ValueError, match="REQUIRED_USER_EVIDENCE_MISMATCH"):
        OnboardingEvidence(
            step=step,
            outcome=outcome,
            safe_code="ONBOARDING_VERIFIED",
            required_users=users if with_users else None,
        )


# Operation detail recognizes the new persisted key without exposing the captured identity payload.
def test_operation_detail_accepts_capture_key():
    from otm.operations.views import OperationStepView

    step = OperationStepView(
        step_key="capture_required_users",
        state="verified",
        attempt_number=1,
        verified_at=NOW,
        safe_code="ONBOARDING_VERIFIED",
    )
    assert step.step_key == "capture_required_users"


# Both permanent identities must retain their separately verified administrative assignments.
@pytest.mark.parametrize("purpose", ["automation", "recovery"])
def test_setup_requires_observed_administrator_assignments(registry, purpose):
    app, intent, _, _ = case(registry)
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    users = app.facade.capture_onboarding_users(intent, discovery.model_dump(mode="json"))
    assert (
        users.automation_administrator.facts.group_members
        == users.recovery_administrator.facts.group_members
    )
    capture = getattr(users, purpose + "_administrator")
    damaged = users.model_copy(
        update={
            purpose + "_administrator": capture.model_copy(
                update={"facts": capture.facts.model_copy(update={"role_groups": ()})}
            )
        }
    )
    with patch.object(app.facade, "capture_onboarding_users", return_value=damaged):
        with pytest.raises(ValueError, match="ADMINISTRATOR_ASSIGNMENTS_UNVERIFIED"):
            capture_users(app.facade, intent, discovery.model_dump(mode="json"))
