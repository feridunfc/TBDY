"""Bounded column application composition for PRODUCT-SPINE-COL-1.

Public LIVE execution is fail-closed before FND-COL-2X because current main has
no accepted builder from ``TrustedLiveAcquisitionContext`` to complete
``RegulatoryCompileInputs``. Private underscore seams exist only to prove that,
once an upstream lineage is qualified, current authorities compose without
turning fixture truth into production request state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from tbdy_engine.application.contracts import ColumnExecutionRequest
from tbdy_engine.design.columns.column_combo_eligibility_projection import ComponentReadinessBinding
from tbdy_engine.design.columns.column_longitudinal_production_composition import compose_canonical_column_longitudinal_selection
from tbdy_engine.design.columns.column_longitudinal_selection_policy_factory import build_reviewed_column_longitudinal_selection_policy_input
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.regulatory.column_candidate_adequacy_authority import authorize_candidate_adequacy_policy
from tbdy_engine.regulatory.column_longitudinal_rebar import evaluate_column_longitudinal_layouts
from tbdy_engine.regulatory.column_pmm_authority import authorize_pmm_numerical_policy
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    ColumnTransverseConfinementResult,
    evaluate_column_transverse_confinement,
)
from tbdy_engine.regulatory.fnd_col_2_program import compile_source_bound_fnd_col_2_program, execute_source_bound_fnd_col_2_with_artifact
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import FND_COL_1_AUTHORITY_CATALOG
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
from tbdy_engine.regulatory.sources.fnd_col_4_pmm import FND_COL_4_PMM_AUTHORITY_CATALOG
from tbdy_engine.regulatory.vs6_column_shear_p7_program import VS6P7ColumnShearRun

STATUS_FACTUAL_ACQUISITION_BLOCKED = "FACTUAL_ACQUISITION_BLOCKED"
STATUS_APPLICATION_BLOCKED = "APPLICATION_BLOCKED"
STATUS_READY = "READY"
STATUS_SELECTED = "SELECTED"
STATUS_BLOCKED = "BLOCKED"
STATUS_REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
STATUS_UNRESOLVED = "UNRESOLVED"
BLOCKER_LIVE_FND2_INPUT_LINEAGE = "LIVE_FND2_INPUT_LINEAGE_NOT_QUALIFIED"
BLOCKER_LIVE_DESIGN_LINEAGE = "LIVE_DESIGN_RESULT_LINEAGE_NOT_QUALIFIED"
BLOCKER_LANE_C_SHEAR = "QUALIFIED_COLUMN_SHEAR_RESULT_NOT_AVAILABLE"


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
    layout_authority: object | None = None
    longitudinal_selection: object | None = None
    transverse_confinement: ColumnTransverseConfinementResult | None = None
    column_shear: VS6P7ColumnShearRun | None = None

    @property
    def selected_rebar(self):
        return None if self.longitudinal_selection is None else self.longitudinal_selection.selected_rebar


def execute_column_domain(
    request: ColumnExecutionRequest,
    *,
    acquisition_context: TrustedLiveAcquisitionContext,
) -> ColumnDomainArtifact:
    """Legal public LIVE A1 boundary: trusted factual generation, then stop."""
    if not isinstance(request, ColumnExecutionRequest):
        raise TypeError("request must be ColumnExecutionRequest")
    if not isinstance(acquisition_context, TrustedLiveAcquisitionContext):
        raise TypeError("acquisition_context must be TrustedLiveAcquisitionContext")
    return ColumnDomainArtifact(
        component_id=request.component_id,
        model_fingerprint=acquisition_context.model_fingerprint,
        evidence_epoch_id=acquisition_context.evidence_epoch_id,
        status=STATUS_FACTUAL_ACQUISITION_BLOCKED,
        blockers=(BLOCKER_LIVE_FND2_INPUT_LINEAGE,),
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
            provenance_refs=tuple(dict.fromkeys((f"fnd-col-2-plan:{record.plan_identity}", *record.evidence_refs, *readiness.source_refs))),
        )
    if readiness is None:
        status, blockers = STATUS_BLOCKED, ("FND_COL_2_TYPED_READINESS_NOT_EMITTED",)
    elif readiness.status == STATUS_READY:
        status, blockers = STATUS_READY, ()
    elif readiness.status in {STATUS_BLOCKED, STATUS_REANALYSIS_REQUIRED, STATUS_UNRESOLVED}:
        status, blockers = readiness.status, tuple(readiness.blocked_items)
    else:
        raise ColumnExecutionContractError(f"unsupported FND-COL-2 readiness status: {readiness.status}")
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


def _compose_lane_c_outputs(
    column: ColumnDomainArtifact,
    *,
    transverse_input: ColumnTransverseConfinementInput,
    column_shear: VS6P7ColumnShearRun | None,
) -> ColumnDomainArtifact:
    """Compose canonical Lane-C outputs without creating a second engineering owner."""
    if not isinstance(column, ColumnDomainArtifact):
        raise TypeError("column must be ColumnDomainArtifact")
    if not isinstance(transverse_input, ColumnTransverseConfinementInput):
        raise TypeError("transverse_input must be ColumnTransverseConfinementInput")
    if transverse_input.component_id != column.component_id:
        raise ColumnExecutionContractError("Lane-C transverse component identity mismatch")
    transverse = evaluate_column_transverse_confinement(
        transverse_input,
        selected_rebar=column.selected_rebar,
    )
    blockers = list(column.blockers)
    blockers.extend(f"TRANSVERSE_CONFINEMENT:{item}" for item in transverse.blockers)
    if column_shear is None:
        blockers.append(BLOCKER_LANE_C_SHEAR)
    else:
        if not isinstance(column_shear, VS6P7ColumnShearRun):
            raise TypeError("column_shear must be VS6P7ColumnShearRun or None")
        if column_shear.component_id != column.component_id:
            raise ColumnExecutionContractError("Lane-C shear component identity mismatch")
        if tuple(item.direction for item in column_shear.directions) != ("V2", "V3"):
            raise ColumnExecutionContractError("Lane-C shear requires exact V2/V3 direction population")
    if blockers and column.status == STATUS_SELECTED:
        status = STATUS_APPLICATION_BLOCKED
    else:
        status = column.status
    return replace(
        column,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        transverse_confinement=transverse,
        column_shear=column_shear,
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
    lane_c_transverse_input=None,
    lane_c_column_shear=None,
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
        raise ColumnExecutionContractError("test-only READY evidence identity mismatch")
    if req.component_id != request.component_id or material_context.component_id != request.component_id:
        raise ColumnExecutionContractError("test-only READY component identity mismatch")
    if factual_design_results.expected_component_ids != (request.component_id,):
        raise ColumnExecutionContractError("test-only design-result population mismatch")
    bindings = tuple(combo_analysis_basis_bindings)
    if any(b.model_fingerprint != model_fingerprint or b.evidence_epoch_id != evidence_epoch_id for b in bindings):
        raise ColumnExecutionContractError("test-only combo analysis-basis identity mismatch")
    mapping = {b.design_combo_identity: b for b in bindings}
    if len(mapping) != len(bindings):
        raise ColumnExecutionContractError("duplicate test-only combo analysis-basis identity")

    layout = evaluate_column_longitudinal_layouts(layout_inputs, authority_catalog=FND_COL_1_AUTHORITY_CATALOG)
    selection = compose_canonical_column_longitudinal_selection(
        component_id=request.component_id,
        layout_authority=layout,
        readiness_binding=column.readiness_binding,
        combo_reconciliation=combo_reconciliation,
        combo_analysis_basis_bindings=mapping,
        factual_design_results=factual_design_results,
        selection_policy=build_reviewed_column_longitudinal_selection_policy_input(),
        numerical_policy=authorize_pmm_numerical_policy(authority_catalog=FND_COL_4_PMM_AUTHORITY_CATALOG),
        material_context=material_context,
        adequacy_policy=authorize_candidate_adequacy_policy(authority_catalog=FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG),
    )
    composed = ColumnDomainArtifact(
        component_id=column.component_id,
        model_fingerprint=column.model_fingerprint,
        evidence_epoch_id=column.evidence_epoch_id,
        status=STATUS_SELECTED if selection.selected else STATUS_APPLICATION_BLOCKED,
        blockers=() if selection.selected else tuple(selection.blockers or (selection.status,)),
        fnd_col_2_program=column.fnd_col_2_program,
        fnd_col_2_execution=column.fnd_col_2_execution,
        readiness_binding=column.readiness_binding,
        layout_authority=layout,
        longitudinal_selection=selection,
    )
    if lane_c_transverse_input is None:
        if lane_c_column_shear is not None:
            raise ColumnExecutionContractError("Lane-C shear cannot be composed without transverse/confinement input")
        return composed
    return _compose_lane_c_outputs(
        composed,
        transverse_input=lane_c_transverse_input,
        column_shear=lane_c_column_shear,
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
