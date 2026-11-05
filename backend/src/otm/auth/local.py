"""Local password/TOTP proofs and bounded login orchestration, independent of corporate SSO."""

import re
from datetime import UTC, datetime
from threading import BoundedSemaphore
from typing import Annotated, Literal, Protocol
from uuid import UUID

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pydantic import Field, SecretStr, TypeAdapter

from otm.auth.contracts import AdminSession
from otm.contracts import Contract, UtcInstant
from otm.secrets.directory import MfaSecrets
from otm.settings import ApplicationSettings

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)


# Keep factor values masked even in accidental model representations; HTTP errors remain fixed.
class LocalSignIn(Contract):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[SecretStr, Field(max_length=128)]
    totp_code: Annotated[SecretStr, Field(min_length=6, max_length=6)]


# Carry a handle only to the response boundary, never to JSON responses or audit.
class IssuedSession(Contract):
    handle: SecretStr
    session: AdminSession


# Allowlist authentication evidence without credential values, attempted usernames or request
# bodies.
class SecurityEvidence(Contract):
    contract_version: Literal["local-auth-1"]
    outcome: Literal[
        "administrator_bootstrapped",
        "local_credentials_reset",
        "local_sign_in_succeeded",
        "local_sign_in_failed",
        "session_logged_out",
    ]
    session_id: UUID | None
    authorization_revision: UUID | None


# Return fixed local-auth/operator diagnostics; never raw SDK, SQL or enrollment values.
class LocalAuthFailure(Exception):
    # Restrict status/code combinations before the public HTTP/CLI boundary consumes them.
    def __init__(self, status: int, code: str):
        if (status, code) not in {
            (401, "LOCAL_AUTHENTICATION_FAILED"),
            (409, "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED"),
            (409, "LOCAL_CREDENTIALS_CHANGED"),
            (403, "OPERATOR_PRIVILEGES_REQUIRED"),
            (503, "LOCAL_AUTHENTICATION_UNAVAILABLE"),
            (400, "INVALID_LOCAL_CREDENTIALS"),
        }:
            raise ValueError("INVALID_LOCAL_AUTH_DIAGNOSTIC") from None
        super().__init__(code)
        self.status, self.code = status, code


# Enforce the accepted passphrase bounds without silently trimming Unicode or whitespace.
def password_verifier(password: str) -> str:
    if (
        not isinstance(password, str)
        or not 15 <= len(password) <= 128
        or len(password.encode("utf-8")) > 512
    ):
        raise LocalAuthFailure(400, "INVALID_LOCAL_CREDENTIALS")
    return PASSWORDS.hash(password)


# Return only a fresh matching library-verified time step; consuming it belongs to the DB
# transaction.
def totp_step(seed: str, code: str, at: datetime, last_step: int) -> int | None:
    if not re.fullmatch("[A-Z2-7]{32}", seed) or not re.fullmatch("[0-9]{6}", code):
        return None
    at = TypeAdapter(UtcInstant).validate_python(at)
    generator = pyotp.TOTP(seed)
    step = generator.timecode(at)
    # Consume the greatest matching counter: adjacent six-digit collisions cannot mint two sessions.
    matching = [
        candidate
        for candidate in (step - 1, step, step + 1)
        if candidate >= 0
        and generator.verify(
            code, for_time=datetime.fromtimestamp(candidate * 30, UTC), valid_window=0
        )
    ]
    accepted = max(matching, default=-1)
    return accepted if accepted > last_step else None


# Define IO/transaction behavior separately from password hashing and HTTP composition.
class LocalLoginRepository(Protocol):
    # Return an internal current grant/credential snapshot without holding a connection while
    # hashing.
    def material(self): ...

    # Recheck snapshot, replay/cooldown/current grant and commit session plus required audit
    # atomically.
    def finish(
        self, material, password_ok: bool, seed: str, code: str, old_handle: str | None
    ) -> IssuedSession: ...


# Bound expensive password work per process and keep all factor failures generic.
class LocalLogin:
    # Require explicit settings, store and immutable secret custody; never configure an IdP
    # fallback.
    def __init__(
        self, settings: ApplicationSettings, repository: LocalLoginRepository, secrets: MfaSecrets
    ):
        if settings.local_auth is None:
            raise ValueError("LOCAL_AUTH_CONFIGURATION_REQUIRED")
        self.settings, self.repository, self.secrets = settings, repository, secrets
        self.capacity = BoundedSemaphore(settings.local_auth.max_password_workers)
        self.dummy = PASSWORDS.hash(pyotp.random_base32())

    # Verify one closed request and never return an issued handle before its transaction commits.
    def sign_in(self, request: LocalSignIn, old_handle: str | None = None) -> IssuedSession:
        try:
            request = LocalSignIn.model_validate(request)
            password = request.password.get_secret_value()
            code = request.totp_code.get_secret_value()
            if (
                len(password) > 128
                or len(password.encode("utf-8")) > 512
                or not re.fullmatch("[0-9]{6}", code)
            ):
                raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED")
            if not self.capacity.acquire(blocking=False):
                raise LocalAuthFailure(503, "LOCAL_AUTHENTICATION_UNAVAILABLE")
            try:
                material = self.repository.material()
                known = material is not None and request.username == "recovery-admin"
                verifier = material[1]["password_hash"] if known else self.dummy
                try:
                    verified = PASSWORDS.verify(verifier, password)
                except VerifyMismatchError:
                    verified = False
                if material is None:
                    raise LocalAuthFailure(401, "LOCAL_AUTHENTICATION_FAILED")
                seed = (
                    self.secrets.get(material[1]["totp_secret_reference"])
                    if known and verified
                    else ""
                )
                return self.repository.finish(
                    material, bool(known and verified), seed, code, old_handle
                )
            finally:
                self.capacity.release()
        except LocalAuthFailure:
            raise
        except Exception:
            raise LocalAuthFailure(503, "LOCAL_AUTHENTICATION_UNAVAILABLE") from None
