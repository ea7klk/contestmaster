"""Small SMTP adapter for one-time participant sign-in links."""

import smtplib
import ssl
from email.message import EmailMessage

from backend.app.config import get_settings


def send_participant_magic_link(email: str, link: str) -> None:
    send_email(
        email,
        "Your Contestmaster sign-in link",
        "Use this one-time link to verify your email address and sign in to Contestmaster. "
        "The link expires in 15 minutes and can be used only once.",
        link,
    )


def send_email(email: str, subject: str, explanation: str, link: str) -> None:
    """Deliver one transactional account link through the configured SMTP relay."""
    settings = get_settings()
    if not settings.email_smtp_host or not settings.email_from_address:
        raise RuntimeError("Email delivery is not configured.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from_address
    message["To"] = email
    message.set_content(
        f"{explanation}\n\n{link}\n\nIf you did not request this link, you can ignore this message."
    )
    with smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port, timeout=10) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        if settings.email_smtp_username:
            server.login(settings.email_smtp_username, settings.email_smtp_password or "")
        server.send_message(message)
