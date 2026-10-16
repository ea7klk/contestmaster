"""Allow referenced-free ruleset versions to be deleted through the guarded API."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.app.contest_deletion_triggers import install_ruleset_deletion_guard

revision: str = "0021_authorized_ruleset_deletion"
down_revision: str | None = "0020_authorized_contest_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("ruleset_deletion_permits"):
        op.create_table(
            "ruleset_deletion_permits",
            sa.Column(
                "ruleset_version_id",
                sa.Integer(),
                sa.ForeignKey("ruleset_versions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )
    install_ruleset_deletion_guard(bind)


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS guard_ruleset_versions_delete")
    bind.exec_driver_sql(
        "CREATE TRIGGER immutable_ruleset_versions_delete BEFORE DELETE ON ruleset_versions "
        "BEGIN SELECT RAISE(ABORT, 'ruleset_versions records are append-only'); END"
    )
    op.drop_table("ruleset_deletion_permits")
