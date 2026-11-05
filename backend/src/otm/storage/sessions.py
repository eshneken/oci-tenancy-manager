"""Opaque-session metadata lookup/revocation; no login, issuance or raw token storage."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import delete, func, literal, or_, select, update
from sqlalchemy.engine import Engine

from otm.auth.contracts import AdminSession
from otm.contracts import UtcInstant
from otm.operations.contracts import ActorIdentity
from otm.storage.security_events import security_event
from otm.storage.tables import admin_session, administrator
from otm.storage.transaction import require_transaction


# Normalize closed row metadata without interpreting absence as an active session.
def session_record(row) -> AdminSession | None:
    if row is None:
        return None
    values = dict(row)
    for name in (
        "entitlement_checked_at",
        "auth_time",
        "created_at",
        "expires_at",
        "last_seen_at",
        "revoked_at",
    ):
        if values[name] is not None:
            values[name] = values[name].astimezone(UTC).isoformat()
    values["id"], values["entitlement_revision"] = (
        str(values["id"]),
        str(values["entitlement_revision"]),
    )
    return AdminSession.model_validate_json(json.dumps(values))


# Use the same pinned-row deadlines for activity and housekeeping, including equality at expiry.
def invalid_session(at: datetime):
    return or_(
        admin_session.c.revoked_at.is_not(None),
        admin_session.c.expires_at <= at,
        admin_session.c.last_seen_at
        + admin_session.c.idle_timeout_seconds * literal(timedelta(seconds=1))
        <= at,
    )


# Use exact hashed handles and scoped parameters; never create a login shortcut.
class SqlSessionRepository:
    # Inject the engine without saved URLs or provider clients.
    def __init__(self, engine: Engine):
        self.engine = engine

    # Return closed metadata; the session boundary sanitizes database errors.
    def find(self, token_hash: str) -> AdminSession | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(admin_session).where(admin_session.c.session_token_hash == token_hash)
                )
                .mappings()
                .one_or_none()
            )
        return session_record(row)

    # Set the first revocation timestamp only for the matching workspace/id/handle digest.
    def revoke(self, session_id: UUID, token_hash: str, workspace_id: str, at: datetime) -> None:
        at = TypeAdapter(UtcInstant).validate_python(at)
        with self.engine.begin() as connection:
            require_transaction(connection)
            row = (
                connection.execute(
                    update(admin_session)
                    .where(
                        admin_session.c.id == session_id,
                        admin_session.c.workspace_id == workspace_id,
                        admin_session.c.session_token_hash == token_hash,
                        admin_session.c.revoked_at.is_(None),
                    )
                    .values(revoked_at=at)
                    .returning(admin_session)
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                stored = session_record(row)
                grant_id = connection.execute(
                    select(administrator.c.id).where(
                        administrator.c.workspace_id == workspace_id,
                        administrator.c.issuer == stored.issuer,
                        administrator.c.subject == stored.subject,
                    )
                ).scalar_one()
                security_event(
                    connection,
                    workspace=workspace_id,
                    kind="session_logged_out",
                    grant_id=grant_id,
                    actor=ActorIdentity(
                        issuer=stored.issuer,
                        subject=stored.subject,
                        display_name=stored.display_snapshot.display_name,
                    ),
                    at=at,
                    session_id=stored.id,
                    revision=stored.entitlement_revision,
                )

    # Refresh only a still-live exact session after current entitlement has been checked.
    def touch(self, session: AdminSession, at: datetime) -> AdminSession | None:
        at = TypeAdapter(UtcInstant).validate_python(at)
        with self.engine.begin() as connection:
            require_transaction(connection)
            row = (
                connection.execute(
                    update(admin_session)
                    .where(
                        admin_session.c.id == session.id,
                        admin_session.c.workspace_id == session.workspace_id,
                        admin_session.c.session_token_hash == session.session_token_hash,
                        admin_session.c.issuer == session.issuer,
                        admin_session.c.subject == session.subject,
                        admin_session.c.entitlement_revision == session.entitlement_revision,
                        ~invalid_session(at),
                    )
                    .values(last_seen_at=func.greatest(admin_session.c.last_seen_at, at))
                    .returning(admin_session)
                )
                .mappings()
                .one_or_none()
            )
        return session_record(row)

    # Delete only invalid session rows, with bounded locking and no administrator/audit mutation.
    def purge_expired(self, at: datetime, limit: int) -> int:
        at = TypeAdapter(UtcInstant).validate_python(at)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10_000:
            raise ValueError("INVALID_SESSION_CLEANUP_LIMIT")
        with self.engine.begin() as connection:
            require_transaction(connection)
            candidates = (
                select(admin_session.c.id)
                .where(invalid_session(at))
                .order_by(admin_session.c.expires_at, admin_session.c.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .cte("expired_sessions")
            )
            result = connection.execute(
                delete(admin_session)
                .where(admin_session.c.id.in_(select(candidates.c.id)), invalid_session(at))
                .returning(admin_session.c.id)
            )
            return len(result.all())
