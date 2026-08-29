import pytest

from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_readiness import (
    READY,
    REANALYSIS_REQUIRED,
    SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED,
    resolve_column_design_demand_readiness,
)
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
)
from tbdy_engine.design.columns.stability_analysis_basis_binding import (
    ColumnSlendernessEvidenceBinding,
    StabilityAnalysisBasisBindingError,
    StorySwayStabilityEvidenceBinding,
    promote_eq713_sway_to_column_slenderness_evidence,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    assess_ts500_eq713_stiffness_basis,
)
from tbdy_engine.design.columns.sway_stability import (
    LOAD_BASIS_AUTHORITY,
    STORY_STABILITY_INPUT_AUTHORITY,
    SWAY_STABILITY_AUTHORITY,
    TS500_LOAD_GQE,
    TS500_LOAD_GQW,
    UNCRACKED_SECTION_BASIS_AUTHORITY,
    StoryStabilityIndexError,
    StoryStabilityIndexEvidence,
    resolve_ts500_story_sway_from_stability_indices,
)


COMP = "+9.00:C56:100"
STORY = "+9.00"
MODEL = "model-fingerprint-A"
EPOCH = "evidence-epoch-A"


def _axis_evidence(axis, *, ln=3000.0):
    return ColumnSlendernessAxisEvidence(
        axis=axis,
        section_dimension_mm=800.0,
        factual_clear_length_candidate_mm=3800.0,
        factual_clear_length_source_ref=f"topology:{axis}",
        factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
        regulatory_free_length_ln_mm=ln,
        regulatory_free_length_source_ref=f"free-length:{axis}",
        regulatory_free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
        sway_classification=None,
        sway_source_ref=None,
        sway_authority=None,
        effective_length_factor_k=None,
        effective_length_source_ref=None,
        effective_length_authority=None,
        moment_ratio_m1_over_m2=None,
        moment_ratio_source_ref=None,
        moment_ratio_authority=None,
        allow_conservative_braced_ratio=True,
    )


def _column_binding(*, ln=3000.0, model=MODEL, epoch=EPOCH):
    evidence = ColumnSlendernessEvidence(
        component_id=COMP,
        m2=_axis_evidence("M2", ln=ln),
        m3=_axis_evidence("M3", ln=ln),
        source_refs=("factual:slenderness",),
    )
    return ColumnSlendernessEvidenceBinding(
        evidence=evidence,
        story=STORY,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        source_refs=("context:column-slenderness",),
    )


def _story_input(direction, load_basis, *, drift=1.0, stiffness_basis="UNCRACKED"):
    return StoryStabilityIndexEvidence(
        story=STORY,
        direction=direction,
        load_basis=load_basis,
        story_height_mm=3000.0,
        relative_story_displacement_mm=drift,
        story_shear_n=1_000_000.0,
        sum_column_axial_design_force_n=1_000_000.0,
        input_authority=STORY_STABILITY_INPUT_AUTHORITY,
        load_basis_authority=LOAD_BASIS_AUTHORITY,
        stiffness_basis=stiffness_basis,
        stiffness_basis_authority=UNCRACKED_SECTION_BASIS_AUTHORITY,
        source_refs=(f"analysis:{direction}:{load_basis}:{stiffness_basis}",),
    )


def _resolution(direction, *, drift=1.0):
    evidences = tuple(
        _story_input(direction, load_basis, drift=drift)
        for load_basis in (TS500_LOAD_GQE, TS500_LOAD_GQW)
    )
    result = resolve_ts500_story_sway_from_stability_indices(
        evidences,
        story=STORY,
        direction=direction,
    )
    assert result.authority == SWAY_STABILITY_AUTHORITY
    return result


def _sway_binding(*, directions=("X", "Y"), model=MODEL, epoch=EPOCH, drift=1.0):
    return StorySwayStabilityEvidenceBinding(
        component_id=COMP,
        story=STORY,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        resolutions=tuple(_resolution(direction, drift=drift) for direction in directions),
        source_refs=("context:eq713-reanalysis",),
    )


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


def _fnd(promoted, *, stiffness=None):
    return resolve_column_design_demand_readiness(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ULS",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("G", 1.0),),
            ),
        ),
        constituent_case_demands=(
            _state("G", "I_END", 0.0, 1_000_000.0, -100_000_000.0, 80_000_000.0),
            _state("G", "J_END", 3.8, 900_000.0, 70_000_000.0, -60_000_000.0),
        ),
        width_mm=800.0,
        depth_mm=800.0,
        slenderness_evidence=promoted.evidence,
        stability_stiffness_basis=stiffness,
    )


