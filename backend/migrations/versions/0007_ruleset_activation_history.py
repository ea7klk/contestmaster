"""Record immutable ruleset activation history per contest.

Revision ID: 0007_ruleset_activation_history
Revises: 0006_remove_iaru_region_master_data
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_ruleset_activation_history"
down_revision: str | None = "0006_remove_iaru_region_master_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ruleset_activations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("ruleset_version_id", sa.Integer(), nullable=False),
        sa.Column("activated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("configuration_sha256", sa.String(length=64), nullable=False),
        sa.Column("activated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint(
            "length(configuration_sha256) = 64",
            name="ck_ruleset_activations_configuration_digest_length",
        ),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["system_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ruleset_version_id"], ["ruleset_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ruleset_activations_contest_id", "ruleset_activations", ["contest_id"])
    op.create_index(
        "ix_ruleset_activations_ruleset_version_id",
        "ruleset_activations",
        ["ruleset_version_id"],
    )
    op.execute(
        "CREATE TRIGGER immutable_ruleset_activations_update BEFORE UPDATE ON ruleset_activations "
        "BEGIN SELECT RAISE(ABORT, 'ruleset activation history is append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_ruleset_activations_delete BEFORE DELETE ON ruleset_activations "
        "BEGIN SELECT RAISE(ABORT, 'ruleset activation history is append-only'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER immutable_ruleset_activations_delete")
    op.execute("DROP TRIGGER immutable_ruleset_activations_update")
    op.drop_index("ix_ruleset_activations_ruleset_version_id", table_name="ruleset_activations")
    op.drop_index("ix_ruleset_activations_contest_id", table_name="ruleset_activations")
    op.drop_table("ruleset_activations")
