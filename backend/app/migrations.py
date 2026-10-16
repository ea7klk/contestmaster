"""Run Alembic revisions before the API serves requests."""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from backend.app.db import build_engine

_BASELINE_REVISION = "0018_remove_unscored_country_data"
logger = logging.getLogger("contestmaster.migrations")


def upgrade_database() -> None:
    """Apply the baseline and pending revisions before serving API requests."""
    logger.info("database_upgrade_started")
    project_root = Path(__file__).resolve().parents[2]
    active_config = _config(project_root)
    active_revision_ids = {
        revision.revision
        for revision in ScriptDirectory.from_config(active_config).walk_revisions()
    }
    database_engine = build_engine()
    try:
        inspector = inspect(database_engine)
        if inspector.has_table("alembic_version"):
            with database_engine.connect() as connection:
                current_revision = connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            if current_revision and current_revision not in active_revision_ids:
                # One-time compatibility path for installations created before the
                # migration squash. These revisions are archived and are not part of
                # the active migration graph for new databases.
                logger.info(
                    "legacy_database_upgrade_started",
                    extra={"current_revision": current_revision},
                )
                legacy_config = _config(project_root, legacy=True)
                command.upgrade(legacy_config, "head")
                logger.info("legacy_database_upgrade_finished")
            elif current_revision == _BASELINE_REVISION:
                # This identifier was also the final revision in the archived graph.
                # The schemas match; applying active forward revisions upgrades such
                # databases without replaying the consolidated create-all baseline.
                logger.info(
                    "shared_legacy_baseline_detected",
                    extra={"current_revision": current_revision},
                )
            elif current_revision:
                logger.info(
                    "current_database_revision_detected",
                    extra={"current_revision": current_revision},
                )
    finally:
        database_engine.dispose()
    command.upgrade(active_config, "head")
    logger.info("database_upgrade_finished")


def _config(project_root: Path, *, legacy: bool = False) -> Config:
    config = Config(str(project_root / "alembic.ini"))
    # API startup already configures structured application logging. Alembic's
    # ini logging setup replaces root handlers and can hide Uvicorn readiness
    # messages after the migration finishes.
    config.attributes["configure_logger"] = False
    migration_root = project_root / "backend" / "migrations"
    if legacy:
        migration_root /= "legacy"
    config.set_main_option("script_location", str(migration_root))
    return config
