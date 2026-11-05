"""Session/CSRF-protected cost refresh commands; dashboard GETs perform no provider reads."""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure
from otm.configuration.rollout_http import bounded_command
from otm.financial.contracts import CostRefreshReceipt, CostRefreshRequest
from otm.financial.service import CostConflict
from otm.storage.admission import RequestConflict


# Fixed conflict codes avoid reflecting malformed CSV/SDK/SQL content into an administrative UI.
def guarded(call):
    try:
        return call()
    except SessionFailure:
        raise
    except (CostConflict, RequestConflict) as error:
        code = str(error)
        known = {
            "COST_TARGET_NOT_FOUND",
            "COST_CONTEXT_UNAVAILABLE",
            "NO_COST_REFRESH_TARGETS",
            "REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT",
        }
        return JSONResponse(
            {"code": code if code in known else "COST_REFRESH_BLOCKED"},
            status_code=404 if code == "COST_TARGET_NOT_FOUND" else 409,
        )
    except ValueError:
        return JSONResponse({"code": "INVALID_COST_REFRESH"}, status_code=400)
    except Exception:
        return JSONResponse({"code": "COST_SERVICE_UNAVAILABLE"}, status_code=503)


# Existing same-origin middleware owns authentication and command header/origin validation.
def cost_router(service):
    router = APIRouter()

    # Scope is optional child-or-fleet; neither endpoints nor credentials are client parameters.
    @router.post("/api/costs/refresh", response_model=CostRefreshReceipt, status_code=202)
    async def refresh(request: Request):
        command = await bounded_command(request, CostRefreshRequest, 4096)
        if isinstance(command, JSONResponse):
            return command
        return await run_in_threadpool(guarded, lambda: service.start(request.user, command))

    return router
