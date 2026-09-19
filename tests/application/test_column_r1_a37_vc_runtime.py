from __future__ import annotations

from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_vc_runtime as subject
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.features.column_shear_demand_evidence import (
    build_column_shear_demand_evidence,
    column_shear_source_identity,
)
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    ShortColumnTransverseFacts,
    TransverseDirectionFacts,
)
from tbdy_engine.regulatory.units import UNIT_KN, UNIT_M

COMPONENT = "S1:C1:101"


def _state(state_id, nd):
    return ColumnDemandState(
        state_id=state_id,
        component_id=COMPONENT,
        output_case="COMB",
        case_type="Combination",
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=nd,
        m2_nmm=0.0,
        m3_nmm=0.0,
        source_identity=f"SOURCE:{state_id}",
    )


def _row(case, v2, v3):
    return {
        "Story": "S1", "Column": "C1", "UniqueName": "101",
        "OutputCase": case, "CaseType": "Combination", "StepType": "",
        "StepNumber": None, "Station": 0.0, "Element": case, "ElemStation": 0.0,
        "P": -300.0, "V2": v2, "V3": v3, "T": 0.0, "M2": 0.0, "M3": 0.0,
    }


def _bundle():
    return build_column_shear_demand_evidence(
        model_fingerprint="model:a37",
        rows=(_row("EQ_ONLY", 60.0, 70.0), _row("TOTAL", 100.0, 120.0)),
        output_names=("EQ_ONLY", "TOTAL"),
        force_unit=UNIT_KN,
        length_unit=UNIT_M,
        unit_provenance_refs=("UNIT:PROOF",),
    )


def _request(high):
    return ColumnTransverseConfinementInput(
        component_id=COMPONENT, story="S1", section="C1",
        high_ductility_applies=high, limited_ductility_applies=not high,
        cantilever_column=False, clear_height_mm=3000.0, width_mm=500.0,
        depth_mm=600.0, gross_area_ac_mm2=300000.0,
        confined_core_area_ack_mm2=240000.0, fck_mpa=30.0, fywk_mpa=420.0,
        axial_design_force_nd_n=300000.0, transverse_diameter_mm=10.0,
        confinement_spacing_mm=100.0, middle_spacing_mm=150.0,
        provided_confinement_region_length_mm=650.0,
        directions=(
            TransverseDirectionFacts(
                direction="DIR2", confined_core_width_bk_mm=410.0,
                provided_ash_mm2=None, horizontal_leg_spacing_mm=180.0,
                source_refs=("DIR2",), provided_asw_mm2=157.0,
                effective_depth_mm=450.0, shear_mapping_proven=True, p7_ve_kn=120.0,
            ),
            TransverseDirectionFacts(
                direction="DIR3", confined_core_width_bk_mm=510.0,
                provided_ash_mm2=None, horizontal_leg_spacing_mm=190.0,
                source_refs=("DIR3",), provided_asw_mm2=314.0,
                effective_depth_mm=520.0, shear_mapping_proven=True, p7_ve_kn=130.0,
            ),
        ),
        arrangement=None, source_refs=("BASE",), fywd_mpa=365.0,
        restrained_longitudinal_bar_spacing_mm=250.0, shear_spacing_mm=100.0,
        model_fingerprint="model:a37", evidence_epoch_id="epoch:a37",
        design_result_ref="design:a37",
    )


def _fake_p7(monkeypatch):
    def one(direction, bw, d):
        return SimpleNamespace(
            direction=direction,
            effective_depth=SimpleNamespace(
                resolved=True,
                web_width_bw_mm=bw,
                effective_depth_d_mm=d,
                source_refs=(f"P7:{direction}:D",),
            ),
        )
    run = SimpleNamespace(
        component_id=COMPONENT,
        directions=(one("V2", 600.0, 450.0), one("V3", 500.0, 520.0)),
    )
    monkeypatch.setattr(subject, "VS6P7ColumnShearRun", type(run))
    return run


