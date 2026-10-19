"""Maidenhead locator parsing and deterministic integer distance helpers."""

from __future__ import annotations

import math
import re

_GRID_PATTERN = re.compile(r"^[A-R]{2}(?:[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?)?$", re.IGNORECASE)
_EARTH_RADIUS_KM = 6371.0088


def normalize_locator(locator: str | None, precision: int) -> str | None:
    """Return a validated locator prefix at the requested Maidenhead precision."""
    if precision not in {4, 6, 8} or locator is None:
        return None
    normalized = "".join(locator.split()).upper()
    if not _GRID_PATTERN.fullmatch(normalized) or len(normalized) < precision:
        return None
    return normalized[:precision]


def locator_center(locator: str, precision: int) -> tuple[float, float] | None:
    """Return the latitude/longitude of a 4, 6, or 8 character locator cell center."""
    normalized = normalize_locator(locator, precision)
    if normalized is None:
        return None

    longitude = -180.0 + (ord(normalized[0]) - ord("A")) * 20.0
    latitude = -90.0 + (ord(normalized[1]) - ord("A")) * 10.0
    longitude_width = 20.0
    latitude_height = 10.0
    if precision >= 4:
        longitude_width = 2.0
        latitude_height = 1.0
        longitude += int(normalized[2]) * longitude_width
        latitude += int(normalized[3]) * latitude_height
    if precision >= 6:
        longitude_width /= 24
        latitude_height /= 24
        longitude += (ord(normalized[4]) - ord("A")) * longitude_width
        latitude += (ord(normalized[5]) - ord("A")) * latitude_height
    if precision >= 8:
        longitude_width /= 10
        latitude_height /= 10
        longitude += int(normalized[6]) * longitude_width
        latitude += int(normalized[7]) * latitude_height
    return latitude + latitude_height / 2, longitude + longitude_width / 2


def commenced_kilometers(distance: float) -> int:
    """Round positive geographic distance up to whole kilometers."""
    if not math.isfinite(distance) or distance < 0:
        raise ValueError("distance must be finite and non-negative")
    if distance == 0:
        return 0
    return max(1, math.ceil(distance - 1e-12))


def distance_kilometers(first: str, second: str, precision: int) -> int | None:
    """Return whole commenced kilometers between locator cell centers.

    The only floating-point values are geographic intermediates. The scoring
    result is an integer and uses a fixed mean Earth radius and ceiling rule.
    """
    first_normalized = normalize_locator(first, precision)
    second_normalized = normalize_locator(second, precision)
    if first_normalized is None or second_normalized is None:
        return None
    if first_normalized == second_normalized:
        return 0

    first_center = locator_center(first_normalized, precision)
    second_center = locator_center(second_normalized, precision)
    if first_center is None or second_center is None:
        return None
    first_lat, first_lon = map(math.radians, first_center)
    second_lat, second_lon = map(math.radians, second_center)
    latitude_delta = second_lat - first_lat
    longitude_delta = second_lon - first_lon
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_lat) * math.cos(second_lat) * math.sin(longitude_delta / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    arc = 2 * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    distance = _EARTH_RADIUS_KM * arc
    return commenced_kilometers(distance)
