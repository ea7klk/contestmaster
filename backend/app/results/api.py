"""Manager result workflows and unauthenticated published result routes."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.adjudication.scoring import recalculate_contest
from backend.app.api.auth import AuthenticatedUser, require_contest_access
from backend.app.api.pagination import Page, page_meta
from backend.app.audit import record_audit_event
from backend.app.config import get_settings
from backend.app.db import SessionFactory, get_session
from backend.app.email_outbox import dispatch_pending_emails, queue_publication_notices
from backend.app.models import (
    Contest,
    ContestStatus,
    ResultPublication,
    ResultPublicationEntry,
    RulesetVersion,
)
from backend.app.results.service import (
    ResultPublicationError,
    current_publication,
    export_results_csv,
    export_results_json,
    list_result_candidates,
    public_result_row,
    publication_policy,
    publish_result_snapshot,
    unresolved_items,
)
from backend.app.rulesets.persistence import load_ruleset_version
from backend.app.rulesets.schema import CategoryRule

router = APIRouter(tags=["results"])
public_router = APIRouter(tags=["public results"])


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_run_ids: list[int] = Field(min_length=1, max_length=100_000)
    reason: str | None = Field(default=None, max_length=2000)


def _public_contest(contest: Contest, publication: ResultPublication) -> dict[str, Any]:
    return {
        "id": contest.id,
        "name": contest.name,
        "slug": contest.slug,
        "description": contest.description,
        "starts_at": contest.starts_at,
        "ends_at": contest.ends_at,
        "status": contest.status.value,
        "publication": {
            "number": publication.publication_number,
            "published_at": publication.published_at,
            "source_digest": publication.source_digest,
            "entry_count": publication.entry_count,
            "withheld_count": publication.withheld_count,
        },
    }


def _ruleset_categories(session: Session, contest: Contest) -> dict[str, list[str]]:
    if contest.ruleset_version_id is None:
        return {}
    version = session.get(RulesetVersion, contest.ruleset_version_id)
    if version is None:
        return {}
    definition = load_ruleset_version(version)
    categories: dict[str, list[str]] = {}
    for configured in definition.rules:
        if isinstance(configured.rule, CategoryRule):
            for dimension in configured.rule.dimensions:
                categories[dimension.key] = [choice.key for choice in dimension.choices]
    return categories


def _manager_candidate(candidate) -> dict[str, Any]:
    run = candidate.score_run
    return {
        "entry_id": candidate.entry.id,
        "entry_status": candidate.entry.status.value,
        "is_late": candidate.entry.is_late,
        "revision_id": candidate.revision.id,
        "revision_number": candidate.revision.revision_number,
        "score_run_id": run.id,
        "score_run_status": run.status.value,
        "callsign": candidate.callsign,
        "category_values": candidate.entry.category_values,
        "result_status": candidate.status,
        "included_by_default": candidate.included_by_default,
        "score": run.final_score,
        "explanation": run.explanation,
    }


@router.post("/contests/{contest_id}/results/generate", status_code=202)
def generate_results(
    contest_id: int,
    payload: GenerateRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    contest: Annotated[Contest, Depends(require_contest_access)],
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    if contest.id != contest_id:
        raise HTTPException(status_code=404, detail="Contest not found.")
    if contest.status is ContestStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Open the contest before generating results.")
    runs = recalculate_contest(
        session,
        contest_id,
        trigger_key=f"manager-result-generation:{idempotency_key}",
        created_by_user_id=principal.user_id,
    )
    session.commit()
    unresolved = unresolved_items(session, contest)
    record_audit_event(
        session,
        actor_user_id=principal.user_id,
        action="contest.results_generated",
        target_type="contest",
        target_id=contest_id,
        reason=payload.reason,
        metadata={
            "score_run_ids": [run.id for run in runs],
            "unresolved_count": len(unresolved),
        },
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return {
        "contest_id": contest_id,
        "score_runs": [
            {"id": run.id, "entry_id": run.entry_id, "status": run.status.value} for run in runs
        ],
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
    }


@router.get("/contests/{contest_id}/results/review")
def review_results(
    contest_id: int,
    contest: Annotated[Contest, Depends(require_contest_access)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    if contest.id != contest_id:
        raise HTTPException(status_code=404, detail="Contest not found.")
    candidates = list_result_candidates(session, contest)
    unresolved = unresolved_items(session, contest)
    return {
        "contest_id": contest.id,
        "contest_slug": contest.slug,
        "status": contest.status.value,
        "publication_policy": publication_policy(session, contest),
        "items": [_manager_candidate(item) for item in candidates],
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
    }


@router.post("/contests/{contest_id}/results/publish", status_code=201)
def publish_results(
    contest_id: int,
    payload: PublishRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    contest: Annotated[Contest, Depends(require_contest_access)],
    principal: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    if contest.id != contest_id:
        raise HTTPException(status_code=404, detail="Contest not found.")
    if contest.status not in {ContestStatus.CLOSED, ContestStatus.PUBLISHED}:
        raise HTTPException(status_code=409, detail="Close the contest before publishing results.")
    try:
        publication = publish_result_snapshot(
            session,
            contest=contest,
            score_run_ids=payload.score_run_ids,
            published_by_user_id=principal.user_id,
        )
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="contest.results_published",
            target_type="contest_result_publication",
            target_id=publication.id,
            reason=payload.reason,
            metadata={
                "contest_id": contest.id,
                "publication_number": publication.publication_number,
                "source_digest": publication.source_digest,
                "entry_count": publication.entry_count,
                "withheld_count": publication.withheld_count,
            },
            request_id=getattr(request.state, "request_id", None),
        )
        queued_notice_count = queue_publication_notices(session, publication)
        session.commit()
    except ResultPublicationError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = get_settings()
    if queued_notice_count and settings.email_smtp_host and settings.email_from_address:
        background_tasks.add_task(dispatch_pending_emails, SessionFactory)
    return {
        "id": publication.id,
        "contest_id": contest.id,
        "publication_number": publication.publication_number,
        "source_digest": publication.source_digest,
        "entry_count": publication.entry_count,
        "withheld_count": publication.withheld_count,
        "published_at": publication.published_at,
        "status": contest.status.value,
        "queued_result_notices": queued_notice_count,
    }


@router.get("/public/contests/{slug}/results")
def get_public_results(
    slug: str,
    session: Annotated[Session, Depends(get_session)],
    page_number: Annotated[int, Query(ge=1, alias="page")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    category: Annotated[str | None, Query(max_length=120)] = None,
    value: Annotated[str | None, Query(max_length=120)] = None,
    band: Annotated[str | None, Query(max_length=24)] = None,
    mode: Annotated[str | None, Query(max_length=40)] = None,
    status: Annotated[str | None, Query(max_length=24)] = None,
    sort: Literal["placement", "score", "callsign", "status"] = "placement",
    order: Literal["asc", "desc"] = "asc",
) -> dict[str, Any]:
    contest = session.scalar(
        select(Contest).where(Contest.slug == slug, Contest.status == ContestStatus.PUBLISHED)
    )
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    publication = current_publication(session, contest)
    if publication is None:
        raise HTTPException(status_code=404, detail="Contest results not found.")
    dimensions = _ruleset_categories(session, contest)
    filters = []
    if category is not None:
        if category not in dimensions:
            raise HTTPException(status_code=422, detail="Select a configured category.")
        if value is not None and value not in dimensions[category]:
            raise HTTPException(status_code=422, detail="Unknown value for configured category.")
        if value is not None:
            filters.append(ResultPublicationEntry.category_values[category].as_string() == value)
    elif value is not None:
        raise HTTPException(status_code=422, detail="A category is required with a category value.")
    for dimension_key, selected_value in (("band", band), ("mode", mode)):
        if selected_value is not None:
            configured_key = next(
                (key for key in dimensions if key.casefold() == dimension_key), None
            )
            if configured_key is None or selected_value not in dimensions[configured_key]:
                raise HTTPException(
                    status_code=422,
                    detail=f"{dimension_key.title()} filter is not configured for this contest.",
                )
            filters.append(
                ResultPublicationEntry.category_values[configured_key].as_string() == selected_value
            )
    allowed_statuses = {
        "scored",
        "late",
        "checklog",
        "needs_review",
        "reclassified",
        "disqualified",
    }
    if status is not None:
        if status not in allowed_statuses:
            raise HTTPException(status_code=422, detail="Unknown result status filter.")
        filters.append(ResultPublicationEntry.status == status)
    statement = select(ResultPublicationEntry).where(
        ResultPublicationEntry.publication_id == publication.id, *filters
    )
    page = Page(page=page_number, page_size=page_size, sort=sort, order=order)
    count = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    sort_field = {
        "placement": ResultPublicationEntry.placement,
        "score": ResultPublicationEntry.score,
        "callsign": ResultPublicationEntry.callsign,
        "status": ResultPublicationEntry.status,
    }[sort]
    direction = sort_field.asc() if order == "asc" else sort_field.desc()
    ordering = (
        [ResultPublicationEntry.placement.is_(None).asc(), direction]
        if sort == "placement"
        else [direction, ResultPublicationEntry.callsign.asc()]
    )
    rows = list(
        session.scalars(
            statement.order_by(
                *ordering,
                ResultPublicationEntry.id.asc(),
            )
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    )
    all_rows = list(
        session.scalars(
            select(ResultPublicationEntry)
            .where(ResultPublicationEntry.publication_id == publication.id)
            .order_by(ResultPublicationEntry.callsign)
        )
    )
    available = {
        key: sorted(
            {str(row.category_values[key]) for row in all_rows if key in row.category_values}
        )
        for key in dimensions
    }
    return {
        "contest": _public_contest(contest, publication),
        "items": [public_result_row(row) for row in rows],
        "filters": {
            "categories": [{"key": key, "values": available.get(key, [])} for key in dimensions],
            "bands": next(
                (items for key, items in available.items() if key.casefold() == "band"), []
            ),
            "modes": next(
                (items for key, items in available.items() if key.casefold() == "mode"), []
            ),
            "statuses": sorted({row.status for row in all_rows}),
        },
        "meta": page_meta(page, count),
    }


@public_router.get("/public/contests/{slug}/results/entries/{result_entry_id}")
def get_public_result_detail(
    slug: str,
    result_entry_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    contest = session.scalar(
        select(Contest).where(Contest.slug == slug, Contest.status == ContestStatus.PUBLISHED)
    )
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    publication = current_publication(session, contest)
    row = (
        session.scalar(
            select(ResultPublicationEntry).where(
                ResultPublicationEntry.id == result_entry_id,
                ResultPublicationEntry.publication_id == publication.id,
            )
        )
        if publication
        else None
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Published result not found.")
    return {"contest": _public_contest(contest, publication), "item": public_result_row(row)}


@public_router.get("/public/contests/{slug}/results/export")
def export_public_results(
    slug: str,
    session: Annotated[Session, Depends(get_session)],
    export_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
) -> Response:
    contest = session.scalar(
        select(Contest).where(Contest.slug == slug, Contest.status == ContestStatus.PUBLISHED)
    )
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    publication = current_publication(session, contest)
    if publication is None:
        raise HTTPException(status_code=404, detail="Contest results not found.")
    rows = list(
        session.scalars(
            select(ResultPublicationEntry)
            .where(ResultPublicationEntry.publication_id == publication.id)
            .order_by(
                ResultPublicationEntry.placement.is_(None).asc(),
                ResultPublicationEntry.placement,
                ResultPublicationEntry.callsign,
            )
        )
    )
    filename = f"{contest.slug}-results-v1.{export_format}"
    headers = {
        "X-Contestmaster-Export-Version": "results-v1",
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    if export_format == "csv":
        return Response(
            export_results_csv(rows), media_type="text/csv; charset=utf-8", headers=headers
        )
    data = export_results_json(contest, publication, rows)
    return Response(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        media_type="application/json",
        headers=headers,
    )
