from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.types import UTCDateTime, utc_now


class AdminNote(Base):
    """Private contest-staff notes; these are never part of public result serialization."""

    __tablename__ = "admin_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "contest_id"],
            ["entries.id", "entries.contest_id"],
            ondelete="RESTRICT",
            name="admin_note_entry_contest_fk",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_id: Mapped[int | None] = mapped_column(Integer, index=True)
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )


class AuditEvent(Base):
    """Append-only administrative event metadata; do not put secrets or log content here."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, index=True
    )
