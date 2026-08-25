import inspect

import tools.run_live_vs6_ts500_stability_action_inventory as runner


def test_runner_is_read_only_and_does_not_cross_later_closure_boundaries():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "evaluate_ts500_story_stability_index(",
        "resolve_ts500_story_sway_from_stability_indices(",
        "SWAY_PREVENTED",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert "capture_etabs_load_pattern_catalog" in source
    assert "capture_etabs_static_linear_cases" in source
    assert "promote_etabs_static_cases_to_ts500_stability_actions" in source
    assert "resolve_ts500_stability_load_inventory" in source


def test_runner_never_uses_case_names_for_action_role_inference():
    source = inspect.getsource(runner)
    assert '"case_names_used_for_role_inference": False' in source
    assert '"seismic_direction_bound": False' in source
    assert '"wind_direction_bound": False' in source
    assert '"uncracked_stiffness_basis_promoted": False' in source
    assert '"stability_index_calculated": False' in source
    assert '"sway_classification_promoted": False' in source


def test_truthful_blocked_inventory_is_not_adapter_failure():
    source = inspect.getsource(runner)
    assert "A blocked inventory is a truthful engineering closure state" in source
    assert "return 0" in source
