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
    ]
    contest_free_bands = {"2200m", "630m", "60m", "30m", "17m", "12m"}
    for order, (key, label, frequency) in enumerate(bands):
        items.append(
            {
                "kind": "band",
                "key": key,
                "label": label,
                "description": _band_description(key),
                "frequency_range": frequency,
                "sort_order": order,
                "is_active": True,
                "contest_free": key in contest_free_bands,
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
                "description": _mode_description(mode),
                "frequency_range": None,
                "sort_order": order,
                "is_active": True,
                "contest_free": False,
            }
        )
    op.bulk_insert(table, items)


def _band_description(key: str) -> str:
    """Return a compact amateur-radio band designation for the built-in catalog."""
    descriptions = {
        "2200m": "2200 m LF band",
        "630m": "630 m MF band",
        "160m": "160 m HF band",
        "80m": "80 m HF band",
        "60m": "60 m HF band",
        "40m": "40 m HF band",
        "30m": "30 m HF band",
        "20m": "20 m HF band",
        "17m": "17 m HF band",
        "15m": "15 m HF band",
        "12m": "12 m HF band",
        "10m": "10 m HF band",
        "8m": "8 m VHF band",
        "6m": "6 m VHF band",
        "5m": "5 m VHF band",
        "4m": "4 m VHF band",
        "2m": "2 m VHF band",
        "1.25m": "1.25 m VHF band",
        "70cm": "70 cm UHF band",
        "33cm": "33 cm UHF band",
        "23cm": "23 cm UHF band",
        "13cm": "13 cm SHF band",
        "9cm": "9 cm SHF band",
        "6cm": "6 cm SHF band",
        "3cm": "3 cm SHF band",
        "1.25cm": "1.25 cm SHF band",
        "6mm": "6 mm EHF band",
        "4mm": "4 mm EHF band",
        "2.5mm": "2.5 mm EHF band",
        "2mm": "2 mm EHF band",
        "1mm": "1 mm EHF band",
        "0.5mm": "0.5 mm submillimeter band",
        "0.4mm": "0.4 mm submillimeter band",
        "0.2mm": "0.2 mm submillimeter band",
    }
    return descriptions[key]


def _mode_description(key: str) -> str:
    """Return a compact plain-language description of a built-in operating mode."""
    descriptions = {
        "CW": "Morse code",
        "SSB": "Single-sideband voice",
        "AM": "Amplitude-modulated voice",
        "FM": "Frequency-modulated voice",
        "RTTY": "Radio teletype",
        "PSK31": "31-baud phase-shift keying",
        "PSK63": "63-baud phase-shift keying",
        "FT8": "Weak-signal digital mode",
        "FT4": "Fast weak-signal digital mode",
        "JT65": "Weak-signal digital mode",
        "JT9": "Weak-signal digital mode",
        "MSK144": "Meteor-scatter digital mode",
        "JS8": "Keyboard text messaging",
        "Olivia": "MFSK text mode",
        "MFSK": "Multi-frequency shift keying",
        "SSTV": "Slow-scan television",
        "D-STAR": "Digital voice and data",
        "C4FM": "Digital voice and data",
        "DMR": "Digital mobile radio",
        "Packet": "Packet radio",
        "Contestia": "Digital text mode",
        "Q65": "Weak-signal digital mode",
        "WSPR": "Weak-signal propagation beacon",
    }
    return descriptions[key]


def downgrade() -> None:
    op.drop_index("ix_operating_catalog_items_kind", table_name="operating_catalog_items")
    op.drop_table("operating_catalog_items")
