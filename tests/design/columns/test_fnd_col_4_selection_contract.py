from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import inspect

import pytest

import tbdy_engine.design.columns.column_longitudinal_selection_contract as subject

from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    ColumnComboEligibilityProjection,
    ColumnComboEligibilityState,
    ComboConstituentEligibilityFact,
    ComponentReadinessBinding,
)
from tbdy_engine.design.columns.column_design_demand_engine import (
    ColumnComboDefinition,
)
from tbdy_engine.design.columns.column_design_readiness import (
    resolve_column_design_demand_readiness,
)
from tbdy_engine.design.columns.column_design_rebar_promotion import (
    promote_etabs_required_rebar,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    BLOCK_COMPONENT_ID_MISMATCH,
    BLOCK_DESIGN_SECTION_MISMATCH,
    BLOCK_EVIDENCE_EPOCH_MISMATCH,
    BLOCK_MODEL_CONTEXT_MISMATCH,
    BLOCK_P8A_PROMOTION_INCOMPLETE,
    BLOCK_PROJECTION_BINDING,
    BLOCK_READINESS_NOT_READY,
    ColumnLongitudinalSelectionContractError,
    ColumnLongitudinalSelectionInputs,
    ColumnLongitudinalSelectionPolicyInput,
    STATUS_RECONCILED,
    reconcile_column_longitudinal_selection_contract,
)
from tbdy_engine.design.columns.combo_pattern_engine import (
    ComboPatternConstituent,
)
from tbdy_engine.design.columns.rebar_catalog import (
    build_rebar_catalog_from_rows,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    FactualColumnDesignResultPopulation,
    FactualColumnDesignResultRow,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    ColumnLongitudinalLayoutInputs,
    ColumnLongitudinalRequirementInputs,
    evaluate_column_longitudinal_layouts,
)
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    FND_COL_1_AUTHORITY_CATALOG,
)

COMP = "column:1"
MODEL = "model:fixture"
EPOCH = "epoch:fixture"
SECTION = "COL500X800"


def _state(case: str, end: str, station: float, n: float, m2: float, m3: float):
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


def _readiness():
    combo = ColumnComboDefinition(
        name="ULS",
        combo_type="LINEAR_ADD",
        constituents=(ComboPatternConstituent("G", 1.0),),
    )

    demands = (
        _state(
            "G",
            "I_END",
            0.0,
            1_000_000.0,
            -100_000_000.0,
            80_000_000.0,
        ),
        _state(
            "G",
            "J_END",
            3.0,
            900_000.0,
            70_000_000.0,
            -60_000_000.0,
        ),
    )

    basis = ColumnSlendernessBasis(
        component_id=COMP,
        m2=ColumnSlendernessAxisBasis(
            axis="M2",
            section_dimension_mm=800.0,
            free_length_ln_mm=3000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=0.0,
            source_refs=("reviewed:M2",),
        ),
        m3=ColumnSlendernessAxisBasis(
            axis="M3",
            section_dimension_mm=500.0,
            free_length_ln_mm=3000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=0.0,
            source_refs=("reviewed:M3",),
        ),
        source_refs=("reviewed:slenderness",),
    )

    result = resolve_column_design_demand_readiness(
        component_id=COMP,
        combo_definitions=(combo,),
        constituent_case_demands=demands,
        width_mm=500.0,
        depth_mm=800.0,
        slenderness_basis=basis,
    )

    assert result.ready
    return result


def _readiness_binding(*, readiness=None, model=MODEL, epoch=EPOCH):
    readiness = _readiness() if readiness is None else readiness
    return ComponentReadinessBinding(
        readiness=readiness,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        readiness_ref=f"readiness:{COMP}",
        provenance_refs=("fnd-col-2:fixture",),
    )


