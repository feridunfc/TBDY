"""C13.4-P3 FeatureSnapshot to geometry CheckInput adapter.

This module prepares typed geometry check execution bundles only.  It does
not fetch source systems, select combinations, or evaluate engineering
verdicts.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from tbdy_engine.coverage.models import (
    CoverageEvidenceStatus,
    CoveragePolicyStatus,
    CoverageRow,
    CoverageStatus,
)
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

_GEOMETRY_ADAPTER_CHECK_ID = "geometry_check_input_adapter"
_REQUIRED_UNIT_MM = "mm"

_BEAM_GEOMETRY_CHECKS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "beam_geometry_min_width": ("beam_width_mm",),
        "beam_geometry_min_depth": ("beam_depth_mm",),
        "beam_depth_width_ratio": ("beam_depth_mm", "beam_width_mm"),
    }
)
_COLUMN_GEOMETRY_CHECKS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "column_geometry_min_dimension": ("column_width_mm", "column_depth_mm"),
        "column_geometry_min_width": ("column_width_mm",),
        "column_geometry_min_depth": ("column_depth_mm",),
    }
)
_CHECKS_BY_COMPONENT_TYPE: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "beam": _BEAM_GEOMETRY_CHECKS,
        "column": _COLUMN_GEOMETRY_CHECKS,
    }
)
_REQUIRED_UNITS: Mapping[str, str] = MappingProxyType(
    {
        "beam_width_mm": _REQUIRED_UNIT_MM,
        "beam_depth_mm": _REQUIRED_UNIT_MM,
        "column_width_mm": _REQUIRED_UNIT_MM,
        "column_depth_mm": _REQUIRED_UNIT_MM,
    }
)


@dataclass(frozen=True, slots=True)
class GeometryCheckInput:
    check_id: str
    component_id: str
    component_type: str
    story: str | None
    section: str | None
    required_features: tuple[str, ...]
    snapshot: FeatureSnapshot
    coverage: CoverageRow
    evidence_by_feature: Mapping[str, tuple[FeatureEvidence, ...]]

    def __post_init__(self) -> None:
        if not self.check_id or not self.component_id or not self.component_type:
            raise ValueError("GeometryCheckInput requires check_id, component_id, and component_type")
        if not isinstance(self.snapshot, FeatureSnapshot):
            raise TypeError("GeometryCheckInput.snapshot must be a FeatureSnapshot")
        if not isinstance(self.coverage, CoverageRow):
            raise TypeError("GeometryCheckInput.coverage must be a CoverageRow")
        object.__setattr__(self, "required_features", tuple(str(item) for item in self.required_features))
        object.__setattr__(
            self,
            "evidence_by_feature",
            MappingProxyType(
                {
                    str(feature_name): tuple(evidence)
                    for feature_name, evidence in self.evidence_by_feature.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class CheckInputBuildDiagnostic:
    check_id: str
    component_id: str | None
    component_type: str
    status: str
    reason: str
    missing_features: tuple[str, ...] = ()
    invalid_features: tuple[str, ...] = ()
    evidence_by_feature: Mapping[str, tuple[FeatureEvidence, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"READY", "NO_DATA", "BLOCKED", "OUT_OF_SCOPE"}:
            raise ValueError("Unsupported geometry input adapter diagnostic status")
        object.__setattr__(self, "missing_features", tuple(str(item) for item in self.missing_features))
        object.__setattr__(self, "invalid_features", tuple(str(item) for item in self.invalid_features))
        object.__setattr__(
            self,
            "evidence_by_feature",
            MappingProxyType(
                {
                    str(feature_name): tuple(evidence)
                    for feature_name, evidence in self.evidence_by_feature.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class CheckInputBuildResult:
    check_inputs: tuple[GeometryCheckInput, ...]
    diagnostics: tuple[CheckInputBuildDiagnostic, ...]

    def __post_init__(self) -> None:
        normalized_inputs = tuple(self.check_inputs)
        normalized_diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, GeometryCheckInput) for item in normalized_inputs):
            raise TypeError("CheckInputBuildResult.check_inputs must contain GeometryCheckInput objects")
        if any(not isinstance(item, CheckInputBuildDiagnostic) for item in normalized_diagnostics):
            raise TypeError("CheckInputBuildResult.diagnostics must contain CheckInputBuildDiagnostic objects")
        object.__setattr__(self, "check_inputs", normalized_inputs)
        object.__setattr__(self, "diagnostics", normalized_diagnostics)


@dataclass(frozen=True, slots=True)
class _NormalizedSnapshotInput:
    snapshot: FeatureSnapshot
    invalid_fixture_status_by_feature: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "invalid_fixture_status_by_feature",
            MappingProxyType(
                {
                    str(feature_name): str(status)
                    for feature_name, status in self.invalid_fixture_status_by_feature.items()
                }
            ),
        )



def normalize_geometry_feature_snapshot_input(
    snapshot: FeatureSnapshot | Mapping[str, object],
) -> FeatureSnapshot:
    """Normalize the fixture boundary without creating coverage."""
    return _normalize_snapshot_input(snapshot).snapshot

def build_geometry_check_inputs_from_feature_snapshot(
    snapshot: FeatureSnapshot | Mapping[str, object],
) -> CheckInputBuildResult:
    """Build typed geometry check inputs from a resolved feature snapshot.

    Mapping support is a fixture boundary only. Executable payloads are always
    GeometryCheckInput instances containing real FeatureSnapshot and CoverageRow
    objects.
    """
    normalized = _normalize_snapshot_input(snapshot)
    feature_snapshot = normalized.snapshot
    component_type = _normalize_component_type(feature_snapshot.component_type)
    component_checks = _CHECKS_BY_COMPONENT_TYPE.get(component_type)
    if component_checks is None:
        return CheckInputBuildResult(
            check_inputs=(),
            diagnostics=(
                CheckInputBuildDiagnostic(
                    check_id=_GEOMETRY_ADAPTER_CHECK_ID,
                    component_id=feature_snapshot.component_id,
                    component_type=feature_snapshot.component_type,
                    status="OUT_OF_SCOPE",
                    reason=f"No C13.4-P3 geometry adapter checks for component_type={feature_snapshot.component_type!r}",
                ),
            ),
        )

    check_inputs: list[GeometryCheckInput] = []
    diagnostics: list[CheckInputBuildDiagnostic] = []
    for check_id, required_features in component_checks.items():
        built = _build_single_geometry_check_input(
            check_id=check_id,
            required_features=required_features,
            snapshot=feature_snapshot,
            invalid_fixture_status_by_feature=normalized.invalid_fixture_status_by_feature,
        )
        if isinstance(built, GeometryCheckInput):
            check_inputs.append(built)
        else:
            diagnostics.append(built)
    return CheckInputBuildResult(check_inputs=tuple(check_inputs), diagnostics=tuple(diagnostics))



def build_geometry_check_inputs_from_feature_snapshot_and_coverage(
    snapshot: FeatureSnapshot,
    coverage_rows: Sequence[CoverageRow],
) -> CheckInputBuildResult:
    """Build geometry inputs only from externally assessed CoverageRow objects."""

    if not isinstance(snapshot, FeatureSnapshot):
        raise TypeError("snapshot must be a FeatureSnapshot")

    component_type = _normalize_component_type(snapshot.component_type)
    component_checks = _CHECKS_BY_COMPONENT_TYPE.get(component_type)
    if component_checks is None:
        return CheckInputBuildResult(
            check_inputs=(),
            diagnostics=(
                CheckInputBuildDiagnostic(
                    check_id=_GEOMETRY_ADAPTER_CHECK_ID,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="OUT_OF_SCOPE",
                    reason=(
                        "No geometry adapter checks for "
                        f"component_type={snapshot.component_type!r}"
                    ),
                ),
            ),
        )

    rows = tuple(coverage_rows)
    if any(not isinstance(row, CoverageRow) for row in rows):
        raise TypeError("coverage_rows must contain CoverageRow objects")

    check_ids = [row.check_id for row in rows]
    if len(check_ids) != len(set(check_ids)):
        raise ValueError(
            "coverage_rows must not contain duplicate check_id values"
        )

    if not rows:
        return CheckInputBuildResult(
            check_inputs=(),
            diagnostics=(
                CheckInputBuildDiagnostic(
                    check_id=_GEOMETRY_ADAPTER_CHECK_ID,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="NO_DATA",
                    reason="No authoritative coverage rows were supplied",
                ),
            ),
        )

    check_inputs: list[GeometryCheckInput] = []
    diagnostics: list[CheckInputBuildDiagnostic] = []

    for coverage in rows:
        expected_features = component_checks.get(coverage.check_id)
        if expected_features is None:
            diagnostics.append(
                CheckInputBuildDiagnostic(
                    check_id=coverage.check_id,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="OUT_OF_SCOPE",
                    reason=(
                        "Coverage row check_id is outside the geometry "
                        "adapter allowlist for this component type"
                    ),
                )
            )
            continue

        mismatch_reasons: list[str] = []
        if coverage.component_id != snapshot.component_id:
            mismatch_reasons.append(
                "coverage component_id does not match snapshot component_id"
            )
        if (
            _normalize_component_type(coverage.component_type)
            != component_type
        ):
            mismatch_reasons.append(
                "coverage component_type does not match snapshot component_type"
            )
        if tuple(coverage.required_features) != expected_features:
            mismatch_reasons.append(
                "coverage required_features do not match the canonical "
                "geometry adapter requirement"
            )

        if mismatch_reasons:
            diagnostics.append(
                CheckInputBuildDiagnostic(
                    check_id=coverage.check_id,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="BLOCKED",
                    reason="; ".join(mismatch_reasons),
                )
            )
            continue

        if coverage.coverage_status != CoverageStatus.RUNNABLE:
            diagnostics.append(
                CheckInputBuildDiagnostic(
                    check_id=coverage.check_id,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="BLOCKED",
                    reason=(
                        coverage.reason
                        or "Authoritative coverage row is not RUNNABLE"
                    ),
                )
            )
            continue

        if coverage.evidence_status != CoverageEvidenceStatus.FULL:
            diagnostics.append(
                CheckInputBuildDiagnostic(
                    check_id=coverage.check_id,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="BLOCKED",
                    reason=(
                        "Authoritative coverage evidence_status must be FULL"
                    ),
                )
            )
            continue

        policy_statuses = (
            coverage.combo_policy_status,
            coverage.section_state_status,
            coverage.ductility_context_status,
        )
        if CoveragePolicyStatus.MISSING in policy_statuses:
            diagnostics.append(
                CheckInputBuildDiagnostic(
                    check_id=coverage.check_id,
                    component_id=snapshot.component_id,
                    component_type=snapshot.component_type,
                    status="BLOCKED",
                    reason=(
                        "Authoritative coverage contains a missing policy "
                        "or design-context status"
                    ),
                )
            )
            continue

        built = _build_single_geometry_check_input(
            check_id=coverage.check_id,
            required_features=expected_features,
            snapshot=snapshot,
            invalid_fixture_status_by_feature={},
            coverage_override=coverage,
        )
        if isinstance(built, GeometryCheckInput):
            check_inputs.append(built)
        else:
            diagnostics.append(built)

    return CheckInputBuildResult(
        check_inputs=tuple(check_inputs),
        diagnostics=tuple(diagnostics),
    )


def geometry_check_ids_for_component_type(
    component_type: str,
) -> tuple[str, ...]:
    """Return canonical geometry check ids in adapter order."""
    checks = _CHECKS_BY_COMPONENT_TYPE.get(
        _normalize_component_type(component_type)
    )
    return () if checks is None else tuple(checks)

def _build_single_geometry_check_input(
    *,
    check_id: str,
    required_features: tuple[str, ...],
    snapshot: FeatureSnapshot,
    invalid_fixture_status_by_feature: Mapping[str, str],
    coverage_override: CoverageRow | None = None,
) -> GeometryCheckInput | CheckInputBuildDiagnostic:
    missing_features: list[str] = []
    invalid_features: list[str] = []
    reason_parts: list[str] = []
    evidence_by_feature: dict[str, tuple[FeatureEvidence, ...]] = {}

    for feature_name in required_features:
        if feature_name in invalid_fixture_status_by_feature:
            invalid_features.append(feature_name)
            status = invalid_fixture_status_by_feature[feature_name]
            reason_parts.append(f"{feature_name}: unsupported fixture status {status!r}")
            continue

        feature_value = snapshot.features.get(feature_name)
        if feature_value is None:
            missing_features.append(feature_name)
            reason_parts.append(f"{feature_name}: feature is absent")
            continue

        feature_evidence = _evidence_for_feature(snapshot, feature_value)
        if feature_value.status != FeatureValueStatus.RESOLVED:
            invalid_features.append(feature_name)
            evidence_by_feature[feature_name] = feature_evidence
            reason_parts.append(f"{feature_name}: feature status {feature_value.status.value!r} is not executable")
            continue

        required_unit = _REQUIRED_UNITS[feature_name]
        if feature_value.unit == "":
            invalid_features.append(feature_name)
            evidence_by_feature[feature_name] = feature_evidence
            reason_parts.append(f"{feature_name}: required unit metadata {required_unit!r} is missing")
            continue
        if feature_value.unit != required_unit:
            invalid_features.append(feature_name)
            evidence_by_feature[feature_name] = feature_evidence
            reason_parts.append(
                f"{feature_name}: unit {feature_value.unit!r} does not match required unit {required_unit!r}"
            )
            continue
        if not feature_evidence:
            invalid_features.append(feature_name)
            reason_parts.append(f"{feature_name}: evidence is missing")
            continue

        evidence_by_feature[feature_name] = feature_evidence

    if missing_features or invalid_features:
        diagnostic_status = "BLOCKED" if invalid_features else "NO_DATA"
        return CheckInputBuildDiagnostic(
            check_id=check_id,
            component_id=snapshot.component_id,
            component_type=snapshot.component_type,
            status=diagnostic_status,
            reason="; ".join(reason_parts),
            missing_features=tuple(missing_features),
            invalid_features=tuple(invalid_features),
            evidence_by_feature=evidence_by_feature,
        )

    return GeometryCheckInput(
        check_id=check_id,
        component_id=snapshot.component_id,
        component_type=snapshot.component_type,
        story=_optional_identity_text(snapshot, "story"),
        section=_optional_identity_text(snapshot, "section"),
        required_features=required_features,
        snapshot=snapshot,
        coverage=(
            coverage_override
            if coverage_override is not None
            else _build_runnable_coverage_row(
                check_id=check_id,
                component_type=snapshot.component_type,
                component_id=snapshot.component_id,
                required_features=required_features,
            )
        ),
        evidence_by_feature=evidence_by_feature,
    )


def _build_runnable_coverage_row(
    *,
    check_id: str,
    component_type: str,
    component_id: str,
    required_features: tuple[str, ...],
) -> CoverageRow:
    return CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id=component_id,
        required_features=required_features,
        resolved_features=required_features,
        missing_features=(),
        required_design_context=(),
        resolved_design_context=(),
        missing_design_context=(),
        combo_policy_status=CoveragePolicyStatus.NOT_APPLICABLE,
        section_state_status=CoveragePolicyStatus.NOT_APPLICABLE,
        ductility_context_status=CoveragePolicyStatus.NOT_APPLICABLE,
        evidence_status=CoverageEvidenceStatus.FULL,
        coverage_status=CoverageStatus.RUNNABLE,
    )


def _normalize_snapshot_input(snapshot: FeatureSnapshot | Mapping[str, object]) -> _NormalizedSnapshotInput:
    if isinstance(snapshot, FeatureSnapshot):
        return _NormalizedSnapshotInput(snapshot=snapshot)
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a FeatureSnapshot or mapping fixture")
    return _snapshot_from_mapping_fixture(snapshot)


def _snapshot_from_mapping_fixture(payload: Mapping[str, object]) -> _NormalizedSnapshotInput:
    component_type = _required_text(payload, "component_type")
    component_id = _required_text(payload, "component_id")
    identity = _optional_mapping(payload.get("identity"), field_name="identity") or {}
    raw_features = _optional_mapping(payload.get("features"), field_name="features") or {}
    raw_top_evidence = _optional_mapping(payload.get("evidence_by_feature"), field_name="evidence_by_feature") or {}

    features: dict[str, FeatureValue] = {}
    invalid_statuses: dict[str, str] = {}
    for raw_name, raw_feature in raw_features.items():
        feature_name = str(raw_name)
        if isinstance(raw_feature, FeatureValue):
            features[feature_name] = raw_feature
            continue
        if not isinstance(raw_feature, Mapping):
            raise TypeError("mapping fixture feature payloads must be FeatureValue objects or mappings")

        status_text = _fixture_status_text(raw_feature.get("status", FeatureValueStatus.RESOLVED.value))
        if status_text not in {item.value for item in FeatureValueStatus}:
            invalid_statuses[feature_name] = status_text
            continue

        feature_evidence = _fixture_feature_evidence(feature_name, raw_feature, raw_top_evidence)
        features[feature_name] = FeatureValue(
            feature_name=feature_name,
            value=raw_feature.get("value"),
            unit=_optional_text(raw_feature.get("unit")) or "",
            semantic_role=_optional_text(raw_feature.get("semantic_role")) or "UNKNOWN",
            status=FeatureValueStatus(status_text),
            evidence=feature_evidence,
        )

    return _NormalizedSnapshotInput(
        snapshot=FeatureSnapshot(
            component_type=component_type,
            component_id=component_id,
            identity=identity,
            features=features,
        ),
        invalid_fixture_status_by_feature=invalid_statuses,
    )


def _fixture_feature_evidence(
    feature_name: str,
    raw_feature: Mapping[str, object],
    raw_top_evidence: Mapping[object, object],
) -> tuple[FeatureEvidence, ...]:
    if "evidence" in raw_feature:
        return _coerce_evidence_sequence(raw_feature.get("evidence"))
    return _coerce_evidence_sequence(raw_top_evidence.get(feature_name))


def _coerce_evidence_sequence(raw_evidence: object) -> tuple[FeatureEvidence, ...]:
    if raw_evidence is None:
        return ()
    if isinstance(raw_evidence, FeatureEvidence):
        return (raw_evidence,)
    if isinstance(raw_evidence, Mapping):
        return (_evidence_from_mapping(raw_evidence),)
    if isinstance(raw_evidence, Sequence) and not isinstance(raw_evidence, (str, bytes, bytearray)):
        return tuple(_coerce_single_evidence(item) for item in raw_evidence)
    raise TypeError("fixture evidence must be FeatureEvidence, mapping, sequence, or None")


def _coerce_single_evidence(raw_evidence: object) -> FeatureEvidence:
    if isinstance(raw_evidence, FeatureEvidence):
        return raw_evidence
    if isinstance(raw_evidence, Mapping):
        return _evidence_from_mapping(raw_evidence)
    raise TypeError("fixture evidence sequence entries must be FeatureEvidence objects or mappings")


def _evidence_from_mapping(payload: Mapping[str, object]) -> FeatureEvidence:
    source_row = payload.get("source_row")
    if source_row is not None and not isinstance(source_row, Mapping):
        raise TypeError("FeatureEvidence.source_row fixture value must be a mapping when present")
    return FeatureEvidence(
        evidence_status=_optional_text(payload.get("evidence_status")) or "MISSING",
        source_table=_optional_text(payload.get("source_table")),
        actual_table_name=_optional_text(payload.get("actual_table_name")),
        source_column=_optional_text(payload.get("source_column")),
        source_row=source_row,
        output_case=_optional_text(payload.get("output_case")),
        combo_family=_optional_text(payload.get("combo_family")),
        governing_combo=_optional_text(payload.get("governing_combo")),
        section_state=_optional_text(payload.get("section_state")),
        ductility_class=_optional_text(payload.get("ductility_class")),
        raw_value=payload.get("raw_value"),
        normalized_value=payload.get("normalized_value"),
        unit=_optional_text(payload.get("unit")) or "",
        resolver=_optional_text(payload.get("resolver")) or "generic_table_resolver",
        reason=_optional_text(payload.get("reason")),
    )


def _evidence_for_feature(snapshot: FeatureSnapshot, feature_value: FeatureValue) -> tuple[FeatureEvidence, ...]:
    evidence = tuple(feature_value.evidence)
    if evidence:
        return evidence
    return tuple(snapshot.evidence_by_feature.get(feature_value.feature_name, ()))


def _normalize_component_type(component_type: str) -> str:
    return component_type.strip().casefold()


def _optional_identity_text(snapshot: FeatureSnapshot, field_name: str) -> str | None:
    value = snapshot.identity.get(field_name)
    return None if value is None else str(value)


def _required_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    text = _optional_text(value)
    if not text:
        raise ValueError(f"mapping fixture requires non-empty {field_name}")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _fixture_status_text(value: object) -> str:
    if isinstance(value, FeatureValueStatus):
        return value.value
    return str(value).strip().upper()


def _optional_mapping(value: object, *, field_name: str) -> Mapping[object, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"mapping fixture field {field_name!r} must be a mapping")
    return value


__all__ = [
    "CheckInputBuildDiagnostic",
    "CheckInputBuildResult",
    "GeometryCheckInput",
    "build_geometry_check_inputs_from_feature_snapshot",
    "build_geometry_check_inputs_from_feature_snapshot_and_coverage",
    "geometry_check_ids_for_component_type",
    "normalize_geometry_feature_snapshot_input",
]
