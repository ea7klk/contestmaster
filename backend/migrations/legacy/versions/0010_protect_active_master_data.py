"""Prevent direct deletion of the active master-data snapshot.

Revision ID: 0010_protect_active_master_data
Revises: 0009_participant_sessions
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_protect_active_master_data"
down_revision: str | None = "0009_participant_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER prevent_active_master_data_version_delete "
        "BEFORE DELETE ON master_data_versions "
        "WHEN OLD.status = 'active' "
        "BEGIN SELECT RAISE(ABORT, 'active master data versions cannot be deleted'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER prevent_active_master_data_version_delete")
