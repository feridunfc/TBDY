from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from tbdy_engine.design.beams.beam_module import BeamDesignModule
from tbdy_engine.engine.context_builder import (
    BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES,
    BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES,
    EnvKeys,
    _build_beam_design_envelope_semantic_map,
    _get_first_nonempty_table,
    _merge_beam_design_envelope_semantics,
)


@dataclass
class FakeContext:
    envelopes: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    design_metadata: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)


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
                "AsBotCombo": "Crack_SeisX",
                "MomentBot": 68.473,
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "Middle",
                "AsTopCombo": "Crack_SeisX",
                "MomentTop": -32.5942,
                "AsBotCombo": "Crack_SeisX",
                "MomentBot": 80.8195,
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "End-J",
                "AsTopCombo": "Crack_SeisX",
                "MomentTop": -130.3767,
                "AsBotCombo": "Crack_SeisX_Soil",
                "MomentBot": 65.1417,
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
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "Middle",
                "VCombo": "Crack_SeisY_Soil",
                "Shear": 92.187,
            },
            {
                "Story": "S1",
                "Label": "B1",
                "UniqueName": "297",
                "DesignSect": "B30x60",
                "Location": "End-J",
                "VCombo": "Crack_SeisY_Soil",
                "Shear": 123.2144,
            },
        ]
    )


def test_beam_design_envelope_helper_maps_flexure_and_shear_rows_exactly():
    mapped = _build_beam_design_envelope_semantic_map(
        _b1_flexure_rows(),
        _b1_shear_rows(),
    )

    b1 = mapped["B1"]

    assert b1["M_neg_left"] == 109.7213
    assert b1["M_neg_left_case"] == "Crack_SeisX_Soil"
    assert b1["M_pos"] == 80.8195
    assert b1["M_pos_case"] == "Crack_SeisX"
    assert b1["M_neg_right"] == 130.3767
    assert b1["M_neg_right_case"] == "Crack_SeisX"

    assert b1["V_max"] == 129.1275
    assert b1["V_max_case"] == "Crack_SeisY_Soil"
    assert b1["V_support"] == 129.1275
    assert b1["V_support_case"] == "Crack_SeisY_Soil"

    assert b1["T_max"] == 0.0
    assert b1["T_max_case"] is None
    assert "combo_family" not in b1


def test_beam_design_envelope_helper_duplicate_rows_choose_max_abs_and_winning_case():
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

    b1 = _build_beam_design_envelope_semantic_map(flexure, shear)["B1"]

    assert b1["M_pos"] == 95.0
    assert b1["M_pos_case"] == "MIDDLE_WIN"
    assert b1["M_neg_left"] == 110.0
    assert b1["M_neg_left_case"] == "END_I_WIN"
    assert b1["V_max"] == 140.0
    assert b1["V_max_case"] == "SHEAR_WIN"
    assert b1["V_support"] == 140.0
    assert b1["V_support_case"] == "SHEAR_WIN"


def test_beam_design_envelope_helper_missing_middle_gives_zero_and_none_case():
    flexure = pd.DataFrame(
        [
            {"Label": "B1", "Location": "End-I", "MomentTop": -109.7213, "AsTopCombo": "Crack_SeisX_Soil"},
            {"Label": "B1", "Location": "End-J", "MomentTop": -130.3767, "AsTopCombo": "Crack_SeisX"},
        ]
    )

    b1 = _build_beam_design_envelope_semantic_map(flexure, pd.DataFrame())["B1"]

    assert b1["M_neg_left"] == 109.7213
    assert b1["M_neg_right"] == 130.3767
    assert b1["M_pos"] == 0.0
    assert b1["M_pos_case"] is None


def test_get_first_nonempty_table_prefers_two_space_table_name():
    two_space = BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES[0]
    one_space = BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES[1]

    tables = {
        one_space: pd.DataFrame([{"Label": "B_ONE"}]),
        two_space: pd.DataFrame([{"Label": "B_TWO"}]),
    }

    selected = _get_first_nonempty_table(tables, BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES)

    assert selected is tables[two_space]
    assert selected.iloc[0]["Label"] == "B_TWO"


def test_merge_beam_design_envelope_semantics_preserves_existing_beam_forces_keys():
    ctx = FakeContext(
        envelopes={
            EnvKeys.BEAM_FORCES_MAP: {
                "B1": {
                    "combo": "GENERIC_BEAM_COMBO",
                    "custom": 123,
                }
            }
        },
        tables={
            BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES[0]: _b1_flexure_rows(),
            BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES[0]: _b1_shear_rows(),
        },
        notes={"data_gaps": []},
    )

    _merge_beam_design_envelope_semantics(ctx)

    b1 = ctx.envelopes[EnvKeys.BEAM_FORCES_MAP]["B1"]

    assert b1["combo"] == "GENERIC_BEAM_COMBO"
    assert b1["custom"] == 123
    assert b1["M_pos"] == 80.8195
    assert b1["M_pos_case"] == "Crack_SeisX"
    assert b1["V_support"] == 129.1275
    assert b1["V_support_case"] == "Crack_SeisY_Soil"
    assert "combo_family" not in b1


def test_beam_design_module_consumes_semantic_values_after_map_population():
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
    assert force.M_neg_left_knm == 109.7213
    assert force.M_neg_right_knm == 130.3767
    assert force.V_max_kn == 129.1275
    assert force.V_at_support_kn == 129.1275
    assert force.T_max_knm == 0.0

    assert force.M_pos_case == "Crack_SeisX"
    assert force.M_neg_left_case == "Crack_SeisX_Soil"
    assert force.M_neg_right_case == "Crack_SeisX"
    assert force.V_max_case == "Crack_SeisY_Soil"
    assert force.V_at_support_case == "Crack_SeisY_Soil"
    assert force.T_max_case == ""
    assert not hasattr(force, "combo_family")


def test_merge_beam_design_envelope_semantics_generates_no_combo_family():
    ctx = FakeContext(
        envelopes={EnvKeys.BEAM_FORCES_MAP: {}},
        tables={
            BEAM_FLEXURE_ENVELOPE_TABLE_CANDIDATES[0]: _b1_flexure_rows(),
            BEAM_SHEAR_ENVELOPE_TABLE_CANDIDATES[0]: _b1_shear_rows(),
        },
        notes={"data_gaps": []},
    )

    _merge_beam_design_envelope_semantics(ctx)

    assert "combo_family" not in ctx.envelopes[EnvKeys.BEAM_FORCES_MAP]["B1"]