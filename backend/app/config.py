from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./var/contestmaster.db"
    sqlite_busy_timeout_ms: int = 5000
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    allowed_origins: list[str] = ["http://localhost:5173"]

    @field_validator("sqlite_busy_timeout_ms")
    @classmethod
    def busy_timeout_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("sqlite_busy_timeout_ms must be positive")
        return value


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
