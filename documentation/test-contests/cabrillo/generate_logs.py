#!/usr/bin/env python3
"""Generate deterministic Cabrillo 3.0 logs for the test sprint."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contact_graph import build_contact_plan  # noqa: E402

PARTICIPANT_COUNT = 110
CONTEST = "CM-CABRILLO-RESULTS-SPRINT"
QSO_DATE = "2024-09-14"
STARTS_AT = datetime(2024, 9, 14, 12, 0, tzinfo=UTC)


def callsign(index: int) -> str:
    """Return K0 plus a unique three-letter suffix for a zero-based index."""
    if index < 0 or index >= 26**3:
        raise ValueError("participant index is outside the callsign fixture range")
    chars = []
    value = index
    for _ in range(3):
        chars.append(chr(ord("A") + value % 26))
        value //= 26
    return "K0" + "".join(reversed(chars))


def build_logs() -> dict[str, str]:
    stations = [callsign(index) for index in range(PARTICIPANT_COUNT)]
    contact_plan = build_contact_plan(
        stations, STARTS_AT, featured_contact_degrees={0: 64, 1: 24, 2: 16}
    )
    logs: dict[str, str] = {}
    for station in stations:
        qso_lines = []
        for contact in contact_plan[station]:
            # WWROF Cabrillo QSO times have UTC minute precision (HHMM).
            time_on = contact.occurred_at.strftime("%H%M")
            qso_lines.append(
                f"QSO: {contact.frequency_khz} CW "
                f"{QSO_DATE} {time_on} {station} 599 {contact.sent_serial:03d} "
                f"{contact.worked_callsign} 599 {contact.received_serial:03d}"
            )
        logs[f"{station}.log"] = "\n".join(
            (
                "START-OF-LOG: 3.0",
                "CREATED-BY: Contestmaster synthetic test fixture",
                f"CONTEST: {CONTEST}",
                f"CALLSIGN: {station}",
                f"EMAIL: {station}@nomail.invalid",
                *qso_lines,
                "END-OF-LOG:",
                "",
            )
        )
    return logs


def write_logs(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = set(build_logs())
    for existing in output_dir.glob("*.log"):
        if existing.name not in expected:
            existing.unlink()
    for filename, content in build_logs().items():
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
    print(f"Generated {write_logs(args.output_dir)} Cabrillo logs in {args.output_dir}")


if __name__ == "__main__":
    main()
