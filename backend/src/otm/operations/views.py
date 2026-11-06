"""Closed read models for the durable operation directory; never expose raw intent/provider JSON."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from otm.contracts import Contract, Generation, Text, UtcInstant
from otm.notifications.contracts import NotificationSummary
from otm.operations.contracts import OperationState
from otm.providers.inspection_contracts import TenancyOcid


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
    ]
    state: OperationState
    stage: Text
    accepted_at: UtcInstant
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
            pattern=r"^(inspect_target|apply_lifecycle|handoff|inspect_bootstrap|establish_automation|verify_automation|configure_required|verify_required|retire_temporary|configure_baseline|verify_configured_access|capture_required_users|configuration_check:[0-9a-f-]{36}|cost:[0-9a-f-]{36}|(remove_member_groups|delete_member_user):[0-9a-f-]{36}|configuration:[0-9a-f-]{36})$"
        ),
    ]
    state: Literal["running", "verified", "needs_attention"]
    attempt_number: Generation
    verified_at: UtcInstant | None
    safe_code: Text | None


# Preserve event ordering and bounded historical visibility without disclosing authorization data.
class OperationEventView(Contract):
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
    ]
    at: UtcInstant
    safe_code: Text | None


# Keep status, logical steps and recent history from one read-only database snapshot.
class OperationDetail(Contract):
    notifications: tuple[NotificationSummary, ...] = ()
    operation: OperationSummary
    steps: list[OperationStepView]
    events: list[OperationEventView]
    events_limited: bool
