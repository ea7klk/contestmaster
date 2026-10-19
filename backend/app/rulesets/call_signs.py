"""Deterministic call-sign-derived multiplier values.

The WPX prefix is intentionally independent from CTY country/prefix mappings.
It implements the sponsor's letter/numeral prefix convention for parsing a
worked call; sponsor-specific authorization decisions still require adjudication.
"""

from __future__ import annotations

import re

_CALLSIGN_CLASS_SUFFIXES = {"A", "E", "J", "P"}
_MOBILE_SUFFIXES = {"M", "AM", "MM"}


def callsign_suffix(callsign: str) -> str | None:
    """Return the final slash suffix of a normalized worked callsign, if present."""
    normalized = "".join(callsign.upper().split())
    if "/" not in normalized:
        return None
    suffix = normalized.rsplit("/", 1)[1]
    return suffix or None


def _prefix_from_designator(designator: str) -> str | None:
    match = re.match(r"^(\d*[A-Z]+\d*)", designator)
    if match:
        prefix = match.group(1)
        if any(character.isdigit() for character in prefix):
            return prefix
        letters = re.match(r"^[A-Z]+", prefix)
        return f"{letters.group(0)[:2]}0" if letters else None
    # WPX rules assign zero after the first two letters when a call has no digit.
    letters = re.match(r"^[A-Z]+", designator)
    if letters and not any(character.isdigit() for character in designator):
        return f"{letters.group(0)[:2]}0"
    return None


def wpx_prefix_for_callsign(callsign: str) -> str | None:
    """Return a deterministic WPX-style prefix for a worked call.

    Recognized license-class suffixes (``/A``, ``/E``, ``/J``, ``/P``) do not
    replace the operating prefix. Mobile calls (``/M``, ``/AM``, ``/MM``) do
    not receive a prefix multiplier. For portable calls, a short slash component
    (such as ``PA`` or ``KH9``) is treated as the portable designator; otherwise
    the final component is used. This derives a candidate prefix only and does
    not determine whether a portable designator is authorized by its regulator.
    """
    normalized = "".join(callsign.upper().split())
    if not normalized:
        return None
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return None
    if parts[-1] in _MOBILE_SUFFIXES:
        return None
    while len(parts) > 1 and parts[-1] in _CALLSIGN_CLASS_SUFFIXES:
        parts.pop()
    if parts[-1] in _MOBILE_SUFFIXES:
        return None

    designator = parts[-1]
    if len(parts) > 1:
        prefix_only = [
            part
            for part in parts
            if re.fullmatch(r"(?:[A-Z]{1,3}\d{0,4}|\d[A-Z]{1,3}\d{0,4})", part)
        ]
        if prefix_only:
            designator = prefix_only[-1]

    return _prefix_from_designator(designator)
