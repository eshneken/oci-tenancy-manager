"""Laptop-only CSV intake and organization/tenancy UI over the existing reconciliation store."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from otm.organization.associations import TenancyRegistry
from otm.organization.contracts import Contract
from otm.organization.csv_feed import MAX_BYTES, CsvFeedError, csv_envelope, parse_csv
from otm.organization.local_lab import LocalLab
from otm.organization.review_workflow import ReviewWorkflow, informational_history, open_reviews
from otm.organization.store import PublicationConflict, Store

STATIC = Path(__file__).with_name("static")


# Expose actual employee profiles, retaining absent employees but excluding placeholders.
def employee_rows(store: Store, workspace_id: str) -> list[dict]:
    rows = [
        row
        for row in store.inspection_rows("current_organization", workspace_id)
        if row["profile"] == "employee"
    ]
    head = store.head(workspace_id)
    if not head:
        return rows
    people = {person.email: person for person in head.people}
    names = {address: person.full_name or address for address, person in people.items()}
    # Missing source names remain the observed/configured name or email; never hardcode a team.
    registry = TenancyRegistry(store, workspace_id).read()
    directory = {p["id"]: p for p in registry["people"]}
    rows = [r for r in rows if directory.get(str(r["person_id"]), {}).get("managed", True)]
    pending_onboarding = {
        str(i) for i in store.configuration(workspace_id).pending_onboarding_person_ids
    }
    for row in rows:
        registry_person = directory.get(str(row["person_id"]), {})
        row["association_count"] = registry_person.get("association_count", 0)
        row["management_status"] = registry_person.get("status", "Managed")
        if str(row["person_id"]) in pending_onboarding or registry_person.get(
            "onboarding_required"
        ):
            row["tenancy_setup_review"] = True
        reported = people[row["email"]].reported_top_manager_email
        row["reported_top_manager_email"] = reported
        person = people[row["email"]]
        row["retained_absence"] = bool(person.absence_review_since and not person.absence_review)
        row["top_manager_name"] = (
            names.get(reported) if reported else row["accountable_leader_name"]
        )
        row["manager_name"] = row["manager_name"] or names.get(row["manager_email"])
    return rows


# Join active registry tenancies to the owner's current derived organizational LOB.
#
# Source hierarchy changes affect accountability rollups, never tenancy ownership. Registry
# reads also retain legacy/ownerless entries so unresolved ownership cannot hide a tenancy.
def tenancy_rows(store: Store, workspace_id: str) -> list[dict]:
    registry = TenancyRegistry(store, workspace_id).read()
    head = store.head(workspace_id)
    people = {str(person.id): person for person in head.people} if head else {}
    labels = {lob.id: lob.label for lob in store.configuration(workspace_id).lobs}
    rows = []
    for tenancy in registry["tenancies"]:
        owner = people.get(tenancy["owner_person_id"])
        rows.append(
            {
                key: tenancy[key]
                for key in (
                    "id",
                    "name",
                    "kind",
                    "status",
                    "owner_person_id",
                    "owner_name",
                    "owner_email",
                    "member_count",
                )
            }
            | {
                "lob_name": labels.get(owner.lob_id) if owner else None,
                "member_count": len(tenancy["associations"]),
            }
        )
    return rows


# Return actionable reviews only so source warnings cannot obscure administrator work.
def review_rows(store: Store, workspace_id: str) -> list[dict]:
    return [row for row in open_reviews(store, workspace_id) if row["category"] == "actionable"]


# Bind a clean confirmation to the exact run, proposal, applied head and configuration.
class CleanWorkspaceRequest(Contract):
    workspace_id: str
    applied_version_id: UUID | None
    proposed_version_id: UUID | None
    configuration_id: UUID


# Strict, context-bound administrator command; no caller-supplied organization state.
class ReviewCommand(Contract):
    context: CleanWorkspaceRequest
    case_id: str
    operation: Literal[
        "create_tenancy",
        "import_tenancy",
        "shared_membership",
        "delete_tenancy",
        "keep_tenancy",
        "resolve",
        "no_tenancy_required",
        "ignore",
        "remove_user",
        "keep_returned",
        "merge",
    ]
    reason: str | None = Field(default=None, min_length=3, max_length=1000)
    partner_email: str | None = None
    tenancy_id: UUID | None = None
    name: str | None = None
    kind: Literal["individual", "shared"] | None = None


# One explicit disposition for one current association in an offboarding preview.
class AssociationPlan(Contract):
    association_id: UUID
    action: Literal["delete", "remove", "transfer", "keep"]
    recipient_person_id: UUID | None = None


# Version-bound local registry command; caller supplies intent, never replacement state.
class RegistryCommand(Contract):
    context: CleanWorkspaceRequest
    operation: Literal[
        "create_tenancy",
        "import_tenancy",
        "join_shared",
        "offboard_person",
        "reonboard",
        "return_to_org",
        "no_tenancy_required",
        "update_tenancy",
        "transfer_owner",
        "assign_owner",
        "remove_member",
        "delete_tenancy",
    ]
    person_id: UUID
    tenancy_id: UUID | None = None
    name: str | None = Field(default=None, max_length=200)
    kind: Literal["individual", "shared"] | None = None
    owner_person_id: UUID | None = None
    reason: str | None = Field(default=None, min_length=3, max_length=1000)
    plan: tuple[AssociationPlan, ...] = ()
    confirm_no_associations: bool = False


# Serve opted-in local inspection/intake; the launcher must bind only to loopback.
def build_local_web(
    store: Store,
    workspace_id: str,
    *,
    allow_local_prototype: bool = False,
    allow_clean_workspace: bool = False,
) -> FastAPI:
    if not allow_local_prototype:
        raise ValueError("explicit local prototype opt-in required")
    lab = LocalLab(store, workspace_id) if allow_clean_workspace else None

    # Resolve the stable lab after each clean; existing read-only harnesses stay fixed.
    def active_workspace() -> str:
        return lab.active() if lab else workspace_id

    app = FastAPI(title="OCI Tenancy Manager · local organization lab")
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    # Require same-origin custom-header writes; never allow a remote site to submit a feed.
    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = urlsplit(str(request.base_url))
            supplied = urlsplit(origin) if origin else None
            if (
                request.headers.get("x-otm-local") != "csv-upload"
                or (
                    supplied
                    and (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc)
                )
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse(
                    {"detail": "Upload must originate from this local app."}, status_code=403
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    # Serve the shared employee, tenancy and exception screens with local static assets.
    @app.get("/", response_class=FileResponse)
    @app.get("/exceptions", response_class=FileResponse)
    @app.get("/tenancies", response_class=FileResponse)
    def screen():
        return FileResponse(STATIC / "index.html")

    # Return counts and the current applied snapshot without exposing credentials.
    @app.get("/api/local/summary")
    def summary():
        active = active_workspace()
        people = employee_rows(store, active)
        issues = review_rows(store, active)
        head = store.head(active)
        feed = None
        if head:
            with store.engine.connect() as connection:
                feed = (
                    connection.execute(
                        select(store.tables["feed"]).where(
                            store.tables["feed"].c.id == str(head.snapshot_id)
                        )
                    )
                    .mappings()
                    .one()
                )
        tenancies = TenancyRegistry(store, active).read()["tenancies"]
        return {
            "tenancies": {
                "total": len(tenancies),
                "individual": sum(t["kind"] == "individual" for t in tenancies),
                "shared": sum(t["kind"] == "shared" for t in tenancies),
                "unassigned_owner": sum(t["owner_person_id"] is None for t in tenancies),
            },
            "workspace_id": active,
            "context": store.workspace_context(active),
            "can_clean_workspace": lab is not None,
            "employees": len(people),
            "absences": sum(p["absence_review"] for p in people),
            "new_employees": sum(p["tenancy_setup_review"] for p in people),
            "exceptions": len(issues),
            "informational": len(informational_history(store, active)),
            "lobs": sorted({p["lob_name"] for p in people if p["lob_name"]}),
            "revision_id": str(head.id) if head else None,
            "published_at": head.published_at if head else None,
            "absence_eligible": head.absence_eligible if head else None,
            "input_rows": len(feed["data"]["records"]) if feed else 0,
            "source_name": feed["data"]["envelope"]["external_snapshot_id"].split("|", 1)[0]
            if feed
            else None,
        }

    # Search all visible columns and deterministically sort/page the current small census.
    @app.get("/api/local/employees")
    def employees(
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        query: str = Query("", max_length=200),
        lob: str = "",
        sort: Literal[
            "full_name",
            "email",
            "manager_name",
            "accountable_leader_name",
            "top_manager_name",
            "lob_name",
            "association_count",
        ] = "full_name",
        direction: Literal["asc", "desc"] = "asc",
    ):
        rows = employee_rows(store, active_workspace())
        fields = ("full_name", "email", "manager_name", "top_manager_name", "lob_name")
        needle = query.strip().casefold()
        rows = [
            r
            for r in rows
            if (not lob or r["lob_name"] == lob)
            and (not needle or any(needle in str(r.get(k) or "").casefold() for k in fields))
        ]
        rows.sort(
            key=lambda r: (
                r[sort] if sort == "association_count" else str(r.get(sort) or "").casefold(),
                r["email"],
            ),
            reverse=direction == "desc",
        )
        offset = (page - 1) * page_size
        return {
            "data": rows[offset : offset + page_size],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    # Search active tenancies with numeric count sorting and a stable ID tie-break.
    @app.get("/api/local/tenancies")
    def tenancies(
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        query: str = Query("", max_length=200),
        lob: str = "",
        sort: Literal[
            "name", "kind", "owner_name", "owner_email", "lob_name", "member_count"
        ] = "name",
        direction: Literal["asc", "desc"] = "asc",
    ):
        rows = tenancy_rows(store, active_workspace())
        needle = query.strip().casefold()
        fields = ("name", "kind", "owner_name", "owner_email", "lob_name")
        rows = [
            row
            for row in rows
            if (not lob or row["lob_name"] == lob)
            and (not needle or any(needle in str(row.get(key) or "").casefold() for key in fields))
        ]
        rows.sort(
            key=lambda row: (
                row[sort] if sort == "member_count" else str(row[sort] or "").casefold(),
                row["id"],
            ),
            reverse=direction == "desc",
        )
        offset = (page - 1) * page_size
        return {
            "data": rows[offset : offset + page_size],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    # Page the actionable queue separately from dated warning/change history.
    @app.get("/api/local/exceptions")
    def exceptions(
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
        query: str = Query("", max_length=200),
        kind: str = "",
        tab: Literal["actionable", "informational"] = "actionable",
    ):
        active = active_workspace()
        rows = (
            review_rows(store, active)
            if tab == "actionable"
            else informational_history(store, active)
        )
        needle = query.strip().casefold()
        filtered = [
            r
            for r in rows
            if (not kind or r["kind"] == kind)
            and (not needle or needle in " ".join(str(v or "") for v in r.values()).casefold())
        ]
        offset = (page - 1) * page_size
        return {
            "data": filtered[offset : offset + page_size],
            "total": len(filtered),
            "page": page,
            "page_size": page_size,
            "kinds": [
                {
                    "value": k,
                    "label": "Tenancy simulations"
                    if k == "TENANCY_ACTION_SIMULATED"
                    else next(r["title"] for r in rows if r["kind"] == k),
                }
                for k in sorted({r["kind"] for r in rows})
            ],
        }

    # Apply guarded simulated success or an organization decision without OCI operations.
    @app.post("/api/local/reviews/operate")
    def review_operation(command: ReviewCommand):
        active = active_workspace()
        if command.context.workspace_id != active:
            raise HTTPException(409, "Workspace changed. Refresh before taking action.")
        try:
            return ReviewWorkflow(store, active).operate(
                command.case_id,
                command.operation,
                command.context.model_dump(mode="json"),
                command.reason,
                command.partner_email,
                tenancy_id=command.tenancy_id,
                name=command.name,
                kind=command.kind,
            )
        except PublicationConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    # Expose registered ownership/membership and explicit re-onboarding candidates.
    @app.get("/api/local/tenancy-registry")
    def tenancy_registry():
        return TenancyRegistry(store, active_workspace()).read()

    # Atomically simulate an association operation with directory and review consequences.
    @app.post("/api/local/tenancy-registry/operate")
    def registry_operation(command: RegistryCommand):
        active = active_workspace()
        if command.context.workspace_id != active:
            raise HTTPException(409, "Workspace changed. Refresh before taking action.")
        try:
            return TenancyRegistry(store, active).operate(command.model_dump(mode="json"))
        except PublicationConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    # Offer unresolved absent/new pairs from this run, never inferred name matches.
    @app.get("/api/local/reviews/merge-candidates")
    def merge_candidates(case_id: str):
        rows = review_rows(store, active_workspace())
        case = next((row for row in rows if row["id"] == case_id), None)
        if not case:
            raise HTTPException(404, "Review is no longer open.")
        kind = (
            "TENANCY_SETUP_REVIEW"
            if case["kind"] == "PERSON_ABSENCE_REVIEW"
            else "PERSON_ABSENCE_REVIEW"
        )
        return [
            {"email": row["email"], "name": row["name"]}
            for row in rows
            if row["kind"] == kind and row["email"] != case["email"]
        ]

    # Retain bounded rejection facts without storing untrusted oversized raw content.
    def reject_intake(active, message):
        with store.engine.begin() as connection:
            store._audit(
                connection,
                active,
                "feed_rejected",
                datetime.now(UTC),
                {"diagnostics": [message], "format": "csv"},
                actor="service:csv-intake",
            )

    # Validate CSV, retain canonical JSON and run transactional publication.
    #
    # Each POST is a new snapshot, even when its bytes match a previous upload.
    # The generated snapshot identity is independent of the raw-content audit hash.
    # Local receipt time is the scenario clock; future connectors must bind real capture
    # metadata and reuse an observation identity only when retrying the same delivery.
    @app.post("/api/local/feeds")
    async def upload(request: Request, complete: bool = True):
        active = active_workspace()
        if request.headers.get("x-otm-workspace", active) != active:
            raise HTTPException(409, "Workspace changed. Refresh before uploading.")
        if request.headers.get("content-type", "").split(";")[0] != "text/csv":
            reject_intake(active, "Select a CSV file.")
            raise HTTPException(415, "Select a CSV file.")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                reject_intake(active, "CSV exceeds the 2 MiB upload limit.")
                raise HTTPException(413, "CSV exceeds the 2 MiB upload limit.")
        try:
            records = parse_csv(bytes(content))
        except CsvFeedError as error:
            reject_intake(active, str(error))
            raise HTTPException(422, str(error)) from error
        now = datetime.now(UTC)
        envelope, digest = csv_envelope(store, active, bytes(content), complete=complete, now=now)
        result = await run_in_threadpool(store.ingest, records, envelope, now, digest)
        return {
            "outcome": result.model_dump(mode="json"),
            "input_rows": len(records),
            "identity_key": "normalized_email",
            "clock": "local_upload_receipt",
        }

    # Start a clean local run only after same-origin, version-bound user confirmation.
    @app.post("/api/local/workspace/clean")
    def clean_workspace(expected: CleanWorkspaceRequest):
        if lab is None:
            raise HTTPException(403, "Cleaning is not enabled for this workspace.")
        try:
            active = lab.clean(expected.model_dump(mode="json"))
        except PublicationConflict as error:
            raise HTTPException(409, str(error)) from error
        return {"workspace_id": active, "history_preserved": True}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