def test_high_vc_runtime_uses_exact_reviewed_states_and_rows(monkeypatch):
    evidence = _bundle()
    eq_id = column_shear_source_identity(next(x for x in evidence.rows if x["OutputCase"] == "EQ_ONLY"))
    total_id = column_shear_source_identity(next(x for x in evidence.rows if x["OutputCase"] == "TOTAL"))
    reviewed = subject.ReviewedColumnVcRuntimeContext(
        component_id=COMPONENT,
        high_directions=tuple(
            subject.ReviewedHighColumnVcDirectionPlan(
                component_id=COMPONENT,
                direction=direction,
                ts500_axial_state_id="TS500",
                suppression_axial_state_id="SUPPRESS",
                earthquake_only_source_identity=eq_id,
                total_seismic_source_identity=total_id,
                suppression_concurrency_proven=True,
                review_refs=(f"REVIEW:{direction}",),
            )
            for direction in ("V2", "V3")
        ),
        review_refs=("REVIEW:VC",),
    )
    result = subject.apply_reviewed_vc_to_transverse_input(
        _request(True),
        reviewed=reviewed,
        a23_states=(_state("TS500", 300000.0), _state("SUPPRESS", 300000.0)),
        shear_evidence=evidence,
        p7_run=_fake_p7(monkeypatch),
        fcd_mpa=20.0,
        target_unique_name="101",
        material_source_refs=("MAT:FCD",),
    )
    by_dir = {x.direction: x for x in result.directions}
    assert by_dir["DIR2"].qualified_vc_kn == pytest.approx(0.0)
    assert by_dir["DIR3"].qualified_vc_kn == pytest.approx(0.0)
    assert by_dir["DIR2"].provided_asw_mm2 == pytest.approx(157.0)
    assert by_dir["DIR3"].provided_asw_mm2 == pytest.approx(314.0)


def test_limited_vc_minimum_nd_only_inside_reviewed_scope(monkeypatch):
    from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
    from tbdy_engine.design.columns.column_shear_upper_bounds import (
        ColumnEffectiveDepthResolution,
        EFFECTIVE_DEPTH_PROVEN,
    )
    from tbdy_engine.regulatory.column_shear_limited_program import (
        LimitedColumnShearDirectionRun,
        LimitedColumnShearRun,
    )
    from tbdy_engine.regulatory.vs6_column_shear_p7_program import SourceBoundShearDemand

    evidence = _bundle()
    reviewed = subject.ReviewedColumnVcRuntimeContext(
        component_id=COMPONENT,
        limited_directions=tuple(
            subject.ReviewedLimitedColumnVcDirectionPlan(
                component_id=COMPONENT,
                direction=direction,
                vertical_plus_earthquake_state_ids=("N500", "N200", "N350"),
                review_refs=(f"REVIEW:LD:{direction}",),
            )
            for direction in ("V2", "V3")
        ),
        review_refs=("REVIEW:VC:LD",),
    )

    def check(direction):
        return CheckResult(
            check_id=f"TEST:{direction}",
            component=COMPONENT,
            component_type="column",
            story="S1",
            section="C1",
            status=CheckStatus.OK,
            value=100.0,
            limit=200.0,
            demand=100.0,
            capacity=200.0,
            ratio=0.5,
            ratio_type="demand_over_capacity",
            pass_rule="test fixture",
            unit="kN",
            evaluation_level=EvaluationLevel.DESIGN_LEVEL,
            evidence=(f"TEST:{direction}:CHECK",),
            messages=("OK",),
            code_ref="TEST",
            diagnostics=(),
        )

    def direction(local, bw, d, vd):
        effective = ColumnEffectiveDepthResolution(
            component_id=COMPONENT,
            direction=local,
            moment_axis="M3" if local == "V2" else "M2",
            moment_sign=1,
            effective_depth_d_mm=d,
            web_width_bw_mm=bw,
            tension_bar_coordinate_mm=0.0,
            status=EFFECTIVE_DEPTH_PROVEN,
            source_refs=(f"LD:{local}:D",),
        )
        demand = SourceBoundShearDemand(
            demand_kn=vd,
            source_identity=f"LD:{local}:ROW",
            output_case="LD_D_COMB",
            case_type="Combination",
            evidence_epoch_id="epoch:a37",
            source_refs=(f"LD:{local}:VD",),
        )
        return LimitedColumnShearDirectionRun(
            component_id=COMPONENT,
            story="S1",
            section="C1",
            direction=local,
            vd=demand,
            effective_depth=effective,
            tbdy_brittle_result=check(local),
            ts500_web_result=check(local),
            source_refs=(f"LD:{local}",),
        )

    limited_run = LimitedColumnShearRun(
        component_id=COMPONENT,
        directions=(
            direction("V2", 600.0, 450.0, 120.0),
            direction("V3", 500.0, 520.0, 130.0),
        ),
    )

    captured = []
    real = subject.qualify_column_vc

    def wrapped(**kwargs):
        captured.append(kwargs["ts500_axial_nd_signed_compression_n"])
        return real(**kwargs)

    monkeypatch.setattr(subject, "qualify_column_vc", wrapped)

    request = _request(False)
    request = replace(
        request,
        directions=tuple(
            replace(item, p7_ve_kn=None)
            for item in request.directions
        ),
    )
    result = subject.apply_reviewed_vc_to_transverse_input(
        request,
        reviewed=reviewed,
        a23_states=(
            _state("N500", 500000.0),
            _state("N200", 200000.0),
            _state("N350", 350000.0),
            _state("OUTSIDE", 100000.0),
        ),
        shear_evidence=evidence,
        p7_run=None,
        limited_run=limited_run,
        fcd_mpa=20.0,
        target_unique_name="101",
        material_source_refs=("MAT:FCD",),
    )
    assert captured == [200000.0, 200000.0]
    assert all(x.qualified_vc_kn is not None for x in result.directions)



