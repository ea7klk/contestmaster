"""Add revocable sessions for registered contest participants.

Revision ID: 0009_participant_sessions
Revises: 0008_privileged_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_participant_sessions"
down_revision: str | None = "0008_privileged_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "participant_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("participant_email_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("expires_at", sa.String(length=27), nullable=False),
        sa.Column("revoked_at", sa.String(length=27), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 64", name="ck_participant_sessions_session_token_hash_length"
        ),
        sa.CheckConstraint(
            "length(csrf_token_hash) = 64",
            name="ck_participant_sessions_session_csrf_hash_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_participant_sessions_session_expires_after_created"
        ),
        sa.ForeignKeyConstraint(
            ["participant_email_id"], ["participant_emails.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_participant_sessions_token_hash"),
    )
    op.create_index(
        "ix_participant_sessions_participant_email_id",
        "participant_sessions",
        ["participant_email_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_participant_sessions_participant_email_id", table_name="participant_sessions"
    )
    op.drop_table("participant_sessions")
