from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from tbdy_engine.design.beams.beam_module import BeamDesignModule


BEAM_FLEXURE_ENVELOPE_TABLE = "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)"
BEAM_SHEAR_ENVELOPE_TABLE = "Concrete Beam Shear Envelope -  TS 500-2000(R2018)"


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label(row: pd.Series) -> str:
    return _text(row.get("Label") or row.get("Beam") or row.get("label") or row.get("beam"))


def _location(row: pd.Series) -> str:
    return _text(row.get("Location") or row.get("location"))


def _update_if_abs_greater(out: dict[str, Any], value_key: str, case_key: str, value: Any, case: Any) -> None:
    candidate = abs(_safe_float(value))
    current = abs(_safe_float(out.get(value_key), 0.0))
    if candidate > current:
        out[value_key] = candidate
        out[case_key] = _text(case) or None


def _empty_semantic_force() -> dict[str, Any]:
    return {
        "M_pos": 0.0,
        "M_pos_case": None,
        "M_neg_left": 0.0,
        "M_neg_left_case": None,
        "M_neg_right": 0.0,
        "M_neg_right_case": None,
        "V_max": 0.0,
        "V_max_case": None,
        "V_support": 0.0,
        "V_support_case": None,
        "T_max": 0.0,
        "T_max_case": None,
    }


def _build_beam_semantic_forces_from_design_envelopes(
    flexure_rows: pd.DataFrame,
    shear_rows: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    for _, row in flexure_rows.iterrows():
        beam = _label(row)
        if not beam:
            continue
        target = out.setdefault(beam, _empty_semantic_force())
        location = _location(row)
        if location == "End-I":
            _update_if_abs_greater(target, "M_neg_left", "M_neg_left_case", row.get("MomentTop"), row.get("AsTopCombo"))
        elif location == "Middle":
            _update_if_abs_greater(target, "M_pos", "M_pos_case", row.get("MomentBot"), row.get("AsBotCombo"))
        elif location == "End-J":
            _update_if_abs_greater(target, "M_neg_right", "M_neg_right_case", row.get("MomentTop"), row.get("AsTopCombo"))

    for _, row in shear_rows.iterrows():
        beam = _label(row)
        if not beam:
            continue
        target = out.setdefault(beam, _empty_semantic_force())
        location = _location(row)
        _update_if_abs_greater(target, "V_max", "V_max_case", row.get("Shear"), row.get("VCombo"))
        if location in {"End-I", "End-J"}:
            _update_if_abs_greater(target, "V_support", "V_support_case", row.get("Shear"), row.get("VCombo"))

    return out


def _b1_flexure_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "End-I",
                "AsTopCombo": "Crack_SeisX_Soil",
                "MomentTop": -109.7213,
                "AsTop": 10.0,
                "AsBotCombo": "Crack_SeisX",
                "MomentBot": 68.473,
                "AsBot": 8.0,
                "Status": "OK",
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "Middle",
                "AsTopCombo": "Crack_SeisX",
                "MomentTop": -32.5942,
                "AsTop": 4.0,
                "AsBotCombo": "Crack_SeisX",
                "MomentBot": 80.8195,
                "AsBot": 9.0,
                "Status": "OK",
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "End-J",
                "AsTopCombo": "Crack_SeisX",
                "MomentTop": -130.3767,
                "AsTop": 11.0,
                "AsBotCombo": "Crack_SeisX_Soil",
                "MomentBot": 65.1417,
                "AsBot": 7.0,
                "Status": "OK",
            },
        ]
    )


def _b1_shear_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "End-I",
                "VCombo": "Crack_SeisY_Soil",
                "Shear": 129.1275,
                "VTorsion": 0.0,
                "VRebar": 8.0,
                "TTrnCombo": "",
                "TTrnTorsion": 0.0,
                "TTrnRebar": 0.0,
                "TLngCombo": "",
                "TLngTorsion": 0.0,
                "TLngRebar": 0.0,
                "Status": "OK",
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "Middle",
                "VCombo": "Crack_SeisY_Soil",
                "Shear": 92.187,
                "VTorsion": 0.0,
                "VRebar": 6.0,
                "TTrnCombo": "",
                "TTrnTorsion": 0.0,
                "TTrnRebar": 0.0,
                "TLngCombo": "",
                "TLngTorsion": 0.0,
                "TLngRebar": 0.0,
                "Status": "OK",
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "End-J",
                "VCombo": "Crack_SeisY_Soil",
                "Shear": 123.2144,
                "VTorsion": 0.0,
                "VRebar": 7.0,
                "TTrnCombo": "",
                "TTrnTorsion": 0.0,
                "TTrnRebar": 0.0,
                "TLngCombo": "",
                "TLngTorsion": 0.0,
                "TLngRebar": 0.0,
                "Status": "OK",
            },
        ]
    )


