"""Authenticated CSV acquisition and employee read model over immutable organization storage."""

from datetime import UTC
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, TypeAdapter
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure
from otm.organization.contracts import Configuration, Envelope, Intake
from otm.organization.csv_feed import MAX_BYTES, CsvFeedError, parse_csv
from otm.organization.persistence_contracts import OrganizationOutcome
from otm.organization.review_rules import suppressed
from otm.organization.views import (
    EmployeeView,
    OrganizationDirectory,
    OrganizationFinding,
    OrganizationQuery,
)
from otm.storage.organization import OrganizationConflict, outcome


# Load only an explicitly selected private operator profile; CSV content cannot grant census trust.
def load_profile(path: Path | None):
    if path is None:
        return None
    if path.stat().st_size > 65536:
        raise ValueError("INVALID_ORGANIZATION_CONFIGURATION")
    config = Configuration.model_validate_json(path.read_bytes())
    if config.policy.allow_undated_development_metadata:
        raise ValueError("DATED_PRODUCTION_FEEDS_REQUIRED")
    return config


# Derive current issues without adding another mutable copy of employee or snapshot state.
def project(config, current, previous, issues=()):
    if current is None:
        return (), ()
    people = {p.email: p for p in current.people}
    lobs = {lob.id: lob.label for lob in config.lobs}
    rows, findings = [], []
    prior = {p.id: p for p in previous.people} if previous else {}

    # Names can be absent for referenced managers; use their email instead of inventing a profile.
    def name(address):
        person = people.get(address)
        return (person.full_name or address) if person else address

    # Apply durable administrator suppressions to current conditions, never to metadata history.
    def finding(person, code, detail, category="actionable", target=None):
        if category == "change" or not suppressed(
            config, code, target or person.email, current.people
        ):
            findings.append(
                OrganizationFinding(
                    category=category,
                    code=code,
                    employee_name=person.full_name or person.email,
                    email=person.email,
                    detail=detail,
                    at=current.published_at,
                )
            )

    for person in current.people:
        descriptions = {
            "PERSON_ABSENCE_REVIEW": (
                "Missing from a qualified feed. Review tenancy associations before offboarding."
            ),
            "LOB_MAPPING_REVIEW": "No configured industry segment matches this employee.",
            "LOB_LEADER_REVIEW": "The configured accountable leader requires review.",
            "DESIGNEE_INVALID": ("A configured designee requires eligibility review."),
            "OVERRIDE_CONFLICT": "The source changed a value with an administrator override.",
            "TOP_MANAGER_MISMATCH": (
                "The reported top manager differs from the derived accountable leader."
            ),
            "MANAGER_PROFILE_MISSING": (
                "A manager is referenced but has no employee row in the feed."
            ),
            "ANCESTRY_UNRESOLVED": (
                "The reporting chain is incomplete. Correct the feed or source configuration."
            ),
        }
        for code, target in issues:
            if person.email in target.split(":"):
                finding(
                    person,
                    code,
                    descriptions.get(code, "Review the source configuration."),
                    "informational"
                    if code
                    in {"TOP_MANAGER_MISMATCH", "MANAGER_PROFILE_MISSING", "ANCESTRY_UNRESOLVED"}
                    else "actionable",
                    target=target,
                )
        if person.profile != "employee" or person.id in config.managed_exclusions:
            continue
        rows.append(
            EmployeeView(
                id=person.id,
                full_name=person.full_name or person.email,
                email=person.email,
                manager_name=name(person.manager_email),
                leader_name=name(person.accountable_leader_email),
                lob_name=lobs.get(person.lob_id),
                absence_review=person.absence_review,
            )
        )
        old = prior.get(person.id)
        if old:
            changes = [
                label
                for field, label in (
                    ("full_name", "Name"),
                    ("email", "Email"),
                    ("manager_email", "Manager"),
                    ("lob_id", "Industry segment"),
                )
                if getattr(old, field) != getattr(person, field)
            ]
            if changes:
                finding(
                    person,
                    "METADATA_UPDATED",
                    ", ".join(changes) + " updated automatically.",
                    "change",
                )
        elif not person.absence_review:
            finding(
                person,
                "EMPLOYEE_ADDED",
                "Added to the organization. Tenancy onboarding will be available "
                "in a later development slice.",
                "change",
            )
    return tuple(rows), tuple(findings)


