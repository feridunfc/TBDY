"""Production B6 -> longitudinal/PMM -> ENGINE_SELECTED_REBAR composition.

Application sequencing only. Every engineering decision is delegated to the
existing combo-reconciliation, ETABS_REQUIRED_REBAR, FND-COL-1, PMM,
candidate-adequacy and ranking owners. No request DTO contains these truths.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.application.column_design_basis import (
    BoundColumnDesignBasis,
    ReviewedColumnDesignBasis,
    bind_reviewed_column_design_basis,
)
from tbdy_engine.application.column_longitudinal_detailing import (
    ColumnLongitudinalDetailingResolution,
    materialize_selected_column_longitudinal_detailing,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    ConcreteDesignComboReconciliation,
    build_actual_selected_combo_population,
    normalized_combo_definition_fingerprint,
    reconcile_concrete_design_combos,
)
from tbdy_engine.design.columns.column_design_result_projection import (
    project_factual_design_results_to_component,
)
from tbdy_engine.design.columns.column_longitudinal_production_composition import (
    CanonicalColumnLongitudinalSelectionComposition,
    compose_canonical_column_longitudinal_selection,
)
from tbdy_engine.design.columns.column_longitudinal_selection_policy_factory import (
    build_reviewed_column_longitudinal_selection_policy_input,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ExpectedConcreteDesignComboPolicy,
)
from tbdy_engine.features.used_rc_material_population import (
    MaterialPopulationReadiness,
    MaterialUsageStatus,
    UsedRcMaterialPopulation,
    build_used_rc_material_population_from_same_verified_session,
)
from tbdy_engine.providers.etabs_column_combo_case_type_provider import (
    EtabsColumnComboCaseTypePopulation,
    project_b5_column_combo_case_types,
)
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    EtabsColumnRebarIntentEvidence,
    capture_etabs_column_rebar_intent_from_session,
)
from tbdy_engine.design.columns.rebar_catalog import RebarCatalog
from tbdy_engine.providers.etabs_rebar_catalog_provider import (
    EtabsRebarCatalogEvidence,
    capture_etabs_rebar_catalog_evidence_from_session,
    promote_live_proven_etabs_rebar_catalog,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    authorize_candidate_adequacy_policy,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    ColumnLongitudinalLayoutAuthorityResult,
    ColumnLongitudinalLayoutInputs,
    ColumnLongitudinalRequirementInputs,
    evaluate_column_longitudinal_layouts,
)
from tbdy_engine.regulatory.column_pmm_authority import authorize_pmm_numerical_policy
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    FND_COL_1_AUTHORITY_CATALOG,
)
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import (
    FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
)
from tbdy_engine.regulatory.sources.fnd_col_4_pmm import (
    FND_COL_4_PMM_AUTHORITY_CATALOG,
)


class ColumnLongitudinalRuntimeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalRuntimeComposition:
    component_id: str
    target_topology: object
    used_material_population: UsedRcMaterialPopulation
    rebar_intent: EtabsColumnRebarIntentEvidence
    rebar_catalog_evidence: EtabsRebarCatalogEvidence
    bound_design_basis: BoundColumnDesignBasis
    case_type_population: EtabsColumnComboCaseTypePopulation
    combo_reconciliation: ConcreteDesignComboReconciliation
    layout_authority: ColumnLongitudinalLayoutAuthorityResult
    selection: CanonicalColumnLongitudinalSelectionComposition
    detailing: ColumnLongitudinalDetailingResolution | None
    tie_diameter_mm: float | None = None
    tie_catalog_ref: str | None = None
    rebar_catalog: RebarCatalog | None = None

    @property
    def selected(self) -> bool:
        return self.selection.selected

    @property
    def selected_rebar(self):
        return self.selection.selected_rebar


def _target_column(topology, component_id: str):
    matches = tuple(item for item in topology.columns if item.component_id == component_id)
    if len(matches) != 1:
        raise ColumnLongitudinalRuntimeError(
            f"strict topology must contain exactly one target component {component_id!r}; got {len(matches)}"
        )
    return matches[0]


def _concrete_usage_and_definition(
    population: UsedRcMaterialPopulation,
    *,
    target,
):
    usages = tuple(
        item
        for item in population.usages
        if item.component_type == "Column"
        and item.component_identity == target.unique_name
        and item.story == target.story
        and item.label == target.column_label
        and item.assigned_property == target.section
        and item.status is MaterialUsageStatus.RESOLVED_CONCRETE_USAGE
    )
    if len(usages) != 1:
        raise ColumnLongitudinalRuntimeError(
            "exact target Column concrete material usage is not uniquely resolved"
        )
    usage = usages[0]
    definitions = tuple(
        item
        for item in population.used_material_definitions
        if item.material_name == usage.material_name
    )
    if len(definitions) != 1:
        raise ColumnLongitudinalRuntimeError(
            "exact target Column concrete material definition is not uniquely resolved"
        )
    return usage, definitions[0]


def _tie_diameter_mm(catalog, tie_size_name: str) -> tuple[float, str]:
    matches = tuple(item for item in catalog.entries if item.name == tie_size_name)
    if len(matches) != 1:
        raise ColumnLongitudinalRuntimeError(
            f"factual tie-size {tie_size_name!r} is not uniquely present in ETABS rebar catalog"
        )
    return matches[0].diameter_mm, matches[0].source_identity


def _required_leaf_case_names(flattened_combos: Sequence[tuple[str, Sequence[tuple[str, float]]]]) -> tuple[str, ...]:
    names = tuple(
        sorted(
            {
                case_name
                for _combo_name, leaves in flattened_combos
                for case_name, _scale in leaves
            }
        )
    )
    if not names:
        raise ColumnLongitudinalRuntimeError("selected design combos have no flattened load-case leaves")
    return names


def compose_column_longitudinal_runtime(
    *,
    component_id: str,
    column_model_fingerprint: str,
    column_evidence_epoch_id: str,
    readiness_binding,
    acquisition_context,
    analysis_execution,
    topology,
    selected_combo_population,
    combo_definitions,
    flattened_combos,
    combo_analysis_basis_bindings,
    controlled_design_result,
    reviewed_design_basis: ReviewedColumnDesignBasis,
    expected_combo_policy: ExpectedConcreteDesignComboPolicy,
) -> ColumnLongitudinalRuntimeComposition:
    """Compose the existing authorities after qualified FND2 and qualified B6."""
    if not isinstance(reviewed_design_basis, ReviewedColumnDesignBasis):
        raise TypeError("reviewed_design_basis must be ReviewedColumnDesignBasis")
    if not isinstance(expected_combo_policy, ExpectedConcreteDesignComboPolicy):
        raise TypeError("expected_combo_policy must be ExpectedConcreteDesignComboPolicy")
    if readiness_binding is None:
        raise ColumnLongitudinalRuntimeError("longitudinal production requires FND2 readiness binding")
    if not controlled_design_result.design_lineage.qualified:
        raise ColumnLongitudinalRuntimeError("longitudinal production requires qualified B6 design lineage")
    if controlled_design_result.design_state.model_fingerprint != column_model_fingerprint:
        raise ColumnLongitudinalRuntimeError("B6 DesignState model fingerprint mismatch")
    if controlled_design_result.design_state.evidence_epoch_id != column_evidence_epoch_id:
        raise ColumnLongitudinalRuntimeError("B6 DesignState EvidenceEpoch mismatch")

    target = _target_column(topology, component_id)
    reviewed_length_unit = topology.reviewed_length_unit

    material_population = build_used_rc_material_population_from_same_verified_session(
        session=acquisition_context.verified_session,
        inventory_identity_namespace=column_model_fingerprint,
    )
    if material_population.readiness is MaterialPopulationReadiness.BLOCKED:
        raise ColumnLongitudinalRuntimeError("same-session factual RC material population is BLOCKED")
    usage, material_definition = _concrete_usage_and_definition(
        material_population,
        target=target,
    )

    rebar_intent = capture_etabs_column_rebar_intent_from_session(
        acquisition_context.verified_session,
        target.section,
        reviewed_length_unit=reviewed_length_unit,
    )
    catalog_evidence = capture_etabs_rebar_catalog_evidence_from_session(
        acquisition_context.verified_session
    )
    catalog = promote_live_proven_etabs_rebar_catalog(
        catalog_evidence,
        reviewed_length_unit=reviewed_length_unit,
        source_name=f"ETABS:{catalog_evidence.table_name}:{acquisition_context.session_provenance_ref}",
    )

    bound_basis = bind_reviewed_column_design_basis(
        reviewed_design_basis,
        component_id=component_id,
        section_id=target.section,
        factual_concrete_usage=usage,
        factual_concrete_definition=material_definition,
        factual_rebar_intent=rebar_intent,
        model_fingerprint=column_model_fingerprint,
        evidence_epoch_id=column_evidence_epoch_id,
    )

    tie_diameter_mm, tie_catalog_ref = _tie_diameter_mm(catalog, rebar_intent.tie_size_name)
    requirement_inputs = ColumnLongitudinalRequirementInputs(
        component_id=component_id,
        section_id=target.section,
        width_mm=target.width_t2_m * 1000.0,
        depth_mm=target.depth_t3_m * 1000.0,
        model_identity=column_model_fingerprint,
        evidence_epoch_id=column_evidence_epoch_id,
        geometry_source_ref=(
            f"{acquisition_context.session_provenance_ref}:strict-column-topology:{target.unique_name}:{target.section}"
        ),
    )
    layout_inputs = ColumnLongitudinalLayoutInputs(
        requirement_inputs=requirement_inputs,
        clear_cover_mm=rebar_intent.cover_mm,
        tie_diameter_mm=tie_diameter_mm,
        aggregate_max_mm=bound_basis.aggregate_max_mm,
        rebar_catalog=catalog,
        cover_source_ref=f"ETABS:PropFrame.GetRebarColumn:{target.section}:cover",
        tie_source_ref=(
            f"ETABS:PropFrame.GetRebarColumn:{target.section}:tie={rebar_intent.tie_size_name}|{tie_catalog_ref}"
        ),
        aggregate_source_ref=bound_basis.aggregate_source_ref,
    )
    layout = evaluate_column_longitudinal_layouts(
        layout_inputs,
        authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
    )

    required_case_names = _required_leaf_case_names(flattened_combos)
    case_type_population = project_b5_column_combo_case_types(
        analysis_execution.manifest.runtime_scope_resolution.case_type_facts,
        required_case_names=required_case_names,
        analysis_result_identity_ref=analysis_execution.analysis_result_identity.identity_ref,
        execution_proof_ref=analysis_execution.execution_proof_ref,
    )

    definition_refs = tuple(
        sorted(normalized_combo_definition_fingerprint(item) for item in combo_definitions)
    )
    actual_combo_population = build_actual_selected_combo_population(
        selected_population=selected_combo_population,
        definitions=combo_definitions,
        definition_model_fingerprint=column_model_fingerprint,
        definition_evidence_epoch_id=column_evidence_epoch_id,
        definition_capture_refs=definition_refs,
    )
    binding_mapping = {
        item.design_combo_identity: item
        for item in tuple(combo_analysis_basis_bindings)
    }
    if len(binding_mapping) != len(tuple(combo_analysis_basis_bindings)):
        raise ColumnLongitudinalRuntimeError("duplicate combo-analysis-basis binding identity")
    reconciliation = reconcile_concrete_design_combos(
        expected_policy=expected_combo_policy,
        actual_population=actual_combo_population,
        current_definitions=combo_definitions,
        current_definition_model_fingerprint=column_model_fingerprint,
        current_definition_evidence_epoch_id=column_evidence_epoch_id,
        current_definition_capture_refs=definition_refs,
        case_types=case_type_population.case_types,
        analysis_basis_by_combo={
            identity: binding.evidence
            for identity, binding in binding_mapping.items()
        },
    )

    design_lineage = controlled_design_result.design_lineage
    target_results = project_factual_design_results_to_component(
        controlled_design_result.factual_design_results,
        component_id=component_id,
        design_result_identity_ref=controlled_design_result.design_result_identity.identity_ref,
        design_lineage_qualification_ref=design_lineage.qualification_ref,
    )
    selection = compose_canonical_column_longitudinal_selection(
        component_id=component_id,
        layout_authority=layout,
        readiness_binding=readiness_binding,
        combo_reconciliation=reconciliation,
        combo_analysis_basis_bindings=binding_mapping,
        factual_design_results=target_results,
        selection_policy=build_reviewed_column_longitudinal_selection_policy_input(),
        numerical_policy=authorize_pmm_numerical_policy(
            authority_catalog=FND_COL_4_PMM_AUTHORITY_CATALOG
        ),
        material_context=bound_basis.material_context,
        adequacy_policy=authorize_candidate_adequacy_policy(
            authority_catalog=FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
        ),
    )
    detailing = None
    if selection.selected:
        if selection.selected_rebar is None:
            raise ColumnLongitudinalRuntimeError(
                "selected longitudinal result lost ENGINE_SELECTED_REBAR artifact"
            )
        detailing = materialize_selected_column_longitudinal_detailing(
            selection.selected_rebar,
            authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
        )

    return ColumnLongitudinalRuntimeComposition(
        component_id=component_id,
        target_topology=target,
        used_material_population=material_population,
        rebar_intent=rebar_intent,
        rebar_catalog_evidence=catalog_evidence,
        bound_design_basis=bound_basis,
        case_type_population=case_type_population,
        combo_reconciliation=reconciliation,
        layout_authority=layout,
        selection=selection,
        detailing=detailing,
        tie_diameter_mm=tie_diameter_mm,
        tie_catalog_ref=tie_catalog_ref,
    )


__all__ = [
    "ColumnLongitudinalRuntimeComposition",
    "ColumnLongitudinalRuntimeError",
    "compose_column_longitudinal_runtime",
]
