#!/usr/bin/env python3
"""Generate deterministic Cabrillo 3.0 logs for the test sprint."""

from __future__ import annotations

import argparse
from pathlib import Path

PARTICIPANT_COUNT = 110
CONTEST = "test-cabrillo-sprint"
QSO_DATE = "2024-09-14"


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
    logs: dict[str, str] = {}
    for index in range(PARTICIPANT_COUNT):
        station = callsign(index)
        minute = index % 60
        time_on = f"{12 + index // 60:02d}{minute:02d}"
        logs[f"{station}.log"] = "\n".join(
            (
                "START-OF-LOG: 3.0",
                "CREATED-BY: Contestmaster synthetic test fixture",
                f"CONTEST: {CONTEST}",
                f"CALLSIGN: {station}",
                f"QSO: 14000 CW {QSO_DATE} {time_on} {station} 599 599 EA7TEST 599 599",
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
