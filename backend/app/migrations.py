"""Run Alembic revisions before the API serves requests."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from backend.app.db import build_engine

_BASELINE_REVISION = "0018_remove_unscored_country_data"


def upgrade_database() -> None:
    """Apply the baseline and pending revisions before serving API requests."""
    project_root = Path(__file__).resolve().parents[2]
    database_engine = build_engine()
    try:
        inspector = inspect(database_engine)
        if inspector.has_table("alembic_version"):
            with database_engine.connect() as connection:
                current_revision = connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            if current_revision and current_revision != _BASELINE_REVISION:
                # One-time compatibility path for installations created before the
                # migration squash. These revisions are archived and are not part of
                # the active migration graph for new databases.
                legacy_config = _config(project_root, legacy=True)
                command.upgrade(legacy_config, "head")
    finally:
        database_engine.dispose()
    command.upgrade(_config(project_root), "head")


def _config(project_root: Path, *, legacy: bool = False) -> Config:
    config = Config(str(project_root / "alembic.ini"))
    migration_root = project_root / "backend" / "migrations"
    if legacy:
        migration_root /= "legacy"
    config.set_main_option("script_location", str(migration_root))
    return config
