"""Add complete score detail and protect completed adjudication records.

Revision ID: 0012_adjudication_score_details
Revises: 0011_guest_log_submissions
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0012_adjudication_score_details"
down_revision: str | None = "0011_guest_log_submissions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Use in-place additions: rebuilding score_runs temporarily removes a table
    # referenced by existing SQLite QSO-score triggers.
    op.add_column(
        "score_runs", sa.Column("bonus_points", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("score_runs", sa.Column("adjudicated_score", sa.Integer(), nullable=True))
    op.add_column(
        "score_runs", sa.Column("explanation", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column(
        "qso_scores", sa.Column("bonus_points", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "qso_scores",
        sa.Column("status", sa.String(length=24), nullable=False, server_default="credited"),
    )
    op.add_column(
        "qso_scores", sa.Column("reason_codes", sa.JSON(), nullable=False, server_default="[]")
    )
    op.execute(
        "CREATE TRIGGER integer_score_run_detail_insert BEFORE INSERT ON score_runs "
        "WHEN typeof(NEW.bonus_points) != 'integer' OR NEW.bonus_points < 0 OR "
        "(NEW.adjudicated_score IS NOT NULL AND "
        "(typeof(NEW.adjudicated_score) != 'integer' OR NEW.adjudicated_score < 0)) "
        "BEGIN SELECT RAISE(ABORT, 'score details must be nonnegative integers'); END"
    )
    op.execute(
        "CREATE TRIGGER integer_score_run_detail_update BEFORE UPDATE ON score_runs "
        "WHEN typeof(NEW.bonus_points) != 'integer' OR NEW.bonus_points < 0 OR "
        "(NEW.adjudicated_score IS NOT NULL AND "
        "(typeof(NEW.adjudicated_score) != 'integer' OR NEW.adjudicated_score < 0)) "
        "BEGIN SELECT RAISE(ABORT, 'score details must be nonnegative integers'); END"
    )
    op.execute(
        "CREATE TRIGGER integer_qso_score_bonus_insert BEFORE INSERT ON qso_scores "
        "WHEN typeof(NEW.bonus_points) != 'integer' OR NEW.bonus_points < 0 "
        "BEGIN SELECT RAISE(ABORT, 'QSO bonus points must be a nonnegative integer'); END"
    )

    op.execute(
        "CREATE TRIGGER immutable_completed_score_run BEFORE UPDATE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score_runs are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER retain_score_runs BEFORE DELETE ON score_runs "
        "BEGIN SELECT RAISE(ABORT, 'score_runs are retained for audit'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS integer_qso_score_bonus_insert")
    op.execute("DROP TRIGGER IF EXISTS integer_score_run_detail_update")
    op.execute("DROP TRIGGER IF EXISTS integer_score_run_detail_insert")
    op.execute("DROP TRIGGER IF EXISTS retain_score_runs")
    op.execute("DROP TRIGGER IF EXISTS immutable_completed_score_run")
    op.drop_column("qso_scores", "reason_codes")
    op.drop_column("qso_scores", "status")
    op.drop_column("qso_scores", "bonus_points")
    op.drop_column("score_runs", "adjudicated_score")
    op.drop_column("score_runs", "explanation")
    op.drop_column("score_runs", "bonus_points")
