"""Bounded ADI/ADIF text importer for standard QSO records."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from backend.app.logs.cabrillo import (
    MAX_LOG_LINES,
    MAX_LOG_QSOS,
    ImportMessage,
    ParsedLog,
    ParsedQso,
)

FIELD_TAG = re.compile(r"^([^:<>]+):(\d+)(?::([^<>]*))?$")
MAX_ADIF_LINE_LENGTH = 8192
_BAND_KEYS = {
    "160M": "160m",
    "80M": "80m",
    "60M": "60m",
    "40M": "40m",
    "30M": "30m",
    "20M": "20m",
    "17M": "17m",
    "15M": "15m",
    "12M": "12m",
    "10M": "10m",
    "6M": "6m",
    "4M": "4m",
    "2M": "2m",
    "1.25M": "1.25m",
    "70CM": "70cm",
    "33CM": "33cm",
    "23CM": "23cm",
    "13CM": "13cm",
    "9CM": "9cm",
    "6CM": "6cm",
    "3CM": "3cm",
    "1.25CM": "1.25cm",
    "6MM": "6mm",
    "4MM": "4mm",
    "2.5MM": "2.5mm",
    "2MM": "2mm",
    "1MM": "1mm",
    "SUBMM": "submm",
}


def _line_at(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def band_from_frequency_mhz(value: str) -> str | None:
    try:
        mhz = float(value)
    except ValueError:
        return None
    ranges = (
        (1.8, 2.0, "160m"),
        (3.5, 4.0, "80m"),
        (5.0, 5.5, "60m"),
        (7.0, 7.3, "40m"),
        (10.1, 10.15, "30m"),
        (14.0, 14.35, "20m"),
        (18.068, 18.168, "17m"),
        (21.0, 21.45, "15m"),
        (24.89, 24.99, "12m"),
        (28.0, 29.7, "10m"),
        (50.0, 54.0, "6m"),
        (70.0, 71.0, "4m"),
        (144.0, 148.0, "2m"),
        (219.0, 225.0, "1.25m"),
        (420.0, 450.0, "70cm"),
        (902.0, 928.0, "33cm"),
        (1240.0, 1300.0, "23cm"),
        (2300.0, 2450.0, "13cm"),
        (3300.0, 3500.0, "9cm"),
        (5650.0, 5925.0, "6cm"),
        (10000.0, 10500.0, "3cm"),
        (24000.0, 24250.0, "1.25cm"),
        (47000.0, 47200.0, "6mm"),
        (75500.0, 81000.0, "4mm"),
        (119980.0, 120020.0, "2.5mm"),
        (142000.0, 149000.0, "2mm"),
    )
    return next((band for lower, upper, band in ranges if lower <= mhz <= upper), None)


def _first(fields: dict[str, list[str]], *names: str) -> str:
    for name in names:
        values = fields.get(name)
        if values and values[0].strip():
            return values[0].strip()
    return ""


def _qso(fields: dict[str, list[str]], line: int) -> tuple[ParsedQso | None, ImportMessage | None]:
    date_value = _first(fields, "QSO_DATE")
    time_value = _first(fields, "TIME_ON")
    if not re.fullmatch(r"\d{8}", date_value) or not re.fullmatch(r"\d{4}(?:\d{2})?", time_value):
        return None, ImportMessage(
            line,
            "invalid_qso_time",
            "QSO_DATE must be YYYYMMDD and TIME_ON must be HHMM or HHMMSS in UTC.",
        )
    try:
        time_format = "%H%M%S" if len(time_value) == 6 else "%H%M"
        occurred = datetime.strptime(f"{date_value} {time_value}", f"%Y%m%d {time_format}").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None, ImportMessage(
            line, "invalid_qso_time", "QSO_DATE or TIME_ON is not a valid UTC date/time."
        )

    call = _first(fields, "CALL")
    mode = _first(fields, "SUBMODE", "MODE").upper()
    band_value = _first(fields, "BAND").upper()
    frequency = _first(fields, "FREQ")
    band = (
        _BAND_KEYS.get(band_value, band_value.lower())
        if band_value
        else band_from_frequency_mhz(frequency)
    )
    required = [
        name
        for name, value in (("CALL", call), ("MODE", mode), ("BAND or FREQ", band or ""))
        if not value
    ]
    if required:
        return None, ImportMessage(
            line,
            "missing_qso_field",
            "Required ADIF QSO fields are missing: " + ", ".join(required) + ".",
        )

    sent_rst = _first(fields, "RST_SENT")
    received_rst = _first(fields, "RST_RCVD")
    sent = _first(fields, "STX_STRING", "STX", "MY_GRIDSQUARE")
    received = _first(fields, "SRX_STRING", "SRX", "GRIDSQUARE")
    if not sent:
        sent = " ".join(
            value[0].strip()
            for key, value in fields.items()
            if key in {"MY_STATE", "MY_CNTY", "MY_CQ_ZONE", "MY_ITU_ZONE", "MY_IOTA", "MY_SIG_INFO"}
            and value
        )
    if not received:
        received = " ".join(
            value[0].strip()
            for key, value in fields.items()
            if key in {"STATE", "CNTY", "CQZ", "ITUZ", "IOTA", "SIG_INFO"} and value
        )
    if not sent and sent_rst:
        sent = sent_rst
    if not received and received_rst:
        received = received_rst
    if not sent or not received:
        return None, ImportMessage(
            line,
            "missing_exchange",
            "The ADIF QSO needs sent and received exchange data (for example STX_STRING/SRX_STRING "
            "or MY_GRIDSQUARE/GRIDSQUARE).",
        )

    canonical_sent = {
        "grid": _first(fields, "MY_GRIDSQUARE"),
        "serial": _first(fields, "STX"),
        "report": sent_rst,
        "state": _first(fields, "MY_STATE"),
        "cq_zone": _first(fields, "MY_CQ_ZONE"),
        "itu_zone": _first(fields, "MY_ITU_ZONE"),
    }
    canonical_received = {
        "grid": _first(fields, "GRIDSQUARE"),
        "serial": _first(fields, "SRX"),
        "report": received_rst,
        "state": _first(fields, "STATE"),
        "cq_zone": _first(fields, "CQZ"),
        "itu_zone": _first(fields, "ITUZ"),
    }
    canonical_sent = {key: value for key, value in canonical_sent.items() if value}
    canonical_received = {key: value for key, value in canonical_received.items() if value}
    return ParsedQso(
        line=line,
        occurred_at=occurred,
        frequency=band,
        mode=mode,
        callsign_sent=_first(fields, "STATION_CALLSIGN", "OPERATOR"),
        rst_sent=sent_rst,
        exchange_sent=sent,
        callsign_received=call,
        rst_received=received_rst,
        exchange_received=received,
        fields={
            **{
                name.lower(): values[0] if len(values) == 1 else values
                for name, values in fields.items()
            },
            "_exchange_sent_values": canonical_sent,
            "_exchange_received_values": canonical_received,
            "_sent_rst": sent_rst,
            "_received_rst": received_rst,
        },
    ), None


def parse_adif(text: str) -> ParsedLog:
    """Parse ADI text (the standard ADIF interchange serialization)."""
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    if line_count > MAX_LOG_LINES:
        return ParsedLog(
            {},
            [],
            [],
            [
                ImportMessage(
                    0, "too_many_lines", f"A log may contain at most {MAX_LOG_LINES} lines."
                )
            ],
            [],
            [],
            {},
        )
    too_long = next(
        (
            index
            for index, line in enumerate(text.splitlines(), 1)
            if len(line) > MAX_ADIF_LINE_LENGTH
        ),
        None,
    )
    if too_long:
        return ParsedLog(
            {},
            [],
            [],
            [
                ImportMessage(
                    too_long,
                    "line_too_long",
                    f"An ADIF line may not exceed {MAX_ADIF_LINE_LENGTH} characters.",
                )
            ],
            [],
            text.splitlines(),
            {},
        )

    qsos: list[ParsedQso] = []
    errors: list[ImportMessage] = []
    unknown_headers: list[dict[str, Any]] = []
    headers: dict[str, list[str]] = {}
    cursor = 0
    record_start = 0
    header_fields: dict[str, list[str]] = {}
    record_fields: dict[str, list[str]] = {}
    explicit_header = False
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            break
        if text[cursor] != "<":
            errors.append(
                ImportMessage(
                    _line_at(text, cursor),
                    "invalid_adif_tag",
                    "Expected an ADIF field tag beginning with '<'.",
                )
            )
            break
        closing = text.find(">", cursor + 1)
        if closing < 0:
            errors.append(
                ImportMessage(
                    _line_at(text, cursor),
                    "invalid_adif_tag",
                    "An ADIF field tag is missing its closing '>'.",
                )
            )
            break
        tag = text[cursor + 1 : closing].strip()
        if tag.casefold() == "eoh":
            explicit_header = True
            headers.update(header_fields)
            header_fields = {}
            cursor = closing + 1
            record_start = cursor
            continue
        if tag.casefold() == "eof":
            cursor = closing + 1
            break
        if tag.casefold() == "eor":
            fields = record_fields if explicit_header else header_fields
            parsed, issue_message = _qso(fields, _line_at(text, record_start))
            if issue_message:
                errors.append(issue_message)
            elif parsed is not None:
                qsos.append(parsed)
                if len(qsos) > MAX_LOG_QSOS:
                    errors.append(
                        ImportMessage(
                            0,
                            "too_many_qsos",
                            f"A log may contain at most {MAX_LOG_QSOS} QSO records.",
                        )
                    )
                    break
            cursor = closing + 1
            record_start = cursor
            record_fields = {}
            header_fields = {}
            continue
        match = FIELD_TAG.fullmatch(tag)
        if not match:
            errors.append(
                ImportMessage(
                    _line_at(text, cursor),
                    "invalid_adif_tag",
                    "An ADIF field tag has an invalid name or length.",
                )
            )
            break
        name, raw_length, _field_type = match.groups()
        length = int(raw_length)
        value_start, value_end = closing + 1, closing + 1 + length
        if value_end > len(text):
            errors.append(
                ImportMessage(
                    _line_at(text, cursor),
                    "short_adif_field",
                    f"ADIF field {name.upper()} is shorter than its declared length.",
                )
            )
            break
        value = text[value_start:value_end]
        target = header_fields if (not explicit_header and not qsos) else record_fields
        target.setdefault(name.upper(), []).append(value)
        cursor = value_end
    if record_fields or (not explicit_header and header_fields):
        errors.append(
            ImportMessage(
                _line_at(text, len(text)),
                "missing_adif_eor",
                "The final ADIF QSO record is missing <EOR>.",
            )
        )
    if explicit_header:
        headers.update(header_fields)
    if not qsos and not errors:
        errors.append(
            ImportMessage(
                0,
                "no_qsos",
                "The ADIF file must contain at least one complete QSO record ending in <EOR>.",
            )
        )

    # ADIF header carries station identity; WSJT-X records commonly repeat it per QSO.
    if not headers.get("CALLSIGN"):
        station_calls = _first(headers, "STATION_CALLSIGN", "OPERATOR") or next(
            (qso.callsign_sent for qso in qsos if qso.callsign_sent), ""
        )
        if station_calls:
            headers["CALLSIGN"] = [station_calls]
        else:
            errors.append(
                ImportMessage(
                    0,
                    "missing_station_callsign",
                    "ADIF must identify the submitting station with STATION_CALLSIGN or OPERATOR.",
                )
            )
    station_call = _first(headers, "CALLSIGN")
    if station_call:
        qsos = [
            replace(qso, callsign_sent=station_call) if not qso.callsign_sent else qso
            for qso in qsos
        ]
    for header, field_names in {
        "CALLSIGN": ("STATION_CALLSIGN", "OPERATOR"),
        "NAME": ("MY_NAME",),
        "LOCATION": ("MY_GRIDSQUARE",),
    }.items():
        if not headers.get(header):
            value = next(
                (
                    str(qso.fields.get(name.lower(), ""))
                    for qso in qsos
                    for name in field_names
                    if qso.fields.get(name.lower())
                ),
                "",
            )
            if value:
                headers[header] = [value]
    return ParsedLog(headers, unknown_headers, qsos, errors, [], text.splitlines(), {})
