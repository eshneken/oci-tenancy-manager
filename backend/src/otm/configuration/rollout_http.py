"""Bounded same-origin administrator endpoints for baseline update preview, start and retry."""

from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure
from otm.configuration.override_contracts import (
    CreateConfigurationPlan,
    OverrideEditor,
    OverridePreviewRequest,
    SaveConfigurationReview,
)
from otm.configuration.plans import ConfigurationPlans
from otm.configuration.repair_contracts import ConfigurationRepairRequest
from otm.configuration.rollout_contracts import (
    ConfigurationPlanView,
    ConfigurationPreview,
    ConfigurationProgress,
    ConfigurationUpdate,
)
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import ActionReceipt


# Return fixed diagnostics without reflecting a provider error, SQL statement or employee input.
def guarded(call):
    try:
        return call()
    except SessionFailure:
        raise
    except (OrganizationConflict, RequestConflict) as error:
        known = {
            "CONFIGURATION_TARGET_NOT_FOUND",
            "CONFIGURATION_REPAIR_BLOCKED",
            "CONFIGURATION_CHECK_BUSY",
            "NO_CONFIGURATION_CHECK_TARGETS",
            "CONFIGURATION_PREVIEW_CHANGED",
            "CONFIGURATION_UPDATE_BLOCKED",
            "CONFIGURATION_CONTEXT_UNAVAILABLE",
            "REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT",
            "ORGANIZATION_NOT_CONFIGURED",
        }
        code = str(error) if str(error) in known else "CONFIGURATION_UPDATE_BLOCKED"
        return JSONResponse(
            {"code": code}, status_code=404 if code == "CONFIGURATION_TARGET_NOT_FOUND" else 409
        )
    except ValueError:
        return JSONResponse({"code": "INVALID_CONFIGURATION_UPDATE"}, status_code=400)
    except Exception:
        return JSONResponse({"code": "CONFIGURATION_SERVICE_UNAVAILABLE"}, status_code=503)


# Stream bounds apply before JSON parsing; errors never echo statements, secrets or malformed input.
async def bounded_command(request, model, limit):
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        return JSONResponse({"code": "CONFIGURATION_JSON_REQUIRED"}, status_code=415)
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > limit:
            return JSONResponse({"code": "CONFIGURATION_COMMAND_TOO_LARGE"}, status_code=413)
        body.extend(part)
    try:
        return model.model_validate_json(body)
    except ValueError:
        return JSONResponse({"code": "INVALID_CONFIGURATION_UPDATE"}, status_code=400)


