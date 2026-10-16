"""Add hashed server-side sessions for privileged accounts.

Revision ID: 0008_privileged_sessions
Revises: 0007_ruleset_activation_history
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_privileged_sessions"
down_revision: str | None = "0007_ruleset_activation_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("expires_at", sa.String(length=27), nullable=False),
        sa.Column("revoked_at", sa.String(length=27), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 64", name="ck_system_sessions_session_token_hash_length"
        ),
        sa.CheckConstraint(
            "length(csrf_token_hash) = 64", name="ck_system_sessions_session_csrf_hash_length"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_system_sessions_session_expires_after_created"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["system_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_system_sessions_token_hash"),
    )
    op.create_index("ix_system_sessions_user_id", "system_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_system_sessions_user_id", table_name="system_sessions")
    op.drop_table("system_sessions")
