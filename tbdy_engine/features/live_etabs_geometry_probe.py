"""C13.5 live read-only geometry FeatureSnapshot probe."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import json
import re

from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STRATEGIES,
    EtabsAttachFailure,
    EtabsAttachResult,
    attach_to_running_etabs,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

_PROBE_SCOPE = "C13_5_LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE"
_ATTACH_FAILURE_SCOPE = "LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE"
_RUNNER = "C13.5 Live ETABS Read-Only Geometry FeatureSnapshot Probe"
_ATTACH_FAILURE_RUNNER = "C13.5-P3 ETABS COM Attach Compatibility Boundary"
_OUTPUT_FILES = (
    "feature_snapshot.json",
    "live_geometry_probe_summary.json",
    "live_geometry_probe_diagnostics.json",
    "live_geometry_probe_manifest.json",
)
_ATTACH_FAILURE_OUTPUT_FILES = (
    "live_geometry_probe_summary.json",
    "live_geometry_probe_diagnostics.json",
    "live_geometry_probe_manifest.json",
)
_ALLOWED_PROBE_STATUSES = frozenset({"OK", "PARTIAL", "FAIL"})
_ALLOWED_DIAGNOSTIC_STATUSES = frozenset({"NO_DATA", "BLOCKED", "WARNING"})
_ALLOWED_TABLE_READ_STATUSES = frozenset({"FETCHED", "EMPTY", "FAILED", "PARSE_EMPTY"})
_ALLOWED_COMPONENT_SOURCE_STATUSES = frozenset({"FETCHED", "EMPTY", "FAILED", "PARSE_EMPTY", "MISSING"})
_REQUIRED_UNIT = "mm"
_DEFAULT_MAX_ROWS = 20
_LOCKED_COMPONENT_TYPE_SOURCE_TABLE = "Frame Assignments - Summary"
_LOCKED_ASSIGNMENT_SOURCE_TABLE = "Frame Assignments - Section Properties"
_LOCKED_PROPERTY_SOURCE_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
_FEATURES_BY_COMPONENT_TYPE: Mapping[str, tuple[str, str]] = {
    "beam": ("beam_width_mm", "beam_depth_mm"),
    "column": ("column_width_mm", "column_depth_mm"),
}
_WIDTH_KEYS = ("width_mm", "beam_width_mm", "column_width_mm")
_DEPTH_KEYS = ("depth_mm", "beam_depth_mm", "column_depth_mm")
_IDENTITY_KEYS = ("label", "story", "section", "unique_name", "section_name")
_COMPONENT_TYPE_COLUMN_CANDIDATES = (
    "Type",
    "Design Type",
    "DesignType",
    "ComponentType",
    "component_type",
    "ObjectType",
    "FrameType",
    "MemberType",
    "ElementType",
    "LineObjectType",
    "Classification",
)
_COMPONENT_TYPE_JOIN_KEY_CANDIDATES = (
    "UniqueName",
    "unique_name",
    "ObjectUniqueName",
    "LineUniqueName",
    "FrameUniqueName",
    "ObjectID",
    "LineObjectID",
)
_COMPONENT_TYPE_VALUES = {"beam": "beam", "column": "column"}
FORCE_UNITS = {1: "lb", 2: "kip", 3: "N", 4: "kN", 5: "kgf", 6: "tonf"}
LENGTH_UNITS = {1: "in", 2: "ft", 3: "um", 4: "mm", 5: "cm", 6: "m"}
TEMP_UNITS = {1: "F", 2: "C"}
LENGTH_TO_MM_FACTOR = {"um": 0.001, "mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
_NUMERIC_LITERAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


@dataclass(frozen=True, slots=True)
class AcceptedGeometryMapping:
    assignment_table_key: str
    assignment_section_column: str
    property_table_key: str
    property_name_column: str
    width_column: str
    depth_column: str
    mapping_basis: str

    def __post_init__(self) -> None:
        for field_name in (
            "assignment_table_key",
            "assignment_section_column",
            "property_table_key",
            "property_name_column",
            "width_column",
            "depth_column",
            "mapping_basis",
        ):
            raw = getattr(self, field_name)
            if raw is None or not str(raw).strip():
                raise ValueError(f"AcceptedGeometryMapping.{field_name} is required")
        if self.mapping_basis != "explicit_columns_only":
            raise ValueError("AcceptedGeometryMapping.mapping_basis must be explicit_columns_only")

    def as_dict(self) -> dict[str, object]:
        return {
            "assignment_section_column": self.assignment_section_column,
            "assignment_table_key": self.assignment_table_key,
            "depth_column": self.depth_column,
            "mapping_basis": self.mapping_basis,
            "property_name_column": self.property_name_column,
            "property_table_key": self.property_table_key,
            "width_column": self.width_column,
        }


DEFAULT_ACCEPTED_GEOMETRY_MAPPING = AcceptedGeometryMapping(
    assignment_table_key=_LOCKED_ASSIGNMENT_SOURCE_TABLE,
    assignment_section_column="SectProp",
    property_table_key=_LOCKED_PROPERTY_SOURCE_TABLE,
    property_name_column="Name",
    width_column="t2",
    depth_column="t3",
    mapping_basis="explicit_columns_only",
)


@dataclass(frozen=True, slots=True)
class LiveGeometryProbeDiagnostic:
    status: str
    code: str
    message: str
    component_id: str | None = None
    component_type: str | None = None
    feature_id: str | None = None
    source_table: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_DIAGNOSTIC_STATUSES:
            raise ValueError("Unsupported live geometry probe diagnostic status")
        if not self.code or not self.message:
            raise ValueError("LiveGeometryProbeDiagnostic requires code and message")

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "component_id": self.component_id,
            "component_type": self.component_type,
            "feature_id": self.feature_id,
            "message": self.message,
            "source_table": self.source_table,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class LiveEtabsLengthUnitEvidence:
    present_force_unit: str
    present_length_unit: str
    present_temperature_unit: str
    database_force_unit: str
    database_length_unit: str
    database_temperature_unit: str
    present_units_raw: tuple[object, ...]
    database_units_raw: tuple[object, ...]
    normalization_basis: str = "ETABS_GetPresentUnits_2"

    def as_dict(self) -> dict[str, object]:
        return {
            "database_force_unit": self.database_force_unit,
            "database_length_unit": self.database_length_unit,
            "database_temperature_unit": self.database_temperature_unit,
            "database_units_raw": list(self.database_units_raw),
            "normalization_basis": self.normalization_basis,
            "present_force_unit": self.present_force_unit,
            "present_length_unit": self.present_length_unit,
            "present_temperature_unit": self.present_temperature_unit,
            "present_units_raw": list(self.present_units_raw),
        }


@dataclass(frozen=True, slots=True)
class LiveFrameComponentTypeEvidence:
    unique_name: str
    component_type: str
    source_table: str
    source_column: str
    raw_row: Mapping[str, object]
    join_key_column: str = "UniqueName"

    def __post_init__(self) -> None:
        normalized = _normalize_component_type(self.component_type)
        if not _text(self.unique_name):
            raise ValueError("LiveFrameComponentTypeEvidence.unique_name is required")
        if normalized not in _FEATURES_BY_COMPONENT_TYPE:
            raise ValueError("LiveFrameComponentTypeEvidence.component_type must be beam or column")
        object.__setattr__(self, "unique_name", _text(self.unique_name))
        object.__setattr__(self, "component_type", normalized)
        object.__setattr__(self, "source_table", _text(self.source_table))
        object.__setattr__(self, "source_column", _text(self.source_column))
        object.__setattr__(self, "join_key_column", _text(self.join_key_column))
        object.__setattr__(self, "raw_row", dict(self.raw_row))

    def as_dict(self) -> dict[str, object]:
        return {
            "component_type": self.component_type,
            "join_key_column": self.join_key_column,
            "raw_row": dict(self.raw_row),
            "source_column": self.source_column,
            "source_table": self.source_table,
            "unique_name": self.unique_name,
        }


@dataclass(frozen=True, slots=True)
class LiveFrameComponentTypeSourceResult:
    status: str
    source_table: str | None
    source_column: str | None
    join_key_column: str | None
    row_count: int
    evidence_by_unique_name: Mapping[str, LiveFrameComponentTypeEvidence]
    diagnostics: tuple[LiveGeometryProbeDiagnostic, ...]

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_COMPONENT_SOURCE_STATUSES:
            raise ValueError("Unsupported component type source status")
        if self.row_count < 0:
            raise ValueError("LiveFrameComponentTypeSourceResult.row_count cannot be negative")
        object.__setattr__(self, "evidence_by_unique_name", dict(self.evidence_by_unique_name))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class LiveGeometryAssignmentRow:
    story: str
    label: str
    unique_name: str
    section_name: str
    source_table: str
    component_type: str
    raw_row: Mapping[str, object]
    component_type_source_table: str | None = None
    component_type_source_column: str | None = None
    component_type_source_row: Mapping[str, object] | None = None
    component_type_join_key_column: str | None = None

    def __post_init__(self) -> None:
        if not self.story or not self.label or not self.unique_name or not self.section_name:
            raise ValueError("LiveGeometryAssignmentRow requires story, label, unique_name, and section_name")
        if self.component_type not in _FEATURES_BY_COMPONENT_TYPE:
            raise ValueError("LiveGeometryAssignmentRow.component_type must be beam or column")
        object.__setattr__(self, "raw_row", dict(self.raw_row))
        object.__setattr__(self, "component_type_source_row", dict(self.component_type_source_row or {}))


@dataclass(frozen=True, slots=True)
class NormalizedGeometryDimension:
    raw_value: object
    raw_value_type: str
    parsed_value: float
    source_unit: str
    target_unit: str
    normalization_factor_to_mm: float
    normalized_value: float
    normalized_unit: str
    normalization_basis: str
    unit_evidence: LiveEtabsLengthUnitEvidence | None

    def evidence_details(self) -> dict[str, object]:
        details = {
            "database_units_raw": [],
            "normalization_basis": self.normalization_basis,
            "normalization_factor_to_mm": self.normalization_factor_to_mm,
            "normalized_unit": self.normalized_unit,
            "normalized_value": self.normalized_value,
            "parsed_value": self.parsed_value,
            "present_units_raw": [],
            "raw_value": self.raw_value,
            "raw_value_type": self.raw_value_type,
            "source_unit": self.source_unit,
            "target_unit": self.target_unit,
        }
        if self.unit_evidence is not None:
            details.update(self.unit_evidence.as_dict())
        return details


@dataclass(frozen=True, slots=True)
class LiveGeometryPropertyRow:
    section_name: str
    width: NormalizedGeometryDimension
    depth: NormalizedGeometryDimension
    source_table: str
    raw_row: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.section_name:
            raise ValueError("LiveGeometryPropertyRow.section_name is required")
        object.__setattr__(self, "raw_row", dict(self.raw_row))


@dataclass(frozen=True, slots=True)
class LiveGeometryResolvedRow:
    story: str
    label: str
    unique_name: str
    section_name: str
    width: NormalizedGeometryDimension
    depth: NormalizedGeometryDimension
    assignment_table: str
    property_table: str
    component_type: str
    component_type_source_table: str | None
    component_type_source_column: str | None
    component_type_source_row: Mapping[str, object]
    component_type_join_key_column: str | None

    def as_feature_row(self, *, mapping: AcceptedGeometryMapping, assignment_row: Mapping[str, object], property_row: Mapping[str, object]) -> dict[str, object]:
        return {
            "actual_table_name": self.property_table,
            "assignment_section_column": mapping.assignment_section_column,
            "assignment_source_row": dict(assignment_row),
            "component_id": self.unique_name,
            "component_type": self.component_type,
            "component_type_join_key": self.unique_name,
            "component_type_join_key_column": self.component_type_join_key_column,
            "component_type_source_column": self.component_type_source_column,
            "component_type_source_row": dict(self.component_type_source_row),
            "component_type_source_table": self.component_type_source_table,
            "depth_column": mapping.depth_column,
            "depth_mm": self.depth.normalized_value,
            "depth_mm_source_column": mapping.depth_column,
            "depth_mm_unit": self.depth.normalized_unit,
            "depth_normalization": self.depth.evidence_details(),
            "label": self.label,
            "mapping_basis": mapping.mapping_basis,
            "property_name_column": mapping.property_name_column,
            "property_source_row": dict(property_row),
            "section": self.section_name,
            "section_name": self.section_name,
            "source_table": self.property_table,
            "source_table_assignment": self.assignment_table,
            "source_table_property": self.property_table,
            "story": self.story,
            "unique_name": self.unique_name,
            "unit": _REQUIRED_UNIT,
            "width_column": mapping.width_column,
            "width_mm": self.width.normalized_value,
            "width_mm_source_column": mapping.width_column,
            "width_mm_unit": self.width.normalized_unit,
            "width_normalization": self.width.evidence_details(),
        }


@dataclass(frozen=True, slots=True)
class LiveEtabsTableReadResult:
    table_key: str
    status: str
    columns: tuple[str, ...]
    row_count: int
    rows: tuple[Mapping[str, object], ...]
    raw_metadata: Mapping[str, object]
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.table_key:
            raise ValueError("LiveEtabsTableReadResult.table_key is required")
        if self.status not in _ALLOWED_TABLE_READ_STATUSES:
            raise ValueError("Unsupported live ETABS table read status")
        if self.row_count < 0:
            raise ValueError("LiveEtabsTableReadResult.row_count cannot be negative")
        object.__setattr__(self, "columns", tuple(str(column) for column in self.columns))
        object.__setattr__(self, "rows", tuple(dict(row) for row in self.rows))
        object.__setattr__(self, "raw_metadata", dict(self.raw_metadata))


class GeometryRowProvider(Protocol):
    def iter_geometry_rows(self) -> Sequence[Mapping[str, object]]:
        """Return observed geometry rows without mutating the source model."""


@dataclass(frozen=True, slots=True)
class LiveGeometryProbeResult:
    status: str
    output_dir: Path
    feature_snapshot_path: Path
    summary_path: Path
    diagnostics_path: Path
    manifest_path: Path
    snapshot_count: int
    diagnostic_count: int

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_PROBE_STATUSES:
            raise ValueError("Unsupported live geometry probe result status")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "feature_snapshot_path", Path(self.feature_snapshot_path))
        object.__setattr__(self, "summary_path", Path(self.summary_path))
        object.__setattr__(self, "diagnostics_path", Path(self.diagnostics_path))
        object.__setattr__(self, "manifest_path", Path(self.manifest_path))


@dataclass(frozen=True, slots=True)
class MappingGeometryRowProvider:
    rows: tuple[Mapping[str, object], ...]

    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        object.__setattr__(self, "rows", tuple(dict(row) for row in rows))

    def iter_geometry_rows(self) -> Sequence[Mapping[str, object]]:
        return self.rows


@dataclass(frozen=True, slots=True)
class AcceptedMappingGeometryRowProvider:
    assignment_rows: tuple[Mapping[str, object], ...]
    property_rows: tuple[Mapping[str, object], ...]
    component_type_rows: tuple[Mapping[str, object], ...] | None
    component_type_source_table: str | None
    component_type_source_column: str | None
    component_type_join_key_column: str | None
    length_unit_evidence: LiveEtabsLengthUnitEvidence | None
    require_length_unit_evidence: bool
    mapping: AcceptedGeometryMapping | None

    def __init__(
        self,
        *,
        assignment_rows: Sequence[Mapping[str, object]],
        property_rows: Sequence[Mapping[str, object]],
        component_type_rows: Sequence[Mapping[str, object]] | None = None,
        component_type_source_table: str | None = None,
        component_type_source_column: str | None = None,
        component_type_join_key_column: str | None = None,
        length_unit_evidence: LiveEtabsLengthUnitEvidence | None = None,
        require_length_unit_evidence: bool = False,
        mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    ) -> None:
        object.__setattr__(self, "assignment_rows", tuple(dict(row) for row in assignment_rows))
        object.__setattr__(self, "property_rows", tuple(dict(row) for row in property_rows))
        object.__setattr__(self, "component_type_rows", None if component_type_rows is None else tuple(dict(row) for row in component_type_rows))
        object.__setattr__(self, "component_type_source_table", component_type_source_table)
        object.__setattr__(self, "component_type_source_column", component_type_source_column)
        object.__setattr__(self, "component_type_join_key_column", component_type_join_key_column)
        object.__setattr__(self, "length_unit_evidence", length_unit_evidence)
        object.__setattr__(self, "require_length_unit_evidence", require_length_unit_evidence)
        object.__setattr__(self, "mapping", mapping)

    def iter_geometry_rows(self) -> Sequence[Mapping[str, object]]:
        rows, _diagnostics, _summary = self._resolved_probe_data()
        return rows

    def iter_geometry_diagnostics(self) -> Sequence[LiveGeometryProbeDiagnostic]:
        _rows, diagnostics, _summary = self._resolved_probe_data()
        return diagnostics

    def live_geometry_probe_summary_fields(self) -> Mapping[str, object]:
        _rows, _diagnostics, summary = self._resolved_probe_data()
        return summary

    def _resolved_probe_data(self) -> tuple[tuple[Mapping[str, object], ...], tuple[LiveGeometryProbeDiagnostic, ...], Mapping[str, object]]:
        component_source = _component_type_source_from_fixture_rows(
            rows=self.component_type_rows,
            source_table=self.component_type_source_table,
            source_column=self.component_type_source_column,
            join_key_column=self.component_type_join_key_column,
        )
        if component_source.status == "MISSING" and self.component_type_rows is None:
            rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
                assignment_rows=self.assignment_rows,
                property_rows=self.property_rows,
                mapping=self.mapping,
                length_unit_evidence=self.length_unit_evidence,
                require_length_unit_evidence=self.require_length_unit_evidence,
            )
            return rows, diagnostics, _summary_fields(
                assignment_count=len(self.assignment_rows),
                property_count=len(self.property_rows),
                component_source=component_source,
                resolved_type_count=len(rows),
                resolved_geometry_count=len(rows),
                length_unit_evidence=self.length_unit_evidence,
            )
        if component_source.status != "FETCHED" or not component_source.evidence_by_unique_name:
            return (), component_source.diagnostics, _summary_fields(
                assignment_count=len(self.assignment_rows),
                property_count=len(self.property_rows),
                component_source=component_source,
                resolved_type_count=0,
                resolved_geometry_count=0,
                length_unit_evidence=self.length_unit_evidence,
            )
        rows, resolver_diagnostics = resolve_geometry_rows_from_accepted_mapping(
            assignment_rows=self.assignment_rows,
            property_rows=self.property_rows,
            mapping=self.mapping,
            component_type_evidence_by_unique_name=component_source.evidence_by_unique_name,
            component_type_unsupported_unique_names=_unsupported_component_ids(component_source.diagnostics),
            length_unit_evidence=self.length_unit_evidence,
            require_length_unit_evidence=self.require_length_unit_evidence,
        )
        resolved_type_count = _count_assignment_rows_with_component_type_evidence(
            assignment_rows=self.assignment_rows,
            evidence_by_unique_name=component_source.evidence_by_unique_name,
        )
        return rows, component_source.diagnostics + resolver_diagnostics, _summary_fields(
            assignment_count=len(self.assignment_rows),
            property_count=len(self.property_rows),
            component_source=component_source,
            resolved_type_count=resolved_type_count,
            resolved_geometry_count=len(rows),
            length_unit_evidence=self.length_unit_evidence,
        )


def probe_geometry_feature_snapshots(
    *,
    provider: GeometryRowProvider,
    output_dir: Path,
    target_story: str | None = None,
    target_label: str | None = None,
    target_component: str | None = None,
    design_context: Mapping[str, object] | None = None,
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> LiveGeometryProbeResult:
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    context = {
        str(key): value
        for key, value in sorted(
            (design_context or {}).items(),
            key=lambda item: str(item[0]),
        )
        if value is not None
    }

    out_dir = Path(output_dir)
    feature_snapshot_path = out_dir / "feature_snapshot.json"
    summary_path = out_dir / "live_geometry_probe_summary.json"
    diagnostics_path = out_dir / "live_geometry_probe_diagnostics.json"
    manifest_path = out_dir / "live_geometry_probe_manifest.json"

    rows = tuple(provider.iter_geometry_rows())
    selected_rows, truncation_applied = _select_rows(
        rows,
        target_story=target_story,
        target_label=target_label,
        target_component=target_component,
        max_rows=max_rows,
    )
    snapshots: list[FeatureSnapshot] = []
    diagnostics: list[LiveGeometryProbeDiagnostic] = list(_provider_diagnostics(provider))
    provider_summary = _provider_summary_fields(provider, resolved_row_count=len(rows))

    for row in selected_rows:
        snapshot, row_diagnostics = _snapshot_from_row(
            row,
            design_context=context,
        )
        diagnostics.extend(row_diagnostics)
        if snapshot is not None:
            snapshots.append(snapshot)

    if truncation_applied:
        diagnostics.append(LiveGeometryProbeDiagnostic(status="WARNING", code="ROW_LIMIT_TRUNCATED", message=f"Probe row selection was capped at max_rows={max_rows}"))
    if not snapshots and diagnostics:
        status = "FAIL"
    elif diagnostics:
        status = "PARTIAL"
    else:
        status = "OK"

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(feature_snapshot_path, {"snapshots": [snapshot.as_dict() for snapshot in snapshots]})
    _write_json(diagnostics_path, [diagnostic.as_dict() for diagnostic in diagnostics])
    _write_json(
        summary_path,
        {
            "assignment_table_row_count": _int_summary_value(provider_summary.get("assignment_table_row_count"), default=0),
            "candidate_row_count": len(rows),
            "component_type_resolved_row_count": _int_summary_value(provider_summary.get("component_type_resolved_row_count"), default=0),
            "component_type_source_row_count": _int_summary_value(provider_summary.get("component_type_source_row_count"), default=0),
            "component_type_source_status": _text(provider_summary.get("component_type_source_status")) or "UNKNOWN",
            "component_type_source_table": _text_or_none(provider_summary.get("component_type_source_table")),
            "component_type_unresolved_row_count": _int_summary_value(provider_summary.get("component_type_unresolved_row_count"), default=0),
            "diagnostic_count": len(diagnostics),
            "feature_status_counts": _feature_status_counts(snapshots),
            "length_unit_source": _text_or_none(provider_summary.get("length_unit_source")),
            "max_rows": max_rows,
            "property_table_row_count": _int_summary_value(provider_summary.get("property_table_row_count"), default=0),
            "resolved_geometry_row_count": _int_summary_value(provider_summary.get("resolved_geometry_row_count"), default=len(rows)),
            "selected_row_count": len(selected_rows),
            "snapshot_count": len(snapshots),
            "status": status,
            "target_report_length_unit": _REQUIRED_UNIT,
            "truncation_applied": truncation_applied,
        },
    )
    _write_json(
        manifest_path,
        {
            "accepted_geometry_mapping": DEFAULT_ACCEPTED_GEOMETRY_MAPPING.as_dict(),
            "component_type_source_table": _LOCKED_COMPONENT_TYPE_SOURCE_TABLE,
            "design_context": context,
            "length_unit_maps": {"length_units": LENGTH_UNITS, "length_to_mm_factor": LENGTH_TO_MM_FACTOR},
            "live_etabs_required_for_ci": False,
            "output_files": list(_OUTPUT_FILES),
            "probe_is_read_only": True,
            "property_source_table": _LOCKED_PROPERTY_SOURCE_TABLE,
            "runner": _RUNNER,
            "scope": _PROBE_SCOPE,
            "section_assignment_source_table": _LOCKED_ASSIGNMENT_SOURCE_TABLE,
            "selectors": {"target_component": target_component, "target_label": target_label, "target_story": target_story},
            "target_report_length_unit": _REQUIRED_UNIT,
        },
    )

    return LiveGeometryProbeResult(status=status, output_dir=out_dir, feature_snapshot_path=feature_snapshot_path, summary_path=summary_path, diagnostics_path=diagnostics_path, manifest_path=manifest_path, snapshot_count=len(snapshots), diagnostic_count=len(diagnostics))


def write_com_attach_failure_probe_outputs(*, output_dir: Path, attach_result: EtabsAttachResult) -> LiveGeometryProbeResult:
    out_dir = Path(output_dir)
    feature_snapshot_path = out_dir / "feature_snapshot.json"
    summary_path = out_dir / "live_geometry_probe_summary.json"
    diagnostics_path = out_dir / "live_geometry_probe_diagnostics.json"
    manifest_path = out_dir / "live_geometry_probe_manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    if feature_snapshot_path.exists():
        feature_snapshot_path.unlink()
    attempts = [attempt.as_dict() for attempt in attach_result.attempts]
    _write_json(
        summary_path,
        {
            "assignment_table_row_count": 0,
            "component_type_resolved_row_count": 0,
            "component_type_source_row_count": 0,
            "component_type_source_status": "NOT_ATTEMPTED",
            "component_type_source_table": None,
            "component_type_unresolved_row_count": 0,
            "diagnostic_count": len(attempts),
            "failure_stage": "COM_ATTACH",
            "feature_snapshot_written": False,
            "property_table_row_count": 0,
            "resolved_geometry_row_count": 0,
            "scope": _ATTACH_FAILURE_SCOPE,
            "status": "FAIL",
        },
    )
    _write_json(diagnostics_path, [{"attempts": attempts, "code": "ETABS_COM_ATTACH_FAILED", "message": "No attach strategy succeeded.", "status": "BLOCKED"}])
    _write_json(manifest_path, {"attach_attempt_count": len(attempts), "attach_strategies": list(ATTACH_STRATEGIES), "failure_stage": "COM_ATTACH", "feature_snapshot_written": False, "live_etabs_required_for_ci": False, "output_files": list(_ATTACH_FAILURE_OUTPUT_FILES), "probe_is_read_only": True, "runner": _ATTACH_FAILURE_RUNNER, "scope": _ATTACH_FAILURE_SCOPE})
    return LiveGeometryProbeResult(status="FAIL", output_dir=out_dir, feature_snapshot_path=feature_snapshot_path, summary_path=summary_path, diagnostics_path=diagnostics_path, manifest_path=manifest_path, snapshot_count=0, diagnostic_count=len(attempts))


def load_mapping_provider_from_json(path: Path) -> MappingGeometryRowProvider:
    return MappingGeometryRowProvider(_load_payload_rows(path, field_name="rows"))


def load_accepted_mapping_provider_from_json(*, assignment_rows_path: Path, property_rows_path: Path, mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING) -> AcceptedMappingGeometryRowProvider:
    return AcceptedMappingGeometryRowProvider(assignment_rows=_load_payload_rows(assignment_rows_path, field_name="assignment_rows"), property_rows=_load_payload_rows(property_rows_path, field_name="property_rows"), mapping=mapping)


def create_live_etabs_geometry_provider(*, max_candidate_tables: int = 5, attach_result: EtabsAttachResult | None = None) -> GeometryRowProvider:
    return _EtabsComGeometryProvider(max_candidate_tables=max_candidate_tables, attach_result=attach_result, mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING)


@dataclass(frozen=True, slots=True)
class _EtabsComGeometryProvider:
    max_candidate_tables: int = 5
    attach_result: EtabsAttachResult | None = None
    mapping: AcceptedGeometryMapping = DEFAULT_ACCEPTED_GEOMETRY_MAPPING

    def iter_geometry_rows(self) -> Sequence[Mapping[str, object]]:
        rows, _diagnostics, _summary = self._resolved_probe_data()
        return rows

    def iter_geometry_diagnostics(self) -> Sequence[LiveGeometryProbeDiagnostic]:
        _rows, diagnostics, _summary = self._resolved_probe_data()
        return diagnostics

    def live_geometry_probe_summary_fields(self) -> Mapping[str, object]:
        _rows, _diagnostics, summary = self._resolved_probe_data()
        return summary

    def _resolved_probe_data(self) -> tuple[tuple[Mapping[str, object], ...], tuple[LiveGeometryProbeDiagnostic, ...], Mapping[str, object]]:
        if self.max_candidate_tables <= 0:
            raise ValueError("max_candidate_tables must be positive")
        attach_result = self.attach_result or attach_to_running_etabs()
        if attach_result.status != "ATTACHED":
            raise EtabsAttachFailure(attach_result)
        sap_model = attach_result.sap_model
        if sap_model is None:
            raise RuntimeError("ETABS attach succeeded without SapModel")
        database_tables = sap_model.DatabaseTables
        assignment_result = read_live_etabs_table_for_geometry(database_tables, self.mapping.assignment_table_key)
        property_result = read_live_etabs_table_for_geometry(database_tables, self.mapping.property_table_key)
        component_source = read_live_frame_component_type_source(database_tables, max_candidate_tables=self.max_candidate_tables)
        need_unit_evidence = _rows_need_runtime_units(property_result.rows, mapping=self.mapping)
        length_unit_evidence, unit_diagnostics = read_live_etabs_length_unit_evidence(sap_model) if need_unit_evidence else (None, ())
        table_diagnostics = _table_read_diagnostics(table_role="ASSIGNMENT", result=assignment_result) + _table_read_diagnostics(table_role="PROPERTY", result=property_result)
        resolved_type_count = _count_assignment_rows_with_component_type_evidence(assignment_rows=assignment_result.rows, evidence_by_unique_name=component_source.evidence_by_unique_name)
        summary = _summary_fields(assignment_count=assignment_result.row_count, property_count=property_result.row_count, component_source=component_source, resolved_type_count=resolved_type_count, resolved_geometry_count=0, length_unit_evidence=length_unit_evidence)
        if table_diagnostics:
            return (), table_diagnostics + component_source.diagnostics, summary
        if component_source.status != "FETCHED" or not component_source.evidence_by_unique_name:
            return (), component_source.diagnostics, summary
        rows, resolver_diagnostics = resolve_geometry_rows_from_accepted_mapping(
            assignment_rows=assignment_result.rows,
            property_rows=property_result.rows,
            mapping=self.mapping,
            component_type_evidence_by_unique_name=component_source.evidence_by_unique_name,
            component_type_unsupported_unique_names=_unsupported_component_ids(component_source.diagnostics),
            length_unit_evidence=length_unit_evidence,
            require_length_unit_evidence=need_unit_evidence,
        )
        return rows, component_source.diagnostics + unit_diagnostics + resolver_diagnostics, {**summary, "resolved_geometry_row_count": len(rows)}


def resolve_geometry_rows_from_accepted_mapping(
    *,
    assignment_rows: Sequence[Mapping[str, object]],
    property_rows: Sequence[Mapping[str, object]],
    mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    component_type_evidence_by_unique_name: Mapping[str, LiveFrameComponentTypeEvidence] | None = None,
    component_type_unsupported_unique_names: frozenset[str] | None = None,
    length_unit_evidence: LiveEtabsLengthUnitEvidence | None = None,
    require_length_unit_evidence: bool = False,
) -> tuple[tuple[Mapping[str, object], ...], tuple[LiveGeometryProbeDiagnostic, ...]]:
    diagnostics: list[LiveGeometryProbeDiagnostic] = []
    if mapping is None:
        return (), (LiveGeometryProbeDiagnostic(status="BLOCKED", code="ACCEPTED_GEOMETRY_MAPPING_MISSING", message="Accepted geometry mapping is missing; no geometry values were guessed"),)
    assignment_tuple = tuple(dict(row) for row in assignment_rows)
    property_tuple = tuple(dict(row) for row in property_rows)
    if not assignment_tuple:
        return (), (LiveGeometryProbeDiagnostic(status="NO_DATA", code="ASSIGNMENT_TABLE_MISSING_OR_EMPTY", message="Assignment table rows are missing; no geometry values were guessed", source_table=mapping.assignment_table_key),)
    if not property_tuple:
        return (), (LiveGeometryProbeDiagnostic(status="NO_DATA", code="PROPERTY_TABLE_MISSING_OR_EMPTY", message="Property definition table rows are missing; no geometry values were guessed", source_table=mapping.property_table_key),)
    missing_assignment_columns = _missing_columns(assignment_tuple, ("Story", "Label", "UniqueName", mapping.assignment_section_column))
    if missing_assignment_columns:
        return (), (LiveGeometryProbeDiagnostic(status="BLOCKED", code="ASSIGNMENT_TABLE_REQUIRED_COLUMN_MISSING", message="Assignment table is missing required columns: " + ", ".join(missing_assignment_columns), source_table=mapping.assignment_table_key),)
    missing_property_columns = _missing_columns(property_tuple, (mapping.property_name_column, mapping.width_column, mapping.depth_column))
    if missing_property_columns:
        return (), (LiveGeometryProbeDiagnostic(status="BLOCKED", code="PROPERTY_TABLE_REQUIRED_COLUMN_MISSING", message="Property definition table is missing required columns: " + ", ".join(missing_property_columns), source_table=mapping.property_table_key),)

    properties_by_section = _index_property_rows(property_tuple, mapping=mapping)
    resolved_rows: list[Mapping[str, object]] = []
    for assignment_row in assignment_tuple:
        assignment = _assignment_from_row(
            assignment_row,
            mapping=mapping,
            diagnostics=diagnostics,
            component_type_evidence_by_unique_name=component_type_evidence_by_unique_name,
            component_type_unsupported_unique_names=component_type_unsupported_unique_names,
        )
        if assignment is None:
            continue
        property_row = properties_by_section.get(assignment.section_name)
        if property_row is None:
            diagnostics.append(LiveGeometryProbeDiagnostic(status="NO_DATA", code="SECTION_PROPERTY_NOT_FOUND", message="Assignment section property was not found in accepted property definition table", component_id=assignment.unique_name, component_type=assignment.component_type, source_table=mapping.property_table_key))
            continue
        property_value = _property_from_row(property_row, mapping=mapping, diagnostics=diagnostics, assignment=assignment, length_unit_evidence=length_unit_evidence, require_length_unit_evidence=require_length_unit_evidence)
        if property_value is None:
            continue
        resolved = LiveGeometryResolvedRow(story=assignment.story, label=assignment.label, unique_name=assignment.unique_name, section_name=assignment.section_name, width=property_value.width, depth=property_value.depth, assignment_table=assignment.source_table, property_table=property_value.source_table, component_type=assignment.component_type, component_type_source_table=assignment.component_type_source_table, component_type_source_column=assignment.component_type_source_column, component_type_source_row=assignment.component_type_source_row or {}, component_type_join_key_column=assignment.component_type_join_key_column)
        resolved_rows.append(resolved.as_feature_row(mapping=mapping, assignment_row=assignment.raw_row, property_row=property_value.raw_row))
    return tuple(resolved_rows), tuple(diagnostics)


def read_live_etabs_table_for_geometry(database_tables: object, table_key: str) -> LiveEtabsTableReadResult:
    try:
        raw_result = database_tables.GetTableForDisplayArray(table_key, [], "", 0, [], 0, [])
    except Exception as exc:
        return LiveEtabsTableReadResult(table_key=table_key, status="FAILED", columns=(), row_count=0, rows=(), raw_metadata={"exception_type": type(exc).__name__}, message=str(exc) or repr(exc))
    return _table_read_result_from_raw(table_key=table_key, raw_result=raw_result)


def read_live_frame_component_type_source(database_tables: object, *, max_candidate_tables: int = 5) -> LiveFrameComponentTypeSourceResult:
    result = read_live_etabs_table_for_geometry(database_tables, _LOCKED_COMPONENT_TYPE_SOURCE_TABLE)
    return _component_type_source_from_table_read_results((result,))


def read_live_etabs_length_unit_evidence(sap_model: object) -> tuple[LiveEtabsLengthUnitEvidence | None, tuple[LiveGeometryProbeDiagnostic, ...]]:
    present_reader = getattr(sap_model, "GetPresentUnits_2", None)
    database_reader = getattr(sap_model, "GetDatabaseUnits_2", None)
    if not callable(present_reader) or not callable(database_reader):
        return None, (_unit_missing_diag(role="present", reason="unit API method is unavailable"),)
    try:
        present_raw = tuple(present_reader())
        database_raw = tuple(database_reader())
    except Exception as exc:
        return None, (LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_EVIDENCE_MISSING", message=str(exc) or "ETABS unit evidence could not be read"),)
    present_units, present_diag = _unit_values_from_raw(present_raw, role="present")
    database_units, database_diag = _unit_values_from_raw(database_raw, role="database")
    diagnostics = present_diag + database_diag
    if present_units is None or database_units is None:
        return None, diagnostics
    return LiveEtabsLengthUnitEvidence(present_force_unit=present_units["force_unit"], present_length_unit=present_units["length_unit"], present_temperature_unit=present_units["temperature_unit"], database_force_unit=database_units["force_unit"], database_length_unit=database_units["length_unit"], database_temperature_unit=database_units["temperature_unit"], present_units_raw=present_raw, database_units_raw=database_raw), diagnostics


def _component_type_source_from_table_read_results(results: Sequence[LiveEtabsTableReadResult]) -> LiveFrameComponentTypeSourceResult:
    for result in results:
        if result.status != "FETCHED":
            continue
        source_column = _first_available_column(result.columns, _COMPONENT_TYPE_COLUMN_CANDIDATES)
        join_key_column = _first_available_column(result.columns, _COMPONENT_TYPE_JOIN_KEY_CANDIDATES)
        if source_column is None:
            return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=result.table_key, source_column=None, join_key_column=None, row_count=result.row_count, evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_SOURCE_COLUMN_MISSING", message="Fetched component type source table does not expose an explicit beam/column type column", source_table=result.table_key),))
        if join_key_column is None:
            return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=result.table_key, source_column=None, join_key_column=None, row_count=result.row_count, evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_JOIN_KEY_MISSING", message="Fetched component type source table does not expose an explicit join key column", source_table=result.table_key),))
        evidence_by_unique_name, diagnostics = _component_type_evidence_from_rows(rows=result.rows, source_table=result.table_key, source_column=source_column, join_key_column=join_key_column)
        return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=result.table_key, source_column=source_column, join_key_column=join_key_column, row_count=result.row_count, evidence_by_unique_name=evidence_by_unique_name, diagnostics=diagnostics)
    first = results[0] if results else None
    if first is None:
        return LiveFrameComponentTypeSourceResult(status="MISSING", source_table=None, source_column=None, join_key_column=None, row_count=0, evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="NO_DATA", code="COMPONENT_TYPE_SOURCE_TABLE_MISSING", message="Locked component type source table was not checked"),))
    if first.status == "FAILED" and first.raw_metadata.get("exception_type") in {"KeyError", "LookupError"}:
        return LiveFrameComponentTypeSourceResult(status="MISSING", source_table=None, source_column=None, join_key_column=None, row_count=0, evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="NO_DATA", code="COMPONENT_TYPE_SOURCE_TABLE_MISSING", message="Locked component type source table was not available", source_table=first.table_key),))
    return LiveFrameComponentTypeSourceResult(status=first.status, source_table=first.table_key, source_column=None, join_key_column=None, row_count=0, evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_SOURCE_TABLE_FETCH_FAILED", message=first.message or "Component type source table fetch failed", source_table=first.table_key),))


def _component_type_source_from_fixture_rows(*, rows: Sequence[Mapping[str, object]] | None, source_table: str | None, source_column: str | None, join_key_column: str | None) -> LiveFrameComponentTypeSourceResult:
    if rows is None:
        return LiveFrameComponentTypeSourceResult(status="MISSING", source_table=source_table, source_column=source_column, join_key_column=join_key_column, row_count=0, evidence_by_unique_name={}, diagnostics=())
    table_name = source_table or _LOCKED_COMPONENT_TYPE_SOURCE_TABLE
    row_tuple = tuple(dict(row) for row in rows)
    if not row_tuple:
        return LiveFrameComponentTypeSourceResult(status="EMPTY", source_table=table_name, source_column=source_column, join_key_column=join_key_column, row_count=0, evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="NO_DATA", code="COMPONENT_TYPE_SOURCE_TABLE_EMPTY", message="Component type source rows are empty", source_table=table_name),))
    columns = tuple(str(key) for row in row_tuple for key in row.keys())
    column_set = set(columns)
    resolved_source_column = source_column or _first_available_column(columns, _COMPONENT_TYPE_COLUMN_CANDIDATES)
    resolved_join_column = join_key_column or _first_available_column(columns, _COMPONENT_TYPE_JOIN_KEY_CANDIDATES)
    if resolved_source_column is not None and resolved_source_column not in column_set:
        return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=table_name, source_column=resolved_source_column, join_key_column=resolved_join_column, row_count=len(row_tuple), evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_SOURCE_COLUMN_MISSING", message="Component type source fixture does not expose the configured explicit type column", source_table=table_name),))
    if resolved_join_column is not None and resolved_join_column not in column_set:
        return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=table_name, source_column=resolved_source_column, join_key_column=resolved_join_column, row_count=len(row_tuple), evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_JOIN_KEY_MISSING", message="Component type source fixture does not expose the configured explicit join key column", source_table=table_name),))
    if resolved_source_column is None:
        return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=table_name, source_column=None, join_key_column=resolved_join_column, row_count=len(row_tuple), evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_SOURCE_COLUMN_MISSING", message="Component type source fixture does not expose an explicit type column", source_table=table_name),))
    if resolved_join_column is None:
        return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=table_name, source_column=resolved_source_column, join_key_column=None, row_count=len(row_tuple), evidence_by_unique_name={}, diagnostics=(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_JOIN_KEY_MISSING", message="Component type source fixture does not expose an explicit join key column", source_table=table_name),))
    evidence_by_unique_name, diagnostics = _component_type_evidence_from_rows(rows=row_tuple, source_table=table_name, source_column=resolved_source_column, join_key_column=resolved_join_column)
    return LiveFrameComponentTypeSourceResult(status="FETCHED", source_table=table_name, source_column=resolved_source_column, join_key_column=resolved_join_column, row_count=len(row_tuple), evidence_by_unique_name=evidence_by_unique_name, diagnostics=diagnostics)


def _component_type_evidence_from_rows(*, rows: Sequence[Mapping[str, object]], source_table: str, source_column: str, join_key_column: str) -> tuple[Mapping[str, LiveFrameComponentTypeEvidence], tuple[LiveGeometryProbeDiagnostic, ...]]:
    evidence_by_unique_name: dict[str, LiveFrameComponentTypeEvidence] = {}
    diagnostics: list[LiveGeometryProbeDiagnostic] = []
    for row in rows:
        unique_name = _text(row.get(join_key_column))
        if not unique_name:
            diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_JOIN_KEY_MISSING", message="Component type source row does not contain an explicit join key value", source_table=source_table))
            continue
        component_type = _normalize_component_type(row.get(source_column))
        if component_type not in _FEATURES_BY_COMPONENT_TYPE:
            diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_VALUE_UNSUPPORTED", message="Component type source row value is not supported as beam or column", component_id=unique_name, source_table=source_table))
            continue
        evidence_by_unique_name[unique_name] = LiveFrameComponentTypeEvidence(unique_name=unique_name, component_type=component_type, source_table=source_table, source_column=source_column, raw_row=row, join_key_column=join_key_column)
    return evidence_by_unique_name, tuple(diagnostics)


def _unsupported_component_ids(diagnostics: Sequence[LiveGeometryProbeDiagnostic]) -> frozenset[str]:
    return frozenset(
        diagnostic.component_id
        for diagnostic in diagnostics
        if diagnostic.code == "COMPONENT_TYPE_VALUE_UNSUPPORTED" and diagnostic.component_id
    )


def _table_read_result_from_raw(*, table_key: str, raw_result: object) -> LiveEtabsTableReadResult:
    metadata = _raw_table_metadata(raw_result)
    if isinstance(raw_result, Mapping):
        return _table_read_result_from_mapping(table_key=table_key, raw_result=raw_result, metadata=metadata)
    if not isinstance(raw_result, Sequence) or isinstance(raw_result, (str, bytes, bytearray)):
        return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=(), row_count=0, rows=(), raw_metadata=metadata, message="ETABS display array result was not a supported sequence or mapping shape")
    sequences = tuple(item for item in raw_result if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)))
    string_sequences = tuple(tuple(str(value) for value in item) for item in sequences if all(isinstance(value, str) for value in item))
    columns = _select_column_sequence(table_key=table_key, string_sequences=string_sequences)
    if not columns:
        return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=(), row_count=0, rows=(), raw_metadata=metadata, message="No ETABS display-array field column sequence could be identified")
    data_candidate = _select_flat_data_sequence(columns=columns, sequences=sequences)
    if data_candidate is None:
        status = "EMPTY" if _raw_result_declares_zero_rows(raw_result) else "PARSE_EMPTY"
        return LiveEtabsTableReadResult(table_key=table_key, status=status, columns=columns, row_count=0, rows=(), raw_metadata={**metadata, "columns": list(columns)}, message="No flat data sequence could be identified after the field column sequence")
    if len(data_candidate) == 0:
        return LiveEtabsTableReadResult(table_key=table_key, status="EMPTY", columns=columns, row_count=0, rows=(), raw_metadata={**metadata, "columns": list(columns), "flat_data_length": 0}, message="ETABS returned a field list and zero data values")
    if len(data_candidate) % len(columns) != 0:
        return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=columns, row_count=0, rows=(), raw_metadata={**metadata, "columns": list(columns), "flat_data_length": len(data_candidate)}, message="Flat data length is not divisible by field column count")
    rows = _rows_from_flat_data(table_key=table_key, columns=columns, flat_data=data_candidate)
    if not rows:
        return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=columns, row_count=0, rows=(), raw_metadata={**metadata, "columns": list(columns), "flat_data_length": len(data_candidate)}, message="Flat data sequence could not be decoded into rows")
    return LiveEtabsTableReadResult(table_key=table_key, status="FETCHED", columns=columns, row_count=len(rows), rows=tuple(rows), raw_metadata={**metadata, "columns": list(columns), "flat_data_length": len(data_candidate)})


def _table_read_result_from_mapping(*, table_key: str, raw_result: Mapping[object, object], metadata: Mapping[str, object]) -> LiveEtabsTableReadResult:
    raw_columns = raw_result.get("columns") or raw_result.get("fields") or raw_result.get("field_names") or ()
    if not isinstance(raw_columns, Sequence) or isinstance(raw_columns, (str, bytes, bytearray)):
        return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=(), row_count=0, rows=(), raw_metadata=metadata, message="Mapping table result did not contain a supported columns sequence")
    columns = tuple(str(column) for column in raw_columns)
    raw_rows = raw_result.get("rows")
    if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes, bytearray)):
        rows = tuple({str(key): value for key, value in item.items()} for item in raw_rows if isinstance(item, Mapping))
        return LiveEtabsTableReadResult(table_key=table_key, status="FETCHED" if rows else "EMPTY", columns=columns, row_count=len(rows), rows=rows, raw_metadata=metadata)
    flat_data = raw_result.get("flat_data") or raw_result.get("data")
    if isinstance(flat_data, Sequence) and not isinstance(flat_data, (str, bytes, bytearray)):
        if len(flat_data) == 0:
            return LiveEtabsTableReadResult(table_key=table_key, status="EMPTY", columns=columns, row_count=0, rows=(), raw_metadata=metadata)
        if len(flat_data) % len(columns) != 0:
            return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=columns, row_count=0, rows=(), raw_metadata=metadata)
        rows = tuple(_rows_from_flat_data(table_key=table_key, columns=columns, flat_data=flat_data))
        return LiveEtabsTableReadResult(table_key=table_key, status="FETCHED", columns=columns, row_count=len(rows), rows=rows, raw_metadata=metadata)
    return LiveEtabsTableReadResult(table_key=table_key, status="EMPTY", columns=columns, row_count=0, rows=(), raw_metadata=metadata)


def _assignment_from_row(
    row: Mapping[str, object],
    *,
    mapping: AcceptedGeometryMapping,
    diagnostics: list[LiveGeometryProbeDiagnostic],
    component_type_evidence_by_unique_name: Mapping[str, LiveFrameComponentTypeEvidence] | None = None,
    component_type_unsupported_unique_names: frozenset[str] | None = None,
) -> LiveGeometryAssignmentRow | None:
    story = _text(row.get("Story"))
    label = _text(row.get("Label"))
    unique_name = _text(row.get("UniqueName"))
    section_name = _text(row.get(mapping.assignment_section_column))
    if component_type_evidence_by_unique_name is not None:
        evidence = component_type_evidence_by_unique_name.get(unique_name)
        if evidence is None:
            if unique_name in (component_type_unsupported_unique_names or frozenset()):
                return None
            diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_JOIN_NOT_FOUND", message="No explicit component type evidence row matched the assignment UniqueName", component_id=unique_name, source_table=mapping.assignment_table_key))
            return None
        component_type = evidence.component_type
        component_type_source_table = evidence.source_table
        component_type_source_column = evidence.source_column
        component_type_source_row = evidence.raw_row
        component_type_join_key_column = evidence.join_key_column
    else:
        component_type_source_column = _first_present_column(row, _COMPONENT_TYPE_COLUMN_CANDIDATES)
        component_type = _normalize_component_type(row.get(component_type_source_column) if component_type_source_column else None)
        if not component_type_source_column:
            diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_NOT_EXPLICIT", message="Assignment row does not include explicit beam/column component type evidence", component_id=unique_name or None, source_table=mapping.assignment_table_key))
            return None
        if component_type not in _FEATURES_BY_COMPONENT_TYPE:
            diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_TYPE_VALUE_UNSUPPORTED", message="Assignment row component type value is not supported as beam or column", component_id=unique_name or None, source_table=mapping.assignment_table_key))
            return None
        component_type_source_table = mapping.assignment_table_key
        component_type_source_row = row
        component_type_join_key_column = "UniqueName"
    if not (story and label and unique_name and section_name):
        diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="ASSIGNMENT_ROW_IDENTITY_INCOMPLETE", message="Assignment row identity or section property is incomplete; no geometry value was guessed", component_id=unique_name or None, component_type=component_type, source_table=mapping.assignment_table_key))
        return None
    return LiveGeometryAssignmentRow(story=story, label=label, unique_name=unique_name, section_name=section_name, source_table=mapping.assignment_table_key, component_type=component_type, raw_row=row, component_type_source_table=component_type_source_table, component_type_source_column=component_type_source_column, component_type_source_row=component_type_source_row, component_type_join_key_column=component_type_join_key_column)


def _property_from_row(row: Mapping[str, object], *, mapping: AcceptedGeometryMapping, diagnostics: list[LiveGeometryProbeDiagnostic], assignment: LiveGeometryAssignmentRow, length_unit_evidence: LiveEtabsLengthUnitEvidence | None, require_length_unit_evidence: bool) -> LiveGeometryPropertyRow | None:
    width = _normalize_geometry_dimension(raw_value=row.get(mapping.width_column), source_column=mapping.width_column, row=row, mapping=mapping, assignment=assignment, length_unit_evidence=length_unit_evidence, require_length_unit_evidence=require_length_unit_evidence, diagnostics=diagnostics)
    depth = _normalize_geometry_dimension(raw_value=row.get(mapping.depth_column), source_column=mapping.depth_column, row=row, mapping=mapping, assignment=assignment, length_unit_evidence=length_unit_evidence, require_length_unit_evidence=require_length_unit_evidence, diagnostics=diagnostics)
    if width is None or depth is None:
        return None
    return LiveGeometryPropertyRow(section_name=_text(row.get(mapping.property_name_column)), width=width, depth=depth, source_table=mapping.property_table_key, raw_row=row)


def _normalize_geometry_dimension(*, raw_value: object, source_column: str, row: Mapping[str, object], mapping: AcceptedGeometryMapping, assignment: LiveGeometryAssignmentRow, length_unit_evidence: LiveEtabsLengthUnitEvidence | None, require_length_unit_evidence: bool, diagnostics: list[LiveGeometryProbeDiagnostic]) -> NormalizedGeometryDimension | None:
    is_native_numeric = _is_numeric(raw_value)
    parsed_value = float(raw_value) if is_native_numeric else _parse_plain_numeric(raw_value)
    if parsed_value is None:
        diagnostics.append(_dimension_not_numeric_diagnostic(assignment=assignment, mapping=mapping, source_column=source_column))
        return None

    explicit_row_unit = _unit_from_property_row(row, mapping=mapping)
    if explicit_row_unit == _REQUIRED_UNIT and is_native_numeric:
        return NormalizedGeometryDimension(raw_value=raw_value, raw_value_type=type(raw_value).__name__, parsed_value=parsed_value, source_unit=_REQUIRED_UNIT, target_unit=_REQUIRED_UNIT, normalization_factor_to_mm=1.0, normalized_value=parsed_value, normalized_unit=_REQUIRED_UNIT, normalization_basis="PROPERTY_ROW_UNIT_MM", unit_evidence=None)

    if length_unit_evidence is None:
        if require_length_unit_evidence:
            diagnostics.append(_unit_evidence_missing_diagnostic(assignment=assignment, mapping=mapping, source_column=source_column))
        elif is_native_numeric:
            diagnostics.append(_unit_not_proven_mm_diagnostic(assignment=assignment, mapping=mapping, source_column=source_column))
        else:
            diagnostics.append(_dimension_not_numeric_diagnostic(assignment=assignment, mapping=mapping, source_column=source_column))
        return None

    source_unit = length_unit_evidence.present_length_unit
    factor = LENGTH_TO_MM_FACTOR.get(source_unit)
    if factor is None:
        diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_NORMALIZATION_UNSUPPORTED", message="ETABS present length unit is not supported for geometry normalization to mm", component_id=assignment.unique_name, component_type=assignment.component_type, feature_id=source_column, source_table=mapping.property_table_key))
        return None
    normalized = parsed_value * factor
    return NormalizedGeometryDimension(raw_value=raw_value, raw_value_type=type(raw_value).__name__, parsed_value=parsed_value, source_unit=source_unit, target_unit=_REQUIRED_UNIT, normalization_factor_to_mm=factor, normalized_value=normalized, normalized_unit=_REQUIRED_UNIT, normalization_basis=length_unit_evidence.normalization_basis, unit_evidence=length_unit_evidence)


def _parse_plain_numeric(value: object) -> float | None:
    if _is_numeric(value):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _NUMERIC_LITERAL_RE.fullmatch(text):
        return None
    return float(text)


def _dimension_not_numeric_diagnostic(*, assignment: LiveGeometryAssignmentRow, mapping: AcceptedGeometryMapping, source_column: str) -> LiveGeometryProbeDiagnostic:
    return LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_DIMENSION_VALUE_NOT_NUMERIC", message="Accepted property row t2/t3 value is not a plain numeric literal", component_id=assignment.unique_name, component_type=assignment.component_type, feature_id=source_column, source_table=mapping.property_table_key)


def _unit_evidence_missing_diagnostic(*, assignment: LiveGeometryAssignmentRow, mapping: AcceptedGeometryMapping, source_column: str) -> LiveGeometryProbeDiagnostic:
    return LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_EVIDENCE_MISSING", message="ETABS present length unit evidence is required before geometry normalization to mm", component_id=assignment.unique_name, component_type=assignment.component_type, feature_id=source_column, source_table=mapping.property_table_key)


def _unit_not_proven_mm_diagnostic(*, assignment: LiveGeometryAssignmentRow, mapping: AcceptedGeometryMapping, source_column: str) -> LiveGeometryProbeDiagnostic:
    return LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_NOT_PROVEN_MM", message="Numeric geometry value has no explicit mm unit and no runtime ETABS unit evidence", component_id=assignment.unique_name, component_type=assignment.component_type, feature_id=source_column, source_table=mapping.property_table_key)


def _unit_values_from_raw(raw: tuple[object, ...], *, role: str) -> tuple[Mapping[str, str] | None, tuple[LiveGeometryProbeDiagnostic, ...]]:
    if len(raw) < 4:
        return None, (_unit_missing_diag(role=role, reason="unit API returned fewer than four values"),)
    force_enum, length_enum, temperature_enum, return_code = raw[0], raw[1], raw[2], raw[3]
    if return_code != 0:
        return None, (_unit_missing_diag(role=role, reason="unit API return code was nonzero"),)
    if not isinstance(force_enum, int) or not isinstance(length_enum, int) or not isinstance(temperature_enum, int):
        return None, (_unit_missing_diag(role=role, reason="unit API enum values were malformed"),)
    force_unit = FORCE_UNITS.get(force_enum)
    length_unit = LENGTH_UNITS.get(length_enum)
    temperature_unit = TEMP_UNITS.get(temperature_enum)
    if force_unit is None or temperature_unit is None:
        return None, (_unit_missing_diag(role=role, reason="unit API force or temperature enum was unknown"),)
    if length_unit is None:
        return {"force_unit": force_unit, "length_unit": "", "temperature_unit": temperature_unit}, (LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_NORMALIZATION_UNSUPPORTED", message=f"ETABS {role} length unit enum is not supported"),)
    return {"force_unit": force_unit, "length_unit": length_unit, "temperature_unit": temperature_unit}, ()


def _unit_missing_diag(*, role: str, reason: str) -> LiveGeometryProbeDiagnostic:
    return LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_EVIDENCE_MISSING", message=f"ETABS {role} unit evidence is missing: {reason}")


def _table_read_diagnostics(*, table_role: str, result: LiveEtabsTableReadResult) -> tuple[LiveGeometryProbeDiagnostic, ...]:
    role = table_role.upper()
    if result.status == "FETCHED":
        return ()
    if result.status == "FAILED":
        return (LiveGeometryProbeDiagnostic(status="BLOCKED", code=f"{role}_TABLE_FETCH_FAILED", message=result.message or f"{role.title()} table fetch failed", source_table=result.table_key),)
    if result.status == "EMPTY":
        return (LiveGeometryProbeDiagnostic(status="NO_DATA", code=f"{role}_TABLE_FETCHED_ZERO_ROWS", message=f"{role.title()} table was fetched but contained zero rows", source_table=result.table_key),)
    return (LiveGeometryProbeDiagnostic(status="BLOCKED", code=f"{role}_TABLE_PARSE_EMPTY", message=result.message or f"{role.title()} table display array could not be decoded into rows", source_table=result.table_key),)


def _summary_fields(*, assignment_count: int, property_count: int, component_source: LiveFrameComponentTypeSourceResult, resolved_type_count: int, resolved_geometry_count: int, length_unit_evidence: LiveEtabsLengthUnitEvidence | None) -> dict[str, object]:
    return {"assignment_table_row_count": assignment_count, "component_type_resolved_row_count": resolved_type_count, "component_type_source_row_count": component_source.row_count, "component_type_source_status": component_source.status, "component_type_source_table": component_source.source_table, "component_type_unresolved_row_count": max(assignment_count - resolved_type_count, 0), "length_unit_source": None if length_unit_evidence is None else length_unit_evidence.present_length_unit, "property_table_row_count": property_count, "resolved_geometry_row_count": resolved_geometry_count}


def _index_property_rows(rows: Sequence[Mapping[str, object]], *, mapping: AcceptedGeometryMapping) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        section_name = _text(row.get(mapping.property_name_column))
        if section_name and section_name not in indexed:
            indexed[section_name] = row
    return indexed


def _rows_need_runtime_units(rows: Sequence[Mapping[str, object]], *, mapping: AcceptedGeometryMapping) -> bool:
    for row in rows:
        if isinstance(row.get(mapping.width_column), str) or isinstance(row.get(mapping.depth_column), str):
            return True
    return False


def _missing_columns(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> tuple[str, ...]:
    available = {str(key) for row in rows for key in row.keys()}
    return tuple(column for column in columns if column not in available)


def _unit_from_property_row(row: Mapping[str, object], *, mapping: AcceptedGeometryMapping) -> str:
    width_unit = _text(row.get(f"{mapping.width_column}_unit"))
    depth_unit = _text(row.get(f"{mapping.depth_column}_unit"))
    if width_unit and depth_unit and width_unit == depth_unit:
        return width_unit
    return _text(row.get("unit"))


def _select_column_sequence(*, table_key: str, string_sequences: Sequence[tuple[str, ...]]) -> tuple[str, ...]:
    expected = _expected_column_hints(table_key)
    for sequence in string_sequences:
        if expected and expected.issubset(set(sequence)):
            return sequence
    for sequence in string_sequences:
        if sequence and _looks_like_field_sequence(sequence):
            return sequence
    return ()


def _select_flat_data_sequence(*, columns: Sequence[str], sequences: Sequence[Sequence[object]]) -> tuple[object, ...] | None:
    columns_tuple = tuple(columns)
    after_columns = False
    for sequence in sequences:
        current = tuple(sequence)
        if not after_columns:
            if current == columns_tuple:
                after_columns = True
            continue
        if current == columns_tuple:
            continue
        return current
    return None


def _rows_from_flat_data(*, table_key: str, columns: Sequence[str], flat_data: Sequence[object]) -> list[Mapping[str, object]]:
    width = len(columns)
    rows: list[Mapping[str, object]] = []
    if width <= 0:
        return rows
    for index in range(0, len(flat_data), width):
        values = flat_data[index : index + width]
        if len(values) != width:
            continue
        row = {str(field): values[position] for position, field in enumerate(columns)}
        row.setdefault("source_table", table_key)
        row.setdefault("actual_table_name", table_key)
        rows.append(row)
    return rows


def _expected_column_hints(table_key: str) -> frozenset[str]:
    lowered = table_key.casefold()
    if "assignments" in lowered and "section" in lowered:
        return frozenset({"Story", "Label", "UniqueName", "SectProp"})
    if "property definitions" in lowered and "concrete rectangular" in lowered:
        return frozenset({"Name", "t2", "t3"})
    if table_key == _LOCKED_COMPONENT_TYPE_SOURCE_TABLE:
        return frozenset({"UniqueName"})
    return frozenset()


def _looks_like_field_sequence(sequence: Sequence[str]) -> bool:
    known = {"Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp", "Name", "t2", "t3", "Type", "DesignType", "Design Type", "ComponentType", "ObjectType", "FrameType", "MemberType", "ElementType", "LineObjectType", "Classification"}
    return bool(set(sequence).intersection(known))


def _raw_result_declares_zero_rows(raw_result: Sequence[object]) -> bool:
    return any(isinstance(item, int) and not isinstance(item, bool) and item == 0 for item in raw_result)


def _raw_table_metadata(raw_result: object) -> dict[str, object]:
    if isinstance(raw_result, Mapping):
        return {"mapping_keys": [str(key) for key in sorted(raw_result.keys(), key=str)], "raw_type": type(raw_result).__name__}
    if isinstance(raw_result, Sequence) and not isinstance(raw_result, (str, bytes, bytearray)):
        return {"raw_sequence_length": len(raw_result), "raw_type": type(raw_result).__name__, "sequence_item_types": [type(item).__name__ for item in raw_result]}
    return {"raw_type": type(raw_result).__name__}


def _first_available_column(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    available = {str(column): str(column) for column in columns}
    for candidate in candidates:
        if candidate in available:
            return available[candidate]
    return None


def _first_present_column(row: Mapping[str, object], candidates: Sequence[str]) -> str | None:
    for candidate in candidates:
        if candidate in row:
            return candidate
    return None


def _normalize_component_type(value: object) -> str:
    return _COMPONENT_TYPE_VALUES.get(_text(value).casefold(), "")


def _count_assignment_rows_with_component_type_evidence(*, assignment_rows: Sequence[Mapping[str, object]], evidence_by_unique_name: Mapping[str, LiveFrameComponentTypeEvidence]) -> int:
    count = 0
    for row in assignment_rows:
        unique_name = _text(row.get("UniqueName"))
        if unique_name and unique_name in evidence_by_unique_name:
            count += 1
    return count


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _select_rows(rows: Sequence[Mapping[str, object]], *, target_story: str | None, target_label: str | None, target_component: str | None, max_rows: int) -> tuple[tuple[Mapping[str, object], ...], bool]:
    selected: list[Mapping[str, object]] = []
    for row in rows:
        if target_story is not None and str(row.get("story", "")) != target_story:
            continue
        if target_label is not None and str(row.get("label", "")) != target_label:
            continue
        if target_component is not None and str(row.get("component_id", "")) != target_component:
            continue
        selected.append(row)
    return tuple(selected[:max_rows]), len(selected) > max_rows


def _snapshot_from_row(
    row: Mapping[str, object],
    *,
    design_context: Mapping[str, object],
) -> tuple[FeatureSnapshot | None, tuple[LiveGeometryProbeDiagnostic, ...]]:
    diagnostics: list[LiveGeometryProbeDiagnostic] = []
    component_type = _text(row.get("component_type")).casefold()
    component_id = _text(row.get("component_id"))
    if component_type not in _FEATURES_BY_COMPONENT_TYPE:
        return None, (LiveGeometryProbeDiagnostic(status="WARNING", code="COMPONENT_TYPE_OUT_OF_SCOPE", message="Only beam and column geometry rows are supported", component_id=component_id or None, component_type=component_type or None, source_table=_text_or_none(row.get("source_table"))),)
    if not component_id:
        return None, (LiveGeometryProbeDiagnostic(status="BLOCKED", code="COMPONENT_ID_MISSING", message="Geometry row does not include component_id", component_type=component_type, source_table=_text_or_none(row.get("source_table"))),)
    width_feature, depth_feature = _FEATURES_BY_COMPONENT_TYPE[component_type]
    features = {
        width_feature: _feature_from_dimension_row(row, component_id=component_id, component_type=component_type, feature_id=width_feature, value_keys=_WIDTH_KEYS, details_key="width_normalization", diagnostics=diagnostics),
        depth_feature: _feature_from_dimension_row(row, component_id=component_id, component_type=component_type, feature_id=depth_feature, value_keys=_DEPTH_KEYS, details_key="depth_normalization", diagnostics=diagnostics),
    }
    identity = {
        key: row.get(key)
        for key in _IDENTITY_KEYS
        if row.get(key) is not None
    }
    identity.update(design_context)
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity=identity,
        features=features,
    ), tuple(diagnostics)


def _feature_from_dimension_row(row: Mapping[str, object], *, component_id: str, component_type: str, feature_id: str, value_keys: Sequence[str], details_key: str, diagnostics: list[LiveGeometryProbeDiagnostic]) -> FeatureValue:
    source_table = _text_or_none(row.get("source_table")) or "live_geometry_provider"
    selected_source_key, raw_value = _first_present(row, value_keys)
    unit = _text(row.get(f"{selected_source_key}_unit")) if selected_source_key else ""
    if not unit:
        unit = _text(row.get("unit"))
    if selected_source_key is None or raw_value is None:
        diagnostics.append(LiveGeometryProbeDiagnostic(status="NO_DATA", code="GEOMETRY_FEATURE_MISSING", message="Required observed geometry feature is missing; no value was guessed", component_id=component_id, component_type=component_type, feature_id=feature_id, source_table=source_table))
        return FeatureValue(feature_name=feature_id, value=None, unit=unit, semantic_role="GEOMETRY", status=FeatureValueStatus.MISSING, evidence=())
    if unit != _REQUIRED_UNIT:
        diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_UNIT_NOT_MM", message="Observed geometry unit is not proven to be mm; no unit change was performed", component_id=component_id, component_type=component_type, feature_id=feature_id, source_table=source_table))
        return FeatureValue(feature_name=feature_id, value=None, unit=unit, semantic_role="GEOMETRY", status=FeatureValueStatus.PARTIAL, evidence=())
    if not _is_numeric(raw_value):
        diagnostics.append(LiveGeometryProbeDiagnostic(status="BLOCKED", code="GEOMETRY_VALUE_NOT_NUMERIC", message="Observed geometry value is not numeric", component_id=component_id, component_type=component_type, feature_id=feature_id, source_table=source_table))
        return FeatureValue(feature_name=feature_id, value=None, unit=unit, semantic_role="GEOMETRY", status=FeatureValueStatus.PARTIAL, evidence=())
    value = float(raw_value)
    details = dict(row.get(details_key) or {})
    evidence_source_column = _text_or_none(row.get(f"{selected_source_key}_source_column")) or selected_source_key
    evidence_source_row = {key: _json_safe(item) for key, item in sorted(row.items())}
    evidence_source_row.update(details)
    evidence_source_row["source_column"] = evidence_source_column
    evidence_source_row["source_table"] = source_table
    evidence_raw_value = details.get("raw_value", raw_value)
    evidence_normalized_value = details.get("normalized_value", value)
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=source_table,
        actual_table_name=_text_or_none(row.get("actual_table_name")) or source_table,
        source_column=evidence_source_column,
        source_row=evidence_source_row,
        raw_value=evidence_raw_value,
        normalized_value=float(evidence_normalized_value),
        unit=unit,
        resolver="c13_5_p6_2_runtime_length_unit_normalizer" if details else "c13_5_p6_1_design_type_alias_probe",
    )
    return FeatureValue(feature_name=feature_id, value=value, unit=unit, semantic_role="GEOMETRY", status=FeatureValueStatus.RESOLVED, evidence=(evidence,))


def _provider_diagnostics(provider: GeometryRowProvider) -> tuple[LiveGeometryProbeDiagnostic, ...]:
    diagnostic_reader = getattr(provider, "iter_geometry_diagnostics", None)
    if not callable(diagnostic_reader):
        return ()
    diagnostics = diagnostic_reader()
    return tuple(diagnostic for diagnostic in diagnostics if isinstance(diagnostic, LiveGeometryProbeDiagnostic))


def _provider_summary_fields(provider: GeometryRowProvider, *, resolved_row_count: int) -> Mapping[str, object]:
    default = {"assignment_table_row_count": 0, "component_type_resolved_row_count": 0, "component_type_source_row_count": 0, "component_type_source_status": "UNKNOWN", "component_type_source_table": None, "component_type_unresolved_row_count": 0, "length_unit_source": None, "property_table_row_count": 0, "resolved_geometry_row_count": resolved_row_count}
    summary_reader = getattr(provider, "live_geometry_probe_summary_fields", None)
    if not callable(summary_reader):
        return default
    summary = summary_reader()
    if not isinstance(summary, Mapping):
        return default
    return dict(summary)


def _first_present(row: Mapping[str, object], keys: Sequence[str]) -> tuple[str | None, object | None]:
    for key in keys:
        if key in row:
            return key, row[key]
    return None, None


def _load_payload_rows(path: Path, *, field_name: str) -> tuple[Mapping[str, object], ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError(f"{field_name} fixture must be a row list or an object with a rows list")
    normalized: list[Mapping[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{field_name} row at index {index} must be an object")
        normalized.append(dict(row))
    return tuple(normalized)


def _feature_status_counts(snapshots: Sequence[FeatureSnapshot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for snapshot in snapshots:
        for feature in snapshot.features.values():
            status = feature.status.value
            counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _int_summary_value(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _text_or_none(value: object) -> str | None:
    text = _text(value)
    return text or None


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(nested) for key, nested in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "AcceptedGeometryMapping",
    "AcceptedMappingGeometryRowProvider",
    "DEFAULT_ACCEPTED_GEOMETRY_MAPPING",
    "FORCE_UNITS",
    "GeometryRowProvider",
    "LENGTH_TO_MM_FACTOR",
    "LENGTH_UNITS",
    "LiveEtabsLengthUnitEvidence",
    "LiveEtabsTableReadResult",
    "LiveFrameComponentTypeEvidence",
    "LiveFrameComponentTypeSourceResult",
    "LiveGeometryAssignmentRow",
    "LiveGeometryProbeDiagnostic",
    "LiveGeometryProbeResult",
    "LiveGeometryPropertyRow",
    "LiveGeometryResolvedRow",
    "MappingGeometryRowProvider",
    "TEMP_UNITS",
    "create_live_etabs_geometry_provider",
    "load_accepted_mapping_provider_from_json",
    "load_mapping_provider_from_json",
    "probe_geometry_feature_snapshots",
    "read_live_etabs_length_unit_evidence",
    "read_live_etabs_table_for_geometry",
    "read_live_frame_component_type_source",
    "resolve_geometry_rows_from_accepted_mapping",
    "write_com_attach_failure_probe_outputs",
]
