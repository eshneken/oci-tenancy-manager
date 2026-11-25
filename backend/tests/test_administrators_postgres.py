"""Real protected grants, authority, atomic revocation and restricted-role tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_administrators import LOCAL, grant
from test_admission_service import NOW
from test_sessions import session_case

from otm.auth.administrators import AdministratorFailure, AdministratorQuery
from otm.auth.corporate_enrollment import (
    CorporateLookup,
    DomainPerson,
    EnrollmentTarget,
    NewAccountName,
    membership_request,
)
from otm.auth.corporate_entitlements import CorporateEntitlements
from otm.auth.corporate_oidc import VerifiedDomainLogin
from otm.auth.service import AdminPrincipal, SessionFailure, SessionService
from otm.settings import load_settings
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.corporate_administrators import ConfirmAdministrator, CorporateAdministrators
from otm.storage.corporate_sessions import EVENT, SqlCorporateSessions
from otm.storage.sessions import SqlSessionRepository
from otm.storage.tables import admin_session, administrator, audit_event, local_credential

pytestmark = pytest.mark.postgres
__all__ = ["session_case"]


# Seed only synthetic database fixtures; no production bootstrap/password/sign-in path is invented.
@pytest.fixture
def grants_case(pg_engine, session_case):
    workspace = "grants-" + uuid4().hex
    recovery = grant(local=True, workspace_id=workspace)
    actor = grant(workspace_id=workspace)
    target = grant(workspace_id=workspace, subject="target-administrator")
    session = session_case.session.model_copy(
        update={
            "workspace_id": workspace,
            "entitlement_reference": str(actor.id),
            "entitlement_revision": actor.authorization_revision,
        }
    )
    target_session = session.model_copy(
        update={
            "id": uuid4(),
            "session_token_hash": uuid4().hex + uuid4().hex,
            "subject": target.subject,
            "entitlement_reference": str(target.id),
            "entitlement_revision": target.authorization_revision,
        }
    )
    with pg_engine.begin() as connection:
        for row in (recovery, actor, target):
            connection.execute(administrator.insert().values(**row.model_dump()))
        for row in (session, target_session):
            connection.execute(admin_session.insert().values(**row.model_dump()))
    store = SqlAdministratorStore(
        pg_engine, lambda: NOW, local_issuer=LOCAL, trusted_issuers=frozenset({LOCAL, actor.issuer})
    )
    sessions = SqlSessionRepository(pg_engine)
    service = SessionService(sessions, store, actor.issuer, lambda: NOW)
    return SimpleNamespace(
        engine=pg_engine,
        workspace=workspace,
        recovery=recovery,
        actor=actor,
        target=target,
        session=session,
        target_session=target_session,
        store=store,
        sessions=sessions,
        service=service,
        principal=service.authenticate(session_case.handle),
        handle=session_case.handle,
    )


# Read committed state independently instead of relying on an adapter's returned receipt.
def state(c):
    with c.engine.connect() as connection:
        target = (
            connection.execute(select(administrator).where(administrator.c.id == c.target.id))
            .mappings()
            .one()
        )
        session = (
            connection.execute(
                select(admin_session).where(admin_session.c.id == c.target_session.id)
            )
            .mappings()
            .one()
        )
        events = (
            connection.execute(select(audit_event).where(audit_event.c.workspace_id == c.workspace))
            .mappings()
            .all()
        )
    return target, session, events


# Bound actor/current grant and target sessions change together with append-only, non-operation
# audit.
def test_revoke_commits_revision_sessions_and_closed_audit(grants_case):
    c = grants_case
    result = c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    target, session, events = state(c)
    assert (
        target["status"] == "revoked"
        and target["authorization_revision"] == result.authorization_revision
    )
    assert session["revoked_at"] == NOW and len(events) == 1
    assert events[0]["operation_id"] is None and events[0]["administrator_id"] == c.target.id
    assert events[0]["data"]["prior_revision"] == str(c.target.authorization_revision)
    with pytest.raises(PermissionError):
        c.store.require_admin(c.target.issuer, c.target.subject, c.workspace)
    assert c.service.authenticate(c.handle).session.id == c.session.id
    again = c.store.revoke(c.principal, c.target.id, result.authorization_revision)
    assert again == result and len(state(c)[2]) == 1
    with pytest.raises(AdministratorFailure) as error:
        c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    assert error.value.status == 409
    with pytest.raises(DBAPIError):
        with c.engine.begin() as connection:
            connection.execute(audit_event.delete().where(audit_event.c.id == events[0]["id"]))


# A later regrant cannot make an old session valid, even if its revoked timestamp were cleared.
def test_revision_regrant_never_revives_old_session(grants_case):
    c = grants_case
    c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == c.target.id)
            .values(status="active", revoked_at=None, authorization_revision=uuid4())
        )
        connection.execute(
            update(admin_session)
            .where(admin_session.c.id == c.target_session.id)
            .values(revoked_at=None)
        )
    with pytest.raises(SessionFailure) as error:
        c.service._resolve(c.target_session.session_token_hash)
    assert error.value.status == 403


# Protected principal and unrelated workspace targets cannot be revoked through the internal
# service.
def test_protected_and_wrong_scope_targets_are_denied(grants_case):
    c = grants_case
    for target, revision, status in [
        (c.recovery.id, c.recovery.authorization_revision, 403),
        (uuid4(), uuid4(), 404),
    ]:
        with pytest.raises(AdministratorFailure) as error:
            c.store.revoke(c.principal, target, revision)
        assert error.value.status == status
    assert state(c)[0]["status"] == "active" and not state(c)[2]


# A stale actor is rechecked after taking the workspace authorization lock.
def test_revoked_actor_principal_cannot_mutate(grants_case):
    c = grants_case
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == c.actor.id)
            .values(status="revoked", revoked_at=NOW, authorization_revision=uuid4())
        )
    with pytest.raises(AdministratorFailure) as error:
        c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    assert error.value.status == 403 and state(c)[0]["status"] == "active"


# A deferred COMMIT failure rolls back the grant, session revocation and required audit together.
def test_failed_commit_cannot_return_success_or_partial_state(grants_case):
    c = grants_case
    with c.engine.begin() as connection:
        connection.exec_driver_sql("""
          CREATE FUNCTION public.otm_test_reject_admin_commit() RETURNS trigger
          LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled commit failure'; END $$""")
        connection.exec_driver_sql("""CREATE CONSTRAINT TRIGGER otm_test_admin_commit AFTER UPDATE
          ON public.otm_administrator DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
          WHEN (NEW.status='revoked') EXECUTE FUNCTION public.otm_test_reject_admin_commit()""")
    try:
        with pytest.raises(AdministratorFailure) as error:
            c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
        assert error.value.status == 503
        target, session, events = state(c)
        assert target["status"] == "active" and session["revoked_at"] is None and not events
    finally:
        with c.engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER otm_test_admin_commit ON public.otm_administrator"
            )
            connection.exec_driver_sql("DROP FUNCTION public.otm_test_reject_admin_commit()")


