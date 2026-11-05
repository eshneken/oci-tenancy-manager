"""Environment routing preserves identities and rejects unsafe deployment/contact combinations."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_sessions import session_case
from test_tenancy_workflow_units import registry

__all__ = ["session_case", "registry"]

from otm.app import create_app
from otm.email_policy import EmailContacts, EmailPolicyBlocked, EmailRoute, MailPolicy, mailbox
from otm.notifications.runtime import compose_notifications
from otm.providers.email_contacts import activation_address, identity_contacts, validate_contacts
from otm.release_validation import main, validate_release
from otm.settings import (
    ApplicationSettings,
    ConfigurationError,
    NotificationSettings,
    load_settings,
)

CONFIG = Path(__file__).resolve().parents[1] / "config/application.toml"


# Redirection changes only external contact fields, including an explicitly email-less local admin.
@pytest.mark.parametrize("original", [None, "employee@example.test"])
def test_routes_preserve_identity(original):
    policy = MailPolicy(environment="staging", email_override="tester@example.test")
    route = policy.route(original)
    assert route.original_email == original
    assert policy.guard(route) == "tester@example.test"
    assert route.redirected
    assert policy.guard_address("tester@example.test") == "tester@example.test"
    assert len(policy.fingerprint) == 64
    request = identity_contacts(policy, "distinct.employee", route)
    assert request.username == "distinct.employee"
    assert request.primary_email == request.recovery_email == "tester@example.test"
    assert not request.use_email_as_username


# Production forbids overrides; staging must never silently deliver to source employees.
@pytest.mark.parametrize(
    "values",
    [
        {"environment": "production", "email_override": "tester@example.test"},
        {"environment": "staging"},
        {"environment": "staging", "email_override": ""},
    ],
)
def test_unsafe_environment(values):
    with pytest.raises(ValueError):
        MailPolicy(**values)


# Addresses cannot smuggle headers, multiple recipients, display names or non-string values.
@pytest.mark.parametrize(
    "value",
    [
        "a@example.test\r\nBcc: b@example.test",
        "a@example.test,b@example.test",
        "Name <a@example.test>",
        "a@localhost",
        "a..b@example.test",
        "",
        3,
        "a@" + "x" * 260,
    ],
)
def test_invalid_mailbox(value):
    with pytest.raises(EmailPolicyBlocked):
        mailbox(value)


# Frozen routes are checked against today's complete routing profile before any external call.
def test_route_change_blocks():
    original = MailPolicy(environment="staging", email_override="one@example.test")
    current = MailPolicy(environment="staging", email_override="two@example.test")
    with pytest.raises(EmailPolicyBlocked):
        current.guard(original.route("employee@example.test"))
    with pytest.raises(EmailPolicyBlocked):
        current.guard_address("employee@example.test")
    with pytest.raises(EmailPolicyBlocked):
        current.guard_address(None)
    with pytest.raises(EmailPolicyBlocked):
        MailPolicy().guard(MailPolicy().route(None))
    with pytest.raises(ValidationError):
        EmailRoute(
            original_email="bad",
            effective_email=None,
            environment="local",
            policy_hash="a" * 64,
            redirected=False,
        )
    with pytest.raises(EmailPolicyBlocked):
        MailPolicy().guard(MailPolicy().route("employee@example.test"))
    with pytest.raises(EmailPolicyBlocked):
        MailPolicy().guard_address("employee@example.test")
    live = MailPolicy(environment="production")
    assert live.guard(live.route("employee@example.test")) == "employee@example.test"
    assert live.guard_address("employee@example.test") == "employee@example.test"


# Activation, owner and shared-member contacts all require qualified snapshots; usernames stay real.
def test_provider_contacts():
    policy = MailPolicy(environment="staging", email_override="tester@example.test")
    contacts = EmailContacts(
        activation=policy.route(None),
        owner=policy.route("owner@example.test"),
        people={uuid4(): policy.route("member@example.test")},
    )
    intent = SimpleNamespace(action="create_tenancy", email_contacts=contacts)
    validate_contacts(policy, intent)
    assert activation_address(policy, intent) == "tester@example.test"
    intent.email_contacts = None
    for check in (validate_contacts, activation_address):
        with pytest.raises(EmailPolicyBlocked):
            check(policy, intent)
    intent.action = "import_tenancy"
    intent.email_contacts = EmailContacts(
        activation=MailPolicy().route(None), owner=policy.route("owner@example.test")
    )
    validate_contacts(policy, intent)


# Both release paths enforce independently selected environments before any credentials are loaded.
@pytest.mark.parametrize("kind", ["application", "configuration"])
def test_release_profiles(tmp_path, capsys, kind):
    base = CONFIG.read_text().split("# Laptop-only serving;")[0]
    staging = tmp_path / "staging.toml"
    staging.write_text(
        'environment = "staging"\n' + base + '\n[testing]\nemail_override = "tester@example.test"\n'
    )
    result = validate_release(staging, "staging", kind)
    assert result["email_redirected"] and result["release_kind"] == kind
    assert (
        main(
            ["--config", str(staging), "--expected-environment", "staging", "--release-kind", kind]
        )
        == 0
    )
    assert "tester@example.test" not in capsys.readouterr().out
    assert (
        main(
            [
                "--config",
                str(staging),
                "--expected-environment",
                "production",
                "--release-kind",
                kind,
            ]
        )
        == 1
    )
    assert capsys.readouterr().out.strip() == "RELEASE_SETTINGS_REJECTED"
    with pytest.raises(ValueError):
        validate_release(staging, "invalid", kind)
    with pytest.raises(ValueError):
        validate_release(staging, "staging", "invalid")
    production = tmp_path / "production.toml"
    production.write_text('environment = "production"\n' + base)
    assert not validate_release(production, "production", kind)["email_redirected"]
    production.write_text(production.read_text() + "\n[testing]\n")
    with pytest.raises(ConfigurationError):
        validate_release(production, "production", kind)
    local = tmp_path / "local.toml"
    local.write_text(
        'environment = "staging"\n'
        + CONFIG.read_text()
        + '\n[testing]\nemail_override = "tester@example.test"\n'
    )
    with pytest.raises(ValueError, match="LOCAL_SERVER_FORBIDDEN"):
        validate_release(local, "staging", kind)


# Hosted mail requires TLS and paired secret references; no credentials may fall back to defaults.
@pytest.mark.parametrize(
    "values",
    [
        {"smtp_host": "host name"},
        {"smtp_host": "remote.example.test"},
        {"username": "smtp-user"},
        {"password_secret_reference": "opaque"},
        {"sender_email": "bad"},
    ],
)
def test_invalid_transport_settings(values):
    with pytest.raises(ValueError):
        NotificationSettings(**values)


# SMTP capabilities are injected, and disabled settings do not construct a queue or transport.
def test_runtime_composition():
    settings = load_settings(CONFIG)
    assert compose_notifications(settings, "queue") == (None, None, None)
    settings = settings.model_copy(
        update={
            "notifications": NotificationSettings(
                enabled=True,
                tls_mode="starttls",
                username="user",
                password_secret_reference="opaque",
            )
        }
    )
    with pytest.raises(ValueError, match="SMTP_SECRET_PROVIDER_REQUIRED"):
        compose_notifications(settings, "queue")
    secret = Mock(return_value="private-test-only")
    with patch("otm.notifications.runtime.NotificationEnqueuer"):
        notifier, transport, enqueuer = compose_notifications(
            settings, "queue", secret_loader=secret
        )
    assert notifier.profile_hash == transport.profile_hash
    assert notifier.enqueuer is enqueuer
    secret.assert_not_called()
    assert transport.password_loader() == "private-test-only"
    secret.assert_called_once_with("opaque")


# The testing address cannot leak through a public unauthenticated configuration endpoint.
def test_email_policy_requires_sessions():
    with pytest.raises(ValueError, match="SESSION_BOUNDARY"):
        create_app(email_policy=MailPolicy())
    with TestClient(create_app()) as client:
        assert client.get("/api/email-policy").status_code == 404


# Authorized policy context is no-store and inaccessible without a verified administrator session.
def test_authenticated_policy_context(session_case):
    from test_auth_http import ORIGIN, cookie

    from otm.auth.http import BrowserSettings

    policy = MailPolicy(environment="staging", email_override="tester@example.test")
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), email_policy=policy
    )
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/email-policy").status_code == 401
        result = client.get("/api/email-policy", headers=cookie(session_case))
    assert result.status_code == 200
    assert result.json() == {
        "environment": "staging",
        "redirected": True,
        "effective_test_email": "tester@example.test",
    }
    assert result.headers["cache-control"] == "no-store"


# New optional contact evidence does not change hashes of previously accepted typed work.
def test_legacy_intent_hash_remains_compatible(registry):
    from test_tenancy_workflow_units import intent, person, service

    from otm.operations.contracts import canonical_hash
    from otm.tenancies.contracts import OrganizationIntent

    frozen = intent(registry, service(registry), person(registry))
    old_payload = frozen.model_dump(mode="json")
    assert "email_contacts" not in old_payload
    assert canonical_hash(
        OrganizationIntent.model_validate_json(frozen.model_dump_json()).model_dump(mode="json")
    ) == canonical_hash(old_payload)


# Database lookup remains scoped to the authenticated admin while contacts keep real identities.
def test_admin_contacts_do_not_rewrite_profiles():
    from otm.tenancies.workflows import OrganizationWorkflows

    app = OrganizationWorkflows(
        Mock(), mail_policy=MailPolicy(environment="staging", email_override="tester@example.test")
    )
    connection = Mock()
    connection.execute.return_value.scalar_one.return_value = None
    actor = SimpleNamespace(issuer="issuer", subject="subject")
    principal = SimpleNamespace(session=SimpleNamespace(workspace_id="workspace"), actor=actor)
    person = uuid4()
    result = app._email_contacts(
        connection, principal, "owner@example.test", {person: "member@example.test"}
    )
    assert result.activation.original_email is None
    assert result.people[person].original_email == "member@example.test"
    assert result.people[person].effective_email == "tester@example.test"
    assert result.owner.original_email == "owner@example.test"


# Deployment examples remain executable validation inputs for both independent release paths.
@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("kind", ["application", "configuration"])
def test_versioned_release_templates(environment, kind):
    result = validate_release(
        CONFIG.with_name(environment + ".application.toml"), environment, kind
    )
    assert result["email_redirected"] == (environment == "staging")


# Enabled hosted mail needs a trusted UI origin, and a local origin cannot conflict with serving.
def test_application_origin_guards():
    base = load_settings(CONFIG).model_dump()
    base.update(
        environment="production",
        local_server=None,
        notifications={"enabled": True, "tls_mode": "starttls"},
    )
    with pytest.raises(ValueError, match="NOTIFICATION_APPLICATION_ORIGIN_REQUIRED"):
        ApplicationSettings.model_validate(base)
    base.update(
        environment="local",
        local_server=load_settings(CONFIG).local_server,
        notifications={"enabled": True, "application_origin": "https://other.example.test"},
    )
    with pytest.raises(ValueError, match="NOTIFICATION_APPLICATION_ORIGIN_MISMATCH"):
        ApplicationSettings.model_validate(base)
