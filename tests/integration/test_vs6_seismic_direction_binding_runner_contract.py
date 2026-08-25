import inspect

import tools.run_live_vs6_ts500_seismic_direction_binding as runner


def test_runner_is_read_only_and_keeps_later_closures_blocked():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "evaluate_ts500_story_stability_index(",
        "resolve_ts500_story_sway_from_stability_indices(",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert "capture_etabs_static_linear_cases" in source
    assert "promote_etabs_static_cases_to_ts500_stability_actions" in source
    assert "capture_etabs_auto_seismic_direction_evidence" in source
    assert "bind_etabs_seismic_action_directions" in source


def test_runner_does_not_infer_direction_from_case_names():
    source = inspect.getsource(runner)
    assert '"case_names_used_for_direction_inference": False' in source
    assert '"wind_direction_bound": False' in source
    assert '"ts500_stability_load_combinations_constructed": False' in source
    assert '"uncracked_stiffness_basis_promoted": False' in source
    assert '"stability_index_calculated": False' in source
    assert '"sway_classification_promoted": False' in source


def test_truthful_blocked_binding_is_not_adapter_failure():
    source = inspect.getsource(runner)
    assert "Truthful blocked direction evidence is an engineering closure state" in source
    assert "return 0" in source
