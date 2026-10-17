import json
import smtplib
import ssl
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from backend.app import email_cli, email_delivery
from backend.app.email_delivery import EmailDeliveryError
from backend.app.logging_config import JsonFormatter


class FakeSMTP:
    fail_at: str | None = None
    sent_messages = []
    authentications = []

    def __init__(self, host, port, timeout):
        assert host == "mail.example.test"
        assert port == 587
        assert timeout == 10
        if self.fail_at == "connection":
            raise OSError("private host and account details")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def ehlo(self):
        return None

    def starttls(self, context):
        assert isinstance(context, ssl.SSLContext)
        if self.fail_at == "starttls":
            raise ssl.SSLError("private TLS diagnostic")

    def login(self, username, password):
        self.authentications.append((username, password))
        if self.fail_at == "authentication":
            raise smtplib.SMTPAuthenticationError(535, b"private credentials rejected")

    def send_message(self, message):
        self.sent_messages.append(message)
        if self.fail_at == "send":
            raise smtplib.SMTPDataError(554, b"private message rejection")


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.fail_at = None
    FakeSMTP.sent_messages = []
    FakeSMTP.authentications = []
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(
        email_delivery,
        "get_settings",
        lambda: SimpleNamespace(
            email_smtp_host="mail.example.test",
            email_smtp_port=587,
            email_smtp_username="contestmaster@mail.example.test",
            email_smtp_password=SecretStr("smtp-secret"),
            email_from_address="contestmaster@mail.example.test",
        ),
    )


def test_send_email_uses_starttls_authentication_and_optional_test_body():
    email_delivery.send_email(
        "recipient@example.test",
        "SMTP test",
        "This confirms SMTP delivery.",
    )

    assert FakeSMTP.authentications == [("contestmaster@mail.example.test", "smtp-secret")]
    assert len(FakeSMTP.sent_messages) == 1
    message = FakeSMTP.sent_messages[0]
    assert message["To"] == "recipient@example.test"
    assert "This confirms SMTP delivery." in message.get_content()
    assert "smtp-secret" not in message.get_content()


@pytest.mark.parametrize(
    ("failure_stage", "expected_kind"),
    [
        ("connection", "OSError"),
        ("starttls", "SSLError"),
        ("authentication", "SMTPAuthenticationError"),
        ("send", "SMTPDataError"),
    ],
)
def test_delivery_failures_are_stage_specific_and_do_not_log_private_data(
    failure_stage, expected_kind, caplog
):
    FakeSMTP.fail_at = failure_stage

    with pytest.raises(EmailDeliveryError) as error:
        email_delivery.send_email(
            "private-recipient@example.test",
            "Private subject",
            "private message content",
            "https://example.test/private-token",
        )

    assert error.value.stage == failure_stage
    assert error.value.failure_kind == expected_kind
    record = next(
        record for record in caplog.records if record.name == "contestmaster.email_delivery"
    )
    assert record.stage == failure_stage
    assert record.failure_kind == expected_kind
    formatted_log = JsonFormatter().format(record)
    payload = json.loads(formatted_log)
    assert payload["stage"] == failure_stage
    assert payload["failure_kind"] == expected_kind
    assert "private-recipient@example.test" not in formatted_log
    assert "smtp-secret" not in formatted_log
    assert "private-token" not in formatted_log
    assert "private message content" not in formatted_log


def test_missing_smtp_configuration_has_a_safe_configuration_error(monkeypatch, caplog):
    monkeypatch.setattr(
        email_delivery,
        "get_settings",
        lambda: SimpleNamespace(email_smtp_host=None, email_from_address=None),
    )

    with pytest.raises(EmailDeliveryError) as error:
        email_delivery.send_email("recipient@example.test", "Subject", "Body")

    assert error.value.stage == "configuration"
    assert error.value.failure_kind == "MissingSMTPHostOrSender"
    record = next(
        record for record in caplog.records if record.name == "contestmaster.email_delivery"
    )
    assert record.stage == "configuration"


def test_smtp_cli_requires_and_uses_an_explicit_recipient(monkeypatch, capsys):
    delivered = []
    monkeypatch.setattr(email_cli, "send_email", lambda *args: delivered.append(args))

    email_cli.main(["test", "--to", "operator@example.test"])

    assert delivered == [
        (
            "operator@example.test",
            "Contestmaster SMTP configuration test",
            "This message confirms that Contestmaster can deliver email through its "
            "configured SMTP relay.",
        )
    ]
    assert capsys.readouterr().out == "SMTP test message sent successfully.\n"
