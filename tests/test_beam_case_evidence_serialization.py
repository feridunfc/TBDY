from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tbdy_engine.design.beams.beam_module import BeamDesignModule, BeamForces
from tbdy_engine.engine.context_builder import (
    BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES,
    BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES,
    EnvKeys,
    _merge_beam_design_envelope_semantics,
)
from tests.test_beam_design_envelope_extraction import _b1_flexure_rows, _b1_shear_rows


@dataclass
class FakeContext:
    envelopes: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    design_metadata: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)


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


def _beam_map_with_cases() -> dict[str, dict[str, Any]]:
    return {
        "B1": {
            "M_pos": 80.8195,
            "M_pos_case": "CASE_M_POS",
            "M_neg_left": 109.7213,
            "M_neg_left_case": "CASE_M_LEFT",
            "M_neg_right": 130.3767,
            "M_neg_right_case": "CASE_M_RIGHT",
            "V_max": 129.1275,
            "V_max_case": "CASE_V_MAX",
            "V_support": 129.1275,
            "V_support_case": "CASE_V_SUPPORT",
            "T_max": 0.0,
            "T_max_case": None,
            "combo": "GENERIC_BEAM_COMBO",
        }
    }


def test_beam_forces_exposes_case_fields_from_beam_forces_map():
    ctx = FakeContext(envelopes={EnvKeys.BEAM_FORCES_MAP: _beam_map_with_cases()})

    force = BeamDesignModule(ctx).resolve_forces()["B1"]

    assert force.M_pos_knm == 80.8195
    assert force.M_pos_case == "CASE_M_POS"
    assert force.M_neg_left_case == "CASE_M_LEFT"
    assert force.M_neg_right_case == "CASE_M_RIGHT"
    assert force.V_max_case == "CASE_V_MAX"
    assert force.V_at_support_case == "CASE_V_SUPPORT"
    assert force.T_max_case == ""
    assert force.governing_combo == "GENERIC_BEAM_COMBO"
    assert not hasattr(force, "combo_family")


def test_beam_forces_missing_case_fields_remain_empty_strings():
    ctx = FakeContext(
        envelopes={
            EnvKeys.BEAM_FORCES_MAP: {
                "B1": {
                    "M_pos": 80.8195,
                    "M_neg_left": 109.7213,
                    "M_neg_right": 130.3767,
                    "V_max": 129.1275,
                    "V_support": 129.1275,
                    "T_max": 0.0,
                }
            }
        }
    )

    force = BeamDesignModule(ctx).resolve_forces()["B1"]

    assert force.M_pos_case == ""
    assert force.M_neg_left_case == ""
    assert force.M_neg_right_case == ""
    assert force.V_max_case == ""
    assert force.V_at_support_case == ""
    assert force.T_max_case == ""
    assert not hasattr(force, "combo_family")


def test_flexure_output_evidence_includes_component_moment_cases_and_preserves_generic_governing_combo():
    module = BeamDesignModule(FakeContext())
    forces = BeamForces(
        label="B1",
        M_pos_knm=80.8195,
        M_neg_left_knm=109.7213,
        M_neg_right_knm=130.3767,
        V_max_kn=129.1275,
        V_at_support_kn=129.1275,
        T_max_knm=0.0,
        governing_combo="GENERIC_BEAM_COMBO",
        M_pos_case="CASE_M_POS",
        M_neg_left_case="CASE_M_LEFT",
        M_neg_right_case="CASE_M_RIGHT",
    )

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={"flexure": _fake_check(ratio=0.76, value=0.76, limit=1.0)},
        )
    )

    flexure = output["checks"]["flexure"]
    evidence_forces = flexure["evidence"]["forces"]

    assert flexure["governing_combo"] == "GENERIC_BEAM_COMBO"
    assert flexure["combo_family"] is None
    assert evidence_forces["M_pos_case"] == "CASE_M_POS"
    assert evidence_forces["M_neg_left_case"] == "CASE_M_LEFT"
    assert evidence_forces["M_neg_right_case"] == "CASE_M_RIGHT"
    assert flexure["evidence"]["governing_combo"] == "GENERIC_BEAM_COMBO"


