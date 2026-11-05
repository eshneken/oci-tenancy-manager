"""Session-protected mapping endpoints with bounded bodies and closed public diagnostics."""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure
from otm.organization.mapping_contracts import (
    MappingApply,
    MappingPreview,
    MappingRequest,
    MappingSettings,
)
from otm.storage.organization import OrganizationConflict


# All commands use existing session/same-origin protections and never accept workspace or policy.
def mapping_router(service):
    router = APIRouter()

    # Project authorized current settings; a read never seeds configuration from the legacy file.
    @router.get("/api/organization/mapping", response_model=MappingSettings)
    def read(request: Request):
        return guarded(lambda: service.read(request.user))

    # Bound JSON before validating allowed fields and email syntax.
    async def command(request, apply, page):
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"code": "MAPPING_JSON_REQUIRED"}, status_code=415)
            content = bytearray()
            async for chunk in request.stream():
                if len(content) + len(chunk) > 65536:
                    return JSONResponse({"code": "MAPPING_TOO_LARGE"}, status_code=413)
                content.extend(chunk)
            model = MappingApply if apply else MappingRequest
            value = model.model_validate_json(content)
            return await run_in_threadpool(
                guarded,
                lambda: (
                    service.apply(request.user, value)
                    if apply
                    else service.preview(request.user, value, page)
                ),
            )
        except SessionFailure:
            raise
        except ValueError:
            return JSONResponse({"code": "INVALID_MAPPING_SETTINGS"}, status_code=400)

    # Preview is a nonmutating command; pagination never changes its candidate/revision binding.
    @router.post("/api/organization/mapping/preview", response_model=MappingPreview)
    async def preview(request: Request, page: int = 1):
        return await command(request, False, page)

    # Apply recomputes under the workspace lock rather than trusting browser-rendered impacts.
    @router.post("/api/organization/mapping/apply", response_model=MappingSettings)
    async def apply(request: Request):
        return await command(request, True, 1)

    return router


# Do not echo untrusted validation input, SQL/provider exception strings or private configurations.
def guarded(call):
    try:
        return call()
    except SessionFailure:
        raise
    except OrganizationConflict as failure:
        codes = {
            "MAPPING_PREVIEW_CHANGED",
            "MAPPING_ROOT_FIXED",
            "MAPPING_SEGMENT_CHANGED",
            "MAPPING_SETUP_UNAVAILABLE",
            "MAPPING_INVALID_GRAPH",
            "MAPPING_PENDING_WORK",
        }
        return JSONResponse(
            {"code": str(failure) if str(failure) in codes else "MAPPING_CHANGED"}, status_code=409
        )
    except ValueError:
        return JSONResponse({"code": "INVALID_MAPPING_SETTINGS"}, status_code=400)
    except Exception:
        return JSONResponse({"code": "MAPPING_UNAVAILABLE"}, status_code=503)
