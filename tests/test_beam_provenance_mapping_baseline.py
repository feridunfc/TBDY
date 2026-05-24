from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from tbdy_engine.design.beams.beam_module import BeamDesignModule, BeamForces
from tbdy_engine.engine.context_builder import _build_simple_envelope


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


def _beam_force_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "beam": "B1",
                "story": "S1",
                "station_m": 0.0,
                "output_case": "CASE_I_M2_V2",
                "v2_kn": -90.0,
                "v3_kn": 30.0,
                "m2_knm": -120.0,
                "m3_knm": 45.0,
            },
            {
                "beam": "B1",
                "story": "S1",
                "station_m": 2.5,
                "output_case": "CASE_GLOBAL_V3_M2",
                "v2_kn": 40.0,
                "v3_kn": -140.0,
                "m2_knm": 160.0,
                "m3_knm": 55.0,
            },
            {
                "beam": "B1",
                "story": "S1",
                "station_m": 5.0,
                "output_case": "CASE_J_M3_V3",
                "v2_kn": 45.0,
                "v3_kn": -150.0,
                "m2_knm": 70.0,
                "m3_knm": -180.0,
            },
        ]
    )


def _semantic_beam_map(*, combo: str | None = None, case: str | None = None) -> dict[str, dict[str, Any]]:
    data: dict[str, Any] = {
        "M_pos": 110.0,
        "M_neg_left": 150.0,
        "M_neg_right": 170.0,
        "V_max": 95.0,
        "V_support": 88.0,
        "T_max": 12.0,
    }
    if combo is not None:
        data["combo"] = combo
    if case is not None:
        data["case"] = case
    return {"B1": data}


def _fake_check(
    *,
    status: str = "OK",
    ratio: float = 0.5,
    value: float = 100.0,
    limit: float = 200.0,
    unit: str = "ratio",
    message: str = "ok",
    tbdy_ref: str = "TBDY",
    evaluation_level: str = "DESIGN_LEVEL",
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
            "evaluation_level": evaluation_level,
        },
    )()


def _fake_output(*, forces: BeamForces, checks: dict[str, Any]):
    return type(
        "FakeOutput",
        (),
        {
            "label": "B1",
            "story": "S1",
            "section": "Beam_30x60",
            "status": "OK",
            "geometry": None,
            "forces": forces,
            "rebar": None,
            "checks": checks,
            "governing_check": next(iter(checks.keys())),
            "governing_ratio": next(iter(checks.values())).ratio,
        },
    )()


def test_build_simple_envelope_preserves_beam_component_and_end_station_cases():
    df_env, lookup = _build_simple_envelope(_beam_force_rows(), ["beam"])

    assert not df_env.empty
    assert "B1" in lookup

    row = lookup["B1"]

    assert row["V2_max"] == -90.0
    assert row["V2_case"] == "CASE_I_M2_V2"
    assert row["V3_max"] == -150.0
    assert row["V3_case"] == "CASE_J_M3_V3"
    assert row["M2_max"] == 160.0
    assert row["M2_case"] == "CASE_GLOBAL_V3_M2"
    assert row["M3_max"] == -180.0
    assert row["M3_case"] == "CASE_J_M3_V3"

    assert row["V2_i"] == -90.0
    assert row["V2_i_case"] == "CASE_I_M2_V2"
    assert row["V3_i"] == 30.0
    assert row["V3_i_case"] == "CASE_I_M2_V2"
    assert row["M2_i"] == -120.0
    assert row["M2_i_case"] == "CASE_I_M2_V2"
    assert row["M3_i"] == 45.0
    assert row["M3_i_case"] == "CASE_I_M2_V2"

    assert row["V2_j"] == 45.0
    assert row["V2_j_case"] == "CASE_J_M3_V3"
    assert row["V3_j"] == -150.0
    assert row["V3_j_case"] == "CASE_J_M3_V3"
    assert row["M2_j"] == 70.0
    assert row["M2_j_case"] == "CASE_J_M3_V3"
    assert row["M3_j"] == -180.0
    assert row["M3_j_case"] == "CASE_J_M3_V3"


def test_beam_resolve_forces_consumes_semantic_beam_keys():
    ctx = FakeContext(envelopes={"beam_forces_map": _semantic_beam_map(combo="GENERIC_BEAM_COMBO")})

    force = BeamDesignModule(ctx).resolve_forces()["B1"]

    assert force.M_pos_knm == 110.0
    assert force.M_neg_left_knm == 150.0
    assert force.M_neg_right_knm == 170.0
    assert force.V_max_kn == 95.0
    assert force.V_at_support_kn == 88.0
    assert force.T_max_knm == 12.0
    assert force.governing_combo == "GENERIC_BEAM_COMBO"

    for attr in [
        "M_pos_case",
        "M_neg_left_case",
        "M_neg_right_case",
        "V_max_case",
        "V_at_support_case",
        "combo_family",
    ]:
        assert not hasattr(force, attr)


