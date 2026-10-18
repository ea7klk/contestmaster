"""Allow expiry of audit events outside the required 90-day window."""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_audit_event_retention"
down_revision: str | None = "0026_guest_email_locale"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Audit events remain immutable while retained. The explicit expiry exception is
    # enforced in SQLite too, so ordinary application code cannot erase recent history.
    op.get_bind().exec_driver_sql("DROP TRIGGER IF EXISTS immutable_audit_events_delete")
    op.get_bind().exec_driver_sql(
        "CREATE TRIGGER immutable_audit_events_delete BEFORE DELETE ON audit_events "
        "WHEN julianday(OLD.occurred_at) >= julianday('now', '-90 days') "
        "BEGIN SELECT RAISE(ABORT, 'audit_events within retention are append-only'); END"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TRIGGER IF EXISTS immutable_audit_events_delete")
    op.get_bind().exec_driver_sql(
        "CREATE TRIGGER immutable_audit_events_delete BEFORE DELETE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events records are append-only'); END"
    )
