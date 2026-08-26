from __future__ import annotations

import math

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.design.columns.column_shear_demand import (
    BLOCKED_D,
    BLOCKED_LN,
    BLOCKED_RS_CONCURRENCY,
    CAPACITY_PROVEN,
    SECTION_CAPACITY_UNIT_ADAPTER_REF,
    ColumnEndMomentCapacityBasis,
    ColumnShearDesignDemandInput,
    associated_moment_axis,
    evaluate_tbdy_737_column_shear_demand,
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
    evaluate_tbdy_7375_brittle_upper_bound,
    evaluate_ts500_815_web_compression_upper_bound,
    resolve_exact_rectangular_column_effective_depth,
)
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint
from tbdy_engine.design.columns.section_capacity import ColumnInteractionEnvelope, RadialMomentCapacity
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceError,
    build_column_shear_demand_evidence,
)
from tbdy_engine.product_reports.vs6_column_shear_p7_report import build_vs6_p7_column_shear_reports
from tbdy_engine.regulatory.contracts import PhysicalDimension
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from tbdy_engine.regulatory.units import Unit, UNIT_KN, UNIT_M, UNIT_MM, UNIT_N
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    ColumnShearVrClosureStatus,
    SourceBoundShearDemand,
    build_vs6_p7_column_shear_run,
    run_vs6_p7_direction,
)


def _capacity(end: str, direction: str, value_knm: float, sign: int = 1):
    return ColumnEndMomentCapacityBasis(
        component_id="C1",
        end_tag=end,
        direction=direction,
        moment_axis=associated_moment_axis(direction),
        moment_sign=sign,
        nd_compression_kn=500.0,
        capacity_knm=value_knm,
        status=CAPACITY_PROVEN,
        source_refs=(f"CAP:{end}:{direction}:{sign}",),
    )


def _demand_input(
    *,
    direction="V2",
    bottom_knm=120.0,
    top_knm=80.0,
    ln_mm=2_000.0,
    d_candidate_kn=90.0,
    vd_kn=60.0,
    rs_required=False,
    rs_proven=True,
):
    return ColumnShearDesignDemandInput(
        component_id="C1",
        direction=direction,
        free_length_ln_mm=ln_mm,
        free_length_basis_ref=None if ln_mm is None else "LN:STRICT",
        bottom_capacity=_capacity("BOTTOM", direction, bottom_knm),
        top_capacity=_capacity("TOP", direction, top_knm),
        d_amplified_candidate_kn=d_candidate_kn,
        d_amplified_basis_ref=None if d_candidate_kn is None else "D:REVIEWED",
        vd_floor_kn=vd_kn,
        vd_source_ref="VD:EXACT",
        response_spectrum_concurrency_required=rs_required,
        response_spectrum_concurrency_proven=rs_proven,
    )


