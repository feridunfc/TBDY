
from tools.combo_alias_resolver_v1 import resolve_combo_family, resolve_report, unique_raw_combo_audit

def test_resolver_maps_common_seismic_before_gravity():
    r = resolve_combo_family("G+0.3Q+Ex")
    assert r["resolved_family"] == "S_E"
    assert r["resolved_by"] in {"alias_exact", "pattern", "heuristic_seismic_token"}

def test_resolver_maps_capacity_and_drift():
    assert resolve_combo_family("K_E_X")["resolved_family"] == "K_E"
    assert resolve_combo_family("kapasite kesme y")["resolved_family"] == "K_E"
    assert resolve_combo_family("Story Drift X")["resolved_family"] == "DRIFT"

def test_fallback_marker_is_resolved_as_low_confidence_family():
    r = resolve_combo_family("UNEXPOSED_ETABS_COMBO::S_E", required_family="S_E")
    assert r["resolved_family"] == "S_E"
    assert r["resolved_by"] == "required_family_fallback"
    assert r["matches_required_family"] is True
    assert r["is_fallback_marker"] is True

def test_report_resolution_flags_mismatch():
    report = {
        "report_metadata": {"schema": "x"},
        "checks": [
            {"check_id": "column_pmm", "raw_combo": "G+0.3Q+Ex", "combo_family": "S_E"},
            {"check_id": "beam_shear", "raw_combo": "G+0.3Q+Ex", "combo_family": "K_E"},
        ],
    }
    out = resolve_report(report)
    assert out["checks"][0]["combo_matches_required_family"] is True
    assert out["checks"][1]["combo_matches_required_family"] is False
    assert out["combo_alias_summary"]["rows_mismatch"] == 1

def test_unique_raw_combo_audit_counts_mapping():
    report = {
        "checks": [
            {"check_id": "column_pmm", "raw_combo": "G+0.3Q+Ex", "combo_family": "S_E"},
            {"check_id": "beam_shear", "raw_combo": "K_E_X", "combo_family": "K_E"},
            {"check_id": "drift", "raw_combo": "??unknown??", "combo_family": ""},
        ]
    }
    audit = unique_raw_combo_audit(report)
    assert audit["unique_raw_combo_count"] == 3
    assert audit["mapped_unique"] >= 2
