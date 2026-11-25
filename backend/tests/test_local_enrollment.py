"""Qualify restricted laptop account and group requests with synthetic OCI responses."""

import json
from configparser import Error as ConfigParserError
from types import SimpleNamespace
from unittest.mock import Mock

import oci
import pytest
from sqlalchemy.exc import SQLAlchemyError

from otm.auth.corporate_enrollment import (
    Enrollment,
    EnrollmentTarget,
    NewAccountName,
    federated_user_request,
    membership_request,
)
from otm.local_enrollment import (
    GROUP_ATTRIBUTES,
    LaptopEnrollment,
    laptop_database_accepts_grants,
    read_laptop_enrollment,
)
from otm.platform_auth import PublicOciCredentialPath
from otm.storage.corporate_administrators import FederatedCreateConflict

EMAIL = "synthetic@example.test"
GUID = "c" * 32
TENANCY = "ocid1.tenancy.oc1..synthetic"
USER = "ocid1.user.oc1..synthetic"
GROUP = "ocid1.group.oc1..synthetic"
MEMBERSHIP = "ocid1.groupmembership.oc1..synthetic"


# Use generated SDK response models without constructing a network client.
@pytest.fixture
def adapter_case(tmp_path):
    models = oci.identity_domains.models
    client = Mock()
    iam = Mock()
    target = EnrollmentTarget(
        environment="development",
        workspace="test",
        domain="test-domain",
        issuer="urn:example:oci",
        app="a" * 32,
        group="b" * 32,
    )
    user = models.User(
        id=GUID,
        ocid=USER,
        domain_ocid=target.domain,
        user_name=EMAIL,
        active=True,
        display_name="Synthetic",
        urn_ietf_params_scim_schemas_oracle_idcs_extension_user_user=models.ExtensionUserUser(
            is_federated_user=True
        ),
    )
    client.list_users.return_value.data = models.Users(total_results=1, resources=[user])
    client.create_user.return_value.data = user
    entry = models.Group(
        id=target.group,
        ocid=GROUP,
        domain_ocid=target.domain,
        display_name="otm-development-users",
    )
    client.get_group.return_value = SimpleNamespace(data=entry, headers={"etag": '"version"'})
    present = SimpleNamespace(data=models.Groups(total_results=1, resources=[entry]))
    absent = SimpleNamespace(data=models.Groups(total_results=0, resources=[]))
    member = oci.identity.models.UserGroupMembership(
        id=MEMBERSHIP,
        compartment_id=TENANCY,
        user_id=USER,
        group_id=GROUP,
        lifecycle_state="ACTIVE",
    )
    iam.list_user_group_memberships.return_value = SimpleNamespace(data=[member], next_page=None)
    return SimpleNamespace(
        adapter=LaptopEnrollment(client, iam, TENANCY, target, tmp_path),
        client=client,
        iam=iam,
        member=member,
        target=target,
        user=user,
        present=present,
        absent=absent,
        holds=tmp_path,
        payload=federated_user_request(
            Enrollment(email=EMAIL, target=target, account=None),
            NewAccountName(first_name="Synthetic", last_name="Pilot"),
        ),
    )


# Refuse a wrong domain, mismatched page size, or non-email input without a write.
def test_exact_user_lookup_and_complete_result(adapter_case):
    c = adapter_case
    assert c.adapter.lookup(c.target.domain, EMAIL)[0].guid == GUID
    assert c.client.list_users.call_args.kwargs["filter"] == 'userName eq "synthetic@example.test"'
    with pytest.raises(ValueError, match="DOMAIN_MISMATCH"):
        c.adapter.lookup("other", EMAIL)
    c.client.list_users.return_value.data.total_results = 2
    with pytest.raises(ValueError, match="INCOMPLETE"):
        c.adapter.lookup(c.target.domain, EMAIL)
    c.client.create_user.assert_not_called()
    c.client.patch_group.assert_not_called()


