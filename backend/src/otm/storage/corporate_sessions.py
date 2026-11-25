"""Commit a corporate session and its closed audit receipt after signed group verification."""

import hashlib
import secrets
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import select

from otm.auth.contracts import AdminSession, DisplaySnapshot
from otm.auth.corporate_entitlements import CorporateEntitlements
from otm.auth.corporate_oidc import VerifiedDomainLogin
from otm.auth.local import IssuedSession
from otm.contracts import UtcInstant
from otm.operations.contracts import ActorIdentity, canonical_hash
from otm.settings import session_lifetime
from otm.storage.tables import admin_session, administrator, audit_event

EVENT = "corporate_sign_in_succeeded"
VERSION = "corporate-sign-in-1"


# Use the same SQL grant store for the current Atlas grant precheck and locked issuance recheck.
class SqlCorporateSessions:
    # Keep the database and the existing installation session policy explicit.
    def __init__(self, authority: CorporateEntitlements, sessions, clock):
        self.authority, self.sessions, self.clock = authority, sessions, clock

    # Serialize with grant changes and release the handle only after the audit commit.
    def issue(self, verified: VerifiedDomainLogin) -> IssuedSession:
        target = self.authority.target
        proof = VerifiedDomainLogin.model_validate(verified)
        if proof.group != target.group:
            raise PermissionError("CORPORATE_SESSION_NOT_AUTHORIZED")
        subject = proof.guid
        entitlement = self.authority.require_admin(target.issuer, subject, target.workspace)
        store = self.authority.grants
        with store.engine.begin() as connection:
            anchor = connection.execute(
                select(administrator.c.id)
                .where(
                    administrator.c.workspace_id == target.workspace,
                    administrator.c.issuer == self.authority.local_issuer,
                    administrator.c.identity_kind == "local_recovery",
                    administrator.c.status == "active",
                )
                .with_for_update()
            ).scalar_one_or_none()
            if anchor is None:
                raise PermissionError("CORPORATE_SESSION_NOT_AUTHORIZED")
            grant = store._grant(connection, target.workspace, target.issuer, subject)
            at = TypeAdapter(UtcInstant).validate_python(self.clock())
            if (
                entitlement.reference != str(grant.id)
                or entitlement.revision != grant.authorization_revision
                or not entitlement.checked_at <= at < entitlement.valid_until
            ):
                raise PermissionError("CORPORATE_SESSION_NOT_AUTHORIZED")
            handle = secrets.token_urlsafe(32)
            lifetime = session_lifetime(at, self.sessions)
            session = AdminSession(
                id=uuid4(),
                workspace_id=target.workspace,
                issuer=grant.issuer,
                subject=subject,
                session_token_hash=hashlib.sha256(handle.encode()).hexdigest(),
                display_snapshot=DisplaySnapshot(display_name=grant.display_name),
                entitlement_reference=str(grant.id),
                entitlement_revision=grant.authorization_revision,
                entitlement_checked_at=entitlement.checked_at,
                auth_time=at,
                created_at=at,
                expires_at=lifetime.expires_at,
                idle_timeout_seconds=lifetime.idle_timeout_seconds,
                last_seen_at=at,
                revoked_at=None,
                provider_session_reference_hash=None,
            )
            actor = ActorIdentity(
                issuer=grant.issuer, subject=subject, display_name=grant.display_name
            )
            evidence = {
                "session_id": str(session.id),
                "authorization_revision": str(grant.authorization_revision),
            }
            connection.execute(admin_session.insert().values(**session.model_dump()))
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=target.workspace,
                    administrator_id=grant.id,
                    operation_id=None,
                    intent_revision=None,
                    actor=actor.key,
                    actor_subject=actor.key,
                    actor_snapshot=actor.model_dump(mode="json"),
                    kind=EVENT,
                    at=at,
                    contract_version=VERSION,
                    data=evidence,
                    data_hash=canonical_hash(evidence),
                )
            )
        return IssuedSession(handle=handle, session=session)
