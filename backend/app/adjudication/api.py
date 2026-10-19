"""Contest-manager endpoints for durable QSO review and score-run status."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.adjudication.scoring import recalculate_contest
from backend.app.api.auth import AuthenticatedUser, require_contest_access
from backend.app.audit import record_audit_event
from backend.app.db import get_session
from backend.app.models import (
    Contest,
    Entry,
    Qso,
    QsoDecision,
    QsoDecisionSource,
    QsoDecisionStatus,
    QsoScore,
    ScoreRun,
    SystemRole,
)

router = APIRouter(tags=["adjudication"])


class QsoReviewWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: QsoDecisionStatus
    reason_code: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    reason: str = Field(min_length=1, max_length=4000)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence")
    @classmethod
    def limit_evidence(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, ensure_ascii=False, default=str)) > 16000:
            raise ValueError("Evidence may not exceed 16 KiB when encoded as JSON.")
        return value


def _run_output(run: ScoreRun) -> dict[str, object]:
    failure = (
        run.master_data_snapshot.get("error")
        if isinstance(run.master_data_snapshot, dict)
        else None
    )
    return {
        "id": run.id,
        "entry_id": run.entry_id,
        "entry_revision_id": run.entry_revision_id,
        "run_number": run.run_number,
        "status": run.status.value,
        "input_digest": run.input_digest,
        "claimed_points": run.claimed_points,
        "points": run.points,
        "multiplier_count": run.multiplier_count,
        "bonus_points": run.bonus_points,
        "penalty_points": run.penalty_points,
        "provisional_score": run.final_score,
        "adjudicated_score": run.adjudicated_score,
        "explanation": run.explanation,
        "failure": failure,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


@router.get("/contests/{contest_id}/score-runs")
def list_score_runs(
    contest: Annotated[Contest, Depends(require_contest_access)],
    _principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    runs = session.scalars(
        select(ScoreRun)
        .join(Entry, Entry.id == ScoreRun.entry_id)
        .where(Entry.contest_id == contest.id)
        .order_by(ScoreRun.created_at, ScoreRun.id)
    )
    return {"items": [_run_output(run) for run in runs]}


@router.get("/contests/{contest_id}/score-runs/{score_run_id}")
def get_score_run(
    contest_id: int,
    score_run_id: int,
    contest: Annotated[Contest, Depends(require_contest_access)],
    _principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    run = session.scalar(
        select(ScoreRun)
        .join(Entry, Entry.id == ScoreRun.entry_id)
        .where(ScoreRun.id == score_run_id, Entry.contest_id == contest_id)
    )
    if contest.id != contest_id or run is None:
        raise HTTPException(status_code=404, detail="Score run not found.")
    breakdown = session.scalars(
        select(QsoScore).where(QsoScore.score_run_id == run.id).order_by(QsoScore.qso_id)
    )
    return {
        **_run_output(run),
        "qso_scores": [
            {
                "qso_id": row.qso_id,
                "session_number": row.session_number,
                "status": row.status,
                "credited": row.credited,
                "points": row.points,
                "bonus_points": row.bonus_points,
                "penalty_points": row.penalty_points,
                "multiplier_count": row.multiplier_count,
                "multiplier_keys": row.multiplier_keys,
                "reason_codes": row.reason_codes,
                "explanation": row.explanation,
            }
            for row in breakdown
        ],
    }


@router.post("/contests/{contest_id}/qsos/{qso_id}/decisions", status_code=201)
def review_qso(
    contest_id: int,
    qso_id: int,
    payload: QsoReviewWrite,
    request: Request,
    principal: AuthenticatedUser,
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    if contest.id != contest_id:
        raise HTTPException(status_code=404, detail="Contest not found.")
    from backend.app.models import EntryRevision

    qso = session.scalar(
        select(Qso)
        .join(EntryRevision, EntryRevision.id == Qso.entry_revision_id)
        .join(Entry, Entry.id == EntryRevision.entry_id)
        .where(Qso.id == qso_id, Entry.contest_id == contest_id)
    )
    if qso is None:
        raise HTTPException(status_code=404, detail="QSO not found.")
    previous = session.scalar(
        select(QsoDecision)
        .where(QsoDecision.qso_id == qso.id)
        .order_by(QsoDecision.id.desc())
        .limit(1)
    )
    source = (
        QsoDecisionSource.GLOBAL_ADMINISTRATOR
        if principal.role is SystemRole.GLOBAL_ADMINISTRATOR
        else QsoDecisionSource.CONTEST_MANAGER
    )
    decision = QsoDecision(
        qso_id=qso.id,
        status=payload.status,
        source=source,
        reason_code=payload.reason_code,
        reason=payload.reason.strip(),
        evidence=payload.evidence,
        reviewer_user_id=principal.user_id,
        supersedes_decision_id=previous.id if previous else None,
    )
    session.add(decision)
    session.flush()
    record_audit_event(
        session,
        actor_user_id=principal.user_id,
        action="qso.decision.created",
        target_type="qso",
        target_id=qso.id,
        metadata={
            "decision_id": decision.id,
            "status": payload.status.value,
            "reason_code": payload.reason_code,
        },
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    runs = recalculate_contest(
        session,
        contest_id,
        trigger_key=f"review:{decision.id}",
        created_by_user_id=principal.user_id,
        trigger_kind="adjudication",
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return {
        "decision_id": decision.id,
        "status": decision.status.value,
        "score_runs": [_run_output(run) for run in runs],
    }
