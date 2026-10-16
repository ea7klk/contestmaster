"""Split the band and mode operating catalogs into separate ORM tables.

Revision ID: 0015_split_operating_catalogs
Revises: 0014_operating_catalog
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_split_operating_catalogs"
down_revision: str | None = "0014_operating_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "band_catalog_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frequency_range", sa.String(length=120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("contest_free", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "length(trim(key)) > 0", name="ck_band_catalog_items_band_catalog_key_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(label)) > 0", name="ck_band_catalog_items_band_catalog_label_not_blank"
        ),
        sa.UniqueConstraint("key", name="band_catalog_key_unique"),
    )
    op.create_table(
        "mode_catalog_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "length(trim(key)) > 0", name="ck_mode_catalog_items_mode_catalog_key_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(label)) > 0", name="ck_mode_catalog_items_mode_catalog_label_not_blank"
        ),
        sa.UniqueConstraint("key", name="mode_catalog_key_unique"),
    )
    op.create_index("ix_band_catalog_items_sort_order", "band_catalog_items", ["sort_order"])
    op.create_index("ix_mode_catalog_items_sort_order", "mode_catalog_items", ["sort_order"])

    op.execute(
        sa.text(
            """INSERT INTO band_catalog_items
            (id, key, label, description, frequency_range, sort_order, is_active, contest_free)
            SELECT id, key, label, description, frequency_range, sort_order, is_active, contest_free
            FROM operating_catalog_items WHERE kind = 'band'"""
        )
    )
    op.execute(
        sa.text(
            """INSERT INTO mode_catalog_items
            (id, key, label, description, sort_order, is_active)
            SELECT id, key, label, description, sort_order, is_active
            FROM operating_catalog_items WHERE kind = 'mode'"""
        )
    )
    op.drop_index("ix_operating_catalog_items_kind", table_name="operating_catalog_items")
    op.drop_table("operating_catalog_items")


def downgrade() -> None:
    op.create_table(
        "operating_catalog_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frequency_range", sa.String(length=120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("contest_free", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('band', 'mode')",
            name="ck_operating_catalog_items_operating_catalog_kind",
        ),
        sa.CheckConstraint(
            "length(trim(key)) > 0",
            name="ck_operating_catalog_items_operating_catalog_key_not_blank",
        ),
        sa.CheckConstraint(
            "length(trim(label)) > 0",
            name="ck_operating_catalog_items_operating_catalog_label_not_blank",
        ),
        sa.UniqueConstraint("kind", "key", name="operating_catalog_kind_key_unique"),
    )
    op.create_index("ix_operating_catalog_items_kind", "operating_catalog_items", ["kind"])
    op.execute(
        sa.text(
            """INSERT INTO operating_catalog_items
            (id, kind, key, label, description, frequency_range, sort_order, is_active,
            contest_free)
            SELECT id, 'band', key, label, description, frequency_range, sort_order, is_active,
            contest_free FROM band_catalog_items"""
        )
    )
    op.execute(
        sa.text(
            """INSERT INTO operating_catalog_items
            (id, kind, key, label, description, frequency_range, sort_order, is_active,
            contest_free)
            SELECT id, 'mode', key, label, description, NULL, sort_order, is_active, 0
            FROM mode_catalog_items"""
        )
    )
    op.drop_index("ix_band_catalog_items_sort_order", table_name="band_catalog_items")
    op.drop_index("ix_mode_catalog_items_sort_order", table_name="mode_catalog_items")
    op.drop_table("band_catalog_items")
    op.drop_table("mode_catalog_items")
