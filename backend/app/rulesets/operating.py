"""Contact-derived checks for configured operating and station constraints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from backend.app.rulesets.schema import OperatingConstraintRule

if TYPE_CHECKING:
    from backend.app.rulesets.engine import ScoringEntry


@dataclass(frozen=True)
class ConstraintFinding:
    code: str
    message: str
    needs_review: bool = True


def _minutes_between(earlier: datetime, later: datetime) -> int:
    elapsed = later - earlier
    return elapsed.days * 1440 + elapsed.seconds // 60


def evaluate_operating_constraints(
    rule: OperatingConstraintRule,
    entry: ScoringEntry,
    *,
    contest_starts_at: datetime,
    contest_ends_at: datetime,
) -> list[ConstraintFinding]:
    """Evaluate only facts that a submitted contact log can support.

    Contact-derived elapsed operating time and off-time are estimates because a log
    does not encode transmit duration. Findings remain reviewable rather than making
    a universal disqualification decision.
    """
    start = contest_starts_at.astimezone(UTC)
    end = contest_ends_at.astimezone(UTC)
    qsos = sorted(
        (qso for qso in entry.qsos if start <= qso.occurred_at.astimezone(UTC) < end),
        key=lambda qso: (qso.occurred_at.astimezone(UTC), qso.qso_id),
    )
    findings: list[ConstraintFinding] = []
    gaps = [
        _minutes_between(left.occurred_at.astimezone(UTC), right.occurred_at.astimezone(UTC))
        for left, right in zip(qsos, qsos[1:], strict=False)
    ]

    if rule.max_operating_minutes is not None:
        session_gap = rule.operating_session_gap_minutes
        if not qsos or session_gap is None:
            findings.append(
                ConstraintFinding(
                    "operating_time_unverifiable",
                    "Contact log lacks enough data to estimate operating time.",
                )
            )
        else:
            estimated_minutes = sum(gap for gap in gaps if gap <= session_gap)
            if estimated_minutes > rule.max_operating_minutes:
                findings.append(
                    ConstraintFinding(
                        "maximum_operating_time_exceeded",
                        f"Contact-derived active intervals total {estimated_minutes} minutes; "
                        f"the configured maximum is {rule.max_operating_minutes}.",
                    )
                )

    if rule.off_period_gap_minutes is not None:
        off_periods = [gap for gap in gaps if gap >= rule.off_period_gap_minutes]
        off_minutes = sum(off_periods)
        if len(off_periods) < rule.required_off_periods:
            findings.append(
                ConstraintFinding(
                    "required_off_periods_missing",
                    f"Found {len(off_periods)} contact gaps meeting the off-time threshold; "
                    f"{rule.required_off_periods} are required.",
                )
            )
        if off_minutes < rule.minimum_off_time_minutes:
            findings.append(
                ConstraintFinding(
                    "minimum_off_time_not_met",
                    f"Found {off_minutes} contact-gap minutes of off-time; "
                    f"{rule.minimum_off_time_minutes} are required.",
                )
            )

    changes: list[datetime] = []
    for previous, current in zip(qsos, qsos[1:], strict=False):
        if previous.band and current.band and previous.band.upper() != current.band.upper():
            change_at = current.occurred_at.astimezone(UTC)
            changes.append(change_at)
            dwell = _minutes_between(previous.occurred_at.astimezone(UTC), change_at)
            if (
                rule.minimum_band_dwell_minutes is not None
                and dwell < rule.minimum_band_dwell_minutes
            ):
                findings.append(
                    ConstraintFinding(
                        "minimum_band_dwell_not_met",
                        f"Band changed after {dwell} minutes; "
                        f"{rule.minimum_band_dwell_minutes} minutes are required.",
                    )
                )
    if rule.maximum_band_changes is not None:
        window = timedelta(minutes=rule.band_change_window_minutes)
        for index, instant in enumerate(changes):
            count = sum(
                instant <= candidate < instant + window for candidate in changes[index:]
            )
            if count > rule.maximum_band_changes:
                findings.append(
                    ConstraintFinding(
                        "band_change_limit_exceeded",
                        f"More than {rule.maximum_band_changes} band changes occurred "
                        f"within a rolling {rule.band_change_window_minutes}-minute window.",
                    )
                )
                break

    if rule.maximum_transmitters is not None:
        transmitters = {qso.transmitter for qso in qsos if qso.transmitter}
        missing_transmitter = any(not qso.transmitter for qso in qsos)
        if missing_transmitter:
            findings.append(
                ConstraintFinding(
                    "transmitter_count_unverifiable",
                    "Some contacts do not identify a transmitter; verify the configured "
                    "transmitter limit.",
                )
            )
        elif len(transmitters) > rule.maximum_transmitters:
            findings.append(
                ConstraintFinding(
                    "maximum_transmitters_exceeded",
                    f"Log identifies {len(transmitters)} transmitters; "
                    f"the configured maximum is {rule.maximum_transmitters}.",
                )
            )

    if rule.one_transmitted_signal_per_band:
        findings.append(
            ConstraintFinding(
                "one_signal_per_band_needs_review",
                "The contact log does not establish whether simultaneous transmissions "
                "complied with the one-signal-per-band rule.",
            )
        )

    for field in rule.declaration_fields:
        if field not in entry.declarations:
            findings.append(
                ConstraintFinding(
                    f"missing_declaration:{field}",
                    f"Entrant declaration {field} is required for human review.",
                )
            )
        else:
            findings.append(
                ConstraintFinding(
                    f"declaration_review:{field}",
                    f"Entrant declaration {field} requires human verification.",
                )
            )

    return findings
