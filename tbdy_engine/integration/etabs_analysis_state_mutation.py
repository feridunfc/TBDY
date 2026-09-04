"""B4B causal analysis-state mutation authority for owned ETABS scratch models.

This module consumes an already-qualified B4S ``OwnedScratchContext`` and an
explicit B4A requested derived-state manifest. It owns only the causal
SECTION_STIFFNESS_MODIFIERS mutation lifecycle:

requested state -> factual pre-read -> typed SET -> factual readback ->
mutation manifest -> established derived state -> exact/tolerant comparison ->
AnalysisStateIdentity.

It does not run analysis, select run cases, delete results, start design,
change present units, choose engineering modifier values, or expose raw ETABS
capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import ntpath
from typing import Mapping, Sequence

from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSetFact,
    FrameModifierSurface,
    FrameModifierVector,
    get_frame_modifiers_from_session,
    set_frame_modifiers_from_session,
)
from tbdy_engine.etabs.safety import reread_verified_session_identity
from tbdy_engine.integration.etabs_analysis_lineage import AnalysisStateIdentity
from tbdy_engine.integration.etabs_derived_state import (
    DerivedStateComparison,
    DerivedStateFamily,
    EstablishedDerivedStateManifest,
    NumericTolerance,
    RequestedDerivedStateManifest,
    _POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
    _establish_derived_state_from_verified_readback,
    build_analysis_state_identity_from_derived_state,
    compare_derived_state_manifests,
    request_derived_state,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import (
    OwnedScratchContext,
    PhysicalFileSnapshot,
    capture_physical_file_snapshot,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)


FRAME_MODIFIER_PLAN_CONTRACT = "TBDY_B4B_FRAME_MODIFIER_PLAN_V1"
FRAME_MODIFIER_MUTATION_FACT_CONTRACT = "TBDY_B4B_FRAME_MODIFIER_MUTATION_FACT_V1"
ANALYSIS_STATE_MUTATION_MANIFEST_CONTRACT = "TBDY_B4B_ANALYSIS_STATE_MUTATION_MANIFEST_V1"
ANALYSIS_STATE_MUTATION_RESULT_CONTRACT = "TBDY_B4B_ANALYSIS_STATE_MUTATION_RESULT_V1"
MUTATION_FACT_REF_PREFIX = "b4b-frame-modifier-mutation:sha256:"
MUTATION_MANIFEST_REF_PREFIX = "b4b-analysis-state-mutation:sha256:"


class AnalysisStateMutationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        restoration_status: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.restoration_status = restoration_status
        self.details = dict(details or {})


class MutationRestorationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    RESTORED = "RESTORED"
    FAILED = "FAILED"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AnalysisStateMutationError(
            f"{label} must be a nonblank canonical string",
            stage="contract_validation",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    return value


def _digest(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _canonical_model_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(_text(value, "model_path")))


def _same_physical_bytes(left: PhysicalFileSnapshot, right: PhysicalFileSnapshot) -> bool:
    return (
        left.exists is True
        and right.exists is True
        and left.file_size_bytes == right.file_size_bytes
        and left.sha256_content_digest == right.sha256_content_digest
    )


@dataclass(frozen=True, slots=True)
class FrameModifierTargetRequest:
    surface: FrameModifierSurface
    target_name: str
    modifiers: FrameModifierVector

    def __post_init__(self) -> None:
        if not isinstance(self.surface, FrameModifierSurface):
            raise TypeError("surface must be FrameModifierSurface")
        object.__setattr__(self, "target_name", _text(self.target_name, "target_name"))
        if not isinstance(self.modifiers, FrameModifierVector):
            raise TypeError("modifiers must be FrameModifierVector")

    @property
    def key(self) -> tuple[str, str]:
        return self.surface.value, self.target_name

    def semantic_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface.value,
            "target_name": self.target_name,
            "modifiers": self.modifiers.as_list(),
        }


@dataclass(frozen=True, slots=True)
class FrameModifierMutationFact:
    surface: FrameModifierSurface
    target_name: str
    before: FrameModifierReadFact
    setter: FrameModifierSetFact
    after: FrameModifierReadFact
    mutation_ref: str = field(init=False)
    contract: str = FRAME_MODIFIER_MUTATION_FACT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != FRAME_MODIFIER_MUTATION_FACT_CONTRACT:
            raise AnalysisStateMutationError(
                "frame modifier mutation fact contract mismatch",
                stage="mutation_fact_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        if not isinstance(self.surface, FrameModifierSurface):
            raise TypeError("surface must be FrameModifierSurface")
        target = _text(self.target_name, "target_name")
        object.__setattr__(self, "target_name", target)
        for label, fact in (("before", self.before), ("setter", self.setter), ("after", self.after)):
            expected = FrameModifierSetFact if label == "setter" else FrameModifierReadFact
            if not isinstance(fact, expected):
                raise TypeError(f"{label} has wrong factual type")
            if fact.surface is not self.surface or fact.target_name != target:
                raise AnalysisStateMutationError(
                    f"{label} fact does not bind to mutation target",
                    stage="mutation_fact_contract",
                    restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
                )
        object.__setattr__(
            self,
            "mutation_ref",
            _digest(
                MUTATION_FACT_REF_PREFIX,
                {
                    "contract": self.contract,
                    "surface": self.surface.value,
                    "target_name": target,
                    "before_ref": self.before.evidence_ref,
                    "setter_ref": self.setter.evidence_ref,
                    "after_ref": self.after.evidence_ref,
                },
            ),
        )

    def semantic_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface.value,
            "target_name": self.target_name,
            "before": self.before.modifiers.as_list(),
            "setter_return_code": self.setter.return_code,
            "after": self.after.modifiers.as_list(),
            "mutation_ref": self.mutation_ref,
        }


@dataclass(frozen=True, slots=True)
class AnalysisStateMutationManifest:
    source_model_ref: str
    ownership_proof_ref: str
    requested_manifest_ref: str
    active_model_path_before: str
    active_model_path_after: str
    model_locked_before: bool | None
    model_locked_after: bool | None
    source_before: PhysicalFileSnapshot
    source_after: PhysicalFileSnapshot
    mutations: tuple[FrameModifierMutationFact, ...]
    logically_invalidates_prior_analysis_results: bool = True
    logically_invalidates_prior_design_results: bool = True
    manifest_ref: str = field(init=False)
    contract: str = ANALYSIS_STATE_MUTATION_MANIFEST_CONTRACT

    def __post_init__(self) -> None:
        for name in ("source_model_ref", "ownership_proof_ref", "requested_manifest_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.contract != ANALYSIS_STATE_MUTATION_MANIFEST_CONTRACT:
            raise AnalysisStateMutationError(
                "analysis-state mutation manifest contract mismatch",
                stage="mutation_manifest_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        if not self.mutations:
            raise AnalysisStateMutationError(
                "analysis-state mutation manifest requires at least one mutation",
                stage="mutation_manifest_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        if (
            self.logically_invalidates_prior_analysis_results is not True
            or self.logically_invalidates_prior_design_results is not True
        ):
            raise AnalysisStateMutationError(
                "B4B mutation must logically invalidate all prior analysis/design result identities",
                stage="mutation_manifest_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        keys = [(item.surface.value, item.target_name) for item in self.mutations]
        if len(set(keys)) != len(keys):
            raise AnalysisStateMutationError(
                "analysis-state mutation manifest contains duplicate targets",
                stage="mutation_manifest_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        object.__setattr__(
            self,
            "manifest_ref",
            _digest(
                MUTATION_MANIFEST_REF_PREFIX,
                {
                    "contract": self.contract,
                    "source_model_ref": self.source_model_ref,
                    "ownership_proof_ref": self.ownership_proof_ref,
                    "requested_manifest_ref": self.requested_manifest_ref,
                    "active_model_path_before": self.active_model_path_before,
                    "active_model_path_after": self.active_model_path_after,
                    "model_locked_before": self.model_locked_before,
                    "model_locked_after": self.model_locked_after,
                    "source_before_sha256": self.source_before.sha256_content_digest,
                    "source_after_sha256": self.source_after.sha256_content_digest,
                    "mutations": [item.semantic_dict() for item in self.mutations],
                    "logical_invalidation": {"analysis_results": True, "design_results": True},
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class AnalysisStateMutationResult:
    requested_manifest: RequestedDerivedStateManifest
    mutation_manifest: AnalysisStateMutationManifest
    established_manifest: EstablishedDerivedStateManifest
    comparison: DerivedStateComparison
    analysis_state_identity: AnalysisStateIdentity
    contract: str = ANALYSIS_STATE_MUTATION_RESULT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ANALYSIS_STATE_MUTATION_RESULT_CONTRACT:
            raise AnalysisStateMutationError(
                "analysis-state mutation result contract mismatch",
                stage="result_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        if not self.comparison.matched:
            raise AnalysisStateMutationError(
                "positive B4B result requires a matched derived-state comparison",
                stage="result_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )


def _ordered_targets(targets: Sequence[FrameModifierTargetRequest]) -> tuple[FrameModifierTargetRequest, ...]:
    if isinstance(targets, (str, bytes)) or not isinstance(targets, Sequence):
        raise TypeError("targets must be a sequence")
    normalized = tuple(targets)
    if not normalized:
        raise AnalysisStateMutationError(
            "frame modifier request requires at least one target",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    if not all(isinstance(item, FrameModifierTargetRequest) for item in normalized):
        raise TypeError("targets must contain FrameModifierTargetRequest")
    keys = [item.key for item in normalized]
    if len(set(keys)) != len(keys):
        raise AnalysisStateMutationError(
            "duplicate frame modifier request target",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    return tuple(sorted(normalized, key=lambda item: item.key))


def build_requested_frame_modifier_manifest(
    *,
    source_model_ref: str,
    targets: Sequence[FrameModifierTargetRequest],
    tolerance: NumericTolerance = NumericTolerance(),
    provenance_refs: Sequence[str] = (),
) -> RequestedDerivedStateManifest:
    ordered = _ordered_targets(targets)
    if not isinstance(tolerance, NumericTolerance):
        raise TypeError("tolerance must be NumericTolerance")
    entry = request_derived_state(
        family=DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS,
        value={
            "contract": FRAME_MODIFIER_PLAN_CONTRACT,
            "targets": [item.semantic_dict() for item in ordered],
        },
        tolerance=tolerance,
        provenance_refs=provenance_refs,
    )
    return RequestedDerivedStateManifest(
        source_model_ref=_text(source_model_ref, "source_model_ref"),
        entries=(entry,),
        provenance_refs=tuple(provenance_refs),
    )


def _parse_requested_targets(manifest: RequestedDerivedStateManifest) -> tuple[FrameModifierTargetRequest, ...]:
    if not isinstance(manifest, RequestedDerivedStateManifest):
        raise TypeError("requested_manifest must be RequestedDerivedStateManifest")
    if manifest.family_set != frozenset({DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS}):
        raise AnalysisStateMutationError(
            "B4B-R1 accepts only SECTION_STIFFNESS_MODIFIERS",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    if len(manifest.entries) != 1:
        raise AnalysisStateMutationError(
            "B4B-R1 requires exactly one derived-state entry",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    value = manifest.entries[0].canonical_value
    if not isinstance(value, Mapping) or value.get("contract") != FRAME_MODIFIER_PLAN_CONTRACT:
        raise AnalysisStateMutationError(
            "SECTION_STIFFNESS_MODIFIERS requires the B4B frame modifier plan contract",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    raw_targets = value.get("targets")
    if not isinstance(raw_targets, list):
        raise AnalysisStateMutationError(
            "frame modifier plan targets must be a list",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    parsed: list[FrameModifierTargetRequest] = []
    for item in raw_targets:
        if not isinstance(item, Mapping):
            raise AnalysisStateMutationError(
                "frame modifier target must be a mapping",
                stage="request_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        try:
            surface = FrameModifierSurface(item["surface"])
            target_name = item["target_name"]
            modifiers = FrameModifierVector.from_sequence(item["modifiers"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalysisStateMutationError(
                "invalid frame modifier target contract",
                stage="request_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            ) from exc
        parsed.append(FrameModifierTargetRequest(surface=surface, target_name=target_name, modifiers=modifiers))
    return _ordered_targets(parsed)


def _read_identity(context: TrustedLiveAcquisitionContext):
    return reread_verified_session_identity(context.verified_session)


def _require_bindings(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    requested_manifest: RequestedDerivedStateManifest,
) -> object:
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(requested_manifest, RequestedDerivedStateManifest):
        raise TypeError("requested_manifest must be RequestedDerivedStateManifest")
    if owned_scratch.source_model_identity != context.source_model_identity:
        raise AnalysisStateMutationError(
            "owned scratch does not belong to trusted acquisition context",
            stage="source_binding",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    source_ref = context.source_model_identity.source_model_ref
    if requested_manifest.source_model_ref != source_ref:
        raise AnalysisStateMutationError(
            "requested derived state is bound to a different source model",
            stage="source_binding",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    identity = _read_identity(context)
    if _canonical_model_path(identity.model_full_path) != _canonical_model_path(owned_scratch.scratch_path):
        raise AnalysisStateMutationError(
            "active ETABS model is not the qualified owned scratch",
            stage="active_scratch_binding",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            details={"active_model_path": identity.model_full_path, "owned_scratch_path": owned_scratch.scratch_path},
        )
    return identity


def _require_source_unchanged(current: PhysicalFileSnapshot, baseline: PhysicalFileSnapshot, *, stage: str) -> None:
    if not _same_physical_bytes(current, baseline):
        raise AnalysisStateMutationError(
            "protected source physical bytes changed",
            stage=stage,
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            details={
                "baseline_sha256": baseline.sha256_content_digest,
                "current_sha256": current.sha256_content_digest,
                "baseline_size": baseline.file_size_bytes,
                "current_size": current.file_size_bytes,
            },
        )


def _restoration(
    context: TrustedLiveAcquisitionContext,
    before: Mapping[tuple[str, str], FrameModifierReadFact],
    applied: Sequence[tuple[str, str]],
    *,
    timeout_seconds: float,
) -> MutationRestorationStatus:
    if not applied:
        return MutationRestorationStatus.NOT_REQUIRED
    try:
        for key in reversed(tuple(applied)):
            original = before[key]
            setter = set_frame_modifiers_from_session(
                context.verified_session,
                surface=original.surface,
                target_name=original.target_name,
                modifiers=original.modifiers,
                timeout_seconds=timeout_seconds,
            )
            if not setter.success:
                return MutationRestorationStatus.FAILED
            readback = get_frame_modifiers_from_session(
                context.verified_session,
                surface=original.surface,
                target_name=original.target_name,
                timeout_seconds=timeout_seconds,
            )
            if not readback.success or readback.modifiers.as_tuple() != original.modifiers.as_tuple():
                return MutationRestorationStatus.FAILED
    except Exception:
        return MutationRestorationStatus.FAILED
    return MutationRestorationStatus.RESTORED


def _raise_with_restoration(
    *,
    context: TrustedLiveAcquisitionContext,
    before: Mapping[tuple[str, str], FrameModifierReadFact],
    applied: Sequence[tuple[str, str]],
    timeout_seconds: float,
    stage: str,
    message: str,
    details: Mapping[str, object] | None = None,
    cause: BaseException | None = None,
) -> None:
    status = _restoration(context, before, applied, timeout_seconds=timeout_seconds)
    error = AnalysisStateMutationError(
        message,
        stage=stage,
        restoration_status=status.value,
        details=details,
    )
    if cause is None:
        raise error
    raise error from cause


def establish_frame_modifier_analysis_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    requested_manifest: RequestedDerivedStateManifest,
    timeout_seconds: float = 30.0,
) -> AnalysisStateMutationResult:
    """Mutate and causally establish one exact B4B frame-modifier state."""
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    identity_before = _require_bindings(context, owned_scratch, requested_manifest)
    targets = _parse_requested_targets(requested_manifest)

    source_before = capture_physical_file_snapshot(owned_scratch.source_pre.canonical_absolute_path)
    _require_source_unchanged(source_before, owned_scratch.source_post, stage="source_pre_mutation_integrity")

    before: dict[tuple[str, str], FrameModifierReadFact] = {}
    for target in targets:
        fact = get_frame_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            timeout_seconds=timeout,
        )
        if not fact.success:
            raise AnalysisStateMutationError(
                "pre-mutation modifier readback returned nonzero",
                stage="pre_readback",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
                details={"surface": target.surface.value, "target_name": target.target_name, "return_code": fact.return_code},
            )
        before[target.key] = fact

    applied: list[tuple[str, str]] = []
    mutations: list[FrameModifierMutationFact] = []
    try:
        for target in targets:
            setter = set_frame_modifiers_from_session(
                context.verified_session,
                surface=target.surface,
                target_name=target.target_name,
                modifiers=target.modifiers,
                timeout_seconds=timeout,
            )
            applied.append(target.key)
            if not setter.success:
                _raise_with_restoration(
                    context=context,
                    before=before,
                    applied=applied,
                    timeout_seconds=timeout,
                    stage="setter_nonzero",
                    message="frame modifier setter returned nonzero",
                    details={"surface": target.surface.value, "target_name": target.target_name, "return_code": setter.return_code},
                )
            after = get_frame_modifiers_from_session(
                context.verified_session,
                surface=target.surface,
                target_name=target.target_name,
                timeout_seconds=timeout,
            )
            if not after.success:
                _raise_with_restoration(
                    context=context,
                    before=before,
                    applied=applied,
                    timeout_seconds=timeout,
                    stage="post_readback_nonzero",
                    message="post-mutation modifier readback returned nonzero",
                    details={"surface": target.surface.value, "target_name": target.target_name, "return_code": after.return_code},
                )
            mutations.append(FrameModifierMutationFact(surface=target.surface, target_name=target.target_name, before=before[target.key], setter=setter, after=after))
    except AnalysisStateMutationError:
        raise
    except Exception as exc:
        _raise_with_restoration(
            context=context,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="mutation_exception",
            message="frame modifier mutation raised an unexpected factual/transport error",
            cause=exc,
        )

    identity_after = _read_identity(context)
    if _canonical_model_path(identity_after.model_full_path) != _canonical_model_path(owned_scratch.scratch_path):
        _raise_with_restoration(
            context=context,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="active_scratch_postcondition",
            message="active ETABS model changed away from the owned scratch during B4B",
            details={"active_model_path": identity_after.model_full_path},
        )

    source_after = capture_physical_file_snapshot(owned_scratch.source_pre.canonical_absolute_path)
    if not _same_physical_bytes(source_before, source_after):
        _raise_with_restoration(
            context=context,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="source_post_mutation_integrity",
            message="protected source physical bytes changed during B4B mutation",
            details={"before_sha256": source_before.sha256_content_digest, "after_sha256": source_after.sha256_content_digest},
        )

    mutation_manifest = AnalysisStateMutationManifest(
        source_model_ref=context.source_model_identity.source_model_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        requested_manifest_ref=requested_manifest.manifest_ref,
        active_model_path_before=identity_before.model_full_path,
        active_model_path_after=identity_after.model_full_path,
        model_locked_before=identity_before.model_locked,
        model_locked_after=identity_after.model_locked,
        source_before=source_before,
        source_after=source_after,
        mutations=tuple(mutations),
    )

    readback_targets = [
        {"surface": item.surface.value, "target_name": item.target_name, "modifiers": item.after.modifiers.as_list()}
        for item in mutations
    ]
    requested_entry = requested_manifest.entries[0]
    established_entry = _establish_derived_state_from_verified_readback(
        _issuer_token=_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
        family=DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS,
        readback_value={"contract": FRAME_MODIFIER_PLAN_CONTRACT, "targets": readback_targets},
        readback_evidence_refs=tuple(item.after.evidence_ref for item in mutations),
        normalization=requested_entry.normalization,
        provenance_refs=(
            owned_scratch.ownership_proof_ref,
            mutation_manifest.manifest_ref,
            context.acquisition_context_ref,
            context.session_provenance_ref,
        ),
    )
    established_manifest = EstablishedDerivedStateManifest(
        source_model_ref=context.source_model_identity.source_model_ref,
        entries=(established_entry,),
        provenance_refs=(owned_scratch.ownership_proof_ref, mutation_manifest.manifest_ref),
    )
    comparison = compare_derived_state_manifests(
        requested_manifest,
        established_manifest,
        provenance_refs=(mutation_manifest.manifest_ref,),
    )

    if not comparison.matched or not comparison.exact_causal_family_population:
        _raise_with_restoration(
            context=context,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="requested_vs_readback_mismatch",
            message="requested frame modifier state does not match factual ETABS readback",
            details={"comparison_ref": comparison.comparison_ref, "comparison_status": comparison.status.value},
        )

    analysis_state = build_analysis_state_identity_from_derived_state(
        comparison=comparison,
        state_basis_refs=(owned_scratch.ownership_proof_ref, requested_manifest.manifest_ref, mutation_manifest.manifest_ref),
        provenance_refs=(
            context.acquisition_context_ref,
            context.session_provenance_ref,
            owned_scratch.ownership_proof_ref,
            mutation_manifest.manifest_ref,
        ),
    )
    return AnalysisStateMutationResult(
        requested_manifest=requested_manifest,
        mutation_manifest=mutation_manifest,
        established_manifest=established_manifest,
        comparison=comparison,
        analysis_state_identity=analysis_state,
    )


__all__ = [
    "ANALYSIS_STATE_MUTATION_MANIFEST_CONTRACT",
    "ANALYSIS_STATE_MUTATION_RESULT_CONTRACT",
    "FRAME_MODIFIER_MUTATION_FACT_CONTRACT",
    "FRAME_MODIFIER_PLAN_CONTRACT",
    "AnalysisStateMutationError",
    "AnalysisStateMutationManifest",
    "AnalysisStateMutationResult",
    "FrameModifierMutationFact",
    "FrameModifierTargetRequest",
    "MutationRestorationStatus",
    "build_requested_frame_modifier_manifest",
    "establish_frame_modifier_analysis_state",
]
