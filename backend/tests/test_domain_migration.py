import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db import build_engine
from backend.app.models import RulesetVersion


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
        "participants",
        "contests",
        "entries",
        "entry_revisions",
        "qsos",
        "score_runs",
        "qso_scores",
        "cq_zones",
        "itu_zones",
        "iaru_regions",
        "contest_entities",
        "callsign_prefixes",
        "call_districts",
        "audit_events",
    } <= tables
    with engine.connect() as connection:
        version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
    assert version == "833dcfe825b9"
    assert foreign_keys == 1
    triggers = {
        row[0]
        for row in engine.connect().exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    assert "immutable_ruleset_versions_update" in triggers
    assert "completed_score_runs_update" in triggers

    with Session(engine) as session:
        ruleset = RulesetVersion(ruleset_key="initial", version="1")
        session.add(ruleset)
        session.commit()
        ruleset.version = "2"
        with pytest.raises(DBAPIError, match="append-only"):
            session.commit()
    engine.dispose()
