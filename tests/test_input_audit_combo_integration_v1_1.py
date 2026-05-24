
from tools.run_input_audit_v1_1 import combo_alias_audit, build_audit

def test_combo_alias_audit_uses_summary_and_unique_items():
    report = {
        "combo_alias_summary": {
            "rows_resolved": 2,
            "rows_fallback_marker": 1,
            "rows_mismatch": 0,
            "resolved_by": {"required_family_fallback": 1, "alias_exact": 1},
            "resolved_family": {"S_E": 1, "K_E": 1},
        },
        "checks": [
            {
                "check_id": "column_pmm",
                "raw_combo": "UNEXPOSED_ETABS_COMBO::S_E",
                "combo_family": "S_E",
                "combo_required_family": "S_E",
                "combo_resolved_family": "S_E",
                "combo_resolved_by_v1": "required_family_fallback",
                "combo_matches_required_family": True,
            },
            {
                "check_id": "beam_shear",
                "raw_combo": "K_E_X",
                "combo_family": "K_E",
                "combo_required_family": "K_E",
                "combo_resolved_family": "K_E",
                "combo_resolved_by_v1": "alias_exact",
                "combo_matches_required_family": True,
            },
        ],
    }
    out = combo_alias_audit(report)
    assert out["combo_audit_source"] == "combo_alias_summary_v1"
    assert out["rows_resolved"] == 2
    assert out["mapped_unique"] == 2
    assert out["unmapped_unique"] == 0
    assert out["fallback_unique"] == 1
    assert out["actual_unique"] == 1

def test_build_audit_includes_v1_1_combo_fields():
    report = {
        "combo_alias_summary": {
            "rows_resolved": 1,
            "rows_fallback_marker": 1,
            "rows_mismatch": 0,
            "resolved_by": {"required_family_fallback": 1},
            "resolved_family": {"S_E": 1},
        },
        "checks": [
            {
                "check_id": "column_pmm",
                "status": "OK",
                "source": "pmm_module",
                "evaluation_level": "DESIGN_LEVEL",
                "raw_combo": "UNEXPOSED_ETABS_COMBO::S_E",
                "governing_combo": "UNEXPOSED_ETABS_COMBO::S_E",
                "combo_family": "S_E",
                "combo_required_family": "S_E",
                "combo_resolved_family": "S_E",
                "combo_resolved_by_v1": "required_family_fallback",
                "combo_matches_required_family": True,
                "raw_unit": "ratio",
                "canonical_unit": "ratio",
                "display_unit": "ratio",
            }
        ],
    }
    audit = build_audit(report)
    combo = audit["combo_contract_audit"]
    assert combo["combo_audit_source"] == "combo_alias_summary_v1"
    assert combo["rows_fallback_marker"] == 1
    assert audit["unit_audit"]["raw_units_seen"] == ["ratio"]
