"""Persist guest notification language for asynchronous result messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_guest_email_locale"
down_revision: str | None = "0025_initial_password_change"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    return any(item["name"] == column for item in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("guest_entry_emails", "locale"):
        op.add_column(
            "guest_entry_emails",
            sa.Column("locale", sa.String(length=2), nullable=False, server_default="en"),
        )
    inspector = sa.inspect(op.get_bind())
    has_locale_check = any(
        (item.get("name") or "").endswith("guest_entry_email_locale")
        for item in inspector.get_check_constraints("guest_entry_emails")
    )
    if not has_locale_check:
        with op.batch_alter_table("guest_entry_emails") as batch:
            batch.create_check_constraint(
                "guest_entry_email_locale", "locale IN ('en', 'de', 'fr', 'es', 'it')"
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    locale_check_name = next(
        (
            item.get("name")
            for item in inspector.get_check_constraints("guest_entry_emails")
            if (item.get("name") or "").endswith("guest_entry_email_locale")
        ),
        None,
    )
    if locale_check_name or _has_column("guest_entry_emails", "locale"):
        with op.batch_alter_table("guest_entry_emails") as batch:
            if locale_check_name:
                batch.drop_constraint(sa.schema.conv(locale_check_name), type_="check")
            if _has_column("guest_entry_emails", "locale"):
                batch.drop_column("locale")
