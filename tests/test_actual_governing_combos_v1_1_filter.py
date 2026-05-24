
from tools.extract_actual_governing_combos_v1 import (
    is_candidate_key,
    source_path_allows_actual_combo,
    scan_report_rows,
)

def test_v1_1_excludes_pipeline_metadata_keys():
    assert not is_candidate_key("combo_family")
    assert not is_candidate_key("combo_required_family")
    assert not is_candidate_key("combo_resolved_family")
    assert not is_candidate_key("combo_resolved_by_v1")
    assert not is_candidate_key("raw_combo_values_found_in_report")

def test_v1_1_blocks_final_report_pipeline_paths():
    assert not source_path_allows_actual_combo("raw_combo", "raw_combo", "final_engine_report_combo_resolved.json.checks[0]")
    assert not source_path_allows_actual_combo("governing_combo", "governing_combo", "final_engine_report_combo_resolved.json.checks[0]")
    assert not source_path_allows_actual_combo("combo_family", "combo_family", "final_engine_report_combo_resolved.json.checks[0]")

def test_v1_1_allows_nested_design_summary_combo():
    assert source_path_allows_actual_combo(
        "evidence.beam_design_summary.Combo",
        "Combo",
        "final_engine_report_combo_resolved.json.checks[0]",
    )

def test_v1_1_scan_report_rows_ignores_combo_family_false_positive():
    report = {"checks": [{"check_id": "beam_shear", "combo_family": "K_E", "combo_required_family": "K_E", "combo_resolved_family": "K_E", "raw_combo": "UNEXPOSED_ETABS_COMBO::K_E"}]}
    assert scan_report_rows(report, "final_engine_report_combo_resolved.json") == []

def test_v1_1_scan_report_rows_accepts_actual_nested_combo():
    report = {"checks": [{"check_id": "beam_shear", "combo_family": "K_E", "evidence": {"beam_design_summary": {"Combo": "K_E_X"}}}]}
    found = scan_report_rows(report, "final_engine_report_combo_resolved.json")
    assert len(found) == 1
    assert found[0]["candidate"] == "K_E_X"
    assert found[0]["family"] == "K_E"
