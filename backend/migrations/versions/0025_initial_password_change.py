"""Require an initial password change for selected system accounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_initial_password_change"
down_revision: str | None = "0024_guest_email_access_and_notices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    return any(item["name"] == column for item in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("system_users", "must_change_password"):
        op.add_column(
            "system_users",
            sa.Column(
                "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    if _has_column("system_users", "must_change_password"):
        op.drop_column("system_users", "must_change_password")
