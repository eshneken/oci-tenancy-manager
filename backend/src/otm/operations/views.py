"""Closed read models for the durable operation directory; never expose raw intent/provider JSON."""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.notifications.contracts import NotificationSummary
from otm.operations.contracts import OperationState
from otm.providers.inspection_contracts import TenancyOcid
from otm.tenancies.automation_keys import AutomationKeysView


# Bound all directory controls before SQL construction; workspace comes only from the session.
class OperationQuery(Contract):
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50, 100] = 10
    sort: Literal["accepted_at", "updated_at", "state", "stage"] = "accepted_at"
    direction: Literal["asc", "desc"] = "desc"
    state: Literal[
        "", "queued", "running", "waiting", "needs_attention", "succeeded", "cancelled", "failed"
    ] = ""
    query: Annotated[str, Field(max_length=128)] = ""


# Expose immutable target/display metadata and current business state without credential bindings.
class OperationSummary(Contract):
    responsible_administrator_name: Text | None = None
    responsible_administrator_id: UUID | None = None
    responsibility_revision: int | None = None
    can_take_responsibility: bool = False
    id: UUID
    kind: Literal[
        "inspect_import",
        "organization_action",
        "configuration_update",
        "configuration_check",
        "cost_collection",
        "required_user_check",
        "recovery_network_repair",
        "recovery_password",
        "signing_key",
    ]
    state: OperationState
    stage: Text
    accepted_at: UtcInstant
    # Earliest execution eligibility for a still-scheduled rotation, not its acceptance time.
    scheduled_for: UtcInstant | None = Field(default=None, exclude_if=lambda value: value is None)
    updated_at: UtcInstant
    completed_at: UtcInstant | None
    initiated_by: Text | None
    target_tenancy_ocid: TenancyOcid | None
    title: Text | None = None
    target_label: Text | None = None
    provider_mode: Literal["simulated"] = "simulated"
    guided_onboarding: bool = False
    result_tenancy_id: UUID | None = None


# Return a stable page of real persisted operations; an empty directory is a valid initial state.
class OperationDirectory(Contract):
    # Workspace-wide supported human actions on waiting/attention workflows, not diagnostics.
    attention_count: int = Field(default=0, ge=0)
    items: list[OperationSummary]
    total: int
    page: int
    page_size: int
    pages: int


# Show the current logical step and last safe result code, never a raw SDK exception or payload.
class OperationStepView(Contract):
    step_key: Annotated[
        str,
        Field(
            pattern=r"^(inspect_target|apply_lifecycle|handoff|inspect_bootstrap|establish_automation|verify_automation|configure_required|verify_required|retire_temporary|configure_baseline|verify_configured_access|capture_required_users|prepare_automation_signer|prepare_recovery_password|configuration_check:[0-9a-f-]{36}|required_users:[0-9a-f-]{36}|recovery_network:[0-9a-f-]{36}|recovery_password:[0-9a-f-]{36}|signing_key:[0-9a-f-]{36}|cost:[0-9a-f-]{36}|(remove_member_groups|delete_member_user):[0-9a-f-]{36}|configuration:[0-9a-f-]{36})$"
        ),
    ]
    state: Literal["running", "verified", "needs_attention"]
    attempt_number: Generation
    verified_at: UtcInstant | None
    safe_code: Text | None


# Project only named, closed result labels; provider contexts and identity bindings stay private.
class UserCheckFact(Contract):
    label: Literal[
        "Presence",
        "Administrators group",
        "Domain administrator role",
        "Console MFA exemption",
        "Approved-network restriction",
    ]
    state: Literal["not_checked", "present", "missing", "unknown", "verified", "drift"]


# Historical sections describe this operation's observation, never current access readiness.
class UserCheckSection(Contract):
    anchor: Literal[
        "automation-presence",
        "automation-assignment",
        "recovery-presence",
        "recovery-assignment",
        "recovery-policy",
    ]
    checked_at: UtcInstant | None = None
    facts: tuple[UserCheckFact, ...]


# Preserve event ordering and bounded historical visibility without disclosing authorization data.
class OperationEventView(Contract):
    # Fixed server-derived checkpoint text; raw outcomes and private version references stay private.
    summary: Text | None = Field(default=None, exclude_if=lambda value: value is None)
    # Only required-user outcomes carry these safe historical result sections.
    user_checks: tuple[UserCheckSection, ...] = ()
    automation_keys: AutomationKeysView | None = None
    kind: Literal[
        "operation_responsibility_changed",
        "email_delivery",
        "operation_intent",
        "inspection_dispatch",
        "inspection_outcome",
        "organization_action_outcome",
        "onboarding_action",
        "onboarding_outcome",
        "configuration_outcome",
        "configuration_retry",
        "configuration_check_outcome",
        "cost_collection_outcome",
        "required_user_check_outcome",
        "recovery_network_outcome",
        "recovery_password_outcome",
        "recovery_password_disclosed",
        "signing_key_outcome",
        "signing_key_requested",
    ]
    at: UtcInstant
    safe_code: Text | None


# Summarize the original recovery obligation without exposing custody references or secret material.
class RecoveryPasswordProgress(Contract):
    phase: Literal["setup", "rotation"]
    tenancy_id: UUID
    user_name: Text
    first_request_at: UtcInstant | None = None
    rotation_due_at: UtcInstant | None = None
    request_count: int = Field(ge=0)

    # Missing/inconsistent history is unavailable; page reads never invent or extend a window.
    @model_validator(mode="after")
    def original_window(self):
        if self.phase == "setup":
            if (
                self.first_request_at is not None
                or self.rotation_due_at is not None
                or self.request_count
            ):
                raise ValueError("INVALID_RECOVERY_PROGRESS")
        elif (
            self.first_request_at is None
            or self.rotation_due_at is None
            or self.request_count < 1
            or self.rotation_due_at - self.first_request_at != timedelta(hours=4)
        ):
            raise ValueError("INVALID_RECOVERY_PROGRESS")
        return self


# Keep status, logical steps and recent history from one read-only database snapshot.
class OperationDetail(Contract):
    recovery_password: RecoveryPasswordProgress | None = None
    notifications: tuple[NotificationSummary, ...] = ()
    operation: OperationSummary
    steps: list[OperationStepView]
    events: list[OperationEventView]
    events_limited: bool
