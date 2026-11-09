"""Load explicit nonsecret application settings without environment or database fallbacks."""

import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from otm.contracts import Contract, HttpsOrigin, Text, UtcInstant
from otm.email_policy import Environment, MailPolicy, mailbox
from otm.financial.contracts import CostPolicy
from otm.recovery_console import RecoveryConsoleSettings

PositiveSeconds = Annotated[int, Field(ge=1, le=2_147_483_647)]


# Keep configuration diagnostics fixed; TOML or validation errors may contain accidental secrets.
class ConfigurationError(ValueError):
    pass


# Bound housekeeping transactions and define a daily UTC schedule from this same source.
class SessionCleanupSettings(Contract):
    # UTC hour 0–23 for daily cleanup; schedule changes require updating the CronJob.
    hour_utc: Annotated[int, Field(ge=0, le=23)]
    # UTC minute 0–59 for daily cleanup; independent of running Jobs.
    minute_utc: Annotated[int, Field(ge=0, le=59)]
    # Rows per cleanup transaction, integer 1–10000; bounds lock/write work.
    batch_size: Annotated[int, Field(ge=1, le=10_000)]
    # Maximum batches per invocation, integer 1–1000; reaching it defers remaining work.
    max_batches: Annotated[int, Field(ge=1, le=1_000)]


# Pin these authentication limits into newly issued sessions instead of reviving old rows on reload.
class SessionSettings(Contract):
    # Idle seconds, integer 1–2147483647; pinned into each newly issued session.
    idle_timeout_seconds: PositiveSeconds
    # Absolute seconds, integer 1–2147483647; cannot be shorter than idle timeout.
    absolute_timeout_seconds: PositiveSeconds
    # Validated bounded cleanup policy; no live scheduler is created by parsing it.
    cleanup: SessionCleanupSettings

    # Reject a contradictory policy instead of silently truncating the configured idle limit.
    @model_validator(mode="after")
    def require_coherent_limits(self):
        if self.idle_timeout_seconds > self.absolute_timeout_seconds:
            raise ValueError("Idle timeout must not exceed absolute lifetime")
        return self


# Bound recovery-login work without embedding credentials or disabling MFA in development.
class LocalAuthSettings(Contract):
    # Exact deployment workspace, 1–256 nonblank characters; never accepted from the login form.
    workspace_id: Text
    # Stable installation-local issuer, 1–256 nonblank characters; changing it invalidates bindings.
    issuer: Text
    # Failures per window before a temporary cooldown, integer 1–20; shared through PostgreSQL.
    max_failures: Annotated[int, Field(ge=1, le=20)]
    # Failed-attempt counting window in seconds, integer 30–3600.
    failure_window_seconds: Annotated[int, Field(ge=30, le=3600)]
    # Temporary cooldown in seconds, integer 1–300; rejected cooldown attempts do not extend it.
    cooldown_seconds: Annotated[int, Field(ge=1, le=300)]
    # Maximum simultaneous expensive password checks per process, integer 1–4; excess fails closed.
    max_password_workers: Annotated[int, Field(ge=1, le=4)]


# Keep laptop serving explicitly separate from production ingress/proxy configuration.
class LocalServerSettings(Contract):
    # Canonical HTTPS origin, at most256 characters; laptop launcher additionally requires loopback.
    public_origin: HttpsOrigin
    # False by default; laptop-only operator reset and UI instructions, never a reset API.
    organization_reset_enabled: bool = False


# Public raster paths stay under a packaged same-origin directory, never remote URLs or traversal.
BrandingAsset = Annotated[
    str,
    Field(pattern=r"^/branding-assets/[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.(png|webp|ico|jpg|jpeg)$"),
]


# Instance identity is public presentation only; it never changes internal OTM identifiers.
class BrandingSettings(Contract):
    # Public display name, 1–80 nonblank characters; plain text, not markup or an identifier.
    display_name: Annotated[Text, Field(max_length=80)] = "OCI Tenancy Manager"
    # Optional same-origin packaged raster logo URL; omit for a text-only instance identity.
    logo_url: BrandingAsset | None = None
    # Optional same-origin packaged raster browser icon URL; omit for no custom favicon.
    icon_url: BrandingAsset | None = None


# Serialize only the three public presentation fields, never the complete application configuration.
class BrandingView(Contract):
    display_name: Text
    logo_url: BrandingAsset | None
    icon_url: BrandingAsset | None


# Optional environment-owned redirection applies to both SMTP and OCI-triggered contact fields.
class TestingSettings(Contract):
    # Single testing mailbox, validated as an address; production forbids any testing section.
    email_override: str | None = None


