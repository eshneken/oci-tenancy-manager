"""Closed delivery intent and safe status contracts without credentials or provider exceptions."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field

from otm.contracts import Contract, HttpsOrigin, Text, UtcInstant
from otm.email_policy import EmailRoute


# Header addresses are a single mailbox, never display names, lists or SMTP commands.
def mailbox(value: str) -> str:
    if (
        not value.isascii()
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or value.count("@") != 1
        or any(char in value for char in '<>,;:"\\()[]')
        or not all(value.split("@"))
    ):
        raise ValueError("INVALID_EMAIL_ADDRESS")
    return value


Mailbox = Annotated[Text, AfterValidator(mailbox)]
DeliveryState = Literal["pending", "blocked", "sending", "sent", "failed", "unknown", "superseded"]


# Freeze the responsible recipient and deployment route; a retry never adopts changed routing.
class NotificationIntent(Contract):
    contract_version: Literal["lifecycle-email-1"] = "lifecycle-email-1"
    operation_id: UUID
    operation_revision: Annotated[int, Field(ge=1)]
    intent_event_id: UUID
    intent_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    responsible_subject: Text
    administrator_id: UUID
    authorization_revision: UUID
    original_recipient: Mailbox | None
    delivery_recipient: Mailbox | None
    route: EmailRoute
    application_origin: HttpsOrigin | None = None
    delivery_profile_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    event: Literal["action_required", "terminal_failure"]
    operation_state: Literal["waiting", "needs_attention", "failed"]
    stage: Text
    wait_reason: Text | None = None
    safe_code: Text | None = None
    created_at: UtcInstant


# Exhausted cost acquisitions retain administrator recipients independently of D50 takeover.
class CostFailureNotice(Contract):
    contract_version: Literal["cost-failure-email-1"] = "cost-failure-email-1"
    operation_id: UUID
    collection_id: UUID
    tenancy_id: UUID
    source_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    failure_scope_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    administrator_id: UUID
    authorization_revision: UUID
    original_recipient: Mailbox | None
    delivery_recipient: Mailbox | None
    route: EmailRoute
    application_origin: HttpsOrigin | None = None
    delivery_profile_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    event: Literal["cost_read_failed"] = "cost_read_failed"
    created_at: UtcInstant


# The SMTP capability receives one bounded plain-text message; no HTML, attachments or custom
# headers.
class Envelope(Contract):
    notification_id: UUID
    recipient: Mailbox
    subject: Annotated[str, Field(min_length=1, max_length=160)]
    body: Annotated[str, Field(min_length=1, max_length=4096)]


# Transport results state what is known about remote acceptance, never expose raw server text.
class DeliveryResult(Contract):
    state: Literal["accepted", "rejected", "uncertain"]
    safe_code: Literal["SMTP_ACCEPTED", "SMTP_REJECTED", "SMTP_UNAVAILABLE", "SMTP_OUTCOME_UNKNOWN"]


# Operations can inspect delivery metadata without exposing message content or credentials.
class NotificationSummary(Contract):
    id: UUID
    state: DeliveryState
    event: Literal["action_required", "terminal_failure", "cost_read_failed"]
    recipient: Mailbox | None
    original_recipient: Mailbox | None
    created_at: UtcInstant
    updated_at: UtcInstant
    redirected: bool
    last_attempt_at: UtcInstant | None = None
    attempts: Annotated[int, Field(ge=0, le=3)]
    safe_code: Text | None = None


# Append-only state evidence identifies a frozen intent without copying mailbox or message data.
class NotificationEvidence(Contract):
    contract_version: Literal["email-delivery-1"] = "email-delivery-1"
    notification_id: UUID
    intent_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    state: DeliveryState
    attempts: Annotated[int, Field(ge=0, le=3)]
    safe_code: Text | None = None
