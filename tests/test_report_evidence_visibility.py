from __future__ import annotations

from pathlib import Path

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.reports.json_reporter import JSONReporter


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_CHECK_IDS = {
    "column_axial",
    "column_pmm",
    "column_shear",
    "column_rebar_minimum",
    "beam_flexure",
    "beam_shear",
    "column_capacity_hierarchy",
    "beam_capacity_hierarchy",
}


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _check_payload(*, status: str = "OK", ratio: float = 0.5, evidence: dict | None = None, **extra):
    payload = {
        "status": status,
        "ratio": ratio,
        "value": ratio,
        "limit": 1.0,
        "unit": "ratio",
        "message": "evidence visibility fixture",
        "tbdy_ref": "fixture",
        "evaluation_level": "DESIGN_LEVEL",
    }
    if evidence is not None:
        payload["evidence"] = evidence
    payload.update(extra)
    return payload


def _eval_results():
    return {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "geometry": _check_payload(evidence={"geometry": "ok"}),
                            "axial": _check_payload(
                                governing_combo="CASE_N",
                                combo_family=None,
                                evidence={
                                    "force": "N_kn",
                                    "component_case": "CASE_N",
                                    "governing_combo": "CASE_N",
                                },
                            ),
                            "pmm": _check_payload(
                                governing_combo="PMM_COMBO",
                                combo_family=None,
                                evidence={
                                    "governing_combo": "PMM_COMBO",
                                    "source": "column_pmm",
                                },
                            ),
                            "shear": _check_payload(
                                governing_combo=None,
                                combo_family=None,
                                evidence={
                                    "force": "max(abs(Vx_kn), abs(Vy_kn))",
                                    "Vx_case": "CASE_VX",
                                    "Vy_case": "CASE_VY",
                                },
                            ),
                            "confinement": _check_payload(evidence={"confinement": "ok"}),
                            "rebar_minimum": _check_payload(
                                governing_combo=None,
                                combo_family=None,
                                evidence={
                                    "As_total_mm2": 1200.0,
                                    "As_min_mm2": 900.0,
                                    "rho_pct": 1.33,
                                    "rho_min_pct": 1.0,
                                    "source": "real_rebar",
                                },
                            ),
                        },
                    }
                ]
            },
            "BEAM_DESIGN": {
                "outputs": [
                    {
                        "label": "B1",
                        "story": "S1",
                        "checks": {
                            "geometry": _check_payload(evidence={"geometry": "ok"}),
                            "flexure": _check_payload(
                                governing_combo="BEAM_FLEX_COMBO",
                                combo_family=None,
                                evidence={
                                    "forces": {
                                        "M_pos_case": "CASE_M_POS",
                                        "M_neg_left_case": "CASE_M_LEFT",
                                        "M_neg_right_case": "CASE_M_RIGHT",
                                    },
                                    "governing_combo": "BEAM_FLEX_COMBO",
                                },
                            ),
                            "shear": _check_payload(
                                governing_combo="BEAM_SHEAR_COMBO",
                                combo_family=None,
                                evidence={
                                    "forces": {
                                        "V_max_case": "CASE_V_MAX",
                                        "V_at_support_case": "CASE_V_SUPPORT",
                                    },
                                    "governing_combo": "BEAM_SHEAR_COMBO",
                                },
                            ),
                            "ductility": _check_payload(evidence={"ductility": "ok"}),
                        },
                    }
                ]
            },
            "SCWB_CHECK": {
                "column_capacity_hierarchy": [
                    _check_payload(
                        status="WARNING",
                        ratio=0.9,
                        evidence={
                            "joint_id": "J1",
                            "Mrc_sum": 900.0,
                            "Mrb_sum": 1000.0,
                            "ratio": 0.9,
                        },
                    )
                ],
                "beam_capacity_hierarchy": [
                    _check_payload(
                        status="WARNING",
                        ratio=0.9,
                        evidence={
                            "joint_id": "J1",
                            "Mrc_sum": 900.0,
                            "Mrb_sum": 1000.0,
                            "ratio": 0.9,
                        },
                    )
                ],
            },
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN", "BEAM_DESIGN", "SCWB_CHECK"],
        "cache_stats": {},
    }


