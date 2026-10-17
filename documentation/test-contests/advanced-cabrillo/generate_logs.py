#!/usr/bin/env python3
"""Generate deterministic Cabrillo logs for the advanced rules test contest."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contact_graph import build_contact_plan  # noqa: E402

PARTICIPANT_COUNT = 2_500
PARTICIPANTS_PER_ENTITY = 250
ENTITY_PREFIXES = (
    "K0",  # United States
    "VE3",  # Canada
    "DL1",  # Germany
    "EA7",  # Spain
    "JA1",  # Japan
    "VK2",  # Australia
    "LU1",  # Argentina
    "PY2",  # Brazil
    "ZS1",  # South Africa
    "F4",  # France
)
SEED = "contestmaster-advanced-cabrillo-2500-v1"
CONTEST = "test-advanced-cabrillo-rules-challenge"
QSO_DATE = "2024-09-14"
STARTS_AT = datetime(2024, 9, 14, 12, 0, tzinfo=UTC)
ENDS_AT = datetime(2024, 9, 14, 18, 0, tzinfo=UTC)
BAND_SESSIONS = (
    (STARTS_AT, STARTS_AT + timedelta(minutes=25), "20m", 14_000, 14_350),
    (STARTS_AT + timedelta(minutes=90), STARTS_AT + timedelta(minutes=115), "40m", 7_000, 7_300),
    (STARTS_AT + timedelta(minutes=180), STARTS_AT + timedelta(minutes=205), "15m", 21_000, 21_450),
    (STARTS_AT + timedelta(minutes=270), STARTS_AT + timedelta(minutes=295), "10m", 28_000, 29_700),
)
EVENT_WINDOWS = tuple((start, end) for start, end, _band, _low, _high in BAND_SESSIONS)


def callsign(index: int) -> str:
    if index < 0 or index >= PARTICIPANT_COUNT:
        raise ValueError("participant index is outside the callsign fixture range")
    entity_index, suffix_index = divmod(index, PARTICIPANTS_PER_ENTITY)
    chars = []
    value = suffix_index
    for _ in range(3):
        chars.append(chr(ord("A") + value % 26))
        value //= 26
    return ENTITY_PREFIXES[entity_index] + "".join(reversed(chars))


def _power(index: int) -> str:
    return "HIGH" if index == 0 or index % 3 == 0 else "LOW" if index % 3 == 1 else "QRP"


def build_logs() -> dict[str, str]:
    stations = [callsign(index) for index in range(PARTICIPANT_COUNT)]
    count_rng = Random(f"{SEED}:qso-counts")
    qso_counts = [count_rng.randint(50, 200) for _ in stations]
    # Feature a predictable top trio so the advanced scoring fixture has clear
    # results as well as broad randomized coverage.
    qso_counts[:3] = [250, 246, 242]
    contact_degrees = [(count * 4 // 5 // 2) * 2 for count in qso_counts]
    unmatched_counts = [
        count - degree for count, degree in zip(qso_counts, contact_degrees, strict=True)
    ]
    contact_plan = build_contact_plan(
        stations,
        STARTS_AT,
        featured_contact_degrees={},
        contact_degrees=contact_degrees,
        unmatched_counts=unmatched_counts,
        seed=SEED,
        event_windows=EVENT_WINDOWS,
    )
    logs: dict[str, str] = {}
    frequency_rng = Random(f"{SEED}:frequencies")
    shared_frequencies: dict[tuple[datetime, str, str], int] = {}
    for station_index, station in enumerate(stations):
        contacts = list(contact_plan[station])
        qso_lines = []
        for contact in contacts:
            session = next(
                session
                for session in BAND_SESSIONS
                if session[0] <= contact.occurred_at < session[1]
            )
            frequency_key = (
                contact.occurred_at,
                *sorted((station, contact.worked_callsign)),
            )
            if frequency_key not in shared_frequencies:
                shared_frequencies[frequency_key] = frequency_rng.randint(session[3], session[4])
            frequency_khz = shared_frequencies[frequency_key]
            time_on = contact.occurred_at.strftime("%H%M%S")
            qso_lines.append(
                f"QSO: {frequency_khz} CW {QSO_DATE} {time_on} "
                f"{station} 599 {contact.sent_serial:03d} "
                f"{contact.worked_callsign} 599 {contact.received_serial:03d} "
                f"{1 + contact.sent_serial % 2}"
            )
        operator = "MULTI-OP"
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
            "CATEGORY-BAND: ALL",
            "CATEGORY-MODE: CW",
            "CATEGORY-TRANSMITTER: TWO",
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