# Failure before audit insertion also rolls back prior state and session writes.
def test_failed_audit_insert_rolls_back_mutation(grants_case):
    c = grants_case

    # Reject only this test's audit insertion before it reaches PostgreSQL.
    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO public.audit_event"):
            raise RuntimeError("controlled audit failure")

    event.listen(c.engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(AdministratorFailure) as error:
            c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
        assert error.value.status == 503
        target, session, events = state(c)
        assert target["status"] == "active" and session["revoked_at"] is None and not events
    finally:
        event.remove(c.engine, "before_cursor_execute", reject)


# The protected-row lock serializes mutual revocation; the loser observes its actor is revoked.
def test_concurrent_mutual_revocation_cannot_authorize_both(grants_case):
    c = grants_case
    gate = Barrier(2)

    # Keep real target session metadata, without inventing a browser login or token issuer.
    def revoke(principal, target, revision):
        gate.wait()
        try:
            return c.store.revoke(principal, target, revision).status
        except AdministratorFailure as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(revoke, c.principal, c.target.id, c.target.authorization_revision),
            executor.submit(
                revoke, AdminPrincipal(c.target_session), c.actor.id, c.actor.authorization_revision
            ),
        ]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(map(str, results)) == ["403", "revoked"]
    with c.engine.connect() as connection:
        assert (
            connection.execute(
                select(administrator.c.status).where(
                    administrator.c.id.in_([c.actor.id, c.target.id])
                )
            )
            .scalars()
            .all()
            .count("revoked")
            == 1
        )


