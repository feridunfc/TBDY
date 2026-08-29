from __future__ import annotations

import math
from decimal import Decimal

import pytest

import tbdy_engine.regulatory.vs6_column_shear_p7_integration as integration
from tbdy_engine.design.columns.column_longitudinal_selection import (
    CanonicalEngineSelectedRebar,
)
from tbdy_engine.design.columns.column_longitudinal_ranking_authority import (
    ColumnLongitudinalRankingKey,
)
from tbdy_engine.design.columns.column_design_demand_engine import ColumnDesignDemandEngineResult
from tbdy_engine.design.columns.column_design_engine import ColumnDesignEngineResult
from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs, ColumnRebarDesignResult
from tbdy_engine.design.columns.column_shear_demand import CAPACITY_PROVEN, ColumnEndMomentCapacityBasis, associated_moment_axis
from tbdy_engine.design.columns.column_shear_upper_bounds import EFFECTIVE_DEPTH_PROVEN, ColumnEffectiveDepthResolution
from tbdy_engine.design.columns.free_length_basis import (
    FREE_LENGTH_BLOCKED,
    FREE_LENGTH_PROVEN,
    ColumnEndpointSupportResolution,
    ColumnFreeLengthResolution,
)
from tbdy_engine.design.columns.rebar_layout import (
    ColumnBarPoint,
    ColumnRebarCandidate,
    ColumnRebarGeometryCandidate,
)
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
    ColumnRebarSelectionResult,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.features.column_shear_demand_evidence import build_column_shear_demand_evidence, column_shear_source_identity
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence
from tbdy_engine.regulatory.column_shear_p7 import TBDY_BRITTLE_RULE_ID, TS500_WEB_RULE_ID, VE_RULE_ID
from tbdy_engine.regulatory.contracts import AvailabilityState, ClosureExecutionStatus
from tbdy_engine.regulatory.units import UNIT_KN, UNIT_M
from tbdy_engine.regulatory.vs6_column_shear_p7_integration import (
    BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY_REF,
    BOTH_SIGNS_CONSERVATIVE_MIN_EFFECTIVE_DEPTH_REF,
    ColumnShearCapacityStateSelection,
    ColumnShearDemandSelection,
    ReviewedDAmplifiedShearAuthority,
    VS6P7IntegrationError,
    resolve_exact_source_bound_shear_demand,
    run_vs6_p7_from_production_evidence,
)

COMPONENT = "S1:C1:101"


def _bars():
    area = math.pi * 100.0
    return (
        ColumnBarPoint(1, -150.0, -190.0, 20.0, area),
        ColumnBarPoint(2, 150.0, -190.0, 20.0, area),
        ColumnBarPoint(3, 150.0, 190.0, 20.0, area),
        ColumnBarPoint(4, -150.0, 190.0, 20.0, area),
    )


def _candidate():
    return ColumnRebarCandidate(
        candidate_id="RECT-4D20",
        bar_diameter_mm=20.0,
        n_bars_dir2=2,
        n_bars_dir3=2,
        bars=_bars(),
        as_total_mm2=4.0 * math.pi * 100.0,
        rho=4.0 * math.pi * 100.0 / 200_000.0,
        min_clear_spacing_mm=250.0,
        required_min_clear_spacing_mm=40.0,
    )


def _geometry_candidate():
    legacy = _candidate()
    return ColumnRebarGeometryCandidate(
        candidate_id=legacy.candidate_id,
        bar_diameter_mm=legacy.bar_diameter_mm,
        n_bars_dir2=legacy.n_bars_dir2,
        n_bars_dir3=legacy.n_bars_dir3,
        bars=legacy.bars,
        as_total_mm2=legacy.as_total_mm2,
        rho=legacy.rho,
        min_clear_spacing_mm=legacy.min_clear_spacing_mm,
    )


