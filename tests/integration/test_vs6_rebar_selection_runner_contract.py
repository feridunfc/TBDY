import inspect

import tools.run_live_vs6_column_rebar_selection as legacy_runner
import tools.run_live_vs6_column_design_engine as integrated_runner


def test_legacy_rebar_selection_entrypoint_delegates_to_integrated_engine():
    source = inspect.getsource(legacy_runner)
    assert "run_live_vs6_column_design_engine" in source
    assert legacy_runner.main is integrated_runner.main

    for forbidden in (
        "normalize_etabs_column_end_demands(",
        "generate_rectangular_column_rebar_candidates(",
        "select_engine_rebar_for_demands(",
        "--reviewed-bar-diameters-mm",
        "--combination-scope-status",
    ):
        assert forbidden not in source


def test_integrated_entrypoint_owns_current_live_rebar_contract():
    source = inspect.getsource(integrated_runner)
    assert "--combos" in source
    assert "--rebar-name-field" in source
    assert "--rebar-diameter-field" in source
    assert "--rebar-diameter-unit" in source
    assert "--analysis-order-status" in source
    assert "--minimum-eccentricity-status" in source
    assert "--slenderness-status" in source
    assert '"combination_scope_status": "ENGINE_DERIVED"' in source
