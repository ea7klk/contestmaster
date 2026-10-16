"""Public guest log intake and entry-scoped revision/contact access."""

from __future__ import annotations

import hmac
import json
import re
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.api.auth import normalize_email
from backend.app.api.participant_identity import ParticipantPrincipal, require_participant
from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.logs.adif import parse_adif
from backend.app.logs.cabrillo import ImportMessage, ParsedLog, map_categories, parse_cabrillo
from backend.app.logs.service import (
    IdempotencyConflict,
    create_guest_entry,
    digest,
    persist_revision,
    recalculate_after_accepted_upload,
)
from backend.app.models import (
    Contest,
    ContestStatus,
    Entry,
    EntryAccessGrant,
    EntryRevision,
    EntryStatus,
    LogSubmissionRequest,
    Qso,
    RulesetVersion,
    Station,
)
from backend.app.rate_limit import enforce_rate_limit, limiter
from backend.app.rulesets.persistence import load_ruleset_version
from backend.app.rulesets.schema import SubmissionRule

router = APIRouter(tags=["log submissions"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
FORMAT_SUFFIXES = {
    ".log": "cabrillo",
    ".cbr": "cabrillo",
    ".cabrillo": "cabrillo",
    ".txt": "cabrillo",
    ".adi": "adif",
    ".adif": "adif",
}
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
RATE_LIMIT_COUNT = 20
RATE_LIMIT_WINDOW_SECONDS = 60


def allow_submission(client_key: str, now: float) -> bool:
    allowed, _retry = limiter.allow(
        "guest-log-upload",
        client_key,
        limit=RATE_LIMIT_COUNT,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        now=now,
    )
    return allowed


def _message(message: ImportMessage) -> dict[str, object]:
    return {"line": message.line, "code": message.code, "message": message.message}


def _receipt_for_submission(contest_id: int, idempotency_key: str, content_sha256: str) -> str:
    message = f"entry-receipt-v1:{contest_id}:{idempotency_key}:{content_sha256}".encode()
    return hmac.digest(get_settings().entry_receipt_secret.encode(), message, "sha256").hex()


@router.get("/submittable-contests")
def list_submittable_contests(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    now = datetime.now(UTC)
    contests = list(
        session.scalars(
            select(Contest)
            .where(
                Contest.status == ContestStatus.OPEN,
                Contest.log_submission_cutoff_at > now,
            )
            .order_by(Contest.starts_at.desc(), Contest.id.asc())
        )
    )
    items = []
    for row in contests:
        accepted_formats = _contest_upload_formats(session, row)
        if accepted_formats:
            items.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "slug": row.slug,
                    "cutoff_at": row.log_submission_cutoff_at,
                    "accepted_formats": accepted_formats,
                }
            )
    return {"items": items}


def _contest_upload_formats(session: Session, contest: Contest) -> list[str]:
    if contest.ruleset_version_id is None:
        return ["cabrillo"]
    version = session.get(RulesetVersion, contest.ruleset_version_id)
    if version is None:
        return []
    definition = load_ruleset_version(version)
    return sorted(
        {
            configured.rule.format
            for configured in definition.rules
            if configured.rule.kind == "format_mapping"
            and configured.rule.format in {"cabrillo", "adif"}
        }
    )


def _filename(value: str | None) -> str:
    basename = PurePosixPath((value or "").replace("\\", "/")).name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", basename).strip("._")
    return (safe or "upload.log")[:255]


async def _read_upload(request: Request) -> tuple[bytes, str | None, str | None]:
    """Read one bounded multipart file part without trusting Content-Length."""
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data;"):
        raise HTTPException(status_code=415, detail="Submit the log as a multipart file upload.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Log upload requests may not exceed 5 MiB plus multipart overhead.",
            )
    try:
        envelope = (
            b"MIME-Version: 1.0\r\nContent-Type: "
            + content_type.encode("latin-1")
            + b"\r\n\r\n"
            + bytes(body)
        )
        message = BytesParser(policy=policy.default).parsebytes(envelope)
    except (UnicodeEncodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="The multipart upload is malformed.") from exc
    if not message.is_multipart():
        raise HTTPException(status_code=400, detail="The multipart upload is malformed.")
    for part in message.iter_parts():
        if (
            part.get_content_disposition() == "form-data"
            and part.get_param("name", header="content-disposition") == "file"
        ):
            payload = part.get_payload(decode=True) or b""
            if len(payload) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Log files may not exceed 5 MiB.")
            return payload, part.get_filename(), part.get_content_type()
    raise HTTPException(status_code=422, detail="A file field is required.")


def _contest_rules(
    session: Session, slug: str
) -> tuple[int, str, str, object, str, dict[str, dict[str, object]]]:
    contest = session.scalar(select(Contest).where(Contest.slug == slug))
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    if contest.status is not ContestStatus.OPEN:
        raise HTTPException(
            status_code=409, detail="This contest is not accepting log submissions."
        )
    now = datetime.now(UTC)
    if contest.log_submission_cutoff_at <= now:
        raise HTTPException(status_code=409, detail="The log submission deadline has passed.")
    format_configs: dict[str, dict[str, object]] = {}
    late_policy = "accept_late"
    if contest.ruleset_version_id is not None:
        version = session.get(RulesetVersion, contest.ruleset_version_id)
        if version is None:
            raise HTTPException(status_code=409, detail="The contest ruleset is unavailable.")
        ruleset = load_ruleset_version(version)
        for configured in ruleset.rules:
            if configured.rule.kind == "format_mapping":
                format_configs[configured.rule.format] = {
                    "qso_columns": configured.rule.qso_columns or None,
                    "header_fields": configured.rule.header_fields,
                    "category_mappings": [
                        item.model_dump(mode="json") for item in configured.rule.category_mappings
                    ],
                }
            if isinstance(configured.rule, SubmissionRule):
                late_policy = configured.rule.late_policy
    # Read-only metadata is captured, then release the DB transaction before parsing.
    contest_id = contest.id
    contest_name = contest.name
    contest_slug = contest.slug
    contest_ends_at = contest.ends_at
    session.rollback()
    return (
        contest_id,
        contest_slug,
        contest_name,
        contest_ends_at,
        late_policy,
        format_configs,
    )


def _selected_format_config(
    format_configs: dict[str, dict[str, object]], upload_format: str
) -> dict[str, object]:
    # Legacy contests without a stored ruleset keep their original Cabrillo behavior.
    if not format_configs and upload_format == "cabrillo":
        return {"qso_columns": None, "header_fields": {}, "category_mappings": []}
    config = format_configs.get(upload_format)
    if config is None:
        raise HTTPException(
            status_code=415,
            detail=f"This contest's ruleset does not accept {upload_format.upper()} logs.",
        )
    return config


def _parse_log(content: str, upload_format: str, config: dict[str, object]) -> ParsedLog:
    if upload_format == "adif":
        return parse_adif(content)
    return parse_cabrillo(
        content,
        qso_columns=config.get("qso_columns") or None,
        header_fields=config.get("header_fields") or {},
    )


def _validate_log(
    parsed: ParsedLog,
    contest_slug: str,
    contest_name: str,
    mappings: list[dict[str, object]],
) -> tuple[dict[str, str], list[ImportMessage]]:
    errors = list(parsed.errors)
    contest_header = parsed.header_aliases.get("contest", "CONTEST")
    declared_contest = parsed.headers.get(contest_header, [""])[0].strip().casefold()
    if declared_contest and declared_contest not in {
        contest_slug.casefold(),
        contest_name.casefold(),
    }:
        errors.append(
            ImportMessage(
                0,
                "contest_mismatch",
                "The Cabrillo CONTEST header does not match the selected contest.",
            )
        )
    email = parsed.headers.get("EMAIL", [])
    if email:
        try:
            normalize_email(email[0])
        except ValueError:
            errors.append(
                ImportMessage(0, "invalid_email", "The EMAIL header is not a valid email address.")
            )
    categories, category_warnings = map_categories(parsed, mappings)
    return categories, [*errors, *category_warnings]


def _optional_participant(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> ParticipantPrincipal | None:
    try:
        return require_participant(request, session)
    except HTTPException:
        return None


@router.post("/contests/{contest_slug}/logs", status_code=201)
async def submit_log(
    contest_slug: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, object]:
    """Accept a complete ruleset-supported log anonymously and atomically."""
    if not _IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(status_code=400, detail="Idempotency-Key has an invalid format.")
    enforce_rate_limit(
        request,
        "guest-log-upload",
        limit=RATE_LIMIT_COUNT,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
        message="Too many log submissions. Retry later.",
    )
    content_bytes, upload_filename, content_type = await _read_upload(request)
    filename = _filename(upload_filename)
    suffix = PurePosixPath(filename).suffix.casefold()
    upload_format = FORMAT_SUFFIXES.get(suffix)
    if upload_format is None:
        raise HTTPException(
            status_code=415,
            detail=(
                "Use a supported Cabrillo (.log/.cbr/.cabrillo/.txt) or ADI/ADIF (.adi/.adif) file."
            ),
        )
    if not content_bytes:
        raise HTTPException(status_code=422, detail="The uploaded log file is empty.")
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="The log file must be UTF-8 encoded.") from exc
    (
        contest_id,
        selected_slug,
        selected_name,
        contest_ends_at,
        late_policy,
        format_configs,
    ) = _contest_rules(session, contest_slug)
    format_config = _selected_format_config(format_configs, upload_format)
    category_mappings = format_config["category_mappings"]
    parsed = _parse_log(content, upload_format, format_config)
    category_values, validation = _validate_log(
        parsed, selected_slug, selected_name, category_mappings
    )
    errors = [message for message in validation if message.code not in {"unmapped_category"}]
    warnings = [
        *parsed.warnings,
        *(message for message in validation if message.code == "unmapped_category"),
    ]
    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "summary": {
                    "accepted_qsos": 0,
                    "rejected_qsos": len(parsed.qsos),
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                },
                "errors": [_message(message) for message in errors],
                "warnings": [_message(message) for message in warnings],
            },
        )

    key_hash = digest(idempotency_key)
    content_hash = digest(content_bytes)
    receipt_token = _receipt_for_submission(contest_id, idempotency_key, content_hash)
    is_late = datetime.now(UTC) > contest_ends_at
    if is_late and late_policy == "reject":
        raise HTTPException(status_code=409, detail="This contest does not accept late logs.")
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        contest = session.get(Contest, contest_id)
        if (
            contest is None
            or contest.status is not ContestStatus.OPEN
            or contest.log_submission_cutoff_at <= datetime.now(UTC)
            or (is_late and late_policy == "reject")
        ):
            session.rollback()
            raise HTTPException(
                status_code=409, detail="This contest is no longer accepting log submissions."
            )
        entry, receipt_token, replayed = create_guest_entry(
            session,
            contest=contest,
            parsed=parsed,
            content=content,
            filename=filename,
            content_type=content_type,
            category_values=category_values,
            request_key_hash=key_hash,
            content_sha256=content_hash,
            receipt_token=receipt_token,
            is_late=is_late,
            late_policy=late_policy,
            import_format=upload_format,
        )
        session.commit()
    except IdempotencyConflict as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    revision = _latest_revision(session, entry.id)
    score_runs = (
        recalculate_after_accepted_upload(
            session,
            contest_id=contest_id,
            entry_id=entry.id,
            revision_id=revision.id if revision else 0,
            replayed=replayed,
        )
        if revision
        else []
    )
    return {
        "status": "accepted",
        "replayed": replayed,
        "entry_id": entry.id,
        "entry_key": entry.entry_key,
        "receipt_token": receipt_token or None,
        "receipt_token_replayed": replayed,
        "summary": {
            "accepted_qsos": len(parsed.qsos),
            "rejected_qsos": 0,
            "error_count": 0,
            "warning_count": len(warnings),
        },
        "errors": [],
        "warnings": [_message(message) for message in warnings],
        "score_runs": score_runs,
    }


