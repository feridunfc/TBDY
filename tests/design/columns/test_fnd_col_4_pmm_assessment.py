from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import ast
from pathlib import Path

import pytest

import tbdy_engine.design.columns.column_pmm_assessment as subject

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
    ColumnLongitudinalSelectionInputs,
    ColumnLongitudinalSelectionPolicyInput,
    reconcile_column_longitudinal_selection_contract,
)
from tbdy_engine.design.columns.column_pmm_assessment import (
    BLOCKED_MATERIAL_CONTEXT,
    BLOCKED_NUMERICAL_POLICY_DOMAIN,
    COMPLETE,
    COMPLETE_WITH_UNRESOLVED,
    ROW_OUTSIDE_AXIAL,
    ROW_PROVEN,
    ColumnPmmMaterialContextBinding,
    assess_all_column_pmm_candidate_demands,
)
from tbdy_engine.design.columns.combo_pattern_engine import (
    ComboPatternConstituent,
)
from tbdy_engine.design.columns.rebar_catalog import (
    build_rebar_catalog_from_rows,
)
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandState,
)
from tbdy_engine.design.columns.section_capacity import (
    ColumnInteractionEnvelope,
    ColumnSectionMaterial,
    RadialMomentCapacity,
)
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
from tbdy_engine.regulatory.column_pmm_authority import (
    authorize_pmm_numerical_policy,
)
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    FND_COL_1_AUTHORITY_CATALOG,
)
from tbdy_engine.regulatory.sources.fnd_col_4_pmm import (
    FND_COL_4_PMM_AUTHORITY_CATALOG,
)


COMP = "column:1"
MODEL = "model:fixture"
EPOCH = "epoch:fixture"
SECTION = "COL500X800"


def _state(
    case: str,
    end: str,
    station: float,
    n: float,
    m2: float,
    m3: float,
):
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
        constituents=(
            ComboPatternConstituent("G", 1.0),
        ),
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


def _layout():
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

    full = evaluate_column_longitudinal_layouts(
        ColumnLongitudinalLayoutInputs(
            requirement_inputs=(
                ColumnLongitudinalRequirementInputs(
                    component_id=COMP,
                    section_id=SECTION,
                    width_mm=500.0,
                    depth_mm=800.0,
                    model_identity=MODEL,
                    evidence_epoch_id=EPOCH,
                    geometry_source_ref=(
                        "geometry:column:1"
                    ),
                )
            ),
            clear_cover_mm=30.0,
            tie_diameter_mm=8.0,
            aggregate_max_mm=20.0,
            rebar_catalog=catalog,
            cover_source_ref="project:cover",
            tie_source_ref="project:tie",
            aggregate_source_ref="project:aggregate",
        ),
        authority_catalog=(
            FND_COL_1_AUTHORITY_CATALOG
        ),
    )

    assert len(full.eligible_candidates) >= 2

    # Test-only fixture reduction. Production function still consumes
    # the complete supplied authority population.
    return replace(
        full,
        eligible_candidates=(
            full.eligible_candidates[:2]
        ),
    )


def _projection(readiness_ref: str):
    return ColumnComboEligibilityProjection(
        projection_id="projection:column1:Strength:ULS",
        component_id=COMP,
        design_combo_identity=("Strength", "ULS"),
        normalized_definition_fingerprint=(
            "combo-definition:ULS"
        ),
        constituent_facts=(
            ComboConstituentEligibilityFact(
                name="G",
                scale_factor="1",
                cname_type="LOAD_CASE",
                case_type="LinStatic",
            ),
        ),
        combo_pattern="SUPPORTED_STATIC_LINEAR",
        reconstruction_authority=(
            "STATIC_LINEAR_EXACT_DESIGN_STATE"
        ),
        reconstruction_behavior_refs=(),
        analysis_basis_status="MATCH",
        analysis_basis_ref=(
            "analysis-basis:Strength:ULS"
        ),
        component_readiness_status="READY",
        component_readiness_ref=readiness_ref,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        eligibility_state=(
            ColumnComboEligibilityState.ELIGIBLE
        ),
        blockers=(),
        provenance_refs=("projection:provenance",),
    )


