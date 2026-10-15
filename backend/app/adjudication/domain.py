"""Pure, storage- and HTTP-independent amateur-radio adjudication helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

_CALLSIGN = re.compile(r"^[A-Z0-9]+(?:/[A-Z0-9]+)*$")


class AdjudicationInputError(ValueError):
    """An adjudication input or tolerance configuration is invalid."""


def normalize_callsign(value: str) -> str:
    """Normalize spacing/case without removing portable or compound-call separators."""
    normalized = "".join(value.split()).upper()
    if not normalized or len(normalized) > 32 or not _CALLSIGN.fullmatch(normalized):
        raise AdjudicationInputError("Callsign must contain letters/digits and optional slashes.")
    return normalized


def normalize_exchange(exchange: dict[str, Any]) -> dict[str, Any]:
    """Return a stable exchange view; raw submitted mappings remain untouched in persistence."""
    normalized: dict[str, Any] = {}
    for key, value in exchange.items():
        name = str(key).strip().casefold()
        if not name:
            continue
        if isinstance(value, str):
            normalized[name] = " ".join(value.split()).upper()
        else:
            normalized[name] = value
    return normalized


@dataclass(frozen=True, slots=True)
class ExchangeComparison:
    matches: bool
    mismatched_fields: tuple[str, ...]


def compare_exchange(
    expected: dict[str, Any],
    observed: dict[str, Any],
    *,
    numeric_tolerances: dict[str, int] | None = None,
) -> ExchangeComparison:
    """Compare normalized exchange fields with optional per-field integer tolerances."""
    tolerances = numeric_tolerances or {}
    if any(type(value) is not int or value < 0 for value in tolerances.values()):
        raise AdjudicationInputError("Exchange tolerances must be nonnegative integers.")
    left = normalize_exchange(expected)
    right = normalize_exchange(observed)
    mismatches: list[str] = []
    for field in sorted(set(left) | set(right)):
        first, second = left.get(field), right.get(field)
        if type(first) is int and type(second) is int and field in tolerances:
            equal = abs(first - second) <= tolerances[field]
        else:
            equal = type(first) is type(second) and first == second
        if not equal:
            mismatches.append(field)
    return ExchangeComparison(not mismatches, tuple(mismatches))


@dataclass(frozen=True, slots=True)
class QsoFacts:
    qso_id: int
    occurred_at: datetime
    station_callsign: str
    worked_callsign: str
    band: str | None
    mode: str | None
    sent_exchange: dict[str, Any]
    received_exchange: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CtyCallsignMatch:
    prefix_pattern: str
    entity: str | None
    cq_zone: str | None
    itu_zone: str | None
    continent: str | None


def resolve_cty_callsign(
    callsign: str, mappings: list[CtyCallsignMatch]
) -> CtyCallsignMatch | None:
    """Resolve a call from one already-selected CTY snapshot, preferring exact/longest match."""
    normalized = normalize_callsign(callsign)
    parts = [normalized, *normalized.split("/")]
    exact = [
        mapping
        for mapping in mappings
        if mapping.prefix_pattern.startswith("=") and mapping.prefix_pattern[1:] in parts
    ]
    if exact:
        return min(exact, key=lambda item: (len(item.prefix_pattern), item.prefix_pattern))
    candidates = []
    for mapping in mappings:
        pattern = mapping.prefix_pattern
        if pattern.startswith("=") or any(char in pattern for char in "*?"):
            continue
        if any(part.startswith(pattern) for part in parts):
            candidates.append(mapping)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (len(item.prefix_pattern), item.prefix_pattern))


@dataclass(frozen=True, slots=True)
class Finding:
    status: Literal["credited", "not_credited", "needs_review"]
    reason_code: str
    reason: str
    evidence: dict[str, Any]


def validate_qso(
    qso: QsoFacts,
    *,
    starts_at: datetime,
    ends_at: datetime,
    allowed_bands: set[str] | None = None,
    allowed_modes: set[str] | None = None,
) -> list[Finding]:
    """Check generic contest boundaries and configured band/mode allowlists."""
    for value in (qso.occurred_at, starts_at, ends_at):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AdjudicationInputError("Contest and QSO timestamps must be timezone-aware.")
    start, end = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
    instant = qso.occurred_at.astimezone(UTC)
    findings: list[Finding] = []
    if not start < end:
        raise AdjudicationInputError("Contest start must precede contest end.")
    if instant < start or instant >= end:
        findings.append(
            Finding(
                "not_credited",
                "out_of_period",
                "QSO is outside the contest period.",
                {"starts_at": start.isoformat(), "ends_at_exclusive": end.isoformat()},
            )
        )
    if normalize_callsign(qso.station_callsign) == normalize_callsign(qso.worked_callsign):
        findings.append(
            Finding(
                "not_credited", "self_contact", "A station cannot claim a contact with itself.", {}
            )
        )
    if allowed_bands is not None and (qso.band or "").upper() not in {
        v.upper() for v in allowed_bands
    }:
        findings.append(
            Finding(
                "not_credited",
                "band_not_allowed",
                "QSO band is not enabled by this contest.",
                {"band": qso.band},
            )
        )
    if allowed_modes is not None and (qso.mode or "").upper() not in {
        v.upper() for v in allowed_modes
    }:
        findings.append(
            Finding(
                "not_credited",
                "mode_not_allowed",
                "QSO mode is not enabled by this contest.",
                {"mode": qso.mode},
            )
        )
    return findings


def select_duplicate_qsos(
    qsos: list[QsoFacts], *, scope: tuple[str, ...] = ("worked_callsign", "band", "mode")
) -> dict[int, Finding]:
    """Select earliest QSO deterministically for a duplicate scope; ties use QSO id."""
    allowed = {"worked_callsign", "band", "mode"}
    if not scope or set(scope) - allowed:
        raise AdjudicationInputError("Duplicate scope supports callsign, band, and mode.")
    ordered = sorted(qsos, key=lambda item: (item.occurred_at.astimezone(UTC), item.qso_id))
    winners: dict[tuple[str, ...], int] = {}
    duplicate_findings: dict[int, Finding] = {}
    for qso in ordered:
        values = {
            "worked_callsign": normalize_callsign(qso.worked_callsign),
            "band": (qso.band or "").strip().upper(),
            "mode": (qso.mode or "").strip().upper(),
        }
        key = tuple(values[item] for item in scope)
        if key in winners:
            duplicate_findings[qso.qso_id] = Finding(
                "not_credited",
                "duplicate",
                "A prior QSO has the same configured duplicate key.",
                {"winner_qso_id": winners[key], "scope": list(scope), "key": list(key)},
            )
        else:
            winners[key] = qso.qso_id
    return duplicate_findings


def match_counterpart(
    qso: QsoFacts,
    candidates: list[QsoFacts],
    *,
    timestamp_tolerance_seconds: int = 300,
    numeric_exchange_tolerances: dict[str, int] | None = None,
) -> Finding:
    """Match the reciprocal log QSO with configurable timestamp/exchange tolerances."""
    if type(timestamp_tolerance_seconds) is not int or timestamp_tolerance_seconds < 0:
        raise AdjudicationInputError("Timestamp tolerance must be a nonnegative integer.")
    if qso.occurred_at.tzinfo is None:
        raise AdjudicationInputError("QSO timestamps must be timezone-aware.")
    station = normalize_callsign(qso.station_callsign)
    worked = normalize_callsign(qso.worked_callsign)
    reciprocal = [
        candidate
        for candidate in candidates
        if candidate.qso_id != qso.qso_id
        and normalize_callsign(candidate.station_callsign) == worked
        and normalize_callsign(candidate.worked_callsign) == station
    ]
    within = [
        candidate
        for candidate in reciprocal
        if candidate.occurred_at.tzinfo is not None
        and abs(
            (
                candidate.occurred_at.astimezone(UTC) - qso.occurred_at.astimezone(UTC)
            ).total_seconds()
        )
        <= timestamp_tolerance_seconds
        and (not qso.band or not candidate.band or qso.band.casefold() == candidate.band.casefold())
        and (not qso.mode or not candidate.mode or qso.mode.casefold() == candidate.mode.casefold())
    ]
    scored = []
    for candidate in within:
        sent = compare_exchange(
            qso.sent_exchange,
            candidate.received_exchange,
            numeric_tolerances=numeric_exchange_tolerances,
        )
        received = compare_exchange(
            qso.received_exchange,
            candidate.sent_exchange,
            numeric_tolerances=numeric_exchange_tolerances,
        )
        scored.append(
            (
                len(sent.mismatched_fields) + len(received.mismatched_fields),
                abs(
                    (
                        candidate.occurred_at.astimezone(UTC) - qso.occurred_at.astimezone(UTC)
                    ).total_seconds()
                ),
                candidate.qso_id,
                candidate,
                sent,
                received,
            )
        )
    if scored:
        _, seconds, _, candidate, sent, received = min(scored, key=lambda row: row[:3])
        status = "credited" if sent.matches and received.matches else "needs_review"
        return Finding(
            status,
            "counterpart_match"
            if sent.matches and received.matches
            else "counterpart_exchange_mismatch",
            "Reciprocal log contact matched."
            if sent.matches and received.matches
            else "Reciprocal contact has exchange differences requiring review.",
            {
                "counterpart_qso_id": candidate.qso_id,
                "timestamp_difference_seconds": int(seconds),
                "sent_exchange_mismatches": list(sent.mismatched_fields),
                "received_exchange_mismatches": list(received.mismatched_fields),
            },
        )
    code = "counterpart_not_found" if not reciprocal else "counterpart_outside_tolerance"
    return Finding(
        "needs_review",
        code,
        "No reciprocal log contact matched the configured tolerance.",
        {
            "reciprocal_candidates": len(reciprocal),
            "timestamp_tolerance_seconds": timestamp_tolerance_seconds,
        },
    )