@router.put("/entries/{entry_id}/log", response_model=None)
async def resubmit_log(
    entry_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    receipt: Annotated[str | None, Header(alias="X-Entry-Receipt")] = None,
    participant: Annotated[ParticipantPrincipal | None, Depends(_optional_participant)] = None,
) -> dict[str, object] | JSONResponse:
    enforce_rate_limit(
        request,
        "entry-log-revision",
        limit=60,
        window_seconds=60,
        message="Too many entry changes. Retry later.",
    )
    if not _IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(status_code=400, detail="Idempotency-Key has an invalid format.")
    content_bytes, upload_filename, content_type = await _read_upload(request)
    filename = _filename(upload_filename)
    upload_format = FORMAT_SUFFIXES.get(PurePosixPath(filename).suffix.casefold())
    if upload_format is None:
        raise HTTPException(
            status_code=415, detail="Use a supported Cabrillo or ADI/ADIF log file."
        )
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="The log file must be UTF-8 encoded.") from exc
    entry = _entry_and_authorize(entry_id, request, session, receipt, participant)
    contest = session.get(Contest, entry.contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    contest_id, contest_slug, contest_name = contest.id, contest.slug, contest.name
    contest_ends_at = contest.ends_at
    late_policy = "accept_late"
    format_configs: dict[str, dict[str, object]] = {}
    if contest.ruleset_version_id is not None:
        ruleset_row = session.get(RulesetVersion, contest.ruleset_version_id)
        if ruleset_row:
            ruleset = load_ruleset_version(ruleset_row)
            for configured in ruleset.rules:
                if configured.rule.kind == "format_mapping":
                    format_configs[configured.rule.format] = {
                        "qso_columns": configured.rule.qso_columns or None,
                        "header_fields": configured.rule.header_fields,
                        "category_mappings": [
                            item.model_dump(mode="json")
                            for item in configured.rule.category_mappings
                        ],
                    }
                if isinstance(configured.rule, SubmissionRule):
                    late_policy = configured.rule.late_policy
    session.rollback()
    format_config = _selected_format_config(format_configs, upload_format)
    parsed = _parse_log(content, upload_format, format_config)
    category_values, validation = _validate_log(
        parsed, contest_slug, contest_name, format_config["category_mappings"]
    )
    errors = [message for message in validation if message.code != "unmapped_category"]
    warnings = [
        *parsed.warnings,
        *(message for message in validation if message.code == "unmapped_category"),
    ]
    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "summary": {
                    "accepted_qsos": 0,
                    "rejected_qsos": len(parsed.qsos),
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                },
                "errors": [_message(message) for message in errors],
                "warnings": [_message(message) for message in warnings],
            },
        )

    session.execute(text("BEGIN IMMEDIATE"))
    current = session.get(Entry, entry_id)
    current_contest = session.get(Contest, contest_id)
    if current is None:
        session.rollback()
        raise HTTPException(status_code=404, detail="Entry not found.")
    _authorize_entry(
        current, request=request, session=session, receipt=receipt, participant=participant
    )
    now = datetime.now(UTC)
    is_late = now > contest_ends_at
    if current.status in {EntryStatus.WITHDRAWN, EntryStatus.DISQUALIFIED}:
        session.rollback()
        raise HTTPException(status_code=409, detail="This entry cannot accept a log revision.")
    if (
        current_contest is None
        or current_contest.status is ContestStatus.PUBLISHED
        or current_contest.log_submission_cutoff_at <= now
    ):
        session.rollback()
        raise HTTPException(status_code=409, detail="The log submission deadline has passed.")
    if is_late and late_policy == "reject":
        session.rollback()
        raise HTTPException(status_code=409, detail="This contest does not accept late logs.")
    key_hash = digest(idempotency_key)
    content_hash = digest(content_bytes)
    previous = session.scalar(
        select(LogSubmissionRequest).where(
            LogSubmissionRequest.contest_id == contest_id,
            LogSubmissionRequest.key_sha256 == key_hash,
        )
    )
    if previous is not None:
        if previous.entry_id != current.id or previous.content_sha256 != content_hash:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail="This idempotency key was already used for another submission.",
            )
        session.rollback()
        return {"status": "accepted", "replayed": True, **_entry_output(session, current)}

    revision = persist_revision(
        session,
        entry=current,
        parsed=parsed,
        original_content=content,
        filename=filename,
        content_type=content_type,
        category_values=category_values,
        received_by_user_id=None,
        received_by_participant_email_id=(
            participant.participant_email_id if participant is not None else None
        ),
        received_via="participant_session" if participant is not None else "entry_receipt",
        import_format=upload_format,
    )
    current.is_late = is_late
    if is_late and late_policy == "checklog":
        current.status = EntryStatus.CHECKLOG
    session.add(
        LogSubmissionRequest(
            contest_id=contest_id,
            key_sha256=key_hash,
            content_sha256=content_hash,
            entry_id=current.id,
        )
    )
    session.commit()
    score_runs = recalculate_after_accepted_upload(
        session,
        contest_id=contest_id,
        entry_id=current.id,
        revision_id=revision.id,
        replayed=False,
    )
    return {
        "status": "accepted",
        "replayed": False,
        "entry_id": current.id,
        "revision_number": revision.revision_number,
        "summary": {
            "accepted_qsos": len(parsed.qsos),
            "rejected_qsos": 0,
            "error_count": 0,
            "warning_count": len(warnings),
        },
        "errors": [],
        "warnings": [_message(message) for message in warnings],
        "score_runs": score_runs,
    }