# Preserve only the allowlisted federated user and its idempotent SDK token.
def test_create_forwards_closed_payload_and_releases_hold(adapter_case):
    c = adapter_case
    key = "a" * 64
    with pytest.raises(ValueError, match="UNSAFE"):
        c.adapter.create(c.payload | {"password": "rejected"}, key)
    for name in (None, {"givenName": "Synthetic"}, c.payload["name"] | {"extra": "rejected"}):
        with pytest.raises(ValueError, match="UNSAFE"):
            c.adapter.create(c.payload | {"name": name}, key)
    c.client.create_user.assert_not_called()
    assert c.adapter.create(c.payload, key).guid == GUID
    kwargs = c.client.create_user.call_args.kwargs
    assert kwargs["user"] == c.payload and kwargs["opc_retry_token"] == key
    assert list(c.holds.iterdir()) == []


# Definite negative responses release the hold while a timeout fences new writes after restart.
@pytest.mark.parametrize(
    "error,exception,retained",
    [
        (409, FederatedCreateConflict, False),
        (403, oci.exceptions.ServiceError, False),
        (500, oci.exceptions.ServiceError, True),
        (None, TimeoutError, True),
    ],
)
def test_create_fences_unresolved_attempt(adapter_case, error, exception, retained):
    c = adapter_case
    c.client.create_user.side_effect = (
        oci.exceptions.ServiceError(error, "Synthetic", {}, "Synthetic")
        if error
        else oci.exceptions.RequestException("synthetic transport error")
    )
    with pytest.raises(exception):
        c.adapter.create(c.payload, "z" * 64)
    assert bool(list(c.holds.iterdir())) is retained
    if retained:
        restarted = LaptopEnrollment(c.client, c.iam, TENANCY, c.target, c.holds)
        with pytest.raises(FileExistsError):
            restarted.create(c.payload, "y" * 64)
        c.client.create_user.assert_called_once()


# Native removal deletes only the verified membership OCID and adds only the verified pair.
@pytest.mark.parametrize("add", [False, True])
def test_group_write_and_idempotent_readback(adapter_case, add):
    c = adapter_case
    before, after = (c.absent, c.present) if add else (c.present, c.absent)
    c.client.list_groups.side_effect = [before, after, after]
    absent = SimpleNamespace(data=[], next_page=None)
    present = c.iam.list_user_group_memberships.return_value
    before_native, after_native = (absent, present) if add else (present, absent)
    c.iam.list_user_group_memberships.side_effect = [before_native, after_native, after_native]
    args = membership_request(c.target, GUID, add=add)
    assert c.adapter.membership(*args)
    assert c.adapter.membership(*args)
    calls = c.iam.list_user_group_memberships.call_args_list
    assert len(calls) == 3
    assert all(
        call.args == (TENANCY,)
        and call.kwargs
        == {
            "group_id": GROUP,
            "user_id": USER,
            "limit": 2,
        }
        for call in calls
    )
    if add:
        details = c.iam.add_user_to_group.call_args.args[0]
        assert (details.group_id, details.user_id) == (GROUP, USER)
        c.iam.remove_user_from_group.assert_not_called()
    else:
        c.iam.remove_user_from_group.assert_called_once_with(MEMBERSHIP)
        c.iam.add_user_to_group.assert_not_called()
    c.client.patch_group.assert_not_called()
    c.client.delete_user.assert_not_called()
    assert c.client.list_groups.call_args.kwargs["filter"] == (
        f'id eq "{c.target.group}" and members.value eq "{GUID}"'
    )
    assert c.client.list_users.call_args.kwargs["filter"] == f'id eq "{GUID}"'
    assert list(c.holds.iterdir()) == []


