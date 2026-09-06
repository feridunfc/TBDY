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

``additional_state_basis_refs`` is an opaque identity-commitment seam only. B4B
does not interpret those refs as derived state or factual truth; downstream
positive authorities must validate the typed evidence that owns any such ref.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import ntpath
from typing import Mapping, Sequence

from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSetFact,
    AreaModifierSurface,
    AreaModifierVector,
    get_area_modifiers_from_session,
    set_area_modifiers_from_session,
)
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
SECTION_MODIFIER_PLAN_CONTRACT = "TBDY_B4B_SECTION_MODIFIER_PLAN_V2"
AREA_MODIFIER_MUTATION_FACT_CONTRACT = (
    "TBDY_B4B_AREA_MODIFIER_MUTATION_FACT_V1"
)
SECTION_MODIFIER_MUTATION_MANIFEST_CONTRACT = (
    "TBDY_B4B_SECTION_MODIFIER_MUTATION_MANIFEST_V2"
)
AREA_MUTATION_FACT_REF_PREFIX = "b4b-area-modifier-mutation:sha256:"
SECTION_MUTATION_MANIFEST_REF_PREFIX = (
    "b4b-section-modifier-mutation:sha256:"
)


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
    BLOCKED_UNSAFE = "BLOCKED_UNSAFE"


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


