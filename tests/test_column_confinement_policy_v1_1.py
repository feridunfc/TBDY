
from tools.apply_column_confinement_policy_v1_1 import (
    apply_policy,
    apply_policy_to_row,
    extract_confinement_fields,
)

def test_extracts_confinement_evidence_fields():
    row = {
        "check_id": "column_confinement",
        "message": "Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3, source=etabs_design_summary. Proposal: use at least 12 legs Phi8",
    }
    out = extract_confinement_fields(row)
    assert out["Ash_provided"] == 236
    assert out["Ash_required"] == 567
    assert out["tie_dia_mm"] == 10
    assert out["spacing_mm"] == 150
    assert out["legs_x"] == 3
    assert out["legs_y"] == 3

def test_downgrades_non_final_proposal_fail_to_warning():
    row = {
        "check_id": "column_confinement",
        "status": "FAIL",
        "evaluation_level": "ETABS_DESIGN_RESULT",
        "source": "etabs_design_summary.",
        "message": "Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3, source=etabs_design_summary. Proposal: use at least 12 legs Phi8",
    }
    out, changed = apply_policy_to_row(row)
    assert changed is True
    assert out["status"] == "WARNING"
    assert out["evaluation_level"] == "SCREENING"
    assert out["reason_code"] == "non_final_confinement_proposal"
    assert out["Ash_provided"] == 236
    assert out["Ash_required"] == 567
    assert out["spacing_mm"] == 150
    assert out["legs_x"] == 3
    assert out["legs_y"] == 3

def test_preserves_real_final_provided_fail():
    row = {
        "check_id": "column_confinement",
        "status": "FAIL",
        "evaluation_level": "DESIGN_LEVEL",
        "source": "provided_rebar",
        "message": "Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3",
    }
    out, changed = apply_policy_to_row(row)
    assert changed is False
    assert out["status"] == "FAIL"
    assert out["evaluation_level"] == "DESIGN_LEVEL"
    assert out["source"] == "provided_rebar"
    assert out["Ash_required"] == 567

def test_apply_policy_updates_summary_when_no_real_confinement_fail_remains():
    report = {
        "report_metadata": {"schema": "engine_report.v1.2"},
        "checks": [
            {
                "check_id": "column_confinement",
                "element_label": "C1",
                "status": "FAIL",
                "evaluation_level": "ETABS_DESIGN_RESULT",
                "source": "etabs_design_summary.",
                "message": "Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3, source=etabs_design_summary. Proposal: use at least 12 legs Phi8",
            },
            {
                "check_id": "column_design_full",
                "element_label": "C1",
                "status": "FAIL",
                "evaluation_level": "DESIGN_LEVEL",
                "source": "column_module_summary",
                "message": "Full design fail controlled by confinement",
            },
        ],
    }
    out = apply_policy(report)
    assert out["confinement_policy_summary"]["column_confinement_fail_to_warning"] == 1
    assert out["confinement_policy_summary"]["column_design_full_fail_to_warning"] == 1
    rows = out["checks"]
    assert rows[0]["status"] == "WARNING"
    assert rows[1]["status"] == "WARNING"
