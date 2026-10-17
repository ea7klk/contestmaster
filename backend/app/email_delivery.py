"""Small SMTP adapter for one-time participant sign-in links."""

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from time import monotonic

from pydantic import ValidationError

from backend.app.config import get_settings
from backend.app.email_templates import render_email

logger = logging.getLogger("contestmaster.email_delivery")
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_CREDENTIAL_PATTERN = re.compile(
    r"\b(password|passwd|token|secret|authorization)\s*[:=]\s*\S+", re.IGNORECASE
)


class EmailDeliveryError(RuntimeError):
    """Safe SMTP failure details that never include message or credential content."""

    def __init__(self, stage: str, failure_kind: str):
        super().__init__(f"Email delivery failed during {stage} ({failure_kind}).")
        self.stage = stage
        self.failure_kind = failure_kind


def send_participant_magic_link(email: str, link: str, *, locale: str = "en") -> None:
    send_email(
        email,
        "Your Contestmaster sign-in link",
        "Use this one-time link to verify your email address and sign in to Contestmaster. "
        "The link expires in 15 minutes and can be used only once.",
        link,
        locale=locale,
        template="magic_link",
    )


def send_guest_entry_verification(email: str, link: str, *, locale: str = "en") -> None:
    send_email(
        email,
        "Verify access to your Contestmaster log",
        "Confirm this address to enable the guest log options you selected. "
        "The link expires in 24 hours and can be used only once.",
        link,
        locale=locale,
        template="guest_verify",
    )


def send_guest_result_notice(
    email: str, contest_name: str, publication_number: int, link: str, *, locale: str = "en"
) -> None:
    send_email(
        email,
        f"{contest_name}: results are published",
        f"Contestmaster has published result list {publication_number} for {contest_name}. "
        "Open the public results page to view the standings.",
        link,
        locale=locale,
        template="result_notice",
        template_values={"contest_name": contest_name, "publication_number": publication_number},
    )