def test_vc_context_not_in_request_dtos():
    forbidden = {"reviewed_column_vc_context", "qualified_vc_kn", "ts500_axial_state_id"}
    assert forbidden.isdisjoint({x.name for x in fields(ColumnExecutionRequest)})
    assert forbidden.isdisjoint({x.name for x in fields(ProjectExecutionRequest)})

def test_limited_short_vc_keeps_minimum_nd_but_uses_short_p7_geometry(monkeypatch):
    evidence = _bundle()
    reviewed = subject.ReviewedColumnVcRuntimeContext(
        component_id=COMPONENT,
        limited_directions=tuple(
            subject.ReviewedLimitedColumnVcDirectionPlan(
                component_id=COMPONENT,
                direction=direction,
                vertical_plus_earthquake_state_ids=("N500", "N200", "N350"),
                review_refs=(f"REVIEW:SHORT:LD:{direction}",),
            )
            for direction in ("V2", "V3")
        ),
        review_refs=("REVIEW:VC:SHORT:LD",),
    )
    captured = []
    real = subject.qualify_column_vc
    def wrapped(**kwargs):
        captured.append(kwargs["ts500_axial_nd_signed_compression_n"])
        return real(**kwargs)
    monkeypatch.setattr(subject, "qualify_column_vc", wrapped)
    request = replace(
        _request(False),
        short_column=ShortColumnTransverseFacts(
            applies=True,
            actual_short_free_length_mm=900.0,
            required_full_confinement_length_mm=2500.0,
            infill_fully_adjacent=False,
            source_refs=("REVIEW:SHORT:7.7.6",),
        ),
    )
    result = subject.apply_reviewed_vc_to_transverse_input(
        request,
        reviewed=reviewed,
        a23_states=(
            _state("N500", 500000.0),
            _state("N200", 200000.0),
            _state("N350", 350000.0),
            _state("OUTSIDE", 100000.0),
        ),
        shear_evidence=evidence,
        p7_run=_fake_p7(monkeypatch),
        limited_run=None,
        fcd_mpa=20.0,
        target_unique_name="101",
        material_source_refs=("MAT:FCD",),
    )
    assert captured == [200000.0, 200000.0]
    assert all(item.qualified_vc_kn is not None for item in result.directions)
