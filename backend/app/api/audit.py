"""Global-administrator audit-log search API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from backend.app.api.auth import GlobalAdministrator
from backend.app.db import get_session
from backend.app.models import AuditEvent, SystemUser

router = APIRouter(prefix="/admin/audit-events", tags=["audit log"])
RETENTION = timedelta(days=90)


@router.get("")
def search_audit_events(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    q: str | None = Query(default=None, max_length=200),
    action: str | None = Query(default=None, max_length=100),
    target_type: str | None = Query(default=None, max_length=100),
    actor_user_id: int | None = Query(default=None, ge=1),
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    """Search recent events; retention is enforced in the query as a defense in depth."""
    now = datetime.now(UTC)
    cutoff = now - RETENTION
    if from_at is not None:
        if from_at.tzinfo is None or from_at.utcoffset() is None:
            raise HTTPException(status_code=422, detail="from_at must include a timezone.")
        from_at = from_at.astimezone(UTC)
        if from_at < cutoff:
            from_at = cutoff
    if to_at is not None:
        if to_at.tzinfo is None or to_at.utcoffset() is None:
            raise HTTPException(status_code=422, detail="to_at must include a timezone.")
        to_at = to_at.astimezone(UTC)
    if from_at and to_at and from_at > to_at:
        raise HTTPException(status_code=422, detail="from_at must not be later than to_at.")

    statement = select(AuditEvent, SystemUser.username, SystemUser.display_name).outerjoin(
        SystemUser, AuditEvent.actor_user_id == SystemUser.id
    )
    count_statement = (
        select(func.count())
        .select_from(AuditEvent)
        .outerjoin(SystemUser, AuditEvent.actor_user_id == SystemUser.id)
    )
    conditions = [AuditEvent.occurred_at >= cutoff]
    if from_at is not None:
        conditions.append(AuditEvent.occurred_at >= from_at)
    if to_at is not None:
        conditions.append(AuditEvent.occurred_at <= to_at)
    if action and action.strip():
        conditions.append(AuditEvent.action == action.strip())
    if target_type and target_type.strip():
        conditions.append(AuditEvent.target_type == target_type.strip())
    if actor_user_id is not None:
        conditions.append(AuditEvent.actor_user_id == actor_user_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                AuditEvent.action.ilike(pattern),
                AuditEvent.target_type.ilike(pattern),
                AuditEvent.target_id.ilike(pattern),
                AuditEvent.reason.ilike(pattern),
                cast(AuditEvent.event_metadata, String).ilike(pattern),
                SystemUser.username.ilike(pattern),
                SystemUser.display_name.ilike(pattern),
            )
        )
    statement = statement.where(*conditions)
    count_statement = count_statement.where(*conditions)
    rows = session.execute(
        statement.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for event, username, display_name in rows:
        items.append(
            {
                "id": event.id,
                "occurred_at": event.occurred_at,
                "actor_user_id": event.actor_user_id,
                "actor": display_name or username,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "reason": event.reason,
                "metadata": event.event_metadata,
                "request_id": event.request_id,
            }
        )
    return {
        "items": items,
        "total": session.scalar(count_statement) or 0,
        "page": page,
        "page_size": page_size,
        "retention_days": 90,
    }