def test_beam_resolve_forces_does_not_consume_component_case_provenance():
    beam_map = _semantic_beam_map()["B1"]
    beam_map.update(
        {
            "M2_case": "CASE_M2",
            "M3_case": "CASE_M3",
            "V2_case": "CASE_V2",
            "V3_case": "CASE_V3",
            "M2_i_case": "CASE_M2_I",
            "M3_i_case": "CASE_M3_I",
            "V2_i_case": "CASE_V2_I",
            "V3_i_case": "CASE_V3_I",
            "M2_j_case": "CASE_M2_J",
            "M3_j_case": "CASE_M3_J",
            "V2_j_case": "CASE_V2_J",
            "V3_j_case": "CASE_V3_J",
        }
    )
    ctx = FakeContext(envelopes={"beam_forces_map": {"B1": beam_map}})

    force = BeamDesignModule(ctx).resolve_forces()["B1"]

    assert force.M_pos_knm == 110.0
    assert force.V_max_kn == 95.0
    assert force.governing_combo == ""

    component_cases = {
        "CASE_M2",
        "CASE_M3",
        "CASE_V2",
        "CASE_V3",
        "CASE_M2_I",
        "CASE_M3_I",
        "CASE_V2_I",
        "CASE_V3_I",
        "CASE_M2_J",
        "CASE_M3_J",
        "CASE_V2_J",
        "CASE_V3_J",
    }
    assert force.governing_combo not in component_cases

    for attr in [
        "M_pos_case",
        "M_neg_left_case",
        "M_neg_right_case",
        "V_max_case",
        "V_at_support_case",
    ]:
        assert not hasattr(force, attr)


def test_beam_resolve_forces_current_generic_combo_and_case_behavior():
    combo_force = BeamDesignModule(
        FakeContext(envelopes={"beam_forces_map": _semantic_beam_map(combo="GENERIC_BEAM_COMBO")})
    ).resolve_forces()["B1"]
    case_force = BeamDesignModule(
        FakeContext(envelopes={"beam_forces_map": _semantic_beam_map(case="GENERIC_BEAM_CASE")})
    ).resolve_forces()["B1"]
    both_force = BeamDesignModule(
        FakeContext(
            envelopes={
                "beam_forces_map": _semantic_beam_map(
                    combo="GENERIC_BEAM_COMBO",
                    case="GENERIC_BEAM_CASE",
                )
            }
        )
    ).resolve_forces()["B1"]

    assert combo_force.governing_combo == "GENERIC_BEAM_COMBO"
    assert case_force.governing_combo == "GENERIC_BEAM_CASE"
    assert both_force.governing_combo == "GENERIC_BEAM_COMBO"


def test_beam_output_evidence_uses_generic_governing_combo_for_flexure_and_shear():
    module = BeamDesignModule(FakeContext())
    forces = BeamForces(
        label="B1",
        M_pos_knm=110.0,
        M_neg_left_knm=150.0,
        M_neg_right_knm=170.0,
        V_max_kn=95.0,
        V_at_support_kn=88.0,
        T_max_knm=12.0,
        governing_combo="GENERIC_BEAM_COMBO",
    )
    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={
                "flexure": _fake_check(ratio=0.76, value=0.76, limit=1.0),
                "shear": _fake_check(ratio=0.69, value=95.0, limit=140.0, unit="kN"),
            },
        )
    )

    flexure = output["checks"]["flexure"]
    shear = output["checks"]["shear"]

    assert flexure["governing_combo"] == "GENERIC_BEAM_COMBO"
    assert flexure["combo_family"] is None
    assert flexure["evidence"]["governing_combo"] == "GENERIC_BEAM_COMBO"
    assert not ({"M_pos_case", "M_neg_left_case", "M_neg_right_case"} & set(flexure["evidence"]))

    assert shear["governing_combo"] == "GENERIC_BEAM_COMBO"
    assert shear["combo_family"] is None
    assert shear["evidence"]["governing_combo"] == "GENERIC_BEAM_COMBO"
    assert not ({"V_max_case", "V_at_support_case"} & set(shear["evidence"]))


def test_no_combo_family_proof_exists_for_beam_provenance_baseline():
    module = BeamDesignModule(FakeContext())
    forces = BeamForces(label="B1", governing_combo="GENERIC_BEAM_COMBO")

    assert not hasattr(forces, "combo_family")

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={
                "flexure": _fake_check(),
                "shear": _fake_check(),
            },
        )
    )

    assert output["checks"]["flexure"]["combo_family"] is None
    assert output["checks"]["shear"]["combo_family"] is None
    assert output["checks"]["flexure"]["combo_family"] != "S_E"
    assert output["checks"]["shear"]["combo_family"] != "K_E"
