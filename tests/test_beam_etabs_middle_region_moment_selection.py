from __future__ import annotations

from tbdy_engine.design.beams.etabs_single_beam_frameforce_runner import (
    _middle_region_positive_m3_row,
)


def test_middle_region_positive_m3_selects_governing_region_value_not_exact_mid() -> None:
    rows = [
        {"station": 0.0, "m3": 18.2055},
        {"station": 1.8, "m3": 31.8228},
        {"station": 2.52, "m3": 43.7621},
        {"station": 3.6, "m3": 42.9902},
    ]

    row = _middle_region_positive_m3_row(rows)

    assert row is not None
    assert row["station"] == 2.52
    assert row["m3"] == 43.7621


def test_middle_region_positive_m3_excludes_next_end_j_design_station() -> None:
    rows = [
        {"station": 0.0, "m3": 18.2055},
        {"station": 1.8, "m3": 31.8228},
        {"station": 2.52, "m3": 43.7621},
        {"station": 2.88, "m3": 47.1527},
        {"station": 3.6, "m3": 42.9902},
    ]

    row = _middle_region_positive_m3_row(rows)

    assert row is not None
    assert row["station"] == 2.52
    assert row["m3"] == 43.7621


def test_middle_region_positive_m3_returns_none_when_no_positive_rows() -> None:
    rows = [
        {"station": 0.0, "m3": -10.0},
        {"station": 1.8, "m3": -5.0},
        {"station": 3.6, "m3": -2.0},
    ]

    assert _middle_region_positive_m3_row(rows) is None
