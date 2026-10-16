import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert, inspect, text
from sqlalchemy.orm import Session

from backend.app.db import build_engine
from backend.app.migrations import _config
from backend.app.models import (
    BandCatalogItem,
    Contest,
    ContestStatus,
    RulesetVersion,
    SystemRole,
    SystemUser,
)


def test_api_migration_config_preserves_application_logging() -> None:
    config = _config(Path(__file__).resolve().parents[2])
    legacy_config = _config(Path(__file__).resolve().parents[2], legacy=True)

    assert config.attributes["configure_logger"] is False
    assert legacy_config.attributes["configure_logger"] is False


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
        "contest_deletion_permits",
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
            "0020_authorized_contest_deletion"
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
            "immutable_ruleset_activations_update",
            "guard_entry_revisions_delete",
            "guard_stations_delete",
            "guard_qsos_delete",
            "guard_qso_decisions_update",
            "guard_qso_decisions_delete",
            "guard_ruleset_activations_delete",
            "guard_score_runs_delete",
            "guard_qso_scores_delete",
            "guard_result_publications_delete",
            "guard_result_publication_entries_delete",
            "integer_score_run_detail_insert",
            "integer_score_run_detail_update",
            "immutable_completed_score_run",
            "immutable_result_publication_update",
            "prevent_active_master_data_version_delete",
        } <= triggers
        assert not {
            "immutable_entry_revisions_delete",
            "immutable_stations_delete",
            "immutable_qsos_delete",
            "immutable_qso_decisions_delete",
            "immutable_ruleset_activations_delete",
            "retain_score_runs",
            "completed_score_runs_delete",
            "completed_qso_scores_delete",
            "retain_result_publications",
            "retain_result_publication_entries",
        } & triggers
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


def test_contest_deletion_permit_is_added_by_forward_migration(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'contest-deletion-permit.sqlite3'}"

    _alembic(database_url, "upgrade", "0019_contest_periodicity")
    engine = build_engine(database_url)
    assert "contest_deletion_permits" not in set(inspect(engine).get_table_names())
    engine.dispose()

    _alembic(database_url, "upgrade", "head")
    engine = build_engine(database_url)
    assert "contest_deletion_permits" in set(inspect(engine).get_table_names())
    engine.dispose()


def test_migration_history_has_one_baseline_and_forward_migration() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    config = Config(os.path.join(project_root, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(project_root, "backend", "migrations"))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert len(revisions) == 3
    assert revisions[0].revision == "0020_authorized_contest_deletion"
    assert revisions[0].down_revision == "0019_contest_periodicity"
    assert revisions[1].revision == "0019_contest_periodicity"
    assert revisions[1].down_revision == "0018_remove_unscored_country_data"
    assert revisions[2].down_revision is None
    assert revisions[2].revision == "0018_remove_unscored_country_data"


def test_periodicity_migration_copies_legacy_ruleset_recurrence(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'periodicity.sqlite3'}"
    _alembic(database_url, "upgrade", "head")
    engine = build_engine(database_url)
    with Session(engine) as session:
        actor = SystemUser(
            username="migration-manager",
            email_normalized="migration-manager@example.test",
            display_name="Migration Manager",
            role=SystemRole.CONTEST_MANAGER,
            password_hash="test-hash",
        )
        session.add(actor)
        session.flush()
        ruleset = RulesetVersion(
            ruleset_key="legacy-scheduled",
            version="2025",
            rule_type_keys=["schedule", "submission"],
            configuration={
                "schema_version": 1,
                "rules": [
                    {
                        "id": "schedule",
                        "rule": {
                            "kind": "schedule",
                            "recurrence": {
                                "frequency": "nth_weekday",
                                "month": 6,
                                "weekday": 5,
                                "occurrence": 3,
                            },
                        },
                    }
                ],
            },
            created_by_user_id=actor.id,
        )
        session.add(ruleset)
        session.flush()
        contest = Contest(
            owner_user_id=actor.id,
            ruleset_version_id=ruleset.id,
            name="Legacy Scheduled Contest",
            slug="legacy-scheduled-contest",
            starts_at=datetime(2025, 6, 21, tzinfo=UTC),
            ends_at=datetime(2025, 6, 21, 2, tzinfo=UTC),
            log_submission_cutoff_at=datetime(2025, 6, 28, tzinfo=UTC),
        )
        session.add(contest)
        session.commit()
        contest_id = contest.id
    engine.dispose()

    _alembic(database_url, "downgrade", "0018_remove_unscored_country_data")
    _alembic(database_url, "upgrade", "head")

    engine = build_engine(database_url)
    with Session(engine) as session:
        migrated = session.get(Contest, contest_id)
        assert migrated is not None
        assert migrated.periodicity == {
            "frequency": "nth_weekday",
            "month": 6,
            "weekday": 5,
            "occurrence": 3,
        }
    engine.dispose()


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
    _alembic(database_url, "check")

    engine = build_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0020_authorized_contest_deletion"
        )
    with Session(engine) as session:
        assert session.query(SystemUser).filter_by(username="legacy-admin").count() == 1
    engine.dispose()


