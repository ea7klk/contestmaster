"""Add the WWROF Cabrillo Phone mode token to the shared mode catalog.

Revision ID: 0029_cabrillo_phone_mode
Revises: 0028_scoring_session_numbers
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_cabrillo_phone_mode"
down_revision: str | None = "0028_scoring_session_numbers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    mode_catalog = sa.table(
        "mode_catalog_items",
        sa.column("key", sa.String()),
        sa.column("label", sa.String()),
        sa.column("description", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    existing = bind.scalar(
        sa.select(sa.func.count()).select_from(mode_catalog).where(mode_catalog.c.key == "PH")
    )
    if not existing:
        bind.execute(
            sa.insert(mode_catalog).values(
                key="PH",
                label="Phone (Cabrillo PH)",
                description="Cabrillo log mode token for phone contacts",
                sort_order=100,
                is_active=True,
            )
        )


def downgrade() -> None:
    # Mode catalog rows are administrator-managed shared data. Retain this
    # additive seed on downgrade rather than deleting a row that may be in use.
    pass