def _selection_context():
    readiness = _readiness()

    binding = ComponentReadinessBinding(
        readiness=readiness,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        readiness_ref=f"readiness:{COMP}",
        provenance_refs=("fnd-col-2:fixture",),
    )

    projection = _projection(binding.readiness_ref)

    rows = (
        FactualColumnDesignResultRow(
            source_row_id="row:1",
            component_id=COMP,
            unique_name="U1",
            story="Story1",
            label="C1",
            assigned_section=SECTION,
            design_section=SECTION,
            my_option=2,
            pmm_combo="ULS",
            location_mm=Decimal("500"),
            pmm_area_mm2=Decimal("4200"),
            error_summary="",
            warning_summary="",
            model_fingerprint=MODEL,
            evidence_epoch_id=EPOCH,
            source_refs=("source:row:1",),
        ),
    )

    factual = FactualColumnDesignResultPopulation(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        expected_component_ids=(COMP,),
        attempted_component_ids=(COMP,),
        captured_component_ids=(COMP,),
        reported_result_row_count=1,
        rows=rows,
        source_refs=("capture:fixture",),
    )

    promotion = promote_etabs_required_rebar(
        factual,
        combo_eligibility_projections=(projection,),
    )

    inputs = ColumnLongitudinalSelectionInputs(
        component_id=COMP,
        layout_authority=_layout(),
        readiness_binding=binding,
        etabs_required_rebar=promotion,
        combo_eligibility_projections=(projection,),
        policy=ColumnLongitudinalSelectionPolicyInput(
            policy_id="PROJECT_COLUMN_REBAR_POLICY",
            policy_version="v1",
            primary_objective="MIN_TOTAL_AS",
            tie_breakers=(
                "MIN_BAR_COUNT",
                "MIN_BAR_DIAMETER",
            ),
            review_ref=(
                "review:column-selection-policy:v1"
            ),
        ),
    )

    contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    assert contract.reconciled

    return inputs, contract


def _material(
    *,
    fck: float = 30.0,
    model: str = MODEL,
    epoch: str = EPOCH,
):
    return ColumnPmmMaterialContextBinding(
        component_id=COMP,
        section_id=SECTION,
        material_name=f"C{fck:g}",
        material=ColumnSectionMaterial(
            fck_mpa=fck,
            fcd_mpa=20.0,
            fyd_mpa=365.0,
        ),
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        section_material_binding_ref=(
            "section-material:column:1"
        ),
        concrete_strength_source_refs=(
            "used-rc-material:C30:Fc",
        ),
        concrete_design_strength_review_refs=(
            "review:fcd:C30",
        ),
        steel_design_strength_review_refs=(
            "review:fyd:B420C",
        ),
    )


def _policy():
    return authorize_pmm_numerical_policy(
        authority_catalog=(
            FND_COL_4_PMM_AUTHORITY_CATALOG
        )
    )


def _patch_capacity(monkeypatch):
    calls = []

    def fake_envelope(
        *,
        width_mm,
        depth_mm,
        bars,
        material,
        target_n_compression_n,
        angle_count,
        axial_tolerance_n,
    ):
        calls.append(
            (
                width_mm,
                depth_mm,
                len(bars),
                target_n_compression_n,
                angle_count,
                axial_tolerance_n,
            )
        )

        outside = (
            len(bars) > 4
            and target_n_compression_n
            == 900_000.0
        )

        return ColumnInteractionEnvelope(
            target_n_compression_n=(
                target_n_compression_n
            ),
            states=(),
            status=(
                "OUTSIDE_AXIAL_CAPACITY"
                if outside
                else "PROVEN"
            ),
            angle_step_deg=(
                360.0 / float(angle_count)
            ),
        )

    def fake_radial(
        envelope,
        *,
        demand_m2_nmm,
        demand_m3_nmm,
    ):
        return RadialMomentCapacity(
            demand_angle_deg=0.0,
            capacity_nmm=1_000_000_000.0,
            boundary_m2_nmm=(
                1_000_000_000.0
            ),
            boundary_m3_nmm=0.0,
            status="PROVEN",
        )

    monkeypatch.setattr(
        subject,
        "build_interaction_envelope_at_axial_force",
        fake_envelope,
    )

    monkeypatch.setattr(
        subject,
        "radial_moment_capacity",
        fake_radial,
    )

    return calls


def test_every_candidate_x_every_demand_is_assessed_exactly_once(
    monkeypatch,
):
    inputs, contract = _selection_context()
    calls = _patch_capacity(monkeypatch)

    result = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=_policy(),
        material_context=_material(),
    )

    assert result.enumeration_complete

    assert len(result.candidate_ids) == 2
    assert len(result.demand_state_ids) == 2

    assert result.expected_assessment_count == 4
    assert len(result.assessment_rows) == 4
    assert len(calls) == 4

    pairs = {
        (row.candidate_id, row.state_id)
        for row in result.assessment_rows
    }

    assert len(pairs) == 4

    assert all(
        call[4] == 1152
        for call in calls
    )

    assert all(
        call[5] == pytest.approx(1.0)
        for call in calls
    )


def test_unresolved_pair_does_not_stop_remaining_population(
    monkeypatch,
):
    inputs, contract = _selection_context()
    _patch_capacity(monkeypatch)

    result = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=_policy(),
        material_context=_material(),
    )

    assert (
        result.status
        == COMPLETE_WITH_UNRESOLVED
    )

    assert len(result.assessment_rows) == 4

    statuses = {
        row.numerical_status
        for row in result.assessment_rows
    }

    assert ROW_PROVEN in statuses
    assert ROW_OUTSIDE_AXIAL in statuses
    assert result.unresolved_row_count >= 1


