import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import build_engine
from backend.app.migrations import _config
from backend.app.models import (
    AuditEvent,
    BandCatalogItem,
    Contest,
    ContestSeries,
    ContestSeriesException,
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
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=project_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)


def _run_python(database_url: str, code: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)


def _insert_legacy_system_user(engine, *, username: str, email: str, role: str) -> int:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "INSERT INTO system_users "
                "(username, email_normalized, display_name, role, password_hash, is_active, "
                "created_at, updated_at) "
                "VALUES (:username, :email, :display, :role, 'test-hash', 1, "
                "'2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:00.000000Z')"
            ),
            {"username": username, "email": email, "display": username, "role": role},
        )
        return result.lastrowid


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
        "contest_series",
        "contest_series_exceptions",
        "participant_callsigns",
        "participant_email_changes",
        "participant_password_resets",
        "system_password_resets",
        "contest_administrators",
        "rulesets",
        "ruleset_administrators",
        "contest_deletion_permits",
        "ruleset_deletion_permits",
        "entries",
        "guest_entry_emails",
        "guest_entry_email_verifications",
        "email_outbox",
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
    assert "session_number" in {
        column["name"] for column in inspect(engine).get_columns("qso_scores")
    }
    system_user_columns = {
        column["name"]: column for column in inspect(engine).get_columns("system_users")
    }
    assert system_user_columns["must_change_password"]["default"].strip("'") in {
        "0",
        "false",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0028_scoring_session_numbers"
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM system_users WHERE must_change_password != 0")
            )
            == 0
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
        assert "immutable_audit_events_update" in triggers
        assert "immutable_audit_events_delete" in triggers
        assert {
            "immutable_ruleset_versions_update",
            "immutable_entry_revisions_update",
            "immutable_ruleset_activations_update",
            "guard_entry_revisions_delete",
            "guard_stations_delete",
            "guard_qsos_delete",
            "guard_qso_decisions_update",
            "guard_qso_decisions_delete",
            "guard_ruleset_activations_delete",
            "guard_ruleset_versions_delete",
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
        assert (
            not {
                "immutable_ruleset_versions_delete",
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
            }
            & triggers
        )
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


def test_migrated_audit_trigger_allows_only_expired_event_deletion(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'audit-retention.sqlite3'}"
    _alembic(database_url, "upgrade", "head")
    engine = build_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory.begin() as session:
        recent = AuditEvent(
            action="recent",
            target_type="test",
            target_id="1",
            event_metadata={},
            occurred_at=now - timedelta(days=89),
        )
        expired = AuditEvent(
            action="expired",
            target_type="test",
            target_id="2",
            event_metadata={},
            occurred_at=now - timedelta(days=91),
        )
        session.add_all([recent, expired])
        session.flush()
        recent_id, expired_id = recent.id, expired.id
    try:
        with factory() as session:
            with pytest.raises(IntegrityError, match="audit_events within retention"):
                session.execute(delete(AuditEvent).where(AuditEvent.id == recent_id))
            session.rollback()
        with factory.begin() as session:
            session.execute(delete(AuditEvent).where(AuditEvent.id == expired_id))
        with factory() as session:
            assert session.get(AuditEvent, recent_id) is not None
            assert session.get(AuditEvent, expired_id) is None
    finally:
        engine.dispose()


def test_guest_email_locale_migration_adds_supported_language_column(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'guest-email-locale.sqlite3'}"
    _alembic(database_url, "upgrade", "0025_initial_password_change")
    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "check")

    engine = build_engine(database_url)
    columns = {
        column["name"]: column for column in inspect(engine).get_columns("guest_entry_emails")
    }
    assert columns["locale"]["nullable"] is False
    assert columns["locale"]["default"].strip("'") == "en"
    checks = inspect(engine).get_check_constraints("guest_entry_emails")
    assert any((item["name"] or "").endswith("guest_entry_email_locale") for item in checks)
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


