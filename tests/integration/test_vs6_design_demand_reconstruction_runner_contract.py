import inspect

import tools.run_vs6_design_demand_reconstruction as runner


def test_reconstruction_runner_is_offline_and_stops_before_design_actions():
    source = inspect.getsource(runner)
    for forbidden in (
        "attach_to_running_etabs",
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "select_engine_rebar_for_demands(",
        "generate_rectangular_column_rebar_candidates(",
        "build_linear_combo_design_demands(",
        "verify_observed_combo_rows_are_generated_subset(",
    ):
        assert forbidden not in source
    assert "evaluate_column_design_demands(" in source
    assert '"etabs_connection_opened": False' in source
    assert '"reinforcement_selected": False' in source
    assert '"section_capacity_computed": False' in source
    assert '"raw_combo_rows_promoted_to_concurrent_states": False' in source


def test_reconstruction_runner_requires_all_three_factual_artifacts():
    source = inspect.getsource(runner)
    assert "--constituent-demand" in source
    assert "--observed-combo-demand" in source
    assert "--combo-definitions" in source
    assert "--combos" in source
