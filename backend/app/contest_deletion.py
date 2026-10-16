"""Transactional deletion of contest-owned records and unused ruleset versions."""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.app.models import (
    AdminNote,
    Contest,
    ContestMasterDataVersion,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    LogSubmissionRequest,
    Qso,
    QsoDecision,
    QsoScore,
    ResultPublication,
    ResultPublicationEntry,
    RulesetActivation,
    RulesetVersion,
    ScoreRun,
    ScoreRunMasterDataVersion,
    Station,
)


class DeletionConflictError(ValueError):
    """Raised when retained cross-record provenance prevents a safe deletion."""


def delete_contest_records(session: Session, contest: Contest) -> dict[str, int]:
    """Delete a contest and all its dependent records within the caller's transaction.

    Participants and global audit events are deliberately retained: participant identities can
    be shared across contests, and the final contest-deleted audit event must survive deletion.
    """
    contest_id = contest.id
    entry_ids = select(Entry.id).where(Entry.contest_id == contest_id)
    revision_ids = select(EntryRevision.id).where(EntryRevision.entry_id.in_(entry_ids))
    qso_ids = select(Qso.id).where(Qso.entry_revision_id.in_(revision_ids))
    score_run_ids = select(ScoreRun.id).where(ScoreRun.entry_id.in_(entry_ids))
    publication_ids = select(ResultPublication.id).where(ResultPublication.contest_id == contest_id)

    # A decision chain is expected to stay within a single QSO. Refuse malformed cross-QSO
    # references instead of silently editing another contest's adjudication history.
    decision_ids = select(QsoDecision.id).where(QsoDecision.qso_id.in_(qso_ids))
    external_decision = session.scalar(
        select(QsoDecision.id)
        .where(
            QsoDecision.supersedes_decision_id.in_(decision_ids),
            ~QsoDecision.qso_id.in_(qso_ids),
        )
        .limit(1)
    )
    if external_decision is not None:
        raise DeletionConflictError(
            "A contest adjudication decision is referenced by a decision for another log."
        )

    counts = {
        "entries": session.scalar(
            select(func.count()).select_from(Entry).where(Entry.contest_id == contest_id)
        )
        or 0,
        "revisions": session.scalar(
            select(func.count())
            .select_from(EntryRevision)
            .where(EntryRevision.entry_id.in_(entry_ids))
        )
        or 0,
        "qsos": session.scalar(
            select(func.count()).select_from(Qso).where(Qso.entry_revision_id.in_(revision_ids))
        )
        or 0,
        "score_runs": session.scalar(
            select(func.count()).select_from(ScoreRun).where(ScoreRun.entry_id.in_(entry_ids))
        )
        or 0,
        "publications": session.scalar(
            select(func.count())
            .select_from(ResultPublication)
            .where(ResultPublication.contest_id == contest_id)
        )
        or 0,
    }

    # Restrictive FKs make the dependency order explicit and protect against accidental orphans.
    session.execute(
        delete(ResultPublicationEntry).where(
            ResultPublicationEntry.publication_id.in_(publication_ids)
        )
    )
    session.execute(
        delete(ResultPublicationEntry).where(ResultPublicationEntry.entry_id.in_(entry_ids))
    )
    session.execute(
        delete(ResultPublicationEntry).where(ResultPublicationEntry.score_run_id.in_(score_run_ids))
    )
    session.execute(delete(QsoScore).where(QsoScore.entry_revision_id.in_(revision_ids)))
    # Clear links within the contest's decision chains before deleting those decisions.
    session.execute(
        update(QsoDecision)
        .where(QsoDecision.qso_id.in_(qso_ids))
        .values(supersedes_decision_id=None)
    )
    session.execute(delete(QsoDecision).where(QsoDecision.qso_id.in_(qso_ids)))
    session.execute(delete(Qso).where(Qso.entry_revision_id.in_(revision_ids)))
    session.execute(delete(Station).where(Station.entry_revision_id.in_(revision_ids)))
    session.execute(
        delete(ScoreRunMasterDataVersion).where(
            ScoreRunMasterDataVersion.score_run_id.in_(score_run_ids)
        )
    )
    session.execute(delete(ScoreRun).where(ScoreRun.id.in_(score_run_ids)))
    session.execute(delete(EntryAccessGrant).where(EntryAccessGrant.entry_id.in_(entry_ids)))
    session.execute(
        delete(LogSubmissionRequest).where(LogSubmissionRequest.contest_id == contest_id)
    )
    session.execute(delete(AdminNote).where(AdminNote.contest_id == contest_id))
    session.execute(
        delete(ContestMasterDataVersion).where(ContestMasterDataVersion.contest_id == contest_id)
    )
    session.execute(delete(RulesetActivation).where(RulesetActivation.contest_id == contest_id))
    session.execute(delete(ResultPublication).where(ResultPublication.contest_id == contest_id))
    session.execute(delete(EntryRevision).where(EntryRevision.entry_id.in_(entry_ids)))
    session.execute(delete(Entry).where(Entry.contest_id == contest_id))
    session.delete(contest)
    session.flush()
    return counts


def delete_unused_ruleset_version(session: Session, version: RulesetVersion) -> None:
    """Delete a ruleset version only when no current or historical result references it."""
    references = (
        (Contest, Contest.ruleset_version_id),
        (RulesetActivation, RulesetActivation.ruleset_version_id),
        (ScoreRun, ScoreRun.ruleset_version_id),
    )
    for model, column in references:
        if session.scalar(select(model.id).where(column == version.id).limit(1)) is not None:
            raise DeletionConflictError(
                "This ruleset version is referenced by a contest or score history "
                "and cannot be deleted."
            )
    session.delete(version)
    session.flush()
