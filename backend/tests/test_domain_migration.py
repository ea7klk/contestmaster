import os
import subprocess
import sys

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.app.db import build_engine
from backend.app.models import BandCatalogItem, SystemRole, SystemUser


def _alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_python(database_url: str, code: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_single_baseline_migration_creates_current_schema_and_catalog(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'baseline.sqlite3'}"

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "check")

    engine = build_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "system_users",
        "system_sessions",
        "participant_sessions",
        "participants",
        "contests",
        "entries",
        "entry_revisions",
        "log_submission_requests",
        "qsos",
        "score_runs",
        "qso_scores",
        "cq_zones",
        "itu_zones",
        "contest_entities",
        "callsign_prefixes",
        "audit_events",
        "ruleset_activations",
        "result_publications",
        "result_publication_entries",
        "band_catalog_items",
        "mode_catalog_items",
    } <= tables
    assert "call_districts" not in tables
    assert "iaru_regions" not in tables
    assert "itu_radio_regions" not in tables
    assert "operating_catalog_items" not in tables
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0018_remove_unscored_country_data"
        )
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert (
            connection.scalar(text("SELECT count(*) FROM band_catalog_items WHERE is_active = 1"))
            == 25
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM band_catalog_items WHERE contest_free = 1")
            )
            == 6
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM band_catalog_items WHERE is_active = 1 AND key = '3cm'")
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM band_catalog_items WHERE is_active = 1 AND key = '1.25cm'"
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM mode_catalog_items WHERE key = 'FT8' AND is_active = 1")
            )
            == 1
        )
        triggers = set(
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).scalars()
        )
        assert {
            "immutable_ruleset_versions_update",
            "immutable_ruleset_versions_delete",
            "immutable_entry_revisions_update",
            "immutable_entry_revisions_delete",
            "immutable_ruleset_activations_update",
            "immutable_ruleset_activations_delete",
            "integer_score_run_detail_insert",
            "integer_score_run_detail_update",
            "immutable_completed_score_run",
            "immutable_result_publication_update",
            "prevent_active_master_data_version_delete",
        } <= triggers
    with Session(engine) as session:
        band = session.query(BandCatalogItem).filter_by(key="160m").one()
        assert band.description == "160 m HF band"
        user = SystemUser(
            username="kept-admin",
            email_normalized="kept-admin@example.test",
            display_name="Kept Admin",
            role=SystemRole.GLOBAL_ADMINISTRATOR,
            password_hash="test-hash",
            is_active=True,
        )
        session.add(user)
        session.commit()

    # Re-running the consolidated startup migration is safe and preserves application data.
    _alembic(database_url, "upgrade", "head")
    with Session(engine) as session:
        assert session.query(SystemUser).filter_by(username="kept-admin").count() == 1
    engine.dispose()


def test_migration_history_is_one_baseline_revision() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    config = Config(os.path.join(project_root, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(project_root, "backend", "migrations"))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert len(revisions) == 1
    assert revisions[0].down_revision is None
    assert revisions[0].revision == "0018_remove_unscored_country_data"


def test_startup_upgrades_pre_squash_database_without_losing_records(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    legacy_root = os.path.join(project_root, "backend", "migrations", "legacy")
    _run_python(
        database_url,
        "from alembic import command; from alembic.config import Config; "
        f"config = Config({os.path.join(project_root, 'alembic.ini')!r}); "
        f"config.set_main_option('script_location', {legacy_root!r}); "
        "command.upgrade(config, '0017_contest_free_band_defaults')",
    )
    engine = build_engine(database_url)
    with Session(engine) as session:
        session.add(
            SystemUser(
                username="legacy-admin",
                email_normalized="legacy-admin@example.test",
                display_name="Legacy Admin",
                role=SystemRole.GLOBAL_ADMINISTRATOR,
                password_hash="test-hash",
                is_active=True,
            )
        )
        session.commit()
    engine.dispose()

    _run_python(
        database_url, "from backend.app.migrations import upgrade_database; upgrade_database()"
    )

    engine = build_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0018_remove_unscored_country_data"
        )
    with Session(engine) as session:
        assert session.query(SystemUser).filter_by(username="legacy-admin").count() == 1
    engine.dispose()