# Unknown write outcomes or delayed readback fence opposite mutations after restart.
@pytest.mark.parametrize("timeout", [False, True])
def test_group_fence_blocks_opposite_mutation(adapter_case, timeout):
    c = adapter_case
    c.client.list_groups.return_value = c.present
    if timeout:
        c.iam.remove_user_from_group.side_effect = oci.exceptions.RequestException(
            "synthetic transport error"
        )
        with pytest.raises(oci.exceptions.RequestException):
            c.adapter.membership(*membership_request(c.target, GUID, add=False))
    else:
        assert not c.adapter.membership(*membership_request(c.target, GUID, add=False))
    restarted = LaptopEnrollment(c.client, c.iam, TENANCY, c.target, c.holds)
    with pytest.raises(FileExistsError):
        restarted.membership(*membership_request(c.target, GUID, add=True))
    c.iam.remove_user_from_group.assert_called_once()
    c.iam.add_user_to_group.assert_not_called()
    if not timeout:
        c.client.list_groups.return_value = c.absent
        with pytest.raises(FileExistsError):
            restarted.membership(*membership_request(c.target, GUID, add=True))
        c.iam.list_user_group_memberships.return_value.data = []
        assert restarted.membership(*membership_request(c.target, GUID, add=False))
        assert not list(c.holds.iterdir())
        c.iam.remove_user_from_group.assert_called_once()
        c.client.list_groups.side_effect = [c.absent, c.present]
        c.iam.list_user_group_memberships.side_effect = [
            SimpleNamespace(data=[], next_page=None),
            SimpleNamespace(data=[c.member], next_page=None),
        ]
        assert restarted.membership(*membership_request(c.target, GUID, add=True))
        c.iam.add_user_to_group.assert_called_once()


# Reject invalid input and stale, foreign or paginated membership lookup before writing.
@pytest.mark.parametrize(
    "fault",
    [
        "group",
        "direction",
        "group-domain",
        "user-domain",
        "bad-ocid",
        "foreign-user",
        "foreign-group",
        "foreign-tenancy",
        "page",
        "duplicate",
    ],
)
def test_group_scope_and_precondition_fail_closed(adapter_case, fault):
    c = adapter_case
    group, subject, add = membership_request(c.target, GUID, add=False)
    c.client.list_groups.return_value = c.present
    if fault == "group":
        group = "unrelated"
    elif fault == "direction":
        add = "remove"
    elif fault == "group-domain":
        c.client.get_group.return_value.data.domain_ocid = "other"
    elif fault == "user-domain":
        c.user.domain_ocid = "other"
    elif fault == "bad-ocid":
        c.member.id = USER
    elif fault == "foreign-user":
        c.member.user_id = "other"
    elif fault == "foreign-group":
        c.member.group_id = "other"
    elif fault == "foreign-tenancy":
        c.member.compartment_id = "other"
    elif fault == "page":
        c.iam.list_user_group_memberships.return_value.next_page = "more"
    else:
        c.iam.list_user_group_memberships.return_value.data.append(c.member)
    with pytest.raises(ValueError):
        c.adapter.membership(group, subject, add)
    assert not list(c.holds.iterdir())
    c.iam.add_user_to_group.assert_not_called()
    c.iam.remove_user_from_group.assert_not_called()


# If OCI's two membership views disagree or the association is transitioning, defer the write.
@pytest.mark.parametrize(
    "fault", ["native-missing", "existing-add", "deleting", "creating-visible"]
)
def test_transitional_membership_defers_without_dispatch(adapter_case, fault):
    c = adapter_case
    add = fault in ("existing-add", "creating-visible")
    c.client.list_groups.return_value = c.absent if fault == "existing-add" else c.present
    if fault == "native-missing":
        c.iam.list_user_group_memberships.return_value.data = []
    elif fault == "deleting":
        c.member.lifecycle_state = "DELETING"
    elif fault == "creating-visible":
        c.member.lifecycle_state = "CREATING"
    assert c.adapter.membership(*membership_request(c.target, GUID, add=add)) is False
    assert not list(c.holds.iterdir())
    c.iam.add_user_to_group.assert_not_called()
    c.iam.remove_user_from_group.assert_not_called()


