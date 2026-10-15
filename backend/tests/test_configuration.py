import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def valid_staging_settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "staging",
        "secure_cookies": True,
        "allowed_origins": ["https://contest.example.test"],
        "frontend_base_url": "https://contest.example.test",
        "entry_receipt_secret": "S" * 48,
        "email_smtp_host": "mail.example.test",
        "email_from_address": "contestmaster@example.test",
        "master_data_scheduler_enabled": True,
    }
    values.update(overrides)
    return values


def test_staging_accepts_explicit_secure_settings():
    settings = Settings(**valid_staging_settings())

    assert settings.secure_cookies
    assert settings.allowed_origins == ["https://contest.example.test"]


@pytest.mark.parametrize(
    "override, message",
    [
        ({"secure_cookies": False}, "secure_cookies"),
        ({"entry_receipt_secret": "development-only-change-before-deploy"}, "entry_receipt_secret"),
        ({"entry_receipt_secret": "short"}, "entry_receipt_secret"),
        ({"allowed_origins": ["*"]}, "allowed_origins"),
        ({"allowed_origins": ["http://contest.example.test"]}, "allowed_origins"),
        ({"frontend_base_url": "http://contest.example.test"}, "frontend_base_url"),
        ({"email_smtp_host": None}, "email_smtp_host"),
        ({"master_data_scheduler_enabled": False}, "master_data_scheduler_enabled"),
    ],
)
def test_staging_rejects_insecure_or_incomplete_settings(override, message):
    with pytest.raises(ValidationError, match=message):
        Settings(**valid_staging_settings(**override))


def test_enabled_metrics_require_a_long_bearer_secret():
    with pytest.raises(ValidationError, match="metrics_bearer_token"):
        Settings(**valid_staging_settings(metrics_enabled=True))

    settings = Settings(
        **valid_staging_settings(
            metrics_enabled=True,
            metrics_bearer_token="T" * 48,
        )
    )
    assert settings.metrics_bearer_token.get_secret_value() == "T" * 48