# Repeated/concurrent first-seed attempts cannot create a second local principal in one workspace.
def test_unique_recovery_and_history_are_protected(grants_case):
    c = grants_case
    with pytest.raises(IntegrityError):
        with c.engine.begin() as connection:
            connection.execute(
                administrator.insert().values(
                    **grant(local=True, workspace_id=c.workspace).model_dump()
                )
            )
    with pytest.raises(DBAPIError):
        with c.engine.begin() as connection:
            connection.execute(administrator.delete().where(administrator.c.id == c.recovery.id))
    for changes in [dict(subject="new-subject"), dict(identity_kind="corporate_sso")]:
        with pytest.raises(DBAPIError):
            with c.engine.begin() as connection:
                connection.execute(
                    update(administrator)
                    .where(administrator.c.id == c.recovery.id)
                    .values(**changes)
                )


# Equivalent aware database timestamps are normalized rather than causing an auth outage.
def test_grants_work_with_non_utc_database_timezone(grants_case):
    c = grants_case
    # The connection is explicit and rollback-scoped; no pool-wide timezone mutation persists.
    with c.engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL timezone='Europe/Paris'")
        value = c.store._grant(connection, c.workspace, c.actor.issuer, c.actor.subject)
        assert value.created_at == NOW and value.created_at.utcoffset() == timedelta(0)


# Verify local credential constraints and actual API privileges, including a temporary-catalog
# decoy.
def test_api_role_cannot_bootstrap_or_reset_even_with_catalog_decoy(grants_case):
    c = grants_case
    credential = dict(
        workspace_id=c.workspace,
        administrator_id=c.recovery.id,
        password_hash="$argon2id$synthetic-nonusable-verifier",
        totp_secret_reference="test-store:immutable-version-1",
        last_totp_step=100,
        mfa_enrolled_at=NOW,
        password_changed_at=NOW,
        failed_attempts=0,
        failure_window_started_at=None,
        retry_after=None,
    )
    with c.engine.begin() as connection:
        connection.execute(local_credential.insert().values(**credential))
        connection.exec_driver_sql("CREATE ROLE otm_administrator_api_test NOLOGIN")
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO otm_administrator_api_test")
        connection.exec_driver_sql(
            "GRANT SELECT,INSERT ON public.otm_administrator TO otm_administrator_api_test"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(id,status,authorization_revision,updated_at,revoked_at) "
            "ON public.otm_administrator TO otm_administrator_api_test"
        )
        connection.exec_driver_sql(
            "GRANT SELECT ON public.otm_local_credential TO otm_administrator_api_test"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(last_totp_step,failed_attempts,failure_window_started_at,retry_after) "
            "ON public.otm_local_credential TO otm_administrator_api_test"
        )
    with c.engine.begin() as connection:
        connection.exec_driver_sql(
            "GRANT SELECT ON public.otm_admin_session TO otm_administrator_api_test"
        )
        connection.exec_driver_sql(
            "GRANT UPDATE(revoked_at) ON public.otm_admin_session TO otm_administrator_api_test"
        )
        connection.exec_driver_sql(
            "GRANT INSERT ON public.audit_event TO otm_administrator_api_test"
        )

    # Run the real revocation service under the actual restricted role, not a mocked
    # permission check.
    class RoleEngine:
        # Keep role selection transaction-local and tied to this disposable engine only.
        @contextmanager
        def begin(self):
            with c.engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL ROLE otm_administrator_api_test")
                yield connection

    restricted = SqlAdministratorStore(
        RoleEngine(),
        lambda: NOW,
        local_issuer=LOCAL,
        trusted_issuers=frozenset({LOCAL, c.actor.issuer}),
    )
    assert (
        restricted.revoke(c.principal, c.target.id, c.target.authorization_revision).status
        == "revoked"
    )

    # The same role can perform legitimate replay/throttle bookkeeping, but not replace secret
    # material.
    with c.engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE otm_administrator_api_test")
        connection.execute(
            update(local_credential)
            .where(local_credential.c.administrator_id == c.recovery.id)
            .values(last_totp_step=101)
        )
    forbidden = [
        administrator.insert().values(
            **grant(local=True, workspace_id="forbidden-" + uuid4().hex).model_dump()
        ),
        local_credential.insert().values(**{**credential, "administrator_id": c.actor.id}),
        update(local_credential)
        .where(local_credential.c.administrator_id == c.recovery.id)
        .values(password_hash="$argon2id$forbidden"),
        update(local_credential)
        .where(local_credential.c.administrator_id == c.recovery.id)
        .values(totp_secret_reference="forbidden"),
        update(administrator)
        .where(administrator.c.id == c.recovery.id)
        .values(authorization_revision=uuid4()),
    ]
    for statement in forbidden:
        with c.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL ROLE otm_administrator_api_test")
            connection.exec_driver_sql(
                "CREATE TEMP TABLE pg_class(oid oid,relowner oid) ON COMMIT DROP"
            )
            connection.exec_driver_sql(
                "INSERT INTO pg_temp.pg_class VALUES ('public.otm_administrator'::regclass,"
                "(SELECT oid FROM pg_roles WHERE rolname=current_user))"
            )
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM pg_temp.pg_class").scalar_one()
                == 1
            )
            with pytest.raises(DBAPIError) as error:
                with connection.begin_nested():
                    connection.execute(statement)
            assert error.value.orig.sqlstate in {"42501", "P0001"}
    with pytest.raises(DBAPIError):
        with c.engine.begin() as connection:
            connection.execute(
                local_credential.insert().values(**{**credential, "administrator_id": c.actor.id})
            )


