"""Small SMTP adapter for one-time participant sign-in links."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from pydantic import ValidationError

from backend.app.config import get_settings

logger = logging.getLogger("contestmaster.email_delivery")


class EmailDeliveryError(RuntimeError):
    """Safe SMTP failure details that never include message or credential content."""

    def __init__(self, stage: str, failure_kind: str):
        super().__init__(f"Email delivery failed during {stage} ({failure_kind}).")
        self.stage = stage
        self.failure_kind = failure_kind


def send_participant_magic_link(email: str, link: str) -> None:
    send_email(
        email,
        "Your Contestmaster sign-in link",
        "Use this one-time link to verify your email address and sign in to Contestmaster. "
        "The link expires in 15 minutes and can be used only once.",
        link,
    )


def send_guest_entry_verification(email: str, link: str) -> None:
    send_email(
        email,
        "Verify access to your Contestmaster log",
        "Confirm this address to enable the guest log options you selected. "
        "The link expires in 24 hours and can be used only once.",
        link,
    )


def send_guest_result_notice(
    email: str, contest_name: str, publication_number: int, link: str
) -> None:
    send_email(
        email,
        f"{contest_name}: results are published",
        f"Contestmaster has published result list {publication_number} for {contest_name}. "
        "Open the public results page to view the standings.",
        link,
    )


def send_email(email: str, subject: str, explanation: str, link: str | None = None) -> None:
    """Deliver one transactional account link through the configured SMTP relay."""
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
    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.email_from_address
        message["To"] = email
        body = explanation
        if link:
            body = f"{body}\n\n{link}"
        message.set_content(f"{body}\n\nIf you did not request this message, you can ignore it.")

        stage = "connection"
        with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port, timeout=10) as server:
            stage = "greeting"
            server.ehlo()
            stage = "starttls"
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            if settings.email_smtp_username:
                stage = "authentication"
                password = (
                    settings.email_smtp_password.get_secret_value()
                    if settings.email_smtp_password is not None
                    else ""
                )
                server.login(settings.email_smtp_username, password)
            stage = "send"
            server.send_message(message)
    except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
        logger.warning(
            "email_delivery_failed",
            extra={"stage": stage, "failure_kind": type(exc).__name__},
        )
        raise EmailDeliveryError(stage, type(exc).__name__) from exc


def _raise_delivery_error(stage: str, failure_kind: str) -> None:
    logger.warning(
        "email_delivery_failed",
        extra={"stage": stage, "failure_kind": failure_kind},
    )
    raise EmailDeliveryError(stage, failure_kind)
