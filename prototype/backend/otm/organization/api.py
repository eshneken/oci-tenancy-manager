"""Local, read-only contract harness; no SSO or production deployment entry point."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from otm.organization.contracts import Completeness, Contract, PersonState, Revision
from otm.organization.store import Store


# Revision and coverage metadata attached to each pinned organization response.
class Context(Contract):
    organization_revision_id: UUID
    configuration_revision_id: UUID
    source_snapshot_id: UUID
    published_at: datetime
    source_captured_at: datetime | None
    declared_completeness: Completeness
    assessed_coverage: Completeness
    absence_eligible: bool


# Independent current applied/proposed pointers for inspection and stale-preview checks.
class Workspace(Contract):
    workspace_id: str
    applied_version_id: UUID | None
    proposed_version_id: UUID | None
    configuration_id: UUID
    proposal_status: Literal["no_proposal", "already_applied", "pending_application", "stale"]
    message: str


# Readable metadata delta or exception, with original evidence and live processing
# status.
class ReconciliationRow(Contract):
    id: UUID
    workspace_id: str
    feed_id: UUID
    proposed_version_id: UUID
    applied_version_id: UUID | None
    person_id: UUID | None
    person_email: str | None
    category: str
    kind: str
    target: str
    field: str | None
    before_value: object | None
    after_value: object | None
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    reason: str | None
    actor: str | None


# Requested bounded page and total matching records before pagination.
class Pagination(Contract):
    page: int
    page_size: int
    total: int


# One page of people from a single explicitly selected organization revision.
class PeoplePage(Contract):
    context: Context
    data: tuple[PersonState, ...]
    pagination: Pagination


# Person state and provenance from the requested revision, never an implicit latest read.
class PersonDetail(Contract):
    context: Context
    data: PersonState


# Current publication pointer used to offer refresh without replacing a pinned view.
class Head(Contract):
    organization_revision_id: UUID | None
    published_at: datetime | None


# Project revision provenance into the shared read-response context.
def context(revision: Revision) -> Context:
    return Context(
        organization_revision_id=revision.id,
        configuration_revision_id=revision.configuration_id,
        source_snapshot_id=revision.snapshot_id,
        published_at=revision.published_at,
        source_captured_at=revision.source_captured_at,
        declared_completeness=revision.declared_completeness,
        assessed_coverage=revision.assessed_coverage,
        absence_eligible=revision.absence_eligible,
    )


# Build the explicitly opted-in, read-only local API for one population.
#
# This harness has no SSO and must not be used as a production entry point.
# People list/detail reads require a revision; only head discovery follows latest state.
def build_local_read_api(
    store: Store, population_id: str, *, allow_local_prototype: bool = False
) -> FastAPI:
    if not allow_local_prototype:
        raise ValueError("explicit local prototype opt-in required; SSO is not implemented")
    app = FastAPI(
        title="Tenancy Manager organization contract prototype",
        version="0.1.0",
        description="Local read-only harness. No SSO; not a production entry point.",
    )

    # Wrap intentional HTTP failures in the local contract error envelope.
    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"error": error.detail})

    # Load a sealed revision and hide missing or other-population revisions behind 404.
    def read_revision(revision_id: UUID) -> Revision:
        try:
            result = store.revision(revision_id)
        except KeyError as error:
            raise HTTPException(404, {"code": "REVISION_NOT_FOUND"}) from error
        if result.population_id != population_id:
            raise HTTPException(404, {"code": "REVISION_NOT_FOUND"})
        return result

    # Return the current revision pointer without changing an existing pinned view.
    @app.get("/api/v1/organization/head", response_model=Head)
    def head() -> Head:
        value = store.head(population_id)
        return Head(
            organization_revision_id=value.id if value else None,
            published_at=value.published_at if value else None,
        )

    # Filter, deterministically sort and page people within one selected revision.
    #
    # manager_id selects all descendants, excluding the manager itself. The prototype
    # filters its small immutable snapshot in memory; this is not a production query plan.
    @app.get("/api/v1/organization/people", response_model=PeoplePage)
    def people(
        revision_id: UUID,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        query: str = Query("", max_length=200),
        manager_id: UUID | None = None,
        lob_id: str | None = None,
        sort: Literal["name", "email"] = "name",
        direction: Literal["asc", "desc"] = "asc",
    ) -> PeoplePage:
        value = read_revision(revision_id)
        items = list(value.people)
        if manager_id:
            manager = next((person for person in items if person.id == manager_id), None)
            if manager is None:
                raise HTTPException(404, {"code": "PERSON_NOT_IN_REVISION"})
            items = [p for p in items if manager.email in p.manager_path]
        if lob_id:
            items = [p for p in items if p.lob_id == lob_id]
        needle = query.strip().casefold()
        if needle:
            items = [
                p
                for p in items
                if needle in (p.full_name or "").casefold() or needle in p.email.casefold()
            ]
        items.sort(
            key=lambda p: (
                (p.full_name or p.email).casefold() if sort == "name" else p.email,
                str(p.id),
            ),
            reverse=direction == "desc",
        )
        offset = (page - 1) * page_size
        return PeoplePage(
            context=context(value),
            data=tuple(items[offset : offset + page_size]),
            pagination=Pagination(page=page, page_size=page_size, total=len(items)),
        )

    # Return a stable person identity only when it exists in the selected revision.
    @app.get("/api/v1/organization/people/{person_id}", response_model=PersonDetail)
    def person(person_id: UUID, revision_id: UUID) -> PersonDetail:
        value = read_revision(revision_id)
        found = next((p for p in value.people if p.id == person_id), None)
        if found is None:
            raise HTTPException(404, {"code": "PERSON_NOT_IN_REVISION"})
        return PersonDetail(context=context(value), data=found)

    # Discover applied/proposed IDs; immutable list/detail routes still require
    # explicit IDs.
    @app.get("/api/v1/organization/workspace", response_model=Workspace)
    def workspace() -> Workspace:
        return Workspace.model_validate(store.workspace_context(population_id))

    # Read bounded live recommendation history or pending exceptions; this sends no
    # messages.
    @app.get("/api/v1/organization/reconciliation", response_model=list[ReconciliationRow])
    def reconciliation(
        pending_only: bool = False,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> list[ReconciliationRow]:
        view = "pending_organization_reviews" if pending_only else "organization_reconciliation"
        rows = store.inspection_rows(view, population_id)
        rows.sort(key=lambda row: (row["created_at"], str(row["id"])), reverse=True)
        return [ReconciliationRow.model_validate(row) for row in rows[offset : offset + limit]]

    return app