def _bars():
    return (
        ColumnBarPoint(0, -150.0, -190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(1, 150.0, -190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(2, 150.0, 190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(3, -150.0, 190.0, 20.0, math.pi * 100.0),
    )


def _source_demand(value_kn: float, ref: str):
    return SourceBoundShearDemand(
        demand_kn=value_kn,
        source_identity=ref,
        output_case="COMB1",
        case_type="Combination",
        evidence_epoch_id="epoch:test",
        source_refs=(ref,),
    )


def _effective(direction="V2", sign=1):
    return resolve_exact_rectangular_column_effective_depth(
        component_id="C1",
        direction=direction,
        moment_sign=sign,
        width_mm=400.0,
        depth_mm=500.0,
        bars=_bars(),
        source_refs=("REBAR:SELECTED", "GEOM:RECT"),
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
        return RadialMomentCapacity(270.0, 123_000_000.0, 0.0, -123_000_000.0, "PROVEN")

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


def test_eq75_works_in_kn_knm_mm_and_d_candidate_can_govern():
    result = evaluate_tbdy_737_column_shear_demand(_demand_input())
    assert result.ve_capacity_eq75_kn == 100.0
    assert result.final_ve_kn == 90.0
    assert result.governing_rule == "TBDY_7_3_7_1_D_AMPLIFIED_CANDIDATE"


def test_eq75_capacity_candidate_can_govern():
    result = evaluate_tbdy_737_column_shear_demand(_demand_input(d_candidate_kn=150.0))
    assert result.final_ve_kn == 100.0
    assert result.governing_rule == "TBDY_7_3_7_1_EQ7_5"


def test_vd_floor_can_govern():
    result = evaluate_tbdy_737_column_shear_demand(_demand_input(vd_kn=95.0))
    assert result.final_ve_kn == 95.0
    assert result.governing_rule == "TBDY_7_3_7_5_VD_FLOOR"


def test_missing_d_authority_blocks_without_default():
    result = evaluate_tbdy_737_column_shear_demand(_demand_input(d_candidate_kn=None))
    assert result.status == BLOCKED_D
    assert result.final_ve_kn is None


def test_missing_ln_authority_blocks_without_length_fallback():
    result = evaluate_tbdy_737_column_shear_demand(_demand_input(ln_mm=None))
    assert result.status == BLOCKED_LN
    assert result.final_ve_kn is None


def test_response_spectrum_concurrency_blocks_when_unproven():
    result = evaluate_tbdy_737_column_shear_demand(
        _demand_input(rs_required=True, rs_proven=False)
    )
    assert result.status == BLOCKED_RS_CONCURRENCY
    assert result.final_ve_kn is None


def test_effective_depth_uses_selected_bar_coordinates_not_09h():
    v2 = _effective("V2", 1)
    assert v2.status == EFFECTIVE_DEPTH_PROVEN
    assert v2.effective_depth_d_mm == 350.0
    assert v2.web_width_bw_mm == 500.0
    assert v2.effective_depth_d_mm != pytest.approx(0.9 * 400.0)

    v3 = _effective("V3", 1)
    assert v3.effective_depth_d_mm == 440.0
    assert v3.web_width_bw_mm == 400.0
    assert v3.effective_depth_d_mm != pytest.approx(0.9 * 500.0)


def test_tbdy_brittle_upper_bound_returns_kn():
    aw_mm2 = 200_000.0
    fck_mpa = 25.0
    limit_kn = 0.85 * aw_mm2 * math.sqrt(fck_mpa) / 1000.0
    on = evaluate_tbdy_7375_brittle_upper_bound(
        component_id="C1", story="S1", section="C400x500", direction="V2",
        ve_kn=limit_kn, aw_mm2=aw_mm2, fck_mpa=fck_mpa, evidence=("x",),
    )
    above = evaluate_tbdy_7375_brittle_upper_bound(
        component_id="C1", story="S1", section="C400x500", direction="V2",
        ve_kn=limit_kn + 0.001, aw_mm2=aw_mm2, fck_mpa=fck_mpa, evidence=("x",),
    )
    assert on.status is CheckStatus.OK
    assert on.unit == "kN"
    assert on.limit == pytest.approx(limit_kn)
    assert above.status is CheckStatus.FAIL


def test_ts500_web_upper_bound_returns_kn():
    eff = _effective("V2", 1)
    fcd_mpa = 16.6666666667
    limit_kn = 0.22 * fcd_mpa * eff.web_width_bw_mm * eff.effective_depth_d_mm / 1000.0
    on = evaluate_ts500_815_web_compression_upper_bound(
        component_id="C1", story="S1", section="C400x500", direction="V2",
        vd_kn=limit_kn, fcd_mpa=fcd_mpa, effective_depth=eff, evidence=("x",),
    )
    above = evaluate_ts500_815_web_compression_upper_bound(
        component_id="C1", story="S1", section="C400x500", direction="V2",
        vd_kn=limit_kn + 0.001, fcd_mpa=fcd_mpa, effective_depth=eff, evidence=("x",),
    )
    assert on.status is CheckStatus.OK
    assert on.unit == "kN"
    assert on.limit == pytest.approx(limit_kn)
    assert above.status is CheckStatus.FAIL


def _run(*, tbdy_vd_kn=60.0, aw_mm2=200_000.0, d_candidate_kn=150.0):
    direction = "V2"
    return run_vs6_p7_direction(
        component_id="C1",
        story="S1",
        section="C400x500",
        direction=direction,
        tbdy_high_ductility_applies=True,
        ts500_rc_applies=True,
        free_length_ln_mm=2_000.0,
        free_length_basis_ref="LN:STRICT",
        bottom_capacity=_capacity("BOTTOM", direction, 120.0),
        top_capacity=_capacity("TOP", direction, 80.0),
        d_amplified_candidate_kn=d_candidate_kn,
        d_amplified_basis_ref="D:REVIEWED",
        tbdy_vd=_source_demand(tbdy_vd_kn, "VD:TBDY"),
        ts500_vd=_source_demand(50.0, "VD:TS500"),
        response_spectrum_concurrency_required=False,
        response_spectrum_concurrency_proven=True,
        aw_mm2=aw_mm2,
        aw_source_ref="AW:RECTANGULAR_SOURCE_BOUND",
        fck_mpa=25.0,
        fcd_mpa=16.6666666667,
        effective_depth=_effective(direction, 1),
    )


def test_tbdy_brittle_failure_preserves_reanalysis_required():
    run = _run(aw_mm2=10_000.0)
    assert run.tbdy_brittle_result.status is CheckStatus.FAIL
    assert run.analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED
    assert run.full_vr_closure_status is ColumnShearVrClosureStatus.BLOCKED_BY_TRANSVERSE_REBAR_SLICE


def test_upper_bound_ok_does_not_claim_full_shear_pass_and_report_projects_kn():
    direction = _run()
    assert direction.tbdy_brittle_result.status is CheckStatus.OK
    assert direction.ts500_web_result.status is CheckStatus.OK
    assert direction.ve_kn == 100.0
    assert direction.full_vr_closure_status is ColumnShearVrClosureStatus.BLOCKED_BY_TRANSVERSE_REBAR_SLICE
    run = build_vs6_p7_column_shear_run(component_id="C1", directions=(direction,))
    report = build_vs6_p7_column_shear_reports(run)[0]
    assert report.status == "PARTIAL"
    fields = {item.key: item for item in report.summary_fields}
    assert fields["Ve_kn"].unit == "kN"
    assert fields["bottom_capacity_knm"].unit == "kN*m"
    assert fields["effective_depth_d_mm"].unit == "mm"
    assert any("deferred to VS6-P8" in warning for warning in report.warnings)


def test_unproven_high_ductility_never_auto_applies_tbdy():
    direction = run_vs6_p7_direction(
        component_id="C1",
        story="S1",
        section="C400x500",
        direction="V2",
        tbdy_high_ductility_applies=None,
        ts500_rc_applies=True,
        free_length_ln_mm=2_000.0,
        free_length_basis_ref="LN:STRICT",
        bottom_capacity=_capacity("BOTTOM", "V2", 120.0),
        top_capacity=_capacity("TOP", "V2", 80.0),
        d_amplified_candidate_kn=150.0,
        d_amplified_basis_ref="D:REVIEWED",
        tbdy_vd=_source_demand(60.0, "VD:TBDY"),
        ts500_vd=_source_demand(50.0, "VD:TS500"),
        response_spectrum_concurrency_required=False,
        response_spectrum_concurrency_proven=True,
        aw_mm2=200_000.0,
        aw_source_ref="AW:RECTANGULAR_SOURCE_BOUND",
        fck_mpa=25.0,
        fcd_mpa=16.6666666667,
        effective_depth=_effective("V2", 1),
    )
    assert direction.demand.final_ve_kn is None
    assert direction.tbdy_brittle_result.status is CheckStatus.BLOCKED
    assert direction.ts500_web_result.status is CheckStatus.OK
