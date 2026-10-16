"""Set initial contest-free bands and retire default bands above 10 GHz.

Revision ID: 0017_contest_free_band_defaults
Revises: 0016_catalog_item_descriptions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_contest_free_band_defaults"
down_revision: str | None = "0016_catalog_item_descriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONTEST_FREE_BANDS = ("2200m", "630m", "60m", "30m", "17m", "12m")
_ABOVE_10_GHZ_DEFAULT_BANDS = (
    "1.25cm",
    "6mm",
    "4mm",
    "2.5mm",
    "2mm",
    "1mm",
    "0.5mm",
    "0.4mm",
    "0.2mm",
)


def upgrade() -> None:
    bands = sa.table(
        "band_catalog_items",
        sa.column("key", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("contest_free", sa.Boolean()),
    )
    op.execute(bands.update().where(bands.c.key.in_(_CONTEST_FREE_BANDS)).values(contest_free=True))
    # Keep existing stable keys for saved rulesets and history, but prevent these
    # formerly seeded defaults from appearing as choices in newly composed rulesets.
    op.execute(
        bands.update().where(bands.c.key.in_(_ABOVE_10_GHZ_DEFAULT_BANDS)).values(is_active=False)
    )


def downgrade() -> None:
    # These are catalog policy defaults. Retain them when downgrading rather than
    # overwriting administrator changes or reactivating unsupported choices.
    pass
