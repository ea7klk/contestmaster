"""Allow protected contest history to be removed only through contest deletion.

Revision ID: 0020_authorized_contest_deletion
Revises: 0019_contest_periodicity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.app.contest_deletion_triggers import install_contest_deletion_guards

revision: str = "0020_authorized_contest_deletion"
down_revision: str | None = "0019_contest_periodicity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table("contest_deletion_permits"):
        op.create_table(
            "contest_deletion_permits",
            sa.Column(
                "contest_id",
                sa.Integer(),
                sa.ForeignKey("contests.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )
    install_contest_deletion_guards(bind)


def downgrade() -> None:
    bind = op.get_bind()
    guard_names = (
        "guard_entry_revisions_delete",
        "guard_stations_delete",
        "guard_qsos_delete",
        "guard_qso_decisions_delete",
        "guard_qso_decisions_update",
        "guard_ruleset_activations_delete",
        "guard_score_runs_delete",
        "guard_qso_scores_delete",
        "guard_result_publications_delete",
        "guard_result_publication_entries_delete",
    )
    for trigger_name in guard_names:
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger_name}")
    statements = (
        "CREATE TRIGGER immutable_entry_revisions_delete BEFORE DELETE ON entry_revisions "
        "BEGIN SELECT RAISE(ABORT, 'entry_revisions records are append-only'); END",
        "CREATE TRIGGER immutable_stations_delete BEFORE DELETE ON stations "
        "BEGIN SELECT RAISE(ABORT, 'stations records are append-only'); END",
        "CREATE TRIGGER immutable_qsos_delete BEFORE DELETE ON qsos "
        "BEGIN SELECT RAISE(ABORT, 'qsos records are append-only'); END",
        "CREATE TRIGGER immutable_qso_decisions_update BEFORE UPDATE ON qso_decisions "
        "BEGIN SELECT RAISE(ABORT, 'qso_decisions records are append-only'); END",
        "CREATE TRIGGER immutable_qso_decisions_delete BEFORE DELETE ON qso_decisions "
        "BEGIN SELECT RAISE(ABORT, 'qso_decisions records are append-only'); END",
        "CREATE TRIGGER immutable_ruleset_activations_delete BEFORE DELETE ON ruleset_activations "
        "BEGIN SELECT RAISE(ABORT, 'ruleset activation history is append-only'); END",
        "CREATE TRIGGER retain_score_runs BEFORE DELETE ON score_runs "
        "BEGIN SELECT RAISE(ABORT, 'score_runs are retained for audit'); END",
        "CREATE TRIGGER completed_score_runs_delete BEFORE DELETE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score runs are immutable'); END",
        "CREATE TRIGGER completed_qso_scores_delete BEFORE DELETE ON qso_scores "
        "WHEN EXISTS (SELECT 1 FROM score_runs "
        "WHERE score_runs.id = OLD.score_run_id AND score_runs.status = 'completed') "
        "BEGIN SELECT RAISE(ABORT, 'completed score breakdowns are immutable'); END",
        "CREATE TRIGGER retain_result_publications BEFORE DELETE ON result_publications "
        "BEGIN SELECT RAISE(ABORT, 'result publications are retained for audit'); END",
        "CREATE TRIGGER retain_result_publication_entries "
        "BEFORE DELETE ON result_publication_entries "
        "BEGIN SELECT RAISE(ABORT, 'published result entries are retained for audit'); END",
    )
    for statement in statements:
        bind.exec_driver_sql(statement)
    op.drop_table("contest_deletion_permits")
