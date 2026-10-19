from backend.app.adjudication.scoring import _exchange_values
from backend.app.logs.adif import parse_adif
from backend.app.rulesets.schema import ExchangeRule

LOG = """<ADIF_VER:5>3.1.8<PROGRAMID:6>WSJT-X<STATION_CALLSIGN:6>EA7KLK<EOH>
<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:2>2m<FREQ:7>144.174<MODE:4>MFSK<SUBMODE:3>FT8<CALL:5>F4ABC<GRIDSQUARE:4>JN18<MY_GRIDSQUARE:4>IM87<RST_SENT:3>-10<RST_RCVD:3>-12<APP_TEST:6>kept!!<EOR>
"""


def test_adif_reads_length_delimited_ft8_qso_and_normalizes_exchange_fields():
    parsed = parse_adif(LOG)

    assert parsed.errors == []
    assert parsed.headers["GRID-LOCATOR"] == ["IM87"]
    assert len(parsed.qsos) == 1
    qso = parsed.qsos[0]
    assert qso.occurred_at.isoformat() == "2026-10-15T12:34:00+00:00"
    assert qso.frequency == "2m"
    assert qso.mode == "FT8"
    assert qso.callsign_sent == "EA7KLK"
    assert qso.callsign_received == "F4ABC"
    assert qso.fields["app_test"] == "kept!!"
    assert qso.fields["_exchange_sent_values"] == {"grid": "IM87", "report": "-10"}
    assert qso.fields["_exchange_received_values"] == {"grid": "JN18", "report": "-12"}


def test_adif_without_optional_header_uses_first_record_and_submode_ft4():
    parsed = parse_adif(
        "<QSO_DATE:8>20261015<TIME_ON:6>123456<BAND:3>20m<MODE:4>MFSK"
        "<SUBMODE:3>FT4<CALL:5>F4ABC<STATION_CALLSIGN:6>EA7KLK"
        "<RST_SENT:3>-08<RST_RCVD:3>-11<EOR>"
    )

    assert parsed.errors == []
    assert parsed.headers["CALLSIGN"] == ["EA7KLK"]
    assert parsed.qsos[0].mode == "FT4"
    assert parsed.qsos[0].frequency == "20m"


def test_adif_moving_station_keeps_per_qso_grids_without_inventing_one_station_grid():
    parsed = parse_adif(
        "<ADIF_VER:5>3.1.8<EOH>"
        "<QSO_DATE:8>20261015<TIME_ON:4>1200<BAND:3>20m<MODE:2>CW"
        "<STATION_CALLSIGN:6>EA7KLK<CALL:5>F4ABC"
        "<MY_GRIDSQUARE:6>IO91AA<GRIDSQUARE:6>JN18AA<RST_SENT:3>599<RST_RCVD:3>599<EOR>"
        "<QSO_DATE:8>20261015<TIME_ON:4>1201<BAND:3>20m<MODE:2>CW"
        "<STATION_CALLSIGN:6>EA7KLK<CALL:5>F4ABC"
        "<MY_GRIDSQUARE:6>IO91AB<GRIDSQUARE:6>JN18AB<RST_SENT:3>599<RST_RCVD:3>599<EOR>"
    )

    assert parsed.errors == []
    assert "GRID-LOCATOR" not in parsed.headers
    assert parsed.qsos[0].fields["_exchange_sent_values"]["grid"] == "IO91AA"
    assert parsed.qsos[1].fields["_exchange_sent_values"]["grid"] == "IO91AB"


def test_adif_derives_band_from_frequency_and_reports_invalid_records():
    valid = parse_adif(
        "<QSO_DATE:8>20261015<TIME_ON:4>1234<FREQ:7>144.174<MODE:3>FT8"
        "<STATION_CALLSIGN:6>EA7KLK"
        "<CALL:5>F4ABC<RST_SENT:3>-10<RST_RCVD:3>-12<EOR>"
    )
    malformed = parse_adif(
        "<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:2>2m<MODE:3>FT8"
        "<CALL:5>F4ABC<RST_SENT:3>-10<RST_RCVD:3>-12"
    )

    assert valid.errors == []
    assert valid.qsos[0].frequency == "2m"
    assert malformed.qsos == []
    assert malformed.errors[0].code == "missing_adif_eor"


def test_adif_rejects_truncated_length_and_missing_required_values():
    truncated = parse_adif("<CALL:12>F4ABC<EOR>")
    incomplete = parse_adif("<CALL:5>F4ABC<EOR>")
    missing_station = parse_adif(
        "<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:2>2m<MODE:3>FT8"
        "<CALL:5>F4ABC<RST_SENT:3>-10<RST_RCVD:3>-12<EOR>"
    )

    assert truncated.errors[0].code == "short_adif_field"
    assert incomplete.errors[0].code == "invalid_qso_time"
    assert missing_station.errors[0].code == "missing_station_callsign"


def test_adif_exchange_values_feed_configured_scoring_fields():
    exchange = ExchangeRule.model_validate(
        {
            "kind": "exchange",
            "fields": [{"key": "grid", "label": "Grid", "value_type": "grid", "direction": "both"}],
        }
    )

    assert _exchange_values(
        {"raw": "JN18", "values": {"grid": "JN18"}}, exchange, direction="received"
    ) == {"grid": "JN18"}
