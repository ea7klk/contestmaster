"""Replace generic default band and mode descriptions.

Revision ID: 0016_catalog_item_descriptions
Revises: 0015_split_operating_catalogs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_catalog_item_descriptions"
down_revision: str | None = "0015_split_operating_catalogs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENERIC_BAND_DESCRIPTION = (
    "Band name is a shared catalog identifier; national allocations "
    "and contest rules determine whether it may be used."
)
_GENERIC_MODE_DESCRIPTION = "Common operating mode; contest rules determine eligibility."

_BAND_DESCRIPTIONS = {
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

_MODE_DESCRIPTIONS = {
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


def upgrade() -> None:
    bands = sa.table(
        "band_catalog_items",
        sa.column("key", sa.String()),
        sa.column("description", sa.Text()),
    )
    modes = sa.table(
        "mode_catalog_items",
        sa.column("key", sa.String()),
        sa.column("description", sa.Text()),
    )
    for key, description in _BAND_DESCRIPTIONS.items():
        op.execute(
            bands.update()
            .where(
                sa.and_(
                    bands.c.key == key,
                    bands.c.description == _GENERIC_BAND_DESCRIPTION,
                )
            )
            .values(description=description)
        )
    for key, description in _MODE_DESCRIPTIONS.items():
        op.execute(
            modes.update()
            .where(
                sa.and_(
                    modes.c.key == key,
                    modes.c.description == _GENERIC_MODE_DESCRIPTION,
                )
            )
            .values(description=description)
        )


def downgrade() -> None:
    # Description corrections are intentionally retained when downgrading; reverting them
    # would erase the distinction between untouched defaults and administrator-edited rows.
    pass