def test_flexure_envelope_maps_b1_example_correctly():
    mapped = _build_beam_semantic_forces_from_design_envelopes(_b1_flexure_rows(), pd.DataFrame())
    b1 = mapped["B1"]

    assert b1["M_neg_left"] == 109.7213
    assert b1["M_neg_left_case"] == "Crack_SeisX_Soil"
    assert b1["M_pos"] == 80.8195
    assert b1["M_pos_case"] == "Crack_SeisX"
    assert b1["M_neg_right"] == 130.3767
    assert b1["M_neg_right_case"] == "Crack_SeisX"


def test_shear_envelope_maps_b1_example_correctly():
    mapped = _build_beam_semantic_forces_from_design_envelopes(pd.DataFrame(), _b1_shear_rows())
    b1 = mapped["B1"]

    assert b1["V_max"] == 129.1275
    assert b1["V_max_case"] == "Crack_SeisY_Soil"
    assert b1["V_support"] == 129.1275
    assert b1["V_support_case"] == "Crack_SeisY_Soil"


def test_duplicate_location_rows_choose_max_abs_and_preserve_winning_case():
    flexure = pd.DataFrame(
        [
            {"Label": "B1", "Location": "Middle", "MomentBot": 50.0, "AsBotCombo": "MIDDLE_LOW"},
            {"Label": "B1", "Location": "Middle", "MomentBot": -95.0, "AsBotCombo": "MIDDLE_WIN"},
            {"Label": "B1", "Location": "End-I", "MomentTop": -80.0, "AsTopCombo": "END_I_LOW"},
            {"Label": "B1", "Location": "End-I", "MomentTop": -110.0, "AsTopCombo": "END_I_WIN"},
        ]
    )
    shear = pd.DataFrame(
        [
            {"Label": "B1", "Location": "End-J", "Shear": 60.0, "VCombo": "SHEAR_LOW"},
            {"Label": "B1", "Location": "End-J", "Shear": -140.0, "VCombo": "SHEAR_WIN"},
        ]
    )

    mapped = _build_beam_semantic_forces_from_design_envelopes(flexure, shear)
    b1 = mapped["B1"]

    assert b1["M_pos"] == 95.0
    assert b1["M_pos_case"] == "MIDDLE_WIN"
    assert b1["M_neg_left"] == 110.0
    assert b1["M_neg_left_case"] == "END_I_WIN"
    assert b1["V_max"] == 140.0
    assert b1["V_max_case"] == "SHEAR_WIN"
    assert b1["V_support"] == 140.0
    assert b1["V_support_case"] == "SHEAR_WIN"


def test_missing_middle_flexure_row_leaves_m_pos_zero_without_inference():
    flexure = pd.DataFrame(
        [
            {"Label": "B1", "Location": "End-I", "MomentTop": -109.7213, "AsTopCombo": "Crack_SeisX_Soil"},
            {"Label": "B1", "Location": "End-J", "MomentTop": -130.3767, "AsTopCombo": "Crack_SeisX"},
        ]
    )

    mapped = _build_beam_semantic_forces_from_design_envelopes(flexure, pd.DataFrame())
    b1 = mapped["B1"]

    assert b1["M_neg_left"] == 109.7213
    assert b1["M_neg_right"] == 130.3767
    assert b1["M_pos"] == 0.0
    assert b1["M_pos_case"] is None


def test_no_combo_family_is_produced_by_design_envelope_mapping():
    mapped = _build_beam_semantic_forces_from_design_envelopes(_b1_flexure_rows(), _b1_shear_rows())

    assert "combo_family" not in mapped["B1"]


def test_current_beam_design_module_does_not_consume_raw_design_envelope_fields_automatically():
    ctx = FakeContext(
        envelopes={
            "beam_forces_map": {
                "B1": {
                    "Location": "End-I",
                    "MomentTop": -109.7213,
                    "AsTopCombo": "Crack_SeisX_Soil",
                    "MomentBot": 68.473,
                    "AsBotCombo": "Crack_SeisX",
                    "Shear": 129.1275,
                    "VCombo": "Crack_SeisY_Soil",
                }
            }
        }
    )

    force = BeamDesignModule(ctx).resolve_forces()["B1"]

    assert force.M_pos_knm == 0.0
    assert force.M_neg_left_knm == 0.0
    assert force.M_neg_right_knm == 0.0
    assert force.V_max_kn == 0.0
    assert force.V_at_support_kn == 0.0
    assert force.governing_combo == ""


def test_double_space_beam_design_envelope_table_names_are_documented():
    assert " -  TS " in BEAM_FLEXURE_ENVELOPE_TABLE
    assert " -  TS " in BEAM_SHEAR_ENVELOPE_TABLE
    assert BEAM_FLEXURE_ENVELOPE_TABLE == "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)"
    assert BEAM_SHEAR_ENVELOPE_TABLE == "Concrete Beam Shear Envelope -  TS 500-2000(R2018)"


def test_torsion_semantic_mapping_is_deferred():
    mapped = _build_beam_semantic_forces_from_design_envelopes(_b1_flexure_rows(), _b1_shear_rows())
    b1 = mapped["B1"]

    assert b1["T_max"] == 0.0
    assert b1["T_max_case"] is None