# Missing, unsafe and matching profiles keep mutation routes unavailable.
@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "shared",
        "public",
        "signer",
        "parse",
        "client",
        "same-user",
        "same-key",
        "key",
        "hold",
    ],
)
def test_laptop_activation_rejects_bad_or_shared_registration(adapter_case, monkeypatch, fault):
    settings = SimpleNamespace(
        oci=SimpleNamespace(profile="readiness", region="region", tenancy_ocid="id")
    )
    c = adapter_case
    frontend = c.holds / "dist"
    registration = c.holds / "corporate-enrollment.json"
    if fault != "missing":
        registration.write_text(
            json.dumps(
                {
                    "profile": "readiness" if fault == "shared" else "enrollment",
                    "config_file": str((frontend if fault == "public" else c.holds) / "config"),
                }
            )
        )
        registration.chmod(0o600)
    identity = SimpleNamespace(
        client_config={
            "key_file": str((frontend if fault == "key" else c.holds) / "key"),
            "user": "writer",
            "fingerprint": "writer-key",
        },
        signer=object(),
    )
    readiness = SimpleNamespace(
        client_config={
            "user": "writer" if fault == "same-user" else "reader",
            "fingerprint": "writer-key" if fault == "same-key" else "reader-key",
        }
    )
    signer = Mock(
        side_effect={"signer": ValueError, "parse": ConfigParserError}.get(
            fault, [identity, readiness]
        )
    )
    monkeypatch.setattr("otm.local_enrollment.api_key_signer", signer)
    sdk = Mock(side_effect=oci.exceptions.ClientError if fault == "client" else None)
    monkeypatch.setattr("otm.local_enrollment.oci.identity_domains.IdentityDomainsClient", sdk)
    monkeypatch.setattr(
        "otm.local_enrollment.laptop_database_accepts_grants", Mock(return_value=True)
    )
    if fault == "hold":
        (c.holds / "corporate-enrollment-holds").mkdir(mode=0o755)
    corporate = SimpleNamespace(
        target=c.target, oidc=SimpleNamespace(provider_origin="https://example.test")
    )
    if fault == "public":
        with pytest.raises(PublicOciCredentialPath):
            read_laptop_enrollment(c.holds, corporate, settings, Mock(), frontend)
    else:
        assert read_laptop_enrollment(c.holds, corporate, settings, Mock(), frontend) is None


# Mount only explicit development enrollment, with new-user creation separately controlled.
@pytest.mark.parametrize("create", [False, True])
def test_laptop_registration_routes_to_pinned_writer(adapter_case, monkeypatch, create):
    c = adapter_case
    settings = SimpleNamespace(
        oci=SimpleNamespace(profile="readiness", region="region", tenancy_ocid="id")
    )
    registration = c.holds / "corporate-enrollment.json"
    registration.write_text(
        json.dumps(
            {
                "profile": "enrollment",
                "config_file": str(c.holds / "config"),
                "create_users": create,
            }
        )
    )
    registration.chmod(0o600)
    identity = SimpleNamespace(
        client_config={
            "key_file": str(c.holds / "key"),
            "user": "writer",
            "fingerprint": "writer-key",
        },
        signer=object(),
    )
    readiness = SimpleNamespace(client_config={"user": "reader", "fingerprint": "reader-key"})
    monkeypatch.setattr(
        "otm.local_enrollment.api_key_signer", Mock(side_effect=[identity, readiness])
    )
    sdk = Mock(return_value=c.client)
    monkeypatch.setattr("otm.local_enrollment.oci.identity_domains.IdentityDomainsClient", sdk)
    corporate = SimpleNamespace(
        target=c.target, oidc=SimpleNamespace(provider_origin="https://example.test")
    )
    monkeypatch.setattr(
        "otm.local_enrollment.oci.identity.IdentityClient", Mock(return_value=c.iam)
    )
    store = Mock(local_issuer="urn:example:local", trusted_issuers={c.target.issuer})
    rights = Mock(side_effect=[False, True])
    monkeypatch.setattr("otm.local_enrollment.laptop_database_accepts_grants", rights)
    assert read_laptop_enrollment(c.holds, corporate, settings, store, c.holds / "dist") is None
    monkeypatch.setattr(
        "otm.local_enrollment.api_key_signer", Mock(side_effect=[identity, readiness])
    )
    enrollment = read_laptop_enrollment(c.holds, corporate, settings, store, c.holds / "dist")
    assert enrollment.target == c.target and bool(enrollment.create) is create
    assert sdk.call_args.kwargs["service_endpoint"] == "https://example.test"
    c.client.get_group.assert_called_once_with(c.target.group, attributes=GROUP_ATTRIBUTES)
    c.client.patch_group.assert_not_called()
    c.client.create_user.assert_not_called()


