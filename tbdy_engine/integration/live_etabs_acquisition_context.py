"""Trusted live ETABS factual acquisition-context lifecycle.

This module is a neutral runtime/integration seam. It binds one already
verified live ETABS session to one factory-owned evidence acquisition epoch and
exposes narrow consumers for existing factual F0/P8A acquisition paths.

Identity semantics are intentionally bounded:

* ``SourceModelIdentity`` identifies the verified ETABS source-model reference
  (the normalized full model path observed through the verified session). It is
  not proof of physical file bytes, current in-memory model state, analysis
  state, or analysis results.
* ``model_fingerprint`` is a backward-compatible fingerprint of that bounded
  source-model reference only.
* ``EvidenceEpoch`` identifies one factory-created factual acquisition
  generation. A new context creation intentionally creates a new generation;
  callers cannot supply the epoch id, model fingerprint, or session provenance.

Raw ETABS COM capability is never exposed by this context. All live factual
acquisitions use verified-session semantic providers backed by OAPI -> safety ->
gateway. No engineering/regulatory rule is defined here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import ntpath
import uuid
from typing import Mapping, Sequence

from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession,
    reread_verified_session_identity,
    verify_target_model,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnTopologyEvidenceEnvelope,
)
from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.integration.f0_evidence_adapter import (
    F0EvidenceBinding,
    build_component_f0_authorities,
)
from tbdy_engine.providers.etabs_combo_definition_provider import (
    EtabsComboDefinitionEvidence,
    capture_etabs_combo_definitions_from_session,
)
from tbdy_engine.providers.etabs_concrete_column_design_result_provider import (
    capture_concrete_column_design_results_from_session,
)
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    ActualConcreteDesignComboSelectionPopulation,
    acquire_actual_concrete_design_combo_selection_from_session,
)
from tbdy_engine.providers.etabs_concrete_design_section_provider import (
    ConcreteColumnDesignSectionPopulation,
    capture_concrete_column_design_sections_from_session,
)


SOURCE_MODEL_IDENTITY_CONTRACT = "TRUSTED_LIVE_ETABS_SOURCE_MODEL_REFERENCE_V1"
SOURCE_MODEL_IDENTITY_SEMANTICS = (
    "VERIFIED_TARGET_MODEL_REFERENCE_ONLY_NOT_PHYSICAL_FILE_OR_IN_MEMORY_STATE"
)
MODEL_FINGERPRINT_SEMANTICS = (
    "FINGERPRINT_OF_VERIFIED_SOURCE_MODEL_REFERENCE_ONLY_NOT_PHYSICAL_OR_ANALYSIS_STATE"
)
SESSION_PROVENANCE_CONTRACT = "TRUSTED_LIVE_ETABS_SESSION_PROVENANCE_V1"
ACQUISITION_EPOCH_CONTRACT = "TRUSTED_LIVE_ETABS_ACQUISITION_EPOCH_V1"
ACQUISITION_CONTEXT_CONTRACT = "TRUSTED_LIVE_ETABS_ACQUISITION_CONTEXT_V1"

SOURCE_MODEL_REF_PREFIX = "etabs-source-model-ref:sha256:"
MODEL_FINGERPRINT_PREFIX = "etabs-model-fingerprint:source-reference-only:sha256:"
SESSION_PROVENANCE_PREFIX = "etabs-session-provenance:sha256:"
ACQUISITION_GENERATION_PREFIX = "etabs-acquisition-generation:uuid4:"
ACQUISITION_EPOCH_PREFIX = "epoch:live-acquisition:sha256:"
ACQUISITION_CONTEXT_PREFIX = "etabs-acquisition-context:sha256:"

_FACTORY_TOKEN = object()


class LiveAcquisitionContextError(RuntimeError):
    """Fail-closed trusted live acquisition-context construction/use error."""


class LiveAcquisitionContextMismatchError(LiveAcquisitionContextError):
    """Raised when factual evidence is presented from another acquisition context."""


def _canonical_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise LiveAcquisitionContextError(f"{label} must be a nonblank canonical string")
    return value


def _plain(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _plain(value.value)
    candidate = getattr(value, "value", None)
    if candidate is not None and candidate is not value:
        return _plain(candidate)
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise LiveAcquisitionContextError("session identity mapping keys must be strings")
            result[key] = _plain(item)
        return result
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    raise LiveAcquisitionContextError(
        f"session identity contains unsupported deterministic value type: {type(value).__name__}"
    )


def _stable_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(
            _plain(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LiveAcquisitionContextError(
            "trusted acquisition identity is not deterministic JSON-safe"
        ) from exc


def _digest(prefix: str, payload: object) -> str:
    return prefix + hashlib.sha256(_stable_json_bytes(payload)).hexdigest()


def _normalize_verified_model_reference(path: str) -> str:
    value = _canonical_text(path, "verified model full path")
    return ntpath.normcase(ntpath.normpath(value))


def _session_identity_payload(identity: object) -> dict[str, object]:
    as_dict = getattr(identity, "as_dict", None)
    if not callable(as_dict):
        raise LiveAcquisitionContextError("verified session identity has no factual serialization")
    payload = as_dict()
    if not isinstance(payload, Mapping):
        raise LiveAcquisitionContextError("verified session identity serialization is invalid")
    return dict(payload)


def _new_acquisition_generation_ref() -> str:
    return ACQUISITION_GENERATION_PREFIX + uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class SourceModelIdentity:
    """Bounded identity of the verified target model reference, not model state."""

    source_model_ref: str
    model_fingerprint: str
    normalized_model_reference: str
    semantics: str = SOURCE_MODEL_IDENTITY_SEMANTICS
    model_fingerprint_semantics: str = MODEL_FINGERPRINT_SEMANTICS

    def __post_init__(self) -> None:
        _canonical_text(self.source_model_ref, "source_model_ref")
        _canonical_text(self.model_fingerprint, "model_fingerprint")
        _canonical_text(self.normalized_model_reference, "normalized_model_reference")
        if self.semantics != SOURCE_MODEL_IDENTITY_SEMANTICS:
            raise LiveAcquisitionContextError("source-model identity semantics mismatch")
        if self.model_fingerprint_semantics != MODEL_FINGERPRINT_SEMANTICS:
            raise LiveAcquisitionContextError("model fingerprint semantics mismatch")


@dataclass(frozen=True, slots=True, init=False)
class TrustedLiveAcquisitionContext:
    """One verified live ETABS session bound to one factual acquisition epoch."""

    verified_session: EtabsVerifiedSession
    source_model_identity: SourceModelIdentity
    evidence_epoch: EvidenceEpoch
    acquisition_generation_ref: str
    session_provenance_ref: str
    acquisition_context_ref: str

    def __init__(
        self,
        *,
        _token: object = None,
        verified_session: EtabsVerifiedSession,
        source_model_identity: SourceModelIdentity,
        evidence_epoch: EvidenceEpoch,
        acquisition_generation_ref: str,
        session_provenance_ref: str,
        acquisition_context_ref: str,
    ) -> None:
        if _token is not _FACTORY_TOKEN:
            raise TypeError(
                "TrustedLiveAcquisitionContext is factory-created only; use "
                "create_trusted_live_acquisition_context"
            )
        object.__setattr__(self, "verified_session", verified_session)
        object.__setattr__(self, "source_model_identity", source_model_identity)
        object.__setattr__(self, "evidence_epoch", evidence_epoch)
        object.__setattr__(
            self,
            "acquisition_generation_ref",
            _canonical_text(acquisition_generation_ref, "acquisition_generation_ref"),
        )
        object.__setattr__(
            self,
            "session_provenance_ref",
            _canonical_text(session_provenance_ref, "session_provenance_ref"),
        )
        object.__setattr__(
            self,
            "acquisition_context_ref",
            _canonical_text(acquisition_context_ref, "acquisition_context_ref"),
        )

    @property
    def model_fingerprint(self) -> str:
        """Backward-compatible bounded source-model-reference fingerprint."""
        return self.source_model_identity.model_fingerprint

    @property
    def evidence_epoch_id(self) -> str:
        return self.evidence_epoch.epoch_id

    def require_model_epoch(
        self,
        *,
        model_fingerprint: str,
        evidence_epoch_id: str,
    ) -> None:
        """Reject any factual object not carrying this exact model-reference/epoch pair."""
        if (
            model_fingerprint != self.model_fingerprint
            or evidence_epoch_id != self.evidence_epoch_id
        ):
            raise LiveAcquisitionContextMismatchError(
                "factual evidence model-reference/EvidenceEpoch does not belong to this acquisition context"
            )

    def require_session_provenance(self, session_provenance_ref: str) -> None:
        if session_provenance_ref != self.session_provenance_ref:
            raise LiveAcquisitionContextMismatchError(
                "factual evidence session provenance does not belong to this acquisition context"
            )


def create_trusted_live_acquisition_context(
    verified_session: EtabsVerifiedSession,
) -> TrustedLiveAcquisitionContext:
    """Create one factory-owned factual acquisition generation from a verified session.

    The caller supplies no model fingerprint, epoch id, acquisition generation,
    session provenance, or context identity. The live session is re-read through
    the bounded gateway path and must still match the identity captured by
    ``attach_verified_to_running_etabs``.
    """
    if not isinstance(verified_session, EtabsVerifiedSession):
        raise TypeError("verified_session must be EtabsVerifiedSession")

    current_identity = reread_verified_session_identity(verified_session)
    verify_target_model(current_identity, verified_session.identity.model_full_path)
    if current_identity != verified_session.identity:
        raise LiveAcquisitionContextMismatchError(
            "verified ETABS session identity changed before acquisition-context creation"
        )

    normalized_reference = _normalize_verified_model_reference(current_identity.model_full_path)
    source_payload = {
        "contract": SOURCE_MODEL_IDENTITY_CONTRACT,
        "semantics": SOURCE_MODEL_IDENTITY_SEMANTICS,
        "normalized_model_reference": normalized_reference,
    }
    source_digest = hashlib.sha256(_stable_json_bytes(source_payload)).hexdigest()
    source_identity = SourceModelIdentity(
        source_model_ref=SOURCE_MODEL_REF_PREFIX + source_digest,
        model_fingerprint=MODEL_FINGERPRINT_PREFIX + source_digest,
        normalized_model_reference=normalized_reference,
    )

    generation_ref = _new_acquisition_generation_ref()
    session_payload = {
        "contract": SESSION_PROVENANCE_CONTRACT,
        "source_model_ref": source_identity.source_model_ref,
        "verified_session_identity": _session_identity_payload(current_identity),
        "acquisition_generation_ref": generation_ref,
    }
    session_ref = _digest(SESSION_PROVENANCE_PREFIX, session_payload)

    epoch_payload = {
        "contract": ACQUISITION_EPOCH_CONTRACT,
        "origin": EvidenceEpochOrigin.LIVE_CAPTURE.value,
        "model_fingerprint": source_identity.model_fingerprint,
        "source_model_ref": source_identity.source_model_ref,
        "session_provenance_ref": session_ref,
        "acquisition_generation_ref": generation_ref,
    }
    epoch_id = _digest(ACQUISITION_EPOCH_PREFIX, epoch_payload)
    epoch = EvidenceEpoch(
        epoch_id=epoch_id,
        model_fingerprint=source_identity.model_fingerprint,
        origin=EvidenceEpochOrigin.LIVE_CAPTURE,
        source_fingerprint=source_identity.source_model_ref,
        provenance_refs=(
            source_identity.source_model_ref,
            session_ref,
            generation_ref,
        ),
    )

    context_payload = {
        "contract": ACQUISITION_CONTEXT_CONTRACT,
        "source_model_ref": source_identity.source_model_ref,
        "model_fingerprint": source_identity.model_fingerprint,
        "evidence_epoch_id": epoch.epoch_id,
        "session_provenance_ref": session_ref,
        "acquisition_generation_ref": generation_ref,
    }
    context_ref = _digest(ACQUISITION_CONTEXT_PREFIX, context_payload)

    return TrustedLiveAcquisitionContext(
        _token=_FACTORY_TOKEN,
        verified_session=verified_session,
        source_model_identity=source_identity,
        evidence_epoch=epoch,
        acquisition_generation_ref=generation_ref,
        session_provenance_ref=session_ref,
        acquisition_context_ref=context_ref,
    )


def build_component_f0_authorities_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
    snapshot: FeatureSnapshot,
    bindings: Sequence[F0EvidenceBinding],
):
    """Build existing factual F0 authorities from this context-owned EvidenceEpoch."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    return build_component_f0_authorities(
        epoch=context.evidence_epoch,
        snapshot=snapshot,
        bindings=bindings,
    )


