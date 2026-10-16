"""Create the consolidated current Contestmaster schema.

Revision ID: 0018_remove_unscored_country_data
Revises:

This baseline deliberately retains the former head revision identifier so databases
already at that head remain recognized as current after the migration history is
squashed. New model changes must be introduced as separate Alembic revisions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from backend.app.db import Base

revision: str = "0018_remove_unscored_country_data"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BANDS = (
    ("2200m", "2200 m", "135.7–137.8 kHz", "2200 m LF band", True),
    ("630m", "630 m", "472–479 kHz", "630 m MF band", True),
    ("160m", "160 m", "1.8 MHz", "160 m HF band", True),
    ("80m", "80 m", "3.5 MHz", "80 m HF band", True),
    ("60m", "60 m", "5 MHz", "60 m HF band", True),
    ("40m", "40 m", "7 MHz", "40 m HF band", True),
    ("30m", "30 m", "10 MHz", "30 m HF band", True),
    ("20m", "20 m", "14 MHz", "20 m HF band", True),
    ("17m", "17 m", "18 MHz", "17 m HF band", True),
    ("15m", "15 m", "21 MHz", "15 m HF band", True),
    ("12m", "12 m", "24 MHz", "12 m HF band", True),
    ("10m", "10 m", "28 MHz", "10 m HF band", True),
    ("8m", "8 m", "40 MHz", "8 m VHF band", True),
    ("6m", "6 m", "50 MHz", "6 m VHF band", True),
    ("5m", "5 m", "60 MHz", "5 m VHF band", True),
    ("4m", "4 m", "70 MHz", "4 m VHF band", True),
    ("2m", "2 m", "144 MHz", "2 m VHF band", True),
    ("1.25m", "1.25 m", "220 MHz", "1.25 m VHF band", True),
    ("70cm", "70 cm", "430 MHz", "70 cm UHF band", True),
    ("33cm", "33 cm", "902 MHz", "33 cm UHF band", True),
    ("23cm", "23 cm", "1.2 GHz", "23 cm UHF band", True),
    ("13cm", "13 cm", "2.3 GHz", "13 cm SHF band", True),
    ("9cm", "9 cm", "3.4 GHz", "9 cm SHF band", True),
    ("6cm", "6 cm", "5.6 GHz", "6 cm SHF band", True),
    ("3cm", "3 cm", "10 GHz", "3 cm SHF band", True),
    ("1.25cm", "1.25 cm", "24 GHz", "1.25 cm SHF band", False),
    ("6mm", "6 mm", "47 GHz", "6 mm EHF band", False),
    ("4mm", "4 mm", "75 GHz", "4 mm EHF band", False),
    ("2.5mm", "2.5 mm", "122 GHz", "2.5 mm EHF band", False),
    ("2mm", "2 mm", "134 GHz", "2 mm EHF band", False),
    ("1mm", "1 mm", "241 GHz", "1 mm EHF band", False),
    ("0.5mm", "0.5 mm", "470 GHz", "0.5 mm submillimeter band", False),
    ("0.4mm", "0.4 mm", "750 GHz", "0.4 mm submillimeter band", False),
    ("0.2mm", "0.2 mm", "1.5 THz", "0.2 mm submillimeter band", False),
)
_MODES = (
    ("CW", "Morse code"),
    ("SSB", "Single-sideband voice"),
    ("AM", "Amplitude-modulated voice"),
    ("FM", "Frequency-modulated voice"),
    ("RTTY", "Radio teletype"),
    ("PSK31", "31-baud phase-shift keying"),
    ("PSK63", "63-baud phase-shift keying"),
    ("FT8", "Weak-signal digital mode"),
    ("FT4", "Fast weak-signal digital mode"),
    ("JT65", "Weak-signal digital mode"),
    ("JT9", "Weak-signal digital mode"),
    ("MSK144", "Meteor-scatter digital mode"),
    ("JS8", "Keyboard text messaging"),
    ("Olivia", "MFSK text mode"),
    ("MFSK", "Multi-frequency shift keying"),
    ("SSTV", "Slow-scan television"),
    ("D-STAR", "Digital voice and data"),
    ("C4FM", "Digital voice and data"),
    ("DMR", "Digital mobile radio"),
    ("Packet", "Packet radio"),
    ("Contestia", "Digital text mode"),
    ("Q65", "Weak-signal digital mode"),
    ("WSPR", "Weak-signal propagation beacon"),
)
_CONTEST_FREE_BANDS = {"2200m", "630m", "60m", "30m", "17m", "12m"}


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # This baseline predates contest periodicity. Keep its shape stable even
    # though its table definitions are sourced from the current ORM metadata;
    # revision 0019 adds the column for both fresh and existing installations.
    op.drop_column("contests", "periodicity")
    bind.execute(
        sa.insert(
            sa.table(
                "band_catalog_items",
                sa.column("key", sa.String()),
                sa.column("label", sa.String()),
                sa.column("description", sa.String()),
                sa.column("frequency_range", sa.String()),
                sa.column("sort_order", sa.Integer()),
                sa.column("is_active", sa.Boolean()),
                sa.column("contest_free", sa.Boolean()),
            )
        ),
        [
            {
                "key": key,
                "label": label,
                "description": description,
                "frequency_range": frequency,
                "sort_order": order,
                "is_active": active,
                "contest_free": key in _CONTEST_FREE_BANDS,
            }
            for order, (key, label, frequency, description, active) in enumerate(_BANDS)
        ],
    )
    bind.execute(
        sa.insert(
            sa.table(
                "mode_catalog_items",
                sa.column("key", sa.String()),
                sa.column("label", sa.String()),
                sa.column("description", sa.String()),
                sa.column("sort_order", sa.Integer()),
                sa.column("is_active", sa.Boolean()),
            )
        ),
        [
            {
                "key": key,
                "label": key,
                "description": description,
                "sort_order": order,
                "is_active": True,
            }
            for order, (key, description) in enumerate(_MODES)
        ],
    )
    _create_immutability_triggers(bind)


def _create_immutability_triggers(bind) -> None:
    for table in (
        "ruleset_versions",
        "entry_revisions",
        "stations",
        "qsos",
        "qso_decisions",
        "audit_events",
    ):
        for operation in ("UPDATE", "DELETE"):
            bind.exec_driver_sql(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} "
                f"BEFORE {operation} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} records are append-only'); END"
            )
    statements = (
        "CREATE TRIGGER immutable_ruleset_activations_update BEFORE UPDATE ON ruleset_activations "
        "BEGIN SELECT RAISE(ABORT, 'ruleset activation history is append-only'); END",
        "CREATE TRIGGER immutable_ruleset_activations_delete BEFORE DELETE ON ruleset_activations "
        "BEGIN SELECT RAISE(ABORT, 'ruleset activation history is append-only'); END",
        "CREATE TRIGGER prevent_active_master_data_version_delete "
        "BEFORE DELETE ON master_data_versions "
        "WHEN OLD.status = 'active' "
        "BEGIN SELECT RAISE(ABORT, 'active master data versions cannot be deleted'); END",
        "CREATE TRIGGER integer_score_run_detail_insert BEFORE INSERT ON score_runs "
        "WHEN typeof(NEW.bonus_points) != 'integer' OR NEW.bonus_points < 0 OR "
        "(NEW.adjudicated_score IS NOT NULL AND "
        "(typeof(NEW.adjudicated_score) != 'integer' OR NEW.adjudicated_score < 0)) "
        "BEGIN SELECT RAISE(ABORT, 'score details must be nonnegative integers'); END",
        "CREATE TRIGGER integer_score_run_detail_update BEFORE UPDATE ON score_runs "
        "WHEN typeof(NEW.bonus_points) != 'integer' OR NEW.bonus_points < 0 OR "
        "(NEW.adjudicated_score IS NOT NULL AND "
        "(typeof(NEW.adjudicated_score) != 'integer' OR NEW.adjudicated_score < 0)) "
        "BEGIN SELECT RAISE(ABORT, 'score details must be nonnegative integers'); END",
        "CREATE TRIGGER integer_qso_score_bonus_insert BEFORE INSERT ON qso_scores "
        "WHEN typeof(NEW.bonus_points) != 'integer' OR NEW.bonus_points < 0 "
        "BEGIN SELECT RAISE(ABORT, 'QSO bonus points must be a nonnegative integer'); END",
        "CREATE TRIGGER immutable_completed_score_run BEFORE UPDATE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score_runs are immutable'); END",
        "CREATE TRIGGER retain_score_runs BEFORE DELETE ON score_runs "
        "BEGIN SELECT RAISE(ABORT, 'score_runs are retained for audit'); END",
        "CREATE TRIGGER immutable_result_publication_update BEFORE UPDATE ON result_publications "
        "WHEN OLD.is_sealed = 1 "
        "BEGIN SELECT RAISE(ABORT, 'sealed result publications are immutable'); END",
        "CREATE TRIGGER retain_result_publications BEFORE DELETE ON result_publications "
        "BEGIN SELECT RAISE(ABORT, 'result publications are retained for audit'); END",
        "CREATE TRIGGER no_entries_in_sealed_publication "
        "BEFORE INSERT ON result_publication_entries "
        "WHEN (SELECT is_sealed FROM result_publications WHERE id = NEW.publication_id) = 1 "
        "BEGIN SELECT RAISE(ABORT, 'sealed result publications are immutable'); END",
        "CREATE TRIGGER immutable_result_publication_entry_update "
        "BEFORE UPDATE ON result_publication_entries "
        "BEGIN SELECT RAISE(ABORT, 'published result entries are immutable'); END",
        "CREATE TRIGGER retain_result_publication_entries "
        "BEFORE DELETE ON result_publication_entries "
        "BEGIN SELECT RAISE(ABORT, 'published result entries are retained for audit'); END",
        "CREATE TRIGGER completed_score_runs_update BEFORE UPDATE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score runs are immutable'); END",
        "CREATE TRIGGER completed_score_runs_delete BEFORE DELETE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score runs are immutable'); END",
    )
    for statement in statements:
        bind.exec_driver_sql(statement)
    for operation in ("INSERT", "UPDATE", "DELETE"):
        row = "OLD" if operation == "DELETE" else "NEW"
        bind.exec_driver_sql(
            f"CREATE TRIGGER completed_qso_scores_{operation.lower()} "
            f"BEFORE {operation} ON qso_scores "
            "WHEN EXISTS (SELECT 1 FROM score_runs "
            f"WHERE score_runs.id = {row}.score_run_id AND score_runs.status = 'completed') "
            "BEGIN SELECT RAISE(ABORT, 'completed score breakdowns are immutable'); END"
        )


def downgrade() -> None:
    raise RuntimeError(
        "The consolidated schema baseline is intentionally irreversible; restore a backup instead."
    )
