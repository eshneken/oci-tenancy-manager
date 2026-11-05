"""Compose verified sessions and explicitly configured administrative/workflow services."""

import json
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import FileResponse, JSONResponse, Response

from otm.audit.contracts import AuditDirectory, AuditExportQuery, AuditQuery
from otm.auth.administrators import (
    AdministratorDirectory,
    AdministratorFailure,
    AdministratorQuery,
    RevokeAdministrator,
)
from otm.auth.contracts import SessionView
from otm.auth.http import (
    COOKIE_NAME,
    BrowserBoundaryMiddleware,
    BrowserSettings,
    CookieSessionBackend,
    authentication_error,
    clear_session_cookie,
    session_handle,
)
from otm.auth.local import LocalAuthFailure, LocalLogin, LocalSignIn
from otm.auth.service import AdminPrincipal, SessionFailure, SessionService
from otm.email_policy import EmailPolicyView, MailPolicy
from otm.operations.contracts import Acceptance
from otm.operations.sandbox import (
    InspectionSubmission,
    SandboxAdmission,
    SandboxCatalog,
    SandboxUnavailable,
)
from otm.operations.views import OperationDetail, OperationDirectory, OperationQuery
from otm.organization.web import OrganizationWeb, organization_router
from otm.settings import BrandingSettings, BrandingView
from otm.storage.administrators import SqlAdministratorStore
from otm.storage.admission import RequestConflict
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import AuditExportTooLarge, SqlAuditExport
from otm.storage.operation_directory import SqlOperationDirectory


# Process-only health response; it makes no database, OCI or readiness guarantee.
class Liveness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: str = "ok"


