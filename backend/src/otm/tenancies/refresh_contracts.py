"""Closed fleet-read commands and small job-progress projections; no provider authority."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from otm.contracts import Contract


# One browser command reuses independent child/category request keys after transport loss.
class FleetRefreshRequest(Contract):
    client_request_key: UUID


# Counts describe admission, not healthy provider data; one user job also reads key inventory.
class RefreshCategory(Contract):
    category: Literal["costs", "users", "configuration"]
    operation_ids: tuple[UUID, ...]
    skipped_count: Annotated[int, Field(ge=0)]
    failed_count: Annotated[int, Field(ge=0)]


# The fleet is server-selected across all pages and filters, with independent category eligibility.
class FleetRefreshReceipt(Contract):
    tenancy_count: Annotated[int, Field(ge=0)]
    categories: tuple[RefreshCategory, ...]


# Poll a bounded set of admitted read jobs; IDs cannot grant another workspace's visibility.
class FleetRefreshStatusRequest(Contract):
    operation_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=3000)]


# Finished means the read job ended; actual findings remain in dated tenancy/check records.
class RefreshJob(Contract):
    operation_id: UUID
    state: Literal["pending", "finished", "failed", "unavailable"]


# One scoped query replaces hundreds of browser detail requests on every progress poll.
class FleetRefreshStatus(Contract):
    jobs: tuple[RefreshJob, ...]
