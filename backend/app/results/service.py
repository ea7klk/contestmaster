"""Result generation, publication snapshots, standings, and exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    Contest,
    Entry,
    EntryRevision,
    EntryStatus,
    QsoScore,
    ResultPublication,
    ResultPublicationEntry,
    ScoreRun,
    ScoreRunStatus,
    Station,
)
from backend.app.models.types import utc_now
from backend.app.rulesets.persistence import load_ruleset_version
from backend.app.rulesets.schema import WorkflowHookRule


class ResultPublicationError(ValueError):
    """A result publication request does not match current contest state."""


@dataclass(frozen=True, slots=True)
class ResultCandidate:
    entry: Entry
    revision: EntryRevision
    score_run: ScoreRun
    callsign: str
    status: str
    included_by_default: bool


_PUBLIC_STATUS_KEYS = {
    "late": "include_late",
    "checklog": "include_checklog",
    "needs_review": "include_needs_review",
    "reclassified": "include_reclassified",
    "disqualified": "include_disqualified",
}


def publication_policy(session: Session, contest: Contest) -> dict[str, bool]:
    policy = {
        "include_late": False,
        "include_checklog": False,
        "include_needs_review": False,
        "include_reclassified": True,
        "include_disqualified": True,
    }
    if contest.ruleset_version_id is None:
        return policy
    from backend.app.models import RulesetVersion

    version = session.get(RulesetVersion, contest.ruleset_version_id)
    if version is None:
        return policy
    definition = load_ruleset_version(version)
    for configured in definition.rules:
        rule = configured.rule
        if isinstance(rule, WorkflowHookRule) and rule.stage == "publication":
            for key in policy:
                value = rule.parameters.get(key)
                if type(value) is bool:
                    policy[key] = value
    return policy


def _latest_revision(session: Session, entry_id: int) -> EntryRevision | None:
    return session.scalar(
        select(EntryRevision)
        .where(EntryRevision.entry_id == entry_id)
        .order_by(EntryRevision.revision_number.desc(), EntryRevision.id.desc())
        .limit(1)
    )


def _latest_run(session: Session, entry_id: int, revision_id: int) -> ScoreRun | None:
    return session.scalar(
        select(ScoreRun)
        .where(ScoreRun.entry_id == entry_id, ScoreRun.entry_revision_id == revision_id)
        .order_by(ScoreRun.run_number.desc(), ScoreRun.id.desc())
        .limit(1)
    )


def _candidate_status(entry: Entry, run: ScoreRun) -> str:
    if entry.status is EntryStatus.DISQUALIFIED:
        return "disqualified"
    if entry.status is EntryStatus.CHECKLOG:
        return "checklog"
    if entry.is_late:
        return "late"
    outcome = run.explanation.get("outcome") if isinstance(run.explanation, dict) else None
    if outcome in {"needs_review", "reclassified", "disqualified"}:
        return outcome
    return "scored"


def list_result_candidates(session: Session, contest: Contest) -> list[ResultCandidate]:
    policy = publication_policy(session, contest)
    candidates: list[ResultCandidate] = []
    entries = session.scalars(
        select(Entry).where(Entry.contest_id == contest.id).order_by(Entry.id)
    )
    for entry in entries:
        if entry.status is EntryStatus.WITHDRAWN:
            continue
        revision = _latest_revision(session, entry.id)
        if revision is None:
            continue
        run = _latest_run(session, entry.id, revision.id)
        if run is None or run.status is not ScoreRunStatus.COMPLETED:
            continue
        station = session.scalar(select(Station).where(Station.entry_revision_id == revision.id))
        if station is None:
            continue
        status = _candidate_status(entry, run)
        flag = _PUBLIC_STATUS_KEYS.get(status)
        candidates.append(
            ResultCandidate(
                entry=entry,
                revision=revision,
                score_run=run,
                callsign=station.callsign_normalized or station.callsign_submitted,
                status=status,
                included_by_default=policy.get(flag, True) if flag else True,
            )
        )
    return candidates


def unresolved_items(session: Session, contest: Contest) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    entries = session.scalars(
        select(Entry).where(Entry.contest_id == contest.id).order_by(Entry.id)
    )
    for entry in entries:
        if entry.status is EntryStatus.WITHDRAWN:
            continue
        revision = _latest_revision(session, entry.id)
        if revision is None:
            unresolved.append({"entry_id": entry.id, "status": "missing_log"})
            continue
        run = _latest_run(session, entry.id, revision.id)
        if run is None:
            unresolved.append(
                {"entry_id": entry.id, "revision_id": revision.id, "status": "not_scored"}
            )
            continue
        if run.status is not ScoreRunStatus.COMPLETED:
            unresolved.append(
                {
                    "entry_id": entry.id,
                    "revision_id": revision.id,
                    "score_run_id": run.id,
                    "status": run.status.value,
                    "failure": run.master_data_snapshot.get("error")
                    if isinstance(run.master_data_snapshot, dict)
                    else None,
                }
            )
            continue
        status = _candidate_status(entry, run)
        if status in {"checklog", "needs_review", "late"}:
            unresolved.append(
                {
                    "entry_id": entry.id,
                    "revision_id": revision.id,
                    "score_run_id": run.id,
                    "status": status,
                    "reason_codes": run.explanation.get("review_reasons", [])
                    if isinstance(run.explanation, dict)
                    else [],
                }
            )
        scores = session.scalars(
            select(QsoScore).where(
                QsoScore.score_run_id == run.id,
                QsoScore.status == "needs_review",
            )
        )
        qso_ids = [score.qso_id for score in scores]
        if qso_ids:
            unresolved.append(
                {
                    "entry_id": entry.id,
                    "revision_id": revision.id,
                    "score_run_id": run.id,
                    "status": "qso_review",
                    "qso_ids": qso_ids,
                }
            )
    return unresolved


def _safe_explanation(run: ScoreRun, qso_count: int, credited_count: int) -> dict[str, Any]:
    """Expose score arithmetic and counts, never contact rows or internal review notes."""
    multiplier_counts = run.explanation.get("multiplier_counts", {})
    if not isinstance(multiplier_counts, dict):
        multiplier_counts = {}
    multiplier_counts = {
        str(rule_id): count
        for rule_id, count in multiplier_counts.items()
        if type(count) is int and count >= 0
    }
    return {
        "format_version": 2,
        "points": run.points,
        "multipliers": run.multiplier_count,
        "multiplier_counts": multiplier_counts,
        "bonus_points": run.bonus_points,
        "penalty_points": run.penalty_points,
        "score": run.final_score,
        "qso_count": qso_count,
        "credited_qso_count": credited_count,
        "summary": "Integer score produced by the published contest ruleset.",
    }


def publish_result_snapshot(
    session: Session,
    *,
    contest: Contest,
    score_run_ids: list[int],
    published_by_user_id: int,
) -> ResultPublication:
    if not score_run_ids or len(score_run_ids) != len(set(score_run_ids)):
        raise ResultPublicationError("Select at least one distinct completed score run.")
    candidates = {item.score_run.id: item for item in list_result_candidates(session, contest)}
    selected: list[ResultCandidate] = []
    for run_id in score_run_ids:
        candidate = candidates.get(run_id)
        if candidate is None:
            raise ResultPublicationError(
                f"Score run {run_id} is not the latest completed run "
                "for a publishable contest entry."
            )
        if not candidate.included_by_default:
            raise ResultPublicationError(
                f"Entry {candidate.entry.id} is withheld by the configured publication policy."
            )
        selected.append(candidate)
    if not selected:
        raise ResultPublicationError("There are no result rows to publish.")

    previous_number = (
        session.scalar(
            select(func.max(ResultPublication.publication_number)).where(
                ResultPublication.contest_id == contest.id
            )
        )
        or 0
    )
    selected.sort(
        key=lambda candidate: (
            tuple(sorted(candidate.entry.category_values.items())),
            candidate.status == "disqualified",
            -candidate.score_run.final_score,
            candidate.callsign.casefold(),
            candidate.entry.id,
        )
    )
    digest_source: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    rank_by_group: dict[tuple[tuple[str, str], ...], tuple[int, int]] = {}
    for candidate in selected:
        run = candidate.score_run
        qso_rows = list(session.scalars(select(QsoScore).where(QsoScore.score_run_id == run.id)))
        credited = sum(row.credited for row in qso_rows)
        qso_count = len(qso_rows)
        group = tuple(sorted(candidate.entry.category_values.items()))
        ranked = candidate.status in {"scored", "reclassified"}
        if ranked:
            last_score, last_rank = rank_by_group.get(group, (-1, 0))
            rank = (
                last_rank
                if last_score == run.final_score
                else sum(
                    1
                    for previous in prepared
                    if previous["group"] == group
                    and previous["ranked"]
                    and previous["score"] > run.final_score
                )
                + 1
            )
            rank_by_group[group] = (run.final_score, rank)
        else:
            rank = None
        score = 0 if candidate.status == "disqualified" else run.final_score
        explanation = _safe_explanation(run, qso_count, credited)
        data = {
            "entry_id": candidate.entry.id,
            "score_run_id": run.id,
            "callsign": candidate.callsign,
            "category_values": candidate.entry.category_values or {},
            "status": candidate.status,
            "score": score,
            "points": run.points,
            "multiplier_count": run.multiplier_count,
            "bonus_points": run.bonus_points,
            "penalty_points": run.penalty_points,
            "qso_count": qso_count,
            "credited_qso_count": credited,
            "placement": rank,
            "explanation": explanation,
            "group": group,
            "ranked": ranked,
        }
        prepared.append(data)
        digest_source.append(
            {key: value for key, value in data.items() if key not in {"group", "ranked"}}
            | {"input_digest": run.input_digest}
        )
    source_digest = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    all_entries = (
        session.scalar(
            select(func.count(Entry.id)).where(
                Entry.contest_id == contest.id, Entry.status != EntryStatus.WITHDRAWN
            )
        )
        or 0
    )
    publication = ResultPublication(
        contest_id=contest.id,
        publication_number=previous_number + 1,
        source_digest=source_digest,
        entry_count=len(prepared),
        withheld_count=max(0, all_entries - len(prepared)),
        published_by_user_id=published_by_user_id,
        published_at=utc_now(),
    )
    session.add(publication)
    session.flush()
    session.add_all(
        ResultPublicationEntry(
            publication_id=publication.id,
            entry_id=data["entry_id"],
            score_run_id=data["score_run_id"],
            callsign=data["callsign"],
            category_values=data["category_values"],
            status=data["status"],
            score=data["score"],
            points=data["points"],
            multiplier_count=data["multiplier_count"],
            bonus_points=data["bonus_points"],
            penalty_points=data["penalty_points"],
            qso_count=data["qso_count"],
            credited_qso_count=data["credited_qso_count"],
            placement=data["placement"],
            explanation=data["explanation"],
        )
        for data in prepared
    )
    session.flush()
    contest.status = contest.status.__class__.PUBLISHED
    publication.is_sealed = True
    session.flush()
    return publication


def current_publication(session: Session, contest: Contest) -> ResultPublication | None:
    if contest.status.value != "published":
        return None
    return session.scalar(
        select(ResultPublication)
        .where(ResultPublication.contest_id == contest.id, ResultPublication.is_sealed.is_(True))
        .order_by(ResultPublication.publication_number.desc())
        .limit(1)
    )


def public_result_row(row: ResultPublicationEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "callsign": row.callsign,
        "category_values": row.category_values,
        "status": row.status,
        "score": row.score,
        "points": row.points,
        "multiplier_count": row.multiplier_count,
        "bonus_points": row.bonus_points,
        "penalty_points": row.penalty_points,
        "qso_count": row.qso_count,
        "credited_qso_count": row.credited_qso_count,
        "placement": row.placement,
        "explanation": row.explanation,
    }


def export_results_json(
    contest: Contest, publication: ResultPublication, rows: list[ResultPublicationEntry]
) -> dict[str, Any]:
    return {
        "format": "contestmaster-results",
        "format_version": 1,
        "contest": {"name": contest.name, "slug": contest.slug},
        "publication": {
            "number": publication.publication_number,
            "published_at": publication.published_at.isoformat(),
            "source_digest": publication.source_digest,
            "entry_count": publication.entry_count,
            "withheld_count": publication.withheld_count,
        },
        "items": [public_result_row(row) for row in rows],
    }


def export_results_csv(rows: list[ResultPublicationEntry]) -> str:
    output = io.StringIO(newline="")
    columns = [
        "callsign",
        "placement",
        "score",
        "points",
        "multiplier_count",
        "bonus_points",
        "penalty_points",
        "qso_count",
        "credited_qso_count",
        "status",
        "category_values",
    ]
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        data = public_result_row(row)
        data["category_values"] = json.dumps(
            data["category_values"], sort_keys=True, separators=(",", ":")
        )
        writer.writerow({key: data[key] for key in columns})
    return output.getvalue()
