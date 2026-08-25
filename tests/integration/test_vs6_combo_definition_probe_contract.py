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


def test_generated_com_list_shapes_are_decoded_without_changing_semantics():
    class FakeRespCombo:
        def GetTypeCombo(self, name):
            assert name == "Combo"
            return [0, 0]

        def GetCaseList(self, name):
            assert name == "Combo"
            return [2, [0, 1], ["LC_G", "ENV_CHILD"], [1.0, 0.5], 0]

    combo_type, raw_type = runner._get_combo_type(FakeRespCombo(), "Combo")
    constituents, raw_case_list = runner._get_case_list(FakeRespCombo(), "Combo")

    assert combo_type == 0
    assert raw_type == [0, 0]
    assert raw_case_list == [2, [0, 1], ["LC_G", "ENV_CHILD"], [1.0, 0.5], 0]
    assert constituents == (
        {
            "index": 0,
            "cname_type_code": 0,
            "cname_type": "LOAD_CASE",
            "name": "LC_G",
            "scale_factor": 1.0,
        },
        {
            "index": 1,
            "cname_type_code": 1,
            "cname_type": "LOAD_COMBO",
            "name": "ENV_CHILD",
            "scale_factor": 0.5,
        },
    )
