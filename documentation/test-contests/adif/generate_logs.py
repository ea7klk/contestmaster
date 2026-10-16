#!/usr/bin/env python3
"""Generate deterministic ADI/ADIF logs for the test sprint."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contact_graph import build_contact_plan  # noqa: E402

PARTICIPANT_COUNT = 56
CONTEST = "test-adif-ft8-sprint"
QSO_DATE = "20240914"
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
    contact_plan = build_contact_plan(stations, STARTS_AT)
    logs: dict[str, str] = {}
    for station in stations:
        records = []
        for contact in contact_plan[station]:
            time_on = contact.occurred_at.strftime("%H%M%S")
            worked = contact.worked_callsign
            records.append(
                f"<STATION_CALLSIGN:{len(station)}>{station} "
                f"<CALL:{len(worked)}>{worked} <BAND:3>20M <MODE:3>FT8 "
                f"<QSO_DATE:8>{QSO_DATE} <TIME_ON:6>{time_on} "
                "<RST_SENT:3>-10 <RST_RCVD:3>-12 <EOR>"
            )
        logs[f"{station}.adi"] = "<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n<EOF>\n"
    return logs


def write_logs(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = set(build_logs())
    for existing in output_dir.glob("*.adi"):
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
        help="directory for generated .adi files (default: this folder/logs)",
    )
    args = parser.parse_args()
    print(f"Generated {write_logs(args.output_dir)} ADIF logs in {args.output_dir}")


if __name__ == "__main__":
    main()
