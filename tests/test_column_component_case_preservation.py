from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tbdy_engine.design.columns.module import ColumnDesignModule


@dataclass
class FakeContext:
    envelopes: dict[str, Any] = field(default_factory=dict)
    design_metadata: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    topology: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)
    story_height_map: dict[str, float] = field(default_factory=dict)
    design_basis: dict[str, Any] = field(default_factory=dict)


def _fake_check(
    *,
    status: str = "OK",
    ratio: float = 0.5,
    value: float = 100.0,
    limit: float = 200.0,
    unit: str = "ratio",
    message: str = "ok",
    tbdy_ref: str = "TBDY",
):
    return type(
        "FakeCheck",
        (),
        {
            "status": status,
            "ratio": ratio,
            "value": value,
            "limit": limit,
            "unit": unit,
            "message": message,
            "tbdy_ref": tbdy_ref,
        },
    )()


def _fake_output(*, forces, checks):
    return type(
        "FakeOutput",
        (),
        {
            "label": "C1",
            "story": "S1",
            "section": "Column_80x80",
            "status": "OK",
            "geometry": None,
            "forces": forces,
            "rebar": None,
            "checks": checks,
            "governing_check": next(iter(checks.keys())),
            "governing_ratio": next(iter(checks.values())).ratio,
        },
    )()


def test_column_forces_exposes_component_case_fields():
    ctx = FakeContext(
        envelopes={
            "column_forces_map": {
                "C1": {
                    "P_max": 100.0,
                    "M2_max": 120.0,
                    "M3_max": 180.0,
                    "V2_max": 90.0,
                    "V3_max": 140.0,
                    "P_case": "CASE_P",
                    "M2_case": "CASE_M2",
                    "M3_case": "CASE_M3",
                    "V2_case": "CASE_V2",
                    "V3_case": "CASE_V3",
                }
            }
        }
    )

    forces = ColumnDesignModule(ctx).resolve_forces()
    force = forces["C1"]

    assert force.N_kn == 100.0
    assert force.Mx_knm == 180.0
    assert force.My_knm == 120.0
    assert force.Vx_kn == 90.0
    assert force.Vy_kn == 140.0

    assert force.governing_combo == "CASE_P"
    assert force.N_case == "CASE_P"
    assert force.Mx_case == "CASE_M3"
    assert force.My_case == "CASE_M2"
    assert force.Vx_case == "CASE_V2"
    assert force.Vy_case == "CASE_V3"

    assert not hasattr(force, "combo_family")


def test_column_axial_evidence_uses_n_case():
    module = ColumnDesignModule(FakeContext())

    forces = type(
        "FakeForces",
        (),
        {
            "N_kn": 100.0,
            "Mx_knm": 0.0,
            "My_knm": 0.0,
            "Vx_kn": 0.0,
            "Vy_kn": 0.0,
            "governing_combo": "OLD_GENERIC_CASE",
            "N_case": "CASE_P",
        },
    )()

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={
                "axial": _fake_check(
                    ratio=0.42,
                    value=100.0,
                    limit=240.0,
                    unit="kN",
                    message="axial ok",
                )
            },
        )
    )

    axial = output["checks"]["axial"]

    assert axial["governing_combo"] == "CASE_P"
    assert axial["combo_family"] is None
    assert axial["evidence"]["governing_combo"] == "CASE_P"
    assert axial["evidence"]["component_case"] == "CASE_P"


def test_column_axial_evidence_falls_back_to_legacy_governing_combo():
    module = ColumnDesignModule(FakeContext())

    forces = type(
        "FakeForces",
        (),
        {
            "N_kn": 100.0,
            "Mx_knm": 0.0,
            "My_knm": 0.0,
            "Vx_kn": 0.0,
            "Vy_kn": 0.0,
            "governing_combo": "LEGACY_CASE",
            "N_case": "",
        },
    )()

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={"axial": _fake_check()},
        )
    )

    axial = output["checks"]["axial"]

    assert axial["governing_combo"] == "LEGACY_CASE"
    assert axial["combo_family"] is None
    assert axial["evidence"]["governing_combo"] == "LEGACY_CASE"
    assert axial["evidence"]["component_case"] == "LEGACY_CASE"


def test_column_shear_evidence_includes_vx_vy_cases_but_no_top_level_governing_combo():
    module = ColumnDesignModule(FakeContext())

    forces = type(
        "FakeForces",
        (),
        {
            "N_kn": 0.0,
            "Mx_knm": 0.0,
            "My_knm": 0.0,
            "Vx_kn": 90.0,
            "Vy_kn": 140.0,
            "governing_combo": "AXIAL_CASE_SHOULD_NOT_APPEAR_IN_SHEAR",
            "Vx_case": "CASE_V2",
            "Vy_case": "CASE_V3",
        },
    )()

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={
                "shear": _fake_check(
                    ratio=0.7,
                    value=140.0,
                    limit=200.0,
                    unit="kN",
                    message="shear ok",
                )
            },
        )
    )

    shear = output["checks"]["shear"]

    assert shear["governing_combo"] is None
    assert shear["combo_family"] is None
    assert shear["evidence"]["Vx_case"] == "CASE_V2"
    assert shear["evidence"]["Vy_case"] == "CASE_V3"


def test_missing_component_cases_do_not_break_resolve_or_output():
    ctx = FakeContext(
        envelopes={
            "column_forces_map": {
                "C1": {
                    "P_max": 100.0,
                    "M2_max": 120.0,
                    "M3_max": 180.0,
                    "V2_max": 90.0,
                    "V3_max": 140.0,
                    "P_case": "CASE_P",
                }
            }
        }
    )

    module = ColumnDesignModule(ctx)
    force = module.resolve_forces()["C1"]

    assert force.N_case == "CASE_P"
    assert force.Mx_case == ""
    assert force.My_case == ""
    assert force.Vx_case == ""
    assert force.Vy_case == ""

    output = module._output_to_dict(
        _fake_output(
            forces=force,
            checks={"shear": _fake_check()},
        )
    )

    shear = output["checks"]["shear"]

    assert shear["governing_combo"] is None
    assert shear["combo_family"] is None
    assert shear["evidence"]["Vx_case"] in ("", None)
    assert shear["evidence"]["Vy_case"] in ("", None)