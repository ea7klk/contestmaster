"""Cabrillo frequencies are converted to contest band keys before scoring."""

from backend.app.adjudication.scoring import _scoring_band


def test_scoring_band_normalizes_cabrillo_khz_and_preserves_band_values():
    assert _scoring_band("14214") == "20m"
    assert _scoring_band("14.214") == "20m"
    assert _scoring_band("20m") == "20m"
    assert _scoring_band("VHF-OTHER") == "vhf-other"
    assert _scoring_band(None) is None
