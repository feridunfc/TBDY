"""VS-1 live beam geometry -> F0 regulatory cutover.

This module is the bounded integration seam for one production slice:
existing live beam FeatureSnapshot evidence -> LIVE_CAPTURE EvidenceEpoch ->
existing F0 evidence adapter -> three existing beam geometry rules -> canonical
regulatory execution/assessment -> Findings.

It intentionally owns no engineering rules and performs no ETABS geometry
acquisition.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import ntpath
from pathlib import Path
from typing import Any

from tbdy_engine.features.diagnostics import FeatureDiagnostic
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.findings import (
    Finding,
    build_finding_from_check_result,
    build_finding_from_rule_closure,
)
from tbdy_engine.integration.f0_evidence_adapter import (
    EvidenceBindingSource,
    F0EvidenceBinding,
    build_component_f0_authorities,
    build_f0_compile_inputs,
)
from tbdy_engine.regulatory.b1_geometry_parity import (
    BEAM_DEPTH_KEY,
    BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    BEAM_MIN_DEPTH_CHECK_SPEC,
    BEAM_MIN_DEPTH_RULE_ID,
    Beam7411ApplicabilityInput,
)
from tbdy_engine.regulatory.beam_min_width import (
    BEAM_MIN_WIDTH_CHECK_SPEC,
    BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY,
    RULE_ID as BEAM_MIN_WIDTH_RULE_ID,
    SECTION_KEY,
    STORY_KEY,
    BeamMinWidthApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import (
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AssessmentEngine,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM

MODEL_IDENTITY_CONTRACT = "ETABS_MODEL_IDENTITY_V1"
LIVE_EPOCH_CONTRACT = "LIVE_EVIDENCE_EPOCH_V1"
MODEL_FINGERPRINT_PREFIX = "etabs:model-identity:sha256:"
SOURCE_FINGERPRINT_PREFIX = "etabs:live-geometry-source:sha256:"
EPOCH_ID_PREFIX = "epoch:live:sha256:"
MISSING_LIVE_EPOCH_IDENTITY_STATUS = "BLOCKED_BY_MISSING_LIVE_EPOCH_IDENTITY"
GEOMETRY_TRACE_FEATURE = "beam_geometry_trace"

VS1_BEAM_REGISTRY = RegulatoryRegistry(
    checks=(
        BEAM_MIN_WIDTH_CHECK_SPEC,
        BEAM_MIN_DEPTH_CHECK_SPEC,
        BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    )
)


class VS1LiveBeamIntegrationError(RuntimeError):
    """Bounded VS-1 integration failure."""


class MissingLiveEpochIdentityError(VS1LiveBeamIntegrationError):
    """Raised when the accepted ETABS API exposes no truthful model path."""

    status = MISSING_LIVE_EPOCH_IDENTITY_STATUS


@dataclass(frozen=True, slots=True)
class LiveBeamCaptureArtifact:
    path: Path
    raw_bytes: bytes
    beam_snapshots: tuple[FeatureSnapshot, ...]


@dataclass(frozen=True, slots=True)
class LiveBeamSliceRun:
    epoch: EvidenceEpoch
    snapshot: FeatureSnapshot
    bindings: tuple[F0EvidenceBinding, ...]
    authorities: tuple[object, ...]
    compile_inputs: object
    registry: RegulatoryRegistry
    program: object
    store: object
    assessment: object
    check_findings: tuple[Finding, ...]
    closure_findings: tuple[Finding, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(
            sorted(
                (*self.check_findings, *self.closure_findings),
                key=lambda item: item.finding_id,
            )
        )


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def normalize_observed_etabs_model_path(model_path: object) -> str:
    """Normalize only the factual ETABS model path approved for VS-1 identity."""
    if not isinstance(model_path, str) or not model_path.strip():
        raise MissingLiveEpochIdentityError(MISSING_LIVE_EPOCH_IDENTITY_STATUS)
    return ntpath.normcase(ntpath.normpath(model_path.strip()))


def model_fingerprint_from_path(model_path: object) -> str:
    normalized_path = normalize_observed_etabs_model_path(model_path)
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "contract": MODEL_IDENTITY_CONTRACT,
                "model_path": normalized_path,
            }
        )
    ).hexdigest()
    return f"{MODEL_FINGERPRINT_PREFIX}{digest}"


def source_fingerprint_from_bytes(source_bytes: bytes) -> str:
    if not isinstance(source_bytes, bytes):
        raise TypeError("source_bytes must be bytes")
    return f"{SOURCE_FINGERPRINT_PREFIX}{hashlib.sha256(source_bytes).hexdigest()}"


def source_fingerprint_from_path(feature_snapshot_path: Path) -> str:
    return source_fingerprint_from_bytes(Path(feature_snapshot_path).read_bytes())


def live_epoch_id(
    *,
    model_fingerprint: str,
    source_fingerprint: str,
) -> str:
    digest = hashlib.sha256(
        _canonical_json_bytes(
            {
                "contract": LIVE_EPOCH_CONTRACT,
                "origin": EvidenceEpochOrigin.LIVE_CAPTURE.value,
                "model_fingerprint": model_fingerprint,
                "source_fingerprint": source_fingerprint,
            }
        )
    ).hexdigest()
    return f"{EPOCH_ID_PREFIX}{digest}"


def build_live_capture_epoch(
    *,
    model_path: object,
    source_bytes: bytes,
) -> EvidenceEpoch:
    model_fingerprint = model_fingerprint_from_path(model_path)
    source_fingerprint = source_fingerprint_from_bytes(source_bytes)
    epoch_id = live_epoch_id(
        model_fingerprint=model_fingerprint,
        source_fingerprint=source_fingerprint,
    )
    return EvidenceEpoch(
        epoch_id=epoch_id,
        model_fingerprint=model_fingerprint,
        origin=EvidenceEpochOrigin.LIVE_CAPTURE,
        source_fingerprint=source_fingerprint,
        provenance_refs=(model_fingerprint, source_fingerprint),
    )


def read_observed_etabs_model_path(sap_model: object) -> str:
    """Read the existing ETABS model-path API without fallback identity values."""
    if sap_model is None:
        raise MissingLiveEpochIdentityError(MISSING_LIVE_EPOCH_IDENTITY_STATUS)
    getter = getattr(sap_model, "GetModelFilename", None)
    if not callable(getter):
        raise MissingLiveEpochIdentityError(MISSING_LIVE_EPOCH_IDENTITY_STATUS)
    try:
        raw = getter()
    except Exception as exc:
        raise MissingLiveEpochIdentityError(MISSING_LIVE_EPOCH_IDENTITY_STATUS) from exc

    if isinstance(raw, str):
        return normalize_observed_etabs_model_path(raw)

    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        observed_strings = tuple(
            item for item in raw if isinstance(item, str) and item.strip()
        )
        if len(observed_strings) == 1:
            return normalize_observed_etabs_model_path(observed_strings[0])

    raise MissingLiveEpochIdentityError(MISSING_LIVE_EPOCH_IDENTITY_STATUS)


def _diagnostic_from_payload(payload: object) -> FeatureDiagnostic:
    if not isinstance(payload, Mapping):
        raise VS1LiveBeamIntegrationError("Feature diagnostic payload must be a mapping")
    return FeatureDiagnostic(
        severity=payload.get("severity"),
        code=payload.get("code"),
        message=str(payload.get("message") or ""),
        details=payload.get("details") or {},
    )


def _evidence_from_payload(payload: object) -> FeatureEvidence:
    if not isinstance(payload, Mapping):
        raise VS1LiveBeamIntegrationError("Feature evidence payload must be a mapping")
    return FeatureEvidence(
        evidence_status=payload.get("evidence_status"),
        source_table=payload.get("source_table"),
        actual_table_name=payload.get("actual_table_name"),
        source_column=payload.get("source_column"),
        source_row=payload.get("source_row") or {},
        output_case=payload.get("output_case"),
        combo_family=payload.get("combo_family"),
        governing_combo=payload.get("governing_combo"),
        section_state=payload.get("section_state"),
        ductility_class=payload.get("ductility_class"),
        raw_value=payload.get("raw_value"),
        normalized_value=payload.get("normalized_value"),
        unit=str(payload.get("unit") or ""),
        resolver=str(payload.get("resolver") or "generic_table_resolver"),
        reason=payload.get("reason"),
    )


def _feature_from_payload(feature_name: str, payload: object) -> FeatureValue:
    if not isinstance(payload, Mapping):
        raise VS1LiveBeamIntegrationError("Feature value payload must be a mapping")
    payload_name = payload.get("feature_name")
    if payload_name != feature_name:
        raise VS1LiveBeamIntegrationError(
            "FeatureSnapshot artifact feature mapping key/name mismatch"
        )
    evidence_payload = payload.get("evidence") or ()
    diagnostic_payload = payload.get("diagnostics") or ()
    if not isinstance(evidence_payload, Sequence) or isinstance(
        evidence_payload, (str, bytes, bytearray)
    ):
        raise VS1LiveBeamIntegrationError("Feature evidence list is invalid")
    if not isinstance(diagnostic_payload, Sequence) or isinstance(
        diagnostic_payload, (str, bytes, bytearray)
    ):
        raise VS1LiveBeamIntegrationError("Feature diagnostic list is invalid")
    return FeatureValue(
        feature_name=feature_name,
        value=payload.get("value"),
        unit=str(payload.get("unit") or ""),
        semantic_role=str(payload.get("semantic_role") or "UNKNOWN"),
        status=payload.get("status"),
        evidence=tuple(_evidence_from_payload(item) for item in evidence_payload),
        diagnostics=tuple(_diagnostic_from_payload(item) for item in diagnostic_payload),
    )


def _snapshot_from_payload(payload: object) -> FeatureSnapshot:
    if not isinstance(payload, Mapping):
        raise VS1LiveBeamIntegrationError("FeatureSnapshot payload must be a mapping")
    features_payload = payload.get("features") or {}
    diagnostics_payload = payload.get("diagnostics") or ()
    identity = payload.get("identity") or {}
    if not isinstance(features_payload, Mapping):
        raise VS1LiveBeamIntegrationError("FeatureSnapshot.features must be a mapping")
    if not isinstance(identity, Mapping):
        raise VS1LiveBeamIntegrationError("FeatureSnapshot.identity must be a mapping")
    if not isinstance(diagnostics_payload, Sequence) or isinstance(
        diagnostics_payload, (str, bytes, bytearray)
    ):
        raise VS1LiveBeamIntegrationError("FeatureSnapshot diagnostics must be a sequence")
    features = {
        str(name): _feature_from_payload(str(name), value)
        for name, value in features_payload.items()
    }
    return FeatureSnapshot(
        component_type=str(payload.get("component_type") or ""),
        component_id=str(payload.get("component_id") or ""),
        identity=dict(identity),
        features=features,
        diagnostics=tuple(_diagnostic_from_payload(item) for item in diagnostics_payload),
    )


def load_live_beam_capture_artifact(
    feature_snapshot_path: Path,
) -> LiveBeamCaptureArtifact:
    path = Path(feature_snapshot_path)
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VS1LiveBeamIntegrationError(
            "FeatureSnapshot artifact is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise VS1LiveBeamIntegrationError("FeatureSnapshot artifact root must be a mapping")
    snapshots_payload = payload.get("snapshots")
    if not isinstance(snapshots_payload, Sequence) or isinstance(
        snapshots_payload, (str, bytes, bytearray)
    ):
        raise VS1LiveBeamIntegrationError(
            "FeatureSnapshot artifact must contain a snapshots sequence"
        )
    snapshots = tuple(_snapshot_from_payload(item) for item in snapshots_payload)
    beams = tuple(
        sorted(
            (
                snapshot
                for snapshot in snapshots
                if snapshot.component_type.strip().casefold() == "beam"
            ),
            key=lambda item: (
                item.component_id,
                str(item.identity.get("story") or ""),
                str(item.identity.get("section") or ""),
            ),
        )
    )
    return LiveBeamCaptureArtifact(path=path, raw_bytes=raw_bytes, beam_snapshots=beams)


def _trace_feature(snapshot: FeatureSnapshot) -> FeatureValue:
    evidence: list[FeatureEvidence] = []
    for feature_name in ("beam_width_mm", "beam_depth_mm"):
        feature = snapshot.features.get(feature_name)
        if isinstance(feature, FeatureValue):
            evidence.extend(feature.evidence)

    full = tuple(
        item for item in evidence if item.evidence_status is FeatureEvidenceStatus.FULL
    )
    if full:
        return FeatureValue(
            feature_name=GEOMETRY_TRACE_FEATURE,
            value="LIVE_BEAM_GEOMETRY_CAPTURE",
            unit="",
            semantic_role="TRACEABILITY",
            status=FeatureValueStatus.RESOLVED,
            evidence=full,
        )
    if evidence:
        return FeatureValue(
            feature_name=GEOMETRY_TRACE_FEATURE,
            value="LIVE_BEAM_GEOMETRY_CAPTURE",
            unit="",
            semantic_role="TRACEABILITY",
            status=FeatureValueStatus.PARTIAL,
            evidence=tuple(evidence),
        )
    return FeatureValue(
        feature_name=GEOMETRY_TRACE_FEATURE,
        value=None,
        unit="",
        semantic_role="TRACEABILITY",
        status=FeatureValueStatus.MISSING,
    )


def prepare_live_beam_snapshot(snapshot: FeatureSnapshot) -> FeatureSnapshot:
    if not isinstance(snapshot, FeatureSnapshot):
        raise TypeError("snapshot must be FeatureSnapshot")
    if snapshot.component_type.strip().casefold() != "beam":
        raise VS1LiveBeamIntegrationError("VS-1 production slice accepts beam snapshots only")
    features = dict(snapshot.features)
    if GEOMETRY_TRACE_FEATURE in features:
        raise VS1LiveBeamIntegrationError(
            "live beam capture unexpectedly already contains integration trace feature"
        )
    features[GEOMETRY_TRACE_FEATURE] = _trace_feature(snapshot)
    return FeatureSnapshot(
        component_type=snapshot.component_type,
        component_id=snapshot.component_id,
        identity=dict(snapshot.identity),
        features=features,
        diagnostics=snapshot.diagnostics,
    )


def vs1_beam_bindings() -> tuple[F0EvidenceBinding, ...]:
    return (
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_width_mm",
            dependency_key=BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_depth_mm",
            dependency_key=BEAM_DEPTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_DEPTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
            source_key="story",
            dependency_key=STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            unit=UNIT_ENUM_STATE,
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
            source_key="section",
            dependency_key=SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            unit=UNIT_ENUM_STATE,
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.EVIDENCE_TRACE,
            source_key=GEOMETRY_TRACE_FEATURE,
            dependency_key=EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            unit=UNIT_DIMENSIONLESS,
        ),
    )


def vs1_beam_targets(snapshot: FeatureSnapshot) -> tuple[RuleScopeTarget, ...]:
    scope_ref = snapshot.component_id
    return (
        RuleScopeTarget(
            rule_id=BEAM_MIN_WIDTH_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=scope_ref,
            direction=None,
            applicability_input=BeamMinWidthApplicabilityInput(
                component_type="beam",
                tbdy_7411_applies=True,
            ),
        ),
        RuleScopeTarget(
            rule_id=BEAM_MIN_DEPTH_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=scope_ref,
            direction=None,
            applicability_input=Beam7411ApplicabilityInput(
                is_beam=True,
                tbdy_7411_applies=True,
            ),
        ),
        RuleScopeTarget(
            rule_id=BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=scope_ref,
            direction=None,
            applicability_input=Beam7411ApplicabilityInput(
                is_beam=True,
                tbdy_7411_applies=True,
            ),
        ),
    )


def run_live_beam_f0_slice(
    *,
    epoch: EvidenceEpoch,
    snapshot: FeatureSnapshot,
) -> LiveBeamSliceRun:
    if not isinstance(epoch, EvidenceEpoch):
        raise TypeError("epoch must be EvidenceEpoch")
    if epoch.origin is not EvidenceEpochOrigin.LIVE_CAPTURE:
        raise VS1LiveBeamIntegrationError("VS-1 production slice requires LIVE_CAPTURE epoch")

    prepared = prepare_live_beam_snapshot(snapshot)
    bindings = vs1_beam_bindings()
    authorities = build_component_f0_authorities(
        epoch=epoch,
        snapshot=prepared,
        bindings=bindings,
    )
    compile_inputs = build_f0_compile_inputs(
        rule_targets=vs1_beam_targets(prepared),
        external_authorities=authorities,
    )
    program = RegulatoryCompiler.compile(VS1_BEAM_REGISTRY, compile_inputs)
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)

    provenance_refs = (
        f"epoch:{epoch.epoch_id}",
        epoch.model_fingerprint,
        epoch.source_fingerprint or "",
    )
    provenance_refs = tuple(item for item in provenance_refs if item)

    check_findings: list[Finding] = []
    for record in store.formal_results:
        finding = build_finding_from_check_result(
            instance_id=record.instance_id,
            result=record.result,
            provenance_refs=provenance_refs,
        )
        if finding is not None:
            check_findings.append(finding)

    closure_records = {
        item.instance_id: item for item in program.plan.compiled_closure_inventory
    }
    closure_findings: list[Finding] = []
    for outcome in assessment.closure_outcomes:
        finding = build_finding_from_rule_closure(
            compiled_record=closure_records[outcome.compiled_record_ref],
            outcome=outcome,
            provenance_refs=provenance_refs,
        )
        if finding is not None:
            closure_findings.append(finding)

    return LiveBeamSliceRun(
        epoch=epoch,
        snapshot=prepared,
        bindings=bindings,
        authorities=authorities,
        compile_inputs=compile_inputs,
        registry=VS1_BEAM_REGISTRY,
        program=program,
        store=store,
        assessment=assessment,
        check_findings=tuple(
            sorted(check_findings, key=lambda item: item.finding_id)
        ),
        closure_findings=tuple(
            sorted(closure_findings, key=lambda item: item.finding_id)
        ),
    )


__all__ = [
    "MODEL_IDENTITY_CONTRACT",
    "LIVE_EPOCH_CONTRACT",
    "MODEL_FINGERPRINT_PREFIX",
    "SOURCE_FINGERPRINT_PREFIX",
    "EPOCH_ID_PREFIX",
    "MISSING_LIVE_EPOCH_IDENTITY_STATUS",
    "GEOMETRY_TRACE_FEATURE",
    "VS1_BEAM_REGISTRY",
    "VS1LiveBeamIntegrationError",
    "MissingLiveEpochIdentityError",
    "LiveBeamCaptureArtifact",
    "LiveBeamSliceRun",
    "normalize_observed_etabs_model_path",
    "model_fingerprint_from_path",
    "source_fingerprint_from_bytes",
    "source_fingerprint_from_path",
    "live_epoch_id",
    "build_live_capture_epoch",
    "read_observed_etabs_model_path",
    "load_live_beam_capture_artifact",
    "prepare_live_beam_snapshot",
    "vs1_beam_bindings",
    "vs1_beam_targets",
    "run_live_beam_f0_slice",
]
