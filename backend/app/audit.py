"""Transactional helpers for append-only administrative audit events."""

from sqlalchemy.orm import Session

from backend.app.models import AuditEvent


def record_audit_event(
    session: Session,
    *,
    actor_user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | str,
    reason: str | None = None,
    metadata: dict[str, object] | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Append safe event metadata in the same transaction as its administrative change.

    Callers must never include passwords, tokens, uploaded content, or unnecessary personal data
    in ``metadata``. The database prevents updates and deletes after this event is written.
    """
    normalized_reason = reason.strip() if reason and reason.strip() else None
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        reason=normalized_reason,
        event_metadata=metadata or {},
        request_id=request_id,
    )
    session.add(event)
    return event
