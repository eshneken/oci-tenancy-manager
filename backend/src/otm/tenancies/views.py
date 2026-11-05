"""Closed workflow previews and registry/review screens; private commands remain server-side."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from otm.configuration.contracts import BaselineVersion
from otm.contracts import Contract, UtcInstant
from otm.email_policy import EmailContacts
from otm.tenancies.contracts import Action, OrganizationContext


# Share bounded literal search and paging conventions across the two management directories.
class ReviewQuery(Contract):
    category: Literal["actionable", "informational", "history"] = "actionable"
    query: Annotated[str, Field(max_length=128)] = ""
    sort: Literal["first_seen_at", "name", "kind", "status"] = "first_seen_at"
    direction: Literal["asc", "desc"] = "asc"
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50] = 10


# A persisted episode retains its own dates and safe before/after metadata for human review.
class ReviewView(Contract):
    id: UUID
    kind: str
    category: Literal["actionable", "informational", "change"]
    status: Literal["open", "resolved", "ignored"]
    person_id: UUID | None
    name: str
    email: str
    first_seen_at: UtcInstant
    last_seen_at: UtcInstant
    resolved_at: UtcInstant | None
    resolution: str | None
    operation_id: UUID | None
    data: dict[str, object]


# Return independent inbox, retained history and latest-feed information counts.
class ReviewDirectory(Contract):
    items: tuple[ReviewView, ...]
    total: int
    page: int
    pages: int
    page_size: int
    actionable_count: int
    history_count: int
    informational_count: int = 0


# Named current employees are selected explicitly for transfers and one-way identity merges.
class PersonOption(Contract):
    id: UUID
    name: str
    email: str


# Show every current obligation with only the actions allowed by its role and tenancy type.
class AssociationView(Contract):
    id: UUID
    person_id: UUID
    tenancy_id: UUID
    tenancy_name: str
    tenancy_kind: Literal["individual", "shared"]
    tenancy_status: str
    role: Literal["owner", "member"]
    status: str
    compartment_ocid: str | None
    compartment_name: str | None
    cleanup_required: bool
    operation_id: UUID | None
    actions: tuple[Literal["delete", "transfer", "remove", "keep"], ...]


# A registered tenancy includes its accountable owner in the count and exposes pending work.
class TenancyView(Contract):
    # Confirmed missing/different categories; freshness and read availability are separate.
    configuration_issue_count: int = 0
    configuration_confirmed_issue_count: int = 0
    configuration_check_state: Literal[
        "matching", "drifted", "unavailable", "superseded", "not_checked", "checking"
    ] = "not_checked"
    configuration_checked_at: UtcInstant | None = None
    configuration_check_stale: bool = False
    has_pending_operation: bool = False
    desired_configuration_id: UUID | None = None
    last_verified_configuration_id: UUID | None = None
    override_categories: tuple[Literal["policy", "quota", "budget"], ...] = ()
    operation_completed_at: UtcInstant | None = None
    baseline_version_id: UUID | None = None
    baseline_version_number: int | None = None
    verified_baseline_version_id: UUID | None = None
    verified_baseline_version_number: int | None = None
    configuration_verified_at: UtcInstant | None = None
    id: UUID
    name: str
    tenancy_ocid: str
    parent_tenancy_ocid: str
    home_region: str
    kind: Literal["individual", "shared"]
    status: str
    origin: Literal["create", "import"]
    provider_mode: Literal["simulated"]
    owner_person_id: UUID | None
    owner_name: str | None
    owner_email: str | None
    manager_name: str | None
    leader_name: str | None
    lob_name: str | None
    member_count: int
    operation_id: UUID | None
    operation_state: str | None
    verified_at: UtcInstant | None
    created_at: UtcInstant
    cleanup_count: int


# Parent-subscription choices are provider facts; the browser never supplies the allowed region set.
class CreationRegion(Contract):
    identifier: str
    name: str


# The same exact server context accompanies every dialog, independent of browser-supplied labels.
class PersonWorkflow(Contract):
    email_contacts: EmailContacts | None = None
    current_baseline: BaselineVersion | None = None
    # True blocks provisioning only; existing-tenancy cleanup and decisions remain independent.
    mapping_required: bool = False
    creation_regions: tuple[CreationRegion, ...] = ()
    context: OrganizationContext
    person: PersonOption
    review: ReviewView | None
    source_present: bool
    is_manager: bool
    directory_status: str
    pending_operation_id: UUID | None
    provider_mode: Literal["simulated", "unavailable"]
    actions: tuple[Action, ...]
    associations: tuple[AssociationView, ...]
    shared_tenancies: tuple[TenancyView, ...]
    transfer_recipients: tuple[PersonOption, ...]
    merge_partners: tuple[PersonOption, ...]


# Filter the registered tenancy inventory without mistaking an empty page for zero total children.
class TenancyQuery(Contract):
    shared_only: bool = False
    page: Annotated[int, Field(ge=1, le=100000)] = 1
    page_size: Literal[10, 25, 50] = 10
    query: Annotated[str, Field(max_length=128)] = ""
    sort: Literal["name", "owner_name", "manager_name", "lob_name", "member_count"] = "name"
    direction: Literal["asc", "desc"] = "asc"


# Inventory cards count active/pending registered children rather than organization employees.
class TenancyDirectory(Contract):
    latest_baseline_id: UUID | None = None
    latest_baseline_version_number: int | None = None
    items: tuple[TenancyView, ...]
    total: int
    page: int
    pages: int
    page_size: int
    total_tenancies: int
    individual_count: int
    shared_count: int
    pending_count: int
    issue_count: int


# Existing parent choices are discovered through the facade, never accepted as arbitrary SDK
# targets.
class CompartmentOption(Contract):
    ocid: str
    name: str


# Details preserve removed membership/cleanup obligations separately from active member counts.
class TenancyDetail(Contract):
    configuration_operation_id: UUID | None = None
    onboarding_operation_id: UUID | None = None
    tenancy: TenancyView
    people: tuple[PersonOption, ...]
    memberships: tuple[AssociationView, ...]
    compartment_parents: tuple[CompartmentOption, ...]
