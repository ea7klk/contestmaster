"""Add effective master-data intervals and immutable contest/score pins.

Revision ID: 0003_master_data_intervals
Revises: 833dcfe825b9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_master_data_intervals"
down_revision: str | None = "833dcfe825b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("contest_entities") as batch:
        batch.add_column(sa.Column("continent", sa.String(length=2), nullable=True))
        batch.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch.add_column(sa.Column("utc_offset", sa.Float(), nullable=True))
    with op.batch_alter_table("callsign_prefixes") as batch:
        batch.add_column(sa.Column("continent_override", sa.String(length=2), nullable=True))
        batch.add_column(sa.Column("latitude_override", sa.Float(), nullable=True))
        batch.add_column(sa.Column("longitude_override", sa.Float(), nullable=True))
        batch.add_column(sa.Column("utc_offset_override", sa.Float(), nullable=True))
    with op.batch_alter_table("master_data_versions") as batch:
        batch.drop_constraint("master_data_dataset_checksum_unique", type_="unique")
    op.create_index(
        "uq_master_data_running_source_dataset",
        "master_data_sync_runs",
        ["source_id", "dataset_key"],
        unique=True,
        sqlite_where=sa.text("status = 'running'"),
    )
    with op.batch_alter_table("master_data_versions") as batch:
        batch.add_column(sa.Column("valid_from", sa.String(length=27), nullable=True))
        batch.add_column(sa.Column("valid_to", sa.String(length=27), nullable=True))
        batch.create_unique_constraint(
            "master_data_version_id_dataset_unique", ["id", "dataset_key"]
        )
        batch.create_check_constraint(
            "effective_interval_positive", "valid_to IS NULL OR valid_from < valid_to"
        )
    op.execute(
        "UPDATE master_data_versions SET valid_from = "
        "COALESCE(activated_at, created_at, retrieved_at) WHERE valid_from IS NULL"
    )
    with op.batch_alter_table("master_data_versions") as batch:
        batch.alter_column("valid_from", existing_type=sa.String(length=27), nullable=False)

    with op.batch_alter_table("master_data_sync_runs") as batch:
        batch.add_column(sa.Column("change_detected", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("source_url", sa.String(length=2048), nullable=True))

    op.create_table(
        "contest_master_data_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("dataset_key", sa.String(length=100), nullable=False),
        sa.Column("master_data_version_id", sa.Integer(), nullable=False),
        sa.Column("pinned_at", sa.String(length=27), nullable=False),
        sa.ForeignKeyConstraint(
            ["contest_id"], ["contests.id"], ondelete="RESTRICT", name="fk_contest_md_contest"
        ),
        sa.ForeignKeyConstraint(
            ["master_data_version_id", "dataset_key"],
            ["master_data_versions.id", "master_data_versions.dataset_key"],
            ondelete="RESTRICT",
            name="contest_master_data_version_dataset_fk",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contest_id", "dataset_key", name="contest_dataset_version_unique"),
    )
    op.create_index(
        "ix_contest_master_data_versions_contest_id",
        "contest_master_data_versions",
        ["contest_id"],
    )
    op.create_index(
        "ix_contest_master_data_versions_master_data_version_id",
        "contest_master_data_versions",
        ["master_data_version_id"],
    )

    op.create_table(
        "score_run_master_data_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("score_run_id", sa.Integer(), nullable=False),
        sa.Column("dataset_key", sa.String(length=100), nullable=False),
        sa.Column("master_data_version_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["score_run_id"], ["score_runs.id"], ondelete="RESTRICT", name="fk_score_md_run"
        ),
        sa.ForeignKeyConstraint(
            ["master_data_version_id", "dataset_key"],
            ["master_data_versions.id", "master_data_versions.dataset_key"],
            ondelete="RESTRICT",
            name="score_run_master_data_version_dataset_fk",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("score_run_id", "dataset_key", name="score_run_dataset_version_unique"),
    )
    op.create_index(
        "ix_score_run_master_data_versions_score_run_id",
        "score_run_master_data_versions",
        ["score_run_id"],
    )
    op.create_index(
        "ix_score_run_master_data_versions_master_data_version_id",
        "score_run_master_data_versions",
        ["master_data_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_score_run_master_data_versions_master_data_version_id",
        table_name="score_run_master_data_versions",
    )
    op.drop_index(
        "ix_score_run_master_data_versions_score_run_id",
        table_name="score_run_master_data_versions",
    )
    op.drop_table("score_run_master_data_versions")
    op.drop_index(
        "ix_contest_master_data_versions_master_data_version_id",
        table_name="contest_master_data_versions",
    )
    op.drop_index(
        "ix_contest_master_data_versions_contest_id", table_name="contest_master_data_versions"
    )
    op.drop_table("contest_master_data_versions")
    op.drop_index("uq_master_data_running_source_dataset", table_name="master_data_sync_runs")
    with op.batch_alter_table("master_data_sync_runs") as batch:
        batch.drop_column("source_url")
        batch.drop_column("change_detected")
    with op.batch_alter_table("callsign_prefixes") as batch:
        batch.drop_column("utc_offset_override")
        batch.drop_column("longitude_override")
        batch.drop_column("latitude_override")
        batch.drop_column("continent_override")
    with op.batch_alter_table("contest_entities") as batch:
        batch.drop_column("utc_offset")
        batch.drop_column("longitude")
        batch.drop_column("latitude")
        batch.drop_column("continent")
    with op.batch_alter_table("master_data_versions") as batch:
        batch.drop_constraint("effective_interval_positive", type_="check")
        batch.drop_constraint("master_data_version_id_dataset_unique", type_="unique")
        batch.drop_column("valid_to")
        batch.drop_column("valid_from")
