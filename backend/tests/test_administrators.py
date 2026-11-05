"""Current-grant and revocation unit contracts, separate from real database proofs."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from test_admission_service import NOW
from test_sessions import session_case

from otm.auth.administrators import Administrator, AdministratorFailure
from otm.auth.service import AdminPrincipal
from otm.storage.administrators import SqlAdministratorStore

__all__ = ["session_case"]
LOCAL = "urn:otm:example-installation:local"


# Build a closed independent grant, using a UUID subject for the protected local kind.
def grant(*, local=False, **changes):
    identifier = uuid4()
    values = dict(
        id=identifier,
        workspace_id="example-org",
        identity_kind="local_recovery" if local else "corporate_sso",
        issuer=LOCAL if local else "https://sso.example.test",
        subject=str(identifier) if local else "admin-one",
        display_name="Synthetic administrator",
        email=None,
        status="active",
        authorization_revision=uuid4(),
        created_at=NOW,
        updated_at=NOW,
        revoked_at=None,
    )
    values.update(changes)
    return Administrator(**values)


# Stub only IO while retaining the real query construction, model checks and transaction boundary.
@pytest.fixture
def admin_db(session_case):
    actor = grant()
    session = session_case.session.model_copy(
        update={
            "entitlement_reference": str(actor.id),
            "entitlement_revision": actor.authorization_revision,
        }
    )
    connection = MagicMock()
    engine = Mock(
        connect=Mock(return_value=nullcontext(connection)),
        begin=Mock(return_value=nullcontext(connection)),
    )
    clock = Mock(return_value=NOW)
    store = SqlAdministratorStore(
        engine, clock, local_issuer=LOCAL, trusted_issuers=frozenset({LOCAL, actor.issuer})
    )
    target = grant(subject="another-administrator")
    return SimpleNamespace(
        actor=actor,
        session=session,
        principal=AdminPrincipal(session),
        target=target,
        connection=connection,
        engine=engine,
        clock=clock,
        store=store,
    )


# Model validation rejects inconsistent local identity, status and chronological state.
@pytest.mark.parametrize(
    "changes",
    [
        {"subject": "email-is-not-a-subject"},
        {"status": "revoked", "revoked_at": NOW},
        {"updated_at": NOW - timedelta(seconds=1)},
        {"revoked_at": NOW},
        {"status": "revoked", "revoked_at": NOW - timedelta(seconds=1)},
    ],
)
def test_invalid_grant_record_is_rejected(changes):
    with pytest.raises(ValidationError):
        grant(local=True, **changes)


# Namespace configuration cannot be inferred from requests or silently coerced into trust.
@pytest.mark.parametrize(
    "issuers", [set([LOCAL]), frozenset(), frozenset({"other"}), frozenset({LOCAL, " "})]
)
def test_explicit_issuer_registry_required(issuers):
    with pytest.raises(ValueError):
        SqlAdministratorStore(Mock(), Mock(), local_issuer=LOCAL, trusted_issuers=issuers)


# Current exact-scope authority returns the actual stable grant reference and revision.
def test_fresh_grant_authority_uses_parameterized_identity(admin_db):
    c = admin_db
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        c.actor.model_dump()
    )
    result = c.store.require_admin(c.actor.issuer, c.actor.subject, c.actor.workspace_id)
    assert result.reference == str(c.actor.id) and result.revision == c.actor.authorization_revision
    assert result.valid_until == NOW + timedelta(seconds=5)
    query = c.connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert (
        c.actor.subject in query.params.values() and c.actor.workspace_id in query.params.values()
    )


# Presence cannot authorize revoked records, borrowed namespaces or unknown identities.
@pytest.mark.parametrize("damage", ["missing", "revoked", "local_namespace", "untrusted"])
def test_grant_authority_denies_invalid_current_grants(admin_db, damage):
    c = admin_db
    actor = (
        c.actor.model_copy(update={"status": "revoked", "revoked_at": NOW})
        if damage == "revoked"
        else c.actor
    )
    if damage == "local_namespace":
        actor = grant(issuer=LOCAL)
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        None if damage == "missing" else actor.model_dump()
    )
    with pytest.raises(PermissionError):
        c.store.require_admin(
            "untrusted" if damage == "untrusted" else actor.issuer,
            actor.subject,
            actor.workspace_id,
        )


# Supply ordered responses; SQL integration tests separately verify each real database effect.
def prepare(c, *, anchor=True, session=True, target=True, actor=None):
    results = [Mock(), Mock(), Mock(), Mock(), Mock(), Mock(), Mock()]
    results[0].scalar_one_or_none.return_value = uuid4() if anchor else None
    results[1].mappings.return_value.one_or_none.return_value = (
        c.session.model_dump() if session else None
    )
    results[2].mappings.return_value.one_or_none.return_value = (actor or c.actor).model_dump()
    results[3].mappings.return_value.one_or_none.return_value = (
        c.target.model_dump() if target else None
    )
    c.connection.execute.side_effect = results


# A successful mutation checks live authority, changes revision, revokes sessions and audits once.
def test_atomic_revoke_builds_scoped_updates_and_closed_evidence(admin_db):
    c = admin_db
    prepare(c)
    with patch("otm.storage.administrators.require_transaction"):
        result = c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    assert (
        result.status == "revoked"
        and result.authorization_revision != c.target.authorization_revision
    )
    statements = [
        call.args[0].compile(dialect=postgresql.dialect())
        for call in c.connection.execute.call_args_list
    ]
    assert "FOR UPDATE" in str(statements[0]) and "FOR UPDATE" in str(statements[3])
    assert "public.otm_admin_session" in str(statements[5])
    assert statements[6].params["operation_id"] is None
    assert statements[6].params["kind"] == "administrator_revoked"
    assert statements[6].params["data"]["prior_revision"] == str(c.target.authorization_revision)


# A matched repeat returns existing revocation without a second audit event or state rewrite.
def test_already_revoked_target_is_noop_with_current_revision(admin_db):
    c = admin_db
    c.target = c.target.model_copy(update={"status": "revoked", "revoked_at": NOW})
    prepare(c)
    with patch("otm.storage.administrators.require_transaction"):
        result = c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    assert result.authorization_revision == c.target.authorization_revision
    assert c.connection.execute.call_count == 4


# Every missing, protected or changed authority boundary refuses before the first mutation.
@pytest.mark.parametrize(
    "damage,status",
    [
        ("anchor", 503),
        ("session", 403),
        ("identity", 403),
        ("actor", 403),
        ("reference", 403),
        ("revision", 403),
        ("target", 404),
        ("protected", 403),
        ("expected", 409),
    ],
)
def test_revoke_rechecks_scope_and_state_before_writing(admin_db, damage, status):
    c = admin_db
    if damage == "identity":
        c.principal = AdminPrincipal(c.session.model_copy(update={"subject": "other"}))
    if damage == "reference":
        c.session = c.session.model_copy(update={"entitlement_reference": "old-reference"})
    if damage == "revision":
        c.session = c.session.model_copy(update={"entitlement_revision": uuid4()})
    if damage == "protected":
        c.target = grant(local=True)
    prepare(
        c,
        anchor=damage != "anchor",
        session=damage != "session",
        target=damage != "target",
        actor=c.actor.model_copy(update={"status": "revoked", "revoked_at": NOW})
        if damage == "actor"
        else None,
    )
    with (
        patch("otm.storage.administrators.require_transaction"),
        pytest.raises(AdministratorFailure) as error,
    ):
        c.store.revoke(
            c.principal,
            c.target.id,
            uuid4() if damage == "expected" else c.target.authorization_revision,
        )
    assert error.value.status == status and c.connection.execute.call_count <= 4


# Reject unvalidated caller objects and malformed commands before any transaction.
def test_revoke_requires_principal_and_uuid_commands(admin_db):
    for principal, target, revision, status in [
        (object(), uuid4(), uuid4(), 403),
        (admin_db.principal, "not-id", uuid4(), 400),
    ]:
        with pytest.raises(AdministratorFailure) as error:
            admin_db.store.revoke(principal, target, revision)
        assert error.value.status == status
    admin_db.engine.begin.assert_not_called()


# Audit/COMMIT/connection failures do not return success or leak raw exceptions.
def test_storage_failure_is_fixed_unavailable(admin_db):
    c = admin_db
    c.engine.begin.side_effect = RuntimeError("private database material")
    with pytest.raises(AdministratorFailure) as error:
        c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    assert (
        str(error.value) == "ADMINISTRATOR_SERVICE_UNAVAILABLE" and error.value.__suppress_context__
    )


# Unknown public diagnostics cannot accidentally expose arbitrary provider or database text.
def test_failure_boundary_rejects_arbitrary_error_text():
    with pytest.raises(ValueError, match="INVALID_ADMINISTRATOR_DIAGNOSTIC"):
        AdministratorFailure(500, "private-example")


# Database timezone presentation must preserve the actual instant, without accepting naive time.
@pytest.mark.parametrize("naive", [False, True])
def test_grant_record_normalizes_only_aware_database_time(naive):
    from datetime import timezone

    from otm.storage.administrators import administrator_record

    values = grant().model_dump()
    values["created_at"] = (
        NOW.replace(tzinfo=None) if naive else NOW.astimezone(timezone(timedelta(hours=1)))
    )
    if naive:
        with pytest.raises(ValueError, match="INVALID_ADMINISTRATOR_TIMESTAMP"):
            administrator_record(values)
    else:
        assert administrator_record(values).created_at == NOW


# Compile literal search and bounded sorting while mapping only public fields from storage.
@pytest.mark.parametrize("direction,query", [("asc", ""), ("desc", "%_")])
def test_directory_maps_public_page_and_literal_filter(admin_db, direction, query):
    from otm.auth.administrators import AdministratorQuery, AdministratorView

    c = admin_db.connection
    c.execute.return_value.one.return_value = (13, 12, 1)
    c.scalar.return_value = 1
    row = {key: getattr(admin_db.target, key) for key in AdministratorView.model_fields}
    c.execute.return_value.mappings.return_value.all.return_value = [row]
    result = admin_db.store.directory(
        "example-org", AdministratorQuery(page=100, sort="email", direction=direction, query=query)
    )
    assert result.page == 1 and result.pages == 1 and result.statistics.total == 13
    assert result.items[0].id == admin_db.target.id
    statement = c.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "workspace_id" in str(statement) and "otm_local_credential" not in str(statement)
    if query:
        assert "/%/_" in statement.params.values()
        assert "ESCAPE" in str(statement)