def bind_column_topology_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
    topology: StrictColumnTopologyBundle,
    source_refs: Sequence[str],
) -> ColumnTopologyEvidenceEnvelope:
    """Bind canonical factual topology to this exact live acquisition context."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    refs = tuple(dict.fromkeys((
        context.acquisition_context_ref,
        context.session_provenance_ref,
        *context.evidence_epoch.provenance_refs,
        *source_refs,
    )))
    return ColumnTopologyEvidenceEnvelope.bind(
        topology=topology,
        epoch=context.evidence_epoch,
        source_refs=refs,
    )


def acquire_actual_concrete_design_combo_selection_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
) -> ActualConcreteDesignComboSelectionPopulation:
    """Run existing PASS-1 factual acquisition with context-owned identity."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    return acquire_actual_concrete_design_combo_selection_from_session(
        context.verified_session,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        session_provenance_ref=context.session_provenance_ref,
    )


def capture_etabs_combo_definitions_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
    names: Sequence[str],
) -> tuple[EtabsComboDefinitionEvidence, ...]:
    """Capture factual response-combo definitions through the verified session."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    return capture_etabs_combo_definitions_from_session(
        context.verified_session,
        names,
    )


def capture_concrete_column_design_sections_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
    topology: ColumnTopologyEvidenceEnvelope,
) -> ConcreteColumnDesignSectionPopulation:
    """Capture factual design sections only for topology owned by this context."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    context.require_model_epoch(
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
    )
    return capture_concrete_column_design_sections_from_session(
        context.verified_session,
        topology=topology,
    )