# Build liveness, optionally adding the explicitly configured session boundary.
#
# No prototype router, reset endpoint, local actor or simulated-success command is mounted.
# Sign-in and provider workflows require explicit host dependencies; SSO is not composed.
def create_app(
    sessions: SessionService | None = None,
    browser: BrowserSettings | None = None,
    login: LocalLogin | None = None,
    administrators: SqlAdministratorStore | None = None,
    ui_dist: Path | None = None,
    operations: SqlOperationDirectory | None = None,
    sandbox: SandboxAdmission | None = None,
    audit_history: SqlAuditDirectory | None = None,
    audit_export: SqlAuditExport | None = None,
    branding: BrandingSettings | None = None,
    organization: OrganizationWeb | None = None,
    baseline_qualifier=None,
    configuration_rollouts=None,
    configuration_checks=None,
    email_policy: MailPolicy | None = None,
) -> FastAPI:
    if (
        configuration_rollouts is not None or configuration_checks is not None
    ) and organization is None:
        raise ValueError("CONFIGURATION_ROLLOUT_REQUIRES_ORGANIZATION")
    if baseline_qualifier is not None and organization is None:
        raise ValueError("BASELINE_PUBLICATION_REQUIRES_ORGANIZATION")
    if (sessions is None) != (browser is None):
        raise ValueError("Both session authority and browser settings are required")
    if login is not None and sessions is None:
        raise ValueError("LOCAL_LOGIN_REQUIRES_SESSION_BOUNDARY")
    if (
        email_policy is not None
        or administrators is not None
        or ui_dist is not None
        or operations is not None
        or sandbox is not None
        or audit_history is not None
        or audit_export is not None
        or organization is not None
    ) and sessions is None:
        raise ValueError("ADMINISTRATION_UI_REQUIRES_SESSION_BOUNDARY")
    if branding is not None and ui_dist is None:
        raise ValueError("BRANDING_REQUIRES_PUBLIC_UI")
    branding = BrandingSettings.model_validate(branding or BrandingSettings())
    app = FastAPI(
        title="OCI Tenancy Manager",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Confirm this process can serve requests without accessing external systems.
    @app.get("/health/live", response_model=Liveness, include_in_schema=False)
    def live() -> Liveness:
        return Liveness()

    if sessions is not None:
        # Normalize fresh command-boundary failures without exposing provider details.
        @app.exception_handler(SessionFailure)
        async def authorization_failure(request: Request, failure: SessionFailure):
            response = JSONResponse({"code": failure.code}, status_code=failure.status)
            if failure.status == 401:
                clear_session_cookie(response)
            return response

        app.add_middleware(
            AuthenticationMiddleware,
            backend=CookieSessionBackend(
                sessions, allow_local_login=login is not None, public_ui=ui_dist is not None
            ),
            on_error=authentication_error,
        )
        app.add_middleware(
            BrowserBoundaryMiddleware, settings=browser, public_ui=ui_dist is not None
        )

        # Expose only current authorized UI context, never session hashes, claims or tokens.
        @app.get("/api/session", response_model=SessionView)
        def session_view(request: Request):
            principal = request.user
            if not isinstance(principal, AdminPrincipal):
                return JSONResponse({"code": "AUTHENTICATION_REQUIRED"}, status_code=401)
            return SessionView(
                workspace_id=principal.session.workspace_id,
                display_name=principal.session.display_snapshot.display_name,
                expires_at=principal.session.expires_at,
            )

        # Routing destinations are administrative context, never a public branding/login response.
        @app.get("/api/email-policy", response_model=EmailPolicyView)
        def delivery_policy(request: Request):
            policy = email_policy or MailPolicy()
            return EmailPolicyView(
                environment=policy.environment,
                redirected=policy.email_override is not None,
                effective_test_email=policy.email_override,
            )

        # This explicit activity endpoint is separate from polling and ordinary read-only requests.
        @app.post("/api/session/activity", response_model=SessionView)
        def activity(request: Request):
            principal = sessions.activity(request.user)
            return SessionView(
                workspace_id=principal.session.workspace_id,
                display_name=principal.session.display_snapshot.display_name,
                expires_at=principal.session.expires_at,
            )

        # Logout requires same-origin CSRF guards but no functioning SSO or active admin role.
        @app.post("/api/logout", status_code=204)
        def logout(request: Request):
            response = Response(status_code=204)
            try:
                try:
                    handle = session_handle(request.headers)
                except SessionFailure:
                    handle = None
                sessions.logout(handle)
            except SessionFailure as failure:
                response = JSONResponse({"code": failure.code}, status_code=failure.status)
            clear_session_cookie(response)
            return response

    if login is not None:
        # Bound credential input before decoding; never emit framework errors containing
        # factor values.
        @app.post("/api/auth/local/sign-in", response_model=SessionView)
        async def local_sign_in(request: Request):
            try:
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 4096:
                        raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED")
                    body.extend(chunk)
                try:
                    command = LocalSignIn.model_validate_json(bytes(body))
                except ValueError:
                    raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED") from None
                try:
                    old = session_handle(request.headers)
                except SessionFailure:
                    old = None
                issued = await run_in_threadpool(login.sign_in, command, old)
                response = JSONResponse(
                    SessionView(
                        workspace_id=issued.session.workspace_id,
                        display_name=issued.session.display_snapshot.display_name,
                        expires_at=issued.session.expires_at,
                    ).model_dump(mode="json")
                )
                response.set_cookie(
                    COOKIE_NAME,
                    issued.handle.get_secret_value(),
                    secure=True,
                    httponly=True,
                    samesite="lax",
                    path="/",
                    max_age=int(
                        (issued.session.expires_at - issued.session.created_at).total_seconds()
                    ),
                )
                return response
            except LocalAuthFailure as error:
                return JSONResponse({"code": error.code}, status_code=error.status)
            except Exception:
                return JSONResponse({"code": "LOCAL_AUTHENTICATION_UNAVAILABLE"}, status_code=503)

    if administrators is not None:
        # Normalize storage failures without exposing search values, SQL or identity metadata.
        @app.exception_handler(AdministratorFailure)
        async def administrator_error(request: Request, error: AdministratorFailure):
            return JSONResponse({"code": error.code}, status_code=error.status)

        # Middleware and the fresh boundary determine scope; query inputs cannot choose a
        # workspace.
        @app.get("/api/administrators", response_model=AdministratorDirectory)
        def administrator_directory(
            request: Request,
            page: int = 1,
            page_size: int = 10,
            sort: str = "display_name",
            direction: str = "asc",
            query: str = "",
        ):
            principal = request.user
            sessions.require_admin(principal, principal.session.workspace_id)
            try:
                options = AdministratorQuery(
                    page=page, page_size=page_size, sort=sort, direction=direction, query=query
                )
            except ValueError:
                return JSONResponse({"code": "INVALID_DIRECTORY_QUERY"}, status_code=400)
            try:
                return administrators.directory(principal.session.workspace_id, options)
            except Exception:
                return JSONResponse({"code": "ADMINISTRATOR_SERVICE_UNAVAILABLE"}, status_code=503)

        # Reuse the existing transactional protected-account/revision/authority checks.
        @app.post("/api/administrators/{identifier}/revoke")
        async def revoke_administrator(identifier: UUID, request: Request):
            try:
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise ValueError("INVALID_COMMAND")
                data = bytearray()
                async for chunk in request.stream():
                    if len(data) + len(chunk) > 4096:
                        raise ValueError("INVALID_COMMAND")
                    data.extend(chunk)
                body = RevokeAdministrator.model_validate_json(bytes(data))
            except ValueError:
                return JSONResponse({"code": "INVALID_ADMINISTRATOR_COMMAND"}, status_code=400)
            return await run_in_threadpool(
                administrators.revoke, request.user, identifier, body.expected_revision
            )

    if sandbox is not None:
        # This route exists only with explicit local simulator composition and current admin
        # authority.
        @app.get("/api/inspection-sandbox", response_model=SandboxCatalog)
        def inspection_sandbox(request: Request):
            try:
                return sandbox.catalog(request.user)
            except SessionFailure:
                raise
            except Exception:
                return JSONResponse({"code": "INSPECTION_SANDBOX_UNAVAILABLE"}, status_code=503)

        # Accept only a bounded child/key command; never trust browser actor/workspace/policy
        # fields.
        @app.post("/api/operations/inspect", response_model=Acceptance, status_code=202)
        async def submit_inspection(request: Request):
            try:
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise ValueError("INVALID_COMMAND")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 4096:
                        raise ValueError("INVALID_COMMAND")
                    body.extend(chunk)
                command = InspectionSubmission.model_validate_json(bytes(body))
            except ValueError:
                return JSONResponse({"code": "INVALID_INSPECTION_COMMAND"}, status_code=400)
            try:
                return await run_in_threadpool(sandbox.submit, request.user, command)
            except SessionFailure:
                raise
            except SandboxUnavailable:
                return JSONResponse({"code": "INSPECTION_SUBMISSION_UNAVAILABLE"}, status_code=503)
            except RequestConflict:
                return JSONResponse({"code": "REQUEST_KEY_REUSED"}, status_code=409)
            except ValueError:
                return JSONResponse({"code": "INVALID_INSPECTION_COMMAND"}, status_code=400)
            except Exception:
                return JSONResponse({"code": "INSPECTION_SUBMISSION_UNAVAILABLE"}, status_code=503)

    if audit_history is not None:
        # Every administrator sees only the session workspace; date bounds are UTC and half-open.
        @app.get("/api/audit-history", response_model=AuditDirectory)
        def audit_directory(
            request: Request,
            page: int = 1,
            page_size: int = 10,
            sort: str = "at",
            direction: str = "desc",
            category: str = "",
            query: str = "",
            from_at: str | None = None,
            to_at: str | None = None,
        ):
            principal = request.user
            sessions.require_admin(principal, principal.session.workspace_id)
            try:
                options = AuditQuery.model_validate_json(
                    json.dumps(
                        dict(
                            page=page,
                            page_size=page_size,
                            sort=sort,
                            direction=direction,
                            category=category,
                            query=query,
                            from_at=from_at,
                            to_at=to_at,
                        )
                    )
                )
            except ValueError:
                return JSONResponse({"code": "INVALID_AUDIT_QUERY"}, status_code=400)
            try:
                return audit_history.directory(principal.session.workspace_id, options)
            except Exception:
                return JSONResponse({"code": "AUDIT_SERVICE_UNAVAILABLE"}, status_code=503)

    if audit_export is not None:
        # A bounded POST records preparation before disclosure.
        # Ordinary same-origin CSRF and current-session guards remain required.
        @app.post("/api/audit-history/export")
        async def export_audit_history(request: Request):
            principal = request.user
            sessions.require_admin(principal, principal.session.workspace_id)
            try:
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise ValueError("INVALID_AUDIT_QUERY")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 4096:
                        raise ValueError("INVALID_AUDIT_QUERY")
                    body.extend(chunk)
                options = AuditExportQuery.model_validate_json(bytes(body))
            except ValueError:
                return JSONResponse({"code": "INVALID_AUDIT_QUERY"}, status_code=400)
            try:
                content = await run_in_threadpool(audit_export.export, principal, options)
                return Response(
                    content=content,
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="audit-history.csv"'},
                )
            except AuditExportTooLarge:
                return JSONResponse({"code": "AUDIT_EXPORT_TOO_LARGE"}, status_code=413)
            except SessionFailure:
                raise
            except Exception:
                return JSONResponse({"code": "AUDIT_EXPORT_UNAVAILABLE"}, status_code=503)

    if configuration_rollouts is not None:
        from otm.configuration.rollout_http import rollout_router

        app.include_router(rollout_router(configuration_rollouts))

    if configuration_checks is not None:
        from otm.configuration.drift_http import drift_router

        app.include_router(drift_router(configuration_checks))

    if operations is not None:
        # Session-derived scope and fresh grants govern every read; URLs cannot choose a workspace.
        @app.get("/api/operations", response_model=OperationDirectory)
        def operation_directory(
            request: Request,
            page: int = 1,
            page_size: int = 10,
            sort: str = "accepted_at",
            direction: str = "desc",
            state: str = "",
            query: str = "",
        ):
            principal = request.user
            sessions.require_admin(principal, principal.session.workspace_id)
            try:
                options = OperationQuery(
                    page=page,
                    page_size=page_size,
                    sort=sort,
                    direction=direction,
                    state=state,
                    query=query,
                )
            except ValueError:
                return JSONResponse({"code": "INVALID_OPERATION_QUERY"}, status_code=400)
            try:
                result = operations.directory(principal.session.workspace_id, options)
                if configuration_rollouts is not None:
                    result = result.model_copy(
                        update={
                            "attention_count": result.attention_count
                            + configuration_rollouts.actionable_count(principal)
                        }
                    )
                return result
            except Exception:
                return JSONResponse({"code": "OPERATION_SERVICE_UNAVAILABLE"}, status_code=503)

        # A foreign operation is indistinguishable from an unknown ID; expose no raw evidence JSON.
        @app.get("/api/operations/{identifier}", response_model=OperationDetail)
        def operation_detail(identifier: UUID, request: Request):
            principal = request.user
            sessions.require_admin(principal, principal.session.workspace_id)
            try:
                detail = operations.detail(
                    principal.session.workspace_id, identifier, principal.actor.key
                )
                if detail is None:
                    return JSONResponse({"code": "OPERATION_NOT_FOUND"}, status_code=404)
                return detail
            except Exception:
                return JSONResponse({"code": "OPERATION_SERVICE_UNAVAILABLE"}, status_code=503)

    if organization is not None:
        from otm.configuration.http import baseline_router
        from otm.configuration.service import BaselineAuthoring

        app.include_router(
            baseline_router(BaselineAuthoring(organization.store, baseline_qualifier))
        )

        app.include_router(organization_router(organization))

    if ui_dist is not None:
        # Only a deliberately supplied built asset directory is served; no project
        # directory listing.
        if (
            ui_dist.is_symlink()
            or (ui_dist / "assets").is_symlink()
            or (ui_dist / "index.html").is_symlink()
            or not (ui_dist / "index.html").is_file()
            or not (ui_dist / "assets").is_dir()
        ):
            raise ValueError("BUILT_FRONTEND_REQUIRED")
        app.mount("/assets", StaticFiles(directory=ui_dist / "assets"), name="assets")
        branding_assets = ui_dist / "branding-assets"
        if branding_assets.is_symlink():
            raise ValueError("INVALID_BRANDING_ASSETS")
        for asset in (branding.logo_url, branding.icon_url):
            if asset is not None:
                path = ui_dist / asset.lstrip("/")
                if path.is_symlink() or not path.is_file():
                    raise ValueError("INVALID_BRANDING_ASSETS")
        if branding_assets.is_dir():
            app.mount(
                "/branding-assets", StaticFiles(directory=branding_assets), name="branding-assets"
            )

        # Public sign-in identity contains only allowlisted presentation fields, never settings.
        @app.get("/api/branding", response_model=BrandingView)
        def instance_branding():
            return BrandingView(**branding.model_dump())

        # The public shell contains no user data; every directory/session API keeps its
        # normal guards.
        @app.get("/")
        @app.get("/login")
        @app.get("/tenancies")
        @app.get("/tenancies/{identifier}")
        @app.get("/organization")
        @app.get("/organization/drift")
        @app.get("/organization-mapping")
        @app.get("/configuration/drift")
        @app.get("/configuration/drift/{identifier}")
        @app.get("/configuration")
        @app.get("/administrators")
        @app.get("/audit-history")
        @app.get("/operations")
        @app.get("/operations/{identifier}")
        def application_shell():
            return FileResponse(ui_dist / "index.html", media_type="text/html")

    return app
