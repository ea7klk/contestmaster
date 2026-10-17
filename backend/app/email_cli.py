"""Operator command for checking configured SMTP delivery."""

from __future__ import annotations

import argparse
import sys

from pydantic import ValidationError

from backend.app.config import get_settings
from backend.app.email_delivery import EmailDeliveryError, send_email
from backend.app.logging_config import configure_logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="contestmaster-email")
    subparsers = parser.add_subparsers(dest="command", required=True)
    test_command = subparsers.add_parser(
        "test", help="Send a test message using the configured SMTP relay"
    )
    test_command.add_argument("--to", required=True, help="Recipient address for the test message")
    arguments = parser.parse_args(argv)

    try:
        try:
            settings = get_settings()
        except ValidationError:
            settings = None
        configure_logging(settings.log_level if settings is not None else "INFO")
        send_email(
            arguments.to,
            "Contestmaster SMTP configuration test",
            "This message confirms that Contestmaster can deliver email through its "
            "configured SMTP relay.",
        )
    except EmailDeliveryError as exc:
        print(
            f"SMTP test failed during {exc.stage} ({exc.failure_kind}). "
            "Check the matching EMAIL_SMTP_* settings and application logs.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except ValidationError as exc:
        print(
            "SMTP test could not load valid application settings. "
            "Check the project .env file and EMAIL_SMTP_* credential pair.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print("SMTP test message sent successfully.")


if __name__ == "__main__":
    main()
