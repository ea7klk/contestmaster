from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./var/contestmaster.db"
    sqlite_busy_timeout_ms: int = 5000
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:5173"]
    secure_cookies: bool = True
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_smtp_username: str | None = None
    email_smtp_password: SecretStr | None = None
    email_from_address: str | None = None
    frontend_base_url: str = "http://localhost:5173"
    entry_receipt_secret: str = "development-only-change-before-deploy"
    master_data_scheduler_enabled: bool = True
    master_data_nightly_hour_utc: int = 2
    contest_scheduler_enabled: bool = True
    contest_scheduler_interval_seconds: int = 3600
    metrics_enabled: bool = False
    metrics_bearer_token: SecretStr | None = None

    @field_validator("sqlite_busy_timeout_ms")
    @classmethod
    def busy_timeout_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("sqlite_busy_timeout_ms must be positive")
        return value

    @field_validator("master_data_nightly_hour_utc")
    @classmethod
    def nightly_hour_must_be_valid(cls, value: int) -> int:
        if not 0 <= value <= 23:
            raise ValueError("master_data_nightly_hour_utc must be between 0 and 23")
        return value

    @field_validator("contest_scheduler_interval_seconds")
    @classmethod
    def contest_scheduler_interval_must_be_valid(cls, value: int) -> int:
        if value < 60:
            raise ValueError("contest_scheduler_interval_seconds must be at least 60")
        return value

    @model_validator(mode="after")
    def validate_deployment_settings(self) -> "Settings":
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ValueError("app_env must be development, test, staging, or production")

        if self.metrics_enabled and (
            self.metrics_bearer_token is None
            or len(self.metrics_bearer_token.get_secret_value().encode("utf-8")) < 32
        ):
            raise ValueError(
                "metrics_bearer_token must contain at least 32 bytes when metrics are enabled"
            )

        smtp_username = (self.email_smtp_username or "").strip()
        smtp_password = (
            self.email_smtp_password.get_secret_value().strip()
            if self.email_smtp_password is not None
            else ""
        )
        if bool(smtp_username) != bool(smtp_password):
            raise ValueError(
                "email_smtp_username and email_smtp_password must be configured together"
            )

        if self.app_env in {"staging", "production"}:
            if not self.secure_cookies:
                raise ValueError("secure_cookies must be enabled in staging and production")
            if (
                len(self.entry_receipt_secret.encode("utf-8")) < 32
                or self.entry_receipt_secret == "development-only-change-before-deploy"
            ):
                raise ValueError(
                    "entry_receipt_secret must be a unique secret of at least 32 bytes"
                )
            if not self.allowed_origins:
                raise ValueError("allowed_origins must contain the deployed frontend origin")
            for origin in self.allowed_origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme != "https"
                    or not parsed.netloc
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                    or "*" in origin
                ):
                    raise ValueError(
                        "staging and production allowed_origins must be exact HTTPS origins"
                    )
            frontend = urlsplit(self.frontend_base_url)
            if frontend.scheme != "https" or not frontend.netloc:
                raise ValueError("frontend_base_url must be an HTTPS URL in staging and production")
            if not self.email_smtp_host or not self.email_from_address:
                raise ValueError(
                    "email_smtp_host and email_from_address are required in staging and production"
                )
            if not self.master_data_scheduler_enabled:
                raise ValueError(
                    "master_data_scheduler_enabled must be enabled in staging and production"
                )
            if not self.contest_scheduler_enabled:
                raise ValueError(
                    "contest_scheduler_enabled must be enabled in staging and production"
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent directory for a relative or absolute file-backed SQLite URL."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url == "sqlite:///:memory:":
        return
    raw_path = database_url[len(prefix) :].split("?", maxsplit=1)[0]
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