# Competing first-time inserts produce exactly one protected principal, not two successful seeds.
def test_concurrent_initial_grant_seed_has_exactly_one_winner(pg_engine):
    workspace = "first-seed-" + uuid4().hex
    gate = Barrier(2)

    # Both transactions contend on the real partial unique index in an initially empty scope.
    def seed():
        row = grant(local=True, workspace_id=workspace)
        try:
            with pg_engine.begin() as connection:
                gate.wait()
                connection.execute(administrator.insert().values(**row.model_dump()))
            return "seeded"
        except IntegrityError as error:
            assert error.orig.sqlstate == "23505"
            assert error.orig.diag.constraint_name == "uq_administrator_recovery"
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: seed(), range(2)))
    assert sorted(results) == ["refused", "seeded"]
    with pg_engine.connect() as connection:
        assert (
            len(
                connection.execute(
                    select(administrator.c.id).where(administrator.c.workspace_id == workspace)
                ).all()
            )
            == 1
        )


# New foreign keys cannot attach a session or administrative history to another workspace.
def test_new_scope_foreign_keys_and_audit_kind_targets_are_enforced(grants_case):
    c = grants_case
    forged = c.session.model_dump()
    forged.update(
        id=uuid4(), workspace_id="wrong-scope", session_token_hash=uuid4().hex + uuid4().hex
    )
    with pytest.raises(IntegrityError):
        with c.engine.begin() as connection:
            connection.execute(admin_session.insert().values(**forged))
    c.store.revoke(c.principal, c.target.id, c.target.authorization_revision)
    original = dict(state(c)[2][0])
    for changes in [
        dict(workspace_id="wrong-scope"),
        dict(administrator_id=None),
        dict(kind="operation_intent"),
    ]:
        values = {**original, "id": uuid4(), **changes}
        with pytest.raises(IntegrityError):
            with c.engine.begin() as connection:
                connection.execute(audit_event.insert().values(**values))


