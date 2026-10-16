"""Persist original log revisions and retry-safe submission metadata.

Revision ID: 0011_guest_log_submissions
Revises: 0010_protect_active_master_data
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_guest_log_submissions"
down_revision: str | None = "0010_protect_active_master_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _restore_revision_immutability() -> None:
    op.execute(
        "CREATE TRIGGER immutable_entry_revisions_update BEFORE UPDATE ON entry_revisions "
        "BEGIN SELECT RAISE(ABORT, 'entry_revisions records are append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_entry_revisions_delete BEFORE DELETE ON entry_revisions "
        "BEGIN SELECT RAISE(ABORT, 'entry_revisions records are append-only'); END"
    )


def upgrade() -> None:
    with op.batch_alter_table("entries") as batch:
        batch.add_column(
            sa.Column("category_values", sa.JSON(), nullable=False, server_default="{}")
        )
    with op.batch_alter_table("entry_revisions") as batch:
        batch.add_column(
            sa.Column("original_content", sa.Text(), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("import_metadata", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("received_by_participant_email_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "received_via",
                sa.String(length=40),
                nullable=False,
                server_default="public_submission",
            )
        )
        batch.create_foreign_key(
            "fk_entry_revisions_received_by_participant_email_id_participant_emails",
            "participant_emails",
            ["received_by_participant_email_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # SQLite batch mode recreates the table and drops custom triggers with it.
    _restore_revision_immutability()
    op.create_table(
        "log_submission_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("key_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            "length(key_sha256) = 64", name="ck_log_submission_requests_idempotency_key_hash_length"
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_log_submission_requests_submission_content_hash_length",
        ),
        sa.ForeignKeyConstraint(
            ["contest_id"],
            ["contests.id"],
            ondelete="RESTRICT",
            name="fk_log_submission_requests_contest_id_contests",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            ondelete="RESTRICT",
            name="fk_log_submission_requests_entry_id_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_log_submission_requests"),
        sa.UniqueConstraint("contest_id", "key_sha256", name="contest_submission_key_unique"),
    )
    op.create_index(
        "ix_log_submission_requests_contest_id",
        "log_submission_requests",
        ["contest_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_log_submission_requests_contest_id", table_name="log_submission_requests")
    op.drop_table("log_submission_requests")
    with op.batch_alter_table("entry_revisions") as batch:
        batch.drop_constraint(
            "fk_entry_revisions_received_by_participant_email_id_participant_emails",
            type_="foreignkey",
        )
        batch.drop_column("received_via")
        batch.drop_column("received_by_participant_email_id")
        batch.drop_column("import_metadata")
        batch.drop_column("original_content")
    _restore_revision_immutability()
    with op.batch_alter_table("entries") as batch:
        batch.drop_column("category_values")
