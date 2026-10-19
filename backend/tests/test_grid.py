import pytest

from backend.app.rulesets.grid import (
    commenced_kilometers,
    distance_kilometers,
    locator_center,
    normalize_locator,
)


def test_locator_center_uses_maidenhead_field_square_and_subsquare_steps():
    latitude, longitude = locator_center("IO91AA", 6)

    assert latitude == pytest.approx(51.0208333333)
    assert longitude == pytest.approx(-1.9583333333)


def test_distance_returns_integer_commenced_kilometers_and_same_cell_zero():
    assert distance_kilometers("IO91AA", "IO91AA", 6) == 0
    assert distance_kilometers("IO91AA", "IO91AB", 6) == 5


def test_commenced_kilometer_rounding_handles_exact_and_just_over_threshold():
    assert commenced_kilometers(5.0) == 5
    assert commenced_kilometers(5.000001) == 6
    assert commenced_kilometers(4.999999) == 5


def test_locator_validation_requires_supported_precision_and_valid_maidenhead_text():
    assert normalize_locator(" io91aa ", 4) == "IO91"
    assert normalize_locator("IO91", 6) is None
    assert normalize_locator("ZZ91AA", 6) is None
    assert normalize_locator("IO91AA", 5) is None
