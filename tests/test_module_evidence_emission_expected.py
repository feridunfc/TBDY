from __future__ import annotations

from tbdy_engine.adapters.check_adapter import CheckAdapter


def _row(component: str, check_type: str, evidence: dict, *, story: str = "S1"):
    return CheckAdapter().adapt(
        {
            "component": component,
            "story": story,
            "evidence": evidence,
            "checks": [
                {
                    "check_type": check_type,
                    "status": "OK",
                    "ratio": evidence.get("ratio", 0.8),
                    "demand": evidence.get("value"),
                    "capacity": evidence.get("limit"),
                }
            ],
        }
    )[0]


def test_expected_column_axial_evidence_shape():
    expected = {
        "force": "N_kn",
        "N_kn": 720.0,
        "limit": 1000.0,
        "ratio": 0.72,
        "governing_combo": "P_CASE_1",
    }
    row = _row("C1", "axial", expected)
    assert row.id == "C1:S1:axial"
    assert row.evidence == expected


def test_expected_column_pmm_evidence_shape_without_governing_combo():
    expected = {
        "ratio": 0.81,
        "value": 0.81,
        "limit": 1.0,
        "source": "column_pmm",
        "note": "PMM governing case not structured yet",
    }
    row = _row("C1", "pmm", expected)
    assert row.evidence == expected
    assert "governing_combo" not in row.evidence


def test_expected_column_shear_evidence_shape_without_governing_combo():
    expected = {
        "force": "max(abs(Vx_kn), abs(Vy_kn))",
        "Vx_kn": 310.0,
        "Vy_kn": 280.0,
        "value": 310.0,
        "limit": 500.0,
        "ratio": 0.62,
    }
    row = _row("C1", "shear", expected)
    assert row.evidence == expected
    assert "combo_family" not in row.evidence


def test_expected_beam_flexure_evidence_shape():
    expected = {
        "forces": {"M_pos_knm": 120.0, "M_neg_left_knm": 90.0, "M_neg_right_knm": 95.0},
        "ratio": 0.76,
        "value": 0.76,
        "limit": 1.0,
        "governing_combo": "B_COMBO_1",
    }
    row = _row("B1", "flexure", expected)
    assert row.evidence == expected
    assert row.evidence["governing_combo"] == "B_COMBO_1"


def test_expected_beam_shear_evidence_shape():
    expected = {
        "forces": {"V_max_kn": 345.0, "V_at_support_kn": 330.0},
        "ratio": 0.69,
        "value": 345.0,
        "limit": 500.0,
        "governing_combo": "B_COMBO_2",
    }
    row = _row("B1", "shear", expected)
    assert row.evidence == expected
    assert row.evidence["governing_combo"] == "B_COMBO_2"


def test_expected_scwb_evidence_dict_shape():
    expected = {
        "joint_id": "J1",
        "direction": "X",
        "columns": ("C1", "C2"),
        "beams": ("B1", "B2"),
        "sum_mrc_knm": 950.0,
        "sum_mrb_knm": 830.0,
        "required_mrc_knm": 996.0,
        "reason_code": "scwb_ratio_below_limit",
    }
    row = _row("J1", "column_capacity_hierarchy", expected)
    assert row.evidence == expected
    assert set(row.evidence) == set(expected)


def test_combo_family_is_only_present_when_explicitly_supplied_in_evidence():
    without = _row("C1", "axial", {"governing_combo": "P_CASE_1"})
    with_family = _row("C1", "axial", {"governing_combo": "P_CASE_1", "combo_family": "S_E"})
    assert "combo_family" not in without.evidence
    assert with_family.evidence["combo_family"] == "S_E"


def test_current_adapter_does_not_copy_code_or_catalog_hints_into_evidence():
    evidence = {"governing_combo": "P_CASE_1"}
    row = _row("C1", "axial", evidence)
    assert row.evidence == {"governing_combo": "P_CASE_1"}
    assert "uses_combo" not in row.evidence
