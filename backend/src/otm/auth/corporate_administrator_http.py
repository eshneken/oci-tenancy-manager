"""Private browser commands for qualified corporate administrator provisioning."""

from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from otm.auth.administrators import AdministratorFailure, RevokeAdministrator
from otm.auth.corporate_enrollment import CorporateLookup


# Bound buffered JSON and map parse failures to a fixed public code.
async def administrator_body(request, model):
    try:
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise ValueError()
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 4096:
                raise ValueError()
            data.extend(chunk)
        return model.model_validate_json(bytes(data))
    except ValueError:
        raise AdministratorFailure(400, "INVALID_ADMINISTRATOR_COMMAND") from None


# Suppress private provider and database failures at the browser boundary.
async def administrator_action(action, *arguments):
    try:
        return await run_in_threadpool(action, *arguments)
    except AdministratorFailure:
        raise
    except PermissionError:
        raise AdministratorFailure(403, "ADMINISTRATOR_REQUIRED") from None
    except Exception:
        raise AdministratorFailure(503, "ADMINISTRATOR_SERVICE_UNAVAILABLE") from None


# Mount provider-writing routes only when the app explicitly injects an adapter.
def corporate_administrator_router(onboarding):
    from otm.storage.corporate_administrators import ConfirmAdministrator

    router = APIRouter(prefix="/api/administrators")

    # Preview only verified identity fields for the authenticated actor.
    @router.post("/onboarding/preview")
    async def preview(request: Request):
        lookup = await administrator_body(request, CorporateLookup)
        return await administrator_action(onboarding.preview, request.user, lookup)

    # Require the previous review fingerprint and a freshly authorized actor.
    @router.post("/onboarding/confirm")
    async def confirm(request: Request):
        command = await administrator_body(request, ConfirmAdministrator)
        return await administrator_action(onboarding.confirm, request.user, command)

    # Permit cleanup only after local revocation has committed at the same revision.
    @router.post("/{identifier}/group-cleanup")
    async def cleanup(identifier: UUID, request: Request):
        command = await administrator_body(request, RevokeAdministrator)
        return await administrator_action(
            onboarding.cleanup, request.user, identifier, command.expected_revision
        )

    return router