def _canonical_selected_rebar():
    candidate = _geometry_candidate()
    as_total_mm2 = Decimal(str(candidate.as_total_mm2))

    return CanonicalEngineSelectedRebar(
        selected_rebar_ref=(
            "engine-selected-rebar:sha256:p7-test-canonical"
        ),
        component_id=COMPONENT,
        candidate_id=candidate.candidate_id,
        candidate_geometry_fingerprint=(
            "candidate-geometry:sha256:p7-test"
        ),
        candidate_adequacy_ref=(
            "candidate-adequacy:sha256:p7-test"
        ),
        selected_candidate=candidate,
        as_total_mm2=as_total_mm2,
        rank=1,
        ranking_key=ColumnLongitudinalRankingKey(
            total_as_mm2=as_total_mm2,
            bar_count=candidate.bar_count,
            bar_diameter_mm=Decimal(
                str(candidate.bar_diameter_mm)
            ),
            stable_candidate_id=candidate.candidate_id,
        ),
        required_area_decision_ids=(
            "required-area-decision:p7-test",
        ),
        pmm_decision_ids=(
            "pmm-decision:p7-test",
        ),
        requirement_ids=(
            "requirement:p7-test",
        ),
        demand_state_ids=(
            "demand-state:p7-test",
        ),
        ranking_policy_id="PROJECT_COLUMN_REBAR_POLICY",
        ranking_policy_version="v1",
        ranking_policy_fingerprint=(
            "ranking-policy:sha256:p7-test"
        ),
        ranking_policy_review_ref=(
            "review:column-selection-policy:p7-test"
        ),
        adequacy_policy_fingerprint=(
            "adequacy-policy:sha256:p7-test"
        ),
        numerical_policy_fingerprint=(
            "numerical-policy:sha256:p7-test"
        ),
        material_context_ref=(
            "material-context:p7-test"
        ),
        model_fingerprint="model:p7-test",
        evidence_epoch_id="epoch:p7-test",
        provenance_refs=(
            "CANONICAL_SELECTED_REBAR:P7_TEST_PROVENANCE",
        ),
    )


def _basis():
    return ColumnDemandBasis(
        analysis_order_status="RESOLVED",
        minimum_eccentricity_status="RESOLVED",
        slenderness_status="RESOLVED",
        combination_scope_status="RESOLVED",
        review_refs=("COLUMN_DESIGN_BASIS:REVIEWED",),
    )


def _states(*, case_type="DesignStaticLinearExact", output_case="COMB1", zero_m3=False):
    return (
        ColumnDemandState(
            state_id=f"{COMPONENT}|COMB1|J_END|STATE",
            component_id=COMPONENT,
            output_case=output_case,
            case_type=case_type,
            step_type=None,
            step_number=None,
            station_m=0.0,
            end_tag="J_END",
            nd_compression_n=500_000.0,
            m2_nmm=20_000_000.0,
            m3_nmm=0.0 if zero_m3 else 50_000_000.0,
            source_identity="P-M2-M3:J_END",
        ),
        ColumnDemandState(
            state_id=f"{COMPONENT}|COMB1|I_END|STATE",
            component_id=COMPONENT,
            output_case=output_case,
            case_type=case_type,
            step_type=None,
            step_number=None,
            station_m=3.0,
            end_tag="I_END",
            nd_compression_n=450_000.0,
            m2_nmm=-15_000_000.0,
            m3_nmm=0.0 if zero_m3 else -40_000_000.0,
            source_identity="P-M2-M3:I_END",
        ),
    )


def _design(*, selected=True, states=None):
    states = tuple(states or _states())
    selection = ColumnRebarSelectionResult(
        component_id=COMPONENT,
        status="SELECTED" if selected else "BLOCKED_DEMAND_BASIS",
        authority="ENGINE_SELECTED_REBAR" if selected else "NOT_SELECTED",
        selected_candidate=_candidate() if selected else None,
        required_as_in_candidate_family_mm2=1256.637061 if selected else None,
        governing_state_id=states[0].state_id if selected else None,
        governing_utilization=0.7 if selected else None,
        trials=(),
        selected_evaluations=(),
        basis=_basis(),
    )
    rebar = ColumnRebarDesignResult(
        component_id=COMPONENT,
        status="SELECTED_ENGINE_REBAR" if selected else "BLOCKED_DEMAND_BASIS",
        catalog_status="PROVEN_FACTUAL_REBAR_CATALOG",
        candidate_population=None,
        selection=selection,
        excluded_catalog_bar_names=(),
    )
    demand = ColumnDesignDemandEngineResult(
        component_id=COMPONENT,
        status="PROVEN_COLUMN_DESIGN_DEMAND_SCOPE",
        combo_results=(),
        promoted_states=states,
        blocked_combo_names=(),
    )
    return ColumnDesignEngineResult(
        component_id=COMPONENT,
        status="SELECTED_ENGINE_REBAR" if selected else "BLOCKED_DEMAND_BASIS",
        design_demands=demand,
        minimum_eccentricity=object(),
        slenderness_basis=object(),
        slenderness=object(),
        rebar_design=rebar,
        stability_stiffness_basis=None,
    )


