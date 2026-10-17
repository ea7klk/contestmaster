from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.models.enums import (
    ContestStatus,
    EntryStatus,
    QsoDecisionSource,
    QsoDecisionStatus,
    ScoreRunStatus,
    SystemRole,
)
from backend.app.models.types import UTCDateTime, utc_now


def enum_column(enum_type: type, name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [member.value for member in values],
        length=max(len(member.value) for member in enum_type),
    )


class SystemUser(Base):
    __tablename__ = "system_users"
    __table_args__ = (
        CheckConstraint("length(trim(username)) > 0", name="username_not_blank"),
        CheckConstraint("length(trim(email_normalized)) > 0", name="email_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(80, collation="NOCASE"), nullable=False, unique=True
    )
    email_normalized: Mapped[str] = mapped_column(
        String(320, collation="NOCASE"), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[SystemRole] = mapped_column(enum_column(SystemRole, "system_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )


class SystemSession(Base):
    """Opaque privileged browser session; credentials are stored only as hashes."""

    __tablename__ = "system_sessions"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="session_token_hash_length"),
        CheckConstraint("length(csrf_token_hash) = 64", name="session_csrf_hash_length"),
        CheckConstraint("expires_at > created_at", name="session_expires_after_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("system_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    callsign_submitted: Mapped[str | None] = mapped_column(String(32))
    callsign_normalized: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ParticipantEmail(Base):
    __tablename__ = "participant_emails"
    __table_args__ = (
        UniqueConstraint("participant_id", "email_normalized", name="participant_email_unique"),
        CheckConstraint("length(trim(email_normalized)) > 0", name="email_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_normalized: Mapped[str] = mapped_column(
        String(320, collation="NOCASE"), nullable=False, unique=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ParticipantCallsign(Base):
    __tablename__ = "participant_callsigns"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "callsign_normalized", name="participant_callsign_unique"
        ),
        CheckConstraint("length(trim(callsign_submitted)) > 0", name="callsign_not_blank"),
        CheckConstraint("length(trim(callsign_normalized)) > 0", name="callsign_norm_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    callsign_submitted: Mapped[str] = mapped_column(String(32), nullable=False)
    callsign_normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ParticipantMagicLink(Base):
    __tablename__ = "participant_magic_links"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_email_id: Mapped[int] = mapped_column(
        ForeignKey("participant_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ParticipantEmailChange(Base):
    """Two-address confirmation required before a participant email can change."""

    __tablename__ = "participant_email_changes"
    __table_args__ = (
        CheckConstraint("length(old_token_hash) = 64", name="old_token_hash_length"),
        CheckConstraint("length(new_token_hash) = 64", name="new_token_hash_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    old_email_id: Mapped[int] = mapped_column(
        ForeignKey("participant_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    new_email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    old_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    new_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    old_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    new_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ParticipantPasswordReset(Base):
    __tablename__ = "participant_password_resets"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_email_id: Mapped[int] = mapped_column(
        ForeignKey("participant_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class SystemPasswordReset(Base):
    __tablename__ = "system_password_resets"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("system_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ParticipantSession(Base):
    """Revocable browser session for one verified participant email identity."""

    __tablename__ = "participant_sessions"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="session_token_hash_length"),
        CheckConstraint("length(csrf_token_hash) = 64", name="session_csrf_hash_length"),
        CheckConstraint("expires_at > created_at", name="session_expires_after_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_email_id: Mapped[int] = mapped_column(
        ForeignKey("participant_emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Contest(Base):
    __tablename__ = "contests"
    __table_args__ = (
        Index(
            "contest_series_occurrence_unique", "series_id", "series_occurrence_date", unique=True
        ),
        UniqueConstraint("id", "owner_user_id", name="contest_id_owner_unique"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(slug)) > 0", name="slug_not_blank"),
        CheckConstraint("starts_at < ends_at", name="start_before_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("contest_series.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    series_occurrence_date: Mapped[date | None] = mapped_column(Date)
    is_series_anchor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("system_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ruleset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("ruleset_versions.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120, collation="NOCASE"), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    periodicity: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    log_submission_cutoff_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    cutoff_is_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    status: Mapped[ContestStatus] = mapped_column(
        enum_column(ContestStatus, "contest_status"), nullable=False, default=ContestStatus.DRAFT
    )
    auto_recalculate_on_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )
    series: Mapped[ContestSeries | None] = relationship(back_populates="editions")


class ContestAdministrator(Base):
    """Additional contest admins; the creator remains owner on Contest.owner_user_id."""

    __tablename__ = "contest_administrators"
    __table_args__ = (CheckConstraint("user_id != added_by_user_id", name="admin_not_self_added"),)

    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("system_users.id", ondelete="CASCADE"), primary_key=True
    )
    added_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class Ruleset(Base):
    """Stable ruleset identity; owner_user_id is the permanent original owner."""

    __tablename__ = "rulesets"
    __table_args__ = (
        CheckConstraint("length(trim(ruleset_key)) > 0", name="ruleset_key_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruleset_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class RulesetAdministrator(Base):
    """Additional administrators; the ruleset creator remains its permanent owner."""

    __tablename__ = "ruleset_administrators"
    __table_args__ = (CheckConstraint("user_id != added_by_user_id", name="admin_not_self_added"),)

    ruleset_id: Mapped[int] = mapped_column(
        ForeignKey("rulesets.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("system_users.id", ondelete="CASCADE"), primary_key=True
    )
    added_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ContestSeries(Base):
    """Reusable UTC recurrence and template settings for independent contest editions."""

    __tablename__ = "contest_series"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="contest_series_name_not_blank"),
        CheckConstraint("length(trim(base_slug)) > 0", name="contest_series_slug_not_blank"),
        CheckConstraint(
            "start_time_seconds >= 0 AND start_time_seconds < 86400", name="series_start_time_valid"
        ),
        CheckConstraint("duration_seconds > 0", name="series_duration_positive"),
        CheckConstraint("cutoff_offset_seconds >= 0", name="series_cutoff_offset_nonnegative"),
        CheckConstraint(
            "automatic_window_days IS NULL OR automatic_window_days BETWEEN 1 AND 730",
            name="series_automatic_window_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("system_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_slug: Mapped[str] = mapped_column(String(120, collation="NOCASE"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    periodicity: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    start_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    cutoff_offset_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_window_days: Mapped[int | None] = mapped_column(Integer)
    auto_recalculate_on_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ruleset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("ruleset_versions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )
    editions: Mapped[list[Contest]] = relationship(back_populates="series")
    exceptions: Mapped[list[ContestSeriesException]] = relationship(back_populates="series")


class ContestSeriesException(Base):
    """A skipped or moved recurrence keyed by its original UTC scheduled date."""

    __tablename__ = "contest_series_exceptions"
    __table_args__ = (
        UniqueConstraint("series_id", "occurrence_date", name="series_exception_date_unique"),
        CheckConstraint("action IN ('skip', 'move')", name="series_exception_action_valid"),
        CheckConstraint(
            "(action = 'skip' AND moved_to_date IS NULL) OR "
            "(action = 'move' AND moved_to_date IS NOT NULL)",
            name="series_exception_move_date_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("contest_series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    moved_to_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    series: Mapped[ContestSeries] = relationship(back_populates="exceptions")


class ContestDeletionPermit(Base):
    """Transactional database guard permitting removal of one contest's history."""

    __tablename__ = "contest_deletion_permits"

    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), primary_key=True
    )


class RulesetVersion(Base):
    __tablename__ = "ruleset_versions"
    __table_args__ = (
        UniqueConstraint("ruleset_key", "version", name="ruleset_key_version_unique"),
        CheckConstraint("length(trim(ruleset_key)) > 0", name="ruleset_key_not_blank"),
        CheckConstraint("length(trim(version)) > 0", name="version_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruleset_id: Mapped[int | None] = mapped_column(Integer, index=True)
    ruleset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_edition: Mapped[str | None] = mapped_column(String(120))
    rule_type_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class RulesetDeletionPermit(Base):
    """Transactional database guard permitting removal of one unused ruleset version."""

    __tablename__ = "ruleset_deletion_permits"

    ruleset_version_id: Mapped[int] = mapped_column(
        ForeignKey("ruleset_versions.id", ondelete="CASCADE"), primary_key=True
    )


class RulesetActivation(Base):
    __tablename__ = "ruleset_activations"
    __table_args__ = (
        CheckConstraint("length(configuration_sha256) = 64", name="configuration_digest_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ruleset_version_id: Mapped[int] = mapped_column(
        ForeignKey("ruleset_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    activated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    configuration_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("contest_id", "entry_key", name="contest_entry_key_unique"),
        UniqueConstraint("id", "contest_id", name="entry_id_contest_unique"),
        CheckConstraint("length(trim(entry_key)) > 0", name="entry_key_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Nullable for guest submissions; a participant is never a privileged system account.
    submitter_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL"), index=True
    )
    entry_key: Mapped[str] = mapped_column(String(120), nullable=False)
    category_key: Mapped[str | None] = mapped_column(String(120))
    category_values: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    is_late: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    status: Mapped[EntryStatus] = mapped_column(
        enum_column(EntryStatus, "entry_status"), nullable=False, default=EntryStatus.RECEIVED
    )
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class EntryRevision(Base):
    __tablename__ = "entry_revisions"
    __table_args__ = (
        UniqueConstraint("entry_id", "revision_number", name="entry_revision_number_unique"),
        UniqueConstraint("id", "entry_id", name="entry_revision_id_entry_unique"),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint("length(content_sha256) = 64", name="content_sha256_length"),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_format: Mapped[str] = mapped_column(String(40), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_content: Mapped[str] = mapped_column(Text, nullable=False)
    import_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    received_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    received_by_participant_email_id: Mapped[int | None] = mapped_column(
        ForeignKey("participant_emails.id", ondelete="SET NULL")
    )
    received_via: Mapped[str] = mapped_column(
        String(40), nullable=False, default="public_submission"
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class EntryAccessGrant(Base):
    __tablename__ = "entry_access_grants"
    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256_length"),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at", name="expires_after_created"
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="revoked_after_created"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    revoked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )


class LogSubmissionRequest(Base):
    """Idempotency record for public submissions; keys are never stored verbatim."""

    __tablename__ = "log_submission_requests"
    __table_args__ = (
        UniqueConstraint("contest_id", "key_sha256", name="contest_submission_key_unique"),
        CheckConstraint("length(key_sha256) = 64", name="idempotency_key_hash_length"),
        CheckConstraint("length(content_sha256) = 64", name="submission_content_hash_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("id", "entry_revision_id", name="station_id_revision_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_revision_id: Mapped[int] = mapped_column(
        ForeignKey("entry_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    callsign_submitted: Mapped[str] = mapped_column(String(32), nullable=False)
    callsign_normalized: Mapped[str | None] = mapped_column(String(32))
    operator_name_submitted: Mapped[str | None] = mapped_column(String(160))
    grid_submitted: Mapped[str | None] = mapped_column(String(16))
    station_configuration: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class Qso(Base):
    __tablename__ = "qsos"
    __table_args__ = (
        UniqueConstraint("id", "entry_revision_id", name="qso_id_revision_unique"),
        UniqueConstraint(
            "entry_revision_id", "source_line_number", name="qso_revision_line_unique"
        ),
        ForeignKeyConstraint(
            ["station_id", "entry_revision_id"],
            ["stations.id", "stations.entry_revision_id"],
            ondelete="RESTRICT",
            name="qso_station_revision_fk",
        ),
        ForeignKeyConstraint(
            ["worked_entity_id", "resolved_master_data_version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            ondelete="RESTRICT",
            name="qso_entity_snapshot_fk",
        ),
        ForeignKeyConstraint(
            ["worked_cq_zone_id", "resolved_master_data_version_id"],
            ["cq_zones.id", "cq_zones.version_id"],
            ondelete="RESTRICT",
            name="qso_cq_zone_snapshot_fk",
        ),
        ForeignKeyConstraint(
            ["worked_itu_zone_id", "resolved_master_data_version_id"],
            ["itu_zones.id", "itu_zones.version_id"],
            ondelete="RESTRICT",
            name="qso_itu_zone_snapshot_fk",
        ),
        CheckConstraint(
            "source_line_number IS NULL OR source_line_number > 0", name="source_line_positive"
        ),
        CheckConstraint(
            "resolved_master_data_version_id IS NOT NULL OR "
            "(worked_entity_id IS NULL AND worked_cq_zone_id IS NULL "
            "AND worked_itu_zone_id IS NULL)",
            name="resolved_references_require_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_revision_id: Mapped[int] = mapped_column(
        ForeignKey("entry_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    station_id: Mapped[int | None] = mapped_column(Integer)
    source_line_number: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    callsign_submitted: Mapped[str] = mapped_column(String(32), nullable=False)
    callsign_normalized: Mapped[str | None] = mapped_column(String(32), index=True)
    band: Mapped[str | None] = mapped_column(String(24), index=True)
    mode: Mapped[str | None] = mapped_column(String(40), index=True)
    exchange_sent_submitted: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    exchange_sent_normalized: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    exchange_received_submitted: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    exchange_received_normalized: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_fields: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    resolved_master_data_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT")
    )
    worked_entity_id: Mapped[int | None] = mapped_column(Integer)
    worked_cq_zone_id: Mapped[int | None] = mapped_column(Integer)
    worked_itu_zone_id: Mapped[int | None] = mapped_column(Integer)


class QsoDecision(Base):
    __tablename__ = "qso_decisions"
    __table_args__ = (
        CheckConstraint(
            "supersedes_decision_id IS NULL OR supersedes_decision_id != id",
            name="cannot_supersede_self",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qso_id: Mapped[int] = mapped_column(
        ForeignKey("qsos.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[QsoDecisionStatus] = mapped_column(
        enum_column(QsoDecisionStatus, "qso_decision_status"), nullable=False
    )
    source: Mapped[QsoDecisionSource] = mapped_column(
        enum_column(QsoDecisionSource, "qso_decision_source"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reviewer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    supersedes_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("qso_decisions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ScoreRun(Base):
    __tablename__ = "score_runs"
    __table_args__ = (
        UniqueConstraint(
            "entry_revision_id", "run_number", name="entry_revision_run_number_unique"
        ),
        UniqueConstraint("id", "entry_revision_id", name="score_run_id_revision_unique"),
        ForeignKeyConstraint(
            ["entry_revision_id", "entry_id"],
            ["entry_revisions.id", "entry_revisions.entry_id"],
            ondelete="RESTRICT",
            name="score_run_revision_entry_fk",
        ),
        CheckConstraint("run_number > 0", name="run_number_positive"),
        CheckConstraint(
            "claimed_points IS NULL OR claimed_points >= 0", name="claimed_points_nonnegative"
        ),
        CheckConstraint(
            "points >= 0 AND multiplier_count >= 0 AND bonus_points >= 0 "
            "AND penalty_points >= 0 AND final_score >= 0 "
            "AND (adjudicated_score IS NULL OR adjudicated_score >= 0)",
            name="score_values_nonnegative",
        ),
        CheckConstraint(
            "typeof(points) = 'integer' AND typeof(multiplier_count) = 'integer' "
            "AND typeof(bonus_points) = 'integer' AND typeof(penalty_points) = 'integer' "
            "AND typeof(final_score) = 'integer' "
            "AND (adjudicated_score IS NULL OR typeof(adjudicated_score) = 'integer') "
            "AND (claimed_points IS NULL OR typeof(claimed_points) = 'integer')",
            name="score_values_integer_storage",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="RESTRICT"), nullable=False
    )
    entry_revision_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ruleset_version_id: Mapped[int] = mapped_column(
        ForeignKey("ruleset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    master_data_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT")
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    status: Mapped[ScoreRunStatus] = mapped_column(
        enum_column(ScoreRunStatus, "score_run_status"),
        nullable=False,
        default=ScoreRunStatus.QUEUED,
    )
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    master_data_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    claimed_points: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    multiplier_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalty_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adjudicated_score: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("system_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class QsoScore(Base):
    __tablename__ = "qso_scores"
    __table_args__ = (
        UniqueConstraint("score_run_id", "qso_id", name="score_run_qso_unique"),
        ForeignKeyConstraint(
            ["score_run_id", "entry_revision_id"],
            ["score_runs.id", "score_runs.entry_revision_id"],
            ondelete="CASCADE",
            name="qso_score_run_revision_fk",
        ),
        ForeignKeyConstraint(
            ["qso_id", "entry_revision_id"],
            ["qsos.id", "qsos.entry_revision_id"],
            ondelete="RESTRICT",
            name="qso_score_qso_revision_fk",
        ),
        CheckConstraint(
            "points >= 0 AND bonus_points >= 0 AND penalty_points >= 0 AND multiplier_count >= 0",
            name="qso_score_values_nonnegative",
        ),
        CheckConstraint(
            "typeof(points) = 'integer' AND typeof(penalty_points) = 'integer' "
            "AND typeof(multiplier_count) = 'integer' AND typeof(bonus_points) = 'integer'",
            name="qso_score_values_integer_storage",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    score_run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    qso_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entry_revision_id: Mapped[int] = mapped_column(Integer, nullable=False)
    credited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalty_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    multiplier_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    multiplier_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="credited")
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
