"""Bounded column application composition for PRODUCT-SPINE-COL-1.

Public LIVE execution enters the accepted COLUMN-R1 PUBLIC-A5 composer. That
composer owns no engineering semantics: it binds one trusted factual generation
to the existing Eq7.13, B4B, B5, FND-COL-2, B2 and B6 authorities. Private
underscore seams remain test-only compatibility paths for later column product
stages and never substitute for the public production proof.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from tbdy_engine.application.contracts import ColumnExecutionRequest
from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    ComboAnalysisBasisBinding,
    ComponentReadinessBinding,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    normalized_combo_definition_fingerprint,
)
from tbdy_engine.design.columns.column_longitudinal_production_composition import (
    compose_canonical_column_longitudinal_selection,
)
from tbdy_engine.design.columns.column_longitudinal_selection_policy_factory import (
    build_reviewed_column_longitudinal_selection_policy_input,
)
from tbdy_engine.etabs.oapi.concrete_design import read_design_code_from_session
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnTopologyEvidenceEnvelope,
)
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.integration.etabs_controlled_design_execution import (
    ControlledConcreteDesignResult,
    design_component_scope_ref,
    execute_controlled_concrete_design,
)
from tbdy_engine.integration.etabs_design_lineage import (
    DesignLineageQualification,
    DesignResultIdentity,
    DesignStateIdentity,
    build_design_state_identity,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)
from tbdy_engine.providers.etabs_column_design_procedure_provider import (
    ColumnDesignProcedurePopulation,
    capture_column_design_procedure_population_from_session,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    authorize_candidate_adequacy_policy,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    evaluate_column_longitudinal_layouts,
)
from tbdy_engine.regulatory.column_pmm_authority import authorize_pmm_numerical_policy
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    ColumnTransverseConfinementResult,
    evaluate_column_transverse_confinement_bound,
)
from tbdy_engine.regulatory.fnd_col_2_program import (
    compile_source_bound_fnd_col_2_program,
    execute_source_bound_fnd_col_2_with_artifact,
)
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    FND_COL_1_AUTHORITY_CATALOG,
)
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import (
    FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
)
from tbdy_engine.regulatory.sources.fnd_col_4_pmm import (
    FND_COL_4_PMM_AUTHORITY_CATALOG,
)

STATUS_FACTUAL_ACQUISITION_BLOCKED = "FACTUAL_ACQUISITION_BLOCKED"
STATUS_APPLICATION_BLOCKED = "APPLICATION_BLOCKED"
STATUS_READY = "READY"
STATUS_SELECTED = "SELECTED"
STATUS_BLOCKED = "BLOCKED"
STATUS_REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
STATUS_UNRESOLVED = "UNRESOLVED"
BLOCKER_LIVE_FND2_INPUT_LINEAGE = "LIVE_FND2_INPUT_LINEAGE_NOT_QUALIFIED"
BLOCKER_LIVE_DESIGN_LINEAGE = "LIVE_DESIGN_RESULT_LINEAGE_NOT_QUALIFIED"

_COLUMN_CONCRETE_DESIGN_DOMAIN_REF = "design-domain:concrete-column"
_SELECTED_COMBO_POPULATION_REF_PREFIX = "selected-design-combo-population:sha256:"


class ColumnExecutionContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ColumnDomainArtifact:
    component_id: str
    model_fingerprint: str
    evidence_epoch_id: str
    status: str
    blockers: tuple[str, ...]
    fnd_col_2_program: object | None = None
    fnd_col_2_execution: object | None = None
    readiness_binding: ComponentReadinessBinding | None = None
    design_code: object | None = None
    design_procedure: ColumnDesignProcedurePopulation | None = None
    design_state: DesignStateIdentity | None = None
    controlled_design_result: ControlledConcreteDesignResult | None = None
    layout_authority: object | None = None
    longitudinal_selection: object | None = None
    transverse_confinement: ColumnTransverseConfinementResult | None = None

    @property
    def design_result_identity(self) -> DesignResultIdentity | None:
        if self.controlled_design_result is None:
            return None
        return self.controlled_design_result.design_result_identity

    @property
    def design_lineage(self) -> DesignLineageQualification | None:
        if self.controlled_design_result is None:
            return None
        return self.controlled_design_result.design_lineage

    @property
    def factual_design_results(self):
        if self.controlled_design_result is None:
            return None
        return self.controlled_design_result.factual_design_results

    @property
    def design_sections(self):
        if self.controlled_design_result is None:
            return None
        return self.controlled_design_result.design_sections

    @property
    def selected_rebar(self):
        return None if self.longitudinal_selection is None else self.longitudinal_selection.selected_rebar


def execute_column_domain(
    request: ColumnExecutionRequest,
    *,
    acquisition_context: TrustedLiveAcquisitionContext,
) -> ColumnDomainArtifact:
    """Execute the canonical LIVE Column path through qualified FND2 and controlled B6."""
    if not isinstance(request, ColumnExecutionRequest):
        raise TypeError("request must be ColumnExecutionRequest")
    if not isinstance(acquisition_context, TrustedLiveAcquisitionContext):
        raise TypeError("acquisition_context must be TrustedLiveAcquisitionContext")

    # Lazy import keeps this canonical application entry point free of a module
    # cycle while PUBLIC-A5 reuses the bounded callbacks below.
    from tbdy_engine.application.column_public_a5 import execute_public_a5_column

    return execute_public_a5_column(
        request,
        acquisition_context=acquisition_context,
        execute_fnd2=_execute_fnd2,
        complete_after_fnd2=_complete_public_b6_after_fnd2,
    )


def _execute_fnd2(request, *, model_fingerprint, evidence_epoch_id, fnd_col_2_inputs):
    """Non-public seam valid only after an upstream caller has qualified input lineage."""
    program = compile_source_bound_fnd_col_2_program(fnd_col_2_inputs)
    execution = execute_source_bound_fnd_col_2_with_artifact(fnd_col_2_inputs)
    if execution.snapshot.plan_identity != program.plan.plan_identity:
        raise ColumnExecutionContractError("FND-COL-2 compile/execution plan identity mismatch")
    readiness = execution.readiness
    binding = None
    if readiness is not None:
        record = execution.readiness_records[0]
        binding = ComponentReadinessBinding(
            readiness=readiness,
            model_fingerprint=model_fingerprint,
            evidence_epoch_id=evidence_epoch_id,
            readiness_ref=f"fnd-col-2:{record.readiness_instance_ref.value}",
            provenance_refs=tuple(
                dict.fromkeys(
                    (
                        f"fnd-col-2-plan:{record.plan_identity}",
                        *record.evidence_refs,
                        *readiness.source_refs,
                    )
                )
            ),
        )
    if readiness is None:
        status, blockers = STATUS_BLOCKED, ("FND_COL_2_TYPED_READINESS_NOT_EMITTED",)
    elif readiness.status == STATUS_READY:
        status, blockers = STATUS_READY, ()
    elif readiness.status in {STATUS_BLOCKED, STATUS_REANALYSIS_REQUIRED, STATUS_UNRESOLVED}:
        status, blockers = readiness.status, tuple(readiness.blocked_items)
    else:
        raise ColumnExecutionContractError(
            f"unsupported FND-COL-2 readiness status: {readiness.status}"
        )
    if readiness is not None and readiness.component_id != request.component_id:
        raise ColumnExecutionContractError("FND-COL-2 readiness component does not match request")
    return ColumnDomainArtifact(
        component_id=request.component_id,
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=evidence_epoch_id,
        status=status,
        blockers=blockers,
        fnd_col_2_program=program,
        fnd_col_2_execution=execution,
        readiness_binding=binding,
    )


def _selected_combo_population_ref(selection) -> str:
    refs = tuple(getattr(selection, "source_refs", ()) or ())
    matches = tuple(
        ref for ref in refs if ref.startswith(_SELECTED_COMBO_POPULATION_REF_PREFIX)
    )
    if len(matches) != 1:
        raise ColumnExecutionContractError(
            "selected design-combo population must expose exactly one canonical population ref"
        )
    return matches[0]


def _build_exact_combo_basis_bindings(
    *,
    column: ColumnDomainArtifact,
    analysis_execution: AnalysisExecutionResult,
    selected_combo_population,
    combo_definitions,
    flattened_combos,
) -> tuple[tuple[ComboAnalysisBasisBinding, ...], tuple[str, ...]]:
    """Bind each factual design combo to the exact qualified B5 result generation."""
    if not analysis_execution.qualification.qualified:
        raise ColumnExecutionContractError(
            "B6 composition requires qualified B5 analysis lineage"
        )
    qualified_result = analysis_execution.qualification.require_qualified_result()
    if qualified_result.identity_ref != analysis_execution.analysis_result_identity.identity_ref:
        raise ColumnExecutionContractError(
            "B5 qualification/result identity mismatch at B6 composition"
        )
    if (
        selected_combo_population.model_fingerprint != column.model_fingerprint
        or selected_combo_population.evidence_epoch_id != column.evidence_epoch_id
    ):
        raise ColumnExecutionContractError(
            "selected design-combo population model/EvidenceEpoch mismatch"
        )

    definitions = tuple(combo_definitions)
    definition_by_name = {item.name: item for item in definitions}
    if len(definition_by_name) != len(definitions):
        raise ColumnExecutionContractError("duplicate factual design-combo definition name")
    flattened = tuple(flattened_combos)
    flattened_by_name = {name: tuple(leaves) for name, leaves in flattened}
    if len(flattened_by_name) != len(flattened):
        raise ColumnExecutionContractError("duplicate flattened design-combo name")

    exact_case_scope = frozenset(analysis_execution.manifest.scope.case_names)
    selected_population_ref = _selected_combo_population_ref(selected_combo_population)
    bindings: list[ComboAnalysisBasisBinding] = []
    definition_refs: list[str] = []

    for row in selected_combo_population.rows:
        definition = definition_by_name.get(row.combo_name)
        leaves = flattened_by_name.get(row.combo_name)
        if definition is None or leaves is None:
            raise ColumnExecutionContractError(
                f"selected design combo {row.combo_name!r} lost factual definition/leaf binding"
            )
        leaf_case_names = frozenset(name for name, _scale in leaves)
        if not leaf_case_names or not leaf_case_names.issubset(exact_case_scope):
            raise ColumnExecutionContractError(
                f"selected design combo {row.combo_name!r} is not covered by exact B5 result scope"
            )
        definition_ref = normalized_combo_definition_fingerprint(definition)
        evidence = AnalysisBasisEligibilityEvidence(
            status_value="MATCH",
            compatibility_ref=analysis_execution.analysis_result_identity.identity_ref,
            provenance_refs=(
                analysis_execution.qualification.qualification_ref,
                analysis_execution.execution_proof_ref,
            ),
        )
        binding = ComboAnalysisBasisBinding(
            design_combo_identity=(row.combo_type, row.combo_name),
            evidence=evidence,
            normalized_definition_fingerprint=definition_ref,
            model_fingerprint=column.model_fingerprint,
            evidence_epoch_id=column.evidence_epoch_id,
            provenance_refs=(
                row.source_row_ref,
                selected_population_ref,
                definition_ref,
            ),
        )
        bindings.append(binding)
        definition_refs.append(definition_ref)

    if not bindings:
        raise ColumnExecutionContractError(
            "B6 composition requires nonempty exact combo-analysis-basis bindings"
        )
    return (
        tuple(sorted(bindings, key=lambda item: item.design_combo_identity)),
        tuple(sorted(set(definition_refs))),
    )


def _complete_public_b6_after_fnd2(
    column: ColumnDomainArtifact,
    *,
    acquisition_context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    analysis_execution: AnalysisExecutionResult,
    topology,
    selected_combo_population,
    combo_definitions,
    flattened_combos,
) -> ColumnDomainArtifact:
    """Materialize existing DesignState and invoke the sole controlled B6 owner."""
    if not isinstance(column, ColumnDomainArtifact):
        raise TypeError("column must be ColumnDomainArtifact")
    if column.status != STATUS_READY:
        return column
    if column.readiness_binding is None:
        raise ColumnExecutionContractError(
            "qualified FND2 must retain its ComponentReadinessBinding before B6"
        )

    try:
        analysis_lineage = analysis_execution.qualification
        if not analysis_lineage.qualified:
            raise ColumnExecutionContractError(
                "B6 requires qualified parent analysis lineage"
            )
        parent_result = analysis_lineage.require_qualified_result()
        if parent_result.identity_ref != analysis_execution.analysis_result_identity.identity_ref:
            raise ColumnExecutionContractError(
                "B6 parent AnalysisResultIdentity differs from the qualified B5 result"
            )

        topology_envelope = ColumnTopologyEvidenceEnvelope(
            topology=topology,
            model_fingerprint=column.model_fingerprint,
            evidence_epoch_id=column.evidence_epoch_id,
            source_refs=tuple(
                dict.fromkeys(
                    (
                        acquisition_context.session_provenance_ref,
                        owned_scratch.ownership_proof_ref,
                        analysis_lineage.qualification_ref,
                        parent_result.identity_ref,
                        analysis_execution.execution_proof_ref,
                    )
                )
            ),
        )
        design_code = read_design_code_from_session(
            acquisition_context.verified_session
        )
        design_procedure = capture_column_design_procedure_population_from_session(
            acquisition_context.verified_session,
            topology=topology_envelope,
        )
        if not design_procedure.capture_complete:
            raise ColumnExecutionContractError(
                "Column design-procedure factual population is incomplete"
            )

        selected_population_ref = _selected_combo_population_ref(
            selected_combo_population
        )
        combo_bindings, combo_definition_refs = _build_exact_combo_basis_bindings(
            column=column,
            analysis_execution=analysis_execution,
            selected_combo_population=selected_combo_population,
            combo_definitions=combo_definitions,
            flattened_combos=flattened_combos,
        )
        combo_binding_refs = tuple(item.binding_ref for item in combo_bindings)
        component_population_refs = tuple(
            sorted(
                design_component_scope_ref(item.component_id)
                for item in topology_envelope.topology.columns
            )
        )
        state_basis_refs = tuple(
            dict.fromkeys(
                (
                    column.readiness_binding.readiness_ref,
                    parent_result.identity_ref,
                    analysis_lineage.qualification_ref,
                    owned_scratch.ownership_proof_ref,
                    design_code.design_code_ref,
                    design_procedure.design_procedure_ref,
                    selected_population_ref,
                    *combo_definition_refs,
                    *combo_binding_refs,
                )
            )
        )
        provenance_refs = tuple(
            dict.fromkeys(
                (
                    acquisition_context.acquisition_context_ref,
                    acquisition_context.session_provenance_ref,
                    analysis_execution.execution_proof_ref,
                    *selected_combo_population.source_refs,
                    *design_procedure.source_refs,
                    *topology_envelope.source_refs,
                )
            )
        )
        design_state = build_design_state_identity(
            analysis_lineage=analysis_lineage,
            model_fingerprint=column.model_fingerprint,
            evidence_epoch_id=column.evidence_epoch_id,
            design_code_ref=design_code.design_code_ref,
            design_domain_ref=_COLUMN_CONCRETE_DESIGN_DOMAIN_REF,
            design_procedure_ref=design_procedure.design_procedure_ref,
            selected_design_combo_population_ref=selected_population_ref,
            combo_definition_population_refs=combo_definition_refs,
            combo_grain_binding_refs=combo_binding_refs,
            design_component_population_refs=component_population_refs,
            state_basis_refs=state_basis_refs,
            provenance_refs=provenance_refs,
        )
        controlled = execute_controlled_concrete_design(
            context=acquisition_context,
            owned_scratch=owned_scratch,
            analysis_lineage=analysis_lineage,
            topology=topology_envelope,
            design_state=design_state,
        )
        if controlled.design_state.identity_ref != design_state.identity_ref:
            raise ColumnExecutionContractError(
                "controlled B6 result does not retain the exact executed DesignStateIdentity"
            )
        if (
            controlled.design_result_identity.parent_design_state_ref
            != design_state.identity_ref
        ):
            raise ColumnExecutionContractError(
                "DesignResultIdentity is not causally derived from the executed DesignStateIdentity"
            )
        return replace(
            column,
            design_code=design_code,
            design_procedure=design_procedure,
            design_state=design_state,
            controlled_design_result=controlled,
        )
    except Exception:
        return replace(
            column,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys((*column.blockers, BLOCKER_LIVE_DESIGN_LINEAGE))
            ),
        )


def _compose_lane_c_after_qualified_design(
    column: ColumnDomainArtifact,
    *,
    transverse_input: ColumnTransverseConfinementInput,
    design_lineage: DesignLineageQualification,
) -> ColumnDomainArtifact:
    """Join mature Lane-C authority only after longitudinal/B6 causal qualification.

    This does not recreate the reverted early composition seam. In particular,
    application does not reinterpret Ash/Asw, HD/LD applicability or P7 shear
    direction mechanics. Those remain owned by the canonical bound Lane-C
    evaluator, which must receive the same model/epoch/component identity and
    exact qualified design lineage that produced the selected longitudinal cage.
    """
    if not isinstance(column, ColumnDomainArtifact):
        raise TypeError("column must be ColumnDomainArtifact")
    if not isinstance(transverse_input, ColumnTransverseConfinementInput):
        raise TypeError("transverse_input must be ColumnTransverseConfinementInput")
    if not isinstance(design_lineage, DesignLineageQualification):
        raise TypeError("design_lineage must be DesignLineageQualification")
    if column.status != STATUS_SELECTED or column.selected_rebar is None:
        raise ColumnExecutionContractError(
            "Lane-C composition requires canonical ENGINE_SELECTED_REBAR state"
        )
    checks = (
        (transverse_input.component_id, column.component_id, "component"),
        (transverse_input.model_fingerprint, column.model_fingerprint, "model"),
        (
            transverse_input.evidence_epoch_id,
            column.evidence_epoch_id,
            "EvidenceEpoch",
        ),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise ColumnExecutionContractError(f"Lane-C {label} identity mismatch")

    transverse = evaluate_column_transverse_confinement_bound(
        transverse_input,
        selected_rebar=column.selected_rebar,
        design_lineage=design_lineage,
    )
    if not isinstance(transverse, ColumnTransverseConfinementResult):
        raise ColumnExecutionContractError(
            "Lane-C evaluator did not return ColumnTransverseConfinementResult"
        )
    if transverse.component_id != column.component_id:
        raise ColumnExecutionContractError("Lane-C result component identity mismatch")

    blockers = tuple(
        dict.fromkeys(
            (
                *column.blockers,
                *(
                    f"TRANSVERSE_CONFINEMENT:{item}"
                    for item in transverse.blockers
                ),
            )
        )
    )
    status = STATUS_APPLICATION_BLOCKED if blockers else column.status
    return replace(
        column,
        status=status,
        blockers=blockers,
        transverse_confinement=transverse,
    )


def _execute_column_domain_with_qualified_live_fnd2_for_test(
    request, *, model_fingerprint, evidence_epoch_id, fnd_col_2_inputs
):
    column = _execute_fnd2(
        request,
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=evidence_epoch_id,
        fnd_col_2_inputs=fnd_col_2_inputs,
    )
    if column.status != STATUS_READY:
        return column
    return ColumnDomainArtifact(
        component_id=column.component_id,
        model_fingerprint=column.model_fingerprint,
        evidence_epoch_id=column.evidence_epoch_id,
        status=STATUS_APPLICATION_BLOCKED,
        blockers=(BLOCKER_LIVE_DESIGN_LINEAGE,),
        fnd_col_2_program=column.fnd_col_2_program,
        fnd_col_2_execution=column.fnd_col_2_execution,
        readiness_binding=column.readiness_binding,
    )


def _execute_column_domain_with_ready_fixture_for_test(
    request,
    *,
    model_fingerprint,
    evidence_epoch_id,
    fnd_col_2_inputs,
    layout_inputs,
    combo_reconciliation,
    combo_analysis_basis_bindings,
    factual_design_results,
    material_context,
):
    """Test-only READY proof. None of these authoritative objects live in production DTOs."""
    column = _execute_fnd2(
        request,
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=evidence_epoch_id,
        fnd_col_2_inputs=fnd_col_2_inputs,
    )
    if column.status != STATUS_READY:
        return column
    req = layout_inputs.requirement_inputs
    checks = (
        (req.model_identity, model_fingerprint),
        (req.evidence_epoch_id, evidence_epoch_id),
        (combo_reconciliation.model_fingerprint, model_fingerprint),
        (combo_reconciliation.evidence_epoch_id, evidence_epoch_id),
        (factual_design_results.model_fingerprint, model_fingerprint),
        (factual_design_results.evidence_epoch_id, evidence_epoch_id),
        (material_context.model_fingerprint, model_fingerprint),
        (material_context.evidence_epoch_id, evidence_epoch_id),
    )
    if any(actual != expected for actual, expected in checks):
        raise ColumnExecutionContractError(
            "test-only READY evidence identity mismatch"
        )
    if (
        req.component_id != request.component_id
        or material_context.component_id != request.component_id
    ):
        raise ColumnExecutionContractError(
            "test-only READY component identity mismatch"
        )
    if factual_design_results.expected_component_ids != (request.component_id,):
        raise ColumnExecutionContractError(
            "test-only design-result population mismatch"
        )
    bindings = tuple(combo_analysis_basis_bindings)
    if any(
        b.model_fingerprint != model_fingerprint
        or b.evidence_epoch_id != evidence_epoch_id
        for b in bindings
    ):
        raise ColumnExecutionContractError(
            "test-only combo analysis-basis identity mismatch"
        )
    mapping = {b.design_combo_identity: b for b in bindings}
    if len(mapping) != len(bindings):
        raise ColumnExecutionContractError(
            "duplicate test-only combo analysis-basis identity"
        )

    layout = evaluate_column_longitudinal_layouts(
        layout_inputs,
        authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
    )
    selection = compose_canonical_column_longitudinal_selection(
        component_id=request.component_id,
        layout_authority=layout,
        readiness_binding=column.readiness_binding,
        combo_reconciliation=combo_reconciliation,
        combo_analysis_basis_bindings=mapping,
        factual_design_results=factual_design_results,
        selection_policy=build_reviewed_column_longitudinal_selection_policy_input(),
        numerical_policy=authorize_pmm_numerical_policy(
            authority_catalog=FND_COL_4_PMM_AUTHORITY_CATALOG
        ),
        material_context=material_context,
        adequacy_policy=authorize_candidate_adequacy_policy(
            authority_catalog=FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
        ),
    )
    return ColumnDomainArtifact(
        component_id=column.component_id,
        model_fingerprint=column.model_fingerprint,
        evidence_epoch_id=column.evidence_epoch_id,
        status=STATUS_SELECTED if selection.selected else STATUS_APPLICATION_BLOCKED,
        blockers=()
        if selection.selected
        else tuple(selection.blockers or (selection.status,)),
        fnd_col_2_program=column.fnd_col_2_program,
        fnd_col_2_execution=column.fnd_col_2_execution,
        readiness_binding=column.readiness_binding,
        layout_authority=layout,
        longitudinal_selection=selection,
    )


__all__ = [
    "BLOCKER_LIVE_DESIGN_LINEAGE",
    "BLOCKER_LIVE_FND2_INPUT_LINEAGE",
    "ColumnDomainArtifact",
    "ColumnExecutionContractError",
    "STATUS_APPLICATION_BLOCKED",
    "STATUS_FACTUAL_ACQUISITION_BLOCKED",
    "STATUS_REANALYSIS_REQUIRED",
    "STATUS_SELECTED",
    "execute_column_domain",
]