def _rebar_inputs():
    return ColumnRebarDesignInputs(
        component_id=COMPONENT,
        width_mm=400.0,
        depth_mm=500.0,
        clear_cover_mm=30.0,
        tie_diameter_mm=10.0,
        aggregate_max_mm=20.0,
        material=ColumnSectionMaterial(fck_mpa=25.0, fcd_mpa=25.0 / 1.5, fyd_mpa=420.0),
        demand_basis=_basis(),
        selection_policy=ColumnRebarSelectionPolicy(angle_count=72, axial_tolerance_n=250.0),
    )


def _topology():
    # Exact CSI I/J is opposite physical bottom/top: J_END is bottom, I_END top.
    return ColumnTopologyEvidence(
        unique_name="101",
        column_label="C1",
        story="S1",
        section="C400x500",
        width_t2_m=0.4,
        depth_t3_m=0.5,
        object_length_m=3.0,
        coordinate_length_m=3.0,
        joint_bottom="P_BOT",
        joint_top="P_TOP",
        bottom_coord_m=(0.0, 0.0, 0.0),
        top_coord_m=(0.0, 0.0, 3.0),
        offset_bottom_m=0.1,
        offset_top_m=0.1,
        analysis_clear_length_candidate_m=2.8,
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
        beams_at_bottom=(),
        beams_at_top=(),
        connectivity_row={"UniquePtI": "P_TOP", "UniquePtJ": "P_BOT"},
        assignment_row={"UniqueName": "101", "SectProp": "C400x500"},
        end_offset_row={"UniqueName": "101", "OffsetI": 0.1, "OffsetJ": 0.1},
        section_row={"Name": "C400x500", "t2": 0.4, "t3": 0.5},
        local_axis_row={"UniqueName": "101", "Angle": 0.0},
    )


def _support(end, joint):
    return ColumnEndpointSupportResolution(
        end_tag=end,
        joint_unique_name=joint,
        status="PROVEN_HORIZONTAL_LATERAL_SUPPORT",
        proof_methods=("TEST_SUPPORT",),
        support_vectors_xy=((1.0, 0.0), (0.0, 1.0)),
        source_refs=(f"SUPPORT:{end}",),
    )


def _free_length(*, resolved=True):
    return ColumnFreeLengthResolution(
        component_id=COMPONENT,
        status=FREE_LENGTH_PROVEN if resolved else FREE_LENGTH_BLOCKED,
        free_length_ln_mm=2800.0 if resolved else None,
        factual_candidate_mm=2800.0,
        bottom_support=_support("BOTTOM", "P_BOT"),
        top_support=_support("TOP", "P_TOP"),
        source_refs=("ETABS:END_OFFSETS:101", "TS500:FREE_LENGTH:REVIEW"),
    )


def _row():
    return {
        "Story": "S1",
        "Column": "C1",
        "UniqueName": "101",
        "OutputCase": "COMB1",
        "CaseType": "Combination",
        "StepType": "",
        "StepNumber": None,
        "Station": 0.0,
        "Element": "501",
        "ElemStation": 0.0,
        "V2": -80.0,
        "V3": 30.0,
    }


def _bundle():
    return build_column_shear_demand_evidence(
        model_fingerprint="model:test",
        rows=(_row(),),
        output_names=("COMB1",),
        force_unit=UNIT_KN,
        length_unit=UNIT_M,
        unit_provenance_refs=("GetPresentUnits_2", "CSI_LOCAL_AXES_REVIEWED"),
    )


