"""VS-2 live RC component compliance pack -> F0 regulatory execution.

Bounded composition only. Factual component FeatureSnapshots and the existing
M0 used-RC material population are mapped to existing formal CheckSpecs. No
engineering formula, ETABS acquisition, or serializer verdict lives here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.used_rc_material_population import (
    ConcreteStrengthFactStatus,
    MaterialPopulationReadiness,
    UsedMaterialDefinition,
    UsedRcMaterialPopulation,
)
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.findings import Finding, build_finding_from_check_result, build_finding_from_rule_closure
from tbdy_engine.integration.f0_evidence_adapter import (
    EvidenceBindingSource,
    F0EvidenceBinding,
    build_component_f0_authorities,
    build_f0_compile_inputs,
)
from tbdy_engine.integration.live_beam_geometry_f0 import live_epoch_id, validate_tbdy_7411_applies
from tbdy_engine.regulatory.b1_geometry_parity import (
    BEAM_DEPTH_KEY,
    BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    BEAM_MIN_DEPTH_CHECK_SPEC,
    BEAM_MIN_DEPTH_RULE_ID,
    COLUMN_DEPTH_KEY,
    COLUMN_MIN_DIMENSION_CHECK_SPEC,
    COLUMN_MIN_DIMENSION_RULE_ID,
    COLUMN_WIDTH_KEY,
    Beam7411ApplicabilityInput,
    ColumnMinDimensionApplicabilityInput,
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
from tbdy_engine.regulatory.concrete_material_min_strength import (
    CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,
    EVIDENCE_TRACE_KEY as MATERIAL_EVIDENCE_TRACE_KEY,
    FCK_KEY,
    RULE_ID as MATERIAL_RULE_ID,
    ConcreteMaterialMinStrengthApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import AvailabilityState, DependencySourceKind, Grain, PhysicalDimension, SemanticType
from tbdy_engine.regulatory.kernel import (
    AssessmentEngine,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM, UNIT_MPA

COMPONENT_TRACE_FEATURE = "component_geometry_trace"
LOCKED_RECTANGULAR_PROPERTY_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
MATERIAL_SOURCE_FINGERPRINT_PREFIX = "etabs:used-rc-material-source:sha256:"
MATERIAL_DOMAIN_BLOCK_REASON = "USED_RC_MATERIAL_POPULATION_NOT_COMPLETE"
WALL_NOT_EVALUATED_REASON = "LIVE_FACTUAL_WALL_GEOMETRY_SEAM_NOT_PROMOTED"

VS2_COMPONENT_REGISTRY = RegulatoryRegistry(
    checks=(BEAM_MIN_WIDTH_CHECK_SPEC, BEAM_MIN_DEPTH_CHECK_SPEC, BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC, COLUMN_MIN_DIMENSION_CHECK_SPEC)
)
VS2_RC_REGISTRY = RegulatoryRegistry(
    checks=(*VS2_COMPONENT_REGISTRY.checks, CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC)
)


class VS2RcComponentIntegrationError(RuntimeError):
    pass


class MissingLiveMaterialEvidenceError(VS2RcComponentIntegrationError):
    status = "BLOCKED_BY_MISSING_LIVE_MATERIAL_EVIDENCE"


class RealComponentPackConflictError(VS2RcComponentIntegrationError):
    status = "BLOCKED_BY_REAL_COMPONENT_PACK_CONFLICT"


@dataclass(frozen=True, slots=True)
class RcGeometryCaptureArtifact:
    path: Path
    raw_bytes: bytes
    snapshots: tuple[FeatureSnapshot, ...]
    beam_snapshots: tuple[FeatureSnapshot, ...]
    column_snapshots: tuple[FeatureSnapshot, ...]


@dataclass(frozen=True, slots=True)
class LiveRcComponentPackRun:
    geometry_epoch: EvidenceEpoch
    material_epoch: EvidenceEpoch
    snapshots: tuple[FeatureSnapshot, ...]
    material_population: UsedRcMaterialPopulation
    tbdy_7411_applies: bool | None
    registry: RegulatoryRegistry
    program: object
    store: object
    assessment: object
    authorities: tuple[ExternalDependencyAuthority, ...]
    check_findings: tuple[Finding, ...]
    closure_findings: tuple[Finding, ...]
    material_domain_supported: bool

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(sorted((*self.check_findings, *self.closure_findings), key=lambda item: item.finding_id))

    @property
    def beam_count(self) -> int:
        return sum(item.component_type.strip().casefold() == "beam" for item in self.snapshots)

    @property
    def column_count(self) -> int:
        return sum(item.component_type.strip().casefold() == "column" for item in self.snapshots)

    @property
    def used_concrete_material_count(self) -> int:
        return len(self.material_population.used_concrete_material_definitions)

    @property
    def structural_assessment_status(self) -> str:
        if not self.material_domain_supported:
            return StructuralAssessmentStatus.INCOMPLETE.value
        return self.assessment.structural_status.value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _evidence_from_payload(payload: object) -> FeatureEvidence:
    if not isinstance(payload, Mapping):
        raise VS2RcComponentIntegrationError("Feature evidence payload must be a mapping")
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


def _feature_from_payload(name: str, payload: object) -> FeatureValue:
    if not isinstance(payload, Mapping) or payload.get("feature_name") != name:
        raise VS2RcComponentIntegrationError("FeatureSnapshot feature key/name mismatch")
    raw_evidence = payload.get("evidence") or ()
    if not isinstance(raw_evidence, Sequence) or isinstance(raw_evidence, (str, bytes, bytearray)):
        raise VS2RcComponentIntegrationError("Feature evidence list is invalid")
    return FeatureValue(
        feature_name=name,
        value=payload.get("value"),
        unit=str(payload.get("unit") or ""),
        semantic_role=str(payload.get("semantic_role") or "UNKNOWN"),
        status=payload.get("status"),
        evidence=tuple(_evidence_from_payload(item) for item in raw_evidence),
    )


def _snapshot_from_payload(payload: object) -> FeatureSnapshot:
    if not isinstance(payload, Mapping):
        raise VS2RcComponentIntegrationError("FeatureSnapshot payload must be a mapping")
    identity, features = payload.get("identity") or {}, payload.get("features") or {}
    if not isinstance(identity, Mapping) or not isinstance(features, Mapping):
        raise VS2RcComponentIntegrationError("FeatureSnapshot artifact shape is invalid")
    return FeatureSnapshot(
        component_type=str(payload.get("component_type") or ""),
        component_id=str(payload.get("component_id") or ""),
        identity=dict(identity),
        features={str(name): _feature_from_payload(str(name), value) for name, value in features.items()},
    )


def load_rc_geometry_capture(feature_snapshot_path: Path) -> RcGeometryCaptureArtifact:
    path = Path(feature_snapshot_path)
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VS2RcComponentIntegrationError("FeatureSnapshot artifact is not valid UTF-8 JSON") from exc
    raw_snapshots = payload.get("snapshots") if isinstance(payload, Mapping) else None
    if not isinstance(raw_snapshots, Sequence) or isinstance(raw_snapshots, (str, bytes, bytearray)):
        raise VS2RcComponentIntegrationError("FeatureSnapshot artifact must contain snapshots")
    snapshots = tuple(sorted(
        (_snapshot_from_payload(item) for item in raw_snapshots if isinstance(item, Mapping) and str(item.get("component_type") or "").strip().casefold() in {"beam", "column"}),
        key=lambda item: (item.component_type.casefold(), item.component_id),
    ))
    if len({item.component_id for item in snapshots}) != len(snapshots):
        raise VS2RcComponentIntegrationError("Geometry capture contains duplicate component_id")
    beams = tuple(item for item in snapshots if item.component_type.strip().casefold() == "beam")
    columns = tuple(item for item in snapshots if item.component_type.strip().casefold() == "column")
    return RcGeometryCaptureArtifact(path=path, raw_bytes=raw_bytes, snapshots=snapshots, beam_snapshots=beams, column_snapshots=columns)


def material_source_fingerprint(source_bytes: bytes) -> str:
    if not isinstance(source_bytes, bytes):
        raise TypeError("source_bytes must be bytes")
    return MATERIAL_SOURCE_FINGERPRINT_PREFIX + hashlib.sha256(source_bytes).hexdigest()


def build_material_live_capture_epoch(*, model_fingerprint: str, source_bytes: bytes) -> EvidenceEpoch:
    if not isinstance(model_fingerprint, str) or not model_fingerprint.strip():
        raise VS2RcComponentIntegrationError("material epoch requires model_fingerprint")
    source_fingerprint = material_source_fingerprint(source_bytes)
    return EvidenceEpoch(
        epoch_id=live_epoch_id(model_fingerprint=model_fingerprint, source_fingerprint=source_fingerprint),
        model_fingerprint=model_fingerprint,
        origin=EvidenceEpochOrigin.LIVE_CAPTURE,
        source_fingerprint=source_fingerprint,
        provenance_refs=(model_fingerprint, source_fingerprint),
    )


def _trace_feature(snapshot: FeatureSnapshot) -> FeatureValue:
    evidence = tuple(item for name in sorted(snapshot.features) for item in snapshot.features[name].evidence)
    full = tuple(item for item in evidence if item.evidence_status is FeatureEvidenceStatus.FULL)
    if full:
        return FeatureValue(
            feature_name=COMPONENT_TRACE_FEATURE,
            value="LIVE_RC_COMPONENT_GEOMETRY_CAPTURE",
            semantic_role="TRACEABILITY",
            status=FeatureValueStatus.RESOLVED,
            evidence=full,
        )
    if evidence:
        return FeatureValue(
            feature_name=COMPONENT_TRACE_FEATURE,
            value="LIVE_RC_COMPONENT_GEOMETRY_CAPTURE",
            semantic_role="TRACEABILITY",
            status=FeatureValueStatus.PARTIAL,
            evidence=evidence,
        )
    return FeatureValue(
        feature_name=COMPONENT_TRACE_FEATURE,
        value=None,
        semantic_role="TRACEABILITY",
        status=FeatureValueStatus.MISSING,
    )


def prepare_component_snapshot(snapshot: FeatureSnapshot) -> FeatureSnapshot:
    features = dict(snapshot.features)
    if COMPONENT_TRACE_FEATURE in features:
        raise VS2RcComponentIntegrationError("capture already contains integration trace feature")
    features[COMPONENT_TRACE_FEATURE] = _trace_feature(snapshot)
    return FeatureSnapshot(
        component_type=snapshot.component_type,
        component_id=snapshot.component_id,
        identity=dict(snapshot.identity),
        features=features,
        diagnostics=snapshot.diagnostics,
    )


def _context_bindings() -> tuple[F0EvidenceBinding, ...]:
    return (
        F0EvidenceBinding(source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY, source_key="story", dependency_key=STORY_KEY, source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.COMPONENT_STORY, physical_dimension=PhysicalDimension.ENUM_STATE, grain=Grain.COMPONENT, unit=UNIT_ENUM_STATE),
        F0EvidenceBinding(source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY, source_key="section", dependency_key=SECTION_KEY, source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.COMPONENT_SECTION, physical_dimension=PhysicalDimension.ENUM_STATE, grain=Grain.COMPONENT, unit=UNIT_ENUM_STATE),
        F0EvidenceBinding(source_location=EvidenceBindingSource.EVIDENCE_TRACE, source_key=COMPONENT_TRACE_FEATURE, dependency_key=EVIDENCE_TRACE_KEY, source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.CHECK_EVIDENCE_TRACE, physical_dimension=PhysicalDimension.DIMENSIONLESS, grain=Grain.COMPONENT, unit=UNIT_DIMENSIONLESS),
    )


def component_bindings(component_type: str) -> tuple[F0EvidenceBinding, ...]:
    kind = str(component_type).strip().casefold()
    if kind == "beam":
        dims = (
            F0EvidenceBinding(source_location=EvidenceBindingSource.FEATURE_VALUE, source_key="beam_width_mm", dependency_key=BEAM_WIDTH_KEY, source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.BEAM_WIDTH, physical_dimension=PhysicalDimension.LENGTH, grain=Grain.COMPONENT, unit=UNIT_MM, expected_source_unit="mm"),
            F0EvidenceBinding(source_location=EvidenceBindingSource.FEATURE_VALUE, source_key="beam_depth_mm", dependency_key=BEAM_DEPTH_KEY, source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.BEAM_DEPTH, physical_dimension=PhysicalDimension.LENGTH, grain=Grain.COMPONENT, unit=UNIT_MM, expected_source_unit="mm"),
        )
    elif kind == "column":
        dims = (
            F0EvidenceBinding(source_location=EvidenceBindingSource.FEATURE_VALUE, source_key="column_width_mm", dependency_key=COLUMN_WIDTH_KEY, source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.COLUMN_WIDTH, physical_dimension=PhysicalDimension.LENGTH, grain=Grain.COMPONENT, unit=UNIT_MM, expected_source_unit="mm"),
            F0EvidenceBinding(source_location=EvidenceBindingSource.FEATURE_VALUE, source_key="column_depth_mm", dependency_key=COLUMN_DEPTH_KEY, source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.COLUMN_DEPTH, physical_dimension=PhysicalDimension.LENGTH, grain=Grain.COMPONENT, unit=UNIT_MM, expected_source_unit="mm"),
        )
    else:
        raise VS2RcComponentIntegrationError("VS-2 component must be beam or column")
    return (*dims, *_context_bindings())


def _rectangular_source_proven(snapshot: FeatureSnapshot) -> bool | None:
    if snapshot.component_type.strip().casefold() != "column":
        return None
    for name in ("column_width_mm", "column_depth_mm"):
        feature = snapshot.features.get(name)
        if not isinstance(feature, FeatureValue):
            continue
        for evidence in feature.evidence:
            if evidence.evidence_status is FeatureEvidenceStatus.FULL and (
                evidence.source_table == LOCKED_RECTANGULAR_PROPERTY_TABLE
                or evidence.actual_table_name == LOCKED_RECTANGULAR_PROPERTY_TABLE
            ):
                return True
    return None


def component_targets(snapshot: FeatureSnapshot, *, tbdy_7411_applies: bool | None) -> tuple[RuleScopeTarget, ...]:
    kind = snapshot.component_type.strip().casefold()
    common = {"grain": Grain.COMPONENT, "scope_ref": snapshot.component_id, "direction": None}
    if kind == "beam":
        context = validate_tbdy_7411_applies(tbdy_7411_applies)
        return (
            RuleScopeTarget(rule_id=BEAM_MIN_WIDTH_RULE_ID, applicability_input=BeamMinWidthApplicabilityInput(component_type="beam", tbdy_7411_applies=context), **common),
            RuleScopeTarget(rule_id=BEAM_MIN_DEPTH_RULE_ID, applicability_input=Beam7411ApplicabilityInput(is_beam=True, tbdy_7411_applies=context), **common),
            RuleScopeTarget(rule_id=BEAM_DEPTH_WIDTH_RATIO_RULE_ID, applicability_input=Beam7411ApplicabilityInput(is_beam=True, tbdy_7411_applies=context), **common),
        )
    if kind == "column":
        return (RuleScopeTarget(
            rule_id=COLUMN_MIN_DIMENSION_RULE_ID,
            applicability_input=ColumnMinDimensionApplicabilityInput(is_column=True, is_rectangular_section=_rectangular_source_proven(snapshot)),
            **common,
        ),)
    raise VS2RcComponentIntegrationError("VS-2 target component must be beam or column")


def _material_definition_payload(population: UsedRcMaterialPopulation, material: UsedMaterialDefinition) -> Mapping[str, object]:
    for item in population.as_dict()["used_material_definitions"]:
        if isinstance(item, Mapping) and item.get("material_id") == material.material_id:
            return item
    raise VS2RcComponentIntegrationError("material definition is missing from canonical M0 payload")


def _material_fact_ref(population: UsedRcMaterialPopulation, material: UsedMaterialDefinition) -> str:
    return "material-fact:sha256:" + hashlib.sha256(_canonical_json_bytes(_material_definition_payload(population, material))).hexdigest()


def _material_authority_id(*, epoch: EvidenceEpoch, material_id: str, dependency_key: str, factual_ref: str) -> str:
    digest = hashlib.sha256(_canonical_json_bytes({
        "epoch_id": epoch.epoch_id,
        "model_fingerprint": epoch.model_fingerprint,
        "source_fingerprint": epoch.source_fingerprint,
        "material_id": material_id,
        "dependency_key": dependency_key,
        "factual_ref": factual_ref,
    })).hexdigest()
    return f"vs2:material-authority:sha256:{digest}"


def material_authorities(*, epoch: EvidenceEpoch, population: UsedRcMaterialPopulation, material: UsedMaterialDefinition) -> tuple[ExternalDependencyAuthority, ...]:
    if population.readiness is not MaterialPopulationReadiness.COMPLETE:
        raise VS2RcComponentIntegrationError("material authorities require COMPLETE M0 population")
    if not material.is_concrete or material.concrete_strength_status is not ConcreteStrengthFactStatus.RESOLVED or material.canonical_fck_mpa is None:
        raise VS2RcComponentIntegrationError("material authority requires resolved factual concrete fck")
    factual_ref = _material_fact_ref(population, material)
    provenance = tuple(dict.fromkeys((f"epoch:{epoch.epoch_id}", epoch.model_fingerprint, f"source:{epoch.source_fingerprint}", f"material:{material.material_id}", factual_ref)))
    common = {
        "grain": Grain.MATERIAL_DEFINITION,
        "scope_ref": material.material_id,
        "direction": None,
        "population_completeness": PopulationCompleteness.FULL,
        "provenance_refs": provenance,
    }
    return (
        ExternalDependencyAuthority(
            authority_id=_material_authority_id(epoch=epoch, material_id=material.material_id, dependency_key=FCK_KEY.value, factual_ref=factual_ref),
            key=FCK_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.CONCRETE_FCK,
            physical_dimension=PhysicalDimension.STRESS,
            unit=UNIT_MPA,
            availability=AvailabilityState.RESOLVED,
            value=material.canonical_fck_mpa,
            **common,
        ),
        ExternalDependencyAuthority(
            authority_id=_material_authority_id(epoch=epoch, material_id=material.material_id, dependency_key=MATERIAL_EVIDENCE_TRACE_KEY.value, factual_ref=factual_ref),
            key=MATERIAL_EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            availability=AvailabilityState.RESOLVED,
            value=provenance,
            **common,
        ),
    )


def material_target(material: UsedMaterialDefinition) -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=MATERIAL_RULE_ID,
        grain=Grain.MATERIAL_DEFINITION,
        scope_ref=material.material_id,
        direction=None,
        applicability_input=ConcreteMaterialMinStrengthApplicabilityInput(is_concrete_material=True, used_in_scope_rc_building=True),
    )


def _finding_provenance(*, instance, geometry_epoch: EvidenceEpoch, material_epoch: EvidenceEpoch) -> tuple[str, ...]:
    epoch = material_epoch if instance.grain is Grain.MATERIAL_DEFINITION else geometry_epoch
    return tuple(item for item in (epoch.epoch_id, epoch.model_fingerprint, epoch.source_fingerprint) if item)


def run_live_rc_component_f0_pack(
    *,
    geometry_epoch: EvidenceEpoch,
    snapshots: Sequence[FeatureSnapshot],
    material_epoch: EvidenceEpoch,
    material_population: UsedRcMaterialPopulation,
    tbdy_7411_applies: bool | None,
) -> LiveRcComponentPackRun:
    context = validate_tbdy_7411_applies(tbdy_7411_applies)
    if geometry_epoch.origin is not EvidenceEpochOrigin.LIVE_CAPTURE or material_epoch.origin is not EvidenceEpochOrigin.LIVE_CAPTURE:
        raise VS2RcComponentIntegrationError("VS-2 capture epochs must be LIVE_CAPTURE")
    if geometry_epoch.model_fingerprint != material_epoch.model_fingerprint:
        raise RealComponentPackConflictError("geometry/material EvidenceEpoch model identities differ")
    if material_population.model_fingerprint != geometry_epoch.model_fingerprint:
        raise RealComponentPackConflictError("M0 population model identity differs from geometry epoch")

    prepared = tuple(sorted((prepare_component_snapshot(item) for item in snapshots), key=lambda item: (item.component_type.casefold(), item.component_id)))
    if any(item.component_type.strip().casefold() not in {"beam", "column"} for item in prepared):
        raise VS2RcComponentIntegrationError("VS-2 geometry population contains non beam/column snapshot")
    if len({item.component_id for item in prepared}) != len(prepared):
        raise VS2RcComponentIntegrationError("VS-2 geometry population contains duplicate component_id")

    component_external = tuple(authority for snapshot in prepared for authority in build_component_f0_authorities(
        epoch=geometry_epoch,
        snapshot=snapshot,
        bindings=component_bindings(snapshot.component_type),
    ))
    component_rule_targets = tuple(target for snapshot in prepared for target in component_targets(snapshot, tbdy_7411_applies=context))

    material_supported = material_population.readiness is MaterialPopulationReadiness.COMPLETE
    if material_supported:
        concrete = tuple(sorted(material_population.used_concrete_material_definitions, key=lambda item: item.material_id))
        material_targets = tuple(material_target(item) for item in concrete)
        material_external = tuple(authority for item in concrete for authority in material_authorities(epoch=material_epoch, population=material_population, material=item))
        registry = VS2_RC_REGISTRY
    else:
        material_targets = ()
        material_external = ()
        registry = VS2_COMPONENT_REGISTRY

    compile_inputs = build_f0_compile_inputs(
        rule_targets=(*component_rule_targets, *material_targets),
        external_authorities=(*component_external, *material_external),
    )
    program = RegulatoryCompiler.compile(registry, compile_inputs)
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)

    check_findings = tuple(finding for record in store.formal_results for finding in (
        build_finding_from_check_result(
            instance_id=record.instance_id,
            result=record.result,
            provenance_refs=_finding_provenance(instance=record.instance_id, geometry_epoch=geometry_epoch, material_epoch=material_epoch),
        ),
    ) if finding is not None)
    closure_records = {item.instance_id: item for item in program.plan.compiled_closure_inventory}
    closure_findings = tuple(finding for outcome in assessment.closure_outcomes for finding in (
        build_finding_from_rule_closure(
            compiled_record=closure_records[outcome.compiled_record_ref],
            outcome=outcome,
            provenance_refs=_finding_provenance(instance=outcome.compiled_record_ref, geometry_epoch=geometry_epoch, material_epoch=material_epoch),
        ),
    ) if finding is not None)

    return LiveRcComponentPackRun(
        geometry_epoch=geometry_epoch,
        material_epoch=material_epoch,
        snapshots=prepared,
        material_population=material_population,
        tbdy_7411_applies=context,
        registry=registry,
        program=program,
        store=store,
        assessment=assessment,
        authorities=tuple((*component_external, *material_external)),
        check_findings=tuple(sorted(check_findings, key=lambda item: item.finding_id)),
        closure_findings=tuple(sorted(closure_findings, key=lambda item: item.finding_id)),
        material_domain_supported=material_supported,
    )


__all__ = [
    "COMPONENT_TRACE_FEATURE",
    "LOCKED_RECTANGULAR_PROPERTY_TABLE",
    "MATERIAL_SOURCE_FINGERPRINT_PREFIX",
    "MATERIAL_DOMAIN_BLOCK_REASON",
    "WALL_NOT_EVALUATED_REASON",
    "VS2_COMPONENT_REGISTRY",
    "VS2_RC_REGISTRY",
    "VS2RcComponentIntegrationError",
    "MissingLiveMaterialEvidenceError",
    "RealComponentPackConflictError",
    "RcGeometryCaptureArtifact",
    "LiveRcComponentPackRun",
    "load_rc_geometry_capture",
    "material_source_fingerprint",
    "build_material_live_capture_epoch",
    "prepare_component_snapshot",
    "component_bindings",
    "component_targets",
    "material_authorities",
    "material_target",
    "run_live_rc_component_f0_pack",
]
