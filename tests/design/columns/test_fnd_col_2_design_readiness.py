import pytest

from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_readiness import (
    ANALYSIS_BASIS_MATCH,
    ANALYSIS_BASIS_REANALYSIS_REQUIRED,
    BLOCKED,
    READY,
    REANALYSIS_REQUIRED,
    SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED,
    SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED,
    SECOND_ORDER_NOT_REQUIRED,
    UNRESOLVED,
    resolve_column_design_demand_readiness,
)
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    assess_ts500_eq713_stiffness_basis,
)


COMP = "+0.00:C2:236"


def _state(case, end, station, n, m2, m3):
    return ColumnDemandState(
        state_id=f"{case}:{end}",
        component_id=COMP,
        output_case=case,
        case_type="LinStatic",
        step_type=None,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}",
    )


def _combo():
    return (
        ColumnComboDefinition(
            name="ULS",
            combo_type="LINEAR_ADD",
            constituents=(ComboPatternConstituent("G", 1.0),),
        ),
    )


def _case_demands():
    return (
        _state("G", "I_END", 0.0, 1_000_000.0, -100_000_000.0, 80_000_000.0),
        _state("G", "J_END", 3.0, 900_000.0, 70_000_000.0, -60_000_000.0),
    )


def _axis_basis(axis, *, h=800.0, ln=3000.0, ratio=0.0):
    return ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=h,
        free_length_ln_mm=ln,
        effective_length_factor_k=1.0,
        sway_classification=SWAY_PREVENTED,
        moment_ratio_m1_over_m2=ratio,
        source_refs=(f"reviewed:{axis}",),
    )


def _basis(*, m2=None, m3=None):
    return ColumnSlendernessBasis(
        component_id=COMP,
        m2=m2 or _axis_basis("M2"),
        m3=m3 or _axis_basis("M3"),
        source_refs=("reviewed:slenderness-basis",),
    )


def _axis_evidence(axis, *, ln=3000.0, sway=SWAY_PREVENTED, ratio=None):
    return ColumnSlendernessAxisEvidence(
        axis=axis,
        section_dimension_mm=800.0,
        factual_clear_length_candidate_mm=3000.0,
        factual_clear_length_source_ref=f"topology:{axis}",
        factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
        regulatory_free_length_ln_mm=ln,
        regulatory_free_length_source_ref=(None if ln is None else f"reviewed:{axis}:ln"),
        regulatory_free_length_authority=(None if ln is None else REGULATORY_FREE_LENGTH_AUTHORITY),
        sway_classification=sway,
        sway_source_ref=(None if sway is None else f"reviewed:{axis}:sway"),
        sway_authority=(None if sway is None else SWAY_CLASSIFICATION_AUTHORITY),
        effective_length_factor_k=None,
        effective_length_source_ref=None,
        effective_length_authority=None,
        moment_ratio_m1_over_m2=ratio,
        moment_ratio_source_ref=(None if ratio is None else f"reviewed:{axis}:ratio"),
        moment_ratio_authority=(None if ratio is None else "TS500_END_MOMENT_RATIO"),
        allow_conservative_braced_ratio=True,
    )


def _evidence(m2, m3):
    return ColumnSlendernessEvidence(
        component_id=COMP,
        m2=m2,
        m3=m3,
        source_refs=("fixture:slenderness-evidence",),
    )


def _resolve(**kwargs):
    return resolve_column_design_demand_readiness(
        component_id=COMP,
        combo_definitions=_combo(),
        constituent_case_demands=_case_demands(),
        width_mm=500.0,
        depth_mm=800.0,
        **kwargs,
    )


def test_ready_state_is_derived_without_caller_resolved_flags():
    result = _resolve(slenderness_basis=_basis())
    assert result.status == READY
    assert result.analysis_basis_status == ANALYSIS_BASIS_MATCH
    assert result.second_order_treatment == SECOND_ORDER_NOT_REQUIRED
    assert result.minimum_eccentricity.resolved
    assert result.slenderness.resolved
    assert not hasattr(result, "minimum_eccentricity_status")
    assert not hasattr(result, "combination_scope_status")
    assert not hasattr(result, "rebar_design")


