from __future__ import annotations

import math

import pytest

from tbdy_engine.design.columns.column_shear_demand import (
    CAPACITY_PROVEN,
    SECTION_CAPACITY_UNIT_ADAPTER_REF,
    associated_moment_axis,
    resolve_exact_column_end_moment_capacity,
)
from tbdy_engine.design.columns.column_shear_units import (
    ColumnShearUnitBoundaryError,
    SourceBoundScalar,
    force_to_kn,
    length_to_mm,
)
from tbdy_engine.design.columns.column_shear_upper_bounds import (
    EFFECTIVE_DEPTH_PROVEN,
    resolve_exact_rectangular_column_effective_depth,
)
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint
from tbdy_engine.design.columns.section_capacity import ColumnInteractionEnvelope, RadialMomentCapacity
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceError,
    build_column_shear_demand_evidence,
)
from tbdy_engine.regulatory.contracts import PhysicalDimension
from tbdy_engine.regulatory.units import Unit, UNIT_KN, UNIT_M, UNIT_MM, UNIT_N


def _bars():
    return (
        ColumnBarPoint(0, -150.0, -190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(1, 150.0, -190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(2, 150.0, 190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(3, -150.0, 190.0, 20.0, math.pi * 100.0),
    )


def _row(station: float, *, case="COMB1"):
    return {
        "Story": "S1",
        "Column": "C1",
        "UniqueName": "101",
        "OutputCase": case,
        "CaseType": "Combination",
        "StepType": "",
        "StepNumber": None,
        "Station": station,
        "Element": "501",
        "ElemStation": station,
        "V2": 12.5,
        "V3": -8.0,
    }


def test_unit_boundary_normalizes_force_to_kn_and_length_to_mm():
    assert force_to_kn(SourceBoundScalar(12.5, UNIT_KN, "ETABS:V2")) == 12.5
    assert force_to_kn(SourceBoundScalar(12_500.0, UNIT_N, "ETABS:V2")) == 12.5
    assert length_to_mm(SourceBoundScalar(2.4, UNIT_M, "ETABS:Station")) == 2_400.0
    assert length_to_mm(SourceBoundScalar(2400.0, UNIT_MM, "ETABS:Station")) == 2_400.0


def test_unknown_force_unit_fails_closed():
    unit_tf = Unit("tf", PhysicalDimension.FORCE)
    with pytest.raises(ColumnShearUnitBoundaryError):
        force_to_kn(SourceBoundScalar(1.0, unit_tf, "ETABS:V2"))


def test_factual_identity_preserves_station_and_duplicate_fails():
    bundle = build_column_shear_demand_evidence(
        model_fingerprint="model:1",
        rows=(_row(0.0), _row(3.0)),
        output_names=("COMB1",),
        force_unit=UNIT_KN,
        length_unit=UNIT_M,
        unit_provenance_refs=("GetPresentUnits_2",),
    )
    assert len(bundle.rows) == 2
    with pytest.raises(ColumnShearDemandEvidenceError, match="duplicate exact"):
        build_column_shear_demand_evidence(
            model_fingerprint="model:1",
            rows=(_row(0.0), _row(0.0)),
            output_names=("COMB1",),
            force_unit=UNIT_KN,
            length_unit=UNIT_M,
            unit_provenance_refs=("GetPresentUnits_2",),
        )


def test_wrong_output_case_cannot_enter_evidence():
    with pytest.raises(ColumnShearDemandEvidenceError, match="no exact rows"):
        build_column_shear_demand_evidence(
            model_fingerprint="model:1",
            rows=(_row(0.0, case="OTHER"),),
            output_names=("COMB1",),
            force_unit=UNIT_KN,
            length_unit=UNIT_M,
            unit_provenance_refs=("GetPresentUnits_2",),
        )


def test_local_axis_pairing_is_preserved():
    assert associated_moment_axis("V2") == "M3"
    assert associated_moment_axis("V3") == "M2"


def test_exact_capacity_wrapper_exposes_knm_while_reusing_frozen_145_kernel(monkeypatch):
    import tbdy_engine.design.columns.column_shear_demand as module

    observed = {}

    def fake_envelope(**kwargs):
        observed["target_n"] = kwargs["target_n_compression_n"]
        return ColumnInteractionEnvelope(
            target_n_compression_n=kwargs["target_n_compression_n"],
            states=(),
            status="PROVEN",
            angle_step_deg=5.0,
        )

    def fake_radial(envelope, *, demand_m2_nmm, demand_m3_nmm):
        observed["vector"] = (demand_m2_nmm, demand_m3_nmm)
        return RadialMomentCapacity(
            270.0, 123_000_000.0, 0.0, -123_000_000.0, "PROVEN"
        )

    monkeypatch.setattr(module, "build_interaction_envelope_at_axial_force", fake_envelope)
    monkeypatch.setattr(module, "radial_moment_capacity", fake_radial)

    result = resolve_exact_column_end_moment_capacity(
        component_id="C1",
        end_tag="BOTTOM",
        direction="V2",
        moment_sign=-1,
        nd_compression_kn=500.0,
        width_mm=400.0,
        depth_mm=500.0,
        bars=_bars(),
        material=object(),
        source_refs=("ND:STATE", "REBAR:SELECTED"),
    )
    assert result.status == CAPACITY_PROVEN
    assert result.capacity_knm == 123.0
    assert result.nd_compression_kn == 500.0
    assert observed["target_n"] == 500_000.0
    assert observed["vector"] == (0.0, -1.0)
    assert SECTION_CAPACITY_UNIT_ADAPTER_REF in result.source_refs


def test_effective_depth_uses_selected_bar_coordinates_not_09h():
    v2 = resolve_exact_rectangular_column_effective_depth(
        component_id="C1",
        direction="V2",
        moment_sign=1,
        width_mm=400.0,
        depth_mm=500.0,
        bars=_bars(),
        source_refs=("REBAR:SELECTED", "GEOM:RECT"),
    )
    assert v2.status == EFFECTIVE_DEPTH_PROVEN
    assert v2.effective_depth_d_mm == 350.0
    assert v2.web_width_bw_mm == 500.0
    assert v2.effective_depth_d_mm != pytest.approx(0.9 * 400.0)

    v3 = resolve_exact_rectangular_column_effective_depth(
        component_id="C1",
        direction="V3",
        moment_sign=1,
        width_mm=400.0,
        depth_mm=500.0,
        bars=_bars(),
        source_refs=("REBAR:SELECTED", "GEOM:RECT"),
    )
    assert v3.effective_depth_d_mm == 440.0
    assert v3.web_width_bw_mm == 400.0
    assert v3.effective_depth_d_mm != pytest.approx(0.9 * 500.0)
