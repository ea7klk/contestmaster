"""Add recurring contest series and edition identity.

Revision ID: 0022_recurring_contest_series
Revises: 0021_authorized_ruleset_deletion
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_recurring_contest_series"
down_revision: str | None = "0021_authorized_ruleset_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contest_series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("system_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_slug", sa.String(120, collation="NOCASE"), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("periodicity", sa.JSON(), nullable=False),
        sa.Column("start_time_seconds", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("cutoff_offset_seconds", sa.Integer(), nullable=False),
        sa.Column("automatic_window_days", sa.Integer()),
        sa.Column(
            "auto_recalculate_on_upload", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "ruleset_version_id",
            sa.Integer(),
            sa.ForeignKey("ruleset_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("updated_at", sa.String(27), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="contest_series_name_not_blank"),
        sa.CheckConstraint("length(trim(base_slug)) > 0", name="contest_series_slug_not_blank"),
        sa.CheckConstraint(
            "start_time_seconds >= 0 AND start_time_seconds < 86400",
            name="series_start_time_valid",
        ),
        sa.CheckConstraint("duration_seconds > 0", name="series_duration_positive"),
        sa.CheckConstraint(
            "cutoff_offset_seconds >= 0", name="series_cutoff_offset_nonnegative"
        ),
        sa.CheckConstraint(
            "automatic_window_days IS NULL OR automatic_window_days BETWEEN 1 AND 730",
            name="series_automatic_window_valid",
        ),
    )
    op.create_index("ix_contest_series_owner_user_id", "contest_series", ["owner_user_id"])
    op.create_table(
        "contest_series_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("contest_series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("moved_to_date", sa.Date()),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.UniqueConstraint("series_id", "occurrence_date", name="series_exception_date_unique"),
        sa.CheckConstraint("action IN ('skip', 'move')", name="series_exception_action_valid"),
        sa.CheckConstraint(
            "(action = 'skip' AND moved_to_date IS NULL) OR "
            "(action = 'move' AND moved_to_date IS NOT NULL)",
            name="series_exception_move_date_valid",
        ),
    )
    op.create_index(
        "ix_contest_series_exceptions_series_id", "contest_series_exceptions", ["series_id"]
    )
    with op.batch_alter_table("contests") as batch:
        batch.add_column(
            sa.Column(
                "series_id",
                sa.Integer(),
                sa.ForeignKey("contest_series.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("series_occurrence_date", sa.Date(), nullable=True))
        batch.add_column(
            sa.Column("is_series_anchor", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("cutoff_is_override", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_index("ix_contests_series_id", "contests", ["series_id"])
    op.create_index(
        "contest_series_occurrence_unique",
        "contests",
        ["series_id", "series_occurrence_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("contest_series_occurrence_unique", table_name="contests")
    op.drop_index("ix_contests_series_id", table_name="contests")
    with op.batch_alter_table("contests") as batch:
        batch.drop_column("cutoff_is_override")
        batch.drop_column("series_occurrence_date")
        batch.drop_column("is_series_anchor")
        batch.drop_column("series_id")
    op.drop_index("ix_contest_series_exceptions_series_id", table_name="contest_series_exceptions")
    op.drop_table("contest_series_exceptions")
    op.drop_index("ix_contest_series_owner_user_id", table_name="contest_series")
    op.drop_table("contest_series")