def _latest_revision(session: Session, entry_id: int) -> EntryRevision | None:
    return session.scalar(
        select(EntryRevision)
        .where(EntryRevision.entry_id == entry_id)
        .order_by(EntryRevision.revision_number.desc())
    )


def _authorize_entry(
    entry: Entry,
    *,
    request: Request,
    session: Session,
    receipt: str | None,
    participant: ParticipantPrincipal | None,
) -> None:
    now = datetime.now(UTC)
    if receipt:
        grants = session.scalars(
            select(EntryAccessGrant).where(EntryAccessGrant.entry_id == entry.id)
        )
        received_hash = digest(receipt)
        for grant in grants:
            import hmac

            if hmac.compare_digest(received_hash, grant.token_hash):
                if grant.revoked_at is None and (
                    grant.expires_at is None or grant.expires_at > now
                ):
                    return
                break
    if participant is None:
        try:
            participant = require_participant(request, session)
        except HTTPException:
            participant = None
    if participant is not None and participant.participant_id == entry.participant_id:
        return
    raise HTTPException(status_code=404, detail="Entry not found or access is no longer valid.")


def _entry_and_authorize(
    entry_id: int,
    request: Request,
    session: Session,
    receipt: str | None,
    participant: ParticipantPrincipal | None = None,
) -> Entry:
    enforce_rate_limit(
        request,
        "entry-access",
        limit=120,
        window_seconds=60,
        message="Too many entry access attempts. Retry later.",
    )
    entry = session.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    _authorize_entry(
        entry, request=request, session=session, receipt=receipt, participant=participant
    )
    return entry


