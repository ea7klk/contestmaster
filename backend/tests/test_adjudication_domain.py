from datetime import UTC, datetime, timedelta

import pytest

from backend.app.adjudication.domain import (
    AdjudicationInputError,
    CtyCallsignMatch,
    QsoFacts,
    compare_exchange,
    match_counterpart,
    normalize_callsign,
    resolve_cty_callsign,
    select_duplicate_qsos,
    validate_qso,
)


def qso(
    qso_id: int,
    *,
    at: datetime,
    station: str = "EA7KLK",
    worked: str = "F4ABC",
    sent=None,
    received=None,
):
    return QsoFacts(
        qso_id, at, station, worked, "20M", "CW", sent or {"serial": 10}, received or {"serial": 20}
    )


def test_callsign_normalization_keeps_compound_call_parts_and_rejects_invalid_values():
    assert normalize_callsign(" ea7klk / p ") == "EA7KLK/P"
    with pytest.raises(AdjudicationInputError):
        normalize_callsign("EA7 KLK!")


def test_cty_resolution_prefers_exact_exception_then_longest_plain_prefix():
    match = resolve_cty_callsign(
        "EA7KLK/P",
        [
            CtyCallsignMatch("EA", "EA", "14", "37", "EU"),
            CtyCallsignMatch("EA7", "EA7", "14", "37", "EU"),
            CtyCallsignMatch("=EA7KLK", "EA7KLK", "14", "37", "EU"),
        ],
    )
    wildcard_only = resolve_cty_callsign("F4ABC", [CtyCallsignMatch("F*", "F", "14", "27", "EU")])
    assert match is not None and match.entity == "EA7KLK"
    assert wildcard_only is None


def test_exchange_comparison_uses_per_field_integer_tolerance_and_exact_types():
    exact = compare_exchange(
        {"serial": 10, "rst": "599"}, {"serial": 12, "rst": "599"}, numeric_tolerances={"serial": 2}
    )
    too_far = compare_exchange({"serial": 10}, {"serial": 13}, numeric_tolerances={"serial": 2})
    bool_is_not_integer = compare_exchange(
        {"serial": 1}, {"serial": True}, numeric_tolerances={"serial": 1}
    )
    assert exact.matches
    assert too_far.mismatched_fields == ("serial",)
    assert bool_is_not_integer.mismatched_fields == ("serial",)
    with pytest.raises(AdjudicationInputError):
        compare_exchange({}, {}, numeric_tolerances={"serial": -1})


def test_qso_contest_period_is_start_inclusive_end_exclusive_and_constraints_are_explicit():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    assert validate_qso(qso(1, at=start), starts_at=start, ends_at=end) == []
    assert (
        validate_qso(qso(2, at=end), starts_at=start, ends_at=end)[0].reason_code == "out_of_period"
    )
    invalid = qso(
        3,
        at=start,
        worked="EA7KLK",
    )
    findings = validate_qso(invalid, starts_at=start, ends_at=end, allowed_modes={"SSB"})
    assert {item.reason_code for item in findings} == {"self_contact", "mode_not_allowed"}


def test_duplicate_selection_is_deterministic_even_when_input_order_changes():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    later, earlier = qso(2, at=now + timedelta(seconds=1)), qso(1, at=now)
    first = select_duplicate_qsos([later, earlier])
    second = select_duplicate_qsos([earlier, later])
    assert first == second
    assert first[2].evidence["winner_qso_id"] == 1


def test_counterpart_match_checks_reciprocal_callsign_time_and_swapped_exchanges():
    at = datetime(2026, 1, 1, tzinfo=UTC)
    own = qso(1, at=at)
    reciprocal = qso(
        2,
        at=at + timedelta(seconds=120),
        station="F4ABC",
        worked="EA7KLK",
        sent={"serial": 20},
        received={"serial": 10},
    )
    match = match_counterpart(own, [reciprocal], timestamp_tolerance_seconds=120)
    outside = match_counterpart(own, [reciprocal], timestamp_tolerance_seconds=119)
    mismatch = qso(
        3, at=at, station="F4ABC", worked="EA7KLK", sent={"serial": 99}, received={"serial": 10}
    )
    exchange = match_counterpart(own, [mismatch])
    assert match.status == "credited" and match.reason_code == "counterpart_match"
    assert outside.reason_code == "counterpart_outside_tolerance"
    assert exchange.reason_code == "counterpart_exchange_mismatch"
