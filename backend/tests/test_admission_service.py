"""Unit admission policy tests, independent of SQL, provider execution or SSO implementation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from otm.operations.acceptance import AcceptInspection
from otm.operations.contracts import (
    Acceptance,
    ActorIdentity,
    InspectImportRequest,
    InspectionIntent,
    InspectionPolicy,
    IntentEventData,
    canonical_hash,
)
from otm.providers.inspection_contracts import InspectionTarget

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


# Supply explicit test authorization and trusted server policy.
@pytest.fixture
def admission():
    request = InspectImportRequest(
        workspace_id="example-org",
        client_request_key=uuid4(),
        tenancy_ocid="ocid1.tenancy.oc1..examplechild",
    )
    actor = ActorIdentity(
        issuer="https://sso.example.test", subject="admin-one", display_name="Example Administrator"
    )
    policy = InspectionPolicy(
        workspace_id=request.workspace_id,
        policy_revision=uuid4(),
        organization_id="example-organization",
        access_binding_id=uuid4(),
        parent_tenancy_ocid="ocid1.tenancy.oc1..exampleparent",
    )
    intent = InspectionIntent(
        contract_version="inspect-import-1",
        kind="inspect_import",
        workspace_id=request.workspace_id,
        policy_revision=policy.policy_revision,
        access_binding_id=policy.access_binding_id,
        target=InspectionTarget(
            organization_id=policy.organization_id,
            parent_tenancy_ocid=policy.parent_tenancy_ocid,
            tenancy_ocid=request.tenancy_ocid,
        ),
    )
    accepted = Acceptance(operation_id=uuid4(), state="queued", accepted_at=NOW)
    store = Mock(find=Mock(return_value=None), insert=Mock(return_value=accepted))
    auth = Mock(require_admin=Mock(return_value=actor))
    resolve = Mock(return_value=policy)
    clock = Mock(return_value=NOW)
    return SimpleNamespace(
        request=request,
        actor=actor,
        policy=policy,
        intent=intent,
        accepted=accepted,
        store=store,
        auth=auth,
        resolve=resolve,
        clock=clock,
        service=AcceptInspection(store, auth, resolve, clock),
        principal=object(),
    )


# Client input cannot choose the parent, binding or actor recorded in resolved intent.
def test_new_admission_freezes_server_policy_and_verified_actor(admission):
    result = admission.service.accept(admission.request, admission.principal)
    assert result == admission.accepted and result.state == "queued"
    admission.auth.require_admin.assert_called_once_with(
        admission.principal, admission.request.workspace_id
    )
    request, actor, intent, at = admission.store.insert.call_args.args
    assert request == admission.request and actor == admission.actor and at == NOW
    assert intent == admission.intent


# A known request key does not disclose existing operations after admin access is revoked.
def test_denied_authorization_precedes_replay_and_policy_lookup(admission):
    admission.auth.require_admin.side_effect = PermissionError("NOT_AUTHORIZED")
    with pytest.raises(PermissionError):
        admission.service.accept(admission.request, admission.principal)
    admission.store.find.assert_not_called()
    admission.resolve.assert_not_called()
    admission.store.insert.assert_not_called()


# Fresh policy problems cannot retarget or invalidate a compatible accepted request.
def test_committed_replay_uses_original_acceptance_before_current_policy_checks(admission):
    admission.store.find.return_value = admission.accepted
    admission.resolve.side_effect = RuntimeError("policy changed")
    assert admission.service.accept(admission.request, admission.principal) == admission.accepted
    admission.auth.require_admin.assert_called_once()
    admission.resolve.assert_not_called()
    admission.store.insert.assert_not_called()


# Trusted policy must match the workspace and cannot treat the parent as its own child.
@pytest.mark.parametrize("fault", ["workspace", "parent"])
def test_policy_scope_and_parent_target_fail_before_persistence(admission, fault):
    changes = (
        {"workspace_id": "other-org"}
        if fault == "workspace"
        else {"parent_tenancy_ocid": admission.request.tenancy_ocid}
    )
    admission.resolve.return_value = admission.policy.model_copy(update=changes)
    with pytest.raises(ValueError, match="POLICY_SCOPE|PARENT_IS_NOT"):
        admission.service.accept(admission.request, admission.principal)
    admission.store.insert.assert_not_called()


# Separate issuers while preserving actor ownership across display-name changes.
def test_actor_scope_is_issuer_qualified_and_independent_of_display_metadata(admission):
    original = admission.actor
    renamed = original.model_copy(update={"display_name": "Renamed Administrator"})
    other = original.model_copy(update={"issuer": "https://other.example.test"})
    assert original.key == renamed.key and original.key != other.key
    assert original.subject not in original.key


# Different request keys may express identical input; changed scope/target cannot reuse it.
def test_request_digest_is_canonical_and_covers_kind_workspace_and_target(admission):
    original = admission.request
    assert original.digest == original.model_copy(update={"client_request_key": uuid4()}).digest
    assert original.digest != original.model_copy(update={"workspace_id": "other-org"}).digest
    assert (
        original.digest
        != original.model_copy(update={"tenancy_ocid": "ocid1.tenancy.oc1..other"}).digest
    )
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


# The eventual request boundary cannot accept identity or execution context from the SPA.
@pytest.mark.parametrize(
    "field", ["actor", "issuer", "admin", "parent_tenancy_ocid", "access_binding_id", "private_key"]
)
def test_admission_request_rejects_client_authority_and_credential_fields(admission, field):
    value = admission.request.model_dump()
    value[field] = "untrusted-value"
    with pytest.raises(ValidationError):
        InspectImportRequest.model_validate(value)


# Unexpected token/claim fields cannot silently enter immutable administrative history.
def test_authorization_result_is_allowlisted_instead_of_copying_raw_claims(admission):
    admission.auth.require_admin.return_value = {
        **admission.actor.model_dump(),
        "access_token": "sensitive-marker",
    }
    with pytest.raises(ValidationError) as error:
        admission.service.accept(admission.request, admission.principal)
    assert "sensitive-marker" not in str(error.value)
    admission.store.find.assert_not_called()


# Resolved policy and actor metadata cannot be changed by accidental consumer assignment.
def test_event_data_and_policy_are_frozen_closed_snapshots(admission):
    event = IntentEventData(intent=admission.intent, actor=admission.actor)
    with pytest.raises(ValidationError):
        event.actor.subject = "someone-else"
    with pytest.raises(ValidationError):
        admission.policy.policy_revision = uuid4()
    assert (
        event.model_dump(mode="json")["intent"]["target"]["tenancy_ocid"]
        == admission.request.tenancy_ocid
    )