# Bound the waiter without claiming that a running provider write has been cancelled.
@pytest.mark.parametrize("cancelled", [True, False])
def test_enrollment_deadline_limits_wait_and_requests_cancel(monkeypatch, tmp_path, cancelled):
    from otm.local_enrollment import CALL_DEADLINE, enrollment_io

    future = Mock()
    future.result.side_effect = TimeoutError()
    future.cancel.return_value = cancelled
    hold = tmp_path / "synthetic.pending"
    hold.touch()
    executor = Mock()
    executor.submit.return_value = future
    monkeypatch.setattr("otm.local_enrollment.ENROLLMENT_IO", executor)
    with pytest.raises(TimeoutError):
        enrollment_io(Mock(), "operand", hold=hold)
    assert hold.exists() is not cancelled
    future.result.assert_called_once_with(timeout=CALL_DEADLINE)
    future.cancel.assert_called_once()


# Read the domain returned by OCI so a mismatched result cannot pass the workflow's domain check.
def test_user_projection_does_not_infer_domain_from_configuration(adapter_case):
    c = adapter_case
    c.user.domain_ocid = "wrong"
    assert c.adapter.lookup(c.target.domain, EMAIL)[0].domain == "wrong"


# A worker that finishes preflight after the deadline has never been authorized to mutate OCI.
def test_membership_preflight_timeout_cannot_dispatch(adapter_case, monkeypatch):
    c = adapter_case
    c.client.list_groups.return_value = c.present
    future = Mock()
    future.result.side_effect = TimeoutError()
    future.cancel.return_value = False
    executor = Mock()
    executor.submit.return_value = future
    monkeypatch.setattr("otm.local_enrollment.ENROLLMENT_IO", executor)
    authorize = Mock()
    with pytest.raises(TimeoutError):
        c.adapter.membership(c.target.group, GUID, False, authorize=authorize)
    preflight, *arguments = executor.submit.call_args.args
    preflight(*arguments)
    executor.submit.assert_called_once()
    authorize.assert_not_called()
    c.iam.remove_user_from_group.assert_not_called()
    assert not list(c.holds.iterdir())


# Recheck the actor after resolving membership and reject a different valid named group.
@pytest.mark.parametrize("fault", ["actor", "group"])
def test_membership_stops_before_dispatch_on_preflight_denial(adapter_case, fault):
    c = adapter_case
    c.client.list_groups.return_value = c.present
    authorize = Mock(side_effect=PermissionError)
    if fault == "group":
        c.client.get_group.return_value.data.display_name = "otm-staging-users"
    with pytest.raises((PermissionError, ValueError)):
        c.adapter.membership(c.target.group, GUID, False, authorize=authorize)
    assert authorize.call_count == int(fault == "actor")
    c.iam.remove_user_from_group.assert_not_called()
    assert not list(c.holds.iterdir())


# Avoid exposing enrollment on a database role without every required INSERT column.
@pytest.mark.parametrize("state,expected", [(True, True), (False, False), (None, False)])
def test_laptop_database_grant_preflight(state, expected):
    from contextlib import nullcontext

    connection = Mock()
    connection.scalar.return_value = state
    store = Mock()
    store.engine.connect.return_value = nullcontext(connection)
    assert laptop_database_accepts_grants(store) is expected
    statement, arguments = connection.scalar.call_args_list[0].args
    assert "has_column_privilege" in str(statement)
    assert set(arguments["columns"]) >= {"subject", "identity_kind"}
    store.engine.connect.side_effect = SQLAlchemyError()
    assert laptop_database_accepts_grants(store) is False


