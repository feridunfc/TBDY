"""Canonical Column application composition for COLUMN-R1.

Public LIVE execution enters the accepted PUBLIC-A5 path, preserving the sole
B4B/B5/FND2/B6 lifecycle. Once FND2 and controlled B6 are qualified, optional
reviewed production dependencies may continue the same causal generation into
the existing longitudinal/PMM/ENGINE_SELECTED_REBAR authorities. Application
owns sequencing and identity joins only; no engineering equation is duplicated
here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import partial

from tbdy_engine.application.column_design_basis import ReviewedColumnDesignBasis
from tbdy_engine.application.column_final_cage import (
    ReviewedColumnFinalCageContext,
    apply_reviewed_final_cage_to_transverse_input,
)
from tbdy_engine.application.column_limited_shear_runtime import (
    ReviewedLimitedColumnShearRuntimeContext,
    compose_column_limited_shear_runtime,
)
from tbdy_engine.application.column_longitudinal_runtime import (
    ColumnLongitudinalRuntimeComposition,
    compose_column_longitudinal_runtime,
)
from tbdy_engine.application.column_p7_runtime import (
    ReviewedColumnP7RuntimeContext,
    ReviewedColumnShortColumnContext,
    compose_column_p7_runtime,
)
from tbdy_engine.application.column_vc_runtime import (
    ReviewedColumnVcRuntimeContext,
    apply_reviewed_vc_to_transverse_input,
)
from tbdy_engine.application.contracts import ColumnExecutionRequest
from tbdy_engine.checks.column_axial_selection import ColumnDemandAvailability
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
from tbdy_engine.design.columns.free_length_basis import ColumnFreeLengthResolution
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.etabs.oapi.concrete_design import read_design_code_from_session
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnTopologyEvidenceEnvelope,
    ExpectedConcreteDesignComboPolicy,
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
from tbdy_engine.providers.etabs_column_axial_b5_provider import (
    capture_b5_bound_column_axial_evidence,
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
from tbdy_engine.regulatory.column_shear_limited_program import (
    LimitedColumnShearRun,
)
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    ColumnTransverseConfinementResult,
    ShortColumnTransverseFacts,
    TransverseDirectionFacts,
    evaluate_column_transverse_confinement_bound,
)
from tbdy_engine.regulatory.fnd_col_2_program import (
    compile_source_bound_fnd_col_2_program,
    execute_source_bound_fnd_col_2_with_artifact,
)
from tbdy_engine.regulatory.vs5_column_axial_program import (
    ReviewedVs5ColumnAxialContext,
    VS5ColumnAxialRun,
    run_vs5_column_axial,
)
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceBundle,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    VS6P7ColumnShearRun,
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
BLOCKER_LONGITUDINAL_PRODUCTION = "LONGITUDINAL_PRODUCTION_NOT_CLOSED"
BLOCKER_TRANSVERSE_PRODUCTION = "TRANSVERSE_CONFINEMENT_PRODUCTION_NOT_CLOSED"
BLOCKER_P7_PRODUCTION = "P7_PRODUCTION_NOT_CLOSED"
BLOCKER_LIMITED_SHEAR_PRODUCTION = "LIMITED_SHEAR_PRODUCTION_NOT_CLOSED"

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
    longitudinal_runtime: ColumnLongitudinalRuntimeComposition | None = None
    transverse_confinement: ColumnTransverseConfinementResult | None = None
    column_axial_vs5: VS5ColumnAxialRun | None = None
    column_shear_p7: VS6P7ColumnShearRun | None = None
    column_shear_limited: LimitedColumnShearRun | None = None
    column_shear_evidence: ColumnShearDemandEvidenceBundle | None = None
    final_transverse_cage: ReviewedColumnFinalCageContext | None = None
    free_length: ColumnFreeLengthResolution | None = None
    a23_demand_states: tuple[ColumnDemandState, ...] = ()

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



A37_SHEAR_ROUTE_NONE = "NONE"
A37_SHEAR_ROUTE_P7_ORDINARY = "P7_ORDINARY"
A37_SHEAR_ROUTE_P7_SHORT = "P7_SHORT"
A37_SHEAR_ROUTE_LIMITED_775 = "LIMITED_775"


def _resolve_a37_shear_route(
    *,
    high_ductility_applies: bool | None,
    limited_ductility_applies: bool | None,
    short_column_context: ReviewedColumnShortColumnContext | None,
    p7_context_present: bool,
    limited_context_present: bool,
    downstream_shear_required: bool,
) -> str:
    requested = (
        p7_context_present
        or limited_context_present
        or downstream_shear_required
    )
    if not requested:
        return A37_SHEAR_ROUTE_NONE

    if short_column_context is None:
        raise ColumnExecutionContractError(
            "A37 short-column applicability must be explicitly reviewed"
        )

    high = high_ductility_applies
    limited = limited_ductility_applies
    if (high is True) == (limited is True):
        raise ColumnExecutionContractError(
            "A37 shear routing requires exactly one proven "
            "HIGH or LIMITED ductility family"
        )

    if short_column_context.short_column_applies:
        if not p7_context_present:
            raise ColumnExecutionContractError(
                "TBDY 7.3.8/7.7.6 short-column route requires "
                "reviewed P7 capacity-state context"
            )
        if limited_context_present:
            raise ColumnExecutionContractError(
                "short-column route forbids ordinary §7.7.5 "
                "limited-shear context"
            )
        return A37_SHEAR_ROUTE_P7_SHORT

    if high is True:
        if limited_context_present:
            raise ColumnExecutionContractError(
                "HIGH ordinary route forbids LIMITED shear context"
            )
        if not p7_context_present:
            if downstream_shear_required:
                raise ColumnExecutionContractError(
                    "HIGH final shear requires reviewed P7 context"
                )
            return A37_SHEAR_ROUTE_NONE
        return A37_SHEAR_ROUTE_P7_ORDINARY

    if p7_context_present:
        raise ColumnExecutionContractError(
            "ordinary LIMITED route forbids HIGH P7 context"
        )
    if not limited_context_present:
        if downstream_shear_required:
            raise ColumnExecutionContractError(
                "LIMITED final shear requires reviewed §7.7.5 context"
            )
        return A37_SHEAR_ROUTE_NONE
    return A37_SHEAR_ROUTE_LIMITED_775


def execute_column_domain(
    request: ColumnExecutionRequest,
    *,
    acquisition_context: TrustedLiveAcquisitionContext,
    column_design_basis: ReviewedColumnDesignBasis | None = None,
    expected_combo_policy: ExpectedConcreteDesignComboPolicy | None = None,
    reviewed_vs5_column_axial_context: ReviewedVs5ColumnAxialContext | None = None,
    reviewed_column_p7_context: ReviewedColumnP7RuntimeContext | None = None,
    reviewed_column_short_column_context: ReviewedColumnShortColumnContext | None = None,
    reviewed_column_limited_shear_context: ReviewedLimitedColumnShearRuntimeContext | None = None,
    reviewed_column_final_cage_context: ReviewedColumnFinalCageContext | None = None,
    reviewed_column_vc_context: ReviewedColumnVcRuntimeContext | None = None,
) -> ColumnDomainArtifact:
    """Execute the canonical LIVE Column path without bypassing FND2/B6 gates."""
    if not isinstance(request, ColumnExecutionRequest):
        raise TypeError("request must be ColumnExecutionRequest")
    if not isinstance(acquisition_context, TrustedLiveAcquisitionContext):
        raise TypeError("acquisition_context must be TrustedLiveAcquisitionContext")
    if column_design_basis is not None and not isinstance(column_design_basis, ReviewedColumnDesignBasis):
        raise TypeError("column_design_basis must be ReviewedColumnDesignBasis or None")
    if expected_combo_policy is not None and not isinstance(expected_combo_policy, ExpectedConcreteDesignComboPolicy):
        raise TypeError("expected_combo_policy must be ExpectedConcreteDesignComboPolicy or None")
    if (
        reviewed_vs5_column_axial_context is not None
        and not isinstance(
            reviewed_vs5_column_axial_context,
            ReviewedVs5ColumnAxialContext,
        )
    ):
        raise TypeError(
            "reviewed_vs5_column_axial_context must be "
            "ReviewedVs5ColumnAxialContext or None"
        )

    if (
        reviewed_column_p7_context is not None
        and not isinstance(
            reviewed_column_p7_context,
            ReviewedColumnP7RuntimeContext,
        )
    ):
        raise TypeError(
            "reviewed_column_p7_context must be "
            "ReviewedColumnP7RuntimeContext or None"
        )
    if (
        reviewed_column_short_column_context is not None
        and not isinstance(
            reviewed_column_short_column_context,
            ReviewedColumnShortColumnContext,
        )
    ):
        raise TypeError(
            "reviewed_column_short_column_context must be "
            "ReviewedColumnShortColumnContext or None"
        )
    if (
        reviewed_column_limited_shear_context is not None
        and not isinstance(
            reviewed_column_limited_shear_context,
            ReviewedLimitedColumnShearRuntimeContext,
        )
    ):
        raise TypeError(
            "reviewed_column_limited_shear_context must be "
            "ReviewedLimitedColumnShearRuntimeContext or None"
        )
    if (
        reviewed_column_final_cage_context is not None
        and not isinstance(
            reviewed_column_final_cage_context,
            ReviewedColumnFinalCageContext,
        )
    ):
        raise TypeError(
            "reviewed_column_final_cage_context must be "
            "ReviewedColumnFinalCageContext or None"
        )

    if (
        reviewed_column_vc_context is not None
        and not isinstance(
            reviewed_column_vc_context,
            ReviewedColumnVcRuntimeContext,
        )
    ):
        raise TypeError(
            "reviewed_column_vc_context must be "
            "ReviewedColumnVcRuntimeContext or None"
        )

    from tbdy_engine.application.column_public_a5 import execute_public_a5_column

    completion = _complete_public_b6_after_fnd2
    if (
        column_design_basis is not None
        or expected_combo_policy is not None
        or reviewed_vs5_column_axial_context is not None
        or reviewed_column_p7_context is not None
        or reviewed_column_short_column_context is not None
        or reviewed_column_limited_shear_context is not None
        or reviewed_column_final_cage_context is not None
        or reviewed_column_vc_context is not None
    ):
        completion = partial(
            _complete_public_b6_after_fnd2,
            column_design_basis=column_design_basis,
            expected_combo_policy=expected_combo_policy,
            reviewed_vs5_column_axial_context=reviewed_vs5_column_axial_context,
            reviewed_column_p7_context=reviewed_column_p7_context,
            reviewed_column_short_column_context=reviewed_column_short_column_context,
            reviewed_column_limited_shear_context=reviewed_column_limited_shear_context,
            reviewed_column_final_cage_context=(
                reviewed_column_final_cage_context
            ),
            reviewed_column_vc_context=reviewed_column_vc_context,
        )

    return execute_public_a5_column(
        request,
        acquisition_context=acquisition_context,
        execute_fnd2=_execute_fnd2,
        reviewed_story_translation_tolerance=(
            None
            if column_design_basis is None
            else column_design_basis.story_translation_tolerance
        ),
        complete_after_fnd2=completion,
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


def _decode_canonical_a23_demand_states(
    canonical_second_order: Mapping[str, object],
    *,
    component_id: str,
) -> tuple[ColumnDemandState, ...]:
    # Restore canonical A23 final states without recalculation or selection.
    if not isinstance(canonical_second_order, Mapping):
        raise TypeError("canonical_second_order must be a mapping")

    payload = canonical_second_order.get("canonical_second_order")
    if not isinstance(payload, Mapping):
        raise ColumnExecutionContractError(
            "canonical second-order payload is missing"
        )

    blockers = tuple(payload.get("blockers", ()) or ())
    reanalysis = tuple(payload.get("reanalysis_items", ()) or ())
    if blockers:
        raise ColumnExecutionContractError(
            "canonical A23 demand population is blocked: "
            + "|".join(str(item) for item in blockers)
        )
    if reanalysis:
        raise ColumnExecutionContractError(
            "canonical A23 demand population requires reanalysis: "
            + "|".join(str(item) for item in reanalysis)
        )

    raw_states = payload.get("expected_final_states")
    if not isinstance(raw_states, (tuple, list)) or not raw_states:
        raise ColumnExecutionContractError(
            "canonical A23 final demand-state population is empty"
        )

    states: list[ColumnDemandState] = []
    for raw in raw_states:
        if not isinstance(raw, Mapping):
            raise ColumnExecutionContractError(
                "canonical A23 final state must be a mapping"
            )
        try:
            state = ColumnDemandState(**dict(raw))
        except (TypeError, ValueError) as exc:
            raise ColumnExecutionContractError(
                f"canonical A23 final state cannot be restored: {exc}"
            ) from exc
        if state.component_id != component_id:
            raise ColumnExecutionContractError(
                "canonical A23 state component identity mismatch"
            )
        states.append(state)

    state_ids = tuple(item.state_id for item in states)
    if len(set(state_ids)) != len(state_ids):
        raise ColumnExecutionContractError(
            "canonical A23 final demand-state population contains duplicate state_id"
        )

    return tuple(states)


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


def _run_a36_vs5_axial(
    *,
    column: ColumnDomainArtifact,
    runtime: ColumnLongitudinalRuntimeComposition,
    acquisition_context: TrustedLiveAcquisitionContext,
    analysis_execution: AnalysisExecutionResult,
    topology,
    flattened_combos,
    reviewed_vs5_column_axial_context: ReviewedVs5ColumnAxialContext,
) -> VS5ColumnAxialRun:
    # Execute the existing source-bound VS5 owner once and retain its truth.
    if not isinstance(
        reviewed_vs5_column_axial_context,
        ReviewedVs5ColumnAxialContext,
    ):
        raise TypeError(
            "reviewed_vs5_column_axial_context must be ReviewedVs5ColumnAxialContext"
        )

    target = runtime.target_topology
    basis = runtime.bound_design_basis
    evidence = capture_b5_bound_column_axial_evidence(
        session=acquisition_context.verified_session,
        analysis_execution=analysis_execution,
        topology=topology,
        target=target,
        material_context=basis.material_context,
        model_fingerprint=column.model_fingerprint,
        evidence_epoch_id=column.evidence_epoch_id,
        reviewed=reviewed_vs5_column_axial_context,
        flattened_combos=flattened_combos,
    )
    if evidence.model_fingerprint != column.model_fingerprint:
        raise ColumnExecutionContractError(
            "A36 VS5 factual bundle model identity mismatch"
        )
    if evidence.evidence_epoch_id != column.evidence_epoch_id:
        raise ColumnExecutionContractError(
            "A36 VS5 factual bundle EvidenceEpoch mismatch"
        )

    vs5 = run_vs5_column_axial(
        evidence=evidence,
        reviewed=reviewed_vs5_column_axial_context,
        unique_name=target.unique_name,
    )
    nd = vs5.ts500_demand
    if (
        nd.availability is not ColumnDemandAvailability.RESOLVED
        or nd.demand_kn is None
    ):
        raise ColumnExecutionContractError(
            "A36 requires source-bound RESOLVED VS5 TS500 Nd"
        )

    reviewed_high = (
        reviewed_vs5_column_axial_context
        .tbdy_7312_high_ductility_applies
    )
    if (
        reviewed_high is not None
        and basis.high_ductility_applies is not None
        and reviewed_high != basis.high_ductility_applies
    ):
        raise ColumnExecutionContractError(
            "A36 VS5/design-basis high-ductility applicability mismatch"
        )
    return vs5


def _compose_a36_transverse_input(
    *,
    column: ColumnDomainArtifact,
    runtime: ColumnLongitudinalRuntimeComposition,
    acquisition_context: TrustedLiveAcquisitionContext,
    analysis_execution: AnalysisExecutionResult,
    topology,
    flattened_combos,
    controlled_design_result: ControlledConcreteDesignResult,
    reviewed_vs5_column_axial_context: ReviewedVs5ColumnAxialContext,
    reviewed_column_short_column_context: ReviewedColumnShortColumnContext | None = None,
    reviewed_column_final_cage_context: ReviewedColumnFinalCageContext | None = None,
    reviewed_column_vc_context: ReviewedColumnVcRuntimeContext | None = None,
) -> ColumnTransverseConfinementInput:
    """Materialize source-bound A36 facts; regulatory evaluation stays elsewhere."""

    if not isinstance(
        reviewed_vs5_column_axial_context,
        ReviewedVs5ColumnAxialContext,
    ):
        raise TypeError(
            "reviewed_vs5_column_axial_context must be ReviewedVs5ColumnAxialContext"
        )

    if runtime.component_id != column.component_id:
        raise ColumnExecutionContractError(
            "A36 longitudinal runtime component identity mismatch"
        )

    target = runtime.target_topology
    intent = runtime.rebar_intent
    basis = runtime.bound_design_basis

    if target.component_id != column.component_id:
        raise ColumnExecutionContractError(
            "A36 strict-topology component identity mismatch"
        )
    if basis.component_id != column.component_id:
        raise ColumnExecutionContractError(
            "A36 bound design-basis component identity mismatch"
        )

    if basis.transverse_basis_blockers:
        raise ColumnExecutionContractError(
            "A36 transverse design basis is blocked: "
            + "|".join(basis.transverse_basis_blockers)
        )
    if basis.transverse_fywk_mpa is None:
        raise ColumnExecutionContractError(
            "A36 reviewed transverse fywk is unavailable"
        )

    if runtime.tie_diameter_mm is None or runtime.tie_catalog_ref is None:
        raise ColumnExecutionContractError(
            "A36 factual TieSize catalog diameter is unavailable"
        )

    # Supported materializer is rectangular Pattern=1 only.
    if intent.pattern != 1:
        raise ColumnExecutionContractError(
            f"A36 rectangular rebar pattern required; got Pattern={intent.pattern}"
        )

    width_mm = float(target.width_t2_m) * 1000.0
    depth_mm = float(target.depth_t3_m) * 1000.0
    clear_height_mm = (
        float(target.analysis_clear_length_candidate_m) * 1000.0
    )
    cover_mm = float(intent.cover_mm)
    phi_t_mm = float(runtime.tie_diameter_mm)

    if min(
        width_mm,
        depth_mm,
        clear_height_mm,
        cover_mm,
        phi_t_mm,
    ) <= 0.0:
        raise ColumnExecutionContractError(
            "A36 factual section/cover/tie geometry must be positive"
        )

    # CSI Cover = clear cover to outside of confinement steel.
    # TBDY Ack = outside-to-outside confined core.
    core_outer_dir2_mm = width_mm - 2.0 * cover_mm
    core_outer_dir3_mm = depth_mm - 2.0 * cover_mm

    # TBDY bk = axes of outermost transverse reinforcement.
    bk_dir2_mm = core_outer_dir2_mm - phi_t_mm
    bk_dir3_mm = core_outer_dir3_mm - phi_t_mm

    if min(
        core_outer_dir2_mm,
        core_outer_dir3_mm,
        bk_dir2_mm,
        bk_dir3_mm,
    ) <= 0.0:
        raise ColumnExecutionContractError(
            "A36 cover/tie geometry produces non-positive confined core"
        )

    ac_mm2 = width_mm * depth_mm
    ack_mm2 = core_outer_dir2_mm * core_outer_dir3_mm

    if ack_mm2 >= ac_mm2:
        raise ColumnExecutionContractError(
            "A36 confined core Ack must be smaller than gross Ac"
        )

    vs5 = column.column_axial_vs5
    if vs5 is None:
        # Backward-compatible direct materializer seam used by focused A36
        # tests/tools. Production A38 flow pre-retains this exact run on the
        # ColumnDomainArtifact, so production still executes VS5 only once.
        vs5 = _run_a36_vs5_axial(
            column=column,
            runtime=runtime,
            acquisition_context=acquisition_context,
            analysis_execution=analysis_execution,
            topology=topology,
            flattened_combos=flattened_combos,
            reviewed_vs5_column_axial_context=(
                reviewed_vs5_column_axial_context
            ),
        )
    elif not isinstance(vs5, VS5ColumnAxialRun):
        raise ColumnExecutionContractError(
            "A36 retained VS5 axial artifact has invalid type"
        )
    nd = vs5.ts500_demand

    # CSI GetRebarColumn proves directional tie-leg design intent, but the
    # canonical provider explicitly does NOT promote that evidence to
    # final/provided reinforcement authority. Therefore those counts must not
    # be materialized as provided Ash here. Ack/bk geometry remains valid and
    # provided Ash stays explicitly unresolved until a qualified final-cage
    # owner exists.

    cover_ref = (
        f"ETABS:PropFrame.GetRebarColumn:{target.section}:"
        f"Cover={cover_mm:.12g}mm"
    )
    tie_ref = (
        f"ETABS:PropFrame.GetRebarColumn:{target.section}:"
        f"TieSize={intent.tie_size_name}|{runtime.tie_catalog_ref}"
    )
    topology_ref = (
        f"{acquisition_context.session_provenance_ref}:"
        f"strict-column-topology:{target.unique_name}:{target.section}"
    )
    nd_ref = (
        f"VS5:TS500_ND:{target.unique_name}:"
        f"{float(nd.demand_kn):.12g}kN"
    )

    directions = (
        TransverseDirectionFacts(
            direction="DIR2",
            confined_core_width_bk_mm=bk_dir2_mm,
            provided_ash_mm2=None,
            horizontal_leg_spacing_mm=None,
            source_refs=(cover_ref, tie_ref),
        ),
        TransverseDirectionFacts(
            direction="DIR3",
            confined_core_width_bk_mm=bk_dir3_mm,
            provided_ash_mm2=None,
            horizontal_leg_spacing_mm=None,
            source_refs=(cover_ref, tie_ref),
        ),
    )

    fck_mpa = float(basis.material_context.material.fck_mpa)

    selected_rebar = runtime.selection.selected_rebar
    if selected_rebar is None:
        raise ColumnExecutionContractError(
            "A36 requires canonical ENGINE_SELECTED_REBAR"
        )

    source_refs = tuple(
        dict.fromkeys(
            (
                topology_ref,
                cover_ref,
                tie_ref,
                nd_ref,
                controlled_design_result
                .design_result_identity
                .identity_ref,
                selected_rebar.selected_rebar_ref,
                *basis.source_refs,
                *basis.transverse_basis_refs,
                *tuple(nd.provenance),
            )
        )
    )

    short_transverse_facts = None
    if reviewed_column_short_column_context is not None:
        if (
            reviewed_column_short_column_context.component_id
            != column.component_id
        ):
            raise ColumnExecutionContractError(
                "A37 short-column context component mismatch"
            )
        short_transverse_facts = ShortColumnTransverseFacts(
            applies=reviewed_column_short_column_context.short_column_applies,
            actual_short_free_length_mm=reviewed_column_short_column_context.short_free_length_mm,
            required_full_confinement_length_mm=reviewed_column_short_column_context.required_confinement_length_mm,
            infill_fully_adjacent=reviewed_column_short_column_context.infill_fully_adjacent,
            source_refs=reviewed_column_short_column_context.review_refs,
        )

    transverse_input = ColumnTransverseConfinementInput(
        component_id=column.component_id,
        story=target.story,
        section=target.section,
        high_ductility_applies=basis.high_ductility_applies,
        limited_ductility_applies=basis.limited_ductility_applies,
        short_column=short_transverse_facts,

        # No proven production owner yet. Do not default False.
        cantilever_column=None,

        clear_height_mm=clear_height_mm,
        width_mm=width_mm,
        depth_mm=depth_mm,
        gross_area_ac_mm2=ac_mm2,
        confined_core_area_ack_mm2=ack_mm2,
        fck_mpa=fck_mpa,
        fywk_mpa=float(basis.transverse_fywk_mpa),

        # Historical DTO field name; exact semantic value is TS500 Nd.
        # This value governs the TBDY confinement 2/3 quantity branch.
        axial_design_force_nd_n=float(nd.demand_kn) * 1000.0,

        # GetRebarColumn TieSize is factual section design intent and may
        # support deterministic Ack/bk geometry materialization, but the
        # canonical provider explicitly does not grant final/provided-rebar
        # authority. Do not promote it into provided transverse cage truth.
        transverse_diameter_mm=None,

        # TieSpacingLongit alone is not silently reinterpreted into every
        # seismic region/detailing field.
        confinement_spacing_mm=None,
        middle_spacing_mm=None,
        provided_confinement_region_length_mm=None,

        directions=directions,
        arrangement=None,
        source_refs=source_refs,

        fywd_mpa=basis.transverse_fywd_mpa,
        restrained_longitudinal_bar_spacing_mm=None,
        shear_spacing_mm=None,

        model_fingerprint=column.model_fingerprint,
        evidence_epoch_id=column.evidence_epoch_id,
        design_result_ref=(
            controlled_design_result
            .design_result_identity
            .identity_ref
        ),
    )

    if reviewed_column_final_cage_context is not None:
        if runtime.rebar_catalog is None:
            raise ColumnExecutionContractError(
                "A37 final cage requires retained factual RebarCatalog"
            )
        transverse_input = apply_reviewed_final_cage_to_transverse_input(
            transverse_input,
            reviewed=reviewed_column_final_cage_context,
            rebar_catalog=runtime.rebar_catalog,
            p7_run=column.column_shear_p7,
            limited_run=column.column_shear_limited,
        )

    if reviewed_column_vc_context is not None:
        if (
            (column.column_shear_p7 is None)
            == (column.column_shear_limited is None)
            or column.column_shear_evidence is None
            or not column.a23_demand_states
        ):
            raise ColumnExecutionContractError(
                "A37 Vc requires exactly one ductility-specific "
                "shear run, retained B5 evidence and canonical A23 states"
            )
        material_context = runtime.bound_design_basis.material_context
        transverse_input = apply_reviewed_vc_to_transverse_input(
            transverse_input,
            reviewed=reviewed_column_vc_context,
            a23_states=column.a23_demand_states,
            shear_evidence=column.column_shear_evidence,
            p7_run=column.column_shear_p7,
            limited_run=column.column_shear_limited,
            fcd_mpa=material_context.material.fcd_mpa,
            target_unique_name=runtime.target_topology.unique_name,
            material_source_refs=tuple(
                dict.fromkeys(
                    (
                        material_context.section_material_binding_ref,
                        material_context.binding_ref,
                        *material_context.concrete_strength_source_refs,
                        *material_context.concrete_design_strength_review_refs,
                    )
                )
            ),
        )

    return transverse_input


def _continue_selected_column_into_a36(
    column: ColumnDomainArtifact,
    *,
    runtime: ColumnLongitudinalRuntimeComposition,
    acquisition_context: TrustedLiveAcquisitionContext,
    analysis_execution: AnalysisExecutionResult,
    topology,
    flattened_combos,
    controlled_design_result: ControlledConcreteDesignResult,
    reviewed_vs5_column_axial_context: ReviewedVs5ColumnAxialContext | None,
    reviewed_column_short_column_context: ReviewedColumnShortColumnContext | None = None,
    reviewed_column_final_cage_context: ReviewedColumnFinalCageContext | None = None,
    reviewed_column_vc_context: ReviewedColumnVcRuntimeContext | None = None,
) -> ColumnDomainArtifact:
    """Continue selected A35 state into the existing Lane-C owner."""

    # Absence remains explicit. Never invent reviewed VS5 policy and
    # never silently omit the A36 denominator leaf.
    if reviewed_vs5_column_axial_context is None:
        return replace(
            column,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys(
                    (
                        *column.blockers,
                        f"{BLOCKER_TRANSVERSE_PRODUCTION}:"
                        "REVIEWED_VS5_COLUMN_AXIAL_CONTEXT_NOT_AVAILABLE",
                    )
                )
            ),
        )

    axial_column = column
    try:
        vs5 = _run_a36_vs5_axial(
            column=column,
            runtime=runtime,
            acquisition_context=acquisition_context,
            analysis_execution=analysis_execution,
            topology=topology,
            flattened_combos=flattened_combos,
            reviewed_vs5_column_axial_context=(
                reviewed_vs5_column_axial_context
            ),
        )
        axial_column = replace(
            column,
            column_axial_vs5=vs5,
        )

        transverse_input = _compose_a36_transverse_input(
            column=axial_column,
            runtime=runtime,
            acquisition_context=acquisition_context,
            analysis_execution=analysis_execution,
            topology=topology,
            flattened_combos=flattened_combos,
            controlled_design_result=controlled_design_result,
            reviewed_vs5_column_axial_context=(
                reviewed_vs5_column_axial_context
            ),
            reviewed_column_short_column_context=(
                reviewed_column_short_column_context
            ),
            reviewed_column_final_cage_context=(
                reviewed_column_final_cage_context
            ),
            reviewed_column_vc_context=reviewed_column_vc_context,
        )

        return _compose_lane_c_after_qualified_design(
            axial_column,
            transverse_input=transverse_input,
            design_lineage=controlled_design_result.design_lineage,
        )

    except Exception as exc:
        return replace(
            axial_column,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys(
                    (
                        *column.blockers,
                        f"{BLOCKER_TRANSVERSE_PRODUCTION}:"
                        f"{type(exc).__name__}:{exc}",
                    )
                )
            ),
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
    free_length: ColumnFreeLengthResolution | None = None,
    canonical_second_order: Mapping[str, object] | None = None,
    column_design_basis: ReviewedColumnDesignBasis | None = None,
    expected_combo_policy: ExpectedConcreteDesignComboPolicy | None = None,
    reviewed_vs5_column_axial_context: ReviewedVs5ColumnAxialContext | None = None,
    reviewed_column_p7_context: ReviewedColumnP7RuntimeContext | None = None,
    reviewed_column_short_column_context: ReviewedColumnShortColumnContext | None = None,
    reviewed_column_limited_shear_context: ReviewedLimitedColumnShearRuntimeContext | None = None,
    reviewed_column_final_cage_context: ReviewedColumnFinalCageContext | None = None,
    reviewed_column_vc_context: ReviewedColumnVcRuntimeContext | None = None,
) -> ColumnDomainArtifact:
    """Run sole B6 owner, then optionally continue into existing longitudinal authorities."""
    if not isinstance(column, ColumnDomainArtifact):
        raise TypeError("column must be ColumnDomainArtifact")
    if column.status != STATUS_READY:
        return column
    if column.readiness_binding is None:
        raise ColumnExecutionContractError(
            "qualified FND2 must retain its ComponentReadinessBinding before B6"
        )
    if free_length is not None and not isinstance(
        free_length,
        ColumnFreeLengthResolution,
    ):
        raise TypeError(
            "free_length must be ColumnFreeLengthResolution or None"
        )
    if canonical_second_order is not None and not isinstance(
        canonical_second_order,
        Mapping,
    ):
        raise TypeError(
            "canonical_second_order must be a mapping or None"
        )

    a23_demand_states: tuple[ColumnDemandState, ...] = ()

    # PUBLIC-A5 still supports a bounded legacy FND2 slenderness mapping for
    # compatibility tests / B6-only execution. Only the canonical A17-A23
    # payload owns typed final A23 demand states. Absence of that canonical
    # envelope is not an A37 engineering fact and must not retroactively block
    # an otherwise-qualified B6-only execution.
    if (
        canonical_second_order is not None
        and "canonical_second_order" in canonical_second_order
    ):
        try:
            a23_demand_states = _decode_canonical_a23_demand_states(
                canonical_second_order,
                component_id=column.component_id,
            )
        except Exception as exc:
            return replace(
                column,
                status=STATUS_APPLICATION_BLOCKED,
                blockers=tuple(
                    dict.fromkeys(
                        (
                            *column.blockers,
                            f"{BLOCKER_LIVE_FND2_INPUT_LINEAGE}:"
                            f"A23_RUNTIME_RETENTION:{type(exc).__name__}:{exc}",
                        )
                    )
                ),
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
        completed_b6 = replace(
            column,
            design_code=design_code,
            design_procedure=design_procedure,
            design_state=design_state,
            controlled_design_result=controlled,
            free_length=free_length,
            a23_demand_states=a23_demand_states,
        )
    except Exception:
        return replace(
            column,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys((*column.blockers, BLOCKER_LIVE_DESIGN_LINEAGE))
            ),
        )

    # Backward-compatible B6-only execution remains a truthful READY artifact.
    # Full product callers pass both reviewed dependencies explicitly; they are
    # not stored in ColumnExecutionRequest/ProjectExecutionRequest.
    if column_design_basis is None and expected_combo_policy is None:
        return completed_b6
    if column_design_basis is None or expected_combo_policy is None:
        return replace(
            completed_b6,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys(
                    (*completed_b6.blockers, f"{BLOCKER_LONGITUDINAL_PRODUCTION}:MISSING_REVIEWED_DEPENDENCY")
                )
            ),
        )

    try:
        runtime = compose_column_longitudinal_runtime(
            component_id=completed_b6.component_id,
            column_model_fingerprint=completed_b6.model_fingerprint,
            column_evidence_epoch_id=completed_b6.evidence_epoch_id,
            readiness_binding=completed_b6.readiness_binding,
            acquisition_context=acquisition_context,
            analysis_execution=analysis_execution,
            topology=topology,
            selected_combo_population=selected_combo_population,
            combo_definitions=combo_definitions,
            flattened_combos=flattened_combos,
            combo_analysis_basis_bindings=combo_bindings,
            controlled_design_result=controlled,
            reviewed_design_basis=column_design_basis,
            expected_combo_policy=expected_combo_policy,
        )
    except Exception as exc:
        return replace(
            completed_b6,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys(
                    (
                        *completed_b6.blockers,
                        f"{BLOCKER_LONGITUDINAL_PRODUCTION}:{type(exc).__name__}:{exc}",
                    )
                )
            ),
        )

    if runtime.selection.selected:
        status = STATUS_SELECTED
        blockers: tuple[str, ...] = ()
    else:
        status = STATUS_APPLICATION_BLOCKED
        blockers = tuple(
            dict.fromkeys(
                (
                    *completed_b6.blockers,
                    *(runtime.selection.blockers or (runtime.selection.status,)),
                )
            )
        )
    selected_column = replace(
        completed_b6,
        status=status,
        blockers=blockers,
        layout_authority=runtime.layout_authority,
        longitudinal_selection=runtime.selection,
        longitudinal_runtime=runtime,
    )


    if not runtime.selection.selected:
        return selected_column

    try:
        if (
            reviewed_column_short_column_context is not None
            and reviewed_column_short_column_context.component_id
            != selected_column.component_id
        ):
            raise ColumnExecutionContractError(
                "A37 short-column context component mismatch"
            )

        shear_route = _resolve_a37_shear_route(
            high_ductility_applies=(
                runtime.bound_design_basis.high_ductility_applies
            ),
            limited_ductility_applies=(
                runtime.bound_design_basis.limited_ductility_applies
            ),
            short_column_context=(
                reviewed_column_short_column_context
            ),
            p7_context_present=(
                reviewed_column_p7_context is not None
            ),
            limited_context_present=(
                reviewed_column_limited_shear_context is not None
            ),
            downstream_shear_required=(
                reviewed_column_final_cage_context is not None
                or reviewed_column_vc_context is not None
            ),
        )
    except Exception as exc:
        return replace(
            selected_column,
            status=STATUS_APPLICATION_BLOCKED,
            blockers=tuple(
                dict.fromkeys(
                    (
                        *selected_column.blockers,
                        f"{BLOCKER_P7_PRODUCTION}:"
                        f"A37_SHEAR_ROUTE:{type(exc).__name__}:{exc}",
                    )
                )
            ),
        )

    shear_column = selected_column

    if shear_route in {
        A37_SHEAR_ROUTE_P7_ORDINARY,
        A37_SHEAR_ROUTE_P7_SHORT,
    }:
        try:
            if (
                selected_column.free_length is None
                or not selected_column.a23_demand_states
            ):
                raise ColumnExecutionContractError(
                    "A37 P7 requires retained canonical "
                    "free-length and A23 states"
                )
            if reviewed_column_p7_context is None:
                raise ColumnExecutionContractError(
                    "A37 P7 route lost reviewed P7 context"
                )
            if reviewed_column_short_column_context is None:
                raise ColumnExecutionContractError(
                    "A37 P7 route lost reviewed short-column context"
                )

            p7_runtime = compose_column_p7_runtime(
                component_id=selected_column.component_id,
                model_fingerprint=selected_column.model_fingerprint,
                acquisition_context=acquisition_context,
                analysis_execution=analysis_execution,
                free_length=selected_column.free_length,
                demand_states=selected_column.a23_demand_states,
                longitudinal_runtime=runtime,
                reviewed_context=reviewed_column_p7_context,
                short_column_context=(
                    reviewed_column_short_column_context
                ),
            )
            shear_column = replace(
                selected_column,
                column_shear_p7=p7_runtime.p7_run,
                column_shear_limited=None,
                column_shear_evidence=p7_runtime.shear_evidence,
            )
        except Exception as exc:
            shear_column = replace(
                selected_column,
                status=STATUS_APPLICATION_BLOCKED,
                blockers=tuple(
                    dict.fromkeys(
                        (
                            *selected_column.blockers,
                            f"{BLOCKER_P7_PRODUCTION}:"
                            f"{type(exc).__name__}:{exc}",
                        )
                    )
                ),
            )

    elif shear_route == A37_SHEAR_ROUTE_LIMITED_775:
        try:
            if reviewed_column_limited_shear_context is None:
                raise ColumnExecutionContractError(
                    "A37 LIMITED route lost reviewed §7.7.5 context"
                )
            limited_runtime = compose_column_limited_shear_runtime(
                component_id=selected_column.component_id,
                model_fingerprint=selected_column.model_fingerprint,
                acquisition_context=acquisition_context,
                analysis_execution=analysis_execution,
                longitudinal_runtime=runtime,
                reviewed_context=(
                    reviewed_column_limited_shear_context
                ),
                shear_evidence=(
                    selected_column.column_shear_evidence
                ),
            )
            shear_column = replace(
                selected_column,
                column_shear_p7=None,
                column_shear_limited=(
                    limited_runtime.limited_run
                ),
                column_shear_evidence=(
                    limited_runtime.shear_evidence
                ),
            )
        except Exception as exc:
            shear_column = replace(
                selected_column,
                status=STATUS_APPLICATION_BLOCKED,
                blockers=tuple(
                    dict.fromkeys(
                        (
                            *selected_column.blockers,
                            f"{BLOCKER_LIMITED_SHEAR_PRODUCTION}:"
                            f"{type(exc).__name__}:{exc}",
                        )
                    )
                ),
            )

    cage_column = (
        shear_column
        if reviewed_column_final_cage_context is None
        else replace(
            shear_column,
            final_transverse_cage=reviewed_column_final_cage_context,
        )
    )

    return _continue_selected_column_into_a36(
        cage_column,
        runtime=runtime,
        acquisition_context=acquisition_context,
        analysis_execution=analysis_execution,
        topology=topology,
        flattened_combos=flattened_combos,
        controlled_design_result=controlled,
        reviewed_vs5_column_axial_context=(
            reviewed_vs5_column_axial_context
        ),
        reviewed_column_short_column_context=(
            reviewed_column_short_column_context
        ),
        reviewed_column_final_cage_context=(
            reviewed_column_final_cage_context
        ),
        reviewed_column_vc_context=reviewed_column_vc_context,
    )


def _compose_lane_c_after_qualified_design(
    column: ColumnDomainArtifact,
    *,
    transverse_input: ColumnTransverseConfinementInput,
    design_lineage: DesignLineageQualification,
) -> ColumnDomainArtifact:
    """Join mature Lane-C authority only after longitudinal/B6 causal qualification."""
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
    "BLOCKER_LONGITUDINAL_PRODUCTION",
    "ColumnDomainArtifact",
    "ColumnExecutionContractError",
    "STATUS_APPLICATION_BLOCKED",
    "STATUS_FACTUAL_ACQUISITION_BLOCKED",
    "STATUS_REANALYSIS_REQUIRED",
    "STATUS_SELECTED",
    "execute_column_domain",
]
