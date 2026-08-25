import inspect

import tools.run_live_vs6_ts500_stiffness_basis_assessment as runner


def test_runner_is_read_only_and_stops_before_later_engineering_paths():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetModifiers(",
        "evaluate_ts500_story_stability_index(",
        "resolve_ts500_story_sway_from_stability_indices(",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert "capture_etabs_strict_column_topology" in source
    assert "build_assigned_rc_frame_bending_modifier_evidence" in source
    assert "assess_ts500_eq713_stiffness_basis" in source


def test_reanalysis_required_is_truthful_closure_not_adapter_failure():
    source = inspect.getsource(runner)
    assert "REANALYSIS_REQUIRED is a truthful engineering closure state" in source
    assert '"reanalysis_required_emitted": resolution.reanalysis_required' in source
    assert '"stability_index_calculated": False' in source
    assert '"sway_classification_promoted": False' in source
    assert '"engine_selected_rebar_emitted": False' in source
    assert "return 0" in source
