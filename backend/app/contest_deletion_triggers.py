"""SQLite guards for authorized contest-history deletion."""

from sqlalchemy.engine import Connection

_OBSOLETE_DELETE_TRIGGERS = (
    "immutable_entry_revisions_delete",
    "immutable_stations_delete",
    "immutable_qsos_delete",
    "immutable_qso_decisions_update",
    "immutable_qso_decisions_delete",
    "immutable_ruleset_activations_delete",
    "retain_score_runs",
    "completed_score_runs_delete",
    "completed_qso_scores_delete",
    "retain_result_publications",
    "retain_result_publication_entries",
)

_CONTEST_DELETE_GUARDS = (
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


def install_contest_deletion_guards(connection: Connection) -> None:
    """Permit protected history deletes only while its contest permit exists."""
    for trigger_name in (*_OBSOLETE_DELETE_TRIGGERS, *_CONTEST_DELETE_GUARDS):
        connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger_name}")

    statements = (
        """CREATE TRIGGER guard_entry_revisions_delete BEFORE DELETE ON entry_revisions
        WHEN NOT EXISTS (
            SELECT 1 FROM entries e
            JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
            WHERE e.id = OLD.entry_id
        )
        BEGIN SELECT RAISE(ABORT, 'entry revisions require contest deletion permit'); END""",
        """CREATE TRIGGER guard_stations_delete BEFORE DELETE ON stations
        WHEN NOT EXISTS (
            SELECT 1 FROM entry_revisions r
            JOIN entries e ON e.id = r.entry_id
            JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
            WHERE r.id = OLD.entry_revision_id
        )
        BEGIN SELECT RAISE(ABORT, 'stations require contest deletion permit'); END""",
        """CREATE TRIGGER guard_qsos_delete BEFORE DELETE ON qsos
        WHEN NOT EXISTS (
            SELECT 1 FROM entry_revisions r
            JOIN entries e ON e.id = r.entry_id
            JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
            WHERE r.id = OLD.entry_revision_id
        )
        BEGIN SELECT RAISE(ABORT, 'QSOs require contest deletion permit'); END""",
        """CREATE TRIGGER guard_qso_decisions_delete BEFORE DELETE ON qso_decisions
        WHEN NOT EXISTS (
            SELECT 1 FROM qsos q
            JOIN entry_revisions r ON r.id = q.entry_revision_id
            JOIN entries e ON e.id = r.entry_id
            JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
            WHERE q.id = OLD.qso_id
        )
        BEGIN SELECT RAISE(ABORT, 'QSO decisions require contest deletion permit'); END""",
        """CREATE TRIGGER guard_qso_decisions_update BEFORE UPDATE ON qso_decisions
        WHEN NOT (
            OLD.qso_id = NEW.qso_id
            AND OLD.status IS NEW.status
            AND OLD.source IS NEW.source
            AND OLD.reason_code IS NEW.reason_code
            AND OLD.reason IS NEW.reason
            AND OLD.evidence IS NEW.evidence
            AND OLD.reviewer_user_id IS NEW.reviewer_user_id
            AND OLD.created_at IS NEW.created_at
            AND (OLD.supersedes_decision_id IS NEW.supersedes_decision_id
                OR NEW.supersedes_decision_id IS NULL)
            AND EXISTS (
                SELECT 1 FROM qsos q
                JOIN entry_revisions r ON r.id = q.entry_revision_id
                JOIN entries e ON e.id = r.entry_id
                JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
                WHERE q.id = OLD.qso_id
            )
        )
        BEGIN SELECT RAISE(ABORT, 'QSO decisions are append-only'); END""",
        """CREATE TRIGGER guard_ruleset_activations_delete BEFORE DELETE ON ruleset_activations
        WHEN NOT EXISTS (
            SELECT 1 FROM contest_deletion_permits p WHERE p.contest_id = OLD.contest_id
        )
        BEGIN SELECT RAISE(ABORT, 'ruleset activations require contest deletion permit'); END""",
        """CREATE TRIGGER guard_score_runs_delete BEFORE DELETE ON score_runs
        WHEN NOT EXISTS (
            SELECT 1 FROM entries e
            JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
            WHERE e.id = OLD.entry_id
        )
        BEGIN SELECT RAISE(ABORT, 'score runs require contest deletion permit'); END""",
        """CREATE TRIGGER guard_qso_scores_delete BEFORE DELETE ON qso_scores
        WHEN NOT EXISTS (
            SELECT 1 FROM score_runs sr
            JOIN entries e ON e.id = sr.entry_id
            JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
            WHERE sr.id = OLD.score_run_id
        )
        BEGIN SELECT RAISE(ABORT, 'QSO scores require contest deletion permit'); END""",
        """CREATE TRIGGER guard_result_publications_delete BEFORE DELETE ON result_publications
        WHEN NOT EXISTS (
            SELECT 1 FROM contest_deletion_permits p WHERE p.contest_id = OLD.contest_id
        )
        BEGIN SELECT RAISE(ABORT, 'result publications require contest deletion permit'); END""",
        """CREATE TRIGGER guard_result_publication_entries_delete
        BEFORE DELETE ON result_publication_entries
        WHEN NOT (
            EXISTS (
                SELECT 1 FROM result_publications rp
                JOIN contest_deletion_permits p ON p.contest_id = rp.contest_id
                WHERE rp.id = OLD.publication_id
            )
            OR EXISTS (
                SELECT 1 FROM entries e
                JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
                WHERE e.id = OLD.entry_id
            )
            OR EXISTS (
                SELECT 1 FROM score_runs sr
                JOIN entries e ON e.id = sr.entry_id
                JOIN contest_deletion_permits p ON p.contest_id = e.contest_id
                WHERE sr.id = OLD.score_run_id
            )
        )
        BEGIN SELECT RAISE(ABORT,
            'published result entries require contest deletion permit'); END""",
    )
    for statement in statements:
        connection.exec_driver_sql(statement)


def install_ruleset_deletion_guard(connection: Connection) -> None:
    """Allow ruleset-version deletion only with the scoped transactional permit."""
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS guard_ruleset_versions_delete")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS immutable_ruleset_versions_delete")
    connection.exec_driver_sql(
        """CREATE TRIGGER guard_ruleset_versions_delete BEFORE DELETE ON ruleset_versions
        WHEN NOT EXISTS (
            SELECT 1 FROM ruleset_deletion_permits p
            WHERE p.ruleset_version_id = OLD.id
        )
        BEGIN SELECT RAISE(ABORT, 'ruleset versions require deletion permit'); END"""
    )