# Keep acquisition identity stable on transport retry while a new manual upload gets a fresh UUID.
class OrganizationWeb:
    # Dependencies are explicit; the initial profile never replaces an existing database
    # configuration.
    def __init__(self, store, clock, initial=None, *, test_reset_enabled=False, workflows=None):
        self.store, self.clock, self.initial = store, clock, initial
        self.test_reset_enabled = test_reset_enabled
        self.workflows = workflows
        from otm.organization.mapping import MappingService

        self.mapping = MappingService(store, initial, workflows)

    # Validate file structure before any initialization or publication and preserve raw digest
    # evidence.
    def upload(self, principal, content, capture, delivery, complete):
        records = parse_csv(content)
        config, _, _, _, _ = self.store.inspection(principal)
        if config is None or not config.lobs:
            raise OrganizationConflict("ORGANIZATION_NOT_CONFIGURED")
        intake = Intake(
            envelope=Envelope(
                source_id=config.policy.source_id,
                population_id=config.policy.population_id,
                external_snapshot_id="manual:" + str(delivery),
                captured_at=capture,
                declared_completeness="complete" if complete else "partial",
            ),
            records=records,
        )
        return self.store.ingest(principal, intake, raw_digest=sha256(content).hexdigest())

    # Scope reads through the real store; only validated, closed view models reach the browser.
    def directory(self, principal, query):
        if self.workflows is not None:
            return self.workflows.organization_directory(
                principal, query, self.initial, test_reset_enabled=self.test_reset_enabled
            )
        config, current, previous, latest, issues = self.store.inspection(principal)
        rows, findings = project(config, current, previous, issues)
        total = len(rows)
        filtered = [
            p
            for p in rows
            if query.query.casefold()
            in " ".join(
                (p.full_name, p.email, p.manager_name or "", p.leader_name or "", p.lob_name or "")
            ).casefold()
        ]
        filtered.sort(
            key=lambda p: ((getattr(p, query.sort) or "").casefold(), p.email),
            reverse=query.direction == "desc",
        )
        pages = max(1, (len(filtered) + query.page_size - 1) // query.page_size)
        page = min(query.page, pages)
        return OrganizationDirectory(
            test_reset_enabled=self.test_reset_enabled,
            configured=config is not None,
            upload_enabled=bool(config and config.lobs),
            server_time=self.clock(),
            items=tuple(filtered[(page - 1) * query.page_size : page * query.page_size]),
            total=len(filtered),
            employee_count=total,
            absence_count=sum(p.absence_review for p in rows),
            page=page,
            pages=pages,
            page_size=query.page_size,
            applied_at=current.published_at if current else None,
            source_as_of=current.source_captured_at if current else None,
            absence_eligible=current.absence_eligible if current else False,
            latest=outcome(latest) if latest else None,
            findings=findings,
        )


# Mount only authenticated read/upload endpoints; session and CSRF middleware remain authoritative.
def organization_router(service):
    router = APIRouter()
    if getattr(service, "mapping", None) is not None:
        from otm.organization.mapping_http import mapping_router

        router.include_router(mapping_router(service.mapping))
    if service.workflows is not None:
        from otm.tenancies.http import workflow_router

        router.include_router(workflow_router(service.workflows))

    # Validate allowlisted controls before reading; storage errors never echo source data or SQL.
    @router.get("/api/organization", response_model=OrganizationDirectory)
    def directory(
        request: Request,
        page: int = 1,
        page_size: int = 10,
        sort: str = "full_name",
        direction: str = "asc",
        query: str = "",
        include_removed: bool = False,
    ):
        try:
            options = OrganizationQuery(
                page=page,
                page_size=page_size,
                sort=sort,
                direction=direction,
                query=query,
                include_removed=include_removed,
            )
        except ValueError:
            return JSONResponse({"code": "INVALID_ORGANIZATION_QUERY"}, status_code=400)
        try:
            return service.directory(request.user, options)
        except SessionFailure:
            raise
        except Exception:
            return JSONResponse({"code": "ORGANIZATION_UNAVAILABLE"}, status_code=503)

    # Stream-limit before parsing and accept only an explicit timezone-aware source time and UUID.
    @router.post("/api/organization/feeds", response_model=OrganizationOutcome)
    async def upload(request: Request):
        try:
            if request.headers.get("content-type", "").split(";")[0] != "text/csv":
                return JSONResponse({"code": "CSV_CONTENT_TYPE_REQUIRED"}, status_code=415)
            capture = TypeAdapter(AwareDatetime).validate_python(request.headers.get("x-otm-as-of"))
            delivery = UUID(request.headers.get("x-otm-delivery", ""))
            completeness = request.headers.get("x-otm-complete")
            if completeness not in {"true", "false"} or capture > service.clock():
                raise ValueError("INVALID_ORGANIZATION_UPLOAD")
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_BYTES:
                    return JSONResponse(
                        {"code": "CSV_TOO_LARGE", "message": "CSV exceeds the 2 MiB upload limit."},
                        status_code=413,
                    )
                data.extend(chunk)
            return await run_in_threadpool(
                service.upload,
                request.user,
                bytes(data),
                capture.astimezone(UTC),
                delivery,
                completeness == "true",
            )
        except CsvFeedError as error:
            return JSONResponse({"code": "INVALID_CSV", "message": str(error)}, status_code=400)
        except OrganizationConflict:
            return JSONResponse({"code": "ORGANIZATION_UPLOAD_CONFLICT"}, status_code=409)
        except SessionFailure:
            raise
        except ValueError:
            return JSONResponse({"code": "INVALID_ORGANIZATION_UPLOAD"}, status_code=400)
        except Exception:
            return JSONResponse({"code": "ORGANIZATION_UPLOAD_UNAVAILABLE"}, status_code=503)

    return router
