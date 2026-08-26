from __future__ import annotations

import math

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.design.columns.column_shear_demand import (
    CAPACITY_PROVEN,
    ColumnEndMomentCapacityBasis,
    associated_moment_axis,
)
from tbdy_engine.design.columns.column_shear_upper_bounds import (
    resolve_exact_rectangular_column_effective_depth,
)
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint
from tbdy_engine.product_reports.vs6_column_shear_p7_report import (
    build_vs6_p7_column_shear_reports,
)
from tbdy_engine.regulatory.authority import validate_registry_authority
from tbdy_engine.regulatory.column_shear_p7 import (
    TBDY_BRITTLE_RULE_ID,
    TS500_WEB_RULE_ID,
    VE_KN_KEY,
    VE_RULE_ID,
    VS6_COLUMN_SHEAR_P7_REGISTRY,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityState,
    ClosureExecutionStatus,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.sources.vs6_column_shear_p7 import (
    APPROVED_IMPLEMENTATION_FINGERPRINTS,
    build_vs6_column_shear_p7_authority_catalog,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    ColumnShearVrClosureStatus,
    SourceBoundShearDemand,
    build_vs6_p7_column_shear_run,
    run_vs6_p7_direction,
)


def _bars():
    return (
        ColumnBarPoint(0, -150.0, -190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(1, 150.0, -190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(2, 150.0, 190.0, 20.0, math.pi * 100.0),
        ColumnBarPoint(3, -150.0, 190.0, 20.0, math.pi * 100.0),
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


def _run(
    *,
    direction="V2",
    bottom_knm=120.0,
    top_knm=80.0,
    free_length_ln_mm=2000.0,
    d_candidate_kn=150.0,
    tbdy_vd_kn=60.0,
    ts500_vd_kn=50.0,
    tbdy_applies=True,
    rc_applies=True,
    rs_required=False,
    rs_proven=True,
):
    return run_vs6_p7_direction(
        component_id="C1",
        story="S1",
        section="C400x500",
        direction=direction,
        tbdy_high_ductility_applies=tbdy_applies,
        ts500_rc_applies=rc_applies,
        free_length_ln_mm=free_length_ln_mm,
        free_length_basis_ref=None if free_length_ln_mm is None else "LN:STRICT",
        bottom_capacity=_capacity("BOTTOM", direction, bottom_knm),
        top_capacity=_capacity("TOP", direction, top_knm),
        d_amplified_candidate_kn=d_candidate_kn,
        d_amplified_basis_ref=None if d_candidate_kn is None else "D:REVIEWED",
        tbdy_vd=_source_demand(tbdy_vd_kn, "VD:TBDY"),
        ts500_vd=_source_demand(ts500_vd_kn, "VD:TS500"),
        response_spectrum_concurrency_required=rs_required,
        response_spectrum_concurrency_proven=rs_proven,
        width_mm=400.0,
        depth_mm=500.0,
        geometry_source_ref="GEOM:RECT",
        fck_mpa=25.0,
        fcd_mpa=16.6666666667,
        material_source_refs=("MAT:FCK", "MAT:FCD"),
        effective_depth=_effective(direction, 1),
    )


def _outcome(run, rule_id):
    matches = tuple(
        item
        for item in run.regulatory_snapshot.closure_outcomes
        if item.compiled_record_ref.rule_id == rule_id
    )
    assert len(matches) == 1
    return matches[0]


def test_f09_source_catalog_validates_all_three_formal_rules():
    catalog = build_vs6_column_shear_p7_authority_catalog()
    validated = validate_registry_authority(VS6_COLUMN_SHEAR_P7_REGISTRY, catalog)
    assert len(validated) == 3
    assert {item.rule_id for item in validated} == {
        VE_RULE_ID,
        TBDY_BRITTLE_RULE_ID,
        TS500_WEB_RULE_ID,
    }
    assert {
        item.rule_id.value: item.approved_implementation_fingerprint
        for item in validated
    } == APPROVED_IMPLEMENTATION_FINGERPRINTS


def test_f0_executes_ve_and_both_upper_bounds_in_kn_knm_mm():
    run = _run()
    assert run.ve_kn == pytest.approx(100.0)
    assert run.tbdy_brittle_result is not None
    assert run.ts500_web_result is not None
    assert run.tbdy_brittle_result.check_id == TBDY_BRITTLE_RULE_ID.value
    assert run.ts500_web_result.check_id == TS500_WEB_RULE_ID.value
    assert run.tbdy_brittle_result.status is CheckStatus.OK
    assert run.ts500_web_result.status is CheckStatus.OK
    assert run.tbdy_brittle_result.unit == "kN"
    assert run.ts500_web_result.unit == "kN"
    assert len(run.regulatory_snapshot.regulatory_quantities) == 1
    assert run.regulatory_snapshot.regulatory_quantities[0].quantity_key == VE_KN_KEY
    assert len(run.regulatory_snapshot.formal_results) == 2
    assert run.structural_assessment.structural_status is StructuralAssessmentStatus.COMPLETE


def test_missing_d_authority_blocks_ve_and_tbdy_but_not_independent_ts500():
    run = _run(d_candidate_kn=None)
    assert run.ve_kn is None
    assert run.tbdy_brittle_result is None
    assert run.ts500_web_result is not None
    assert run.ts500_web_result.status is CheckStatus.OK
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(run, TBDY_BRITTLE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(run, TS500_WEB_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert run.structural_assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE


def test_missing_free_length_blocks_without_story_height_fallback():
    run = _run(free_length_ln_mm=None)
    assert run.ve_kn is None
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(run, TBDY_BRITTLE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert run.ts500_web_result is not None


def test_unproven_response_spectrum_concurrency_blocks_ve():
    run = _run(rs_required=True, rs_proven=False)
    assert run.ve_kn is None
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert run.ts500_web_result is not None


def test_high_ductility_false_is_proven_not_applicable_while_ts500_still_executes():
    run = _run(tbdy_applies=False, rc_applies=True)
    assert run.ve_kn is None
    assert run.tbdy_brittle_result is None
    assert run.ts500_web_result is not None
    assert run.applicability_status == ApplicabilityState.PROVEN_NOT_APPLICABLE.value
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
    assert _outcome(run, TBDY_BRITTLE_RULE_ID).execution_status is ClosureExecutionStatus.PROVEN_NOT_APPLICABLE
    assert _outcome(run, TS500_WEB_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED


def test_unresolved_high_ductility_never_auto_applies_tbdy():
    run = _run(tbdy_applies=None, rc_applies=True)
    assert run.ve_kn is None
    assert run.tbdy_brittle_result is None
    assert run.ts500_web_result is not None
    assert run.applicability_status == ApplicabilityState.UNRESOLVED.value
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED


def test_tbdy_brittle_failure_requires_reanalysis():
    run = _run(bottom_knm=1000.0, top_knm=1000.0, d_candidate_kn=1500.0)
    assert run.ve_kn == pytest.approx(1000.0)
    assert run.tbdy_brittle_result is not None
    assert run.tbdy_brittle_result.status is CheckStatus.FAIL
    assert run.analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED
    assert any("REANALYSIS_REQUIRED" in msg for msg in run.tbdy_brittle_result.messages)


def test_ts500_web_failure_is_independent_formal_fail():
    run = _run(ts500_vd_kn=700.0)
    assert run.tbdy_brittle_result is not None
    assert run.tbdy_brittle_result.status is CheckStatus.OK
    assert run.ts500_web_result is not None
    assert run.ts500_web_result.status is CheckStatus.FAIL
    assert run.analysis_basis_status is AnalysisBasisStatus.MATCH


def test_upper_bound_ok_never_claims_full_shear_pass_and_report_is_projection_only():
    direction = _run()
    assert direction.full_vr_closure_status is ColumnShearVrClosureStatus.BLOCKED_BY_TRANSVERSE_REBAR_SLICE
    run = build_vs6_p7_column_shear_run(component_id="C1", directions=(direction,))
    reports = build_vs6_p7_column_shear_reports(run)
    assert len(reports) == 1
    report = reports[0]
    assert report.status == "PARTIAL"
    fields = {item.key: item for item in report.summary_fields}
    assert fields["Ve_kn"].value == pytest.approx(100.0)
    assert fields["Ve_kn"].unit == "kN"
    assert fields["bottom_capacity_knm"].unit == "kN*m"
    assert fields["effective_depth_d_mm"].unit == "mm"
    assert any("deferred to VS6-P8" in warning for warning in report.warnings)


def test_report_projects_reanalysis_required_from_canonical_tbdy_failure():
    direction = _run(bottom_knm=1000.0, top_knm=1000.0, d_candidate_kn=1500.0)
    run = build_vs6_p7_column_shear_run(component_id="C1", directions=(direction,))
    report = build_vs6_p7_column_shear_reports(run)[0]
    assert report.status == "REANALYSIS_REQUIRED"
