"""Read-only revalidation of an already-established B4B analysis state.

B5 must prove that the exact causal analysis state it received before execution
still exists after execution. This module reuses the B4B request contract, the
same factual frame-modifier getter, and the B4A establishment/comparison spine.
It performs no model mutation and cannot establish a new requested state.

The complete original ``AnalysisStateIdentity.state_basis_refs`` population is
preserved on revalidation. Opaque additional identity commitments remain
identity commitments only; this module does not reinterpret them as B4B
SECTION_STIFFNESS_MODIFIERS state.
"""
from __future__ import annotations

from dataclasses import dataclass
import ntpath

from tbdy_engine.etabs.oapi.frame_modifiers import get_frame_modifiers_from_session
from tbdy_engine.etabs.safety import reread_verified_session_identity
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    FRAME_MODIFIER_PLAN_CONTRACT,
    AnalysisStateMutationResult,
    _parse_requested_targets,
)
from tbdy_engine.integration.etabs_derived_state import (
    DerivedStateComparison,
    EstablishedDerivedStateManifest,
    _POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
    _establish_derived_state_from_verified_readback,
    build_analysis_state_identity_from_derived_state,
    compare_derived_state_manifests,
)
from tbdy_engine.integration.etabs_analysis_lineage import AnalysisStateIdentity
from tbdy_engine.integration.etabs_scratch_lifecycle import (
    OwnedScratchContext,
    PhysicalFileSnapshot,
    capture_physical_file_snapshot,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)


ANALYSIS_STATE_REVALIDATION_CONTRACT = "TBDY_B4B_ANALYSIS_STATE_REVALIDATION_V1"


class AnalysisStateRevalidationError(RuntimeError):
    def __init__(self, message: str, *, stage: str) -> None:
        super().__init__(message)
        self.stage = stage


def _canonical_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(value).strip()))


def _same_bytes(left: PhysicalFileSnapshot, right: PhysicalFileSnapshot) -> bool:
    return (
        left.exists is True
        and right.exists is True
        and left.file_size_bytes == right.file_size_bytes
        and left.sha256_content_digest == right.sha256_content_digest
    )


@dataclass(frozen=True, slots=True)
class AnalysisStateRevalidationResult:
    original_analysis_state: AnalysisStateIdentity
    current_analysis_state: AnalysisStateIdentity
    comparison: DerivedStateComparison
    source_snapshot: PhysicalFileSnapshot
    readback_evidence_refs: tuple[str, ...]
    contract: str = ANALYSIS_STATE_REVALIDATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ANALYSIS_STATE_REVALIDATION_CONTRACT:
            raise AnalysisStateRevalidationError(
                "analysis-state revalidation contract mismatch",
                stage="result_contract",
            )
        if not isinstance(self.original_analysis_state, AnalysisStateIdentity):
            raise TypeError("original_analysis_state must be AnalysisStateIdentity")
        if not isinstance(self.current_analysis_state, AnalysisStateIdentity):
            raise TypeError("current_analysis_state must be AnalysisStateIdentity")
        if self.original_analysis_state.identity_ref != self.current_analysis_state.identity_ref:
            raise AnalysisStateRevalidationError(
                "current causal analysis state does not match the pre-execution AnalysisStateIdentity",
                stage="identity_mismatch",
            )

    @property
    def matched_exact(self) -> bool:
        return (
            self.comparison.matched
            and self.comparison.exact_causal_family_population
            and self.original_analysis_state.identity_ref == self.current_analysis_state.identity_ref
        )


