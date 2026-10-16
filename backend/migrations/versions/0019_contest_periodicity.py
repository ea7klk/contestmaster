"""Move recurring schedule configuration from rulesets onto contests.

Revision ID: 0019_contest_periodicity
Revises: 0018_remove_unscored_country_data
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_contest_periodicity"
down_revision: str | None = "0018_remove_unscored_country_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    # The consolidated baseline is generated from current ORM metadata on a fresh
    # database, while existing installations already stamped at that baseline
    # have its historical schema. Keep both upgrade paths valid.
    columns = {column["name"] for column in sa.inspect(connection).get_columns("contests")}
    if "periodicity" not in columns:
        op.add_column("contests", sa.Column("periodicity", sa.JSON(), nullable=True))
    contests = sa.table(
        "contests",
        sa.column("id", sa.Integer()),
        sa.column("periodicity", sa.JSON()),
    )
    for row in connection.execute(
        sa.text(
            "SELECT contests.id, ruleset_versions.configuration "
            "FROM contests LEFT JOIN ruleset_versions "
            "ON ruleset_versions.id = contests.ruleset_version_id"
        )
    ):
        configuration = row.configuration
        if isinstance(configuration, str):
            configuration = json.loads(configuration)
        periodicity = None
        if isinstance(configuration, dict):
            schedule = next(
                (
                    item.get("rule")
                    for item in configuration.get("rules", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("rule"), dict)
                    and item["rule"].get("kind") == "schedule"
                ),
                None,
            )
            if isinstance(schedule, dict) and isinstance(schedule.get("recurrence"), dict):
                periodicity = schedule["recurrence"]
        connection.execute(
            contests.update().where(contests.c.id == row.id).values(periodicity=periodicity)
        )


def downgrade() -> None:
    op.drop_column("contests", "periodicity")
