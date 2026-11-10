"""Session-protected review, registry and lifecycle routes with bounded closed commands."""

from uuid import UUID

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure
from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import ActionReceipt, OrganizationAction
from otm.tenancies.deletion import TenancyDeletionCommand, TenancyDeletionPreview
from otm.tenancies.onboarding_contracts import OnboardingCommand, OnboardingView
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.recovery_network_contracts import RecoveryNetworkPreview, RecoveryNetworkRequest
from otm.tenancies.recovery_password_contracts import RecoveryPasswordRequest, RecoveryPasswordView
from otm.tenancies.required_users import RequiredUsersDirectory
from otm.tenancies.views import (
    PersonWorkflow,
    ReviewDirectory,
    ReviewQuery,
    TenancyDetail,
    TenancyDirectory,
    TenancyQuery,
)

# Keep conflict explanations closed; unknown exception strings cannot become reflected employee
# text.
PUBLIC_CONFLICTS = frozenset(
    {
        "REQUIRED_USERS_CHECK_UNAVAILABLE",
        "RECOVERY_PASSWORD_UNAVAILABLE",
        "RECOVERY_PASSWORD_READ_UNAVAILABLE",
        "RECOVERY_PASSWORD_CONFIRMATION_REQUIRED",
        "RECOVERY_PASSWORD_PREVIEW_CHANGED",
        "RECOVERY_PASSWORD_REQUEST_CLOSED",
        "RECOVERY_PASSWORD_ROTATION_REQUIRED",
        "RECOVERY_NETWORK_REPAIR_BLOCKED",
        "RECOVERY_NETWORK_CONFIRMATION_REQUIRED",
        "RECOVERY_NETWORK_PREVIEW_CHANGED",
        "RESPONSIBILITY_PREVIEW_CHANGED",
        "EMAIL_CONTACT_CONFIGURATION_REQUIRED",
        "PUBLISHED_BASELINE_REQUIRED",
        "ONBOARDING_NOT_AVAILABLE",
        "ONBOARDING_RESPONSIBLE_ADMIN_REQUIRED",
        "ONBOARDING_PREVIEW_CHANGED",
        "ONBOARDING_CONTEXT_CHANGED",
        "ONBOARDING_TARGET_CHANGED",
        "TENANCY_DELETION_UNAVAILABLE",
        "TENANCY_DELETION_CONFIRMATION_REQUIRED",
        "REGISTERED_CHILD_REQUIRED",
        "DESTRUCTIVE_CONFIRMATION_REQUIRED",
        "FORMER_OWNER_DISPOSITION_REQUIRED",
        "RETAIN_MEMBER_REQUIRES_SHARED_TENANCY",
        "EXACT_PERSONAL_IDENTITY_REQUIRED",
        "PERSON_NOT_ABSENT",
        "MANAGER_CONFIRMATION_REQUIRED",
        "SHARED_CONFIRMATION_REQUIRED",
        "ORGANIZATION_PREVIEW_CHANGED",
        "ORGANIZATION_REVIEW_CHANGED",
        "ORGANIZATION_ACTION_UNAVAILABLE",
        "IDENTITY_HAS_PENDING_WORK",
        "IDENTITY_MERGE_PAIR_REQUIRED",
        "IDENTITY_MERGE_PAIR_INVALID",
        "IDENTITY_MERGE_REVIEWS_CHANGED",
        "MERGE_OVERRIDE_CONFLICT",
        "ORGANIZATION_ROOT_PROTECTED",
        "REVIEW_ALL_ASSOCIATIONS",
        "DISTINCT_TENANCY_NAME_REQUIRED",
        "VALID_CREATE_NAME_REQUIRED",
        "PARENT_SUBSCRIBED_REGION_REQUIRED",
        "TENANCY_ALREADY_REGISTERED",
        "EXACT_IMPORT_TARGET_REQUIRED",
        "SIMULATED_CHILD_REQUIRED",
        "CURRENT_TRANSFER_RECIPIENT_REQUIRED",
        "AVAILABLE_SHARED_TENANCY_REQUIRED",
        "EXISTING_PARENT_COMPARTMENT_REQUIRED",
        "ASSOCIATION_PLAN_CHANGED",
        "ACCOUNTABILITY_MAPPING_REQUIRED",
        "LIFECYCLE_PROVIDER_UNAVAILABLE",
        "PERSON_NOT_SOURCE_PRESENT",
        "SIMULATION_ALREADY_FINISHED",
        "SHARED_COMPARTMENT_NAME_REQUIRED",
    }
)


