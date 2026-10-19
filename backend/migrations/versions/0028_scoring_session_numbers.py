"""Persist the scoring session assigned to each QSO result.

Revision ID: 0028_scoring_session_numbers
Revises: 0027_audit_event_retention
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_scoring_session_numbers"
down_revision: str | None = "0027_audit_event_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("qso_scores")}
    if "session_number" not in columns:
        op.add_column("qso_scores", sa.Column("session_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("qso_scores")}
    if "session_number" in columns:
        op.drop_column("qso_scores", "session_number")
