"""C13.5 live read-only geometry FeatureSnapshot probe.

This module creates FeatureSnapshot JSON from observed geometry rows only. Live
ETABS access is optional and isolated behind explicit runtime boundaries. COM
attachment stays in tbdy_engine.features.etabs_com_attach.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import json

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
_REQUIRED_UNIT = "mm"
_DEFAULT_MAX_ROWS = 20
_FORBIDDEN_SCOPE = (
    "new_engineering_checks",
    "flexure",
    "shear",
    "rebar",
    "capacity_design",
    "SCWB",
    "column_PMM",
    "drift",
    "modal_mass",
    "load_combination_selection",
    "force_envelope_selection",
    "Excel_production_input",
    "Streamlit_UI",
    "final_building_compliance_verdict",
    "implicit_unit_conversion",
    "section_name_parsing",
    "dimension_guessing",
)
_FEATURES_BY_COMPONENT_TYPE: Mapping[str, tuple[str, str]] = {
    "beam": ("beam_width_mm", "beam_depth_mm"),
    "column": ("column_width_mm", "column_depth_mm"),
}
_WIDTH_KEYS = ("width_mm", "beam_width_mm", "column_width_mm")
_DEPTH_KEYS = ("depth_mm", "beam_depth_mm", "column_depth_mm")
_IDENTITY_KEYS = ("label", "story", "section", "unique_name", "section_name")
_COMPONENT_TYPE_COLUMN_CANDIDATES = ("component_type", "ComponentType", "ObjectType", "FrameType", "Type")
_COMPONENT_TYPE_VALUES = {"beam": "beam", "column": "column"}


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
            raw_value = getattr(self, field_name)
            if raw_value is None or not str(raw_value).strip():
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
    assignment_table_key="Frame Assignments - Section Properties",
    assignment_section_column="SectProp",
    property_table_key="Frame Section Property Definitions - Concrete Rectangular",
    property_name_column="Name",
    width_column="t2",
    depth_column="t3",
    mapping_basis="explicit_columns_only",
)


@dataclass(frozen=True, slots=True)
class LiveGeometryAssignmentRow:
    story: str
    label: str
    unique_name: str
    section_name: str
    source_table: str
    component_type: str
    raw_row: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.story or not self.label or not self.unique_name or not self.section_name:
            raise ValueError("LiveGeometryAssignmentRow requires story, label, unique_name, and section_name")
        if self.component_type not in _FEATURES_BY_COMPONENT_TYPE:
            raise ValueError("LiveGeometryAssignmentRow.component_type must be beam or column")
        object.__setattr__(self, "raw_row", dict(self.raw_row))


@dataclass(frozen=True, slots=True)
class LiveGeometryPropertyRow:
    section_name: str
    width_value: object
    depth_value: object
    source_table: str
    unit: str
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
    width_value: object
    depth_value: object
    assignment_table: str
    property_table: str
    component_type: str
    unit: str

    def as_feature_row(self, *, mapping: AcceptedGeometryMapping, assignment_row: Mapping[str, object], property_row: Mapping[str, object]) -> dict[str, object]:
        return {
            "actual_table_name": self.property_table,
            "assignment_section_column": mapping.assignment_section_column,
            "assignment_source_row": dict(assignment_row),
            "component_id": self.unique_name,
            "component_type": self.component_type,
            "depth_column": mapping.depth_column,
            "depth_mm": self.depth_value,
            "depth_mm_source_column": mapping.depth_column,
            "depth_mm_unit": self.unit,
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
            "unit": self.unit,
            "width_column": mapping.width_column,
            "width_mm": self.width_value,
            "width_mm_source_column": mapping.width_column,
            "width_mm_unit": self.unit,
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
        if not self.code:
            raise ValueError("LiveGeometryProbeDiagnostic.code is required")
        if not self.message:
            raise ValueError("LiveGeometryProbeDiagnostic.message is required")

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
    mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING

    def __init__(
        self,
        *,
        assignment_rows: Sequence[Mapping[str, object]],
        property_rows: Sequence[Mapping[str, object]],
        mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    ) -> None:
        object.__setattr__(self, "assignment_rows", tuple(dict(row) for row in assignment_rows))
        object.__setattr__(self, "property_rows", tuple(dict(row) for row in property_rows))
        object.__setattr__(self, "mapping", mapping)

    def iter_geometry_rows(self) -> Sequence[Mapping[str, object]]:
        rows, _diagnostics = resolve_geometry_rows_from_accepted_mapping(
            assignment_rows=self.assignment_rows,
            property_rows=self.property_rows,
            mapping=self.mapping,
        )
        return rows

    def iter_geometry_diagnostics(self) -> Sequence[LiveGeometryProbeDiagnostic]:
        _rows, diagnostics = resolve_geometry_rows_from_accepted_mapping(
            assignment_rows=self.assignment_rows,
            property_rows=self.property_rows,
            mapping=self.mapping,
        )
        return diagnostics

    def live_geometry_probe_summary_fields(self) -> Mapping[str, object]:
        rows, _diagnostics = resolve_geometry_rows_from_accepted_mapping(
            assignment_rows=self.assignment_rows,
            property_rows=self.property_rows,
            mapping=self.mapping,
        )
        return {
            "assignment_table_row_count": len(self.assignment_rows),
            "property_table_row_count": len(self.property_rows),
            "resolved_geometry_row_count": len(rows),
        }


def probe_geometry_feature_snapshots(
    *,
    provider: GeometryRowProvider,
    output_dir: Path,
    target_story: str | None = None,
    target_label: str | None = None,
    target_component: str | None = None,
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> LiveGeometryProbeResult:
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")

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
        snapshot, row_diagnostics = _snapshot_from_row(row)
        diagnostics.extend(row_diagnostics)
        if snapshot is not None:
            snapshots.append(snapshot)

    if truncation_applied:
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="WARNING",
                code="ROW_LIMIT_TRUNCATED",
                message=f"Probe row selection was capped at max_rows={max_rows}",
            )
        )
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
            "diagnostic_count": len(diagnostics),
            "feature_status_counts": _feature_status_counts(snapshots),
            "max_rows": max_rows,
            "property_table_row_count": _int_summary_value(provider_summary.get("property_table_row_count"), default=0),
            "resolved_geometry_row_count": _int_summary_value(provider_summary.get("resolved_geometry_row_count"), default=len(rows)),
            "selected_row_count": len(selected_rows),
            "snapshot_count": len(snapshots),
            "status": status,
            "truncation_applied": truncation_applied,
        },
    )
    _write_json(
        manifest_path,
        {
            "accepted_geometry_mapping": DEFAULT_ACCEPTED_GEOMETRY_MAPPING.as_dict(),
            "forbidden_scope": list(_FORBIDDEN_SCOPE),
            "live_etabs_required_for_ci": False,
            "output_files": list(_OUTPUT_FILES),
            "probe_is_read_only": True,
            "runner": _RUNNER,
            "scope": _PROBE_SCOPE,
            "selectors": {
                "target_component": target_component,
                "target_label": target_label,
                "target_story": target_story,
            },
        },
    )

    return LiveGeometryProbeResult(
        status=status,
        output_dir=out_dir,
        feature_snapshot_path=feature_snapshot_path,
        summary_path=summary_path,
        diagnostics_path=diagnostics_path,
        manifest_path=manifest_path,
        snapshot_count=len(snapshots),
        diagnostic_count=len(diagnostics),
    )


def write_com_attach_failure_probe_outputs(
    *,
    output_dir: Path,
    attach_result: EtabsAttachResult,
) -> LiveGeometryProbeResult:
    out_dir = Path(output_dir)
    feature_snapshot_path = out_dir / "feature_snapshot.json"
    summary_path = out_dir / "live_geometry_probe_summary.json"
    diagnostics_path = out_dir / "live_geometry_probe_diagnostics.json"
    manifest_path = out_dir / "live_geometry_probe_manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    if feature_snapshot_path.exists():
        feature_snapshot_path.unlink()

    attempts = [attempt.as_dict() for attempt in attach_result.attempts]
    diagnostics_payload = [
        {
            "attempts": attempts,
            "code": "ETABS_COM_ATTACH_FAILED",
            "message": "No attach strategy succeeded.",
            "status": "BLOCKED",
        }
    ]
    _write_json(
        summary_path,
        {
            "assignment_table_row_count": 0,
            "diagnostic_count": len(attempts),
            "failure_stage": "COM_ATTACH",
            "feature_snapshot_written": False,
            "property_table_row_count": 0,
            "resolved_geometry_row_count": 0,
            "scope": _ATTACH_FAILURE_SCOPE,
            "status": "FAIL",
        },
    )
    _write_json(diagnostics_path, diagnostics_payload)
    _write_json(
        manifest_path,
        {
            "attach_attempt_count": len(attempts),
            "attach_strategies": list(ATTACH_STRATEGIES),
            "failure_stage": "COM_ATTACH",
            "feature_snapshot_written": False,
            "forbidden_scope": list(_FORBIDDEN_SCOPE),
            "live_etabs_required_for_ci": False,
            "output_files": list(_ATTACH_FAILURE_OUTPUT_FILES),
            "probe_is_read_only": True,
            "runner": _ATTACH_FAILURE_RUNNER,
            "scope": _ATTACH_FAILURE_SCOPE,
        },
    )
    return LiveGeometryProbeResult(
        status="FAIL",
        output_dir=out_dir,
        feature_snapshot_path=feature_snapshot_path,
        summary_path=summary_path,
        diagnostics_path=diagnostics_path,
        manifest_path=manifest_path,
        snapshot_count=0,
        diagnostic_count=len(attempts),
    )


def load_mapping_provider_from_json(path: Path) -> MappingGeometryRowProvider:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("Fake geometry provider fixture must be a row list or an object with a rows list")
    normalized_rows: list[Mapping[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"Fake geometry provider row at index {index} must be an object")
        normalized_rows.append(row)
    return MappingGeometryRowProvider(normalized_rows)


def load_accepted_mapping_provider_from_json(
    *,
    assignment_rows_path: Path,
    property_rows_path: Path,
    mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
) -> AcceptedMappingGeometryRowProvider:
    return AcceptedMappingGeometryRowProvider(
        assignment_rows=_load_rows_json(assignment_rows_path, field_name="assignment_rows"),
        property_rows=_load_rows_json(property_rows_path, field_name="property_rows"),
        mapping=mapping,
    )


def create_live_etabs_geometry_provider(
    *,
    max_candidate_tables: int = 5,
    attach_result: EtabsAttachResult | None = None,
) -> GeometryRowProvider:
    """Create a live provider inside the optional ETABS boundary."""
    return _EtabsComGeometryProvider(
        max_candidate_tables=max_candidate_tables,
        attach_result=attach_result,
        mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    )


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
            raise RuntimeError("ETABS attach succeeded without SapModel; this violates the attach boundary contract")
        database_tables = sap_model.DatabaseTables
        assignment_result = read_live_etabs_table_for_geometry(database_tables, self.mapping.assignment_table_key)
        property_result = read_live_etabs_table_for_geometry(database_tables, self.mapping.property_table_key)
        diagnostics = _table_read_diagnostics(table_role="ASSIGNMENT", result=assignment_result) + _table_read_diagnostics(
            table_role="PROPERTY",
            result=property_result,
        )
        summary = {
            "assignment_table_read_status": assignment_result.status,
            "assignment_table_row_count": assignment_result.row_count,
            "property_table_read_status": property_result.status,
            "property_table_row_count": property_result.row_count,
        }
        if diagnostics:
            return (), diagnostics, {**summary, "resolved_geometry_row_count": 0}
        rows, resolver_diagnostics = resolve_geometry_rows_from_accepted_mapping(
            assignment_rows=assignment_result.rows,
            property_rows=property_result.rows,
            mapping=self.mapping,
        )
        return rows, resolver_diagnostics, {**summary, "resolved_geometry_row_count": len(rows)}


def resolve_geometry_rows_from_accepted_mapping(
    *,
    assignment_rows: Sequence[Mapping[str, object]],
    property_rows: Sequence[Mapping[str, object]],
    mapping: AcceptedGeometryMapping | None = DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
) -> tuple[tuple[Mapping[str, object], ...], tuple[LiveGeometryProbeDiagnostic, ...]]:
    diagnostics: list[LiveGeometryProbeDiagnostic] = []
    if mapping is None:
        return (), (
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="ACCEPTED_GEOMETRY_MAPPING_MISSING",
                message="Accepted geometry mapping is missing; no geometry values were guessed",
            ),
        )
    assignment_tuple = tuple(dict(row) for row in assignment_rows)
    property_tuple = tuple(dict(row) for row in property_rows)
    if not assignment_tuple:
        return (), (
            LiveGeometryProbeDiagnostic(
                status="NO_DATA",
                code="ASSIGNMENT_TABLE_MISSING_OR_EMPTY",
                message="Assignment table rows are missing; no geometry values were guessed",
                source_table=mapping.assignment_table_key,
            ),
        )
    if not property_tuple:
        return (), (
            LiveGeometryProbeDiagnostic(
                status="NO_DATA",
                code="PROPERTY_TABLE_MISSING_OR_EMPTY",
                message="Property definition table rows are missing; no geometry values were guessed",
                source_table=mapping.property_table_key,
            ),
        )
    required_assignment_columns = ("Story", "Label", "UniqueName", mapping.assignment_section_column)
    missing_assignment_columns = _missing_columns(assignment_tuple, required_assignment_columns)
    if missing_assignment_columns:
        return (), (
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="ASSIGNMENT_TABLE_REQUIRED_COLUMN_MISSING",
                message=f"Assignment table is missing required columns: {', '.join(missing_assignment_columns)}",
                source_table=mapping.assignment_table_key,
            ),
        )
    required_property_columns = (mapping.property_name_column, mapping.width_column, mapping.depth_column)
    missing_property_columns = _missing_columns(property_tuple, required_property_columns)
    if missing_property_columns:
        return (), (
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="PROPERTY_TABLE_REQUIRED_COLUMN_MISSING",
                message=f"Property definition table is missing required columns: {', '.join(missing_property_columns)}",
                source_table=mapping.property_table_key,
            ),
        )

    properties_by_section = _index_property_rows(property_tuple, mapping=mapping)
    resolved_rows: list[Mapping[str, object]] = []
    for assignment_row in assignment_tuple:
        assignment = _assignment_from_row(assignment_row, mapping=mapping, diagnostics=diagnostics)
        if assignment is None:
            continue
        property_row = properties_by_section.get(assignment.section_name)
        if property_row is None:
            diagnostics.append(
                LiveGeometryProbeDiagnostic(
                    status="NO_DATA",
                    code="SECTION_PROPERTY_NOT_FOUND",
                    message="Assignment section property was not found in accepted property definition table",
                    component_id=assignment.unique_name,
                    component_type=assignment.component_type,
                    source_table=mapping.property_table_key,
                )
            )
            continue
        property_value = _property_from_row(property_row, mapping=mapping, diagnostics=diagnostics, assignment=assignment)
        if property_value is None:
            continue
        resolved = LiveGeometryResolvedRow(
            story=assignment.story,
            label=assignment.label,
            unique_name=assignment.unique_name,
            section_name=assignment.section_name,
            width_value=property_value.width_value,
            depth_value=property_value.depth_value,
            assignment_table=assignment.source_table,
            property_table=property_value.source_table,
            component_type=assignment.component_type,
            unit=property_value.unit,
        )
        resolved_rows.append(
            resolved.as_feature_row(
                mapping=mapping,
                assignment_row=assignment.raw_row,
                property_row=property_value.raw_row,
            )
        )
    return tuple(resolved_rows), tuple(diagnostics)


def read_live_etabs_table_for_geometry(database_tables: object, table_key: str) -> LiveEtabsTableReadResult:
    try:  # pragma: no cover - live ETABS boundary.
        raw_result = database_tables.GetTableForDisplayArray(table_key, [], "", 0, [], 0, [])
    except Exception as exc:
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="FAILED",
            columns=(),
            row_count=0,
            rows=(),
            raw_metadata={"exception_type": type(exc).__name__},
            message=str(exc) or repr(exc),
        )
    return _table_read_result_from_raw(table_key=table_key, raw_result=raw_result)


def _table_read_result_from_raw(*, table_key: str, raw_result: object) -> LiveEtabsTableReadResult:
    metadata = _raw_table_metadata(raw_result)
    if isinstance(raw_result, Mapping):
        return _table_read_result_from_mapping(table_key=table_key, raw_result=raw_result, metadata=metadata)
    if not isinstance(raw_result, Sequence) or isinstance(raw_result, (str, bytes, bytearray)):
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="PARSE_EMPTY",
            columns=(),
            row_count=0,
            rows=(),
            raw_metadata=metadata,
            message="ETABS display array result was not a supported sequence or mapping shape",
        )
    sequences = tuple(item for item in raw_result if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)))
    string_sequences = tuple(tuple(str(value) for value in item) for item in sequences if all(isinstance(value, str) for value in item))
    columns = _select_column_sequence(table_key=table_key, string_sequences=string_sequences)
    if not columns:
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="PARSE_EMPTY",
            columns=(),
            row_count=0,
            rows=(),
            raw_metadata=metadata,
            message="No ETABS display-array field column sequence could be identified",
        )
    data_candidate = _select_flat_data_sequence(columns=columns, sequences=sequences)
    if data_candidate is None:
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="EMPTY" if _raw_result_declares_zero_rows(raw_result) else "PARSE_EMPTY",
            columns=columns,
            row_count=0,
            rows=(),
            raw_metadata={**metadata, "columns": list(columns)},
            message="No flat data sequence could be identified after the field column sequence",
        )
    if len(data_candidate) == 0:
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="EMPTY",
            columns=columns,
            row_count=0,
            rows=(),
            raw_metadata={**metadata, "columns": list(columns), "flat_data_length": 0},
            message="ETABS returned a field list and zero data values",
        )
    if len(data_candidate) % len(columns) != 0:
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="PARSE_EMPTY",
            columns=columns,
            row_count=0,
            rows=(),
            raw_metadata={**metadata, "columns": list(columns), "flat_data_length": len(data_candidate)},
            message="Flat data length is not divisible by field column count",
        )
    rows = _rows_from_flat_data(table_key=table_key, columns=columns, flat_data=data_candidate)
    if not rows:
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="PARSE_EMPTY",
            columns=columns,
            row_count=0,
            rows=(),
            raw_metadata={**metadata, "columns": list(columns), "flat_data_length": len(data_candidate)},
            message="Flat data sequence could not be decoded into rows",
        )
    return LiveEtabsTableReadResult(
        table_key=table_key,
        status="FETCHED",
        columns=columns,
        row_count=len(rows),
        rows=tuple(rows),
        raw_metadata={**metadata, "columns": list(columns), "flat_data_length": len(data_candidate)},
    )


def _table_read_result_from_mapping(*, table_key: str, raw_result: Mapping[object, object], metadata: Mapping[str, object]) -> LiveEtabsTableReadResult:
    raw_columns = raw_result.get("columns") or raw_result.get("fields") or raw_result.get("field_names") or ()
    if not isinstance(raw_columns, Sequence) or isinstance(raw_columns, (str, bytes, bytearray)):
        return LiveEtabsTableReadResult(
            table_key=table_key,
            status="PARSE_EMPTY",
            columns=(),
            row_count=0,
            rows=(),
            raw_metadata=metadata,
            message="Mapping table result did not contain a supported columns sequence",
        )
    columns = tuple(str(column) for column in raw_columns)
    raw_rows = raw_result.get("rows")
    if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes, bytearray)):
        if not raw_rows:
            return LiveEtabsTableReadResult(table_key=table_key, status="EMPTY", columns=columns, row_count=0, rows=(), raw_metadata=metadata)
        rows: list[Mapping[str, object]] = []
        for item in raw_rows:
            if isinstance(item, Mapping):
                row = {str(key): value for key, value in item.items()}
                row.setdefault("source_table", table_key)
                row.setdefault("actual_table_name", table_key)
                rows.append(row)
        if rows:
            return LiveEtabsTableReadResult(table_key=table_key, status="FETCHED", columns=columns, row_count=len(rows), rows=tuple(rows), raw_metadata=metadata)
        return LiveEtabsTableReadResult(table_key=table_key, status="PARSE_EMPTY", columns=columns, row_count=0, rows=(), raw_metadata=metadata)
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
) -> LiveGeometryAssignmentRow | None:
    story = _text(row.get("Story"))
    label = _text(row.get("Label"))
    unique_name = _text(row.get("UniqueName"))
    section_name = _text(row.get(mapping.assignment_section_column))
    component_type = _component_type_from_assignment_row(row)
    if not component_type:
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="COMPONENT_TYPE_NOT_EXPLICIT",
                message="Assignment row does not include explicit beam/column component type; no label-based guess was made",
                component_id=unique_name or None,
                source_table=mapping.assignment_table_key,
            )
        )
        return None
    if not (story and label and unique_name and section_name):
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="ASSIGNMENT_ROW_IDENTITY_INCOMPLETE",
                message="Assignment row identity or section property is incomplete; no geometry value was guessed",
                component_id=unique_name or None,
                component_type=component_type,
                source_table=mapping.assignment_table_key,
            )
        )
        return None
    return LiveGeometryAssignmentRow(
        story=story,
        label=label,
        unique_name=unique_name,
        section_name=section_name,
        source_table=mapping.assignment_table_key,
        component_type=component_type,
        raw_row=row,
    )


def _property_from_row(
    row: Mapping[str, object],
    *,
    mapping: AcceptedGeometryMapping,
    diagnostics: list[LiveGeometryProbeDiagnostic],
    assignment: LiveGeometryAssignmentRow,
) -> LiveGeometryPropertyRow | None:
    width_value = row.get(mapping.width_column)
    depth_value = row.get(mapping.depth_column)
    if width_value is None or depth_value is None:
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="NO_DATA",
                code="GEOMETRY_DIMENSION_VALUE_MISSING",
                message="Accepted property row is missing t2/t3 value; no geometry value was guessed",
                component_id=assignment.unique_name,
                component_type=assignment.component_type,
                source_table=mapping.property_table_key,
            )
        )
        return None
    if not _is_numeric(width_value) or not _is_numeric(depth_value):
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="GEOMETRY_DIMENSION_VALUE_NOT_NUMERIC",
                message="Accepted property row t2/t3 value is not numeric",
                component_id=assignment.unique_name,
                component_type=assignment.component_type,
                source_table=mapping.property_table_key,
            )
        )
        return None
    unit = _unit_from_property_row(row, mapping=mapping)
    if unit != _REQUIRED_UNIT:
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="GEOMETRY_UNIT_NOT_PROVEN_MM",
                message="Accepted property row unit is not proven to be mm; no conversion was performed",
                component_id=assignment.unique_name,
                component_type=assignment.component_type,
                source_table=mapping.property_table_key,
            )
        )
        return None
    return LiveGeometryPropertyRow(
        section_name=_text(row.get(mapping.property_name_column)),
        width_value=width_value,
        depth_value=depth_value,
        source_table=mapping.property_table_key,
        unit=unit,
        raw_row=row,
    )


def _table_read_diagnostics(*, table_role: str, result: LiveEtabsTableReadResult) -> tuple[LiveGeometryProbeDiagnostic, ...]:
    role = table_role.upper()
    if result.status == "FETCHED":
        return ()
    if result.status == "FAILED":
        return (
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code=f"{role}_TABLE_FETCH_FAILED",
                message=result.message or f"{role.title()} table fetch failed",
                source_table=result.table_key,
            ),
        )
    if result.status == "EMPTY":
        return (
            LiveGeometryProbeDiagnostic(
                status="NO_DATA",
                code=f"{role}_TABLE_FETCHED_ZERO_ROWS",
                message=f"{role.title()} table was fetched but contained zero rows",
                source_table=result.table_key,
            ),
        )
    if result.status == "PARSE_EMPTY":
        return (
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code=f"{role}_TABLE_PARSE_EMPTY",
                message=result.message or f"{role.title()} table display array could not be decoded into rows",
                source_table=result.table_key,
            ),
        )
    return ()


def _index_property_rows(rows: Sequence[Mapping[str, object]], *, mapping: AcceptedGeometryMapping) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        section_name = _text(row.get(mapping.property_name_column))
        if section_name and section_name not in indexed:
            indexed[section_name] = row
    return indexed


def _missing_columns(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> tuple[str, ...]:
    available = {str(key) for row in rows for key in row.keys()}
    return tuple(column for column in columns if column not in available)


def _unit_from_property_row(row: Mapping[str, object], *, mapping: AcceptedGeometryMapping) -> str:
    width_unit = _text(row.get(f"{mapping.width_column}_unit"))
    depth_unit = _text(row.get(f"{mapping.depth_column}_unit"))
    if width_unit and depth_unit and width_unit == depth_unit:
        return width_unit
    return _text(row.get("unit"))


def _component_type_from_assignment_row(row: Mapping[str, object]) -> str:
    for column in _COMPONENT_TYPE_COLUMN_CANDIDATES:
        value = _text(row.get(column)).casefold()
        if value in _COMPONENT_TYPE_VALUES:
            return _COMPONENT_TYPE_VALUES[value]
    return ""


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
    return frozenset()


def _looks_like_field_sequence(sequence: Sequence[str]) -> bool:
    if not sequence:
        return False
    known = {"Story", "Label", "UniqueName", "Shape", "AutoSelect", "SectProp", "Name", "t2", "t3"}
    return bool(set(sequence).intersection(known))


def _raw_result_declares_zero_rows(raw_result: Sequence[object]) -> bool:
    return any(isinstance(item, int) and not isinstance(item, bool) and item == 0 for item in raw_result)


def _raw_table_metadata(raw_result: object) -> dict[str, object]:
    if isinstance(raw_result, Mapping):
        return {
            "raw_type": type(raw_result).__name__,
            "mapping_keys": [str(key) for key in sorted(raw_result.keys(), key=str)],
        }
    if isinstance(raw_result, Sequence) and not isinstance(raw_result, (str, bytes, bytearray)):
        return {
            "raw_sequence_length": len(raw_result),
            "raw_type": type(raw_result).__name__,
            "sequence_item_types": [type(item).__name__ for item in raw_result],
        }
    return {"raw_type": type(raw_result).__name__}


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _select_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    target_story: str | None,
    target_label: str | None,
    target_component: str | None,
    max_rows: int,
) -> tuple[tuple[Mapping[str, object], ...], bool]:
    selected: list[Mapping[str, object]] = []
    for row in rows:
        if target_story is not None and str(row.get("story", "")) != target_story:
            continue
        if target_label is not None and str(row.get("label", "")) != target_label:
            continue
        if target_component is not None and str(row.get("component_id", "")) != target_component:
            continue
        selected.append(row)
    truncation_applied = len(selected) > max_rows
    return tuple(selected[:max_rows]), truncation_applied


def _snapshot_from_row(row: Mapping[str, object]) -> tuple[FeatureSnapshot | None, tuple[LiveGeometryProbeDiagnostic, ...]]:
    diagnostics: list[LiveGeometryProbeDiagnostic] = []
    component_type = _text(row.get("component_type")).casefold()
    component_id = _text(row.get("component_id"))
    if component_type not in _FEATURES_BY_COMPONENT_TYPE:
        return None, (
            LiveGeometryProbeDiagnostic(
                status="WARNING",
                code="COMPONENT_TYPE_OUT_OF_SCOPE",
                message="Only beam and column geometry rows are supported",
                component_id=component_id or None,
                component_type=component_type or None,
                source_table=_text_or_none(row.get("source_table")),
            ),
        )
    if not component_id:
        return None, (
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="COMPONENT_ID_MISSING",
                message="Geometry row does not include component_id",
                component_type=component_type,
                source_table=_text_or_none(row.get("source_table")),
            ),
        )

    width_feature, depth_feature = _FEATURES_BY_COMPONENT_TYPE[component_type]
    features: dict[str, FeatureValue] = {}
    features[width_feature] = _feature_from_dimension_row(
        row,
        component_id=component_id,
        component_type=component_type,
        feature_id=width_feature,
        value_keys=_WIDTH_KEYS,
        diagnostics=diagnostics,
    )
    features[depth_feature] = _feature_from_dimension_row(
        row,
        component_id=component_id,
        component_type=component_type,
        feature_id=depth_feature,
        value_keys=_DEPTH_KEYS,
        diagnostics=diagnostics,
    )
    identity = {key: row.get(key) for key in _IDENTITY_KEYS if row.get(key) is not None}
    return (
        FeatureSnapshot(
            component_type=component_type,
            component_id=component_id,
            identity=identity,
            features=features,
        ),
        tuple(diagnostics),
    )


def _feature_from_dimension_row(
    row: Mapping[str, object],
    *,
    component_id: str,
    component_type: str,
    feature_id: str,
    value_keys: Sequence[str],
    diagnostics: list[LiveGeometryProbeDiagnostic],
) -> FeatureValue:
    source_table = _text_or_none(row.get("source_table")) or "live_geometry_provider"
    source_column, raw_value = _first_present(row, value_keys)
    unit = _text(row.get(f"{source_column}_unit")) if source_column else ""
    if not unit:
        unit = _text(row.get("unit"))
    if source_column is None or raw_value is None:
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="NO_DATA",
                code="GEOMETRY_FEATURE_MISSING",
                message="Required observed geometry feature is missing; no value was guessed",
                component_id=component_id,
                component_type=component_type,
                feature_id=feature_id,
                source_table=source_table,
            )
        )
        return FeatureValue(
            feature_name=feature_id,
            value=None,
            unit=unit,
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.MISSING,
            evidence=(),
        )
    if unit != _REQUIRED_UNIT:
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="GEOMETRY_UNIT_NOT_MM",
                message="Observed geometry unit is not proven to be mm; no conversion was performed",
                component_id=component_id,
                component_type=component_type,
                feature_id=feature_id,
                source_table=source_table,
            )
        )
        return FeatureValue(
            feature_name=feature_id,
            value=None,
            unit=unit,
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.PARTIAL,
            evidence=(),
        )
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        diagnostics.append(
            LiveGeometryProbeDiagnostic(
                status="BLOCKED",
                code="GEOMETRY_VALUE_NOT_NUMERIC",
                message="Observed geometry value is not numeric",
                component_id=component_id,
                component_type=component_type,
                feature_id=feature_id,
                source_table=source_table,
            )
        )
        return FeatureValue(
            feature_name=feature_id,
            value=None,
            unit=unit,
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.PARTIAL,
            evidence=(),
        )

    value = float(raw_value)
    evidence_source_column = _text_or_none(row.get(f"{source_column}_source_column")) or source_column
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=source_table,
        actual_table_name=_text_or_none(row.get("actual_table_name")) or source_table,
        source_column=evidence_source_column,
        source_row={key: _json_safe(value) for key, value in sorted(row.items())},
        raw_value=raw_value,
        normalized_value=value,
        unit=unit,
        resolver="c13_5_p5_accepted_geometry_mapping_probe",
    )
    return FeatureValue(
        feature_name=feature_id,
        value=value,
        unit=unit,
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )


def _provider_diagnostics(provider: GeometryRowProvider) -> tuple[LiveGeometryProbeDiagnostic, ...]:
    diagnostic_reader = getattr(provider, "iter_geometry_diagnostics", None)
    if not callable(diagnostic_reader):
        return ()
    diagnostics = diagnostic_reader()
    return tuple(diagnostic for diagnostic in diagnostics if isinstance(diagnostic, LiveGeometryProbeDiagnostic))


def _provider_summary_fields(provider: GeometryRowProvider, *, resolved_row_count: int) -> Mapping[str, object]:
    summary_reader = getattr(provider, "live_geometry_probe_summary_fields", None)
    if not callable(summary_reader):
        return {
            "assignment_table_row_count": 0,
            "property_table_row_count": 0,
            "resolved_geometry_row_count": resolved_row_count,
        }
    summary = summary_reader()
    if not isinstance(summary, Mapping):
        return {
            "assignment_table_row_count": 0,
            "property_table_row_count": 0,
            "resolved_geometry_row_count": resolved_row_count,
        }
    return dict(summary)


def _first_present(row: Mapping[str, object], keys: Sequence[str]) -> tuple[str | None, object | None]:
    for key in keys:
        if key in row:
            return key, row[key]
    return None, None


def _load_rows_json(path: Path, *, field_name: str) -> tuple[Mapping[str, object], ...]:
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
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


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
    "GeometryRowProvider",
    "LiveEtabsTableReadResult",
    "LiveGeometryAssignmentRow",
    "LiveGeometryProbeDiagnostic",
    "LiveGeometryProbeResult",
    "LiveGeometryPropertyRow",
    "LiveGeometryResolvedRow",
    "MappingGeometryRowProvider",
    "create_live_etabs_geometry_provider",
    "load_accepted_mapping_provider_from_json",
    "load_mapping_provider_from_json",
    "probe_geometry_feature_snapshots",
    "read_live_etabs_table_for_geometry",
    "resolve_geometry_rows_from_accepted_mapping",
    "write_com_attach_failure_probe_outputs",
]
