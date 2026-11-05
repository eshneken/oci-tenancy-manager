"""Session/same-origin protected draft authoring with bounded input and nonreflective errors."""

import json

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure
from otm.configuration.contracts import (
    BaselineDirectory,
    BaselineQuery,
    BaselineVersion,
    PublishBaseline,
    SaveBaselineDraft,
)
from otm.providers.baseline import PublicationUnavailable
from otm.storage.organization import OrganizationConflict


# Map expected conflicts without exposing author statements, private exceptions or SQL.
def guarded(call):
    try:
        return call()
    except SessionFailure:
        raise
    except OrganizationConflict as error:
        return JSONResponse(
            {
                "code": "BASELINE_ORGANIZATION_REQUIRED"
                if str(error) == "ORGANIZATION_NOT_CONFIGURED"
                else "BASELINE_DRAFT_CHANGED"
            },
            status_code=409,
        )
    except PublicationUnavailable:
        return JSONResponse({"code": "BASELINE_PUBLICATION_UNAVAILABLE"}, status_code=503)
    except ValueError:
        return JSONResponse({"code": "INVALID_BASELINE_DRAFT"}, status_code=400)
    except Exception:
        return JSONResponse({"code": "BASELINE_UNAVAILABLE"}, status_code=503)


# Workspace, publisher identity, mode and provider scope remain server-owned.
def baseline_router(service):
    router = APIRouter()

    # Read a scoped draft, latest publication, paged history and optional exact version.
    @router.get("/api/configuration/baselines", response_model=BaselineDirectory)
    def read(request: Request, page: int = 1, page_size: int = 10, baseline_id: str | None = None):
        return guarded(
            lambda: service.read(
                request.user,
                BaselineQuery.model_validate_json(
                    json.dumps({"page": page, "page_size": page_size, "baseline_id": baseline_id})
                ),
            )
        )

    # Stream-limit before parsing; all commands retain fixed nonreflective errors.
    async def command(request, model, execute):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"code": "BASELINE_JSON_REQUIRED"}, status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 2097152:
                return JSONResponse({"code": "BASELINE_TOO_LARGE"}, status_code=413)
            body.extend(chunk)
        try:
            parsed = model.model_validate_json(body)
        except ValueError:
            return JSONResponse({"code": "INVALID_BASELINE_DRAFT"}, status_code=400)
        return await run_in_threadpool(guarded, lambda: execute(request.user, parsed))

    # Recipe editing remains synchronous and never publishes implicitly.
    @router.post("/api/configuration/baselines/draft", response_model=BaselineVersion)
    async def save(request: Request):
        return await command(request, SaveBaselineDraft, service.save)

    # Publish only an exact saved version, using the host's explicitly injected local qualifier.
    @router.post("/api/configuration/baselines/publish", response_model=BaselineVersion)
    async def publish(request: Request):
        return await command(request, PublishBaseline, service.publish)

    return router