def test_no_acceptance_limit_or_candidate_eligibility_is_emitted(
    monkeypatch,
):
    inputs, contract = _selection_context()
    _patch_capacity(monkeypatch)

    result = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=_policy(),
        material_context=_material(),
    )

    assert not hasattr(
        result,
        "selected_candidate",
    )

    assert not hasattr(
        result,
        "eligible_candidates",
    )

    assert all(
        not hasattr(row, "passes")
        for row in result.assessment_rows
    )


def test_exact_model_and_epoch_material_context_are_required(
    monkeypatch,
):
    inputs, contract = _selection_context()
    calls = _patch_capacity(monkeypatch)

    wrong_model = (
        assess_all_column_pmm_candidate_demands(
            inputs=inputs,
            selection_contract=contract,
            numerical_policy=_policy(),
            material_context=_material(
                model="model:other"
            ),
        )
    )

    assert not wrong_model.enumeration_complete
    assert (
        BLOCKED_MATERIAL_CONTEXT
        in wrong_model.blockers
    )
    assert wrong_model.assessment_rows == ()
    assert calls == []

    wrong_epoch = (
        assess_all_column_pmm_candidate_demands(
            inputs=inputs,
            selection_contract=contract,
            numerical_policy=_policy(),
            material_context=_material(
                epoch="epoch:other"
            ),
        )
    )

    assert (
        BLOCKED_MATERIAL_CONTEXT
        in wrong_epoch.blockers
    )
    assert wrong_epoch.assessment_rows == ()
    assert calls == []


def test_numerical_policy_domain_is_fail_closed_before_kernel_execution(
    monkeypatch,
):
    inputs, contract = _selection_context()
    calls = _patch_capacity(monkeypatch)

    result = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=_policy(),
        material_context=_material(fck=20.0),
    )

    assert not result.enumeration_complete
    assert (
        BLOCKED_NUMERICAL_POLICY_DOMAIN
        in result.blockers
    )
    assert result.assessment_rows == ()
    assert calls == []


def test_input_order_does_not_change_assessment_population(
    monkeypatch,
):
    inputs, contract = _selection_context()
    _patch_capacity(monkeypatch)

    first = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=_policy(),
        material_context=_material(),
    )

    reversed_layout = replace(
        inputs.layout_authority,
        eligible_candidates=tuple(
            reversed(
                inputs.layout_authority.eligible_candidates
            )
        ),
    )

    reversed_readiness = replace(
        inputs.readiness_binding.readiness,
        demand_states=tuple(
            reversed(
                inputs.readiness_binding
                .readiness
                .demand_states
            )
        ),
    )

    reversed_binding = replace(
        inputs.readiness_binding,
        readiness=reversed_readiness,
    )

    reversed_inputs = replace(
        inputs,
        layout_authority=reversed_layout,
        readiness_binding=reversed_binding,
    )

    reversed_contract = (
        reconcile_column_longitudinal_selection_contract(
            reversed_inputs
        )
    )

    assert reversed_contract.reconciled

    second = assess_all_column_pmm_candidate_demands(
        inputs=reversed_inputs,
        selection_contract=reversed_contract,
        numerical_policy=_policy(),
        material_context=_material(),
    )

    assert first == second


def test_all_resolved_population_has_neutral_complete_status(
    monkeypatch,
):
    inputs, contract = _selection_context()

    def all_proven_envelope(
        *,
        width_mm,
        depth_mm,
        bars,
        material,
        target_n_compression_n,
        angle_count,
        axial_tolerance_n,
    ):
        return ColumnInteractionEnvelope(
            target_n_compression_n=(
                target_n_compression_n
            ),
            states=(),
            status="PROVEN",
            angle_step_deg=(
                360.0 / float(angle_count)
            ),
        )

    def radial(
        envelope,
        *,
        demand_m2_nmm,
        demand_m3_nmm,
    ):
        return RadialMomentCapacity(
            demand_angle_deg=0.0,
            capacity_nmm=1_000_000_000.0,
            boundary_m2_nmm=(
                1_000_000_000.0
            ),
            boundary_m3_nmm=0.0,
            status="PROVEN",
        )

    monkeypatch.setattr(
        subject,
        "build_interaction_envelope_at_axial_force",
        all_proven_envelope,
    )
    monkeypatch.setattr(
        subject,
        "radial_moment_capacity",
        radial,
    )

    result = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=_policy(),
        material_context=_material(),
    )

    assert result.status == COMPLETE
    assert result.unresolved_row_count == 0
    assert result.resolved_row_count == 4


def test_b2_module_contains_no_selection_authority():
    path = Path(subject.__file__).resolve()

    source = path.read_text(
        encoding="utf-8-sig"
    )

    assert "ENGINE_SELECTED_REBAR" not in source
    assert "select_engine_rebar" not in source
    assert "utilization_limit" not in source

    tree = ast.parse(source)

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(
                alias.name
                for alias in node.names
            )

    assert (
        "tbdy_engine.design.columns."
        "rebar_selection_authority"
        not in imports
    )

    assert (
        "tbdy_engine.design.columns."
        "column_rebar_design_engine"
        not in imports
    )
