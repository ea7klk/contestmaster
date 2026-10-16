"""Classification policy for uploads received after a contest cutoff."""

from datetime import UTC, datetime


def classify_submission(
    submitted_at: datetime,
    cutoff_at: datetime,
    late_policy: str,
    *,
    manager_extension_until: datetime | None = None,
    manager_extension_allowed: bool = False,
) -> str:
    """Return on_time, late, checklog, or rejected for a submission instant."""
    if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
        raise ValueError("submitted_at must be timezone-aware")
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff_at must be timezone-aware")
    if manager_extension_until is not None:
        if manager_extension_until.tzinfo is None or manager_extension_until.utcoffset() is None:
            raise ValueError("manager_extension_until must be timezone-aware")
        if manager_extension_until > cutoff_at and not manager_extension_allowed:
            raise ValueError("This ruleset does not allow manager cutoff extensions")
    cutoff = max(cutoff_at, manager_extension_until) if manager_extension_until else cutoff_at
    if submitted_at.astimezone(UTC) <= cutoff.astimezone(UTC):
        return "on_time"
    if late_policy == "accept_late":
        return "late"
    if late_policy == "checklog":
        return "checklog"
    return "rejected"