def _additional_basis_refs(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("additional_state_basis_refs must be a sequence of strings")
    normalized = tuple(sorted({_text(value, "additional_state_basis_ref") for value in values}))
    return normalized


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
class AreaModifierTargetRequest:
    surface: AreaModifierSurface
    target_name: str
    modifiers: AreaModifierVector

    def __post_init__(self) -> None:
        if not isinstance(self.surface, AreaModifierSurface):
            raise TypeError("surface must be AreaModifierSurface")
        object.__setattr__(self, "target_name", _text(self.target_name, "target_name"))
        if not isinstance(self.modifiers, AreaModifierVector):
            raise TypeError("modifiers must be AreaModifierVector")

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
class AreaModifierMutationFact:
    surface: AreaModifierSurface
    target_name: str
    before: AreaModifierReadFact
    setter: AreaModifierSetFact
    after: AreaModifierReadFact
    mutation_ref: str = field(init=False)
    contract: str = AREA_MODIFIER_MUTATION_FACT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != AREA_MODIFIER_MUTATION_FACT_CONTRACT:
            raise AnalysisStateMutationError(
                "area modifier mutation fact contract mismatch",
                stage="mutation_fact_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        if not isinstance(self.surface, AreaModifierSurface):
            raise TypeError("surface must be AreaModifierSurface")
        target = _text(self.target_name, "target_name")
        object.__setattr__(self, "target_name", target)
        for label, fact in (
            ("before", self.before),
            ("setter", self.setter),
            ("after", self.after),
        ):
            expected = AreaModifierSetFact if label == "setter" else AreaModifierReadFact
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
                AREA_MUTATION_FACT_REF_PREFIX,
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
class SectionModifierMutationManifest:
    """Explicit V2 mixed frame/Area mutation evidence.

    The frame-only V1 AnalysisStateMutationManifest remains unchanged.
    """

    source_model_ref: str
    ownership_proof_ref: str
    requested_manifest_ref: str
    active_model_path_before: str
    active_model_path_after: str
    model_locked_before: bool | None
    model_locked_after: bool | None
    source_before: PhysicalFileSnapshot
    source_after: PhysicalFileSnapshot
    mutations: tuple[FrameModifierMutationFact | AreaModifierMutationFact, ...]
    logically_invalidates_prior_analysis_results: bool = True
    logically_invalidates_prior_design_results: bool = True
    manifest_ref: str = field(init=False)
    contract: str = SECTION_MODIFIER_MUTATION_MANIFEST_CONTRACT

    def __post_init__(self) -> None:
        for name in ("source_model_ref", "ownership_proof_ref", "requested_manifest_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.contract != SECTION_MODIFIER_MUTATION_MANIFEST_CONTRACT:
            raise AnalysisStateMutationError(
                "section-modifier mutation manifest contract mismatch",
                stage="mutation_manifest_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        if not self.mutations:
            raise AnalysisStateMutationError(
                "section-modifier mutation manifest requires at least one mutation",
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
                "section-modifier mutation manifest contains duplicate targets",
                stage="mutation_manifest_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        object.__setattr__(
            self,
            "manifest_ref",
            _digest(
                SECTION_MUTATION_MANIFEST_REF_PREFIX,
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
                    "logical_invalidation": {
                        "analysis_results": True,
                        "design_results": True,
                    },
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class AnalysisStateMutationResult:
    requested_manifest: RequestedDerivedStateManifest
    mutation_manifest: AnalysisStateMutationManifest | SectionModifierMutationManifest
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


def _active_model_is_owned_scratch(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
) -> bool:
    try:
        identity = _read_identity(context)
        return _canonical_model_path(identity.model_full_path) == _canonical_model_path(
            owned_scratch.scratch_path
        )
    except Exception:
        return False


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
    owned_scratch: OwnedScratchContext,
    before: Mapping[tuple[str, str], FrameModifierReadFact],
    applied: Sequence[tuple[str, str]],
    *,
    timeout_seconds: float,
) -> MutationRestorationStatus:
    if not applied:
        return MutationRestorationStatus.NOT_REQUIRED
    if not _active_model_is_owned_scratch(context, owned_scratch):
        return MutationRestorationStatus.BLOCKED_UNSAFE
    try:
        for key in reversed(tuple(applied)):
            if not _active_model_is_owned_scratch(context, owned_scratch):
                return MutationRestorationStatus.BLOCKED_UNSAFE
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
    owned_scratch: OwnedScratchContext,
    before: Mapping[tuple[str, str], FrameModifierReadFact],
    applied: Sequence[tuple[str, str]],
    timeout_seconds: float,
    stage: str,
    message: str,
    details: Mapping[str, object] | None = None,
    cause: BaseException | None = None,
) -> None:
    status = _restoration(
        context,
        owned_scratch,
        before,
        applied,
        timeout_seconds=timeout_seconds,
    )
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
    additional_state_basis_refs: Sequence[str] = (),
    timeout_seconds: float = 30.0,
) -> AnalysisStateMutationResult:
    """Mutate and causally establish one exact B4B frame-modifier state.

    ``additional_state_basis_refs`` commits already-existing external evidence
    into the resulting state identity without making B4B the semantic owner of
    that evidence. The caller must have obtained such evidence before entering
    this synchronous mutation lifecycle; B4B merely commits its opaque ref.
    """
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    extra_basis_refs = _additional_basis_refs(additional_state_basis_refs)

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
            # Mark the target before entering the setter because an exception can
            # occur after ETABS has partially or fully applied the mutation.
            applied.append(target.key)
            setter = set_frame_modifiers_from_session(
                context.verified_session,
                surface=target.surface,
                target_name=target.target_name,
                modifiers=target.modifiers,
                timeout_seconds=timeout,
            )
            if not setter.success:
                _raise_with_restoration(
                    context=context,
                    owned_scratch=owned_scratch,
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
                    owned_scratch=owned_scratch,
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
            owned_scratch=owned_scratch,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="mutation_exception",
            message="frame modifier mutation raised an unexpected factual/transport error",
            cause=exc,
        )

    try:
        try:
            identity_after = _read_identity(context)
        except Exception as exc:
            _raise_with_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="active_scratch_postcondition_read_failed",
                message="active ETABS model could not be re-read after B4B mutation",
                cause=exc,
            )
        if _canonical_model_path(identity_after.model_full_path) != _canonical_model_path(owned_scratch.scratch_path):
            _raise_with_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="active_scratch_postcondition",
                message="active ETABS model changed away from the owned scratch during B4B",
                details={"active_model_path": identity_after.model_full_path},
            )

        try:
            source_after = capture_physical_file_snapshot(owned_scratch.source_pre.canonical_absolute_path)
        except Exception as exc:
            _raise_with_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="source_post_mutation_snapshot_failed",
                message="protected source physical state could not be re-read after B4B mutation",
                cause=exc,
            )
        if not _same_physical_bytes(source_before, source_after):
            _raise_with_restoration(
                context=context,
                owned_scratch=owned_scratch,
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
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="requested_vs_readback_mismatch",
                message="requested frame modifier state does not match factual ETABS readback",
                details={"comparison_ref": comparison.comparison_ref, "comparison_status": comparison.status.value},
            )

        analysis_state = build_analysis_state_identity_from_derived_state(
            comparison=comparison,
            state_basis_refs=(
                owned_scratch.ownership_proof_ref,
                requested_manifest.manifest_ref,
                mutation_manifest.manifest_ref,
                *extra_basis_refs,
            ),
            provenance_refs=(
                context.acquisition_context_ref,
                context.session_provenance_ref,
                owned_scratch.ownership_proof_ref,
                mutation_manifest.manifest_ref,
                *extra_basis_refs,
            ),
        )
        return AnalysisStateMutationResult(
            requested_manifest=requested_manifest,
            mutation_manifest=mutation_manifest,
            established_manifest=established_manifest,
            comparison=comparison,
            analysis_state_identity=analysis_state,
        )
    except AnalysisStateMutationError as exc:
        if exc.restoration_status != MutationRestorationStatus.NOT_REQUIRED.value:
            raise
        _raise_with_restoration(
            context=context,
            owned_scratch=owned_scratch,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="post_mutation_qualification_error",
            message="B4B post-mutation qualification failed before positive AnalysisStateIdentity issuance",
            details={"inner_stage": exc.stage},
            cause=exc,
        )
    except Exception as exc:
        _raise_with_restoration(
            context=context,
            owned_scratch=owned_scratch,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="post_mutation_qualification_exception",
            message="B4B post-mutation qualification raised an unexpected error",
            cause=exc,
        )