# Reserved credential rows must meet their counter, throttle and local-owner invariants.
@pytest.mark.parametrize(
    "changes",
    [
        dict(last_totp_step=-1),
        dict(failed_attempts=-1),
        dict(failed_attempts=1),
        dict(totp_secret_reference=" "),
        dict(password_hash="not-an-argon-verifier"),
    ],
)
def test_reserved_credential_shape_rejects_invalid_states(grants_case, changes):
    c = grants_case
    values = dict(
        workspace_id=c.workspace,
        administrator_id=c.recovery.id,
        password_hash="$argon2id$synthetic-nonusable-verifier",
        totp_secret_reference="synthetic:version-1",
        last_totp_step=100,
        mfa_enrolled_at=NOW,
        password_changed_at=NOW,
        failed_attempts=0,
        failure_window_started_at=None,
        retry_after=None,
    )
    with pytest.raises(IntegrityError):
        with c.engine.begin() as connection:
            connection.execute(local_credential.insert().values(**{**values, **changes}))


# Database filtering/pagination never crosses workspaces or treats wildcard input as SQL patterns.
def test_directory_scope_search_sort_and_statistics(grants_case):
    from otm.auth.administrators import AdministratorQuery

    c = grants_case
    foreign = grant(workspace_id="foreign-" + uuid4().hex, display_name="Wildcard %_ Match")
    literal = grant(workspace_id=c.workspace, subject="literal", display_name="Wildcard %_ Match")
    with c.engine.begin() as connection:
        for row in (foreign, literal):
            connection.execute(administrator.insert().values(**row.model_dump()))
    result = c.store.directory(
        c.workspace, AdministratorQuery(query="%_", page=99, sort="email", direction="desc")
    )
    assert result.total == 1 and result.page == 1 and result.items[0].id == literal.id
    assert result.statistics.total == 4 and result.statistics.protected_recovery == 1
    assert c.store.directory(c.workspace, AdministratorQuery(query="no such name")).total == 0
    with c.engine.begin() as connection:
        for index in range(12):
            row = grant(
                workspace_id=c.workspace, subject=f"page-{index}", display_name=f"Page {index:02}"
            )
            connection.execute(administrator.insert().values(**row.model_dump()))
    result = c.store.directory(c.workspace, AdministratorQuery(query="Page", page=2))
    assert result.total == 12 and result.pages == 2 and len(result.items) == 2
    assert result.items[0].display_name == "Page 10"


# Exercise issuer dispatch and transactional revoke against persisted hashed sessions.
def test_corporate_sign_in_group_and_revocation_preserve_recovery(grants_case):
    c = grants_case
    subject = uuid4().hex
    target = EnrollmentTarget(
        environment="development",
        workspace=c.workspace,
        domain="synthetic-nonprod",
        issuer=c.actor.issuer,
        app=uuid4().hex,
        group=uuid4().hex,
    )
    corporate = grant(workspace_id=c.workspace, subject=subject)
    corporate_session = c.session.model_copy(
        update={
            "id": uuid4(),
            "session_token_hash": uuid4().hex + uuid4().hex,
            "subject": subject,
            "entitlement_reference": str(corporate.id),
            "entitlement_revision": corporate.authorization_revision,
        }
    )
    recovery_session = c.session.model_copy(
        update={
            "id": uuid4(),
            "session_token_hash": uuid4().hex + uuid4().hex,
            "issuer": LOCAL,
            "subject": c.recovery.subject,
            "entitlement_reference": str(c.recovery.id),
            "entitlement_revision": c.recovery.authorization_revision,
        }
    )
    with c.engine.begin() as connection:
        connection.execute(administrator.insert().values(**corporate.model_dump()))
        for session in (corporate_session, recovery_session):
            connection.execute(admin_session.insert().values(**session.model_dump()))
    authorities = CorporateEntitlements(c.store, LOCAL, target)
    sessions = SessionService(c.sessions, c.store, LOCAL, lambda: NOW, corporate=authorities)
    recovery = sessions._resolve(recovery_session.session_token_hash)
    assert (
        sessions._resolve(corporate_session.session_token_hash).session.id == corporate_session.id
    )
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    issuer = SqlCorporateSessions(authorities, settings.sessions, lambda: NOW)
    with pytest.raises(PermissionError):
        issuer.issue(VerifiedDomainLogin(guid=subject, group=uuid4().hex))
    c.store.revoke(recovery, corporate.id, corporate.authorization_revision)
    with pytest.raises(SessionFailure) as revoked:
        sessions._resolve(corporate_session.session_token_hash)
    assert revoked.value.status == 401
    assert sessions._resolve(recovery_session.session_token_hash).session.id == recovery_session.id

    # Re-use the corporate receipt issuer on a second independently granted synthetic identity.
    other = grant(workspace_id=c.workspace, subject=uuid4().hex)
    with c.engine.begin() as connection:
        connection.execute(administrator.insert().values(**other.model_dump()))
    issued = issuer.issue(VerifiedDomainLogin(guid=other.subject, group=target.group))
    assert sessions.authenticate(issued.handle.get_secret_value()).session.id == issued.session.id
    with c.engine.connect() as connection:
        evidence = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.workspace_id == c.workspace, audit_event.c.kind == EVENT
            )
        ).scalar_one()
    assert evidence == {
        "session_id": str(issued.session.id),
        "authorization_revision": str(other.authorization_revision),
    }