def _demand_selection(bundle, direction="V2", *, source_identity=None, epoch=None):
    return ColumnShearDemandSelection(
        component_id=COMPONENT,
        column_unique_name="101",
        direction=direction,
        evidence_epoch_id=epoch or bundle.evidence_epoch_id,
        source_identity=source_identity or column_shear_source_identity(_row()),
        review_refs=(f"SELECT:{direction}:EXACT_ROW",),
    )


def _capacity_selection(*, direction="V2", states=None, rs_proven=True):
    states = tuple(states or _states())
    return ColumnShearCapacityStateSelection(
        component_id=COMPONENT,
        direction=direction,
        bottom_state_id=states[0].state_id,
        top_state_id=states[1].state_id,
        response_spectrum_concurrency_proven=rs_proven,
        review_refs=("CAPACITY_STATE_SELECTION:REVIEWED",),
    )


def _d_authority(direction="V2", *, resolved=True):
    return ReviewedDAmplifiedShearAuthority(
        component_id=COMPONENT,
        direction=direction,
        availability=AvailabilityState.RESOLVED if resolved else AvailabilityState.BLOCKED,
        candidate_kn=150.0 if resolved else None,
        authority_ref="STRUCTURAL_SYSTEM_D_LOAD_ROLE_AUTHORITY",
        review_refs=("D_AMPLIFIED_SHEAR:REVIEWED",),
    )


def _patch_capacity(monkeypatch):
    def capacity(**kwargs):
        value = 120.0 if kwargs["end_tag"] == "BOTTOM" else 80.0
        return ColumnEndMomentCapacityBasis(
            component_id=kwargs["component_id"],
            end_tag=kwargs["end_tag"],
            direction=kwargs["direction"],
            moment_axis=associated_moment_axis(kwargs["direction"]),
            moment_sign=kwargs["moment_sign"],
            nd_compression_kn=kwargs["nd_compression_kn"],
            capacity_knm=value,
            status=CAPACITY_PROVEN,
            source_refs=tuple(kwargs["source_refs"]),
        )
    monkeypatch.setattr(integration, "resolve_exact_column_end_moment_capacity", capacity)


def _patch_depth(monkeypatch, *, plus_d=None, minus_d=None):
    def depth(**kwargs):
        direction = kwargs["direction"]
        member_depth = kwargs["width_mm"] if direction == "V2" else kwargs["depth_mm"]
        default_d = member_depth - 50.0
        d = default_d
        if plus_d is not None and kwargs["moment_sign"] > 0:
            d = plus_d
        if minus_d is not None and kwargs["moment_sign"] < 0:
            d = minus_d
        bw = kwargs["depth_mm"] if direction == "V2" else kwargs["width_mm"]
        return ColumnEffectiveDepthResolution(
            component_id=kwargs["component_id"],
            direction=direction,
            moment_axis=associated_moment_axis(direction),
            moment_sign=kwargs["moment_sign"],
            effective_depth_d_mm=d,
            web_width_bw_mm=bw,
            tension_bar_coordinate_mm=0.0,
            status=EFFECTIVE_DEPTH_PROVEN,
            source_refs=tuple(kwargs["source_refs"]),
        )
    monkeypatch.setattr(integration, "resolve_exact_rectangular_column_effective_depth", depth)


_DEFAULT_SELECTED_REBAR = object()


