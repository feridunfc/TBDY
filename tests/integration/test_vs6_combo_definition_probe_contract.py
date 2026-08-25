import inspect

import tools.run_live_vs6_combo_definition_probe as runner


def test_vs6_combo_definition_probe_is_read_only_and_stops_before_design():
    source = inspect.getsource(runner)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
        "select_engine_rebar_for_demands(",
        "generate_rectangular_column_rebar_candidates(",
    ):
        assert forbidden not in source

    assert "GetTypeCombo" in source
    assert "GetCaseList" in source
    assert "NONCONCURRENT_EXTREME_COMBINATION" in source
    assert '"p_m2_m3_concurrency_promoted": False' in source
    assert '"reinforcement_selected": False' in source
    assert '"compliance_verdict_emitted": False' in source


def test_vs6_combo_definition_probe_requires_fingerprint_and_explicit_combo_scope():
    source = inspect.getsource(runner)
    assert "--expected-model-fingerprint" in source
    assert "--combos" in source
    assert "BLOCKED_MODEL_IDENTITY_MISMATCH" in source