def _cracked_production_stiffness():
    return assess_ts500_eq713_stiffness_basis(
        (
            AssignedFrameBendingModifierEvidence(
                section_name="Column_80x80",
                member_kind="COLUMN",
                i2_modifier=0.70,
                i3_modifier=0.70,
                source_refs=("ETABS:Column_80x80",),
            ),
            AssignedFrameBendingModifierEvidence(
                section_name="Beam",
                member_kind="BEAM",
                i2_modifier=0.35,
                i3_modifier=0.35,
                source_refs=("ETABS:Beam",),
            ),
        )
    )


def test_positive_separate_uncracked_eq713_route_reuses_fnd_col_2_with_cracked_production_model():
    cracked = _cracked_production_stiffness()
    assert cracked.reanalysis_required

    promoted = promote_eq713_sway_to_column_slenderness_evidence(
        column=_column_binding(),
        sway=_sway_binding(),
    )
    result = _fnd(promoted, stiffness=cracked)

    assert promoted.evidence.m2.sway_classification == SWAY_PREVENTED
    assert promoted.evidence.m3.sway_classification == SWAY_PREVENTED
    assert result.status == READY
    assert result.ready
    assert "ENGINE_SELECTED_REBAR" not in repr(result)


def test_cracked_basis_cannot_manufacture_positive_eq713_sway_proof():
    evidences = tuple(
        _story_input("X", load_basis, stiffness_basis="CRACKED")
        for load_basis in (TS500_LOAD_GQE, TS500_LOAD_GQW)
    )
    with pytest.raises(StoryStabilityIndexError, match="requires UNCRACKED"):
        resolve_ts500_story_sway_from_stability_indices(evidences, story=STORY, direction="X")


def test_missing_orthogonal_sway_evidence_fails_closed_and_does_not_invent_classification():
    column = _column_binding()
    with pytest.raises(StabilityAnalysisBasisBindingError, match="both orthogonal"):
        promote_eq713_sway_to_column_slenderness_evidence(
            column=column,
            sway=_sway_binding(directions=("X",)),
        )
    assert column.evidence.m2.sway_classification is None
    assert column.evidence.m3.sway_classification is None


def test_cross_model_sway_evidence_is_rejected():
    with pytest.raises(StabilityAnalysisBasisBindingError, match="cross-model"):
        promote_eq713_sway_to_column_slenderness_evidence(
            column=_column_binding(model="model-A"),
            sway=_sway_binding(model="model-B"),
        )


def test_cross_evidence_epoch_sway_evidence_is_rejected():
    with pytest.raises(StabilityAnalysisBasisBindingError, match="cross-EvidenceEpoch"):
        promote_eq713_sway_to_column_slenderness_evidence(
            column=_column_binding(epoch="epoch-A"),
            sway=_sway_binding(epoch="epoch-B"),
        )


def test_nonproven_sway_resolution_is_not_promoted_to_a_classification():
    with pytest.raises(StabilityAnalysisBasisBindingError, match="is not proven"):
        _sway_binding(drift=200.0)


def test_missing_physical_m1_m2_is_preserved_as_missing_not_invented_by_binding():
    promoted = promote_eq713_sway_to_column_slenderness_evidence(
        column=_column_binding(),
        sway=_sway_binding(),
    )
    assert promoted.evidence.m2.moment_ratio_m1_over_m2 is None
    assert promoted.evidence.m3.moment_ratio_m1_over_m2 is None
    assert promoted.evidence.m2.moment_ratio_authority is None
    assert promoted.evidence.m3.moment_ratio_authority is None


def test_general_second_order_required_has_no_first_order_fallback():
    promoted = promote_eq713_sway_to_column_slenderness_evidence(
        column=_column_binding(ln=25_000.0),
        sway=_sway_binding(),
    )
    result = _fnd(promoted, stiffness=_cracked_production_stiffness())
    assert result.status == REANALYSIS_REQUIRED
    assert result.second_order_treatment == SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
    assert "TS500_7.6.1_GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED" in result.blocked_items


def test_stability_binding_and_fnd_result_are_deterministic():
    first = promote_eq713_sway_to_column_slenderness_evidence(
        column=_column_binding(),
        sway=_sway_binding(),
    )
    second = promote_eq713_sway_to_column_slenderness_evidence(
        column=_column_binding(),
        sway=_sway_binding(),
    )
    assert first == second
    assert _fnd(first, stiffness=_cracked_production_stiffness()) == _fnd(
        second,
        stiffness=_cracked_production_stiffness(),
    )