def _adapted_rows():
    rows = CheckAdapter(_catalog()).adapt_all(_eval_results())
    return {row.check_id: row for row in rows}


def test_check_adapter_preserves_evidence_dict_for_key_checks():
    rows = _adapted_rows()

    assert rows["column_axial"].evidence["component_case"] == "CASE_N"
    assert rows["column_axial"].governing_combo == "CASE_N"
    assert rows["column_pmm"].evidence["governing_combo"] == "PMM_COMBO"
    assert rows["column_pmm"].governing_combo == "PMM_COMBO"
    assert rows["column_shear"].evidence["Vx_case"] == "CASE_VX"
    assert rows["column_shear"].evidence["Vy_case"] == "CASE_VY"
    assert rows["column_rebar_minimum"].evidence["As_min_mm2"] == 900.0
    assert rows["column_rebar_minimum"].evidence["source"] == "real_rebar"
    assert rows["beam_flexure"].evidence["forces"]["M_pos_case"] == "CASE_M_POS"
    assert rows["beam_flexure"].evidence["forces"]["M_neg_left_case"] == "CASE_M_LEFT"
    assert rows["beam_flexure"].evidence["forces"]["M_neg_right_case"] == "CASE_M_RIGHT"
    assert rows["beam_shear"].evidence["forces"]["V_max_case"] == "CASE_V_MAX"
    assert rows["beam_shear"].evidence["forces"]["V_at_support_case"] == "CASE_V_SUPPORT"
    assert rows["column_capacity_hierarchy"].evidence["Mrc_sum"] == 900.0
    assert rows["beam_capacity_hierarchy"].evidence["Mrb_sum"] == 1000.0


def test_check_adapter_does_not_infer_combo_family_or_copy_uses_combo():
    rows = _adapted_rows()

    for check_id in EVIDENCE_CHECK_IDS:
        assert rows[check_id].combo_family is None

    assert rows["column_axial"].governing_combo == "CASE_N"
    assert rows["column_axial"].combo_family != "S_E"
    assert rows["column_shear"].combo_family != "K_E"
    assert rows["beam_flexure"].combo_family != "S_E"
    assert rows["beam_shear"].combo_family != "K_E"


def test_json_reporter_preserves_evidence_in_check_rows():
    checks = list(_adapted_rows().values())
    payload = JSONReporter(write_history=False).build_payload(checks, _eval_results(), runtime_catalog=_catalog())
    rows = {row["check_id"]: row for row in payload["checks"]}

    assert rows["column_pmm"]["evidence"]["governing_combo"] == "PMM_COMBO"
    assert rows["column_axial"]["evidence"]["component_case"] == "CASE_N"
    assert rows["column_shear"]["evidence"]["Vx_case"] == "CASE_VX"
    assert rows["column_rebar_minimum"]["evidence"]["As_min_mm2"] == 900.0
    assert rows["beam_flexure"]["evidence"]["forces"]["M_pos_case"] == "CASE_M_POS"
    assert rows["beam_shear"]["evidence"]["forces"]["V_max_case"] == "CASE_V_MAX"
    assert rows["column_capacity_hierarchy"]["evidence"]["Mrc_sum"] == 900.0
    assert rows["beam_capacity_hierarchy"]["evidence"]["Mrb_sum"] == 1000.0


def test_contract_report_outputs_include_evidence_for_implemented_evidence_checks():
    catalog = _catalog()

    for check_id in EVIDENCE_CHECK_IDS:
        check = catalog.checks[check_id]
        assert check.implementation_status == "IMPLEMENTED"
        assert check.runner_enabled is True
        assert "evidence" in check.report_outputs
