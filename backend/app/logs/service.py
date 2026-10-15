"""Short-transaction persistence for parsed entry revisions."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.logs.cabrillo import ParsedLog
from backend.app.models import (
    Contest,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    EntryStatus,
    LogSubmissionRequest,
    Participant,
    ParticipantEmail,
    Qso,
    Station,
)


class IdempotencyConflict(ValueError):
    pass


def recalculate_after_accepted_upload(
    session: Session, *, contest_id: int, entry_id: int, revision_id: int, replayed: bool
) -> list[dict[str, int | str]]:
    """Honor the contest toggle only after a newly accepted revision has committed."""
    if replayed:
        return []
    contest = session.get(Contest, contest_id)
    if contest is None or not contest.auto_recalculate_on_upload:
        return []
    from backend.app.adjudication.scoring import recalculate_contest

    runs = recalculate_contest(
        session,
        contest_id,
        trigger_key=f"accepted-upload:entry:{entry_id}:revision:{revision_id}",
    )
    session.commit()
    return [{"id": run.id, "entry_id": run.entry_id, "status": run.status.value} for run in runs]


def digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _header(parsed: ParsedLog, name: str) -> str | None:
    selected = parsed.header_aliases.get(name.casefold(), name.upper())
    values = parsed.headers.get(selected, [])
    return values[0].strip() if values and values[0].strip() else None


def persist_revision(
    session: Session,
    *,
    entry: Entry,
    parsed: ParsedLog,
    original_content: str,
    filename: str,
    content_type: str | None,
    category_values: dict[str, str],
    received_by_user_id: int | None = None,
    received_by_participant_email_id: int | None = None,
    received_via: str = "public_submission",
    created_at: datetime | None = None,
    import_format: str = "cabrillo",
) -> EntryRevision:
    """Append a complete revision and its normalized station/QSO rows atomically."""
    now = created_at or datetime.now(UTC)
    revision_number = (
        session.scalar(
            select(func.max(EntryRevision.revision_number)).where(
                EntryRevision.entry_id == entry.id
            )
        )
        or 0
    ) + 1
    content_sha256 = digest(original_content)
    revision = EntryRevision(
        entry_id=entry.id,
        revision_number=revision_number,
        input_format=import_format,
        original_filename=filename,
        content_type=content_type,
        storage_key=f"database://entry-revisions/{entry.id}/{revision_number}",
        original_content=original_content,
        import_metadata={
            "headers": parsed.headers,
            "header_aliases": parsed.header_aliases,
            "unknown_headers": parsed.unknown_headers,
            "warnings": [
                {"line": message.line, "code": message.code, "message": message.message}
                for message in parsed.warnings
            ],
            "category_values": category_values,
        },
        content_sha256=content_sha256,
        byte_size=len(original_content.encode("utf-8")),
        submitted_at=now,
        received_at=now,
        received_by_user_id=received_by_user_id,
        received_by_participant_email_id=received_by_participant_email_id,
        received_via=received_via,
    )
    session.add(revision)
    session.flush()
    entry.category_values = category_values
    entry.category_key = (
        ",".join(f"{key}={value}" for key, value in sorted(category_values.items())) or None
    )
    station_call = _header(parsed, "CALLSIGN") or "UNKNOWN"
    station = Station(
        entry_revision_id=revision.id,
        callsign_submitted=station_call,
        callsign_normalized="".join(station_call.upper().split()),
        operator_name_submitted=_header(parsed, "NAME"),
        grid_submitted=_header(parsed, "LOCATION") or _header(parsed, "GRID-LOCATOR"),
        station_configuration={
            "operators": parsed.headers.get("OPERATORS", []),
            "unknown_headers": parsed.unknown_headers,
        },
    )
    session.add(station)
    session.flush()
    for qso in parsed.qsos:
        session.add(
            Qso(
                entry_revision_id=revision.id,
                station_id=station.id,
                source_line_number=qso.line,
                occurred_at=qso.occurred_at,
                callsign_submitted=qso.callsign_received,
                callsign_normalized="".join(qso.callsign_received.upper().split()),
                band=qso.frequency,
                mode=qso.mode.upper(),
                exchange_sent_submitted={"raw": qso.exchange_sent, "rst": qso.rst_sent},
                exchange_received_submitted={"raw": qso.exchange_received, "rst": qso.rst_received},
                source_fields={**qso.fields, "extra_fields": qso.extra_fields},
            )
        )
    return revision


def create_guest_entry(
    session: Session,
    *,
    contest: Contest,
    parsed: ParsedLog,
    content: str,
    filename: str,
    content_type: str | None,
    category_values: dict[str, str],
    request_key_hash: str,
    content_sha256: str,
    receipt_token: str,
    is_late: bool = False,
    late_policy: str = "accept_late",
) -> tuple[Entry, str, bool]:
    """Create an entry, receipt grant, first revision, and idempotency row together."""
    previous = session.scalar(
        select(LogSubmissionRequest).where(
            LogSubmissionRequest.contest_id == contest.id,
            LogSubmissionRequest.key_sha256 == request_key_hash,
        )
    )
    if previous is not None:
        if previous.content_sha256 != content_sha256:
            raise IdempotencyConflict(
                "This idempotency key was already used for different content."
            )
        entry = session.get(Entry, previous.entry_id)
        if entry is None:
            raise IdempotencyConflict("The original submission is no longer available.")
        return entry, receipt_token, True

    call = _header(parsed, "CALLSIGN") or ""
    email_address = _header(parsed, "EMAIL")
    participant: Participant | None = None
    if email_address:
        normalized_email = email_address.strip().casefold()
        email_row = session.scalar(
            select(ParticipantEmail).where(ParticipantEmail.email_normalized == normalized_email)
        )
        if email_row is not None:
            participant = session.get(Participant, email_row.participant_id)
        else:
            participant = Participant(
                display_name=_header(parsed, "NAME"),
                callsign_submitted=call,
                callsign_normalized="".join(call.upper().split()),
            )
            session.add(participant)
            session.flush()
            session.add(
                ParticipantEmail(participant_id=participant.id, email_normalized=normalized_email)
            )
    if participant is None:
        participant = Participant(
            display_name=_header(parsed, "NAME"),
            callsign_submitted=call,
            callsign_normalized="".join(call.upper().split()),
        )
        session.add(participant)
        session.flush()
    elif participant.display_name is None and _header(parsed, "NAME"):
        participant.display_name = _header(parsed, "NAME")
    if participant.callsign_submitted is None:
        participant.callsign_submitted = call
        participant.callsign_normalized = "".join(call.upper().split())

    entry = Entry(
        contest_id=contest.id,
        participant_id=participant.id,
        submitter_user_id=None,
        entry_key=secrets.token_urlsafe(18),
        status=EntryStatus.CHECKLOG
        if is_late and late_policy == "checklog"
        else EntryStatus.ACCEPTED,
        is_late=is_late,
    )
    session.add(entry)
    session.flush()
    persist_revision(
        session,
        entry=entry,
        parsed=parsed,
        original_content=content,
        filename=filename,
        content_type=content_type,
        category_values=category_values,
    )
    session.add(EntryAccessGrant(entry_id=entry.id, token_hash=digest(receipt_token)))
    session.add(
        LogSubmissionRequest(
            contest_id=contest.id,
            key_sha256=request_key_hash,
            content_sha256=content_sha256,
            entry_id=entry.id,
        )
    )
    session.flush()
    return entry, receipt_token, False


def encode_contact_snapshot(contacts: list[dict[str, Any]], headers: dict[str, list[str]]) -> str:
    return json.dumps(
        {"headers": headers, "contacts": contacts}, sort_keys=True, separators=(",", ":")
    )