# Route service failures without disclosing SQL, private provider errors or command body contents.
def guarded(call):
    try:
        return call()
    except SessionFailure:
        raise
    except RequestConflict:
        return JSONResponse({"code": "REQUEST_KEY_REUSED"}, status_code=409)
    except OrganizationConflict as error:
        code = str(error)
        if code == "RECOVERY_PASSWORD_READ_UNAVAILABLE":
            return JSONResponse({"code": code}, status_code=503)
        if code in {
            "RESPONSIBILITY_OPERATION_NOT_FOUND",
            "TENANCY_NOT_FOUND",
            "ORGANIZATION_PERSON_NOT_FOUND",
        }:
            return JSONResponse({"code": "WORKSPACE_RECORD_NOT_FOUND"}, status_code=404)
        return JSONResponse(
            {"code": code if code in PUBLIC_CONFLICTS else "ORGANIZATION_WORKFLOW_CHANGED"},
            status_code=409,
        )
    except (ValueError, LifecycleBlocked):
        return JSONResponse({"code": "INVALID_ORGANIZATION_ACTION"}, status_code=400)
    except Exception:
        return JSONResponse({"code": "ORGANIZATION_WORKFLOW_UNAVAILABLE"}, status_code=503)


# Only this last-mile password response is sensitive; errors and metadata remain non-cacheable too.
def private_password_response(result):
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"}
    if isinstance(result, JSONResponse):
        result.headers.update(headers)
        return result
    body = result.model_dump(mode="json") if isinstance(result, RecoveryPasswordView) else result
    return JSONResponse(body, headers=headers)


