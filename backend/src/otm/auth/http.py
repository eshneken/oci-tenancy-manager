"""Starlette request authentication and same-origin browser guards; no SSO/session issuance."""

import re
from urllib.parse import urlsplit

from starlette.authentication import AuthCredentials, AuthenticationBackend, AuthenticationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from otm.auth.service import SessionFailure, SessionService
from otm.contracts import Contract, HttpsOrigin

COOKIE_NAME = "__Host-otm_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# One explicit public HTTPS origin; never derive authorization/origin policy from a request.
class BrowserSettings(Contract):
    # Canonical HTTPS origin, 1–256 characters; exact Host/Origin guard for all non-health paths.
    # No credentials, path, query, fragment or explicit default port; never inferred from requests.
    public_origin: HttpsOrigin


# Expose only a fixed code/status accepted by the middleware error handler.
class BoundaryAuthenticationError(AuthenticationError):
    # Do not chain or retain provider exceptions, cookies or raw claims.
    def __init__(self, failure: SessionFailure):
        super().__init__(failure.code)
        self.status, self.code = failure.status, failure.code


# Normalize authentication errors without reflecting private request/provider details.
def authentication_error(connection, error):
    response = JSONResponse({"code": error.code}, status_code=error.status)
    if error.status == 401:
        clear_session_cookie(response)
    return response


# Extract only one bounded target cookie; errors never include the presented bearer value.
def session_handle(headers: Headers) -> str:
    raw = ";".join(headers.getlist("cookie"))
    if len(raw) > 4096:
        raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
    values = []
    for item in raw.split(";"):
        key, separator, value = item.strip().partition("=")
        if key.strip() == COOKIE_NAME:
            values.append(value.strip() if separator else "")
    if len(values) != 1:
        raise SessionFailure(401, "AUTHENTICATION_REQUIRED")
    return values[0]


# A __Host cookie deletion must match its secure host-only original scope.
def clear_session_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")


# Only the immutable application shell/assets are public; API reads remain session-protected.
def ui_path(path: str) -> bool:
    return (
        path
        in {
            "/",
            "/login",
            "/administrators",
            "/operations",
            "/audit-history",
            "/api/branding",
            "/organization",
            "/tenancies",
            "/organization/drift",
            "/organization-mapping",
            "/configuration",
            "/configuration/drift",
        }
        or re.fullmatch(
            r"/(?:operations|tenancies|configuration/drift)/"
            r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}",
            path,
        )
        is not None
        or path.startswith("/assets/")
        or re.fullmatch(
            r"/branding-assets/[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.(png|webp|ico|jpg|jpeg)", path
        )
        is not None
    )


# Resolve one opaque cookie using the required session/current-entitlement boundary.
class CookieSessionBackend(AuthenticationBackend):
    # Use explicit dependencies; authentication has no environment or local-actor fallback.
    def __init__(
        self, sessions: SessionService, allow_local_login: bool = False, public_ui: bool = False
    ):
        self.sessions = sessions
        self.allow_local_login = allow_local_login
        self.public_ui = public_ui

    # Bound parsing and reject duplicate target cookies before external access.
    async def authenticate(self, conn: HTTPConnection):
        if (
            (
                self.public_ui
                and conn.scope.get("method") in {"GET", "HEAD"}
                and ui_path(conn.url.path)
            )
            or conn.url.path == "/health/live"
            or (conn.url.path == "/api/logout" and conn.scope.get("method") == "POST")
            or (
                self.allow_local_login
                and conn.url.path == "/api/auth/local/sign-in"
                and conn.scope.get("method") == "POST"
            )
        ):
            return None
        try:
            # Synchronous SQL/provider verification runs off the ASGI event loop. The repository
            # releases its connection before the separate current-entitlement check is invoked.
            principal = await run_in_threadpool(
                self.sessions.authenticate, session_handle(conn.headers)
            )
        except SessionFailure as failure:
            raise BoundaryAuthenticationError(failure) from None
        return AuthCredentials(["authenticated", "administrator"]), principal


# Apply server-side HTTPS/Host and unsafe-request guards, plus non-cacheable API responses.
class BrowserBoundaryMiddleware:
    # Freeze a configured public origin; never trust forwarded headers here.
    def __init__(self, app, settings: BrowserSettings, public_ui: bool = False):
        self.app, self.settings = app, settings
        self.public_ui = public_ui
        self.host = urlsplit(settings.public_origin).netloc

    # Keep health process-only while guarding all other HTTP paths before authentication.
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health/live":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)

        # Prevent browsers/proxies from caching identity/error data and sniffing it as HTML.
        async def private_response(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["Cache-Control"] = "no-store"
                response_headers.add_vary_header("Cookie")
                response_headers["X-Content-Type-Options"] = "nosniff"
                response_headers["Content-Security-Policy"] = (
                    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                    "img-src 'self'; font-src 'self'; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'self'"
                    if self.public_ui and ui_path(scope["path"])
                    else "default-src 'none'; frame-ancestors 'none'"
                )
                response_headers["Referrer-Policy"] = "no-referrer"
            await send(message)

        if (
            scope["scheme"] != "https"
            or headers.get("host") != self.host
            or len(headers.getlist("host")) != 1
        ):
            await JSONResponse({"code": "INVALID_REQUEST_ORIGIN"}, status_code=400)(
                scope, receive, private_response
            )
            return
        if scope["method"] not in SAFE_METHODS:
            # A custom header forces cross-origin browser requests to preflight. No permissive
            # CORS middleware is installed. Reject missing/null/mismatched Origin as well.
            if (
                headers.get("origin") != self.settings.public_origin
                or len(headers.getlist("origin")) != 1
                or headers.get("x-otm-request") != "1"
                or len(headers.getlist("x-otm-request")) != 1
            ):
                await JSONResponse({"code": "REQUEST_ORIGIN_REQUIRED"}, status_code=403)(
                    scope, receive, private_response
                )
                return
        await self.app(scope, receive, private_response)