def _run_raw(
    monkeypatch,
    *,
    direction="V2",
    design=None,
    selected_rebar=_DEFAULT_SELECTED_REBAR,
    free=None,
    d=None,
    states=None,
    rs_proven=True,
    patch_defaults=True,
):
    if patch_defaults:
        _patch_capacity(monkeypatch)
        _patch_depth(monkeypatch)
    bundle = _bundle()
    states = tuple(states or _states())

    canonical_selected_rebar = (
        _canonical_selected_rebar()
        if selected_rebar is _DEFAULT_SELECTED_REBAR
        else selected_rebar
    )

    return run_vs6_p7_from_production_evidence(
        column_design=design or _design(states=states),
        rebar_inputs=_rebar_inputs(),
        selected_rebar=canonical_selected_rebar,
        topology=_topology(),
        free_length=free or _free_length(),
        shear_evidence=bundle,
        tbdy_vd_selection=_demand_selection(bundle, direction),
        ts500_vd_selection=_demand_selection(bundle, direction),
        capacity_state_selection=_capacity_selection(direction=direction, states=states, rs_proven=rs_proven),
        d_amplified_authority=d or _d_authority(direction),
        tbdy_high_ductility_applies=True,
        ts500_rc_applies=True,
        material_source_refs=("MATERIAL:ETABS:FCK", "MATERIAL:TS500:FCD"),
    )


def _outcome(run, rule_id):
    items = tuple(item for item in run.regulatory_snapshot.closure_outcomes if item.compiled_record_ref.rule_id == rule_id)
    assert len(items) == 1
    return items[0]


def test_exact_shear_selector_uses_bundle_value_and_preserves_signed_component():
    bundle = _bundle()
    resolved = resolve_exact_source_bound_shear_demand(bundle=bundle, selection=_demand_selection(bundle, "V2"))
    assert resolved.signed_value_kn == pytest.approx(-80.0)
    assert resolved.demand.demand_kn == pytest.approx(80.0)
    assert resolved.demand.evidence_epoch_id == bundle.evidence_epoch_id
    assert any("LOCAL_AXIS_COMPONENT:V2" in ref for ref in resolved.demand.source_refs)


def test_wrong_shear_source_identity_and_epoch_fail_closed():
    bundle = _bundle()
    with pytest.raises(VS6P7IntegrationError, match="source identity"):
        resolve_exact_source_bound_shear_demand(
            bundle=bundle,
            selection=_demand_selection(bundle, source_identity="not-a-real-row"),
        )
    with pytest.raises(VS6P7IntegrationError, match="epoch"):
        resolve_exact_source_bound_shear_demand(
            bundle=bundle,
            selection=_demand_selection(bundle, epoch="epoch:wrong"),
        )


def test_v2_v3_are_distinct_and_never_anonymous_max(monkeypatch):
    v2 = _run_raw(monkeypatch, direction="V2")
    v3 = _run_raw(monkeypatch, direction="V3")
    assert v2.tbdy_vd.demand_kn == pytest.approx(80.0)
    assert v3.tbdy_vd.demand_kn == pytest.approx(30.0)
    assert v2.direction == "V2"
    assert v3.direction == "V3"


def test_exact_i_j_mapping_rejects_wrong_physical_end_state(monkeypatch):
    _patch_capacity(monkeypatch)
    _patch_depth(monkeypatch)
    bundle = _bundle()
    states = _states()
    wrong = ColumnShearCapacityStateSelection(
        component_id=COMPONENT,
        direction="V2",
        bottom_state_id=states[1].state_id,
        top_state_id=states[0].state_id,
        response_spectrum_concurrency_proven=True,
        review_refs=("WRONG_END_TEST",),
    )
    with pytest.raises(VS6P7IntegrationError, match="physical bottom/top"):
        run_vs6_p7_from_production_evidence(
            column_design=_design(states=states),
            rebar_inputs=_rebar_inputs(),
            selected_rebar=_canonical_selected_rebar(),
            topology=_topology(),
            free_length=_free_length(),
            shear_evidence=bundle,
            tbdy_vd_selection=_demand_selection(bundle),
            ts500_vd_selection=_demand_selection(bundle),
            capacity_state_selection=wrong,
            d_amplified_authority=_d_authority(),
            tbdy_high_ductility_applies=True,
            ts500_rc_applies=True,
            material_source_refs=("MAT:FCK", "MAT:FCD"),
        )


