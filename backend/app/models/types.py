from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware instants as fixed-width UTC ISO-8601 text at microsecond precision."""

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        normalized = value.astimezone(UTC)
        return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_result_value(self, value: str | None, _dialect) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Stored UTCDateTime value is missing its UTC offset")
        return parsed.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)
