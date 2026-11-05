"""Validate opaque sessions and current authority; do not implement an SSO protocol."""

import hashlib
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from pydantic import TypeAdapter
from starlette.authentication import BaseUser

from otm.auth.contracts import AdminEntitlement, AdminSession
from otm.contracts import UtcInstant
from otm.operations.contracts import ActorIdentity

HANDLE = re.compile(r"[A-Za-z0-9_-]{43}\Z")


# Carry only a fixed public diagnostic; never attach tokens, raw claims or provider errors.
class SessionFailure(Exception):
    # Separate unavailable verification from missing authentication without private detail.
    def __init__(self, status: int, code: str):
        if (status, code) not in {
            (401, "AUTHENTICATION_REQUIRED"),
            (403, "ADMINISTRATOR_REQUIRED"),
            (503, "AUTHENTICATION_UNAVAILABLE"),
        }:
            raise ValueError("INVALID_AUTHENTICATION_DIAGNOSTIC") from None
        super().__init__(code)
        self.status, self.code = status, code


# Look up hashes only; issuance belongs to the eventual maintained SSO flow.
class SessionRepository(Protocol):
    # Read the unique server-side session, without returning or accepting bearer material.
    def find(self, token_hash: str) -> AdminSession | None: ...

    # Atomically refresh qualified activity only while the exact session remains live.
    def touch(self, session: AdminSession, at: datetime) -> AdminSession | None: ...

    # Revoke only the exact session scope, idempotently retaining its first revocation time.
    def revoke(
        self, session_id: UUID, token_hash: str, workspace_id: str, at: datetime
    ) -> None: ...


# A concrete authority resolves current OTM grants; corporate identity qualification is separate.
class EntitlementAuthority(Protocol):
    # Reject disabled/unauthorized subjects; fail unavailable if verification fails.
    def require_admin(self, issuer: str, subject: str, workspace_id: str) -> AdminEntitlement: ...


# Internal validated request principal, not a model accepted from JSON or identity headers.
class AdminPrincipal(BaseUser):
    # Retain nonsecret validated metadata for rechecking at a later command boundary.
    def __init__(self, session: AdminSession):
        self.session = session

    # Starlette uses this only after the session service has authenticated the request.
    @property
    def is_authenticated(self) -> bool:
        return True

    # Provide display text without inferring identity from an employee name or email.
    @property
    def display_name(self) -> str:
        return self.session.display_snapshot.display_name or "Administrator"

    # Keep issuer and subject distinct from organization/person identity.
    @property
    def identity(self) -> str:
        return self.actor.key

    # Project only the allowlisted actor snapshot used by operation admission.
    @property
    def actor(self) -> ActorIdentity:
        return ActorIdentity(
            issuer=self.session.issuer,
            subject=self.session.subject,
            display_name=self.session.display_snapshot.display_name,
        )


# Require explicit storage, trusted issuer and current entitlement; no default access.
class SessionService:
    # Compose verification independently of cookies, provider callbacks or network defaults.
    def __init__(
        self,
        repository: SessionRepository,
        entitlements: EntitlementAuthority,
        trusted_issuer: str,
        clock: Callable[[], datetime],
    ):
        self.repository, self.entitlements = repository, entitlements
        self.trusted_issuer, self.clock = trusted_issuer, clock

    # Hash a bounded opaque handle; do not retain it in principal, database or diagnostics.
    def authenticate(self, handle: str) -> AdminPrincipal:
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
        return self._resolve(hashlib.sha256(handle.encode()).hexdigest())

    # Revalidate expiry/revocation and current exact-scope entitlement on every call.
    def _resolve(self, token_hash: str) -> AdminPrincipal:
        try:
            stored = self.repository.find(token_hash)
            if stored is None:
                raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
            session = AdminSession.model_validate(stored)
            now = TypeAdapter(UtcInstant).validate_python(self.clock())
            if (
                session.session_token_hash != token_hash
                or session.issuer != self.trusted_issuer
                or session.revoked_at is not None
                or now >= session.last_seen_at + timedelta(seconds=session.idle_timeout_seconds)
                or not session.auth_time <= session.created_at <= now < session.expires_at
            ):
                raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
            try:
                grant = AdminEntitlement.model_validate(
                    self.entitlements.require_admin(
                        session.issuer, session.subject, session.workspace_id
                    )
                )
            except PermissionError:
                raise SessionFailure(403, "ADMINISTRATOR_REQUIRED") from None
            # Check time again after external verification. A slow entitlement call cannot
            # extend an expired session or silently authorize another issuer/subject/workspace.
            now = TypeAdapter(UtcInstant).validate_python(self.clock())
            if now >= session.expires_at or now >= session.last_seen_at + timedelta(
                seconds=session.idle_timeout_seconds
            ):
                raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
            if (
                grant.workspace_id != session.workspace_id
                or grant.issuer != session.issuer
                or grant.subject != session.subject
                or grant.reference != session.entitlement_reference
                or grant.revision != session.entitlement_revision
                or not grant.checked_at <= now < grant.valid_until
            ):
                raise SessionFailure(403, "ADMINISTRATOR_REQUIRED")
            return AdminPrincipal(session)
        except SessionFailure:
            raise
        except Exception:
            raise SessionFailure(503, "AUTHENTICATION_UNAVAILABLE") from None

    # Recheck session authority for admission; deny stale or cross-workspace principals.
    def require_admin(self, principal: object, workspace_id: str) -> ActorIdentity:
        if not isinstance(principal, AdminPrincipal):
            raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
        refreshed = self._resolve(principal.session.session_token_hash)
        if (
            refreshed.session.id != principal.session.id
            or refreshed.actor.key != principal.actor.key
            or refreshed.session.workspace_id != workspace_id
        ):
            raise SessionFailure(403, "ADMINISTRATOR_REQUIRED")
        return refreshed.actor

    # Refresh explicitly asserted activity; read-only polling never calls this method.
    def activity(self, principal: object) -> AdminPrincipal:
        self.require_admin(
            principal,
            principal.session.workspace_id if isinstance(principal, AdminPrincipal) else "",
        )
        try:
            updated = self.repository.touch(
                principal.session, TypeAdapter(UtcInstant).validate_python(self.clock())
            )
            if updated is None:
                raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
            return AdminPrincipal(AdminSession.model_validate(updated))
        except SessionFailure:
            raise
        except Exception:
            raise SessionFailure(503, "AUTHENTICATION_UNAVAILABLE") from None

    # Revoke the presented handle even when SSO/entitlement is unavailable; no privilege is granted.
    def logout(self, handle: str | None) -> None:
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            return
        try:
            digest = hashlib.sha256(handle.encode()).hexdigest()
            stored = self.repository.find(digest)
            if stored is not None:
                session = AdminSession.model_validate(stored)
                if session.session_token_hash != digest:
                    raise ValueError("SESSION_HANDLE_MISMATCH")
                self.repository.revoke(
                    session.id,
                    digest,
                    session.workspace_id,
                    TypeAdapter(UtcInstant).validate_python(self.clock()),
                )
        except Exception:
            raise SessionFailure(503, "AUTHENTICATION_UNAVAILABLE") from None
