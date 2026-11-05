"""Bounded same-origin administrator routes for read-only configuration check workflows."""

from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.configuration.drift_contracts import (
    ConfigurationCheckRequest,
    ConfigurationCheckSummary,
    ConfigurationDriftDirectory,
    ConfigurationDriftQuery,
)
from otm.configuration.rollout_http import bounded_command, guarded
from otm.tenancies.contracts import ActionReceipt


# Session/Origin/custom-header middleware remains mandatory; these routes never select a workspace.
def drift_router(service):
    router = APIRouter()

    # Both tabs are projections; reading them cannot enqueue checks or clear existing findings.
    @router.get("/api/configuration/drift", response_model=ConfigurationDriftDirectory)
    def directory(
        request: Request,
        tab: str = "confirmed",
        query: str = "",
        state: str = "all",
        tenancy_id: UUID | None = None,
        sort: str = "name",
        direction: str = "asc",
        page: int = 1,
        page_size: int = 10,
    ):
        return guarded(
            lambda: service.directory(
                request.user,
                ConfigurationDriftQuery(
                    tab=tab,
                    query=query,
                    state=state,
                    tenancy_id=tenancy_id,
                    sort=sort,
                    direction=direction,
                    page=page,
                    page_size=page_size,
                ),
            )
        )

    # A direct child URL always resolves that exact scoped record, never the first current result.
    @router.get("/api/configuration/drift/{identifier}", response_model=ConfigurationCheckSummary)
    def detail(identifier: UUID, request: Request):
        return guarded(lambda: service.detail(request.user, identifier))

    # The only accepted mutation queues a read; it contains no desired values or provider
    # credentials.
    @router.post(
        "/api/configuration/checks",
        response_model=ActionReceipt,
        status_code=202,
        responses={200: {"model": ActionReceipt}},
    )
    async def start(request: Request):
        command = await bounded_command(request, ConfigurationCheckRequest, 4096)
        if isinstance(command, JSONResponse):
            return command
        response = await run_in_threadpool(guarded, lambda: service.start(request.user, command))
        return (
            JSONResponse(
                response.model_dump(mode="json"),
                status_code=202 if response.state == "queued" else 200,
            )
            if isinstance(response, ActionReceipt)
            else response
        )

    return router
