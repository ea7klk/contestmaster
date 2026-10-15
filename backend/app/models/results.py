"""Immutable, public-safe snapshots of contest result publications."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.types import UTCDateTime, utc_now


class ResultPublication(Base):
    __tablename__ = "result_publications"
    __table_args__ = (
        UniqueConstraint("contest_id", "publication_number", name="contest_publication_number"),
        CheckConstraint("publication_number > 0", name="publication_number_positive"),
        CheckConstraint(
            "entry_count >= 0 AND withheld_count >= 0", name="publication_counts_nonnegative"
        ),
        CheckConstraint("length(source_digest) = 64", name="publication_digest_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    publication_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    withheld_count: Mapped[int] = mapped_column(Integer, nullable=False)
    published_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    is_sealed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")


class ResultPublicationEntry(Base):
    __tablename__ = "result_publication_entries"
    __table_args__ = (
        UniqueConstraint("publication_id", "entry_id", name="publication_entry_unique"),
        CheckConstraint("score >= 0", name="published_score_nonnegative"),
        CheckConstraint(
            "points >= 0 AND multiplier_count >= 0 AND bonus_points >= 0 "
            "AND penalty_points >= 0 AND qso_count >= 0 AND credited_qso_count >= 0 "
            "AND (placement IS NULL OR placement > 0)",
            name="published_result_counts_nonnegative",
        ),
        CheckConstraint(
            "typeof(score) = 'integer' AND typeof(points) = 'integer' "
            "AND typeof(multiplier_count) = 'integer' AND typeof(bonus_points) = 'integer' "
            "AND typeof(penalty_points) = 'integer' AND typeof(qso_count) = 'integer' "
            "AND typeof(credited_qso_count) = 'integer'",
            name="published_result_integer_values",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("result_publications.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    score_run_id: Mapped[int] = mapped_column(
        ForeignKey("score_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    callsign: Mapped[str] = mapped_column(String(32), nullable=False)
    category_values: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplier_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_points: Mapped[int] = mapped_column(Integer, nullable=False)
    penalty_points: Mapped[int] = mapped_column(Integer, nullable=False)
    qso_count: Mapped[int] = mapped_column(Integer, nullable=False)
    credited_qso_count: Mapped[int] = mapped_column(Integer, nullable=False)
    placement: Mapped[int | None] = mapped_column(Integer)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
