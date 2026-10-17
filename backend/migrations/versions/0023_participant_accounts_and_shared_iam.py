"""Add participant credentials and shared contest/ruleset administration."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_participant_accounts_and_shared_iam"
down_revision: str | None = "0022_recurring_contest_series"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    def has_table(name: str) -> bool:
        return sa.inspect(op.get_bind()).has_table(name)

    def has_column(table: str, name: str) -> bool:
        return any(c["name"] == name for c in sa.inspect(op.get_bind()).get_columns(table))

    def has_index(table: str, name: str) -> bool:
        return any(i["name"] == name for i in sa.inspect(op.get_bind()).get_indexes(table))

    def create_table(name: str, *columns: object) -> None:
        if not has_table(name):
            op.create_table(name, *columns)

    def create_index(name: str, table: str, columns: list[str]) -> None:
        if not has_index(table, name):
            op.create_index(name, table, columns)

    participant_columns = {c["name"] for c in sa.inspect(bind).get_columns("participants")}
    if "password_hash" not in participant_columns:
        op.add_column("participants", sa.Column("password_hash", sa.String(255), nullable=True))
    if "is_active" not in participant_columns:
        op.add_column(
            "participants",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    email_columns = {c["name"] for c in sa.inspect(bind).get_columns("participant_emails")}
    if "is_primary" not in email_columns:
        op.add_column(
            "participant_emails",
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute(
            "UPDATE participant_emails SET is_primary = 1 WHERE id IN "
            "(SELECT MIN(id) FROM participant_emails GROUP BY participant_id)"
        )
    if "is_active" not in email_columns:
        op.add_column(
            "participant_emails",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    create_table(
        "participant_callsigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("callsign_submitted", sa.String(32), nullable=False),
        sa.Column("callsign_normalized", sa.String(32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.String(27)),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.UniqueConstraint(
            "participant_id", "callsign_normalized", name="participant_callsign_unique"
        ),
        sa.CheckConstraint("length(trim(callsign_submitted)) > 0", name="callsign_not_blank"),
        sa.CheckConstraint("length(trim(callsign_normalized)) > 0", name="callsign_norm_not_blank"),
    )
    create_index(
        "ix_participant_callsigns_participant_id", "participant_callsigns", ["participant_id"]
    )
    op.execute("DROP TRIGGER IF EXISTS immutable_ruleset_versions_update")
    op.execute(
        "INSERT OR IGNORE INTO participant_callsigns "
        "(participant_id, callsign_submitted, callsign_normalized, is_primary, created_at) "
        "SELECT id, callsign_submitted, callsign_normalized, 1, created_at FROM participants "
        "WHERE callsign_submitted IS NOT NULL AND trim(callsign_submitted) != '' "
        "AND callsign_normalized IS NOT NULL AND trim(callsign_normalized) != ''"
    )

    create_table(
        "participant_email_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "old_email_id",
            sa.Integer(),
            sa.ForeignKey("participant_emails.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("new_email_normalized", sa.String(320), nullable=False),
        sa.Column("old_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("new_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("expires_at", sa.String(27), nullable=False),
        sa.Column("old_confirmed_at", sa.String(27)),
        sa.Column("new_confirmed_at", sa.String(27)),
        sa.Column("completed_at", sa.String(27)),
        sa.CheckConstraint("length(old_token_hash) = 64", name="old_token_hash_length"),
        sa.CheckConstraint("length(new_token_hash) = 64", name="new_token_hash_length"),
        sa.CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )
    create_index(
        "ix_participant_email_changes_participant_id",
        "participant_email_changes",
        ["participant_id"],
    )
    create_index(
        "ix_participant_email_changes_old_email_id", "participant_email_changes", ["old_email_id"]
    )

    for table, owner_column in (
        ("participant_password_resets", "participant_id"),
        ("system_password_resets", "user_id"),
    ):
        target = "participants.id" if table.startswith("participant") else "system_users.id"
        columns = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                owner_column,
                sa.Integer(),
                sa.ForeignKey(target, ondelete="CASCADE"),
                nullable=False,
            ),
        ]
        if table.startswith("participant"):
            columns.append(
                sa.Column(
                    "participant_email_id",
                    sa.Integer(),
                    sa.ForeignKey("participant_emails.id", ondelete="CASCADE"),
                    nullable=False,
                )
            )
        columns.extend(
            [
                sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
                sa.Column("created_at", sa.String(27), nullable=False),
                sa.Column("expires_at", sa.String(27), nullable=False),
                sa.Column("consumed_at", sa.String(27)),
                sa.CheckConstraint("length(token_hash) = 64", name="token_hash_sha256_length"),
                sa.CheckConstraint("expires_at > created_at", name="expires_after_created"),
            ]
        )
        create_table(table, *columns)
        create_index(f"ix_{table}_{owner_column}", table, [owner_column])
        if table == "participant_password_resets":
            create_index(
                "ix_participant_password_resets_participant_email_id",
                table,
                ["participant_email_id"],
            )

    create_table(
        "contest_administrators",
        sa.Column(
            "contest_id",
            sa.Integer(),
            sa.ForeignKey("contests.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("system_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_by_user_id", sa.Integer(), sa.ForeignKey("system_users.id", ondelete="SET NULL")
        ),
        sa.Column("added_at", sa.String(27), nullable=False),
        sa.CheckConstraint("user_id != added_by_user_id", name="admin_not_self_added"),
    )

    create_table(
        "rulesets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ruleset_key", sa.String(120), nullable=False, unique=True),
        sa.Column(
            "owner_user_id", sa.Integer(), sa.ForeignKey("system_users.id", ondelete="RESTRICT")
        ),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.CheckConstraint("length(trim(ruleset_key)) > 0", name="ruleset_key_not_blank"),
    )
    create_index("ix_rulesets_owner_user_id", "rulesets", ["owner_user_id"])
    if not has_column("ruleset_versions", "ruleset_id"):
        op.execute("ALTER TABLE ruleset_versions ADD COLUMN ruleset_id INTEGER")
    create_index("ix_ruleset_versions_ruleset_id", "ruleset_versions", ["ruleset_id"])
    op.execute(
        "INSERT INTO rulesets (ruleset_key, owner_user_id, created_at) "
        "SELECT rv.ruleset_key, (SELECT rv2.created_by_user_id FROM ruleset_versions rv2 "
        "WHERE rv2.ruleset_key = rv.ruleset_key AND rv2.created_by_user_id IS NOT NULL "
        "ORDER BY rv2.created_at, rv2.id LIMIT 1), MIN(rv.created_at) "
        "FROM ruleset_versions rv GROUP BY rv.ruleset_key"
    )
    op.execute(
        "UPDATE ruleset_versions SET ruleset_id = "
        "(SELECT r.id FROM rulesets r WHERE r.ruleset_key = ruleset_versions.ruleset_key) "
        "WHERE ruleset_id IS NULL"
    )
    op.execute(
        "CREATE TRIGGER immutable_ruleset_versions_update BEFORE UPDATE ON ruleset_versions "
        "BEGIN SELECT RAISE(ABORT, 'ruleset_versions records are append-only'); END"
    )
    create_table(
        "ruleset_administrators",
        sa.Column(
            "ruleset_id",
            sa.Integer(),
            sa.ForeignKey("rulesets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("system_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_by_user_id", sa.Integer(), sa.ForeignKey("system_users.id", ondelete="SET NULL")
        ),
        sa.Column("added_at", sa.String(27), nullable=False),
        sa.CheckConstraint("user_id != added_by_user_id", name="admin_not_self_added"),
    )


def downgrade() -> None:
    # Keep identity and historic ownership records intact. This no-op exists so
    # migration tests and operators can move the revision marker for diagnostics.
    pass