def test_concurrent_signed_p_m2_m3_states_are_preserved_without_independent_max_envelope():
    result = _resolve(slenderness_basis=_basis())
    assert len(result.demand_states) == 2
    by_end = {state.end_tag: state for state in result.demand_states}
    assert by_end["I_END"].nd_compression_n == pytest.approx(1_000_000.0)
    assert by_end["I_END"].m2_nmm == pytest.approx(-100_000_000.0)
    assert by_end["I_END"].m3_nmm == pytest.approx(80_000_000.0)
    assert by_end["J_END"].nd_compression_n == pytest.approx(900_000.0)
    assert by_end["J_END"].m2_nmm == pytest.approx(70_000_000.0)
    assert by_end["J_END"].m3_nmm == pytest.approx(-60_000_000.0)
    assert all("src:G:" in state.source_identity for state in result.demand_states)


def test_axis_specific_slenderness_can_require_magnification_without_reanalysis():
    result = _resolve(
        slenderness_basis=_basis(
            m2=_axis_basis("M2", h=500.0, ln=6000.0, ratio=1.0),
            m3=_axis_basis("M3", h=800.0, ln=3000.0, ratio=0.0),
        )
    )
    assert result.status == BLOCKED
    assert result.analysis_basis_status == ANALYSIS_BASIS_MATCH
    assert result.second_order_treatment == SECOND_ORDER_MOMENT_MAGNIFICATION_REQUIRED
    assert result.slenderness.m2.status == "MOMENT_MAGNIFICATION_REQUIRED"
    assert result.slenderness.m3.status == "SLENDERNESS_EFFECTS_NEGLIGIBLE"


def test_conservative_unknown_moment_ratio_failure_is_unresolved_not_false_magnification_authority():
    evidence = _evidence(
        _axis_evidence("M2", ln=8000.0, sway=SWAY_PREVENTED, ratio=None),
        _axis_evidence("M3", ln=3000.0, sway=SWAY_PREVENTED, ratio=0.0),
    )
    result = _resolve(slenderness_evidence=evidence)
    assert result.status == UNRESOLVED
    assert "M2:ACTUAL_M1_M2_RATIO_REQUIRED" in result.blocked_items


def test_missing_regulatory_free_length_blocks_readiness():
    evidence = _evidence(
        _axis_evidence("M2", ln=None, sway=SWAY_PREVENTED, ratio=0.0),
        _axis_evidence("M3", ln=3000.0, sway=SWAY_PREVENTED, ratio=0.0),
    )
    result = _resolve(slenderness_evidence=evidence)
    assert result.status == BLOCKED
    assert "M2:REGULATORY_FREE_LENGTH_NOT_PROMOTED" in result.blocked_items


def test_stiffness_basis_mismatch_with_unpromoted_sway_requires_reanalysis():
    stiffness = assess_ts500_eq713_stiffness_basis(
        (
            AssignedFrameBendingModifierEvidence(
                section_name="C80",
                member_kind="COLUMN",
                i2_modifier=0.70,
                i3_modifier=0.70,
                source_refs=("ETABS:C80",),
            ),
        )
    )
    evidence = _evidence(
        _axis_evidence("M2", ln=3000.0, sway=None, ratio=None),
        _axis_evidence("M3", ln=3000.0, sway=None, ratio=None),
    )
    result = _resolve(slenderness_evidence=evidence, stability_stiffness_basis=stiffness)
    assert result.status == REANALYSIS_REQUIRED
    assert result.analysis_basis_status == ANALYSIS_BASIS_REANALYSIS_REQUIRED
    assert result.second_order_treatment == SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED


def test_slenderness_above_100_requires_general_second_order_reanalysis():
    result = _resolve(
        slenderness_basis=_basis(
            m2=_axis_basis("M2", h=500.0, ln=16000.0, ratio=0.0),
            m3=_axis_basis("M3"),
        )
    )
    assert result.status == REANALYSIS_REQUIRED
    assert result.analysis_basis_status == ANALYSIS_BASIS_REANALYSIS_REQUIRED
    assert result.second_order_treatment == SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED


def test_output_is_deterministic_and_produces_no_engine_selected_rebar():
    first = _resolve(slenderness_basis=_basis())
    second = _resolve(slenderness_basis=_basis())
    assert first == second
    assert first.authority == "FND_COL_2_CANONICAL_COLUMN_DESIGN_DEMAND_READINESS"
    assert "ENGINE_SELECTED_REBAR" not in repr(first)
