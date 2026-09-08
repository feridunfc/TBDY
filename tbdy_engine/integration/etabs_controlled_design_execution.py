"""B6 controlled concrete-design execution and causal lineage issuer.

This is the single production owner of ``DesignConcrete.StartDesign``. It is
layered on B6-P0 preflight and B2 design-lineage contracts. OAPI remains the
factual invocation boundary; P8A remains the factual design-result provider;
this module only owns causal orchestration and qualification.

A qualified result is issued only when the same OwnedScratch/analysis lineage,
exact design state, selected design-combination population and exact expected
Column population survive the complete attempt. Existing ETABS result rows are
never silently promoted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import ntpath
from typing import Sequence

from tbdy_engine.etabs.oapi.concrete_design import (
    ConcreteDesignStartFact,
    read_results_available_from_session,
    start_concrete_design_from_session,
)
from tbdy_engine.etabs.safety import reread_verified_session_identity
from tbdy_engine.features.column_concrete_design_evidence import ColumnTopologyEvidenceEnvelope
from tbdy_engine.features.column_design_rebar_evidence import FactualColumnDesignResultPopulation
from tbdy_engine.integration.etabs_analysis_lineage import AnalysisLineageQualification
from tbdy_engine.integration.etabs_design_execution import (
    DesignPreflightSnapshot,
    DesignPreflightStatus,
    capture_design_preflight,
)
from tbdy_engine.integration.etabs_design_lineage import (
    DesignLineageQualification,
    DesignLineageQualificationError,
    DesignResultIdentity,
    DesignStateIdentity,
    _DESIGN_LINEAGE_FACTORY_KEY,
    _DESIGN_PROOF_FACTORY_KEY,
    _VerifiedDesignExecutionProof,
    _build_qualified_design_lineage,
    _design_execution_proof_ref,
    build_design_result_identity,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
    capture_concrete_column_design_results_from_context,
    capture_concrete_column_design_sections_from_context,
    capture_actual_concrete_design_combo_selection_from_context,
)


CONTROLLED_CONCRETE_DESIGN_CONTRACT = "TBDY_B6_CONTROLLED_CONCRETE_DESIGN_V1"
DESIGN_ATTEMPT_REF_PREFIX = "b6-design-attempt:sha256:"
DESIGN_GENERATION_REF_PREFIX = "b6-design-generation:sha256:"
DESIGN_COMPONENT_SCOPE_PREFIX = "column-design-result-scope:"


class ControlledDesignExecutionError(RuntimeError):
    def __init__(self, message: str, *, stage: str) -> None:
        super().__init__(message)
        self.stage = stage


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ControlledDesignExecutionError(
            f"{label} must be a nonblank canonical string",
            stage="contract",
        )
    return value


def _refs(values: Sequence[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence")
    refs = tuple(sorted({_text(value, label) for value in values}))
    if required and not refs:
        raise ControlledDesignExecutionError(
            f"{label} must be nonempty",
            stage="contract",
        )
    return refs


def _sha_ref(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(_text(value, "model path")))


def design_component_scope_ref(component_id: str) -> str:
    return DESIGN_COMPONENT_SCOPE_PREFIX + _text(component_id, "component_id")


def _population_ref(selection: object) -> str:
    refs = tuple(getattr(selection, "source_refs", ()) or ())
    matches = tuple(ref for ref in refs if ref.startswith("selected-design-combo-population:sha256:"))
    if len(matches) != 1:
        raise ControlledDesignExecutionError(
            "selected design-combo population does not expose one canonical population ref",
            stage="design_state_revalidation",
        )
    return matches[0]


def _expected_scope_refs(topology: ColumnTopologyEvidenceEnvelope) -> tuple[str, ...]:
    columns = tuple(topology.topology.columns)
    if not columns:
        raise ControlledDesignExecutionError(
            "expected concrete-column population is empty",
            stage="component_population",
        )
    refs = tuple(sorted(design_component_scope_ref(item.component_id) for item in columns))
    if len(refs) != len(set(refs)):
        raise ControlledDesignExecutionError(
            "expected concrete-column component population is not unique",
            stage="component_population",
        )
    return refs


def _validate_design_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    analysis_lineage: AnalysisLineageQualification,
    topology: ColumnTopologyEvidenceEnvelope,
    design_state: DesignStateIdentity,
    selected_combo_population_ref: str,
) -> tuple[object, tuple[str, ...]]:
    if not isinstance(design_state, DesignStateIdentity):
        raise TypeError("design_state must be DesignStateIdentity")
    try:
        parent_result = analysis_lineage.require_qualified_result()
    except Exception as exc:
        raise ControlledDesignExecutionError(
            "B6 requires a QUALIFIED parent analysis lineage",
            stage="analysis_lineage",
        ) from exc

    expected_scopes = _expected_scope_refs(topology)
    checks = (
        (design_state.source_model_ref, context.source_model_identity.source_model_ref, "source model"),
        (design_state.parent_analysis_result_ref, parent_result.identity_ref, "parent analysis result"),
        (design_state.analysis_lineage_qualification_ref, analysis_lineage.qualification_ref, "analysis qualification"),
        (design_state.model_fingerprint, topology.model_fingerprint, "model fingerprint"),
        (design_state.evidence_epoch_id, topology.evidence_epoch_id, "EvidenceEpoch"),
        (design_state.selected_design_combo_population_ref, selected_combo_population_ref, "selected design-combo population"),
        (tuple(design_state.design_component_population_refs), expected_scopes, "design component population"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise ControlledDesignExecutionError(
                f"design state {label} mismatch",
                stage="design_state_binding",
            )

    if owned_scratch.ownership_proof_ref not in analysis_lineage.capture_provenance_refs:
        raise ControlledDesignExecutionError(
            "parent B5 lineage is not bound to this exact OwnedScratchContext",
            stage="scratch_binding",
        )
    return parent_result, expected_scopes


def _revalidate_active_scratch(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    timeout_seconds: float,
) -> str:
    identity = reread_verified_session_identity(
        context.verified_session,
        timeout_seconds=timeout_seconds,
    )
    if _path(identity.model_full_path) != _path(owned_scratch.scratch_path):
        raise ControlledDesignExecutionError(
            "active ETABS model is not the exact OwnedScratchContext",
            stage="active_scratch_revalidation",
        )
    return _text(identity.model_full_path, "active model path")


@dataclass(frozen=True, slots=True)
class ControlledConcreteDesignResult:
    preflight: DesignPreflightSnapshot
    start_fact: ConcreteDesignStartFact
    design_state: DesignStateIdentity
    design_result_identity: DesignResultIdentity
    design_lineage: DesignLineageQualification
    factual_design_results: FactualColumnDesignResultPopulation
    design_sections: object
    selected_combo_population_ref: str
    design_attempt_ref: str
    design_generation_ref: str
    provenance_refs: tuple[str, ...]
    contract: str = CONTROLLED_CONCRETE_DESIGN_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != CONTROLLED_CONCRETE_DESIGN_CONTRACT:
            raise ControlledDesignExecutionError(
                "controlled design result contract mismatch",
                stage="result_contract",
            )
        if not self.design_lineage.qualified:
            raise ControlledDesignExecutionError(
                "controlled design result must carry qualified lineage",
                stage="result_contract",
            )
        if not self.factual_design_results.capture_complete:
            raise ControlledDesignExecutionError(
                "controlled design result requires complete factual result population",
                stage="result_contract",
            )


def execute_controlled_concrete_design(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    analysis_lineage: AnalysisLineageQualification,
    topology: ColumnTopologyEvidenceEnvelope,
    design_state: DesignStateIdentity,
    timeout_seconds: float = 300.0,
) -> ControlledConcreteDesignResult:
    """Cause exactly one concrete-design generation and issue qualified B6 lineage."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(analysis_lineage, AnalysisLineageQualification):
        raise TypeError("analysis_lineage must be AnalysisLineageQualification")
    if not isinstance(topology, ColumnTopologyEvidenceEnvelope):
        raise TypeError("topology must be ColumnTopologyEvidenceEnvelope")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    preflight = capture_design_preflight(
        context=context,
        owned_scratch=owned_scratch,
        analysis_lineage=analysis_lineage,
        topology=topology,
        timeout_seconds=min(timeout, 30.0),
    )
    if preflight.status is not DesignPreflightStatus.ABSENT:
        raise ControlledDesignExecutionError(
            f"pre-existing concrete-design result state is {preflight.status.value}",
            stage="preflight",
        )

    selected_before = capture_actual_concrete_design_combo_selection_from_context(context)
    selected_ref = _population_ref(selected_before)
    parent_result, expected_scopes = _validate_design_state(
        context=context,
        owned_scratch=owned_scratch,
        analysis_lineage=analysis_lineage,
        topology=topology,
        design_state=design_state,
        selected_combo_population_ref=selected_ref,
    )
    active_path_before = _revalidate_active_scratch(
        context=context,
        owned_scratch=owned_scratch,
        timeout_seconds=min(timeout, 30.0),
    )

    attempt_ref = _sha_ref(
        DESIGN_ATTEMPT_REF_PREFIX,
        {
            "source_model_ref": design_state.source_model_ref,
            "parent_analysis_result_ref": parent_result.identity_ref,
            "design_state_ref": design_state.identity_ref,
            "preflight_ref": preflight.preflight_ref,
            "ownership_proof_ref": owned_scratch.ownership_proof_ref,
            "selected_combo_population_ref": selected_ref,
            "expected_result_scope_refs": list(expected_scopes),
        },
    )

    # The only StartDesign call in production lives below this line.
    start_fact = start_concrete_design_from_session(
        context.verified_session,
        timeout_seconds=timeout,
    )
    if not start_fact.success:
        raise ControlledDesignExecutionError(
            f"DesignConcrete.StartDesign returned {start_fact.return_code}",
            stage="start_design_nonzero",
        )

    active_path_after = _revalidate_active_scratch(
        context=context,
        owned_scratch=owned_scratch,
        timeout_seconds=min(timeout, 30.0),
    )
    if _path(active_path_after) != _path(active_path_before):
        raise ControlledDesignExecutionError(
            "active scratch changed during concrete design",
            stage="design_state_revalidation",
        )

    availability = read_results_available_from_session(
        context.verified_session,
        timeout_seconds=min(timeout, 30.0),
    )
    if not availability.results_available:
        raise ControlledDesignExecutionError(
            "StartDesign succeeded but concrete design results are not available",
            stage="post_design_results_unavailable",
        )

    selected_after = capture_actual_concrete_design_combo_selection_from_context(context)
    if _population_ref(selected_after) != selected_ref:
        raise ControlledDesignExecutionError(
            "selected concrete design-combo population changed during StartDesign",
            stage="design_state_revalidation",
        )

    design_sections = capture_concrete_column_design_sections_from_context(context)
    factual_results = capture_concrete_column_design_results_from_context(
        context,
        topology=topology,
        design_sections=design_sections,
    )
    if not factual_results.capture_complete:
        raise ControlledDesignExecutionError(
            "post-design exact result population did not close",
            stage="result_population",
        )
    if tuple(sorted(design_component_scope_ref(item) for item in factual_results.expected_component_ids)) != expected_scopes:
        raise ControlledDesignExecutionError(
            "post-design result population differs from DesignState component scope",
            stage="result_population",
        )

    generation_ref = _sha_ref(
        DESIGN_GENERATION_REF_PREFIX,
        {
            "design_attempt_ref": attempt_ref,
            "start_design_evidence_ref": start_fact.evidence_ref,
            "selected_combo_population_ref": selected_ref,
            "result_source_refs": list(sorted(factual_results.source_refs)),
            "reported_result_row_count": factual_results.reported_result_row_count,
        },
    )
    result_identity = build_design_result_identity(
        design_state=design_state,
        design_generation_ref=generation_ref,
        result_scope_refs=expected_scopes,
        provenance_refs=(
            attempt_ref,
            start_fact.evidence_ref,
            *factual_results.source_refs,
        ),
    )

    proof_refs = _refs(
        (
            context.acquisition_context_ref,
            context.session_provenance_ref,
            owned_scratch.ownership_proof_ref,
            analysis_lineage.qualification_ref,
            parent_result.identity_ref,
            preflight.preflight_ref,
            selected_ref,
            start_fact.evidence_ref,
            *factual_results.source_refs,
        ),
        "design execution provenance_ref",
        required=True,
    )
    proof_values = {
        "source_model_ref": design_state.source_model_ref,
        "parent_analysis_result_ref": parent_result.identity_ref,
        "analysis_lineage_qualification_ref": analysis_lineage.qualification_ref,
        "model_fingerprint": design_state.model_fingerprint,
        "evidence_epoch_id": design_state.evidence_epoch_id,
        "design_state_ref": design_state.identity_ref,
        "design_result_ref": result_identity.identity_ref,
        "design_attempt_ref": attempt_ref,
        "design_generation_ref": generation_ref,
        "requested_result_scope_refs": expected_scopes,
        "reconciled_result_scope_refs": expected_scopes,
        "combo_grain_binding_refs": design_state.combo_grain_binding_refs,
        "provenance_refs": proof_refs,
    }
    execution_proof = _VerifiedDesignExecutionProof(
        _token=_DESIGN_PROOF_FACTORY_KEY,
        proof_ref=_design_execution_proof_ref(**proof_values),
        **proof_values,
    )
    try:
        lineage = _build_qualified_design_lineage(
            _token=_DESIGN_LINEAGE_FACTORY_KEY,
            parent_analysis_lineage=analysis_lineage,
            design_state=design_state,
            design_result=result_identity,
            execution_proof=execution_proof,
            qualification_provenance_refs=proof_refs,
            capture_provenance_refs=(
                context.acquisition_context_ref,
                context.session_provenance_ref,
                owned_scratch.ownership_proof_ref,
            ),
        )
    except DesignLineageQualificationError as exc:
        raise ControlledDesignExecutionError(
            "B2 rejected the controlled design causal proof",
            stage="lineage_qualification",
        ) from exc

    return ControlledConcreteDesignResult(
        preflight=preflight,
        start_fact=start_fact,
        design_state=design_state,
        design_result_identity=result_identity,
        design_lineage=lineage,
        factual_design_results=factual_results,
        design_sections=design_sections,
        selected_combo_population_ref=selected_ref,
        design_attempt_ref=attempt_ref,
        design_generation_ref=generation_ref,
        provenance_refs=proof_refs,
    )


__all__ = [
    "CONTROLLED_CONCRETE_DESIGN_CONTRACT",
    "ControlledConcreteDesignResult",
    "ControlledDesignExecutionError",
    "design_component_scope_ref",
    "execute_controlled_concrete_design",
]
