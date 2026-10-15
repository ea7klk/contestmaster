"""Add administrator-managed band and mode catalogs.

Revision ID: 0014_operating_catalog
Revises: 0013_result_publications
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_operating_catalog"
down_revision: str | None = "0013_result_publications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
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
            "kind IN ('band', 'mode')", name="ck_operating_catalog_items_operating_catalog_kind"
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

    items: list[dict[str, object]] = []
    bands = [
        ("2200m", "2200 m", "135.7–137.8 kHz"),
        ("630m", "630 m", "472–479 kHz"),
        ("160m", "160 m", "1.8 MHz"),
        ("80m", "80 m", "3.5 MHz"),
        ("60m", "60 m", "5 MHz"),
        ("40m", "40 m", "7 MHz"),
        ("30m", "30 m", "10 MHz"),
        ("20m", "20 m", "14 MHz"),
        ("17m", "17 m", "18 MHz"),
        ("15m", "15 m", "21 MHz"),
        ("12m", "12 m", "24 MHz"),
        ("10m", "10 m", "28 MHz"),
        ("8m", "8 m", "40 MHz"),
        ("6m", "6 m", "50 MHz"),
        ("5m", "5 m", "60 MHz"),
        ("4m", "4 m", "70 MHz"),
        ("2m", "2 m", "144 MHz"),
        ("1.25m", "1.25 m", "220 MHz"),
        ("70cm", "70 cm", "430 MHz"),
        ("33cm", "33 cm", "902 MHz"),
        ("23cm", "23 cm", "1.2 GHz"),
        ("13cm", "13 cm", "2.3 GHz"),
        ("9cm", "9 cm", "3.4 GHz"),
        ("6cm", "6 cm", "5.6 GHz"),
        ("3cm", "3 cm", "10 GHz"),
        ("1.25cm", "1.25 cm", "24 GHz"),
        ("6mm", "6 mm", "47 GHz"),
        ("4mm", "4 mm", "76 GHz"),
        ("2.5mm", "2.5 mm", "122 GHz"),
        ("2mm", "2 mm", "134 GHz"),
        ("1mm", "1 mm", "241 GHz"),
        ("0.5mm", "0.5 mm", "472 GHz"),
        ("0.4mm", "0.4 mm", "755 GHz"),
        ("0.2mm", "0.2 mm", "1.4 THz"),
    ]
    for order, (key, label, frequency) in enumerate(bands):
        items.append(
            {
                "kind": "band",
                "key": key,
                "label": label,
                "description": (
                    "Band name is a shared catalog identifier; national allocations "
                    "and contest rules determine whether it may be used."
                ),
                "frequency_range": frequency,
                "sort_order": order,
                "is_active": True,
                "contest_free": False,
            }
        )
    modes = [
        "CW",
        "SSB",
        "AM",
        "FM",
        "RTTY",
        "PSK31",
        "PSK63",
        "FT8",
        "FT4",
        "JT65",
        "JT9",
        "MSK144",
        "JS8",
        "Olivia",
        "MFSK",
        "SSTV",
        "D-STAR",
        "C4FM",
        "DMR",
        "Packet",
        "Contestia",
        "Q65",
        "WSPR",
    ]
    for order, mode in enumerate(modes):
        items.append(
            {
                "kind": "mode",
                "key": mode,
                "label": mode,
                "description": "Common operating mode; contest rules determine eligibility.",
                "frequency_range": None,
                "sort_order": order,
                "is_active": True,
                "contest_free": False,
            }
        )
    op.bulk_insert(table, items)


def downgrade() -> None:
    op.drop_index("ix_operating_catalog_items_kind", table_name="operating_catalog_items")
    op.drop_table("operating_catalog_items")
