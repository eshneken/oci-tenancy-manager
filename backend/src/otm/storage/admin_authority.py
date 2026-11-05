"""Same-transaction administrator checks shared by privileged command repositories."""

from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import TypeAdapter
from sqlalchemy import select

from otm.auth.service import AdminPrincipal, SessionFailure
from otm.contracts import UtcInstant
from otm.storage.sessions import session_record
from otm.storage.tables import admin_session, administrator


# Serialize administrator commands with grant revocation and check expiry after waiting for locks.
def authorize_administrator(connection, principal: AdminPrincipal, clock: Callable[[], datetime]):
    presented = principal.session
    workspace = presented.workspace_id
    # The same protected anchor serializes grant revocation/reset; no new lock table is needed.
    anchor = connection.execute(
        select(administrator.c.id)
        .where(
            administrator.c.workspace_id == workspace,
            administrator.c.identity_kind == "local_recovery",
            administrator.c.status == "active",
        )
        .with_for_update()
    ).scalar_one_or_none()
    if anchor is None:
        raise SessionFailure(403, "ADMINISTRATOR_REQUIRED")
    row = (
        connection.execute(
            select(admin_session)
            .where(
                admin_session.c.id == presented.id,
                admin_session.c.workspace_id == workspace,
                admin_session.c.session_token_hash == presented.session_token_hash,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    stored = session_record(row)
    # Read time only after both locks: a blocked command cannot reuse its pre-wait lifetime.
    at = TypeAdapter(UtcInstant).validate_python(clock())
    if (
        stored is None
        or stored.revoked_at is not None
        or stored.expires_at <= at
        or stored.last_seen_at + timedelta(seconds=stored.idle_timeout_seconds) <= at
        or not stored.auth_time <= stored.created_at <= at
        or (stored.issuer, stored.subject) != (presented.issuer, presented.subject)
    ):
        raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
    grant = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == workspace,
                administrator.c.issuer == stored.issuer,
                administrator.c.subject == stored.subject,
                administrator.c.status == "active",
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        grant is None
        or stored.entitlement_reference != str(grant["id"])
        or stored.entitlement_revision != grant["authorization_revision"]
    ):
        raise SessionFailure(403, "ADMINISTRATOR_REQUIRED")
    return grant["id"]
