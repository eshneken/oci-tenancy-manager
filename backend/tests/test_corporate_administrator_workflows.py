"""Exercise exact onboarding and cleanup ordering with synthetic directory and database IO."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import ANY, Mock
from uuid import uuid4

import pytest
from test_administrators import LOCAL, grant
from test_admission_service import NOW
from test_sessions import session_case

from otm.auth.administrators import AdministratorChange, AdministratorFailure
from otm.auth.corporate_enrollment import (
    CorporateLookup,
    DomainPerson,
    EnrollmentTarget,
    NewAccountName,
)
from otm.auth.service import AdminPrincipal
from otm.storage.corporate_administrators import (
    ConfirmAdministrator,
    CorporateAdministrators,
    FederatedCreateConflict,
)

__all__ = ["session_case"]


# Capture ordered provider and transactional operations without creating any real user.
@pytest.fixture
def workflow(session_case):
    principal = AdminPrincipal(session_case.session)
    target = EnrollmentTarget(
        environment="development",
        workspace=principal.session.workspace_id,
        domain="example-domain",
        issuer="urn:otm:corporate:test",
        app="b" * 32,
        group="c" * 32,
    )
    account = DomainPerson(
        guid="a" * 32,
        domain=target.domain,
        username="synthetic@example.test",
        display_name="Éloïse Synthetic",
        active=True,
        federated=True,
        deleting=False,
    )
    conn = Mock()
    lookup_result = conn.execute.return_value.mappings.return_value
    lookup_result.one_or_none.return_value = None
    store = Mock(local_issuer=LOCAL, trusted_issuers=frozenset({LOCAL, target.issuer}))
    store.engine.connect.return_value = nullcontext(conn)
    store.engine.begin.return_value = nullcontext(conn)
    store.current_actor.return_value = NOW
    domain_lookup = Mock(return_value=(account,))
    membership = Mock(return_value=True)
    creator = Mock(return_value=account)
    service = CorporateAdministrators(store, target, domain_lookup, membership, creator)
    return SimpleNamespace(
        principal=principal,
        target=target,
        service=service,
        account=account,
        conn=conn,
        stored=lookup_result.one_or_none,
        store=store,
        domain_lookup=domain_lookup,
        membership=membership,
        creator=creator,
        lookup=CorporateLookup(value=account.username),
    )


# Turn an actual review into the closed command used by the confirmation boundary.
def confirm_command(w):
    review = w.service.preview(w.principal, w.lookup)
    assert review.display_name == (
        w.account.display_name if review.existing_account else w.lookup.value
    )
    assert review.username == review.work_email == w.lookup.value
    assert review.environment == "development"
    w.membership.assert_not_called()
    return ConfirmAdministrator(
        value=w.lookup.value,
        confirmation=review.confirmation,
        name=None
        if review.existing_account
        else NewAccountName(first_name="Synthetic", last_name="Pilot"),
    )


# Existing OCI users bypass account creation. Group assignment precedes grant and audit inserts.
def test_enrollment_writes_only_the_exact_assignment_then_audits_the_grant(workflow):
    w = workflow
    command = confirm_command(w)
    events = Mock()
    events.attach_mock(w.membership, "membership")
    events.attach_mock(w.conn, "connection")
    receipt = w.service.confirm(w.principal, command)
    assert receipt.status == "active"
    w.creator.assert_not_called()
    w.membership.assert_called_once()
    w.membership.assert_called_once_with(w.target.group, w.account.guid, True, authorize=ANY)
    ordered = [
        call[0] for call in events.mock_calls if call[0] in ("membership", "connection.execute")
    ]
    assert ordered == [
        "connection.execute",
        "membership",
        "connection.execute",
        "connection.execute",
    ]
    assert "audit_event" in str(w.conn.execute.call_args.args[0])


# Changed proofs, cross-environment inputs and unavailable provider operations cannot grant access.
@pytest.mark.parametrize(
    "fault", ["changed", "ambiguous", "provider", "active", "cross", "unqualified"]
)
def test_enrollment_fails_closed_before_unverified_local_writes(workflow, fault):
    w = workflow
    command = confirm_command(w)
    actor = w.principal
    if fault == "changed":
        w.domain_lookup.return_value = (w.account.model_copy(update={"display_name": "New name"}),)
    elif fault == "ambiguous":
        w.domain_lookup.return_value = (w.account, w.account)
    elif fault == "provider":
        w.membership.return_value = False
    elif fault == "active":
        w.stored.return_value = grant().model_dump()
    elif fault == "cross":
        actor = AdminPrincipal(actor.session.model_copy(update={"workspace_id": "other"}))
    else:
        w.domain_lookup.return_value = ()
        w.service.create = None
    with pytest.raises(AdministratorFailure):
        w.service.confirm(actor, command)
    assert not any(str(call.args[0]).startswith("INSERT") for call in w.conn.execute.call_args_list)
    if fault != "provider":
        w.membership.assert_not_called()
    w.creator.assert_not_called()


# Missing names for creation or submitted names for an existing account must cause no writes.
@pytest.mark.parametrize("existing_account", [True, False])
def test_names_are_accepted_only_for_new_accounts(workflow, existing_account):
    w = workflow
    if not existing_account:
        w.domain_lookup.return_value = ()
    review = confirm_command(w)
    name = NewAccountName(first_name="Synthetic", last_name="Pilot") if existing_account else None
    command = ConfirmAdministrator(value=review.value, confirmation=review.confirmation, name=name)
    with pytest.raises(AdministratorFailure) as denied:
        w.service.confirm(w.principal, command)
    assert denied.value.status == 400
    w.creator.assert_not_called()
    w.membership.assert_not_called()
    assert not any(str(call.args[0]).startswith("INSERT") for call in w.conn.execute.call_args_list)


# The create uses a narrow payload and waits for independent readback before assigning membership.
def test_new_account_uses_allowlisted_create_and_exact_readback(workflow):
    w = workflow
    w.domain_lookup.side_effect = [(), (), (w.account,)]
    command = confirm_command(w)
    events = Mock()
    events.attach_mock(w.creator, "create")
    events.attach_mock(w.domain_lookup, "read")
    events.attach_mock(w.membership, "membership")
    w.service.confirm(w.principal, command)
    payload, key = w.creator.call_args.args
    assert len(key) == 64 and key != command.confirmation
    assert payload["name"] == {"givenName": "Synthetic", "familyName": "Pilot"}
    assert set(payload) == {
        "schemas",
        "userName",
        "displayName",
        "name",
        "emails",
        "urn:ietf:params:scim:schemas:oracle:idcs:extension:user:User",
    }
    assert payload[payload["schemas"][1]] == {
        "isFederatedUser": True,
        "bypassNotification": True,
    }
    assert [call[0] for call in events.mock_calls] == ["read", "create", "read", "membership"]
    assert w.membership.call_args.args[0] == w.target.group


# Reconcile an ambiguous create or a conflict with a single verified lookup.
@pytest.mark.parametrize("failure", [TimeoutError, FederatedCreateConflict])
def test_new_account_reuses_verified_domain_account_after_uncertain_create(workflow, failure):
    w = workflow
    w.domain_lookup.side_effect = [(), (), (w.account,)]
    w.creator.side_effect = failure
    receipt = w.service.confirm(w.principal, confirm_command(w))
    assert receipt.status == "active"
    w.creator.assert_called_once()
    assert w.membership.call_args.args == (w.target.group, w.account.guid, True)


# A new administrator session keeps the provider retry key for the same verified create payload.
def test_uncertain_create_keeps_the_provider_key_across_admin_sessions(workflow):
    w = workflow
    w.domain_lookup.side_effect = [(), (), (), (), (), (w.account,)]
    w.creator.side_effect = [TimeoutError(), w.account]
    with pytest.raises(AdministratorFailure) as denied:
        w.service.confirm(w.principal, confirm_command(w))
    assert denied.value.status == 503
    w.membership.assert_not_called()
    w.principal = AdminPrincipal(w.principal.session.model_copy(update={"id": uuid4()}))
    assert w.service.confirm(w.principal, confirm_command(w)).status == "active"
    first, second = w.creator.call_args_list
    assert first.args == second.args
    w.membership.assert_called_once()


# A missing, reassigned or different account cannot reach group membership or grant creation.
@pytest.mark.parametrize(
    "fault",
    [
        "absent",
        "reassigned",
        "different-guid",
        "unverified-receipt",
        "native-readback",
        "native-receipt",
    ],
)
def test_new_account_requires_matching_receipt_and_independent_directory_binding(workflow, fault):
    w = workflow
    results = (w.account,)
    if fault == "absent":
        results = ()
    elif fault == "reassigned":
        results = (w.account.model_copy(update={"username": "reassigned@example.test"}),)
    elif fault == "different-guid":
        results = (w.account.model_copy(update={"guid": uuid4().hex}),)
    elif fault == "native-readback":
        results = (w.account.model_copy(update={"federated": False}),)
    elif fault == "native-receipt":
        w.creator.return_value = w.account.model_copy(update={"federated": False})
    else:
        w.creator.return_value = w.account.model_copy(
            update={"username": "unverified@example.test"}
        )
    w.domain_lookup.side_effect = [(), (), results]
    with pytest.raises(AdministratorFailure) as denied:
        w.service.confirm(w.principal, confirm_command(w))
    assert denied.value.status == (503 if fault in {"absent", "different-guid"} else 422)
    w.creator.assert_called_once()
    w.membership.assert_not_called()
    w.conn.execute.assert_not_called()


# Regrant keeps the prior stable grant ID and creates a new authorization revision.
def test_regrant_updates_revoked_grant_without_reusing_revision(workflow):
    w = workflow
    prior = grant(status="revoked", revoked_at=NOW)
    w.stored.return_value = prior.model_dump()
    result = w.service.confirm(w.principal, confirm_command(w))
    assert result.id == prior.id and result.authorization_revision != prior.authorization_revision
    assert any(str(call.args[0]).startswith("UPDATE") for call in w.conn.execute.call_args_list)


# Simulate the committed local revoke and ensure exact cleanup can't touch any other OCI object.
@pytest.mark.parametrize("failure", [None, "local", "remote", "readback"])
def test_removal_commits_before_exact_cleanup(workflow, failure):
    w = workflow
    prior = grant(workspace_id=w.target.workspace, issuer=w.target.issuer, subject=w.account.guid)
    revision = uuid4()
    revoked = prior.model_copy(
        update={"status": "revoked", "revoked_at": NOW, "authorization_revision": revision}
    )
    w.stored.return_value = revoked.model_dump()
    change = AdministratorChange(
        administrator_id=prior.id, status="revoked", authorization_revision=revision, at=NOW
    )
    events = Mock()
    events.attach_mock(w.store.revoke, "revoke")
    events.attach_mock(w.membership, "membership")
    w.store.revoke.return_value = change
    if failure == "local":
        w.store.revoke.side_effect = AdministratorFailure(503, "ADMINISTRATOR_SERVICE_UNAVAILABLE")
        with pytest.raises(AdministratorFailure):
            w.service.remove(w.principal, prior.id, prior.authorization_revision)
        w.membership.assert_not_called()
        return
    if failure == "remote":
        w.membership.side_effect = TimeoutError()
    elif failure == "readback":
        w.membership.return_value = False
    result = w.service.remove(w.principal, prior.id, prior.authorization_revision)
    assert result.group_cleanup == ("pending" if failure else "complete")
    assert [call[0] for call in events.mock_calls] == ["revoke", "membership"]
    w.membership.assert_called_once_with(w.target.group, w.account.guid, False, authorize=ANY)


# A stale cleanup receipt cannot mutate a regranted or unknown identity.
@pytest.mark.parametrize("case", ["missing", "active", "stale"])
def test_cleanup_rejects_old_or_foreign_revision(workflow, case):
    w = workflow
    prior = grant(status="revoked", revoked_at=NOW) if case == "stale" else grant()
    w.stored.return_value = None if case == "missing" else prior.model_dump()
    with pytest.raises(AdministratorFailure):
        w.service.cleanup(w.principal, prior.id, uuid4())
    w.membership.assert_not_called()


# The local protected namespace and unregistered issuers cannot be configured for provisioning.
def test_service_requires_a_distinct_trusted_issuer(workflow):
    w = workflow
    for issuer in (LOCAL, "urn:untrusted"):
        with pytest.raises(ValueError, match="UNTRUSTED_CORPORATE"):
            CorporateAdministrators(
                w.store,
                w.target.model_copy(update={"issuer": issuer}),
                w.domain_lookup,
                w.membership,
            )
