from tools.run_input_audit_v1 import (
    audit_combo_contract,
    audit_units,
    build_audit,
    family_match,
    load_combo_contract,
)

def test_family_match_alias_and_pattern():
    families = {
        "S_E": {"aliases": ["EQX"], "patterns": [r".*Ex.*"]},
        "G": {"aliases": ["G"], "patterns": [r"1\.4G"]},
    }
    assert family_match("EQX", families)[:2] == ("S_E", "alias_exact")
    assert family_match("G+0.3Q+Ex", families)[0] == "S_E"
    assert family_match("1.4G+1.6Q", families)[0] == "G"

def test_combo_audit_maps_report_combo_values():
    report = {
        "checks": [
            {"check_id": "column_pmm", "status": "OK", "governing_combo": "G+0.3Q+Ex"},
            {"check_id": "beam_shear", "status": "OK", "combo": "K_E_X"},
            {"check_id": "drift", "status": "WARNING", "combo": "UNKNOWN_COMBO"},
        ]
    }
    contract = {
        "families": {
            "S_E": {"aliases": ["EQ"], "patterns": [r".*Ex.*"]},
            "K_E": {"aliases": ["K_E_X"], "patterns": []},
            "DRIFT": {"aliases": ["DRIFT"], "patterns": []},
        },
        "usage": {"column_pmm": ["S_E"], "beam_shear": ["K_E"], "drift": ["DRIFT"]},
    }
    out = audit_combo_contract(report, contract)
    assert len(out["mapped_combos"]) == 2
    assert len(out["unmapped_combos"]) == 1

def test_unit_audit_detects_suspicious_ash():
    report = {
        "checks": [
            {
                "check_id": "column_confinement",
                "element_label": "C1",
                "status": "WARNING",
                "Ash_required": 99999,
                "Ash_provided": 236,
                "spacing_mm": 150,
            }
        ]
    }
    out = audit_units(report)
    assert out["suspicious_unit_values"]
    assert out["suspicious_unit_values"][0]["field"] == "Ash_required"

def test_build_audit_minimal_report():
    report = {
        "report_metadata": {"schema": "final_engine_report.v1"},
        "checks": [
            {
                "check_id": "column_confinement",
                "status": "WARNING",
                "source": "confinement_proposal",
                "evaluation_level": "SCREENING",
                "reason_code": "non_final_confinement_proposal",
                "confinement_policy": "FAIL_to_WARNING_non_final_proposal",
                "Ash_required": 567,
                "Ash_provided": 236,
                "spacing_mm": 150,
            },
            {
                "check_id": "beam_capacity_hierarchy",
                "status": "WARNING",
                "source": "scwb_resolver",
                "evaluation_level": "APPROXIMATE",
                "reason_code": "approximate_capacity",
            },
        ],
    }
    audit = build_audit(report)
    assert audit["model_input_audit"]["has_scwb_projection_rows"] is True
    assert audit["model_input_audit"]["has_column_confinement_policy"] is True
    assert audit["unit_audit"]["unit_policy"]["engine_canonical"]["moment"] == "kNm"
