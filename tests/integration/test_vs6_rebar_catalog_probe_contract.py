import inspect

import tools.run_live_vs6_rebar_catalog_probe as runner


def test_live_rebar_catalog_probe_is_read_only_and_delegates_to_provider():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
        "build_rebar_catalog_from_rows(",
        "generate_rectangular_column_rebar_candidates(",
        "select_engine_rebar_for_demands(",
        "evaluate_column_design(",
    ):
        assert forbidden not in source

    assert "capture_etabs_rebar_catalog_evidence" in source
    assert '"catalog_field_semantics_promoted": False' in source
    assert '"column_longitudinal_bar_catalog_promoted": False' in source
    assert '"reinforcement_selected": False' in source


def test_live_rebar_catalog_probe_requires_exact_model_fingerprint():
    source = inspect.getsource(runner)
    assert "--expected-model-fingerprint" in source
    assert "BLOCKED_MODEL_IDENTITY_MISMATCH" in source