def test_missing_canonical_selected_rebar_blocks_capacity_ve_and_ts500_d(
    monkeypatch,
):
    states = _states()

    # Deliberately retain a legacy ENGINE_SELECTED_REBAR inside
    # ColumnDesignEngineResult. P7 must not consume that legacy authority.
    run = _run_raw(
        monkeypatch,
        design=_design(selected=True, states=states),
        selected_rebar=None,
        states=states,
    )
    assert run.bottom_capacity.status != CAPACITY_PROVEN
    assert run.top_capacity.status != CAPACITY_PROVEN
    assert run.ve_kn is None
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(run, TBDY_BRITTLE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(run, TS500_WEB_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED


def test_zero_moment_sign_uses_conservative_max_of_both_capacities(monkeypatch):
    states = _states(zero_m3=True)
    calls = []

    def capacity(**kwargs):
        calls.append((kwargs["end_tag"], kwargs["moment_sign"]))
        value = 120.0 if kwargs["moment_sign"] > 0 else 140.0
        return ColumnEndMomentCapacityBasis(
            component_id=kwargs["component_id"],
            end_tag=kwargs["end_tag"],
            direction=kwargs["direction"],
            moment_axis=associated_moment_axis(kwargs["direction"]),
            moment_sign=kwargs["moment_sign"],
            nd_compression_kn=kwargs["nd_compression_kn"],
            capacity_knm=value,
            status=CAPACITY_PROVEN,
            source_refs=tuple(kwargs["source_refs"]),
        )

    monkeypatch.setattr(integration, "resolve_exact_column_end_moment_capacity", capacity)
    _patch_depth(monkeypatch)
    run = _run_raw(monkeypatch, states=states, patch_defaults=False)
    assert run.bottom_capacity.capacity_knm == pytest.approx(140.0)
    assert run.top_capacity.capacity_knm == pytest.approx(140.0)
    assert BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY_REF in run.bottom_capacity.source_refs
    assert BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY_REF in run.top_capacity.source_refs
    assert {sign for _end, sign in calls} == {-1, 1}


def test_effective_depth_uses_conservative_minimum_of_both_signs(monkeypatch):
    _patch_capacity(monkeypatch)
    _patch_depth(monkeypatch, plus_d=360.0, minus_d=340.0)
    run = _run_raw(monkeypatch, patch_defaults=False)
    assert run.effective_depth.effective_depth_d_mm == pytest.approx(340.0)
    assert run.effective_depth.moment_sign == -1
    assert BOTH_SIGNS_CONSERVATIVE_MIN_EFFECTIVE_DEPTH_REF in run.effective_depth.source_refs


def test_unresolved_free_length_and_d_authority_block_without_fallback(monkeypatch):
    no_ln = _run_raw(monkeypatch, free=_free_length(resolved=False))
    assert no_ln.ve_kn is None
    assert _outcome(no_ln, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(no_ln, TBDY_BRITTLE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(no_ln, TS500_WEB_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED

    no_d = _run_raw(monkeypatch, d=_d_authority(resolved=False))
    assert no_d.ve_kn is None
    assert _outcome(no_d, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(no_d, TBDY_BRITTLE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(no_d, TS500_WEB_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED


def test_response_spectrum_state_requires_explicit_concurrency_review(monkeypatch):
    states = _states(case_type="DesignResponseSpectrumPermutation")
    run = _run_raw(monkeypatch, states=states, rs_proven=False)
    assert run.ve_kn is None
    assert _outcome(run, VE_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED


def test_capacity_state_output_case_must_match_exact_tbdy_shear(monkeypatch):
    _patch_capacity(monkeypatch)
    _patch_depth(monkeypatch)
    bundle = _bundle()
    states = _states(output_case="OTHER_COMBO")
    with pytest.raises(VS6P7IntegrationError, match="output case"):
        run_vs6_p7_from_production_evidence(
            column_design=_design(states=states),
            rebar_inputs=_rebar_inputs(),
            selected_rebar=_canonical_selected_rebar(),
            topology=_topology(),
            free_length=_free_length(),
            shear_evidence=bundle,
            tbdy_vd_selection=_demand_selection(bundle),
            ts500_vd_selection=_demand_selection(bundle),
            capacity_state_selection=_capacity_selection(states=states),
            d_amplified_authority=_d_authority(),
            tbdy_high_ductility_applies=True,
            ts500_rc_applies=True,
            material_source_refs=("MAT:FCK", "MAT:FCD"),
        )
