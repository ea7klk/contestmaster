import pytest

from backend.app.logs.cabrillo import map_categories, parse_cabrillo

VALID = """START-OF-LOG
CONTEST: test-contest
CALLSIGN: EA7KLK
NAME: Operator
CATEGORY-POWER: LOW
X-LOCAL-HEADER: preserved
QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001 F4ABC 599 002 extra
END-OF-LOG
"""


def test_cabrillo_parse_preserves_unknowns_and_reports_extra_qso_fields():
    parsed = parse_cabrillo(VALID)

    assert not parsed.errors
    assert parsed.headers["CALLSIGN"] == ["EA7KLK"]
    assert parsed.qsos[0].callsign_received == "F4ABC"
    assert parsed.qsos[0].occurred_at.isoformat() == "2026-10-15T12:34:00+00:00"
    assert parsed.qsos[0].extra_fields == ["extra"]
    assert parsed.unknown_headers[0]["raw"] == "X-LOCAL-HEADER: preserved"
    assert {warning.code for warning in parsed.warnings} == {"unknown_header", "extra_qso_fields"}


@pytest.mark.parametrize(
    ("version", "category_header"),
    [
        ("2.0", "CATEGORY: SINGLE-OP ALL LOW"),
        ("3.0", "CATEGORY-OPERATOR: SINGLE-OP"),
    ],
)
def test_cabrillo_v2_and_v3_versioned_markers_parse_common_qsos(version, category_header):
    parsed = parse_cabrillo(
        f"START-OF-LOG: {version}\n"
        "CONTEST: test-contest\n"
        "CALLSIGN: EA7KLK\n"
        f"{category_header}\n"
        "QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001 F4ABC 599 002 0\n"
        "END-OF-LOG:\n"
    )

    assert parsed.errors == []
    assert parsed.headers["CALLSIGN"] == ["EA7KLK"]
    assert len(parsed.qsos) == 1
    assert parsed.qsos[0].callsign_received == "F4ABC"
    assert parsed.qsos[0].extra_fields == ["0"]
    assert parsed.qsos[0].occurred_at.isoformat() == "2026-10-15T12:34:00+00:00"


@pytest.mark.parametrize(
    ("start_record", "expected_error"),
    [
        ("START-OF-LOG:", "missing_cabrillo_version"),
        ("START-OF-LOG: 1.0", "unsupported_cabrillo_version"),
        ("START-OF-LOG: 3.1", "unsupported_cabrillo_version"),
    ],
)
def test_cabrillo_rejects_missing_or_unsupported_declared_versions(start_record, expected_error):
    parsed = parse_cabrillo(
        f"{start_record}\nCONTEST: test-contest\nCALLSIGN: EA7KLK\n"
        "QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001 F4ABC 599 002\nEND-OF-LOG:\n"
    )

    error = next(error for error in parsed.errors if error.code == expected_error)
    assert error.line == 1


def test_versioned_cabrillo_requires_colon_terminated_end_marker():
    parsed = parse_cabrillo(
        "START-OF-LOG: 3.0\nCONTEST: test-contest\nCALLSIGN: EA7KLK\n"
        "QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001 F4ABC 599 002\nEND-OF-LOG\n"
    )

    assert [(error.line, error.code) for error in parsed.errors] == [(5, "invalid_end_record")]


def test_cabrillo_errors_are_line_scoped_and_do_not_accept_partial_qsos():
    parsed = parse_cabrillo(
        "START-OF-LOG\nCONTEST: test-contest\nCALLSIGN: EA7KLK\n"
        "QSO: 14025 CW 2026-99-15 1260 EA7KLK 599 001 F4ABC 599 002\n"
        "QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001\nEND-OF-LOG\n"
    )

    assert parsed.qsos == []
    assert {error.code for error in parsed.errors} >= {"invalid_qso_time", "incomplete_qso"}
    assert all(
        error.line > 0
        for error in parsed.errors
        if error.code in {"invalid_qso_time", "incomplete_qso"}
    )


def test_category_mapping_is_case_insensitive_and_leaves_unknown_values_for_review():
    parsed = parse_cabrillo(VALID)
    mapped, warnings = map_categories(
        parsed,
        [
            {
                "external_field": "CATEGORY-POWER",
                "external_value": "LOW",
                "category_values": {"power": "low-power"},
            }
        ],
    )

    assert mapped == {"power": "low-power"}
    assert warnings == []


def test_category_mapping_does_not_match_same_token_under_a_different_header():
    parsed = parse_cabrillo(VALID)
    mapped, warnings = map_categories(
        parsed,
        [
            {
                "external_field": "CATEGORY-MODE",
                "external_value": "LOW",
                "category_values": {"power": "low-power"},
            }
        ],
    )

    assert mapped == {}
    assert warnings[0].code == "unmapped_category"


def test_contest_specific_header_template_maps_required_fields_without_losing_originals():
    parsed = parse_cabrillo(
        "START-OF-LOG\nEVENT: test-contest\nOPERATOR-CALL: EA7KLK\n"
        "QSO: 14025 CW 2026-10-15 1234 EA7KLK 599 001 F4ABC 599 002\nEND-OF-LOG\n",
        header_fields={"contest": "EVENT", "callsign": "OPERATOR-CALL"},
    )

    assert parsed.errors == []
    assert parsed.headers["EVENT"] == ["test-contest"]
    assert parsed.header_aliases["callsign"] == "OPERATOR-CALL"
    assert parsed.warnings == []


def test_cabrillo_parser_bounds_line_count_and_line_length():
    from backend.app.logs.cabrillo import (
        MAX_CABRILLO_LINE_LENGTH,
        MAX_LOG_LINES,
    )

    too_many = parse_cabrillo("\n".join("x" for _ in range(MAX_LOG_LINES + 1)))
    assert too_many.errors[0].code == "too_many_lines"
    long_line = parse_cabrillo("START-OF-LOG\n" + ("x" * (MAX_CABRILLO_LINE_LENGTH + 1)))
    assert any(error.code == "line_too_long" for error in long_line.errors)
