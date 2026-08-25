import inspect

import tools.probe_vs6_ts500_load_basis_sources as probe


def test_load_basis_probe_is_read_only_and_factual_only():
    source = inspect.getsource(probe)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetLoadType(",
        "SetLoads(",
        "SWAY_PREVENTED",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert "capture_etabs_static_linear_cases" in source
    assert '"ts500_action_roles_promoted": False' in source
    assert '"ts500_stability_load_combinations_constructed": False' in source
    assert '"uncracked_stiffness_basis_promoted": False' in source
    assert '"sway_classification_promoted": False' in source
    assert '"engineering_calculation_performed": False' in source
    assert '"compliance_verdict_emitted": False' in source


def test_probe_selects_linear_static_cases_from_factual_summary_not_names():
    class CaptureStatus:
        value = "FULL"

    class Parsed:
        return_code = 0
        field_keys = ("Name", "Type", "GUID")
        row_count_reported = 4
        rows = (
            {"Name": "A", "Type": "Linear Static", "GUID": "1"},
            {"Name": "B", "Type": "Response Spectrum", "GUID": "2"},
            {"Name": "odd-name", "Type": "Linear Static", "GUID": "3"},
            {"Name": "Modal", "Type": "Modal - Ritz", "GUID": "4"},
        )

    class Fetched:
        capture_status = CaptureStatus()
        parsed = Parsed()
        selected_signature = {}

    original = probe.fetch_display_table
    try:
        probe.fetch_display_table = lambda *_args, **_kwargs: Fetched()
        names, snapshot = probe._linear_static_case_names(object())
    finally:
        probe.fetch_display_table = original

    assert names == ("A", "odd-name")
    assert snapshot["capture_status"] == "FULL"
    assert snapshot["row_count_captured"] == 4