# Prove durable local revoke, exact group changes, and a stale retry fenced after regrant.
@pytest.mark.parametrize("provision", [False, True], ids=["existing-account", "new-account"])
def test_corporate_onboarding_and_failed_cleanup_regrant(grants_case, provision):
    c = grants_case
    target = EnrollmentTarget(
        environment="development",
        workspace=c.workspace,
        domain="synthetic-nonprod",
        issuer=c.actor.issuer,
        app=uuid4().hex,
        group=uuid4().hex,
    )
    account = DomainPerson(
        guid=uuid4().hex,
        domain=target.domain,
        username="pilot@example.test",
        display_name="Synthetic pilot",
        active=True,
        federated=provision,
        deleting=False,
    )
    membership = Mock(side_effect=[True, TimeoutError("synthetic"), True])
    creator = Mock(return_value=account)
    domain = Mock(return_value=[account])
    if provision:
        domain.side_effect = [(), (), (account,), (account,), (account,)]
    workflows = CorporateAdministrators(c.store, target, domain, membership, creator)
    lookup = CorporateLookup(value=account.username)
    preview = workflows.preview(c.principal, lookup)
    assert preview.work_email == account.username
    enrolled = workflows.confirm(
        c.principal,
        ConfirmAdministrator(
            value=lookup.value,
            confirmation=preview.confirmation,
            name=NewAccountName(first_name="Synthetic", last_name="Pilot") if provision else None,
        ),
    )
    authority = CorporateEntitlements(c.store, LOCAL, target)
    service = SessionService(c.sessions, c.store, LOCAL, lambda: NOW, corporate=authority)
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    issuer = SqlCorporateSessions(authority, settings.sessions, lambda: NOW)
    signed_in = issuer.issue(VerifiedDomainLogin(guid=account.guid, group=target.group))
    assert service.authenticate(signed_in.handle.get_secret_value()).session.subject == account.guid
    removal = workflows.remove(c.principal, enrolled.id, enrolled.authorization_revision)
    assert removal.group_cleanup == "pending"
    with pytest.raises(SessionFailure) as denied:
        service.authenticate(signed_in.handle.get_secret_value())
    assert denied.value.status == 401
    renamed = account.model_copy(
        update={"username": "renamed@example.test", "display_name": "Renamed pilot"}
    )
    domain.side_effect = None
    domain.return_value = [renamed]
    lookup = CorporateLookup(value=renamed.username)
    preview = workflows.preview(c.principal, lookup)
    regrant = workflows.confirm(
        c.principal, ConfirmAdministrator(value=lookup.value, confirmation=preview.confirmation)
    )
    assert regrant.id == enrolled.id
    assert (regrant.email, regrant.display_name) == (renamed.username, renamed.display_name)
    assert regrant.authorization_revision != removal.authorization_revision
    with pytest.raises(AdministratorFailure) as stale:
        workflows.cleanup(c.principal, enrolled.id, removal.authorization_revision)
    assert stale.value.code == "ADMINISTRATOR_REVISION_CHANGED"
    with pytest.raises(AdministratorFailure) as protected:
        workflows.remove(c.principal, c.recovery.id, c.recovery.authorization_revision)
    assert protected.value.code == "RECOVERY_ADMINISTRATOR_PROTECTED"
    add = membership_request(target, account.guid, add=True)
    remove = membership_request(target, account.guid, add=False)
    assert [call.args for call in membership.call_args_list] == [add, remove, add]
    with c.engine.connect() as connection:
        kinds = (
            connection.execute(
                select(audit_event.c.kind).where(audit_event.c.workspace_id == c.workspace)
            )
            .scalars()
            .all()
        )
    assert kinds.count("administrator_granted") == 1
    assert kinds.count("administrator_regranted") == 1
    with c.engine.connect() as connection:
        evidence = connection.scalar(
            select(audit_event.c.data).where(
                audit_event.c.administrator_id == enrolled.id,
                audit_event.c.kind == "administrator_regranted",
            )
        )
    assert evidence["previous_authorization_revision"] == str(removal.authorization_revision)
    assert evidence["authorization_revision"] == str(regrant.authorization_revision)
    assert kinds.count("administrator_revoked") == 1
    assert creator.call_count == int(provision)
    if provision:
        assert creator.call_args.args[0]["name"] == {
            "givenName": "Synthetic",
            "familyName": "Pilot",
        }


