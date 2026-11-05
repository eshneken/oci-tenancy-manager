"""Explicit notification composition; no implicit SMTP endpoint or secret-source fallback."""

from otm.notifications.service import LifecycleNotifier
from otm.notifications.transport import SmtpTransport
from otm.notifications.worker import NotificationEnqueuer


# Hosted secret retrieval remains an injected capability; local capture needs no credentials.
def compose_notifications(settings, queue, *, secret_loader=None):
    if not settings.notifications.enabled:
        return None, None, None
    config = settings.notifications
    if config.password_secret_reference and secret_loader is None:
        raise ValueError("SMTP_SECRET_PROVIDER_REQUIRED")

    # Resolve a configured reference only during authenticated transport use, never into a row.
    def password():
        return secret_loader(config.password_secret_reference)

    transport = SmtpTransport(
        host=config.smtp_host,
        port=config.smtp_port,
        sender=config.sender_email,
        tls_mode=config.tls_mode,
        username=config.username,
        password_loader=password if config.password_secret_reference else None,
        password_secret_reference=config.password_secret_reference,
    )
    enqueuer = NotificationEnqueuer(queue)
    return (
        LifecycleNotifier(
            settings.mail_policy(),
            enqueuer,
            profile_hash=transport.profile_hash,
            application_origin=settings.local_server.public_origin
            if settings.local_server
            else config.application_origin,
        ),
        transport,
        enqueuer,
    )