def send_email(
    email: str,
    subject: str,
    explanation: str,
    link: str | None = None,
    *,
    locale: str = "en",
    template: str | None = None,
    template_values: dict[str, str | int] | None = None,
) -> None:
    """Deliver a localized multipart message through the configured SMTP relay."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        logger.warning(
            "email_delivery_failed",
            extra={"stage": "configuration", "failure_kind": "InvalidApplicationConfiguration"},
        )
        raise EmailDeliveryError("configuration", "InvalidApplicationConfiguration") from exc
    if not settings.email_smtp_host or not settings.email_from_address:
        _raise_delivery_error("configuration", "MissingSMTPHostOrSender")

    stage = "message_build"
    started_at = monotonic()
    auth_mechanisms: str | None = None
    try:
        message = EmailMessage()
        rendered = render_email(
            template or "generic",
            locale=locale,
            link=link,
            values={"subject": subject, "explanation": explanation, **(template_values or {})},
        )
        message["Subject"] = rendered.subject
        message["From"] = settings.email_from_address
        message["To"] = email
        message.set_content(rendered.text)
        message.add_alternative(rendered.html, subtype="html")

        stage = "connection"
        _log_delivery_stage(
            stage=stage,
            status="started",
            host=settings.email_smtp_host,
            port=settings.email_smtp_port,
            tls_mode="STARTTLS",
            auth_configured=bool(settings.email_smtp_username),
        )
        with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port, timeout=10) as server:
            stage = "greeting"
            ehlo_code, _ = server.ehlo()
            _log_delivery_stage(stage=stage, status="succeeded", smtp_code=ehlo_code)
            stage = "starttls"
            tls_code, _ = server.starttls(context=ssl.create_default_context())
            _log_delivery_stage(stage=stage, status="succeeded", smtp_code=tls_code)
            ehlo_code, _ = server.ehlo()
            auth_mechanisms = server.esmtp_features.get("auth")
            _log_delivery_stage(
                stage="greeting_after_tls",
                status="succeeded",
                smtp_code=ehlo_code,
                auth_mechanisms=_safe_auth_mechanisms(auth_mechanisms),
            )
            if settings.email_smtp_username:
                stage = "authentication"
                _log_delivery_stage(
                    stage=stage,
                    status="started",
                    auth_mechanisms=_safe_auth_mechanisms(auth_mechanisms),
                )
                password = (
                    settings.email_smtp_password.get_secret_value()
                    if settings.email_smtp_password is not None
                    else ""
                )
                auth_code, _ = server.login(settings.email_smtp_username, password)
                _log_delivery_stage(stage=stage, status="succeeded", smtp_code=auth_code)
            stage = "send"
            server.send_message(message)
            _log_delivery_stage(stage=stage, status="succeeded")
        logger.info(
            "email_delivery_succeeded",
            extra={
                "stage": "complete",
                "status": "succeeded",
                "elapsed_ms": _elapsed_ms(started_at),
            },
        )
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        smtp_code, smtp_reply = _smtp_failure_details(
            exc,
            sensitive_values=(
                settings.email_smtp_username,
                settings.email_smtp_password.get_secret_value()
                if settings.email_smtp_password is not None
                else None,
                settings.email_from_address,
                email,
                link,
            ),
        )
        logger.warning(
            "email_delivery_failed",
            extra={
                "stage": stage,
                "failure_kind": type(exc).__name__,
                "smtp_host": settings.email_smtp_host,
                "smtp_port": settings.email_smtp_port,
                "smtp_code": smtp_code,
                "smtp_reply": smtp_reply,
                "auth_mechanisms": _safe_auth_mechanisms(auth_mechanisms),
                "elapsed_ms": _elapsed_ms(started_at),
            },
        )
        raise EmailDeliveryError(stage, type(exc).__name__) from exc


def _raise_delivery_error(stage: str, failure_kind: str) -> None:
    logger.warning(
        "email_delivery_failed",
        extra={"stage": stage, "failure_kind": failure_kind},
    )
    raise EmailDeliveryError(stage, failure_kind)


def _log_delivery_stage(
    *,
    stage: str,
    status: str,
    host: str | None = None,
    port: int | None = None,
    tls_mode: str | None = None,
    auth_configured: bool | None = None,
    smtp_code: int | None = None,
    auth_mechanisms: str | None = None,
) -> None:
    extra: dict[str, object] = {"stage": stage, "status": status}
    if host is not None:
        extra["smtp_host"] = host
    if port is not None:
        extra["smtp_port"] = port
    if tls_mode is not None:
        extra["tls_mode"] = tls_mode
    if auth_configured is not None:
        extra["auth_configured"] = auth_configured
    if smtp_code is not None:
        extra["smtp_code"] = smtp_code
    if auth_mechanisms:
        extra["auth_mechanisms"] = auth_mechanisms
    logger.info("email_delivery_stage", extra=extra)


def _safe_auth_mechanisms(value: str | None) -> str | None:
    if not value:
        return None
    return (
        " ".join(
            mechanism
            for mechanism in value.upper().split()
            if mechanism in {"PLAIN", "LOGIN", "CRAM-MD5", "XOAUTH2"}
        )
        or None
    )


def _smtp_failure_details(
    exc: BaseException, *, sensitive_values: tuple[str | None, ...]
) -> tuple[int | None, str | None]:
    if isinstance(exc, smtplib.SMTPResponseException):
        smtp_code = exc.smtp_code
        response = exc.smtp_error
    elif isinstance(exc, smtplib.SMTPRecipientsRefused):
        smtp_code = next(
            (code for code, _reply in exc.recipients.values() if isinstance(code, int)), None
        )
        response = next((reply for _code, reply in exc.recipients.values()), None)
    else:
        return None, None

    if isinstance(response, bytes):
        diagnostic = response.decode("utf-8", errors="replace")
    else:
        diagnostic = str(response) if response is not None else ""
    diagnostic = _EMAIL_PATTERN.sub("[redacted-email]", diagnostic)
    diagnostic = _URL_PATTERN.sub("[redacted-url]", diagnostic)
    diagnostic = _CREDENTIAL_PATTERN.sub(r"\1=[redacted]", diagnostic)
    for value in sensitive_values:
        if value:
            diagnostic = diagnostic.replace(value, "[redacted]")
    diagnostic = "".join(char if char.isprintable() else " " for char in diagnostic)
    diagnostic = " ".join(diagnostic.split())[:240]
    return smtp_code, diagnostic or None


def _elapsed_ms(started_at: float) -> float:
    return round((monotonic() - started_at) * 1000, 2)