# Nonsecret SMTP connection policy; passwords are resolved from separately managed secret custody.
class NotificationSettings(Contract):
    # False preserves existing offline configurations; explicit enablement stages lifecycle email.
    enabled: bool = False
    # Operator-controlled SMTP DNS name or loopback IP; never accepted from an application request.
    smtp_host: Text = "127.0.0.1"
    # TCP port1–65535; local capture uses1025 by default.
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = 1025
    # Envelope/header sender, one mailbox only; it never comes from employee data.
    sender_email: str = "no-reply@otm.test"
    # Cleartext is limited to explicit local loopback capture; hosted SMTP requires verified TLS.
    tls_mode: Literal["local", "starttls", "implicit"] = "local"
    # Trusted HTTPS origin for operation links; local serving supplies its own origin.
    application_origin: HttpsOrigin | None = None
    # Optional SMTP login name; absent for unauthenticated local capture.
    username: Text | None = None
    # Nonsecret credential reference; the actual password never belongs in TOML or the outbox.
    password_secret_reference: Text | None = None

    # Local cleartext requires loopback; credentials require paired secret references.
    @model_validator(mode="after")
    def safe_transport(self):
        mailbox(self.sender_email)
        if any(char in self.smtp_host for char in " /\\@\r\n\t"):
            raise ValueError("INVALID_SMTP_HOST")
        if self.tls_mode == "local" and self.smtp_host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LOCAL_SMTP_REQUIRES_LOOPBACK")
        if (self.username is None) != (self.password_secret_reference is None):
            raise ValueError("SMTP_CREDENTIAL_REFERENCE_REQUIRED")
        return self


# Strict versioned application configuration, separate from tenancy configuration and secrets.
class ApplicationSettings(Contract):
    # Deployment identity validated again against the trusted target by both release paths.
    environment: Environment = "local"
    # Explicit testing routing; staging requires its address and production forbids this section.
    testing: TestingSettings | None = None
    # Desired recovery-only console CIDRs; absence blocks recovery readiness, not unrelated work.
    recovery_console: RecoveryConsoleSettings | None = None
    # Qualified local financial source/freshness/retry policy; real OCI qualification is separate.
    costs: CostPolicy = CostPolicy()
    # Durable lifecycle notification connection policy; disabled until an operator enables it.
    notifications: NotificationSettings = NotificationSettings()
    # Supported schema version, exactly integer1; unknown keys/versions fail closed.
    schema_version: Annotated[int, Field(ge=1, le=1)]
    # Optional public instance branding; defaults preserve generic OCI Tenancy Manager identity.
    branding: BrandingSettings = BrandingSettings()
    # Validated session policy shared by issuance and maintenance.
    sessions: SessionSettings
    # Optional explicit local recovery policy; absence does not enable any login route.
    local_auth: LocalAuthSettings | None = None
    # Optional local HTTPS serving policy; absent does not expose a frontend or start a process.
    local_server: LocalServerSettings | None = None

    # Cross-field release validation precedes all API/worker construction, including disabled email.
    @model_validator(mode="after")
    def environment_email_policy(self):
        if self.environment == "production" and self.testing is not None:
            raise ValueError("PRODUCTION_TESTING_SETTINGS_FORBIDDEN")
        self.mail_policy()
        if (
            self.notifications.enabled
            and self.local_server is None
            and self.notifications.application_origin is None
        ):
            raise ValueError("NOTIFICATION_APPLICATION_ORIGIN_REQUIRED")
        if (
            self.local_server is not None
            and self.notifications.application_origin is not None
            and self.notifications.application_origin != self.local_server.public_origin
        ):
            raise ValueError("NOTIFICATION_APPLICATION_ORIGIN_MISMATCH")
        if (
            self.environment != "local"
            and self.notifications.enabled
            and self.notifications.tls_mode == "local"
        ):
            raise ValueError("HOSTED_SMTP_REQUIRES_TLS")
        return self

    # Derive one shared policy rather than giving each workflow its own recipient override switch.
    def mail_policy(self):
        return MailPolicy(
            environment=self.environment,
            email_override=self.testing.email_override if self.testing else None,
        )


# Capture server-selected lifetime values for the eventual local/SSO session issuance boundary.
class SessionLifetime(Contract):
    # UTC issuance time plus configured absolute seconds; activity cannot extend this deadline.
    expires_at: UtcInstant
    # Idle seconds, integer 1–2147483647; pinned into each newly issued session.
    idle_timeout_seconds: PositiveSeconds


# Bound the explicit config file and reject unknown settings without private diagnostics.
def load_settings(path: Path) -> ApplicationSettings:
    try:
        with path.open("rb") as stream:
            content = stream.read(65_537)
        if len(content) > 65_536:
            raise ValueError("Configuration too large")
        return ApplicationSettings.model_validate(tomllib.loads(content.decode("utf-8")))
    except (OSError, ValueError):
        raise ConfigurationError("INVALID_APPLICATION_SETTINGS") from None


# Derive immutable row lifetime from validated settings and a trusted UTC server clock.
def session_lifetime(at: datetime, policy: SessionSettings) -> SessionLifetime:
    at = TypeAdapter(UtcInstant).validate_python(at)
    policy = SessionSettings.model_validate(policy)
    return SessionLifetime(
        expires_at=at + timedelta(seconds=policy.absolute_timeout_seconds),
        idle_timeout_seconds=policy.idle_timeout_seconds,
    )
