from __future__ import annotations

from pathlib import Path

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMBO_FAMILY_NONE_CHECKS = {
    "column_axial",
    "column_pmm",
    "column_shear",
    "beam_flexure",
    "beam_shear",
    "column_capacity_hierarchy",
    "beam_capacity_hierarchy",
}


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _adapter():
    return CheckAdapter(_catalog())


def _by_check_id(rows):
    return {row.check_id: row for row in rows}


def _base_payload(
    *,
    status: str = "OK",
    ratio: float = 0.8,
    value: float = 0.8,
    limit: float = 1.0,
    unit: str = "ratio",
    message: str = "expected future evidence shape",
    tbdy_ref: str = "TBDY 2018",
    governing_combo: str | None = None,
    combo_family: str | None = None,
    evidence: dict | None = None,
):
    payload = {
        "status": status,
        "ratio": ratio,
        "value": value,
        "limit": limit,
        "unit": unit,
        "message": message,
        "tbdy_ref": tbdy_ref,
        "governing_combo": governing_combo,
        "combo_family": combo_family,
        "evidence": evidence,
    }
    return payload


def _expected_column_eval_results():
    axial_evidence = {
        "force": "N_kn",
        "N_kn": 720.0,
        "limit": 1000.0,
        "ratio": 0.72,
        "governing_combo": "P_CASE_1",
    }
    pmm_evidence = {
        "ratio": 0.81,
        "value": 0.81,
        "limit": 1.0,
        "source": "column_pmm",
        "note": "PMM governing case not structured yet",
    }
    shear_evidence = {
        "force": "max(abs(Vx_kn), abs(Vy_kn))",
        "Vx_kn": 310.0,
        "Vy_kn": 280.0,
        "value": 310.0,
        "limit": 500.0,
        "ratio": 0.62,
    }
    return {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "axial": _base_payload(
                                ratio=0.72,
                                value=720.0,
                                limit=1000.0,
                                unit="kN",
                                message="Expected axial evidence shape",
                                tbdy_ref="TBDY 2018 7.3.2",
                                governing_combo="P_CASE_1",
                                combo_family=None,
                                evidence=axial_evidence,
                            ),
                            "pmm": _base_payload(
                                ratio=0.81,
                                value=0.81,
                                limit=1.0,
                                message="Expected PMM evidence shape without structured governing case",
                                tbdy_ref="TBDY 2018 7.3.3",
                                governing_combo=None,
                                combo_family=None,
                                evidence=pmm_evidence,
                            ),
                            "shear": _base_payload(
                                ratio=0.62,
                                value=310.0,
                                limit=500.0,
                                unit="kN",
                                message="Expected column shear evidence shape without governing combo",
                                tbdy_ref="TBDY 2018 7.3.7",
                                governing_combo=None,
                                combo_family=None,
                                evidence=shear_evidence,
                            ),
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {},
    }


