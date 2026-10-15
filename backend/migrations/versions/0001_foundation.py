"""Initialize migration-managed schema baseline.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-10-15
"""

from collections.abc import Sequence

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Phase 2 adds the initial domain schema through an explicit follow-up revision.
    pass


def downgrade() -> None:
    pass