def _entry_output(session: Session, entry: Entry) -> dict[str, object]:
    revision = _latest_revision(session, entry.id)
    qsos = (
        list(
            session.scalars(
                select(Qso)
                .where(Qso.entry_revision_id == revision.id)
                .order_by(Qso.source_line_number, Qso.id)
            )
        )
        if revision
        else []
    )
    return {
        "entry_id": entry.id,
        "contest_id": entry.contest_id,
        "entry_key": entry.entry_key,
        "category_values": entry.category_values,
        "revision_number": revision.revision_number if revision else None,
        "revision_id": revision.id if revision else None,
        "contacts": [
            {
                "id": qso.id,
                "occurred_at": qso.occurred_at,
                "callsign": qso.callsign_submitted,
                "frequency": qso.band,
                "mode": qso.mode,
                "exchange_sent": qso.exchange_sent_submitted,
                "exchange_received": qso.exchange_received_submitted,
            }
            for qso in qsos
        ],
    }


@router.get("/entries/{entry_id}")
def get_entry(
    entry_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    receipt: Annotated[str | None, Header(alias="X-Entry-Receipt")] = None,
    participant: Annotated[ParticipantPrincipal | None, Depends(_optional_participant)] = None,
) -> dict[str, object]:
    entry = _entry_and_authorize(entry_id, request, session, receipt, participant)
    return _entry_output(session, entry)