def test_startup_does_not_send_current_revision_to_legacy_graph(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'already-current.sqlite3'}"
    _alembic(database_url, "upgrade", "head")

    _run_python(
        database_url, "from backend.app.migrations import upgrade_database; upgrade_database()"
    )
    _alembic(database_url, "check")

    engine = build_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0020_authorized_contest_deletion"
        )
    engine.dispose()


def test_startup_upgrades_legacy_database_at_shared_baseline_revision(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'shared-baseline.sqlite3'}"
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    legacy_root = os.path.join(project_root, "backend", "migrations", "legacy")
    _run_python(
        database_url,
        "from alembic import command; from alembic.config import Config; "
        f"config = Config({os.path.join(project_root, 'alembic.ini')!r}); "
        f"config.set_main_option('script_location', {legacy_root!r}); "
        "command.upgrade(config, '0018_remove_unscored_country_data')",
    )
    engine = build_engine(database_url)
    with Session(engine) as session:
        actor = SystemUser(
            username="shared-baseline-admin",
            email_normalized="shared-baseline@example.test",
            display_name="Shared Baseline Admin",
            role=SystemRole.GLOBAL_ADMINISTRATOR,
            password_hash="test-hash",
            is_active=True,
        )
        session.add(actor)
        session.flush()
        ruleset = RulesetVersion(
            ruleset_key="shared-baseline-schedule",
            version="2025",
            rule_type_keys=["schedule"],
            configuration={
                "schema_version": 1,
                "rules": [
                    {
                        "id": "schedule",
                        "rule": {
                            "kind": "schedule",
                            "recurrence": {
                                "frequency": "nth_weekday",
                                "month": 6,
                                "weekday": 5,
                                "occurrence": 3,
                            },
                        },
                    }
                ],
            },
            created_by_user_id=actor.id,
        )
        session.add(ruleset)
        session.flush()
        actor_id = actor.id
        ruleset_id = ruleset.id
        session.commit()

    # The pre-squash Contest table has no `periodicity` column yet, so use a
    # Core insert that writes only columns present in both schema versions.
    with engine.begin() as connection:
        result = connection.execute(
            insert(Contest.__table__).values(
                owner_user_id=actor_id,
                ruleset_version_id=ruleset_id,
                name="Shared Baseline Contest",
                slug="shared-baseline-contest",
                starts_at=datetime(2025, 6, 21, tzinfo=UTC),
                ends_at=datetime(2025, 6, 21, 2, tzinfo=UTC),
                log_submission_cutoff_at=datetime(2025, 6, 28, tzinfo=UTC),
                status=ContestStatus.DRAFT,
            )
        )
        contest_id = result.inserted_primary_key[0]
    engine.dispose()

    _run_python(
        database_url, "from backend.app.migrations import upgrade_database; upgrade_database()"
    )

    _alembic(database_url, "check")
    engine = build_engine(database_url)
    columns = {column["name"] for column in inspect(engine).get_columns("contests")}
    assert "periodicity" in columns
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0020_authorized_contest_deletion"
        )
    with Session(engine) as session:
        assert session.query(SystemUser).filter_by(username="shared-baseline-admin").count() == 1
        migrated = session.get(Contest, contest_id)
        assert migrated is not None
        assert migrated.name == "Shared Baseline Contest"
        assert migrated.periodicity == {
            "frequency": "nth_weekday",
            "month": 6,
            "weekday": 5,
            "occurrence": 3,
        }
        assert session.get(RulesetVersion, ruleset_id) is not None
    engine.dispose()
