"""Add entry-scoped guest email verification and publication delivery outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_guest_email_access_and_notices"
down_revision: str | None = "0023_participant_accounts_and_shared_iam"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, name: str) -> bool:
    return any(column["name"] == name for column in sa.inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table))


def _create_table(name: str, *columns: object) -> None:
    if not _has_table(name):
        op.create_table(name, *columns)


def _create_index(name: str, table: str, columns: list[str]) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    _create_table(
        "guest_entry_emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id", sa.Integer(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("email_normalized", sa.String(320, collation="NOCASE"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("access_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("results_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.String(27)),
        sa.Column("revoked_at", sa.String(27)),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("updated_at", sa.String(27), nullable=False),
        sa.UniqueConstraint("entry_id", name="guest_entry_email_entry_unique"),
        sa.CheckConstraint("length(trim(email_normalized)) > 0", name="guest_entry_email_not_blank"),
        sa.CheckConstraint(
            "source IN ('upload_prompt', 'cabrillo_header')", name="guest_entry_email_source"
        ),
        sa.CheckConstraint(
            "access_opt_in = 1 OR results_opt_in = 1 OR revoked_at IS NOT NULL",
            name="guest_entry_email_has_consent",
        ),
    )
    _create_index("ix_guest_entry_emails_entry_id", "guest_entry_emails", ["entry_id"])

    _create_table(
        "guest_entry_email_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "guest_email_id",
            sa.Integer(),
            sa.ForeignKey("guest_entry_emails.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("expires_at", sa.String(27), nullable=False),
        sa.Column("consumed_at", sa.String(27)),
        sa.CheckConstraint("length(token_hash) = 64", name="guest_email_token_hash_length"),
        sa.CheckConstraint("expires_at > created_at", name="guest_email_expires_after_created"),
    )
    _create_index(
        "ix_guest_entry_email_verifications_guest_email_id",
        "guest_entry_email_verifications",
        ["guest_email_id"],
    )

    _create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column(
            "guest_email_id",
            sa.Integer(),
            sa.ForeignKey("guest_entry_emails.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("result_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.String(27), nullable=False),
        sa.Column("sent_at", sa.String(27)),
        sa.Column("last_error", sa.String(80)),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.UniqueConstraint("event_key", name="email_outbox_event_unique"),
        sa.CheckConstraint(
            "state IN ('pending', 'sent', 'cancelled', 'dead')", name="email_outbox_state"
        ),
    )
    _create_index("ix_email_outbox_guest_email_id", "email_outbox", ["guest_email_id"])
    _create_index("ix_email_outbox_publication_id", "email_outbox", ["publication_id"])

    if not _has_column("entry_access_grants", "guest_email_id"):
        with op.batch_alter_table("entry_access_grants") as batch:
            batch.add_column(sa.Column("guest_email_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_entry_access_grants_guest_email_id_guest_entry_emails",
                "guest_entry_emails",
                ["guest_email_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_index("ix_entry_access_grants_guest_email_id", ["guest_email_id"])


def downgrade() -> None:
    if _has_column("entry_access_grants", "guest_email_id"):
        with op.batch_alter_table("entry_access_grants") as batch:
            if _has_index("entry_access_grants", "ix_entry_access_grants_guest_email_id"):
                batch.drop_index("ix_entry_access_grants_guest_email_id")
            batch.drop_constraint(
                "fk_entry_access_grants_guest_email_id_guest_entry_emails", type_="foreignkey"
            )
            batch.drop_column("guest_email_id")
    for name in ("email_outbox", "guest_entry_email_verifications", "guest_entry_emails"):
        if _has_table(name):
            op.drop_table(name)
