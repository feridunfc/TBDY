
from tools.extract_actual_governing_combos_v1 import (
    apply_actual_combo_to_report,
    build_audit,
    is_candidate_key,
    is_candidate_value,
    scan_report_rows,
)

def test_candidate_key_and_value_detection():
    assert is_candidate_key("Combo")
    assert is_candidate_key("governing_combo")
    assert is_candidate_key("OutputCase")
    assert is_candidate_value("G+0.3Q+Ex")
    assert not is_candidate_value("UNEXPOSED_ETABS_COMBO::S_E")
    assert not is_candidate_value("OK")

def test_scan_report_rows_finds_nested_actual_combo():
    report = {
        "checks": [
            {
                "check_id": "beam_shear",
                "element_label": "B1",
                "combo_family": "K_E",
                "evidence": {"design_summary": {"Combo": "K_E_X"}},
            }
        ]
    }
    found = scan_report_rows(report, "x.json")
    assert len(found) == 1
    assert found[0]["candidate"] == "K_E_X"
    assert found[0]["family"] == "K_E"

def test_apply_actual_combo_attaches_matching_candidate():
    report = {
        "checks": [
            {
                "check_id": "beam_shear",
                "element_label": "B1",
                "combo_family": "K_E",
                "combo_required_family": "K_E",
                "raw_combo": "UNEXPOSED_ETABS_COMBO::K_E",
                "evidence": {"design_summary": {"Combo": "K_E_X"}},
            }
        ]
    }
    candidates = scan_report_rows(report, "x.json")
    out, matches, unmatched = apply_actual_combo_to_report(report, candidates)
    row = out["checks"][0]
    assert row["actual_combo_candidate"] == "K_E_X"
    assert row["actual_combo_family_candidate"] == "K_E"
    assert row["actual_combo_confidence"] == "HIGH"
    assert matches
    assert not unmatched

def test_build_audit_diagnostic_pass_when_no_matches():
    report = {
        "checks": [
            {
                "check_id": "column_pmm",
                "combo_family": "S_E",
                "raw_combo": "UNEXPOSED_ETABS_COMBO::S_E",
            }
        ]
    }
    out, matches, unmatched = apply_actual_combo_to_report(report, [])
    audit = build_audit(out, [], [], matches, unmatched)
    assert audit["summary"]["actual_unique"] == 0
    assert audit["diagnostic"]["actual_combo_source_exposed"] is False
    assert audit["policy"]["changes_check_status"] is False