# Global session/admin and Origin/header middleware remains mandatory for every registered command.
def rollout_router(service):
    router = APIRouter()
    plans = ConfigurationPlans(service)

    # Preview is read-only and cannot choose a baseline version or skip a blocked batch member.
    @router.get("/api/configuration/updates/preview", response_model=ConfigurationPreview)
    def preview(request: Request, tenancy_id: UUID | None = None):
        return guarded(lambda: service.preview(request.user, tenancy_id))

    # Only a fresh same-assignment exact-object preview can authorize selected-category repair.
    @router.post("/api/configuration/repairs/preview", response_model=ConfigurationPreview)
    async def repair_preview(request: Request):
        command = await bounded_command(request, ConfigurationRepairRequest, 4096)
        if isinstance(command, JSONResponse):
            return command
        return await run_in_threadpool(
            guarded, lambda: service.preview_repair(request.user, command)
        )

    # A small closed command contains no policies, credentials, arbitrary target set or
    # actor claims.
    @router.post(
        "/api/configuration/updates",
        response_model=ActionReceipt,
        status_code=202,
        responses={200: {"model": ActionReceipt}},
    )
    async def start(request: Request):
        body = bytearray()
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"code": "CONFIGURATION_JSON_REQUIRED"}, status_code=415)
        async for part in request.stream():
            if len(body) + len(part) > 4096:
                return JSONResponse({"code": "CONFIGURATION_COMMAND_TOO_LARGE"}, status_code=413)
            body.extend(part)
        try:
            command = ConfigurationUpdate.model_validate_json(body)
        except ValueError:
            return JSONResponse({"code": "INVALID_CONFIGURATION_UPDATE"}, status_code=400)
        if command.override_mode:
            return JSONResponse({"code": "INVALID_CONFIGURATION_UPDATE"}, status_code=400)
        response = await run_in_threadpool(guarded, lambda: service.start(request.user, command))
        return (
            JSONResponse(
                response.model_dump(mode="json"),
                status_code=202 if response.state == "queued" else 200,
            )
            if isinstance(response, ActionReceipt)
            else response
        )

    # Progress belongs alongside tenancy/configuration work, independently of the history directory.
    @router.get("/api/configuration/updates/{identifier}", response_model=ConfigurationProgress)
    def progress(identifier: UUID, request: Request):
        return guarded(lambda: service.progress(request.user, identifier))

    # Retry accepts no changed baseline or targets and never re-applies verified children.
    @router.post(
        "/api/configuration/updates/{identifier}/retry",
        response_model=ActionReceipt,
        status_code=202,
        responses={200: {"model": ActionReceipt}},
    )
    async def retry(identifier: UUID, request: Request):
        async for part in request.stream():
            if part:
                return JSONResponse({"code": "INVALID_CONFIGURATION_UPDATE"}, status_code=400)
        response = await run_in_threadpool(guarded, lambda: service.retry(request.user, identifier))
        return (
            JSONResponse(
                response.model_dump(mode="json"),
                status_code=202 if response.state == "queued" else 200,
            )
            if isinstance(response, ActionReceipt)
            else response
        )

    # The editor returns only assigned-version context and authored values, never OCI credentials.
    @router.get("/api/configuration/overrides/{identifier}", response_model=OverrideEditor)
    def override_editor(identifier: UUID, request: Request):
        return guarded(lambda: service.override_editor(request.user, identifier))

    # Statement previews are explicit read-only POSTs to preserve the bounded JSON trust boundary.
    @router.post("/api/configuration/overrides/preview", response_model=ConfigurationPreview)
    async def override_preview(request: Request):
        command = await bounded_command(request, OverridePreviewRequest, 2097152)
        if isinstance(command, JSONResponse):
            return command
        return await run_in_threadpool(
            guarded, lambda: service.preview_override(request.user, command)
        )

    # An override applies to one assigned baseline; it cannot choose another version or a batch.
    @router.post(
        "/api/configuration/overrides",
        response_model=ActionReceipt,
        status_code=202,
        responses={200: {"model": ActionReceipt}},
    )
    async def apply_override(request: Request):
        command = await bounded_command(request, ConfigurationUpdate, 2097152)
        if isinstance(command, JSONResponse):
            return command
        if not command.override_mode:
            return JSONResponse({"code": "INVALID_CONFIGURATION_UPDATE"}, status_code=400)
        response = await run_in_threadpool(guarded, lambda: service.start(request.user, command))
        return (
            JSONResponse(
                response.model_dump(mode="json"),
                status_code=202 if response.state == "queued" else 200,
            )
            if isinstance(response, ActionReceipt)
            else response
        )

    # Staging is a separate local command; GET previews never create a hidden plan or review.
    @router.post("/api/configuration/plans", response_model=ConfigurationPlanView)
    async def create_plan(request: Request):
        command = await bounded_command(request, CreateConfigurationPlan, 4096)
        if isinstance(command, JSONResponse):
            return command
        return await run_in_threadpool(guarded, lambda: plans.create(request.user, command))

    # A persisted plan is reloadable only inside its owner's verified workspace/session.
    @router.get("/api/configuration/plans/{identifier}", response_model=ConfigurationPlanView)
    def read_plan(identifier: UUID, request: Request):
        return guarded(lambda: plans.read(request.user, identifier))

    # Saving exact per-category choices never modifies live configuration or starts a job.
    @router.post(
        "/api/configuration/plans/{identifier}/reviews", response_model=ConfigurationPlanView
    )
    async def review_plan(identifier: UUID, request: Request):
        command = await bounded_command(request, SaveConfigurationReview, 4096)
        if isinstance(command, JSONResponse):
            return command
        return await run_in_threadpool(
            guarded, lambda: plans.review(request.user, identifier, command)
        )

    return router