# Persist cleanup independently of audit and keep regrant bound to the original administrator.
def test_completed_cleanup_hides_grant_and_regrant_restores_same_identity(grants_case):
    c = grants_case
    target = EnrollmentTarget(
        environment="development",
        workspace=c.workspace,
        domain="synthetic",
        issuer=c.actor.issuer,
        app=uuid4().hex,
        group=uuid4().hex,
    )
    account = DomainPerson(
        guid=uuid4().hex,
        domain=target.domain,
        username="pilot@example.test",
        active=True,
        federated=True,
        deleting=False,
    )
    membership = Mock(side_effect=[True, False, True, True])
    workflows = CorporateAdministrators(c.store, target, Mock(return_value=[account]), membership)
    lookup = CorporateLookup(value=account.username)
    review = workflows.preview(c.principal, lookup)
    enrolled = workflows.confirm(
        c.principal, ConfirmAdministrator(value=lookup.value, confirmation=review.confirmation)
    )
    pending = workflows.remove(c.principal, enrolled.id, enrolled.authorization_revision)
    assert pending.group_cleanup == "pending"
    assert enrolled.id in [
        row.id for row in c.store.directory(c.workspace, AdministratorQuery()).items
    ]
    complete = workflows.cleanup(c.principal, enrolled.id, pending.authorization_revision)
    assert complete.group_cleanup == "complete"
    assert enrolled.id not in [
        row.id for row in c.store.directory(c.workspace, AdministratorQuery()).items
    ]
    assert (
        workflows.cleanup(c.principal, enrolled.id, pending.authorization_revision).group_cleanup
        == "complete"
    )
    assert membership.call_count == 3
    review = workflows.preview(c.principal, lookup)
    restored = workflows.confirm(
        c.principal, ConfirmAdministrator(value=lookup.value, confirmation=review.confirmation)
    )
    assert (
        restored.id == enrolled.id
        and restored.authorization_revision != pending.authorization_revision
    )
    assert enrolled.id in [
        row.id for row in c.store.directory(c.workspace, AdministratorQuery()).items
    ]
    with c.engine.connect() as connection:
        events = (
            connection.execute(
                select(audit_event.c.kind).where(audit_event.c.administrator_id == enrolled.id)
            )
            .scalars()
            .all()
        )
    assert events.count("administrator_revoked") == 1
    assert events.count("administrator_granted") == 1
    assert events.count("administrator_regranted") == 1
