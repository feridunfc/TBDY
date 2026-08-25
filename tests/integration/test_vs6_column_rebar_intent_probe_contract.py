import inspect

import tools.run_live_vs6_column_rebar_intent_probe as runner


def test_rebar_intent_probe_is_read_only_and_delegates_to_provider():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
        "GetRebarColumn(",
        "generate_rectangular_column_rebar_candidates(",
        "select_engine_rebar_for_demands(",
        "evaluate_column_design(",
    ):
        assert forbidden not in source

    assert "capture_etabs_column_rebar_intent" in source
    assert '"intent_promoted_to_provided_rebar": False' in source
    assert '"intent_promoted_to_engine_selected_rebar": False' in source
    assert '"reinforcement_selected": False' in source


def test_rebar_intent_probe_requires_exact_model_section_and_length_contract():
    source = inspect.getsource(runner)
    assert "--expected-model-fingerprint" in source
    assert "--section-name" in source
    assert "--reviewed-length-unit" in source
    assert "BLOCKED_MODEL_IDENTITY_MISMATCH" in source
