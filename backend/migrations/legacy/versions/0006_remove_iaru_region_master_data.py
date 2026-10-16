"""Remove IARU Region master data from the current product schema.

Revision ID: 0006_remove_iaru_region_master_data
Revises: 0005_remove_itu_radio_regions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_remove_iaru_region_master_data"
down_revision: str | None = "0005_remove_itu_radio_regions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("entity_iaru_region_assignments")
    op.drop_table("iaru_regions")


def downgrade() -> None:
    op.create_table(
        "iaru_regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["master_data_versions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("version_id", "code", name="iaru_region_version_code_unique"),
        sa.UniqueConstraint("id", "version_id", name="iaru_region_id_version_unique"),
    )
    op.create_index("ix_iaru_regions_version_id", "iaru_regions", ["version_id"])
    op.create_table(
        "entity_iaru_region_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("iaru_region_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_iaru_region_assignments_validity_range",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="entity_iaru_region_entity_version_fk",
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["contest_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["iaru_region_id", "version_id"],
            ["iaru_regions.id", "iaru_regions.version_id"],
            name="entity_iaru_region_region_version_fk",
        ),
        sa.ForeignKeyConstraint(["iaru_region_id"], ["iaru_regions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["master_data_versions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "version_id",
            "entity_id",
            "iaru_region_id",
            "valid_from",
            name="entity_iaru_region_version_effective_unique",
        ),
    )
    for column in ("entity_id", "iaru_region_id", "version_id"):
        op.create_index(
            f"ix_entity_iaru_region_assignments_{column}",
            "entity_iaru_region_assignments",
            [column],
        )
