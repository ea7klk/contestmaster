"""Build deterministic reciprocal contact plans for synthetic contest logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

BAND_MIN_FREQUENCY_KHZ = 14_000
BAND_MAX_FREQUENCY_KHZ = 14_350


@dataclass(frozen=True)
class Contact:
    worked_callsign: str
    occurred_at: datetime
    frequency_khz: int
    sent_serial: int
    received_serial: int
    matched: bool


def _external_callsign(index: int) -> str:
    chars = []
    for _ in range(3):
        chars.append(chr(ord("A") + index % 26))
        index //= 26
    if index:
        raise ValueError("external callsign fixture range exceeded")
    return "W9" + "".join(reversed(chars))


def build_contact_plan(callsigns: list[str], starts_at: datetime) -> dict[str, list[Contact]]:
    """Build 10, 15, or 20 QSOs per station with exactly 80% reciprocal calls."""
    count = len(callsigns)
    if count < 17:
        raise ValueError("at least 17 stations are needed for the configured contact degrees")

    degree_options = (8, 12, 16)
    degrees = [degree_options[i % len(degree_options)] for i in range(count)]
    remaining = degrees.copy()
    tie_break = list(range(count))
    # A stable permutation varies the graph without introducing nondeterminism.
    tie_break = sorted(tie_break, key=lambda index: ((index * 37) % count, index))
    rank = {station: position for position, station in enumerate(tie_break)}
    edges: list[tuple[int, int]] = []

    while True:
        active = sorted(
            (station for station in range(count) if remaining[station] > 0),
            key=lambda station: (-remaining[station], rank[station]),
        )
        if not active:
            break
        station = active[0]
        degree = remaining[station]
        neighbors = active[1 : degree + 1]
        if len(neighbors) != degree or any(remaining[neighbor] <= 0 for neighbor in neighbors):
            raise ValueError("could not construct a simple reciprocal contact graph")
        remaining[station] = 0
        for neighbor in neighbors:
            remaining[neighbor] -= 1
            edges.append((min(station, neighbor), max(station, neighbor)))

    if any(remaining):
        raise ValueError("reciprocal contact graph left unpaired degree")

    events: list[list[dict[str, object]]] = [[] for _ in callsigns]
    adjacency = [0] * count
    frequency_rng = Random("contestmaster-synthetic-20m")
    for edge_index, (left, right) in enumerate(sorted(set(edges))):
        occurred_at = starts_at + timedelta(seconds=edge_index)
        frequency_khz = frequency_rng.randint(
            BAND_MIN_FREQUENCY_KHZ, BAND_MAX_FREQUENCY_KHZ
        )
        events[left].append(
            {
                "peer": right,
                "worked": callsigns[right],
                "at": occurred_at,
                "frequency_khz": frequency_khz,
                "matched": True,
            }
        )
        events[right].append(
            {
                "peer": left,
                "worked": callsigns[left],
                "at": occurred_at,
                "frequency_khz": frequency_khz,
                "matched": True,
            }
        )
        adjacency[left] += 1
        adjacency[right] += 1

    external_index = 0
    for station, degree in enumerate(adjacency):
        expected_degree = degrees[station]
        if degree != expected_degree:
            raise ValueError("generated reciprocal graph does not match its degree sequence")
        unmatched_count = degree // 4
        for _local_index in range(unmatched_count):
            events[station].append(
                {
                    "peer": None,
                    "worked": _external_callsign(external_index),
                    "at": starts_at + timedelta(hours=2, seconds=external_index * 10),
                    "frequency_khz": frequency_rng.randint(
                        BAND_MIN_FREQUENCY_KHZ, BAND_MAX_FREQUENCY_KHZ
                    ),
                    "matched": False,
                }
            )
            external_index += 1

    ordered_events = [
        sorted(station_events, key=lambda event: (event["at"], event["worked"]))
        for station_events in events
    ]
    serials: dict[tuple[int, int], int] = {}
    for station, station_events in enumerate(ordered_events):
        for serial, event in enumerate(station_events, start=1):
            peer = event["peer"]
            if isinstance(peer, int):
                serials[(station, peer)] = serial

    plan: dict[str, list[Contact]] = {}
    for station, station_events in enumerate(ordered_events):
        contacts = []
        for serial, event in enumerate(station_events, start=1):
            peer = event["peer"]
            matched = isinstance(peer, int)
            contacts.append(
                Contact(
                    worked_callsign=str(event["worked"]),
                    occurred_at=event["at"],
                    frequency_khz=int(event["frequency_khz"]),
                    sent_serial=serial,
                    received_serial=serials[(peer, station)] if matched else 1,
                    matched=matched,
                )
            )
        plan[callsigns[station]] = contacts

    return plan
