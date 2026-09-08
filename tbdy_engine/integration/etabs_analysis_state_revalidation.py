"""Read-only revalidation of an already-established B4B analysis state.

B5 must prove that the exact causal analysis state it received still exists
immediately before destructive execution-state changes, immediately before
``RunAnalysis`` and after analysis. A5-I0 extended B4B from the legacy
frame-only modifier plan to the V2 mixed Frame/Area section-modifier plan, so
this revalidator accepts both contracts without weakening the legacy path.

Revalidation is factual only: it rereads the exact requested target population,
rebuilds the existing B4A derived-state comparison and requires the same
``AnalysisStateIdentity``. It performs no mutation and cannot establish a new
requested state.

The complete original ``AnalysisStateIdentity.state_basis_refs`` population is
preserved. Opaque additional identity commitments remain identity commitments
only; this module does not reinterpret them as section-modifier facts.
"""
from __future__ import annotations

from dataclasses import dataclass
import ntpath
from typing import Callable, Sequence

from tbdy_engine.etabs.oapi.frame_modifiers import get_frame_modifiers_from_session
from tbdy_engine.etabs.safety import reread_verified_session_identity
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    FRAME_MODIFIER_PLAN_CONTRACT,
    SECTION_MODIFIER_PLAN_CONTRACT,
    AnalysisStateMutationResult,
    AreaModifierTargetRequest,
    FrameModifierTargetRequest,
    _get_section_modifier_fact,
    _parse_requested_section_targets,
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


ANALYSIS_STATE_REVALIDATION_CONTRACT = "TBDY_B4B_ANALYSIS_STATE_REVALIDATION_V2"
_REVALIDATION_PROVENANCE_REF = "b5-read-only-causal-state-revalidation"


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
                "current causal analysis state does not match the B4B AnalysisStateIdentity",
                stage="identity_mismatch",
            )

    @property
    def matched_exact(self) -> bool:
        return (
            self.comparison.matched
            and self.comparison.exact_causal_family_population
            and self.original_analysis_state.identity_ref
            == self.current_analysis_state.identity_ref
        )


def _requested_plan_contract(established_state: AnalysisStateMutationResult) -> str:
    manifest = established_state.requested_manifest
    if len(manifest.entries) != 1:
        raise AnalysisStateRevalidationError(
            "B4B revalidation requires exactly one requested derived-state entry",
            stage="request_contract",
        )
    value = manifest.entries[0].canonical_value
    if not isinstance(value, dict):
        raise AnalysisStateRevalidationError(
            "B4B requested section-modifier state is not a mapping",
            stage="request_contract",
        )
    contract = value.get("contract")
    if contract not in {FRAME_MODIFIER_PLAN_CONTRACT, SECTION_MODIFIER_PLAN_CONTRACT}:
        raise AnalysisStateRevalidationError(
            "unsupported B4B section-modifier plan contract",
            stage="request_contract",
        )
    return str(contract)


def _require_bindings(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    timeout_seconds: float,
) -> PhysicalFileSnapshot:
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(established_state, AnalysisStateMutationResult):
        raise TypeError("established_state must be AnalysisStateMutationResult")

    if owned_scratch.source_model_identity != context.source_model_identity:
        raise AnalysisStateRevalidationError(
            "owned scratch does not belong to the trusted acquisition context",
            stage="source_binding",
        )
    if (
        established_state.analysis_state_identity.source_model_ref
        != context.source_model_identity.source_model_ref
    ):
        raise AnalysisStateRevalidationError(
            "established AnalysisStateIdentity belongs to a different source model",
            stage="source_binding",
        )
    if (
        established_state.mutation_manifest.ownership_proof_ref
        != owned_scratch.ownership_proof_ref
    ):
        raise AnalysisStateRevalidationError(
            "B4B mutation result is not bound to this exact owned scratch",
            stage="scratch_binding",
        )

    identity = reread_verified_session_identity(
        context.verified_session,
        timeout_seconds=timeout_seconds,
    )
    if _canonical_path(identity.model_full_path) != _canonical_path(
        owned_scratch.scratch_path
    ):
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
    return source_snapshot


