from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from tbdy_engine.design.beams.beam_module import BeamDesignModule
from tbdy_engine.design.columns.module import ColumnDesignModule
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


def _force_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "column": "C1",
                "story": "S1",
                "station_m": 0.0,
                "output_case": "CASE_P",
                "p_kn": 100.0,
                "v2_kn": 10.0,
                "v3_kn": 20.0,
                "m2_knm": 30.0,
                "m3_knm": 40.0,
            },
            {
                "column": "C1",
                "story": "S1",
                "station_m": 0.0,
                "output_case": "CASE_V2_M2_I",
                "p_kn": 50.0,
                "v2_kn": -90.0,
                "v3_kn": 30.0,
                "m2_knm": -120.0,
                "m3_knm": 45.0,
            },
            {
                "column": "C1",
                "story": "S1",
                "station_m": 5.0,
                "output_case": "CASE_V3_M3_J",
                "p_kn": 60.0,
                "v2_kn": 40.0,
                "v3_kn": -140.0,
                "m2_knm": 70.0,
                "m3_knm": -180.0,
            },
        ]
    )


def test_build_simple_envelope_preserves_component_cases():
    df_env, lookup = _build_simple_envelope(_force_rows(), ["column"])

    assert not df_env.empty
    assert "C1" in lookup

    row = lookup["C1"]

    assert row["P_max"] == 100.0
    assert row["P_case"] == "CASE_P"
    assert row["V2_max"] == -90.0
    assert row["V2_case"] == "CASE_V2_M2_I"
    assert row["V3_max"] == -140.0
    assert row["V3_case"] == "CASE_V3_M3_J"
    assert row["M2_max"] == -120.0
    assert row["M2_case"] == "CASE_V2_M2_I"
    assert row["M3_max"] == -180.0
    assert row["M3_case"] == "CASE_V3_M3_J"


def test_build_simple_envelope_preserves_end_station_cases():
    _df_env, lookup = _build_simple_envelope(_force_rows(), ["column"])

    row = lookup["C1"]

    assert row["M2_i"] == -120.0
    assert row["M2_i_case"] == "CASE_V2_M2_I"
    assert row["M3_i"] == 45.0
    assert row["M3_i_case"] == "CASE_V2_M2_I"
    assert row["V2_i"] == -90.0
    assert row["V2_i_case"] == "CASE_V2_M2_I"
    assert row["V3_i"] == 30.0
    assert row["V3_i_case"] == "CASE_V2_M2_I"

    assert row["M2_j"] == 70.0
    assert row["M2_j_case"] == "CASE_V3_M3_J"
    assert row["M3_j"] == -180.0
    assert row["M3_j_case"] == "CASE_V3_M3_J"
    assert row["V2_j"] == 40.0
    assert row["V2_j_case"] == "CASE_V3_M3_J"
    assert row["V3_j"] == -140.0
    assert row["V3_j_case"] == "CASE_V3_M3_J"

def test_column_resolve_forces_preserves_component_case_provenance():
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

    assert force.governing_combo == "CASE_P"
    assert force.N_kn == 100.0
    assert force.Mx_knm == 180.0
    assert force.My_knm == 120.0
    assert force.Vx_kn == 90.0
    assert force.Vy_kn == 140.0

    assert force.N_case == "CASE_P"
    assert force.Mx_case == "CASE_M3"
    assert force.My_case == "CASE_M2"
    assert force.Vx_case == "CASE_V2"
    assert force.Vy_case == "CASE_V3"
    assert not hasattr(force, "combo_family")


def test_beam_resolve_forces_does_not_consume_component_case_provenance():
    ctx = FakeContext(
        envelopes={
            "beam_forces_map": {
                "B1": {
                    "M_pos": 110.0,
                    "M_neg_left": 150.0,
                    "M_neg_right": 170.0,
                    "V_max": 95.0,
                    "V_support": 88.0,
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
            }
        }
    )

    forces = BeamDesignModule(ctx).resolve_forces()
    force = forces["B1"]

    assert force.M_pos_knm == 110.0
    assert force.M_neg_left_knm == 150.0
    assert force.M_neg_right_knm == 170.0
    assert force.V_max_kn == 95.0
    assert force.V_at_support_kn == 88.0
    assert force.governing_combo == ""

    for attr in [
        "M_pos_case",
        "M_neg_left_case",
        "M_neg_right_case",
        "V_max_case",
        "V_at_support_case",
        "combo_family",
    ]:
        assert not hasattr(force, attr)

    for component_case in [
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
    ]:
        assert force.governing_combo != component_case


def test_no_combo_family_proof_is_present_in_force_provenance_baseline():
    column_ctx = FakeContext(
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
    beam_ctx = FakeContext(
        envelopes={
            "beam_forces_map": {
                "B1": {
                    "M_pos": 110.0,
                    "M_neg_left": 150.0,
                    "M_neg_right": 170.0,
                    "V_max": 95.0,
                    "V_support": 88.0,
                    "combo": "COMBO_GENERIC",
                    "M2_case": "CASE_M2",
                    "V2_case": "CASE_V2",
                }
            }
        }
    )

    column_force = ColumnDesignModule(column_ctx).resolve_forces()["C1"]
    beam_force = BeamDesignModule(beam_ctx).resolve_forces()["B1"]

    assert not hasattr(column_force, "combo_family")
    assert not hasattr(beam_force, "combo_family")
    assert column_force.governing_combo == "CASE_P"
    assert beam_force.governing_combo == "COMBO_GENERIC"
