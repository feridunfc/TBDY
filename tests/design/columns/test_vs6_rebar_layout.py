import math
import pytest

from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarLayoutError,
    ColumnRebarLayoutInputs,
    generate_rectangular_column_rebar_candidates,
    ts500_min_clear_spacing_mm,
)


def _inputs(**overrides):
    data = dict(
        width_mm=800.0,
        depth_mm=800.0,
        clear_cover_mm=40.0,
        tie_diameter_mm=10.0,
        aggregate_max_mm=22.0,
        allowed_bar_diameters_mm=(14.0, 16.0, 18.0, 20.0, 22.0, 24.0),
    )
    data.update(overrides)
    return ColumnRebarLayoutInputs(**data)


def test_candidate_population_is_deterministic_symmetric_and_within_rho_bounds():
    first = generate_rectangular_column_rebar_candidates(_inputs())
    second = generate_rectangular_column_rebar_candidates(_inputs())

    assert first.status == "PROVEN"
    assert first.candidates == second.candidates
    assert first.candidates

    for candidate in first.candidates:
        assert 0.01 <= candidate.rho <= 0.04
        assert candidate.bar_count == 2 * candidate.n_bars_dir2 + 2 * candidate.n_bars_dir3 - 4
        coords = {(round(bar.x2_mm, 9), round(bar.x3_mm, 9)) for bar in candidate.bars}
        assert len(coords) == candidate.bar_count
        for x2, x3 in coords:
            assert (-x2, x3) in coords
            assert (x2, -x3) in coords


def test_candidate_population_enforces_reviewed_clear_spacing():
    population = generate_rectangular_column_rebar_candidates(_inputs())
    for candidate in population.candidates:
        assert candidate.min_clear_spacing_mm + 1e-9 >= candidate.required_min_clear_spacing_mm
        assert candidate.required_min_clear_spacing_mm == pytest.approx(
            ts500_min_clear_spacing_mm(
                bar_diameter_mm=candidate.bar_diameter_mm,
                aggregate_max_mm=22.0,
            )
        )


def test_ineligible_bar_diameter_is_not_silently_filtered():
    with pytest.raises(ColumnRebarLayoutError, match=">= 14 mm"):
        _inputs(allowed_bar_diameters_mm=(12.0, 16.0))


def test_missing_project_specific_placement_inputs_cannot_be_defaulted():
    with pytest.raises(TypeError):
        ColumnRebarLayoutInputs(
            width_mm=800.0,
            depth_mm=800.0,
            allowed_bar_diameters_mm=(20.0,),
        )


def test_too_congested_geometry_returns_no_feasible_layout_without_guessing():
    population = generate_rectangular_column_rebar_candidates(
        _inputs(
            width_mm=200.0,
            depth_mm=200.0,
            clear_cover_mm=50.0,
            tie_diameter_mm=16.0,
            allowed_bar_diameters_mm=(32.0,),
        )
    )
    assert population.status == "NO_FEASIBLE_LAYOUT"
    assert population.candidates == ()