def _revalidate(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    plan_contract: str,
    targets: Sequence[object],
    factual_reader: Callable[[object], object],
    timeout_seconds: float,
) -> AnalysisStateRevalidationResult:
    source_snapshot = _require_bindings(
        context=context,
        owned_scratch=owned_scratch,
        established_state=established_state,
        timeout_seconds=timeout_seconds,
    )

    readbacks: list[object] = []
    for target in targets:
        fact = factual_reader(target)
        if not getattr(fact, "success", False):
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
            "contract": plan_contract,
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
            _REVALIDATION_PROVENANCE_REF,
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
            _REVALIDATION_PROVENANCE_REF,
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
            _REVALIDATION_PROVENANCE_REF,
        ),
    )
    if current_state.identity_ref != established_state.analysis_state_identity.identity_ref:
        raise AnalysisStateRevalidationError(
            "revalidated AnalysisStateIdentity differs from the B4B-established identity",
            stage="identity_mismatch",
        )

    return AnalysisStateRevalidationResult(
        original_analysis_state=established_state.analysis_state_identity,
        current_analysis_state=current_state,
        comparison=comparison,
        source_snapshot=source_snapshot,
        readback_evidence_refs=tuple(fact.evidence_ref for fact in readbacks),
    )


def _revalidate_legacy_frame_plan(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    timeout_seconds: float,
) -> AnalysisStateRevalidationResult:
    targets = _parse_requested_targets(established_state.requested_manifest)

    def reader(target: object) -> object:
        if not isinstance(target, FrameModifierTargetRequest):
            raise TypeError("frame plan contains a non-frame target")
        return get_frame_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            timeout_seconds=timeout_seconds,
        )

    return _revalidate(
        context=context,
        owned_scratch=owned_scratch,
        established_state=established_state,
        plan_contract=FRAME_MODIFIER_PLAN_CONTRACT,
        targets=targets,
        factual_reader=reader,
        timeout_seconds=timeout_seconds,
    )


def revalidate_section_modifier_analysis_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    timeout_seconds: float = 30.0,
) -> AnalysisStateRevalidationResult:
    """Reread the exact A5-I0 V2 mixed Frame/Area target population."""
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if _requested_plan_contract(established_state) != SECTION_MODIFIER_PLAN_CONTRACT:
        raise AnalysisStateRevalidationError(
            "mixed section revalidation requires the B4B V2 section plan",
            stage="request_contract",
        )
    targets = _parse_requested_section_targets(established_state.requested_manifest)

    def reader(target: object) -> object:
        if not isinstance(target, (FrameModifierTargetRequest, AreaModifierTargetRequest)):
            raise TypeError("unsupported section-modifier target")
        return _get_section_modifier_fact(
            context,
            target,
            timeout_seconds=timeout,
        )

    return _revalidate(
        context=context,
        owned_scratch=owned_scratch,
        established_state=established_state,
        plan_contract=SECTION_MODIFIER_PLAN_CONTRACT,
        targets=targets,
        factual_reader=reader,
        timeout_seconds=timeout,
    )


def revalidate_analysis_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    timeout_seconds: float = 30.0,
) -> AnalysisStateRevalidationResult:
    """Dispatch to the exact B4B contract; never downgrade V2 to frame-only."""
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    contract = _requested_plan_contract(established_state)
    if contract == FRAME_MODIFIER_PLAN_CONTRACT:
        return _revalidate_legacy_frame_plan(
            context=context,
            owned_scratch=owned_scratch,
            established_state=established_state,
            timeout_seconds=timeout,
        )
    if contract == SECTION_MODIFIER_PLAN_CONTRACT:
        return revalidate_section_modifier_analysis_state(
            context=context,
            owned_scratch=owned_scratch,
            established_state=established_state,
            timeout_seconds=timeout,
        )
    raise AnalysisStateRevalidationError(
        "unsupported B4B plan contract",
        stage="request_contract",
    )


def revalidate_frame_modifier_analysis_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    timeout_seconds: float = 30.0,
) -> AnalysisStateRevalidationResult:
    """B5 compatibility entrypoint, now exact for both B4B V1 and V2.

    B5 historically imports this name. Keeping the symbol while dispatching on
    the requested B4B contract lets existing B5 call sites gain mixed-state
    fail-closed revalidation without a second execution path.
    """
    return revalidate_analysis_state(
        context=context,
        owned_scratch=owned_scratch,
        established_state=established_state,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "ANALYSIS_STATE_REVALIDATION_CONTRACT",
    "AnalysisStateRevalidationError",
    "AnalysisStateRevalidationResult",
    "revalidate_analysis_state",
    "revalidate_frame_modifier_analysis_state",
    "revalidate_section_modifier_analysis_state",
]
