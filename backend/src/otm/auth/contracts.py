"""Allowlisted session metadata and fresh entitlement decisions, excluding all bearer tokens."""

from uuid import UUID

from pydantic import Field

from otm.contracts import Contract, Text, UtcInstant
from otm.settings import PositiveSeconds


# Retain only the optional nonsecret administrator display name, never raw SSO claims.
class DisplaySnapshot(Contract):
    display_name: Text | None = None


# Stored session metadata does not itself grant administrator access.
class AdminSession(Contract):
    id: UUID
    workspace_id: Text
    session_token_hash: Text = Field(repr=False)
    issuer: Text
    subject: Text
    display_snapshot: DisplaySnapshot
    entitlement_reference: Text
    entitlement_revision: UUID
    entitlement_checked_at: UtcInstant
    auth_time: UtcInstant
    created_at: UtcInstant
    expires_at: UtcInstant
    idle_timeout_seconds: PositiveSeconds
    last_seen_at: UtcInstant
    revoked_at: UtcInstant | None
    provider_session_reference_hash: Text | None = Field(repr=False)


# A freshly resolved exact-subject/workspace grant, not an old session/group claim.
class AdminEntitlement(Contract):
    workspace_id: Text
    issuer: Text
    subject: Text
    reference: Text
    revision: UUID
    checked_at: UtcInstant
    valid_until: UtcInstant


# Return the minimum current session context needed by a future administration UI.
class SessionView(Contract):
    workspace_id: Text
    display_name: Text | None
    expires_at: UtcInstant