def test_ruleset_deletion_permit_is_added_by_forward_migration(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'ruleset-deletion-permit.sqlite3'}"

    _alembic(database_url, "upgrade", "0020_authorized_contest_deletion")
    engine = build_engine(database_url)
    assert "ruleset_deletion_permits" not in set(inspect(engine).get_table_names())
    engine.dispose()

    _alembic(database_url, "upgrade", "head")
    engine = build_engine(database_url)
    assert "ruleset_deletion_permits" in set(inspect(engine).get_table_names())
    engine.dispose()


def test_migration_history_has_one_baseline_and_forward_migrations() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    config = Config(os.path.join(project_root, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(project_root, "backend", "migrations"))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert len(revisions) == 11
    assert revisions[0].revision == "0028_scoring_session_numbers"
    assert revisions[0].down_revision == "0027_audit_event_retention"
    assert revisions[1].revision == "0027_audit_event_retention"
    assert revisions[1].down_revision == "0026_guest_email_locale"
    assert revisions[2].revision == "0026_guest_email_locale"
    assert revisions[2].down_revision == "0025_initial_password_change"
    assert revisions[3].revision == "0025_initial_password_change"
    assert revisions[3].down_revision == "0024_guest_email_access_and_notices"
    assert revisions[4].revision == "0024_guest_email_access_and_notices"
    assert revisions[4].down_revision == "0023_participant_accounts_and_shared_iam"
    assert revisions[5].revision == "0023_participant_accounts_and_shared_iam"
    assert revisions[5].down_revision == "0022_recurring_contest_series"
    assert revisions[6].revision == "0022_recurring_contest_series"
    assert revisions[6].down_revision == "0021_authorized_ruleset_deletion"
    assert revisions[7].revision == "0021_authorized_ruleset_deletion"
    assert revisions[7].down_revision == "0020_authorized_contest_deletion"
    assert revisions[8].revision == "0020_authorized_contest_deletion"
    assert revisions[8].down_revision == "0019_contest_periodicity"
    assert revisions[9].revision == "0019_contest_periodicity"
    assert revisions[9].down_revision == "0018_remove_unscored_country_data"
    assert revisions[10].down_revision is None
    assert revisions[10].revision == "0018_remove_unscored_country_data"


def test_recurring_series_migration_preserves_existing_contest_references(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'populated-series-upgrade.sqlite3'}"
    _alembic(database_url, "upgrade", "0021_authorized_ruleset_deletion")

    engine = build_engine(database_url)
    manager_id = _insert_legacy_system_user(
        engine,
        username="migration-series-manager",
        email="migration-series-manager@example.test",
        role="contest_manager",
    )

    with engine.begin() as connection:
        contest_result = connection.execute(
            text(
                "INSERT INTO contests "
                "(owner_user_id, name, slug, starts_at, ends_at, "
                "log_submission_cutoff_at, status, auto_recalculate_on_upload, "
                "created_at, updated_at) "
                "VALUES (:owner_id, 'Existing Contest', 'existing-contest', "
                "'2026-06-01T12:00:00.000000Z', '2026-06-01T18:00:00.000000Z', "
                "'2026-06-03T18:00:00.000000Z', 'draft', 0, "
                "'2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:00.000000Z')"
            ),
            {"owner_id": manager_id},
        )
        contest_id = contest_result.lastrowid
        participant_result = connection.execute(
            text(
                "INSERT INTO participants (display_name, callsign_submitted, "
                "callsign_normalized, created_at) VALUES "
                "('Existing Entrant', 'K1TEST', 'K1TEST', '2026-01-01T00:00:00.000000Z')"
            )
        )
        participant_id = participant_result.lastrowid
        entry_result = connection.execute(
            text(
                "INSERT INTO entries (contest_id, participant_id, entry_key, "
                "category_values, is_late, status, submitted_at, created_at) "
                "VALUES (:contest_id, :participant_id, 'k1test-entry', '{}', 0, 'received', "
                "'2026-06-02T00:00:00.000000Z', '2026-06-02T00:00:00.000000Z')"
            ),
            {"contest_id": contest_id, "participant_id": participant_id},
        )
        entry_id = entry_result.lastrowid

    # A previous 0022 attempt can leave the series tables and SQLite's
    # temporary batch-copy table behind after failing to drop `contests`.
    with engine.begin() as connection:
        ContestSeries.__table__.create(connection)
        ContestSeriesException.__table__.create(connection)
        connection.exec_driver_sql(
            "CREATE TABLE _alembic_tmp_contests (id INTEGER PRIMARY KEY, "
            "series_id INTEGER REFERENCES contest_series(id))"
        )
        connection.execute(
            text("INSERT INTO _alembic_tmp_contests (id, series_id) VALUES (:id, NULL)"),
            {"id": contest_id},
        )

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "check")

    with engine.connect() as connection:
        contest = connection.execute(
            text(
                "SELECT series_id, is_series_anchor, cutoff_is_override "
                "FROM contests WHERE id = :contest_id"
            ),
            {"contest_id": contest_id},
        ).one()
        assert contest == (None, 0, 0)
        assert (
            connection.scalar(
                text("SELECT count(*) FROM entries WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )
            == 1
        )
        series_foreign_key = next(
            row
            for row in connection.exec_driver_sql("PRAGMA foreign_key_list(contests)").all()
            if row[3] == "series_id"
        )
        assert series_foreign_key[2:7] == (
            "contest_series",
            "series_id",
            "id",
            "NO ACTION",
            "RESTRICT",
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []

    _alembic(database_url, "downgrade", "0021_authorized_ruleset_deletion")
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM entries WHERE id = :entry_id"),
                {"entry_id": entry_id},
            )
            == 1
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "check")

    engine.dispose()


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
    _insert_legacy_system_user(
        engine,
        username="legacy-admin",
        email="legacy-admin@example.test",
        role="global_administrator",
    )
    engine.dispose()
    _run_python(
        database_url, "from backend.app.migrations import upgrade_database; upgrade_database()"
    )
    _alembic(database_url, "check")

    engine = build_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0028_scoring_session_numbers"
        )
    with Session(engine) as session:
        legacy_user = session.query(SystemUser).filter_by(username="legacy-admin").one()
        assert legacy_user.must_change_password is False
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
            "0028_scoring_session_numbers"
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
    actor_id = _insert_legacy_system_user(
        engine,
        username="shared-baseline-admin",
        email="shared-baseline@example.test",
        role="global_administrator",
    )
    with Session(engine) as session:
        legacy_configuration = {
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
        }
        # This fixture intentionally targets the pre-IAM legacy schema, whose
        # ruleset_versions table does not yet have the new ruleset_id column.
        ruleset_id = session.execute(
            text(
                "INSERT INTO ruleset_versions "
                "(ruleset_key, version, rule_type_keys, configuration, "
                "created_by_user_id, created_at) "
                "VALUES (:key, :version, :types, :configuration, :creator, :created)"
            ),
            {
                "key": "shared-baseline-schedule",
                "version": "2025",
                "types": json.dumps(["schedule"]),
                "configuration": json.dumps(legacy_configuration),
                "creator": actor_id,
                "created": datetime.now(UTC).isoformat(),
            },
        ).lastrowid
        session.commit()

    # The pre-squash Contest table has no `periodicity` column yet, so use a
    # Core insert that writes only columns present in both schema versions.
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "INSERT INTO contests "
                "(owner_user_id, ruleset_version_id, name, slug, starts_at, ends_at, "
                "log_submission_cutoff_at, status, auto_recalculate_on_upload, "
                "created_at, updated_at) "
                "VALUES (:owner_user_id, :ruleset_version_id, :name, :slug, :starts_at, "
                ":ends_at, :cutoff, :status, 0, :created_at, :updated_at)"
            ),
            {
                "owner_user_id": actor_id,
                "ruleset_version_id": ruleset_id,
                "name": "Shared Baseline Contest",
                "slug": "shared-baseline-contest",
                "starts_at": "2025-06-21T00:00:00.000000Z",
                "ends_at": "2025-06-21T02:00:00.000000Z",
                "cutoff": "2025-06-28T00:00:00.000000Z",
                "status": "draft",
                "created_at": "2025-06-21T00:00:00.000000Z",
                "updated_at": "2025-06-21T00:00:00.000000Z",
            },
        )
        contest_id = result.lastrowid
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
            "0028_scoring_session_numbers"
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
