"""Closed delivery intent and safe status contracts without credentials or provider exceptions."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, model_validator

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


# Frozen role provenance is rechecked at submission; a role change never silently retargets email.
class RecipientReason(Contract):
    role: Literal["owner", "manager", "designee", "administrator"]
    person_id: UUID | None = None
    administrator_id: UUID | None = None
    authorization_revision: UUID | None = None

    # Employee roles and administrator grants use distinct, noninterchangeable authority references.
    @model_validator(mode="after")
    def scoped_reason(self):
        if self.role == "administrator":
            if self.person_id is not None or (
                (self.administrator_id is None) != (self.authorization_revision is None)
            ):
                raise ValueError("NOTIFICATION_REASON_INVALID")
        elif (
            self.person_id is None
            or self.administrator_id is not None
            or self.authorization_revision is not None
        ):
            raise ValueError("NOTIFICATION_REASON_INVALID")
        return self


# A missing-user incident names one exact checked subject and one deduplicated original recipient.
class RequiredUserMissingNotice(Contract):
    contract_version: Literal["required-user-missing-email-1"] = "required-user-missing-email-1"
    operation_id: UUID
    tenancy_id: UUID
    purpose: Literal["automation", "recovery"]
    scope_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    episode_id: UUID
    check_context_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    organization_version_id: UUID
    configuration_id: UUID
    reasons: Annotated[tuple[RecipientReason, ...], Field(min_length=1, max_length=1024)]
    routing_issues: tuple[
        Literal[
            "owner_unavailable",
            "manager_unavailable",
            "designee_unavailable",
            "administrator_unavailable",
        ],
        ...,
    ] = ()
    original_recipient: Mailbox | None
    delivery_recipient: Mailbox | None
    route: EmailRoute
    application_origin: HttpsOrigin | None = None
    delivery_profile_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    event: Literal["required_user_missing"] = "required_user_missing"
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
    event: Literal[
        "action_required",
        "terminal_failure",
        "cost_read_failed",
        "required_user_missing",
        "recovery_password_requested",
        "recovery_password_rotation_failed",
    ]
    recipient: Mailbox | None
    original_recipient: Mailbox | None
    created_at: UtcInstant
    updated_at: UtcInstant
    redirected: bool
    last_attempt_at: UtcInstant | None = None
    attempts: Annotated[int, Field(ge=0, le=3)]
    safe_code: Text | None = None
    required_user_purpose: Literal["automation", "recovery"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    recipient_roles: tuple[Literal["owner", "manager", "designee", "administrator"], ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    routing_issues: tuple[
        Literal[
            "owner_unavailable",
            "manager_unavailable",
            "designee_unavailable",
            "administrator_unavailable",
        ],
        ...,
    ] = Field(default=(), exclude_if=lambda value: not value)


# Append-only state evidence identifies a frozen intent without copying mailbox or message data.
class NotificationEvidence(Contract):
    contract_version: Literal["email-delivery-1"] = "email-delivery-1"
    notification_id: UUID
    intent_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    state: DeliveryState
    attempts: Annotated[int, Field(ge=0, le=3)]
    safe_code: Text | None = None


# Password notices describe an authorized attempt or failure, never contain the secret itself.
class RecoveryPasswordNotice(Contract):
    contract_version: Literal["recovery-password-email-1"] = "recovery-password-email-1"
    operation_id: UUID
    tenancy_id: UUID
    credential_id: UUID
    grant_id: UUID | None
    requester_subject: Text
    organization_version_id: UUID
    configuration_id: UUID
    reasons: Annotated[tuple[RecipientReason, ...], Field(max_length=1024)]
    routing_issues: tuple[
        Literal["owner_unavailable", "manager_unavailable", "administrator_unavailable"], ...
    ] = ()
    original_recipient: Mailbox | None
    delivery_recipient: Mailbox | None
    route: EmailRoute
    application_origin: HttpsOrigin | None
    delivery_profile_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    event: Literal["recovery_password_requested", "recovery_password_rotation_failed"]
    first_disclosure_at: UtcInstant | None
    rotation_due_at: UtcInstant | None
    created_at: UtcInstant

    # No designee recipient or empty invented delivery target can become an authorized notice.
    @model_validator(mode="after")
    def recovery_roles(self):
        if (
            any(reason.role == "designee" for reason in self.reasons)
            or not self.reasons
            and not self.routing_issues
            or self.event == "recovery_password_requested"
            and (
                self.grant_id is None
                or self.first_disclosure_at is None
                or self.rotation_due_at is None
            )
        ):
            raise ValueError("RECOVERY_PASSWORD_NOTICE_INVALID")
        return self
