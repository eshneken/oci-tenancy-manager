"""Local operator enrollment and replay-safe login transactions; no corporate identity calls."""

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from otm.auth.contracts import AdminSession, DisplaySnapshot
from otm.auth.local import IssuedSession, LocalAuthFailure, totp_step
from otm.auth.service import HANDLE
from otm.contracts import UtcInstant
from otm.operations.contracts import ActorIdentity
from otm.settings import ApplicationSettings, session_lifetime
from otm.storage.administrators import administrator_record
from otm.storage.security_events import security_event
from otm.storage.tables import admin_session, administrator, local_credential
from otm.storage.transaction import require_transaction


# Keep every local authority/factor/session transition inside explicit, short database transactions.
class SqlLocalAuth:
    # Require explicit configuration and engine; neither construction nor lookup creates an account.
    def __init__(
        self, engine: Engine, settings: ApplicationSettings, clock: Callable[[], datetime]
    ):
        settings = ApplicationSettings.model_validate(settings)
        if settings.local_auth is None:
            raise ValueError("LOCAL_AUTH_CONFIGURATION_REQUIRED")
        self.engine, self.settings, self.policy, self.clock = (
            engine,
            settings,
            settings.local_auth,
            clock,
        )

    # Verify the actual current DB role can operate on protected identities; labels are not
    # authority.
    def operator_status(self, *, reset=False):
        with self.engine.connect() as connection:
            allowed, role = connection.exec_driver_sql("""SELECT
                pg_catalog.pg_has_role(current_user,pg_catalog.pg_get_userbyid(relowner),'MEMBER'),
                session_user FROM pg_catalog.pg_class
                WHERE oid='public.otm_administrator'::pg_catalog.regclass""").one()
            if not allowed:
                raise LocalAuthFailure(403, "OPERATOR_PRIVILEGES_REQUIRED")
            row = (
                connection.execute(
                    select(administrator).where(
                        administrator.c.workspace_id == self.policy.workspace_id,
                        administrator.c.identity_kind == "local_recovery",
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is not None and not reset:
            raise LocalAuthFailure(409, "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED")
        if reset and row is None:
            raise LocalAuthFailure(400, "INVALID_LOCAL_CREDENTIALS")
        if reset and row["issuer"] != self.policy.issuer:
            raise LocalAuthFailure(409, "LOCAL_CREDENTIALS_CHANGED")
        return (administrator_record(row) if row else None), ActorIdentity(
            issuer="urn:otm:database-operator", subject=role
        )

    # Establish/reset only verified MFA material; a failed/uncertain COMMIT never authorizes
    # seed deletion.
    def enroll(
        self, verifier: str, reference: str, step: int, operator: ActorIdentity, expected=None
    ):
        at = TypeAdapter(UtcInstant).validate_python(self.clock())
        identifier = expected.id if expected is not None else uuid4()
        revision = uuid4()
        with self.engine.begin() as connection:
            require_transaction(connection)
            # Recheck role and immutable existing identity under this transaction, not
            # only before prompts.
            allowed, role = connection.exec_driver_sql("""SELECT
                pg_catalog.pg_has_role(current_user,pg_catalog.pg_get_userbyid(relowner),'MEMBER'),
                session_user FROM pg_catalog.pg_class
                WHERE oid='public.otm_administrator'::pg_catalog.regclass""").one()
            if not allowed or operator != ActorIdentity(
                issuer="urn:otm:database-operator", subject=role
            ):
                raise LocalAuthFailure(403, "OPERATOR_PRIVILEGES_REQUIRED")
            row = (
                connection.execute(
                    select(administrator)
                    .where(
                        administrator.c.workspace_id == self.policy.workspace_id,
                        administrator.c.identity_kind == "local_recovery",
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if expected is None:
                if row is not None:
                    raise LocalAuthFailure(409, "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED")
                connection.execute(
                    administrator.insert().values(
                        id=identifier,
                        workspace_id=self.policy.workspace_id,
                        identity_kind="local_recovery",
                        issuer=self.policy.issuer,
                        subject=str(identifier),
                        display_name="Recovery administrator",
                        email=None,
                        status="active",
                        authorization_revision=revision,
                        created_at=at,
                        updated_at=at,
                        revoked_at=None,
                    )
                )
            else:
                if (
                    row is None
                    or row["id"] != identifier
                    or row["authorization_revision"] != expected.authorization_revision
                    or row["issuer"] != self.policy.issuer
                ):
                    raise LocalAuthFailure(409, "LOCAL_CREDENTIALS_CHANGED")
                connection.execute(
                    update(administrator)
                    .where(administrator.c.id == identifier)
                    .values(
                        authorization_revision=revision,
                        updated_at=at,
                    )
                )
                connection.execute(
                    update(admin_session)
                    .where(
                        admin_session.c.workspace_id == self.policy.workspace_id,
                        admin_session.c.issuer == self.policy.issuer,
                        admin_session.c.subject == str(identifier),
                        admin_session.c.revoked_at.is_(None),
                    )
                    .values(revoked_at=at)
                )
            fields = dict(
                workspace_id=self.policy.workspace_id,
                administrator_id=identifier,
                password_hash=verifier,
                totp_secret_reference=reference,
                last_totp_step=step,
                mfa_enrolled_at=at,
                password_changed_at=at,
                failed_attempts=0,
                failure_window_started_at=None,
                retry_after=None,
            )
            if expected is None:
                connection.execute(local_credential.insert().values(**fields))
            else:
                changed = connection.execute(
                    update(local_credential)
                    .where(
                        local_credential.c.workspace_id == self.policy.workspace_id,
                        local_credential.c.administrator_id == identifier,
                    )
                    .values(**fields)
                )
                if changed.rowcount != 1:
                    raise LocalAuthFailure(409, "LOCAL_CREDENTIALS_CHANGED")
            security_event(
                connection,
                workspace=self.policy.workspace_id,
                kind="local_credentials_reset" if expected else "administrator_bootstrapped",
                grant_id=identifier,
                actor=operator,
                at=at,
                revision=revision,
            )
        return identifier

    # Release the read connection before expensive hashing and external secret retrieval.
    def material(self):
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(administrator).where(
                        administrator.c.workspace_id == self.policy.workspace_id,
                        administrator.c.issuer == self.policy.issuer,
                        administrator.c.identity_kind == "local_recovery",
                        administrator.c.status == "active",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            grant = administrator_record(row)
            credential = (
                connection.execute(
                    select(local_credential).where(
                        local_credential.c.workspace_id == self.policy.workspace_id,
                        local_credential.c.administrator_id == grant.id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if credential is None:
                raise ValueError("LOCAL_CREDENTIAL_UNAVAILABLE")
            return grant, dict(credential)

    # Recheck all mutable proof dependencies and consume a code only with committed session/audit.
    def finish(self, material, password_ok, seed, code, old_handle):
        before, proof = material
        result = None
        with self.engine.begin() as connection:
            require_transaction(connection)
            row = (
                connection.execute(
                    select(administrator)
                    .where(
                        administrator.c.workspace_id == self.policy.workspace_id,
                        administrator.c.id == before.id,
                        administrator.c.identity_kind == "local_recovery",
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            grant = administrator_record(row) if row else None
            current = (
                connection.execute(
                    select(local_credential)
                    .where(
                        local_credential.c.workspace_id == self.policy.workspace_id,
                        local_credential.c.administrator_id == before.id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if (
                grant is None
                or current is None
                or grant.status != "active"
                or grant.issuer != self.policy.issuer
                or grant.authorization_revision != before.authorization_revision
                or current["password_hash"] != proof["password_hash"]
                or current["totp_secret_reference"] != proof["totp_secret_reference"]
            ):
                raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED")
            at = TypeAdapter(UtcInstant).validate_python(self.clock())
            cooling = current["retry_after"] is not None and at < current["retry_after"]
            step = (
                totp_step(seed, code, at, current["last_totp_step"])
                if password_ok and not cooling
                else None
            )
            if step is None:
                if not cooling:
                    start = current["failure_window_started_at"]
                    restart = (
                        start is None
                        or at >= start + timedelta(seconds=self.policy.failure_window_seconds)
                        or current["retry_after"] is not None
                    )
                    count = 1 if restart else current["failed_attempts"] + 1
                    start = at if restart else start
                    due = (
                        at + timedelta(seconds=self.policy.cooldown_seconds)
                        if count >= self.policy.max_failures
                        else None
                    )
                    connection.execute(
                        update(local_credential)
                        .where(
                            local_credential.c.workspace_id == self.policy.workspace_id,
                            local_credential.c.administrator_id == grant.id,
                        )
                        .values(
                            failed_attempts=count, failure_window_started_at=start, retry_after=due
                        )
                    )
                    if count == 1 or due is not None:
                        security_event(
                            connection,
                            workspace=self.policy.workspace_id,
                            kind="local_sign_in_failed",
                            grant_id=grant.id,
                            actor=ActorIdentity(
                                issuer="urn:otm:anonymous", subject="unauthenticated"
                            ),
                            at=at,
                        )
            else:
                connection.execute(
                    update(local_credential)
                    .where(
                        local_credential.c.workspace_id == self.policy.workspace_id,
                        local_credential.c.administrator_id == grant.id,
                    )
                    .values(
                        last_totp_step=step,
                        failed_attempts=0,
                        failure_window_started_at=None,
                        retry_after=None,
                    )
                )
                handle = secrets.token_urlsafe(32)
                lifetime = session_lifetime(at, self.settings.sessions)
                session = AdminSession(
                    id=uuid4(),
                    workspace_id=self.policy.workspace_id,
                    session_token_hash=hashlib.sha256(handle.encode()).hexdigest(),
                    issuer=grant.issuer,
                    subject=grant.subject,
                    display_snapshot=DisplaySnapshot(display_name=grant.display_name),
                    entitlement_reference=str(grant.id),
                    entitlement_revision=grant.authorization_revision,
                    entitlement_checked_at=at,
                    auth_time=at,
                    created_at=at,
                    expires_at=lifetime.expires_at,
                    idle_timeout_seconds=lifetime.idle_timeout_seconds,
                    last_seen_at=at,
                    revoked_at=None,
                    provider_session_reference_hash=None,
                )
                if isinstance(old_handle, str) and HANDLE.fullmatch(old_handle):
                    connection.execute(
                        update(admin_session)
                        .where(
                            admin_session.c.workspace_id == self.policy.workspace_id,
                            admin_session.c.issuer == grant.issuer,
                            admin_session.c.subject == grant.subject,
                            admin_session.c.session_token_hash
                            == hashlib.sha256(old_handle.encode()).hexdigest(),
                            admin_session.c.revoked_at.is_(None),
                        )
                        .values(revoked_at=at)
                    )
                connection.execute(admin_session.insert().values(**session.model_dump()))
                security_event(
                    connection,
                    workspace=self.policy.workspace_id,
                    kind="local_sign_in_succeeded",
                    grant_id=grant.id,
                    actor=ActorIdentity(
                        issuer=grant.issuer, subject=grant.subject, display_name=grant.display_name
                    ),
                    at=at,
                    session_id=session.id,
                    revision=grant.authorization_revision,
                )
                result = IssuedSession(handle=handle, session=session)
        if result is None:
            raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED")
        return result