def capture_concrete_column_design_results_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
    topology: ColumnTopologyEvidenceEnvelope,
    design_sections: ConcreteColumnDesignSectionPopulation,
):
    """Capture factual column design results with context-owned provenance."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    context.require_model_epoch(
        model_fingerprint=topology.model_fingerprint,
        evidence_epoch_id=topology.evidence_epoch_id,
    )
    context.require_model_epoch(
        model_fingerprint=design_sections.model_fingerprint,
        evidence_epoch_id=design_sections.evidence_epoch_id,
    )
    return capture_concrete_column_design_results_from_session(
        context.verified_session,
        topology=topology,
        design_sections=design_sections,
        session_provenance_ref=context.session_provenance_ref,
    )


__all__ = [
    "ACQUISITION_CONTEXT_CONTRACT",
    "ACQUISITION_EPOCH_CONTRACT",
    "MODEL_FINGERPRINT_SEMANTICS",
    "SOURCE_MODEL_IDENTITY_SEMANTICS",
    "LiveAcquisitionContextError",
    "LiveAcquisitionContextMismatchError",
    "SourceModelIdentity",
    "TrustedLiveAcquisitionContext",
    "acquire_actual_concrete_design_combo_selection_from_context",
    "bind_column_topology_from_context",
    "build_component_f0_authorities_from_context",
    "capture_concrete_column_design_results_from_context",
    "capture_concrete_column_design_sections_from_context",
    "capture_etabs_combo_definitions_from_context",
    "create_trusted_live_acquisition_context",
]
