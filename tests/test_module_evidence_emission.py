from __future__ import annotations

from pathlib import Path

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader


ROOT = Path(__file__).resolve().parents[1]


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _adapter():
    return CheckAdapter(_catalog())


def _by_check_id(rows):
    return {row.check_id: row for row in rows}


def _check_payload(
    *,
    status: str = "OK",
    ratio: float = 0.8,
    value: float = 0.8,
    limit: float = 1.0,
    unit: str = "ratio",
    message: str = "module-shaped check payload",
    tbdy_ref: str = "TBDY 2018",
):
    return {
        "status": status,
        "ratio": ratio,
        "value": value,
        "limit": limit,
        "unit": unit,
        "message": message,
        "tbdy_ref": tbdy_ref,
    }


def _scwb_payload(
    *,
    projection: str,
    status: str = "WARNING",
    ratio: float = 0.95,
    joint_id: str = "J1",
    story: str = "S1",
    direction: str = "X",
):
    columns = ["C1", "C2"]
    beams = ["B1", "B2"]
    sum_mrc = 950.0
    sum_mrb = 830.0
    required = 996.0
    return {
        "element_label": joint_id,
        "story": story,
        "status": status,
        "ratio": ratio,
        "value": sum_mrc,
        "limit": required,
        "unit": "kNm",
        "message": (
            f"SCWB {projection} projection: joint={joint_id}; "
            f"columns={','.join(columns)}; beams={','.join(beams)}; "
            f"dir={direction}; reason_code=scwb_ratio_below_limit; source=scwb_resolver"
        ),
        "action": "Verify connected member capacities.",
        "evaluation_level": "APPROXIMATE",
        "source": "scwb_resolver",
        "reason_code": "scwb_ratio_below_limit",
        "joint_id": joint_id,
        "direction": direction,
        "columns": columns,
        "beams": beams,
        "sum_mrc_knm": sum_mrc,
        "sum_mrb_knm": sum_mrb,
        "required_mrc_knm": required,
    }


def _assert_no_structured_evidence(row):
    assert row.governing_combo is None
    assert row.combo_family is None
    assert row.evidence is None


def test_column_module_shaped_payload_without_explicit_evidence_leaves_fields_none():
    eval_results = {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "axial": _check_payload(
                                ratio=0.72,
                                value=720.0,
                                limit=1000.0,
                                unit="kN",
                                message="Nd=720kN <= 0.40*Ac*fcd=1000kN (ratio=0.72)",
                                tbdy_ref="TBDY 2018 7.3.2",
                            ),
                            "pmm": _check_payload(
                                ratio=0.81,
                                value=0.81,
                                limit=1.0,
                                message="PMM ratio=0.810 (ETABS design summary, case=S_E_1)",
                                tbdy_ref="TBDY 2018 7.3.3",
                            ),
                            "shear": _check_payload(
                                ratio=0.62,
                                value=310.0,
                                limit=500.0,
                                unit="kN",
                                message="Ve=310kN <= Vr=500kN (Vc=120, Vw=380)",
                                tbdy_ref="TBDY 2018 7.3.7",
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

    rows = _by_check_id(_adapter().adapt_all(eval_results))

    for check_id in ["column_axial", "column_pmm", "column_shear"]:
        assert rows[check_id].status == "OK"
        _assert_no_structured_evidence(rows[check_id])


def test_beam_module_shaped_payload_without_explicit_evidence_leaves_fields_none():
    eval_results = {
        "results": {
            "BEAM_DESIGN": {
                "outputs": [
                    {
                        "label": "B1",
                        "story": "S1",
                        "checks": {
                            "flexure": _check_payload(
                                ratio=0.76,
                                value=0.76,
                                limit=1.0,
                                message="Md/Mr ratio=0.760",
                                tbdy_ref="TS500 / TBDY 2018 7.4.2",
                            ),
                            "shear": _check_payload(
                                ratio=0.69,
                                value=345.0,
                                limit=500.0,
                                unit="kN",
                                message="Shear OK: Ve=345kN <= Vr=500kN (Vc=130, Vw=370)",
                                tbdy_ref="TS500 8.1 / TBDY 2018 7.4.5",
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

    rows = _by_check_id(_adapter().adapt_all(eval_results))

    for check_id in ["beam_flexure", "beam_shear"]:
        assert rows[check_id].status == "OK"
        _assert_no_structured_evidence(rows[check_id])


def test_scwb_projection_shaped_payload_without_explicit_evidence_leaves_fields_none():
    eval_results = {
        "results": {
            "SCWB_CHECK": {
                "column_capacity_hierarchy": [
                    _scwb_payload(projection="column", joint_id="J1", direction="X"),
                ],
                "beam_capacity_hierarchy": [
                    _scwb_payload(projection="beam", joint_id="J1", direction="X"),
                ],
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["SCWB_CHECK"],
        "cache_stats": {},
    }

    rows = _by_check_id(_adapter().adapt_all(eval_results))

    for check_id in ["column_capacity_hierarchy", "beam_capacity_hierarchy"]:
        assert rows[check_id].status == "WARNING"
        assert rows[check_id].source == "scwb_resolver"
        _assert_no_structured_evidence(rows[check_id])


def test_scwb_diagnostic_fields_are_not_automatically_promoted_to_evidence():
    eval_results = {
        "results": {
            "SCWB_CHECK": {
                "column_capacity_hierarchy": [
                    _scwb_payload(projection="column", joint_id="J2", direction="Y"),
                ],
                "beam_capacity_hierarchy": [
                    _scwb_payload(projection="beam", joint_id="J2", direction="Y"),
                ],
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["SCWB_CHECK"],
        "cache_stats": {},
    }

    rows = _by_check_id(_adapter().adapt_all(eval_results))

    assert rows["column_capacity_hierarchy"].evidence is None
    assert rows["beam_capacity_hierarchy"].evidence is None


def test_explicit_evidence_still_survives_module_shaped_payload():
    eval_results = {
        "results": {
            "BEAM_DESIGN": {
                "outputs": [
                    {
                        "label": "B1",
                        "story": "S1",
                        "checks": {
                            "shear": {
                                **_check_payload(
                                    ratio=0.69,
                                    value=345.0,
                                    limit=500.0,
                                    unit="kN",
                                    message="Shear OK with explicit evidence",
                                    tbdy_ref="TS500 8.1 / TBDY 2018 7.4.5",
                                ),
                                "governing_combo": "K_E_2",
                                "combo_family": "K_E",
                                "evidence": {
                                    "case": "K_E_2",
                                    "family": "K_E",
                                    "force": "V_max_kn",
                                    "value": 345.0,
                                },
                            },
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

    row = _by_check_id(_adapter().adapt_all(eval_results))["beam_shear"]

    assert row.governing_combo == "K_E_2"
    assert row.combo_family == "K_E"
    assert row.evidence == {
        "case": "K_E_2",
        "family": "K_E",
        "force": "V_max_kn",
        "value": 345.0,
    }