@router.get("/entries/{entry_id}/revisions/{revision_id}/download")
def download_entry_revision(
    entry_id: int,
    revision_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    receipt: Annotated[str | None, Header(alias="X-Entry-Receipt")] = None,
    participant: Annotated[ParticipantPrincipal | None, Depends(_optional_participant)] = None,
) -> Response:
    entry = _entry_and_authorize(entry_id, request, session, receipt, participant)
    revision = session.scalar(
        select(EntryRevision).where(
            EntryRevision.id == revision_id, EntryRevision.entry_id == entry.id
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Entry revision not found.")
    filename = _filename(revision.original_filename or f"entry-{entry.id}.log")
    return Response(
        revision.original_content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Contestmaster-Log-Format": f"{revision.input_format}-source-v1",
        },
    )


class ContactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: datetime
    callsign: str = Field(min_length=1, max_length=32)
    frequency: str = Field(min_length=1, max_length=24)
    mode: str = Field(min_length=1, max_length=40)
    exchange_sent: dict[str, str] = Field(default_factory=dict, max_length=40)
    exchange_received: dict[str, str] = Field(default_factory=dict, max_length=40)

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Contact time must include an explicit timezone offset")
        return value.astimezone(UTC)


def _contacts_for_revision(session: Session, revision_id: int) -> list[dict[str, object]]:
    contacts = list(
        session.scalars(
            select(Qso)
            .where(Qso.entry_revision_id == revision_id)
            .order_by(Qso.source_line_number, Qso.id)
        )
    )
    return [
        {
            "occurred_at": qso.occurred_at.isoformat(),
            "callsign": qso.callsign_submitted,
            "frequency": qso.band,
            "mode": qso.mode,
            "exchange_sent": qso.exchange_sent_submitted,
            "exchange_received": qso.exchange_received_submitted,
            "source_fields": qso.source_fields,
        }
        for qso in contacts
    ]


def _append_native_revision(
    session: Session,
    entry: Entry,
    contacts: list[dict[str, object]],
    participant: ParticipantPrincipal | None,
) -> None:
    prior = _latest_revision(session, entry.id)
    if prior is None:
        raise HTTPException(status_code=409, detail="Entry has no submitted revision.")
    parsed = ParsedLog(
        headers=prior.import_metadata.get("headers", {}),
        unknown_headers=prior.import_metadata.get("unknown_headers", []),
        qsos=[],
        errors=[],
        warnings=[],
        raw_lines=[],
        header_aliases=prior.import_metadata.get("header_aliases", {}),
    )
    text_value = json.dumps(
        {"format": "contestmaster-native-v1", "contacts": contacts},
        sort_keys=True,
        separators=(",", ":"),
    )
    revision = persist_revision(
        session,
        entry=entry,
        parsed=parsed,
        original_content=text_value,
        filename=prior.original_filename or "entry.json",
        content_type="application/json",
        category_values=entry.category_values,
        received_by_user_id=None,
        received_by_participant_email_id=(
            participant.participant_email_id if participant is not None else None
        ),
        received_via="participant_session" if participant is not None else "entry_receipt",
        import_format="native",
    )
    # Rewrite the normalized snapshot for a contact edit; historical revision rows remain immutable.
    station = session.scalar(select(Station).where(Station.entry_revision_id == revision.id))
    for line_number, item in enumerate(contacts, 1):
        timestamp = datetime.fromisoformat(str(item["occurred_at"]))
        sent = item.get("exchange_sent", {})
        received = item.get("exchange_received", {})
        session.add(
            Qso(
                entry_revision_id=revision.id,
                station_id=station.id if station else None,
                source_line_number=line_number,
                occurred_at=timestamp.astimezone(UTC),
                callsign_submitted=str(item["callsign"]),
                callsign_normalized="".join(str(item["callsign"]).upper().split()),
                band=str(item["frequency"]),
                mode=str(item["mode"]).upper(),
                exchange_sent_submitted=sent if isinstance(sent, dict) else {"raw": sent},
                exchange_received_submitted=received
                if isinstance(received, dict)
                else {"raw": received},
                source_fields=item.get("source_fields", {"edited": True}),
            )
        )


@router.post("/entries/{entry_id}/contacts", status_code=201)
def add_contact(
    entry_id: int,
    payload: ContactInput,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    receipt: Annotated[str | None, Header(alias="X-Entry-Receipt")] = None,
    participant: Annotated[ParticipantPrincipal | None, Depends(_optional_participant)] = None,
) -> dict[str, object]:
    entry = _entry_and_authorize(entry_id, request, session, receipt, participant)
    revision = _latest_revision(session, entry.id)
    if revision is None:
        raise HTTPException(status_code=409, detail="Entry has no submitted revision.")
    contacts = _contacts_for_revision(session, revision.id)
    contacts.append(payload.model_dump(mode="json"))
    _append_native_revision(session, entry, contacts, participant)
    session.commit()
    return _entry_output(session, entry)


@router.put("/entries/{entry_id}/contacts/{contact_id}")
def edit_contact(
    entry_id: int,
    contact_id: int,
    payload: ContactInput,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    receipt: Annotated[str | None, Header(alias="X-Entry-Receipt")] = None,
    participant: Annotated[ParticipantPrincipal | None, Depends(_optional_participant)] = None,
) -> dict[str, object]:
    entry = _entry_and_authorize(entry_id, request, session, receipt, participant)
    revision = _latest_revision(session, entry.id)
    contacts = _contacts_for_revision(session, revision.id) if revision else []
    # IDs are scoped to the latest revision; clients cannot edit a superseded QSO.
    current = (
        list(
            session.scalars(
                select(Qso)
                .where(Qso.entry_revision_id == revision.id)
                .order_by(Qso.source_line_number, Qso.id)
            )
        )
        if revision
        else []
    )
    current_index = next((index for index, qso in enumerate(current) if qso.id == contact_id), None)
    if current_index is None:
        raise HTTPException(status_code=404, detail="Contact not found in the current revision.")
    contacts[current_index] = payload.model_dump(mode="json")
    _append_native_revision(session, entry, contacts, participant)
    session.commit()
    return _entry_output(session, entry)


@router.delete("/entries/{entry_id}/contacts/{contact_id}")
def remove_contact(
    entry_id: int,
    contact_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    receipt: Annotated[str | None, Header(alias="X-Entry-Receipt")] = None,
    participant: Annotated[ParticipantPrincipal | None, Depends(_optional_participant)] = None,
) -> dict[str, object]:
    entry = _entry_and_authorize(entry_id, request, session, receipt, participant)
    revision = _latest_revision(session, entry.id)
    current = (
        list(
            session.scalars(
                select(Qso)
                .where(Qso.entry_revision_id == revision.id)
                .order_by(Qso.source_line_number, Qso.id)
            )
        )
        if revision
        else []
    )
    contacts = _contacts_for_revision(session, revision.id) if revision else []
    current_index = next((index for index, qso in enumerate(current) if qso.id == contact_id), None)
    if current_index is None:
        raise HTTPException(status_code=404, detail="Contact not found in the current revision.")
    contacts.pop(current_index)
    _append_native_revision(session, entry, contacts, participant)
    session.commit()
    return _entry_output(session, entry)