def _layout(*, model=MODEL, epoch=EPOCH, section=SECTION):
    catalog = build_rebar_catalog_from_rows(
        (
            {"Name": "D16", "Diameter": 16.0},
            {"Name": "D20", "Diameter": 20.0},
        ),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="ETABS Rebar Sizes",
    )

    result = evaluate_column_longitudinal_layouts(
        ColumnLongitudinalLayoutInputs(
            requirement_inputs=ColumnLongitudinalRequirementInputs(
                component_id=COMP,
                section_id=section,
                width_mm=500.0,
                depth_mm=800.0,
                model_identity=model,
                evidence_epoch_id=epoch,
                geometry_source_ref=f"geometry:{section}",
            ),
            clear_cover_mm=30.0,
            tie_diameter_mm=8.0,
            aggregate_max_mm=20.0,
            rebar_catalog=catalog,
            cover_source_ref="project:cover",
            tie_source_ref="project:tie",
            aggregate_source_ref="project:aggregate",
        ),
        authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
    )

    assert result.status == "PROVEN"
    return result


def _projection(
    *,
    model=MODEL,
    epoch=EPOCH,
    readiness_ref=f"readiness:{COMP}",
):
    return ColumnComboEligibilityProjection(
        projection_id="projection:column1:Strength:ULS",
        component_id=COMP,
        design_combo_identity=("Strength", "ULS"),
        normalized_definition_fingerprint="combo-definition:ULS",
        constituent_facts=(
            ComboConstituentEligibilityFact(
                name="G",
                scale_factor="1",
                cname_type="LOAD_CASE",
                case_type="LinStatic",
            ),
        ),
        combo_pattern="SUPPORTED_STATIC_LINEAR",
        reconstruction_authority="STATIC_LINEAR_EXACT_DESIGN_STATE",
        reconstruction_behavior_refs=(),
        analysis_basis_status="MATCH",
        analysis_basis_ref="analysis-basis:Strength:ULS",
        component_readiness_status="READY",
        component_readiness_ref=readiness_ref,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        eligibility_state=ColumnComboEligibilityState.ELIGIBLE,
        blockers=(),
        provenance_refs=("projection:provenance",),
    )


def _row(
    source_row_id: str,
    *,
    area: str,
    warning: str = "",
    model=MODEL,
    epoch=EPOCH,
    design_section=SECTION,
):
    return FactualColumnDesignResultRow(
        source_row_id=source_row_id,
        component_id=COMP,
        unique_name="U1",
        story="Story1",
        label="C1",
        assigned_section=SECTION,
        design_section=design_section,
        my_option=2,
        pmm_combo="ULS",
        location_mm=Decimal("500"),
        pmm_area_mm2=Decimal(area),
        error_summary="",
        warning_summary=warning,
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        source_refs=(f"source:{source_row_id}",),
    )


def _promotion(
    *,
    projection=None,
    warning="",
    model=MODEL,
    epoch=EPOCH,
    design_section=SECTION,
):
    projection = _projection(model=model, epoch=epoch) if projection is None else projection

    rows = (
        _row(
            "row:1",
            area="4200",
            warning=warning,
            model=model,
            epoch=epoch,
            design_section=design_section,
        ),
        _row(
            "row:2",
            area="4600",
            model=model,
            epoch=epoch,
            design_section=design_section,
        ),
    )

    factual = FactualColumnDesignResultPopulation(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        expected_component_ids=(COMP,),
        attempted_component_ids=(COMP,),
        captured_component_ids=(COMP,),
        reported_result_row_count=len(rows),
        rows=rows,
        source_refs=("capture:fixture",),
    )

    return promote_etabs_required_rebar(
        factual,
        combo_eligibility_projections=(projection,),
    )


def _policy():
    return ColumnLongitudinalSelectionPolicyInput(
        policy_id="PROJECT_COLUMN_REBAR_POLICY",
        policy_version="v1",
        primary_objective="MIN_TOTAL_AS",
        tie_breakers=(
            "MIN_BAR_COUNT",
            "MIN_BAR_DIAMETER",
        ),
        review_ref="review:column-selection-policy:v1",
    )


def _inputs(
    *,
    component_id=COMP,
    layout=None,
    readiness_binding=None,
    promotion=None,
    projections=None,
):
    readiness_binding = (
        _readiness_binding()
        if readiness_binding is None
        else readiness_binding
    )
    projection = _projection(
        model=readiness_binding.model_fingerprint,
        epoch=readiness_binding.evidence_epoch_id,
        readiness_ref=readiness_binding.readiness_ref,
    )

    return ColumnLongitudinalSelectionInputs(
        component_id=component_id,
        layout_authority=_layout() if layout is None else layout,
        readiness_binding=readiness_binding,
        etabs_required_rebar=(
            _promotion(projection=projection)
            if promotion is None
            else promotion
        ),
        combo_eligibility_projections=(
            (projection,)
            if projections is None
            else tuple(projections)
        ),
        policy=_policy(),
    )