def revalidate_frame_modifier_analysis_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    timeout_seconds: float = 30.0,
) -> AnalysisStateRevalidationResult:
    """Reread the B4B-R1 causal family and require the exact same state identity."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(established_state, AnalysisStateMutationResult):
        raise TypeError("established_state must be AnalysisStateMutationResult")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    if owned_scratch.source_model_identity != context.source_model_identity:
        raise AnalysisStateRevalidationError(
            "owned scratch does not belong to the trusted acquisition context",
            stage="source_binding",
        )
    if established_state.analysis_state_identity.source_model_ref != context.source_model_identity.source_model_ref:
        raise AnalysisStateRevalidationError(
            "established AnalysisStateIdentity belongs to a different source model",
            stage="source_binding",
        )
    if established_state.mutation_manifest.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise AnalysisStateRevalidationError(
            "B4B mutation result is not bound to this exact owned scratch",
            stage="scratch_binding",
        )

    identity = reread_verified_session_identity(
        context.verified_session,
        timeout_seconds=timeout,
    )
    if _canonical_path(identity.model_full_path) != _canonical_path(owned_scratch.scratch_path):
        raise AnalysisStateRevalidationError(
            "active ETABS model is not the exact owned scratch",
            stage="active_scratch_binding",
        )

    source_snapshot = capture_physical_file_snapshot(
        owned_scratch.source_pre.canonical_absolute_path
    )
    if not _same_bytes(source_snapshot, owned_scratch.source_post):
        raise AnalysisStateRevalidationError(
            "protected source physical bytes changed",
            stage="source_integrity",
        )

    targets = _parse_requested_targets(established_state.requested_manifest)
    readbacks = []
    for target in targets:
        fact = get_frame_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            timeout_seconds=timeout,
        )
        if not fact.success:
            raise AnalysisStateRevalidationError(
                "causal-state factual readback returned nonzero",
                stage="readback_nonzero",
            )
        readbacks.append(fact)

    requested_entry = established_state.requested_manifest.entries[0]
    established_entry = _establish_derived_state_from_verified_readback(
        _issuer_token=_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
        family=requested_entry.family,
        readback_value={
            "contract": FRAME_MODIFIER_PLAN_CONTRACT,
            "targets": [
                {
                    "surface": fact.surface.value,
                    "target_name": fact.target_name,
                    "modifiers": fact.modifiers.as_list(),
                }
                for fact in readbacks
            ],
        },
        readback_evidence_refs=tuple(fact.evidence_ref for fact in readbacks),
        normalization=requested_entry.normalization,
        provenance_refs=(
            owned_scratch.ownership_proof_ref,
            established_state.mutation_manifest.manifest_ref,
            context.acquisition_context_ref,
            context.session_provenance_ref,
            "b5-post-execution-read-only-revalidation",
        ),
    )
    current_manifest = EstablishedDerivedStateManifest(
        source_model_ref=context.source_model_identity.source_model_ref,
        entries=(established_entry,),
        provenance_refs=(
            owned_scratch.ownership_proof_ref,
            established_state.mutation_manifest.manifest_ref,
        ),
    )
    comparison = compare_derived_state_manifests(
        established_state.requested_manifest,
        current_manifest,
        provenance_refs=(
            established_state.mutation_manifest.manifest_ref,
            "b5-post-execution-read-only-revalidation",
        ),
    )
    if not comparison.matched or not comparison.exact_causal_family_population:
        raise AnalysisStateRevalidationError(
            "current factual causal state does not match the original B4B request",
            stage="comparison_mismatch",
        )

    current_state = build_analysis_state_identity_from_derived_state(
        comparison=comparison,
        state_basis_refs=established_state.analysis_state_identity.state_basis_refs,
        provenance_refs=(
            context.acquisition_context_ref,
            context.session_provenance_ref,
            owned_scratch.ownership_proof_ref,
            established_state.mutation_manifest.manifest_ref,
            "b5-post-execution-read-only-revalidation",
        ),
    )
    if current_state.identity_ref != established_state.analysis_state_identity.identity_ref:
        raise AnalysisStateRevalidationError(
            "post-execution AnalysisStateIdentity differs from the B4B-established identity",
            stage="identity_mismatch",
        )

    return AnalysisStateRevalidationResult(
        original_analysis_state=established_state.analysis_state_identity,
        current_analysis_state=current_state,
        comparison=comparison,
        source_snapshot=source_snapshot,
        readback_evidence_refs=tuple(fact.evidence_ref for fact in readbacks),
    )


__all__ = [
    "ANALYSIS_STATE_REVALIDATION_CONTRACT",
    "AnalysisStateRevalidationError",
    "AnalysisStateRevalidationResult",
    "revalidate_frame_modifier_analysis_state",
]