def test_shear_output_evidence_includes_component_shear_cases_and_preserves_generic_governing_combo():
    module = BeamDesignModule(FakeContext())
    forces = BeamForces(
        label="B1",
        M_pos_knm=80.8195,
        M_neg_left_knm=109.7213,
        M_neg_right_knm=130.3767,
        V_max_kn=129.1275,
        V_at_support_kn=129.1275,
        T_max_knm=0.0,
        governing_combo="GENERIC_BEAM_COMBO",
        V_max_case="CASE_V_MAX",
        V_at_support_case="CASE_V_SUPPORT",
    )

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={"shear": _fake_check(ratio=0.69, value=129.1275, limit=200.0, unit="kN")},
        )
    )

    shear = output["checks"]["shear"]
    evidence_forces = shear["evidence"]["forces"]

    assert shear["governing_combo"] == "GENERIC_BEAM_COMBO"
    assert shear["combo_family"] is None
    assert evidence_forces["V_max_case"] == "CASE_V_MAX"
    assert evidence_forces["V_at_support_case"] == "CASE_V_SUPPORT"
    assert shear["evidence"]["governing_combo"] == "GENERIC_BEAM_COMBO"


def test_component_cases_do_not_become_generic_governing_combo():
    module = BeamDesignModule(FakeContext())
    forces = BeamForces(
        label="B1",
        M_pos_knm=80.8195,
        M_neg_left_knm=109.7213,
        M_neg_right_knm=130.3767,
        V_max_kn=129.1275,
        V_at_support_kn=129.1275,
        T_max_knm=0.0,
        governing_combo="",
        M_pos_case="CASE_M_POS",
        V_max_case="CASE_V_MAX",
    )

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={
                "flexure": _fake_check(),
                "shear": _fake_check(),
            },
        )
    )

    flexure = output["checks"]["flexure"]
    shear = output["checks"]["shear"]

    assert flexure["governing_combo"] is None
    assert shear["governing_combo"] is None
    assert flexure["evidence"]["governing_combo"] is None
    assert shear["evidence"]["governing_combo"] is None
    assert flexure["evidence"]["forces"]["M_pos_case"] == "CASE_M_POS"
    assert shear["evidence"]["forces"]["V_max_case"] == "CASE_V_MAX"


def test_integration_with_sprint_3k6_semantic_map_populates_beam_case_fields():
    ctx = FakeContext(
        envelopes={EnvKeys.BEAM_FORCES_MAP: {}},
        tables={
            BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES[0]: _b1_flexure_rows(),
            BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES[0]: _b1_shear_rows(),
        },
        notes={"data_gaps": []},
    )

    _merge_beam_design_envelope_semantics(ctx)

    force = BeamDesignModule(ctx).resolve_forces()["B1"]

    assert force.M_pos_knm == 80.8195
    assert force.M_pos_case == "Crack_SeisX"
    assert force.M_neg_left_case == "Crack_SeisX_Soil"
    assert force.M_neg_right_case == "Crack_SeisX"
    assert force.V_max_case == "Crack_SeisY_Soil"
    assert force.V_at_support_case == "Crack_SeisY_Soil"
    assert not hasattr(force, "combo_family")


def test_no_combo_family_inference_for_beam_case_evidence():
    module = BeamDesignModule(FakeContext())
    forces = BeamForces(
        label="B1",
        governing_combo="GENERIC_BEAM_COMBO",
        M_pos_case="CASE_M_POS",
        V_max_case="CASE_V_MAX",
    )

    output = module._output_to_dict(
        _fake_output(
            forces=forces,
            checks={
                "flexure": _fake_check(),
                "shear": _fake_check(),
            },
        )
    )

    assert not hasattr(forces, "combo_family")
    assert output["checks"]["flexure"]["combo_family"] is None
    assert output["checks"]["shear"]["combo_family"] is None
    assert "uses_combo" not in output["checks"]["flexure"]
    assert "uses_combo" not in output["checks"]["shear"]