def test_exact_authority_join_reconciles_without_selecting_rebar():
    result = reconcile_column_longitudinal_selection_contract(_inputs())

    assert result.status == STATUS_RECONCILED
    assert result.reconciled
    assert result.blockers == ()
    assert len(result.eligible_candidate_ids) > 0
    assert len(result.etabs_requirement_ids) == 2
    assert result.combo_projection_ids == (
        "projection:column1:Strength:ULS",
    )
    assert result.model_fingerprint == MODEL
    assert result.evidence_epoch_id == EPOCH
    assert result.readiness_ref == f"readiness:{COMP}"
    assert not hasattr(result, "selected_candidate")


def test_component_identity_mismatch_is_explicitly_blocked():
    result = reconcile_column_longitudinal_selection_contract(
        _inputs(component_id="column:other")
    )

    assert not result.reconciled
    assert BLOCK_COMPONENT_ID_MISMATCH in result.blockers


def test_model_and_epoch_must_join_exactly():
    wrong_model = reconcile_column_longitudinal_selection_contract(
        _inputs(layout=_layout(model="model:other"))
    )
    assert BLOCK_MODEL_CONTEXT_MISMATCH in wrong_model.blockers

    wrong_epoch = reconcile_column_longitudinal_selection_contract(
        _inputs(layout=_layout(epoch="epoch:other"))
    )
    assert BLOCK_EVIDENCE_EPOCH_MISMATCH in wrong_epoch.blockers


def test_fnd_col_2_readiness_must_be_ready():
    blocked_readiness = replace(_readiness(), status="BLOCKED")
    binding = _readiness_binding(readiness=blocked_readiness)

    result = reconcile_column_longitudinal_selection_contract(
        _inputs(readiness_binding=binding)
    )

    assert BLOCK_READINESS_NOT_READY in result.blockers


def test_incomplete_p8a_promotion_cannot_cross_selection_contract():
    projection = _projection()
    promotion = _promotion(
        projection=projection,
        warning="ETABS design warning",
    )

    result = reconcile_column_longitudinal_selection_contract(
        _inputs(
            promotion=promotion,
            projections=(projection,),
        )
    )

    assert BLOCK_P8A_PROMOTION_INCOMPLETE in result.blockers


def test_every_required_rebar_row_must_retain_its_exact_projection_binding():
    result = reconcile_column_longitudinal_selection_contract(
        _inputs(projections=())
    )

    assert BLOCK_PROJECTION_BINDING in result.blockers


def test_design_section_must_match_fnd_col_1_section_authority():
    projection = _projection()
    promotion = _promotion(
        projection=projection,
        design_section="OTHER_SECTION",
    )

    result = reconcile_column_longitudinal_selection_contract(
        _inputs(
            promotion=promotion,
            projections=(projection,),
        )
    )

    assert BLOCK_DESIGN_SECTION_MISMATCH in result.blockers


def test_policy_has_no_defaults_and_preserves_reviewed_tie_break_order():
    with pytest.raises(TypeError):
        ColumnLongitudinalSelectionPolicyInput()

    policy = _policy()
    assert policy.tie_breakers == (
        "MIN_BAR_COUNT",
        "MIN_BAR_DIAMETER",
    )

    with pytest.raises(
        ColumnLongitudinalSelectionContractError,
        match="duplicates",
    ):
        ColumnLongitudinalSelectionPolicyInput(
            policy_id="p",
            policy_version="v1",
            primary_objective="MIN_TOTAL_AS",
            tie_breakers=("MIN_BAR_COUNT", "MIN_BAR_COUNT"),
            review_ref="review:p",
        )


def test_col4a_contract_layer_contains_no_legacy_selection_execution():
    source = inspect.getsource(subject)

    assert "select_engine_rebar_for_demands" not in source
    assert "select_engine_rebar_from_authorized_demands" not in source
    assert "column_rebar_design_engine" not in source
    assert "ENGINE_SELECTED_REBAR" not in source
