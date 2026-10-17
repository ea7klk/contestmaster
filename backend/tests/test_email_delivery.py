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
    esmtp_features = {"auth": "PLAIN LOGIN"}

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
        return 250, b"mail.example.test ready"

    def starttls(self, context):
        assert isinstance(context, ssl.SSLContext)
        if self.fail_at == "starttls":
            raise smtplib.SMTPResponseException(454, b"TLS not available now")
        return 220, b"TLS go ahead"

    def login(self, username, password):
        self.authentications.append((username, password))
        if self.fail_at == "authentication":
            raise smtplib.SMTPAuthenticationError(
                535,
                b"authentication failed for contestmaster@mail.example.test",
            )
        return 235, b"authentication successful"

    def send_message(self, message):
        self.sent_messages.append(message)
        if self.fail_at == "send":
            raise smtplib.SMTPDataError(
                554,
                b"message rejected for recipient@example.test; token=private-token",
            )


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
    assert message.get_content_type() == "multipart/alternative"
    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    assert plain is not None and "This confirms SMTP delivery." in plain.get_content()
    assert html is not None and "Contestmaster" in html.get_content()
    assert "#511e20" in html.get_content()
    assert "smtp-secret" not in plain.get_content()


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Sign in to Contestmaster"),
        ("de", "Bei Contestmaster anmelden"),
        ("fr", "Se connecter à Contestmaster"),
        ("es", "Accede a Contestmaster"),
        ("it", "Accedi a Contestmaster"),
    ],
)
def test_magic_link_email_is_localized_and_has_both_mime_alternatives(locale, expected):
    email_delivery.send_participant_magic_link(
        "radio@example.test", "https://example.test/a?x=1&y=2", locale=locale
    )
    message = FakeSMTP.sent_messages[-1]
    assert expected in message.get_body(preferencelist=("plain",)).get_content()
    assert message.get_body(preferencelist=("html",)) is not None


def test_html_email_escapes_dynamic_contest_name_and_link():
    email_delivery.send_guest_result_notice(
        "radio@example.test",
        '<Challenge & "Final">',
        3,
        "https://example.test/contest?a=1&b=2",
        locale="en",
    )
    message = FakeSMTP.sent_messages[-1]
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "&lt;Challenge &amp; &quot;Final&quot;&gt;" in html
    assert 'href="https://example.test/contest?a=1&amp;b=2"' in html


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("de-DE", "de"), ("fr, en;q=0.9", "fr"), ("nl-NL", "en"), (None, "en")],
)
def test_email_locale_resolution_uses_supported_base_language(raw, expected):
    from backend.app.email_locale import resolve_email_locale

    assert resolve_email_locale(raw) == expected


def test_success_logs_each_smtp_stage_without_private_message_fields(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="contestmaster.email_delivery")
    email_delivery.send_email(
        "private-recipient@example.test",
        "Private subject",
        "private message content",
        "https://example.test/private-token",
    )

    stage_records = [
        record for record in caplog.records if record.getMessage() == "email_delivery_stage"
    ]
    assert [(record.stage, record.status) for record in stage_records] == [
        ("connection", "started"),
        ("greeting", "succeeded"),
        ("starttls", "succeeded"),
        ("greeting_after_tls", "succeeded"),
        ("authentication", "started"),
        ("authentication", "succeeded"),
        ("send", "succeeded"),
    ]
    assert stage_records[0].smtp_host == "mail.example.test"
    assert stage_records[0].smtp_port == 587
    assert stage_records[0].tls_mode == "STARTTLS"
    assert stage_records[0].auth_configured is True
    auth_record = next(record for record in stage_records if record.stage == "authentication")
    assert auth_record.auth_mechanisms == "PLAIN LOGIN"

    formatted_logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    for private_value in (
        "private-recipient@example.test",
        "Private subject",
        "private message content",
        "private-token",
        "smtp-secret",
    ):
        assert private_value not in formatted_logs


@pytest.mark.parametrize(
    ("failure_stage", "expected_kind"),
    [
        ("connection", "OSError"),
        ("starttls", "SMTPResponseException"),
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
        record
        for record in caplog.records
        if record.name == "contestmaster.email_delivery"
        and record.getMessage() == "email_delivery_failed"
    )
    assert record.stage == failure_stage
    assert record.failure_kind == expected_kind
    formatted_log = JsonFormatter().format(record)
    payload = json.loads(formatted_log)
    assert payload["stage"] == failure_stage
    assert payload["failure_kind"] == expected_kind
    if failure_stage == "authentication":
        assert payload["smtp_code"] == 535
        assert payload["auth_mechanisms"] == "PLAIN LOGIN"
        assert "contestmaster@mail.example.test" not in formatted_log
    if failure_stage == "send":
        assert payload["smtp_code"] == 554
        assert payload["smtp_reply"] == "message rejected for [redacted-email]; token=[redacted]"
    assert "private-recipient@example.test" not in formatted_log
    assert "smtp-secret" not in formatted_log
    assert "private-token" not in formatted_log
    assert "private message content" not in formatted_log


def test_smtp_response_text_is_sanitized_and_bounded():
    error = smtplib.SMTPDataError(
        554,
        b"reject recipient@example.test https://example.test/private-token "
        b"password=smtp-secret " + b"x" * 400,
    )

    smtp_code, reply = email_delivery._smtp_failure_details(
        error,
        sensitive_values=("smtp-secret", "https://example.test/private-token"),
    )

    assert smtp_code == 554
    assert reply is not None
    assert len(reply) <= 240
    assert "recipient@example.test" not in reply
    assert "private-token" not in reply
    assert "smtp-secret" not in reply
    assert "[redacted-url]" in reply


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
    configured_levels = []
    monkeypatch.setattr(email_cli, "get_settings", lambda: SimpleNamespace(log_level="DEBUG"))
    monkeypatch.setattr(email_cli, "configure_logging", configured_levels.append)
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
    assert configured_levels == ["DEBUG"]
