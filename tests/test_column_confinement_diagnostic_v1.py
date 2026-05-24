
from tools.inspect_column_confinement_v1 import classify_confinement_row, diagnose

def test_classifies_auto_screening_fail_candidate():
    row = {
        "check_id": "column_confinement",
        "element_label": "C1",
        "status": "FAIL",
        "evaluation_level": "SCREENING",
        "source": "auto_confinement",
        "message": "Ash=120 < required=180 spacing=100 source=auto_confinement",
    }
    out = classify_confinement_row(row)
    assert out["category"] == "auto_or_screening_fail_candidate"
    assert out["recommended_policy"] == "downgrade_to_WARNING_until_real_confinement_data"

def test_classifies_real_design_fail_candidate():
    row = {
        "check_id": "column_confinement",
        "element_label": "C2",
        "status": "FAIL",
        "evaluation_level": "DESIGN_LEVEL",
        "source": "provided_rebar",
        "message": "Ash=120 < Ash_required=180 spacing=100 legs_x=4 legs_y=4",
    }
    out = classify_confinement_row(row)
    assert out["category"] == "real_design_fail_candidate"
    assert out["recommended_policy"] == "keep_FAIL_and_report_Ash_spacing_evidence"

def test_diagnose_report_counts_rows():
    report = {
        "report_metadata": {"schema": "engine_report.v1.2"},
        "checks": [
            {
                "check_id": "column_confinement",
                "element_label": "C1",
                "status": "FAIL",
                "evaluation_level": "SCREENING",
                "source": "auto_confinement",
                "message": "Ash=120 < required=180 spacing=100",
            },
            {
                "check_id": "column_rebar_minimum",
                "element_label": "C1",
                "status": "WARNING",
                "evaluation_level": "SCREENING",
                "source": "auto_rebar",
                "message": "minimum rebar",
            },
        ],
    }
    diag = diagnose(report)
    assert diag["summary"]["total_column_confinement"] == 1
    assert diag["summary"]["linked_rebar_minimum_by_label"] == 1
    assert diag["summary"]["by_category"]["auto_or_screening_fail_candidate"] == 1
