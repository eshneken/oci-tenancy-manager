"""Browser-bound single-use Oracle SSO attempts for the single-process laptop pilot."""

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, RedirectResponse

from otm.auth.corporate_exchange import OracleCodeExchange
from otm.auth.corporate_oidc import (
    CALLBACK_PATH,
    START_PATH,
    OidcAttemptMaterial,
)
from otm.auth.http import COOKIE_NAME
from otm.storage.corporate_sessions import SqlCorporateSessions

LAPTOP_PILOT_ORIGIN = "https://127.0.0.1:8445"
ATTEMPT_COOKIE = "__Host-otm_oidc_attempt"
ATTEMPT_TTL = 300
ATTEMPT_LIMIT = 128
CORRELATION = re.compile(r"[A-Za-z0-9_-]{43}\Z")


# Keep the PKCE material private and the browser binding in a separate digest.
@dataclass(frozen=True, repr=False)
class PendingAttempt:
    material: OidcAttemptMaterial
    browser_hash: bytes = field(repr=False)
    expires: float


# Bound pending state to one local server process. Hosted replicas need shared atomic storage.
class LaptopOidcAttempts:
    # Use a monotonic clock so the local expiry cannot be extended by a wall-clock adjustment.
    def __init__(self, clock=monotonic):
        self.clock, self.lock = clock, Lock()
        self.pending: dict[str, PendingAttempt] = {}

    # Reject pressure before replacing an unexpired attempt from another browser.
    def begin(self):
        material = OidcAttemptMaterial.generate()
        browser = secrets.token_urlsafe(32)
        with self.lock:
            now = self.clock()
            self.pending = {state: row for state, row in self.pending.items() if row.expires > now}
            if len(self.pending) >= ATTEMPT_LIMIT:
                raise ValueError("OIDC_ATTEMPTS_BUSY")
            self.pending[material.state] = PendingAttempt(
                material, hashlib.sha256(browser.encode()).digest(), now + ATTEMPT_TTL
            )
        return material, browser

    # Consume only the matching browser's valid attempt under one lock, before token exchange.
    def consume(self, state, browser):
        if not CORRELATION.fullmatch(state) or not CORRELATION.fullmatch(browser):
            raise ValueError("OIDC_ATTEMPT_INVALID")
        with self.lock:
            row = self.pending.get(state)
            if (
                row is None
                or row.expires <= self.clock()
                or not secrets.compare_digest(
                    row.browser_hash, hashlib.sha256(browser.encode()).digest()
                )
            ):
                raise ValueError("OIDC_ATTEMPT_INVALID")
            del self.pending[state]
            return row.material


# Inject only the capabilities needed by the laptop routes; no default identity or writer exists.
@dataclass(frozen=True, repr=False)
class CorporateSignIn:
    attempts: LaptopOidcAttempts
    exchange: OracleCodeExchange
    issuer: SqlCorporateSessions


# Register routes only with explicit binding, exchange, and transactional session issuance.
def corporate_router(sign_in: CorporateSignIn):
    router = APIRouter()

    # The existing middleware requires same-origin Origin and custom header on this POST.
    @router.post(START_PATH)
    def start():
        try:
            material, browser = sign_in.attempts.begin()
        except ValueError:
            return JSONResponse({"code": "CORPORATE_SIGN_IN_UNAVAILABLE"}, status_code=503)
        response = JSONResponse(
            {"authorization_url": material.authorization_url(sign_in.exchange.binding)}
        )
        response.set_cookie(
            ATTEMPT_COOKIE,
            browser,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=ATTEMPT_TTL,
        )
        return response

    # Validate the callback without reflecting provider query data or creating a partial session.
    @router.get(CALLBACK_PATH)
    def callback(request: Request):
        response = RedirectResponse("/login?sso=failed", status_code=303)
        try:
            query = request.query_params
            code = query.getlist("code")
            state = query.getlist("state")
            browser = [
                value.strip()
                for header in request.headers.getlist("cookie")
                for pair in header.split(";")
                for key, _, value in (pair.strip().partition("="),)
                if key.strip() == ATTEMPT_COOKIE
            ]
            if (
                len(request.scope["query_string"]) > 4096
                or "error" in query
                or len(code) != 1
                or not 1 <= len(code[0]) <= 2048
                or any(not 33 <= ord(char) <= 126 for char in code[0])
                or len(state) != 1
                or len(browser) != 1
            ):
                raise ValueError("OIDC_CALLBACK_INVALID")
            material = sign_in.attempts.consume(state[0], browser[0])
            verified = sign_in.exchange.exchange(code[0], material)
            issued = sign_in.issuer.issue(verified)
            response = RedirectResponse("/", status_code=303)
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
        except Exception:
            logging.getLogger(__name__).debug("Corporate SSO callback did not complete")
        response.delete_cookie(ATTEMPT_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
        return response

    return router
