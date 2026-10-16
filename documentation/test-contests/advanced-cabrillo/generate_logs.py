#!/usr/bin/env python3
"""Generate deterministic Cabrillo logs for the advanced rules test contest."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contact_graph import build_contact_plan  # noqa: E402

PARTICIPANT_COUNT = 32
CONTEST = "test-advanced-cabrillo-rules-challenge"
QSO_DATE = "2024-09-14"
STARTS_AT = datetime(2024, 9, 14, 12, 0, tzinfo=UTC)
ENDS_AT = datetime(2024, 9, 14, 18, 0, tzinfo=UTC)


def callsign(index: int) -> str:
    if index < 0 or index >= 26**3:
        raise ValueError("participant index is outside the callsign fixture range")
    chars = []
    value = index
    for _ in range(3):
        chars.append(chr(ord("A") + value % 26))
        value //= 26
    return "K0" + "".join(reversed(chars))


def _power(index: int) -> str:
    return "HIGH" if index == 0 or index % 3 == 0 else "LOW" if index % 3 == 1 else "QRP"


def build_logs() -> dict[str, str]:
    stations = [callsign(index) for index in range(PARTICIPANT_COUNT)]
    contact_plan = build_contact_plan(
        stations,
        STARTS_AT,
        featured_contact_degrees={0: 24, 1: 16, 2: 8},
    )
    logs: dict[str, str] = {}
    for station_index, station in enumerate(stations):
        contacts = list(contact_plan[station])
        # K0AAA intentionally repeats its first worked station to exercise duplicate
        # identification and the configured duplicate-contact penalty.
        if station_index == 0:
            first = contacts[0]
            contacts.append(
                type(first)(
                    worked_callsign=first.worked_callsign,
                    occurred_at=ENDS_AT
                    - timedelta(minutes=1)
                    + timedelta(seconds=first.occurred_at.second % 2),
                    frequency_khz=first.frequency_khz,
                    sent_serial=len(contacts) + 1,
                    received_serial=first.received_serial,
                    matched=first.matched,
                )
            )
        qso_lines = []
        for contact in contacts:
            time_on = contact.occurred_at.strftime("%H%M%S")
            mode = "CW" if contact.occurred_at.second % 2 == 0 else "SSB"
            qso_lines.append(
                f"QSO: {contact.frequency_khz} {mode} {QSO_DATE} {time_on} "
                f"{station} 599 {contact.sent_serial:03d} "
                f"{contact.worked_callsign} 599 {contact.received_serial:03d}"
            )
        operator = "MULTI-OP" if station_index % 7 == 0 else "SINGLE-OP"
        power = _power(station_index)
        overlay = "ROOKIE" if station_index % 5 == 0 else "NONE"
        lines = [
            "START-OF-LOG: 3.0",
            "CREATED-BY: Contestmaster advanced synthetic fixture",
            f"CONTEST: {CONTEST}",
            f"CALLSIGN: {station}",
            f"EMAIL: {station}@nomail.invalid",
            f"CATEGORY-OPERATOR: {operator}",
            f"CATEGORY-POWER: {power}",
            "CATEGORY-BAND: 20M",
            "CATEGORY-MODE: MIXED",
            f"CATEGORY-OVERLAY: {overlay}",
            *qso_lines,
            "END-OF-LOG:",
            "",
        ]
        logs[f"{station}.log"] = "\n".join(lines)
    return logs


def write_logs(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = build_logs()
    for existing in output_dir.glob("*.log"):
        if existing.name not in expected:
            existing.unlink()
    for filename, content in expected.items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")
    return len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "logs",
        help="directory for generated .log files (default: this folder/logs)",
    )
    args = parser.parse_args()
    print(f"Generated {write_logs(args.output_dir)} advanced Cabrillo logs in {args.output_dir}")


if __name__ == "__main__":
    main()
