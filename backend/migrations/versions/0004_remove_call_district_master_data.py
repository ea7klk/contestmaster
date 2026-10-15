"""Remove non-scoring call-area master data and the FCC ULS source.

Revision ID: 0004_remove_call_district_master_data
Revises: 0003_master_data_intervals
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_remove_call_district_master_data"
down_revision: str | None = "0003_master_data_intervals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("call_districts")

    # Purge the unused FCC dataset and its references before deleting its version rows.
    op.execute(
        "DELETE FROM contest_master_data_versions "
        "WHERE dataset_key = 'call-districts-us'"
    )
    op.execute(
        "DELETE FROM score_run_master_data_versions "
        "WHERE dataset_key = 'call-districts-us'"
    )
    fcc_entity_ids = (
        "SELECT id FROM contest_entities WHERE version_id IN "
        "(SELECT id FROM master_data_versions WHERE dataset_key = 'call-districts-us')"
    )
    for table in (
        "entity_cq_zone_assignments",
        "entity_itu_zone_assignments",
        "entity_iaru_region_assignments",
        "entity_itu_radio_region_assignments",
        "prefix_entity_assignments",
    ):
        op.execute(sa.text(f"DELETE FROM {table} WHERE entity_id IN ({fcc_entity_ids})"))
    op.execute(f"DELETE FROM contest_entities WHERE id IN ({fcc_entity_ids})")
    op.execute("DELETE FROM master_data_versions WHERE dataset_key = 'call-districts-us'")
    op.execute(
        "DELETE FROM master_data_sync_runs "
        "WHERE dataset_key = 'call-districts-us' "
        "OR source_id IN (SELECT id FROM master_data_sources WHERE source_key = 'fcc-uls-amateur')"
    )
    op.execute("DELETE FROM master_data_sources WHERE source_key = 'fcc-uls-amateur'")


def downgrade() -> None:
    # Source rows were intentionally removed and cannot be recreated from a schema rollback.
    op.create_table(
        "call_districts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("district_code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("callsign_pattern", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name=op.f("ck_call_districts_validity_range"),
        ),
        sa.ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="call_district_entity_version_fk",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["contest_entities.id"],
            name=op.f("fk_call_districts_entity_id_contest_entities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["master_data_sources.id"],
            name=op.f("fk_call_districts_source_id_master_data_sources"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["master_data_versions.id"],
            name=op.f("fk_call_districts_version_id_master_data_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_districts")),
        sa.UniqueConstraint(
            "version_id",
            "entity_id",
            "district_code",
            name="call_district_version_entity_code_unique",
        ),
    )
    op.create_index(
        op.f("ix_call_districts_entity_id"), "call_districts", ["entity_id"], unique=False
    )
    op.create_index(
        op.f("ix_call_districts_version_id"), "call_districts", ["version_id"], unique=False
    )
