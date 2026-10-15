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
        [{"external_value": "low", "category_values": {"power": "low-power"}}],
    )

    assert mapped == {"power": "low-power"}
    assert warnings == []


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
