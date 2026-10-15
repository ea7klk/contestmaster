"""Conservative Cabrillo reader that preserves source text and unknown fields."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ImportMessage:
    line: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ParsedQso:
    line: int
    occurred_at: datetime
    frequency: str
    mode: str
    callsign_sent: str
    rst_sent: str
    exchange_sent: str
    callsign_received: str
    rst_received: str
    exchange_received: str
    fields: dict[str, Any]
    extra_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ParsedLog:
    headers: dict[str, list[str]]
    unknown_headers: list[dict[str, Any]]
    qsos: list[ParsedQso]
    errors: list[ImportMessage]
    warnings: list[ImportMessage]
    raw_lines: list[str]
    header_aliases: dict[str, str] = field(default_factory=dict)


DEFAULT_QSO_COLUMNS = (
    "frequency",
    "mode",
    "date",
    "time",
    "callsign_sent",
    "rst_sent",
    "exchange_sent",
    "callsign_received",
    "rst_received",
    "exchange_received",
)
HEADER_PATTERN = re.compile(r"^([A-Z0-9][A-Z0-9-]*):(?:\s*)(.*)$", re.IGNORECASE)


def _parse_timestamp(date_value: str, time_value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
        raise ValueError("date must use YYYY-MM-DD")
    if not re.fullmatch(r"\d{4}(?:\d{2})?", time_value):
        raise ValueError("time must use HHMM or HHMMSS")
    time_format = "%H%M%S" if len(time_value) == 6 else "%H%M"
    parsed = datetime.strptime(f"{date_value} {time_value}", f"%Y-%m-%d {time_format}")
    return parsed.replace(tzinfo=UTC)


def parse_cabrillo(
    text: str,
    *,
    qso_columns: list[str] | None = None,
    header_fields: dict[str, str] | None = None,
) -> ParsedLog:
    """Parse one Cabrillo document without discarding source lines or extra columns."""
    lines = text.splitlines()
    headers: dict[str, list[str]] = {}
    unknown_headers: list[dict[str, Any]] = []
    qsos: list[ParsedQso] = []
    errors: list[ImportMessage] = []
    warnings: list[ImportMessage] = []
    expected_columns = tuple(qso_columns or DEFAULT_QSO_COLUMNS)
    aliases = {key.casefold(): value.upper() for key, value in (header_fields or {}).items()}
    required = set(DEFAULT_QSO_COLUMNS)
    if not required.issubset(expected_columns):
        errors.append(
            ImportMessage(
                0,
                "invalid_qso_template",
                "The contest QSO template must include frequency, mode, date, time, and both sent "
                "and received exchange fields.",
            )
        )
        return ParsedLog(
            headers, unknown_headers, qsos, errors, warnings, lines, header_fields or {}
        )

    started = False
    ended = False
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper == "START-OF-LOG":
            if started or ended:
                errors.append(
                    ImportMessage(
                        line_number, "unexpected_start", "Unexpected START-OF-LOG record."
                    )
                )
            started = True
            continue
        if upper == "END-OF-LOG":
            if not started or ended:
                errors.append(
                    ImportMessage(line_number, "unexpected_end", "Unexpected END-OF-LOG record.")
                )
            ended = True
            continue
        if not started:
            errors.append(
                ImportMessage(line_number, "missing_start", "Record appears before START-OF-LOG.")
            )
            continue
        if ended:
            errors.append(
                ImportMessage(line_number, "record_after_end", "Record appears after END-OF-LOG.")
            )
            continue
        if upper.startswith("QSO:"):
            tokens = line.split()[1:]
            if len(tokens) < len(expected_columns):
                errors.append(
                    ImportMessage(
                        line_number,
                        "incomplete_qso",
                        f"QSO record needs at least {len(expected_columns)} fields "
                        "for this contest.",
                    )
                )
                continue
            values = dict(zip(expected_columns, tokens, strict=False))
            try:
                occurred_at = _parse_timestamp(values["date"], values["time"])
            except ValueError as exc:
                errors.append(ImportMessage(line_number, "invalid_qso_time", str(exc)))
                continue
            required_values = (
                "frequency",
                "mode",
                "callsign_sent",
                "rst_sent",
                "exchange_sent",
                "callsign_received",
                "rst_received",
                "exchange_received",
            )
            missing = [name for name in required_values if not values.get(name, "").strip()]
            if missing:
                errors.append(
                    ImportMessage(
                        line_number,
                        "missing_qso_field",
                        "Required QSO fields are empty: " + ", ".join(missing) + ".",
                    )
                )
                continue
            known_values = {name: values.get(name) for name in expected_columns}
            qsos.append(
                ParsedQso(
                    line=line_number,
                    occurred_at=occurred_at,
                    frequency=values["frequency"],
                    mode=values["mode"],
                    callsign_sent=values["callsign_sent"],
                    rst_sent=values["rst_sent"],
                    exchange_sent=values["exchange_sent"],
                    callsign_received=values["callsign_received"],
                    rst_received=values["rst_received"],
                    exchange_received=values["exchange_received"],
                    fields=known_values,
                    extra_fields=tokens[len(expected_columns) :],
                )
            )
            if len(tokens) > len(expected_columns):
                warnings.append(
                    ImportMessage(
                        line_number,
                        "extra_qso_fields",
                        "Unmapped QSO fields were preserved for review.",
                    )
                )
            continue
        match = HEADER_PATTERN.fullmatch(line)
        if not match:
            unknown_headers.append({"line": line_number, "raw": raw_line})
            warnings.append(
                ImportMessage(line_number, "unknown_record", "Unrecognized record was preserved.")
            )
            continue
        name, value = match.groups()
        name = name.upper()
        headers.setdefault(name, []).append(value)
        if (
            name
            not in {
                "CALLSIGN",
                "CONTEST",
                "EMAIL",
                "NAME",
                "OPERATORS",
                "CREATED-BY",
            }
            and name not in set(aliases.values())
            and not name.startswith("CATEGORY-")
        ):
            unknown_headers.append(
                {"line": line_number, "name": name, "value": value, "raw": raw_line}
            )
            warnings.append(
                ImportMessage(line_number, "unknown_header", f"Header {name} was preserved.")
            )

    if not started:
        errors.append(
            ImportMessage(0, "missing_start", "Cabrillo document has no START-OF-LOG record.")
        )
    if not ended:
        errors.append(
            ImportMessage(len(lines), "missing_end", "Cabrillo document has no END-OF-LOG record.")
        )
    for required_header in ("CALLSIGN", "CONTEST"):
        selected = aliases.get(required_header.casefold(), required_header)
        if len(headers.get(selected, [])) != 1 or not headers[selected][0].strip():
            errors.append(
                ImportMessage(
                    0,
                    "required_header",
                    f"Exactly one non-empty {required_header} header is required.",
                )
            )
    if not qsos:
        errors.append(
            ImportMessage(0, "no_qsos", "The log must contain at least one valid QSO record.")
        )
    return ParsedLog(headers, unknown_headers, qsos, errors, warnings, lines, aliases)


def map_categories(
    parsed: ParsedLog, mappings: list[dict[str, Any]]
) -> tuple[dict[str, str], list[ImportMessage]]:
    """Map declared category headers using the contest's configured external values."""
    values: dict[str, str] = {}
    warnings: list[ImportMessage] = []
    by_external = {
        str(item["external_value"]).casefold(): item["category_values"] for item in mappings
    }
    for header, candidates in parsed.headers.items():
        if not header.startswith("CATEGORY-"):
            continue
        for value in candidates:
            mapped = by_external.get(value.casefold())
            if mapped is None:
                warnings.append(
                    ImportMessage(
                        0,
                        "unmapped_category",
                        f"Category value for {header} was preserved but not mapped.",
                    )
                )
                continue
            for dimension, choice in mapped.items():
                values[str(dimension)] = str(choice)
    return values, warnings