# All URLs remain behind the existing session/CSRF middleware; none accepts actor or workspace
# input.
def workflow_router(service):
    router = APIRouter()

    # Missing composition disables password capabilities without a secret-store fallback.
    def password_access():
        if service.recovery_passwords is None:
            raise OrganizationConflict("RECOVERY_PASSWORD_UNAVAILABLE")
        return service.recovery_passwords

    # Opening the access dialog reads metadata only and cannot initialize or disclose a secret.
    @router.get("/api/tenancies/{identifier}/administrator-access")
    def administrator_access(identifier: UUID, request: Request):
        return private_password_response(
            guarded(lambda: password_access().view(request.user, identifier))
        )

    # Explicit consent/current authority precede durable audit, notices and the due rotation task.
    @router.post("/api/tenancies/{identifier}/administrator-access/password")
    async def recovery_password(identifier: UUID, request: Request):
        from otm.configuration.rollout_http import bounded_command

        command = await bounded_command(request, RecoveryPasswordRequest, 4096)
        if isinstance(command, JSONResponse):
            return private_password_response(command)
        result = await run_in_threadpool(
            guarded,
            lambda: password_access().disclose(request.user, identifier, command),
        )
        return private_password_response(result)

    # A durable inbox/history page reads only this session's organization and registry.
    @router.get("/api/organization/reviews", response_model=ReviewDirectory)
    def reviews(
        request: Request,
        category: str = "actionable",
        query: str = "",
        page: int = 1,
        page_size: int = 10,
        sort: str = "first_seen_at",
        direction: str = "asc",
    ):
        return guarded(
            lambda: service.reviews(
                request.user,
                ReviewQuery(
                    category=category,
                    query=query,
                    page=page,
                    page_size=page_size,
                    sort=sort,
                    direction=direction,
                ),
            )
        )

    # Explicit self-claim changes responsibility only; no provider dispatch or ownership transfer.
    @router.post("/api/operations/{identifier}/responsibility", response_model=ActionReceipt)
    async def responsibility(identifier: UUID, request: Request):
        from otm.configuration.rollout_http import bounded_command
        from otm.operations.responsibility import ResponsibilityCommand, take_responsibility

        command = await bounded_command(request, ResponsibilityCommand, 4096)
        if isinstance(command, JSONResponse):
            return command
        return await run_in_threadpool(
            guarded, lambda: take_responsibility(service, request.user, identifier, command)
        )

    # Fresh per-person previews make every association and required confirmation visible
    # before admission.
    @router.get("/api/organization/people/{identifier}/workflow", response_model=PersonWorkflow)
    def preview(identifier: UUID, request: Request, review_id: UUID | None = None):
        return guarded(lambda: service.preview(request.user, identifier, review_id))

    # Limit the whole JSON body before parsing; clients cannot submit SDK arguments or default
    # users.
    @router.post(
        "/api/organization/actions",
        response_model=ActionReceipt,
        responses={202: {"model": ActionReceipt, "description": "Durably queued lifecycle work"}},
    )
    async def act(request: Request):
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise ValueError("JSON_REQUIRED")
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > 32768:
                    raise ValueError("ORGANIZATION_ACTION_TOO_LARGE")
                data.extend(chunk)
            command = OrganizationAction.model_validate_json(bytes(data))
        except ValueError:
            return JSONResponse({"code": "INVALID_ORGANIZATION_ACTION"}, status_code=400)
        result = await run_in_threadpool(guarded, lambda: service.act(request.user, command))
        if isinstance(result, ActionReceipt) and result.state == "queued":
            return JSONResponse(result.model_dump(mode="json"), status_code=202)
        return result

    # A closed nonsecret wizard projection is distinct from raw operation history.
    @router.get("/api/tenancy-onboarding/{identifier}", response_model=OnboardingView)
    def onboarding(identifier: UUID, request: Request):
        return guarded(lambda: service.onboarding(request.user, identifier))

    # The handoff body is bounded before parsing and cannot carry arbitrary credentials/SDK options.
    @router.post("/api/tenancy-onboarding/{identifier}", response_model=ActionReceipt)
    async def onboarding_action(identifier: UUID, request: Request):
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise ValueError("JSON_REQUIRED")
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > 4096:
                    raise ValueError("HANDOFF_TOO_LARGE")
                data.extend(chunk)
            command = OnboardingCommand.model_validate_json(bytes(data))
        except ValueError:
            return JSONResponse({"code": "INVALID_ONBOARDING_ACTION"}, status_code=400)
        result = await run_in_threadpool(
            guarded, lambda: service.onboarding_action(request.user, identifier, command)
        )
        if isinstance(result, ActionReceipt) and result.state == "queued":
            return JSONResponse(result.model_dump(mode="json"), status_code=202)
        return result

    # Preview the complete registered child membership without accepting arbitrary affected
    # identities.
    @router.get(
        "/api/tenancies/{identifier}/deletion-preview", response_model=TenancyDeletionPreview
    )
    def deletion_preview(identifier: UUID, request: Request):
        return guarded(lambda: service.deletion_preview(request.user, identifier))

    # All target membership/owner facts are server-derived under the normal session and CSRF guards.
    @router.post("/api/tenancy-deletions", response_model=ActionReceipt)
    async def delete_tenancy(request: Request):
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise ValueError("JSON_REQUIRED")
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > 4096:
                    raise ValueError("DELETION_TOO_LARGE")
                data.extend(chunk)
            command = TenancyDeletionCommand.model_validate_json(bytes(data))
        except ValueError:
            return JSONResponse({"code": "INVALID_TENANCY_DELETION"}, status_code=400)
        result = await run_in_threadpool(
            guarded, lambda: service.delete_tenancy(request.user, command)
        )
        if isinstance(result, ActionReceipt) and result.state == "queued":
            return JSONResponse(result.model_dump(mode="json"), status_code=202)
        return result

    # Inventory search/sort/pagination controls are allowlisted independently of SQL construction.
    @router.get("/api/tenancies", response_model=TenancyDirectory)
    def tenancies(
        request: Request,
        shared_only: bool = False,
        page: int = 1,
        page_size: int = 10,
        query: str = "",
        sort: str = "name",
        direction: str = "asc",
    ):
        return guarded(
            lambda: service.tenancies(
                request.user,
                TenancyQuery(
                    page=page,
                    page_size=page_size,
                    query=query,
                    sort=sort,
                    direction=direction,
                    shared_only=shared_only,
                ),
            )
        )

    # Read account identity records only; no URL/body can select workspace, credentials or probes.
    @router.get("/api/tenancies/{identifier}/required-users", response_model=RequiredUsersDirectory)
    def required_users(identifier: UUID, request: Request):
        return guarded(lambda: service.required_users(request.user, identifier))

    # Reads are queued only by an authenticated CSRF-protected command with one request UUID.
    @router.post(
        "/api/tenancies/{identifier}/required-users/check",
        response_model=ActionReceipt,
        status_code=202,
    )
    async def check_required_users(identifier: UUID, request: Request):
        from otm.configuration.rollout_http import bounded_command

        command = await bounded_command(request, PresenceCheckRequest, 4096)
        if isinstance(command, JSONResponse):
            return command
        if service.presence_checks is None:
            return JSONResponse({"code": "REQUIRED_USERS_CHECK_UNAVAILABLE"}, status_code=409)
        return await run_in_threadpool(
            guarded, lambda: service.presence_checks.start(request.user, identifier, command)
        )

    # A foreign tenancy is indistinguishable from an unknown local identifier.
    @router.get(
        "/api/tenancies/{identifier}/recovery-network-preview",
        response_model=RecoveryNetworkPreview,
    )
    def recovery_network_preview(identifier: UUID, request: Request):
        if service.recovery_network_repairs is None:
            return JSONResponse({"code": "RECOVERY_NETWORK_REPAIR_BLOCKED"}, status_code=409)
        return guarded(lambda: service.recovery_network_repairs.preview(request.user, identifier))

    # Explicit security-change consent and an exact preview are required even for direct API calls.
    @router.post(
        "/api/tenancies/{identifier}/recovery-network-repair",
        response_model=ActionReceipt,
        status_code=202,
    )
    async def recovery_network_repair(identifier: UUID, request: Request):
        from otm.configuration.rollout_http import bounded_command

        command = await bounded_command(request, RecoveryNetworkRequest, 4096)
        if isinstance(command, JSONResponse):
            return command
        if service.recovery_network_repairs is None:
            return JSONResponse({"code": "RECOVERY_NETWORK_REPAIR_BLOCKED"}, status_code=409)
        return await run_in_threadpool(
            guarded,
            lambda: service.recovery_network_repairs.start(request.user, identifier, command),
        )

    # Detail remains a retained database projection, never a provider or credential action.
    @router.get("/api/tenancies/{identifier}", response_model=TenancyDetail)
    def detail(identifier: UUID, request: Request):
        return guarded(lambda: service.tenancy_detail(request.user, identifier))

    return router
