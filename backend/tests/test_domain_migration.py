import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db import build_engine
from backend.app.models import (
    AuditEvent,
    ContestEntity,
    EntityType,
    MasterDataAuthorityRole,
    MasterDataRunStatus,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    RulesetVersion,
)
from backend.app.models.types import utc_now


def test_empty_sqlite_database_upgrades_to_current_domain_schema(tmp_path) -> None:
    database_path = tmp_path / "phase2.sqlite3"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0001_foundation"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    engine = build_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
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
    assert "entity_iaru_region_assignments" not in tables
    assert "itu_radio_regions" not in tables
    assert "entity_itu_radio_region_assignments" not in tables
    assert "iaru_itu_radio_region_mappings" not in tables
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        seeded_bands = connection.exec_driver_sql(
            "SELECT count(*) FROM band_catalog_items WHERE is_active = 1"
        ).scalar_one()
        highest_band = connection.exec_driver_sql(
            "SELECT frequency_range FROM band_catalog_items ORDER BY sort_order DESC LIMIT 1"
        ).scalar_one()
        ft8 = connection.exec_driver_sql(
            "SELECT count(*) FROM mode_catalog_items WHERE key = 'FT8' AND is_active = 1"
        ).scalar_one()
    assert "operating_catalog_items" not in tables
    assert version == "0015_split_operating_catalogs"
    assert foreign_keys == 1
    assert seeded_bands >= 30
    assert highest_band == "1.4 THz"
    assert ft8 == 1
    assert {"category_values", "is_late"} <= {
        column["name"] for column in inspector.get_columns("entries")
    }
    assert {
        "original_content",
        "import_metadata",
        "received_by_participant_email_id",
        "received_via",
    } <= {column["name"] for column in inspector.get_columns("entry_revisions")}
    triggers = {
        row[0]
        for row in engine.connect().exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    assert "immutable_ruleset_versions_update" in triggers
    assert "immutable_entry_revisions_update" in triggers
    assert "immutable_entry_revisions_delete" in triggers
    assert "immutable_ruleset_activations_update" in triggers
    assert "immutable_ruleset_activations_delete" in triggers
    assert "immutable_audit_events_update" in triggers
    assert "immutable_audit_events_delete" in triggers
    assert "completed_score_runs_update" in triggers
    assert "immutable_qso_decisions_update" in triggers
    assert "immutable_qso_decisions_delete" in triggers
    assert "completed_qso_scores_insert" in triggers
    assert "completed_qso_scores_update" in triggers
    assert "completed_qso_scores_delete" in triggers
    assert "immutable_completed_score_run" in triggers
    assert "retain_score_runs" in triggers
    assert "integer_score_run_detail_insert" in triggers
    assert "integer_score_run_detail_update" in triggers
    assert "integer_qso_score_bonus_insert" in triggers
    assert "immutable_result_publication_update" in triggers
    assert "retain_result_publications" in triggers
    assert "no_entries_in_sealed_publication" in triggers
    assert "immutable_result_publication_entry_update" in triggers
    assert "retain_result_publication_entries" in triggers
    assert {
        "bonus_points",
        "adjudicated_score",
        "explanation",
    } <= {column["name"] for column in inspector.get_columns("score_runs")}
    assert {
        "bonus_points",
        "status",
        "reason_codes",
    } <= {column["name"] for column in inspector.get_columns("qso_scores")}
    assert "prevent_active_master_data_version_delete" in triggers

    with Session(engine) as session:
        ruleset = RulesetVersion(ruleset_key="initial", version="1")
        session.add(ruleset)
        session.commit()
        ruleset.version = "2"
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()
        session.rollback()
        event = AuditEvent(
            actor_user_id=None,
            action="test.recorded",
            target_type="contest",
            target_id="1",
            event_metadata={"source": "migration-test"},
        )
        session.add(event)
        session.commit()
        event.reason = "rewrite"
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()
        session.rollback()
        session.delete(event)
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()
        session.rollback()

        source = MasterDataSource(
            source_key="migration-active-source",
            name="Migration Active Source",
            canonical_url="https://example.test/master-data",
            authority_role=MasterDataAuthorityRole.PRIMARY_OPERATIONAL,
        )
        session.add(source)
        session.flush()
        run = MasterDataSyncRun(
            source_id=source.id,
            dataset_key="migration-active-dataset",
            status=MasterDataRunStatus.SUCCEEDED,
            source_release="test-release",
            checksum="a" * 64,
        )
        session.add(run)
        session.flush()
        active_version = MasterDataVersion(
            sync_run_id=run.id,
            dataset_key=run.dataset_key,
            retrieved_at=utc_now(),
            checksum=run.checksum,
            valid_from=utc_now(),
            status=MasterDataVersionStatus.ACTIVE,
        )
        session.add(active_version)
        session.commit()
        with pytest.raises(DBAPIError, match="active master data versions cannot be deleted"):
            session.execute(
                text("DELETE FROM master_data_versions WHERE id = :version_id"),
                {"version_id": active_version.id},
            )
        session.rollback()
    engine.dispose()


def test_operating_catalog_split_migration_preserves_band_and_mode_values(tmp_path) -> None:
    database_path = tmp_path / "catalog-split.sqlite3"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0014_operating_catalog"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = build_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO operating_catalog_items
                (kind, key, label, description, frequency_range, sort_order, is_active,
                contest_free)
                VALUES ('band', 'legacy-band', 'Legacy band', 'Preserve band details',
                '50 MHz', 77, 0, 1)"""
            )
        )
        connection.execute(
            text(
                """INSERT INTO operating_catalog_items
                (kind, key, label, description, frequency_range, sort_order, is_active,
                contest_free)
                VALUES ('mode', 'legacy-mode', 'Legacy mode', 'Preserve mode details',
                NULL, 88, 0, 0)"""
            )
        )
    with Session(engine) as session:
        session.add(
            RulesetVersion(
                ruleset_key="migration-reference",
                version="1",
                rule_type_keys=["eligibility"],
                configuration={
                    "rules": [
                        {
                            "rule": {
                                "kind": "eligibility",
                                "allowed_bands": ["legacy-band"],
                                "allowed_modes": ["legacy-mode"],
                            }
                        }
                    ]
                },
            )
        )
        session.commit()
    engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = build_engine(database_url)
    with engine.connect() as connection:
        band = connection.execute(
            text(
                "SELECT key, label, description, frequency_range, sort_order, is_active, "
                "contest_free "
                "FROM band_catalog_items WHERE key = 'legacy-band'"
            )
        ).one()
        mode = connection.execute(
            text(
                "SELECT key, label, description, sort_order, is_active "
                "FROM mode_catalog_items WHERE key = 'legacy-mode'"
            )
        ).one()
        assert "operating_catalog_items" not in inspect(connection).get_table_names()
    with Session(engine) as session:
        migrated_ruleset = session.scalar(
            select(RulesetVersion).where(RulesetVersion.ruleset_key == "migration-reference")
        )
        assert migrated_ruleset.configuration["rules"][0]["rule"]["allowed_bands"] == [
            "legacy-band"
        ]
        assert migrated_ruleset.configuration["rules"][0]["rule"]["allowed_modes"] == [
            "legacy-mode"
        ]
    assert tuple(band) == (
        "legacy-band",
        "Legacy band",
        "Preserve band details",
        "50 MHz",
        77,
        0,
        1,
    )
    assert tuple(mode) == ("legacy-mode", "Legacy mode", "Preserve mode details", 88, 0)
    engine.dispose()


def test_fcc_call_area_data_is_removed_by_schema_migration(tmp_path) -> None:
    database_path = tmp_path / "fcc-removal.sqlite3"
    database_url = f"sqlite:///{database_path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0003_master_data_intervals"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    engine = build_engine(database_url)
    with Session(engine) as session:
        source = MasterDataSource(
            source_key="fcc-uls-amateur",
            name="FCC ULS Amateur Radio Licenses",
            canonical_url="https://example.test/l_amat.zip",
            source_priority=50,
            authority_role=MasterDataAuthorityRole.GOVERNING_AUTHORITY,
            enabled=True,
        )
        session.add(source)
        session.flush()
        run = MasterDataSyncRun(
            source_id=source.id,
            dataset_key="call-districts-us",
            status=MasterDataRunStatus.SUCCEEDED,
            started_at=utc_now(),
            record_counts={"districts": 10},
        )
        session.add(run)
        session.flush()
        version = MasterDataVersion(
            sync_run_id=run.id,
            dataset_key="call-districts-us",
            retrieved_at=utc_now(),
            checksum="a" * 64,
            status=MasterDataVersionStatus.ACTIVE,
        )
        session.add(version)
        session.flush()
        entity = ContestEntity(
            version_id=version.id,
            namespace="ISO3166-1-alpha2",
            authority_code="US",
            name="United States",
            entity_type=EntityType.SOVEREIGN_COUNTRY,
        )
        session.add(entity)
        session.flush()
        session.execute(
            text(
                "INSERT INTO call_districts "
                "(version_id, entity_id, district_code, name, source_id) "
                "VALUES (:version_id, :entity_id, '0', 'United States call area 0', :source_id)"
            ),
            {"version_id": version.id, "entity_id": entity.id, "source_id": source.id},
        )
        session.commit()
    engine.dispose()

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = build_engine(database_url)
    inspector = inspect(engine)
    assert "call_districts" not in inspector.get_table_names()
    with Session(engine) as session:
        assert session.query(MasterDataSource).filter_by(source_key="fcc-uls-amateur").count() == 0
        assert (
            session.query(MasterDataVersion).filter_by(dataset_key="call-districts-us").count() == 0
        )
    engine.dispose()