def _expected_beam_eval_results():
    flexure_evidence = {
        "forces": {
            "M_pos_knm": 120.0,
            "M_neg_left_knm": 90.0,
            "M_neg_right_knm": 95.0,
        },
        "ratio": 0.76,
        "value": 0.76,
        "limit": 1.0,
        "governing_combo": "B_COMBO_1",
    }
    shear_evidence = {
        "forces": {
            "V_max_kn": 345.0,
            "V_at_support_kn": 330.0,
        },
        "ratio": 0.69,
        "value": 345.0,
        "limit": 500.0,
        "governing_combo": "B_COMBO_2",
    }
    return {
        "results": {
            "BEAM_DESIGN": {
                "outputs": [
                    {
                        "label": "B1",
                        "story": "S1",
                        "checks": {
                            "flexure": _base_payload(
                                ratio=0.76,
                                value=0.76,
                                limit=1.0,
                                message="Expected beam flexure evidence shape",
                                tbdy_ref="TS500 / TBDY 2018 7.4.2",
                                governing_combo="B_COMBO_1",
                                combo_family=None,
                                evidence=flexure_evidence,
                            ),
                            "shear": _base_payload(
                                ratio=0.69,
                                value=345.0,
                                limit=500.0,
                                unit="kN",
                                message="Expected beam shear evidence shape",
                                tbdy_ref="TS500 8.1 / TBDY 2018 7.4.5",
                                governing_combo="B_COMBO_2",
                                combo_family=None,
                                evidence=shear_evidence,
                            ),
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["BEAM_DESIGN"],
        "cache_stats": {},
    }


def _scwb_evidence():
    return {
        "joint_id": "J1",
        "direction": "X",
        "columns": ["C1", "C2"],
        "beams": ["B1", "B2"],
        "sum_mrc_knm": 950.0,
        "sum_mrb_knm": 830.0,
        "required_mrc_knm": 996.0,
        "reason_code": "scwb_ratio_below_limit",
    }


def _expected_scwb_eval_results():
    evidence = _scwb_evidence()
    base = {
        "element_label": "J1",
        "story": "S1",
        "status": "WARNING",
        "ratio": 0.95,
        "value": 950.0,
        "limit": 996.0,
        "unit": "kNm",
        "message": "Expected SCWB evidence shape",
        "action": "Verify connected member capacities.",
        "evaluation_level": "APPROXIMATE",
        "source": "scwb_resolver",
        "reason_code": "scwb_ratio_below_limit",
        "joint_id": "J1",
        "direction": "X",
        "columns": ["C1", "C2"],
        "beams": ["B1", "B2"],
        "sum_mrc_knm": 950.0,
        "sum_mrb_knm": 830.0,
        "required_mrc_knm": 996.0,
        "governing_combo": None,
        "combo_family": None,
        "evidence": evidence,
    }
    return {
        "results": {
            "SCWB_CHECK": {
                "column_capacity_hierarchy": [dict(base)],
                "beam_capacity_hierarchy": [dict(base)],
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["SCWB_CHECK"],
        "cache_stats": {},
    }


def test_expected_column_axial_evidence_shape():
    rows = _by_check_id(_adapter().adapt_all(_expected_column_eval_results()))
    expected = {
        "force": "N_kn",
        "N_kn": 720.0,
        "limit": 1000.0,
        "ratio": 0.72,
        "governing_combo": "P_CASE_1",
    }

    row = rows["column_axial"]

    assert row.check_id == "column_axial"
    assert row.governing_combo == "P_CASE_1"
    assert row.combo_family is None
    assert row.evidence == expected


def test_expected_column_pmm_evidence_shape_without_governing_combo():
    rows = _by_check_id(_adapter().adapt_all(_expected_column_eval_results()))
    expected = {
        "ratio": 0.81,
        "value": 0.81,
        "limit": 1.0,
        "source": "column_pmm",
        "note": "PMM governing case not structured yet",
    }

    row = rows["column_pmm"]

    assert row.governing_combo is None
    assert row.combo_family is None
    assert row.evidence == expected


def test_expected_column_shear_evidence_shape_without_governing_combo():
    rows = _by_check_id(_adapter().adapt_all(_expected_column_eval_results()))
    expected = {
        "force": "max(abs(Vx_kn), abs(Vy_kn))",
        "Vx_kn": 310.0,
        "Vy_kn": 280.0,
        "value": 310.0,
        "limit": 500.0,
        "ratio": 0.62,
    }

    row = rows["column_shear"]

    assert row.governing_combo is None
    assert row.combo_family is None
    assert row.evidence == expected


def test_expected_beam_flexure_evidence_shape():
    rows = _by_check_id(_adapter().adapt_all(_expected_beam_eval_results()))
    expected = {
        "forces": {
            "M_pos_knm": 120.0,
            "M_neg_left_knm": 90.0,
            "M_neg_right_knm": 95.0,
        },
        "ratio": 0.76,
        "value": 0.76,
        "limit": 1.0,
        "governing_combo": "B_COMBO_1",
    }

    row = rows["beam_flexure"]

    assert row.governing_combo == "B_COMBO_1"
    assert row.combo_family is None
    assert row.evidence == expected


def test_expected_beam_shear_evidence_shape():
    rows = _by_check_id(_adapter().adapt_all(_expected_beam_eval_results()))
    expected = {
        "forces": {
            "V_max_kn": 345.0,
            "V_at_support_kn": 330.0,
        },
        "ratio": 0.69,
        "value": 345.0,
        "limit": 500.0,
        "governing_combo": "B_COMBO_2",
    }

    row = rows["beam_shear"]

    assert row.governing_combo == "B_COMBO_2"
    assert row.combo_family is None
    assert row.evidence == expected


def test_expected_scwb_evidence_dict_shape():
    rows = _by_check_id(_adapter().adapt_all(_expected_scwb_eval_results()))
    expected = _scwb_evidence()

    for check_id in ["column_capacity_hierarchy", "beam_capacity_hierarchy"]:
        row = rows[check_id]
        assert row.governing_combo is None
        assert row.combo_family is None
        assert row.evidence == expected


def test_combo_family_remains_none_for_all_expected_future_evidence_rows():
    rows = []
    rows.extend(_adapter().adapt_all(_expected_column_eval_results()))
    rows.extend(_adapter().adapt_all(_expected_beam_eval_results()))
    rows.extend(_adapter().adapt_all(_expected_scwb_eval_results()))
    rows_by_id = _by_check_id(rows)

    for check_id in EXPECTED_COMBO_FAMILY_NONE_CHECKS:
        assert rows_by_id[check_id].combo_family is None


def test_uses_combo_is_not_copied_into_combo_family_when_payload_omits_combo_family():
    eval_results = {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "axial": {
                                "status": "OK",
                                "ratio": 0.72,
                                "value": 720.0,
                                "limit": 1000.0,
                                "unit": "kN",
                                "message": "Payload omits combo_family even though contract uses S_E",
                                "tbdy_ref": "TBDY 2018 7.3.2",
                                "governing_combo": "P_CASE_1",
                                "evidence": {
                                    "force": "N_kn",
                                    "N_kn": 720.0,
                                    "limit": 1000.0,
                                    "ratio": 0.72,
                                    "governing_combo": "P_CASE_1",
                                },
                            },
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {},
    }

    row = _by_check_id(_adapter().adapt_all(eval_results))["column_axial"]

    assert row.governing_combo == "P_CASE_1"
    assert row.combo_family is None
    assert row.evidence["governing_combo"] == "P_CASE_1"
