"""Add immutable result publication snapshots.

Revision ID: 0013_result_publications
Revises: 0012_adjudication_score_details
"""

import sqlalchemy as sa
from alembic import op

from backend.app.models.types import UTCDateTime

revision: str = "0013_result_publications"
down_revision: str | None = "0012_adjudication_score_details"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "entries",
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE entries SET status = 'accepted' "
        "WHERE status = 'received' AND EXISTS "
        "(SELECT 1 FROM entry_revisions WHERE entry_revisions.entry_id = entries.id)"
    )

    op.create_table(
        "result_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("publication_number", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("withheld_count", sa.Integer(), nullable=False),
        sa.Column("published_by_user_id", sa.Integer(), nullable=True),
        sa.Column("published_at", UTCDateTime(), nullable=False),
        sa.Column("is_sealed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("publication_number > 0", name="publication_number_positive"),
        sa.CheckConstraint(
            "entry_count >= 0 AND withheld_count >= 0", name="publication_counts_nonnegative"
        ),
        sa.CheckConstraint("length(source_digest) = 64", name="publication_digest_length"),
        sa.UniqueConstraint("contest_id", "publication_number", name="contest_publication_number"),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["system_users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_result_publications_contest_id", "result_publications", ["contest_id"])
    op.create_table(
        "result_publication_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("score_run_id", sa.Integer(), nullable=False),
        sa.Column("callsign", sa.String(length=32), nullable=False),
        sa.Column("category_values", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("multiplier_count", sa.Integer(), nullable=False),
        sa.Column("bonus_points", sa.Integer(), nullable=False),
        sa.Column("penalty_points", sa.Integer(), nullable=False),
        sa.Column("qso_count", sa.Integer(), nullable=False),
        sa.Column("credited_qso_count", sa.Integer(), nullable=False),
        sa.Column("placement", sa.Integer(), nullable=True),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.CheckConstraint("score >= 0", name="published_score_nonnegative"),
        sa.CheckConstraint(
            "points >= 0 AND multiplier_count >= 0 AND bonus_points >= 0 "
            "AND penalty_points >= 0 AND qso_count >= 0 AND credited_qso_count >= 0 "
            "AND (placement IS NULL OR placement > 0)",
            name="published_result_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "typeof(score) = 'integer' AND typeof(points) = 'integer' "
            "AND typeof(multiplier_count) = 'integer' AND typeof(bonus_points) = 'integer' "
            "AND typeof(penalty_points) = 'integer' AND typeof(qso_count) = 'integer' "
            "AND typeof(credited_qso_count) = 'integer'",
            name="published_result_integer_values",
        ),
        sa.UniqueConstraint("publication_id", "entry_id", name="publication_entry_unique"),
        sa.ForeignKeyConstraint(
            ["publication_id"], ["result_publications.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["entry_id"], ["entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["score_run_id"], ["score_runs.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_result_publication_entries_publication_id",
        "result_publication_entries",
        ["publication_id"],
    )
    op.create_index(
        "ix_result_publication_entries_entry_id",
        "result_publication_entries",
        ["entry_id"],
    )
    op.create_index(
        "ix_result_publication_entries_score_run_id",
        "result_publication_entries",
        ["score_run_id"],
    )
    op.execute(
        "CREATE TRIGGER immutable_result_publication_update "
        "BEFORE UPDATE ON result_publications WHEN OLD.is_sealed = 1 "
        "BEGIN SELECT RAISE(ABORT, 'sealed result publications are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER retain_result_publications BEFORE DELETE ON result_publications "
        "BEGIN SELECT RAISE(ABORT, 'result publications are retained for audit'); END"
    )
    op.execute(
        "CREATE TRIGGER no_entries_in_sealed_publication "
        "BEFORE INSERT ON result_publication_entries "
        "WHEN (SELECT is_sealed FROM result_publications WHERE id = NEW.publication_id) = 1 "
        "BEGIN SELECT RAISE(ABORT, 'sealed result publications are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_result_publication_entry_update "
        "BEFORE UPDATE ON result_publication_entries "
        "BEGIN SELECT RAISE(ABORT, 'published result entries are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER retain_result_publication_entries "
        "BEFORE DELETE ON result_publication_entries "
        "BEGIN SELECT RAISE(ABORT, 'published result entries are retained for audit'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS retain_result_publication_entries")
    op.execute("DROP TRIGGER IF EXISTS immutable_result_publication_entry_update")
    op.execute("DROP TRIGGER IF EXISTS no_entries_in_sealed_publication")
    op.execute("DROP TRIGGER IF EXISTS retain_result_publications")
    op.execute("DROP TRIGGER IF EXISTS immutable_result_publication_update")
    op.drop_index(
        "ix_result_publication_entries_score_run_id", table_name="result_publication_entries"
    )
    op.drop_index("ix_result_publication_entries_entry_id", table_name="result_publication_entries")
    op.drop_index(
        "ix_result_publication_entries_publication_id", table_name="result_publication_entries"
    )
    op.drop_table("result_publication_entries")
    op.drop_index("ix_result_publications_contest_id", table_name="result_publications")
    op.drop_table("result_publications")
    op.drop_column("entries", "is_late")