SectionModifierTargetRequest = FrameModifierTargetRequest | AreaModifierTargetRequest
SectionModifierReadFact = FrameModifierReadFact | AreaModifierReadFact
SectionModifierSetFact = FrameModifierSetFact | AreaModifierSetFact
SectionModifierMutationFact = FrameModifierMutationFact | AreaModifierMutationFact


def _ordered_section_targets(
    targets: Sequence[SectionModifierTargetRequest],
) -> tuple[SectionModifierTargetRequest, ...]:
    if isinstance(targets, (str, bytes)) or not isinstance(targets, Sequence):
        raise TypeError("targets must be a sequence")
    normalized = tuple(targets)
    if not normalized:
        raise AnalysisStateMutationError(
            "section modifier request requires at least one target",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    if not all(
        isinstance(item, (FrameModifierTargetRequest, AreaModifierTargetRequest))
        for item in normalized
    ):
        raise TypeError(
            "targets must contain FrameModifierTargetRequest or AreaModifierTargetRequest"
        )
    keys = [item.key for item in normalized]
    if len(set(keys)) != len(keys):
        raise AnalysisStateMutationError(
            "duplicate section modifier request target",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    surface_rank = {
        FrameModifierSurface.FRAME_SECTION_PROPERTY.value: 0,
        AreaModifierSurface.AREA_PROPERTY.value: 1,
        FrameModifierSurface.FRAME_OBJECT.value: 2,
        AreaModifierSurface.AREA_OBJECT.value: 3,
    }
    return tuple(
        sorted(
            normalized,
            key=lambda item: (
                surface_rank[item.surface.value],
                item.surface.value,
                item.target_name,
            ),
        )
    )


def build_requested_section_modifier_manifest(
    *,
    source_model_ref: str,
    targets: Sequence[SectionModifierTargetRequest],
    tolerance: NumericTolerance = NumericTolerance(),
    provenance_refs: Sequence[str] = (),
) -> RequestedDerivedStateManifest:
    ordered = _ordered_section_targets(targets)
    if not isinstance(tolerance, NumericTolerance):
        raise TypeError("tolerance must be NumericTolerance")
    entry = request_derived_state(
        family=DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS,
        value={
            "contract": SECTION_MODIFIER_PLAN_CONTRACT,
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


def _parse_requested_section_targets(
    manifest: RequestedDerivedStateManifest,
) -> tuple[SectionModifierTargetRequest, ...]:
    if not isinstance(manifest, RequestedDerivedStateManifest):
        raise TypeError("requested_manifest must be RequestedDerivedStateManifest")
    if manifest.family_set != frozenset({DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS}):
        raise AnalysisStateMutationError(
            "B4B mixed path accepts only SECTION_STIFFNESS_MODIFIERS",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    if len(manifest.entries) != 1:
        raise AnalysisStateMutationError(
            "B4B mixed path requires exactly one derived-state entry",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    value = manifest.entries[0].canonical_value
    if not isinstance(value, Mapping) or value.get("contract") != SECTION_MODIFIER_PLAN_CONTRACT:
        raise AnalysisStateMutationError(
            "SECTION_STIFFNESS_MODIFIERS mixed path requires the B4B V2 section modifier plan contract",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    raw_targets = value.get("targets")
    if not isinstance(raw_targets, list):
        raise AnalysisStateMutationError(
            "section modifier plan targets must be a list",
            stage="request_contract",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
        )
    parsed: list[SectionModifierTargetRequest] = []
    frame_surfaces = {member.value for member in FrameModifierSurface}
    area_surfaces = {member.value for member in AreaModifierSurface}
    for item in raw_targets:
        if not isinstance(item, Mapping):
            raise AnalysisStateMutationError(
                "section modifier target must be a mapping",
                stage="request_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            )
        try:
            surface_raw = item["surface"]
            target_name = item["target_name"]
            modifiers_raw = item["modifiers"]
            if surface_raw in frame_surfaces:
                parsed.append(
                    FrameModifierTargetRequest(
                        surface=FrameModifierSurface(surface_raw),
                        target_name=target_name,
                        modifiers=FrameModifierVector.from_sequence(modifiers_raw),
                    )
                )
            elif surface_raw in area_surfaces:
                parsed.append(
                    AreaModifierTargetRequest(
                        surface=AreaModifierSurface(surface_raw),
                        target_name=target_name,
                        modifiers=AreaModifierVector.from_sequence(modifiers_raw),
                    )
                )
            else:
                raise ValueError("unsupported section-modifier surface")
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalysisStateMutationError(
                "invalid section modifier target contract",
                stage="request_contract",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            ) from exc
    return _ordered_section_targets(parsed)


def _get_section_modifier_fact(
    context: TrustedLiveAcquisitionContext,
    target: SectionModifierTargetRequest,
    *,
    timeout_seconds: float,
) -> SectionModifierReadFact:
    if isinstance(target, FrameModifierTargetRequest):
        return get_frame_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            timeout_seconds=timeout_seconds,
        )
    if isinstance(target, AreaModifierTargetRequest):
        return get_area_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            timeout_seconds=timeout_seconds,
        )
    raise TypeError("unsupported section-modifier target")


def _set_section_modifier(
    context: TrustedLiveAcquisitionContext,
    target: SectionModifierTargetRequest,
    *,
    timeout_seconds: float,
) -> SectionModifierSetFact:
    if isinstance(target, FrameModifierTargetRequest):
        return set_frame_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            modifiers=target.modifiers,
            timeout_seconds=timeout_seconds,
        )
    if isinstance(target, AreaModifierTargetRequest):
        return set_area_modifiers_from_session(
            context.verified_session,
            surface=target.surface,
            target_name=target.target_name,
            modifiers=target.modifiers,
            timeout_seconds=timeout_seconds,
        )
    raise TypeError("unsupported section-modifier target")


def _restore_one_section_fact(
    context: TrustedLiveAcquisitionContext,
    original: SectionModifierReadFact,
    *,
    timeout_seconds: float,
) -> bool:
    if isinstance(original, FrameModifierReadFact):
        setter = set_frame_modifiers_from_session(
            context.verified_session,
            surface=original.surface,
            target_name=original.target_name,
            modifiers=original.modifiers,
            timeout_seconds=timeout_seconds,
        )
        if not setter.success:
            return False
        readback = get_frame_modifiers_from_session(
            context.verified_session,
            surface=original.surface,
            target_name=original.target_name,
            timeout_seconds=timeout_seconds,
        )
    elif isinstance(original, AreaModifierReadFact):
        setter = set_area_modifiers_from_session(
            context.verified_session,
            surface=original.surface,
            target_name=original.target_name,
            modifiers=original.modifiers,
            timeout_seconds=timeout_seconds,
        )
        if not setter.success:
            return False
        readback = get_area_modifiers_from_session(
            context.verified_session,
            surface=original.surface,
            target_name=original.target_name,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise TypeError("unsupported section-modifier read fact")
    return readback.success and readback.modifiers.as_tuple() == original.modifiers.as_tuple()


def _section_restoration(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    before: Mapping[tuple[str, str], SectionModifierReadFact],
    applied: Sequence[tuple[str, str]],
    *,
    timeout_seconds: float,
) -> MutationRestorationStatus:
    if not applied:
        return MutationRestorationStatus.NOT_REQUIRED
    if not _active_model_is_owned_scratch(context, owned_scratch):
        return MutationRestorationStatus.BLOCKED_UNSAFE
    try:
        for key in reversed(tuple(applied)):
            if not _active_model_is_owned_scratch(context, owned_scratch):
                return MutationRestorationStatus.BLOCKED_UNSAFE
            if not _restore_one_section_fact(
                context,
                before[key],
                timeout_seconds=timeout_seconds,
            ):
                return MutationRestorationStatus.FAILED
    except Exception:
        return MutationRestorationStatus.FAILED
    return MutationRestorationStatus.RESTORED


def _raise_with_section_restoration(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    before: Mapping[tuple[str, str], SectionModifierReadFact],
    applied: Sequence[tuple[str, str]],
    timeout_seconds: float,
    stage: str,
    message: str,
    details: Mapping[str, object] | None = None,
    cause: BaseException | None = None,
) -> None:
    status = _section_restoration(
        context,
        owned_scratch,
        before,
        applied,
        timeout_seconds=timeout_seconds,
    )
    error = AnalysisStateMutationError(
        message,
        stage=stage,
        restoration_status=status.value,
        details=details,
    )
    if cause is None:
        raise error
    raise error from cause


def establish_section_modifier_analysis_state(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    requested_manifest: RequestedDerivedStateManifest,
    additional_state_basis_refs: Sequence[str] = (),
    timeout_seconds: float = 30.0,
) -> AnalysisStateMutationResult:
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    extra_basis_refs = _additional_basis_refs(additional_state_basis_refs)

    identity_before = _require_bindings(context, owned_scratch, requested_manifest)
    if identity_before.model_locked is not False:
        raise AnalysisStateMutationError(
            "mixed section-modifier mutation requires an unlocked owned scratch",
            stage="scratch_locked",
            restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
            details={"model_locked": identity_before.model_locked},
        )
    targets = _parse_requested_section_targets(requested_manifest)

    source_before = capture_physical_file_snapshot(
        owned_scratch.source_pre.canonical_absolute_path
    )
    _require_source_unchanged(
        source_before,
        owned_scratch.source_post,
        stage="source_pre_mutation_integrity",
    )

    before: dict[tuple[str, str], SectionModifierReadFact] = {}
    for target in targets:
        fact = _get_section_modifier_fact(context, target, timeout_seconds=timeout)
        if not fact.success:
            raise AnalysisStateMutationError(
                "pre-mutation modifier readback returned nonzero",
                stage="pre_readback",
                restoration_status=MutationRestorationStatus.NOT_REQUIRED.value,
                details={
                    "surface": target.surface.value,
                    "target_name": target.target_name,
                    "return_code": fact.return_code,
                },
            )
        before[target.key] = fact

    applied: list[tuple[str, str]] = []
    mutations: list[SectionModifierMutationFact] = []
    try:
        for target in targets:
            applied.append(target.key)
            setter = _set_section_modifier(context, target, timeout_seconds=timeout)
            if not setter.success:
                _raise_with_section_restoration(
                    context=context,
                    owned_scratch=owned_scratch,
                    before=before,
                    applied=applied,
                    timeout_seconds=timeout,
                    stage="setter_nonzero",
                    message="section modifier setter returned nonzero",
                    details={
                        "surface": target.surface.value,
                        "target_name": target.target_name,
                        "return_code": setter.return_code,
                    },
                )
            after = _get_section_modifier_fact(context, target, timeout_seconds=timeout)
            if not after.success:
                _raise_with_section_restoration(
                    context=context,
                    owned_scratch=owned_scratch,
                    before=before,
                    applied=applied,
                    timeout_seconds=timeout,
                    stage="post_readback_nonzero",
                    message="post-mutation modifier readback returned nonzero",
                    details={
                        "surface": target.surface.value,
                        "target_name": target.target_name,
                        "return_code": after.return_code,
                    },
                )
            if isinstance(target, FrameModifierTargetRequest):
                original = before[target.key]
                if not isinstance(original, FrameModifierReadFact):
                    raise TypeError("frame PRE read returned wrong factual type")
                if not isinstance(setter, FrameModifierSetFact):
                    raise TypeError("frame setter returned wrong factual type")
                if not isinstance(after, FrameModifierReadFact):
                    raise TypeError("frame POST read returned wrong factual type")
                mutation = FrameModifierMutationFact(
                    surface=target.surface,
                    target_name=target.target_name,
                    before=original,
                    setter=setter,
                    after=after,
                )
            else:
                original = before[target.key]
                if not isinstance(original, AreaModifierReadFact):
                    raise TypeError("Area PRE read returned wrong factual type")
                if not isinstance(setter, AreaModifierSetFact):
                    raise TypeError("Area setter returned wrong factual type")
                if not isinstance(after, AreaModifierReadFact):
                    raise TypeError("Area POST read returned wrong factual type")
                mutation = AreaModifierMutationFact(
                    surface=target.surface,
                    target_name=target.target_name,
                    before=original,
                    setter=setter,
                    after=after,
                )
            mutations.append(mutation)
    except AnalysisStateMutationError:
        raise
    except Exception as exc:
        _raise_with_section_restoration(
            context=context,
            owned_scratch=owned_scratch,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="mutation_exception",
            message="section modifier mutation raised an unexpected factual/transport error",
            cause=exc,
        )

    try:
        try:
            identity_after = _read_identity(context)
        except Exception as exc:
            _raise_with_section_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="active_scratch_postcondition_read_failed",
                message="active ETABS model could not be re-read after mixed B4B mutation",
                cause=exc,
            )
        if _canonical_model_path(identity_after.model_full_path) != _canonical_model_path(
            owned_scratch.scratch_path
        ):
            _raise_with_section_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="active_scratch_postcondition",
                message="active ETABS model changed away from the owned scratch during mixed B4B mutation",
                details={"active_model_path": identity_after.model_full_path},
            )
        if identity_after.model_locked is not False:
            _raise_with_section_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="scratch_lock_postcondition",
                message="owned scratch became locked during mixed section-modifier mutation",
                details={"model_locked": identity_after.model_locked},
            )

        try:
            source_after = capture_physical_file_snapshot(
                owned_scratch.source_pre.canonical_absolute_path
            )
        except Exception as exc:
            _raise_with_section_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="source_post_mutation_snapshot_failed",
                message="protected source physical state could not be re-read after mixed B4B mutation",
                cause=exc,
            )
        if not _same_physical_bytes(source_before, source_after):
            _raise_with_section_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="source_post_mutation_integrity",
                message="protected source physical bytes changed during mixed B4B mutation",
                details={
                    "before_sha256": source_before.sha256_content_digest,
                    "after_sha256": source_after.sha256_content_digest,
                },
            )

        mutation_manifest = SectionModifierMutationManifest(
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
            {
                "surface": item.surface.value,
                "target_name": item.target_name,
                "modifiers": item.after.modifiers.as_list(),
            }
            for item in mutations
        ]
        requested_entry = requested_manifest.entries[0]
        established_entry = _establish_derived_state_from_verified_readback(
            _issuer_token=_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
            family=DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS,
            readback_value={
                "contract": SECTION_MODIFIER_PLAN_CONTRACT,
                "targets": readback_targets,
            },
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
            provenance_refs=(
                owned_scratch.ownership_proof_ref,
                mutation_manifest.manifest_ref,
            ),
        )
        comparison = compare_derived_state_manifests(
            requested_manifest,
            established_manifest,
            provenance_refs=(mutation_manifest.manifest_ref,),
        )

        if not comparison.matched or not comparison.exact_causal_family_population:
            _raise_with_section_restoration(
                context=context,
                owned_scratch=owned_scratch,
                before=before,
                applied=applied,
                timeout_seconds=timeout,
                stage="requested_vs_readback_mismatch",
                message="requested mixed section modifier state does not match factual ETABS readback",
                details={
                    "comparison_ref": comparison.comparison_ref,
                    "comparison_status": comparison.status.value,
                },
            )

        analysis_state = build_analysis_state_identity_from_derived_state(
            comparison=comparison,
            state_basis_refs=(
                owned_scratch.ownership_proof_ref,
                requested_manifest.manifest_ref,
                mutation_manifest.manifest_ref,
                *extra_basis_refs,
            ),
            provenance_refs=(
                context.acquisition_context_ref,
                context.session_provenance_ref,
                owned_scratch.ownership_proof_ref,
                mutation_manifest.manifest_ref,
                *extra_basis_refs,
            ),
        )
        return AnalysisStateMutationResult(
            requested_manifest=requested_manifest,
            mutation_manifest=mutation_manifest,
            established_manifest=established_manifest,
            comparison=comparison,
            analysis_state_identity=analysis_state,
        )
    except AnalysisStateMutationError as exc:
        if exc.restoration_status != MutationRestorationStatus.NOT_REQUIRED.value:
            raise
        _raise_with_section_restoration(
            context=context,
            owned_scratch=owned_scratch,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="post_mutation_qualification_error",
            message="mixed B4B post-mutation qualification failed before positive AnalysisStateIdentity issuance",
            details={"inner_stage": exc.stage},
            cause=exc,
        )
    except Exception as exc:
        _raise_with_section_restoration(
            context=context,
            owned_scratch=owned_scratch,
            before=before,
            applied=applied,
            timeout_seconds=timeout,
            stage="post_mutation_qualification_exception",
            message="mixed B4B post-mutation qualification raised an unexpected error",
            cause=exc,
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
    "AreaModifierMutationFact",
    "AreaModifierTargetRequest",
    "SectionModifierMutationManifest",
    "MutationRestorationStatus",
    "SECTION_MODIFIER_PLAN_CONTRACT",
    "SECTION_MODIFIER_MUTATION_MANIFEST_CONTRACT",
    "AREA_MODIFIER_MUTATION_FACT_CONTRACT",
    "build_requested_frame_modifier_manifest",
    "build_requested_section_modifier_manifest",
    "establish_frame_modifier_analysis_state",
    "establish_section_modifier_analysis_state",
]