# An abnormal create cannot become eligible for existing-account enrollment on another request.
@pytest.mark.parametrize("source", ["receipt", "readback", "different-guid"])
def test_abnormal_create_is_held_and_cannot_be_reused(adapter_case, source):
    c = adapter_case
    native = oci.identity_domains.models.User(
        id=c.user.id, user_name=c.user.user_name, active=True, domain_ocid=c.user.domain_ocid
    )
    if source == "receipt":
        c.client.create_user.return_value.data = native
    elif source == "readback":
        c.client.list_users.return_value.data.resources = [native]
    else:
        c.client.create_user.return_value.data = oci.identity_domains.models.User(
            id="d" * 32,
            user_name=c.user.user_name,
            active=True,
            domain_ocid=c.user.domain_ocid,
            urn_ietf_params_scim_schemas_oracle_idcs_extension_user_user=(
                oci.identity_domains.models.ExtensionUserUser(is_federated_user=True)
            ),
        )
    with pytest.raises(ValueError, match="RECONCILIATION"):
        c.adapter.create(c.payload, "c" * 64)
    assert len(list(c.holds.iterdir())) == 1
    c.client.list_users.return_value.data.resources = [c.user]
    restarted = LaptopEnrollment(c.client, c.iam, TENANCY, c.target, c.holds)
    with pytest.raises(ValueError, match="RECONCILIATION"):
        restarted.lookup(c.target.domain, EMAIL)
    c.client.patch_group.assert_not_called()


# Explicitly share only the configured scoped 8445 profile and verify reads before mounting.
@pytest.mark.parametrize("fault", [None, "8443", "hosted", "different-profile", "denied"])
def test_enrollment_can_share_the_explicit_scoped_application_profile(
    adapter_case, monkeypatch, fault
):
    c = adapter_case
    frontend = c.holds / "dist"
    config_file = str(c.holds / "oci-config")
    registration = c.holds / "corporate-enrollment.json"
    registration.write_text(
        json.dumps(
            {
                "config_file": config_file,
                "profile": "scoped",
                "use_application_profile": True,
                "create_users": True,
            }
        )
    )
    registration.chmod(0o600)
    policy = SimpleNamespace(
        auth_method="api_key_profile",
        config_file=config_file,
        tenancy_ocid=TENANCY,
        profile="other" if fault == "different-profile" else "scoped",
    )
    settings = SimpleNamespace(oci=policy, environment="staging" if fault == "hosted" else "local")
    corporate = SimpleNamespace(
        target=c.target,
        oidc=SimpleNamespace(
            provider_origin="https://example.test",
            installation_origin="https://127.0.0.1:8443"
            if fault == "8443"
            else "https://127.0.0.1:8445",
        ),
    )
    identity = SimpleNamespace(client_config={"key_file": str(c.holds / "key")}, signer=object())
    signer = Mock(return_value=identity)
    monkeypatch.setattr("otm.local_enrollment.api_key_signer", signer)
    monkeypatch.setattr(
        "otm.local_enrollment.oci.identity_domains.IdentityDomainsClient",
        Mock(return_value=c.client),
    )
    monkeypatch.setattr(
        "otm.local_enrollment.laptop_database_accepts_grants", Mock(return_value=True)
    )
    if fault == "denied":
        c.client.get_group.side_effect = oci.exceptions.ServiceError(401, "Denied", {}, "Denied")
    monkeypatch.setattr(
        "otm.local_enrollment.oci.identity.IdentityClient", Mock(return_value=c.iam)
    )
    store = Mock(local_issuer="urn:example:local", trusted_issuers={c.target.issuer})
    enrollment = read_laptop_enrollment(c.holds, corporate, settings, store, frontend)
    if fault is None:
        assert enrollment.create is not None
    else:
        assert enrollment is None
    if fault in (None, "denied"):
        signer.assert_called_once_with(policy)
        c.client.get_group.assert_called_once()
        c.client.patch_group.assert_not_called()
    else:
        signer.assert_not_called()


# Denied member removal records status only and releases a definitive rejection's hold.
def test_membership_rejection_logs_only_safe_diagnostics(adapter_case, caplog):
    c = adapter_case
    c.client.list_groups.return_value = c.present
    c.iam.remove_user_from_group.side_effect = oci.exceptions.ServiceError(
        401, "NotAuthorized", {}, "private provider details"
    )
    with pytest.raises(oci.exceptions.ServiceError):
        c.adapter.membership(*membership_request(c.target, GUID, add=False))
    assert "membership remove rejected (HTTP 401)" in caplog.text
    assert "private provider details" not in caplog.text
    assert GUID not in caplog.text
    assert not list(c.holds.iterdir())
