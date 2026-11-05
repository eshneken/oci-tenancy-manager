"""Closed directory, import and drift projections; no raw source rows in error responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from otm.contracts import Contract, UtcInstant
from otm.organization.persistence_contracts import OrganizationOutcome


# Allowlist sorting and bound server-side pagination and search independently of SQL syntax.
class OrganizationQuery(Contract):
    page: int = Field(default=1, ge=1, le=100000)
    page_size: Literal[10, 25, 50] = 10
    sort: Literal[
        "full_name", "email", "manager_name", "leader_name", "lob_name", "tenancy_count"
    ] = "full_name"
    direction: Literal["asc", "desc"] = "asc"
    query: str = Field(default="", max_length=128)
    include_removed: bool = False


# Directory fields are derived from one applied revision and its pinned configuration.
class EmployeeView(Contract):
    id: UUID
    full_name: str
    email: str
    manager_name: str | None
    leader_name: str | None
    lob_name: str | None
    absence_review: bool
    tenancy_count: int = 0
    pending_tenancy_count: int = 0
    directory_status: Literal["included", "exempt", "offboarded", "outside", "merged"] = "included"
    pending_operation_id: UUID | None = None


# Current drift has a readable explanation; source defects and metadata changes remain separate.
class OrganizationFinding(Contract):
    category: Literal["actionable", "informational", "change"]
    code: str
    employee_name: str
    email: str
    detail: str
    at: datetime


# One bounded read serves directory controls, current drift and the latest applied metadata changes.
class OrganizationDirectory(Contract):
    # Local instruction control only; exposes no command-execution authority.
    test_reset_enabled: bool = False
    pending_workflows: int = 0
    workflows_enabled: bool = False
    provider_mode: Literal["simulated", "unavailable"] = "unavailable"
    actionable_count: int = 0
    history_count: int = 0
    configured: bool
    upload_enabled: bool
    server_time: UtcInstant
    items: tuple[EmployeeView, ...]
    total: int
    employee_count: int
    absence_count: int
    page: int
    pages: int
    page_size: int
    applied_at: datetime | None
    source_as_of: datetime | None
    absence_eligible: bool
    latest: OrganizationOutcome | None
    findings: tuple[OrganizationFinding, ...]
