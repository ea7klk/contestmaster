import pytest
from pydantic import ValidationError

from backend.app.config import PROJECT_ENV_FILE, Settings


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


def test_smtp_username_and_password_must_be_configured_together():
    with pytest.raises(ValidationError, match="email_smtp_username and email_smtp_password"):
        Settings(**valid_staging_settings(email_smtp_username="contestmaster@example.test"))
    with pytest.raises(ValidationError, match="email_smtp_username and email_smtp_password"):
        Settings(
            **valid_staging_settings(email_smtp_password="a mailbox password")
        )


def test_project_env_file_location_is_absolute_and_independent_of_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    configured_env_file = Settings.model_config["env_file"]
    assert configured_env_file == PROJECT_ENV_FILE
    assert configured_env_file.is_absolute()
    assert configured_env_file.name == ".env"
