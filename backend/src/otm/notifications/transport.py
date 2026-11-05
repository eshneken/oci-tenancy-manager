"""Minimal SMTP adapter with an explicit remote-acceptance uncertainty boundary."""

import ipaddress
import smtplib
import ssl
from email.message import EmailMessage

from otm.notifications.contracts import DeliveryResult, mailbox
from otm.operations.contracts import canonical_hash


# Resolve passwords only inside the adapter; delivery records never contain SMTP credentials.
class SmtpTransport:
    # Plain SMTP is confined to explicitly configured loopback capture in local development.
    def __init__(
        self,
        *,
        host,
        port,
        sender,
        start_tls=True,
        username=None,
        password_loader=None,
        allow_loopback_cleartext=False,
        timeout=10,
        tls_mode=None,
        password_secret_reference=None,
    ):
        mailbox(sender)
        if tls_mode is not None:
            if tls_mode not in {"local", "starttls", "implicit"}:
                raise ValueError("INVALID_SMTP_TLS_MODE")
            start_tls = tls_mode == "starttls"
            allow_loopback_cleartext = tls_mode == "local"
        implicit = tls_mode == "implicit"
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("INVALID_SMTP_PORT")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 30:
            raise ValueError("INVALID_SMTP_TIMEOUT")
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not start_tls and not implicit and not (allow_loopback_cleartext and loopback):
            raise ValueError("SMTP_TLS_REQUIRED")
        if bool(username) != bool(password_loader):
            raise ValueError("SMTP_CREDENTIALS_INCOMPLETE")
        self.host, self.port, self.sender = host, port, sender
        self.start_tls, self.username, self.password_loader = start_tls, username, password_loader
        self.timeout, self.implicit = timeout, implicit
        self.profile_hash = canonical_hash(
            {
                "host": host,
                "port": port,
                "sender": sender,
                "tls_mode": "implicit" if implicit else "starttls" if start_tls else "local",
                "username": username,
                "password_secret_reference": password_secret_reference,
            }
        )

    # Once DATA might have been submitted, failures are uncertain and may not be blindly retried.
    def send(self, envelope):
        message = EmailMessage()
        message["From"], message["To"] = self.sender, envelope.recipient
        message["Subject"] = envelope.subject
        message["Message-ID"] = f"<{envelope.notification_id}@otm.invalid>"
        message.set_content(envelope.body)
        connection, submitted = None, False
        try:
            connection = (
                smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=ssl.create_default_context()
                )
                if self.implicit
                else smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            )
            connection.ehlo()
            if self.start_tls:
                connection.starttls(context=ssl.create_default_context())
                connection.ehlo()
            if self.username:
                connection.login(self.username, self.password_loader())
            code, _ = connection.mail(self.sender)
            if code != 250:
                return DeliveryResult(state="rejected", safe_code="SMTP_REJECTED")
            code, _ = connection.rcpt(envelope.recipient)
            if code not in {250, 251}:
                return DeliveryResult(state="rejected", safe_code="SMTP_REJECTED")
            submitted = True
            code, _ = connection.data(message.as_bytes())
            if code != 250:
                return DeliveryResult(state="rejected", safe_code="SMTP_REJECTED")
            return DeliveryResult(state="accepted", safe_code="SMTP_ACCEPTED")
        except smtplib.SMTPDataError:
            return DeliveryResult(state="rejected", safe_code="SMTP_REJECTED")
        except Exception:
            return DeliveryResult(
                state="uncertain" if submitted else "rejected",
                safe_code="SMTP_OUTCOME_UNKNOWN" if submitted else "SMTP_UNAVAILABLE",
            )
        finally:
            if connection:
                # Closing the socket cannot change already established DATA acceptance knowledge.
                try:
                    connection.close()
                except Exception:  # nosec B110
                    pass
