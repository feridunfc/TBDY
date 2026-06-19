"""C13.5-P2/C13.5-P3 read-only geometry FeatureSnapshot probe.

This module creates FeatureSnapshot JSON from observed geometry rows only. Live
ETABS access is optional and isolated behind explicit runtime boundaries. C13.5-P3
keeps COM attachment in tbdy_engine.features.etabs_com_attach.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
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

_PROBE_SCOPE = "C13_5_P2_LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE"
_ATTACH_FAILURE_SCOPE = "LIVE_ETABS_GEOMETRY_FEATURE_SNAPSHOT_PROBE"
_RUNNER = "C13.5-P2 Live ETABS Read-Only Geometry FeatureSnapshot Probe"
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
_IDENTITY_KEYS = ("label", "story", "section")


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
    diagnostics: list[LiveGeometryProbeDiagnostic] = []

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
            "candidate_row_count": len(rows),
            "diagnostic_count": len(diagnostics),
            "feature_status_counts": _feature_status_counts(snapshots),
            "max_rows": max_rows,
            "selected_row_count": len(selected_rows),
            "snapshot_count": len(snapshots),
            "status": status,
            "truncation_applied": truncation_applied,
        },
    )
    _write_json(
        manifest_path,
        {
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
            "diagnostic_count": len(attempts),
            "failure_stage": "COM_ATTACH",
            "feature_snapshot_written": False,
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


def create_live_etabs_geometry_provider(
    *,
    max_candidate_tables: int = 5,
    attach_result: EtabsAttachResult | None = None,
) -> GeometryRowProvider:
    """Create a live provider inside the optional ETABS boundary."""
    return _EtabsComGeometryProvider(
        max_candidate_tables=max_candidate_tables,
        attach_result=attach_result,
    )


@dataclass(frozen=True, slots=True)
class _EtabsComGeometryProvider:
    max_candidate_tables: int = 5
    attach_result: EtabsAttachResult | None = None

    def iter_geometry_rows(self) -> Sequence[Mapping[str, object]]:
        if self.max_candidate_tables <= 0:
            raise ValueError("max_candidate_tables must be positive")
        attach_result = self.attach_result or attach_to_running_etabs()
        if attach_result.status != "ATTACHED":
            raise EtabsAttachFailure(attach_result)
        sap_model = attach_result.sap_model
        if sap_model is None:
            raise RuntimeError("ETABS attach succeeded without SapModel; this violates the attach boundary contract")
        database_tables = sap_model.DatabaseTables
        table_names = _candidate_live_table_names(database_tables, self.max_candidate_tables)
        rows: list[Mapping[str, object]] = []
        for table_name in table_names:
            rows.extend(_read_live_table_rows(database_tables, table_name))
        return rows


def _candidate_live_table_names(database_tables: object, max_candidate_tables: int) -> tuple[str, ...]:
    preferred = (
        "Frame Assignments - Summary",
        "Frame Section Assignments",
        "Frame Section Property Definitions - Concrete Rectangular",
        "Frame Section Property Definitions - Concrete Rectangular Columns",
        "Frame Section Property Definitions - Concrete Rectangular Beams",
    )
    return preferred[:max_candidate_tables]


def _read_live_table_rows(database_tables: object, table_name: str) -> list[Mapping[str, object]]:
    # ETABS table return signatures vary by version. This boundary is intentionally
    # narrow and best-effort; fake providers own CI behavior.
    try:  # pragma: no cover - live ETABS boundary.
        result = database_tables.GetTableForDisplayArray(table_name, [], "", 0, [], 0, [])
    except Exception:
        return []
    if not isinstance(result, tuple) or len(result) < 2:
        return []
    fields = next((item for item in result if isinstance(item, (list, tuple)) and all(isinstance(x, str) for x in item)), ())
    flat_data = next((item for item in reversed(result) if isinstance(item, (list, tuple)) and item and not all(isinstance(x, str) for x in item)), ())
    if not fields or not flat_data:
        return []
    width = len(fields)
    if width <= 0:
        return []
    rows: list[Mapping[str, object]] = []
    for index in range(0, len(flat_data), width):
        values = flat_data[index : index + width]
        if len(values) != width:
            continue
        row = {str(field): values[position] for position, field in enumerate(fields)}
        row.setdefault("source_table", table_name)
        row.setdefault("actual_table_name", table_name)
        rows.append(row)
    return rows


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
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=source_table,
        actual_table_name=_text_or_none(row.get("actual_table_name")) or source_table,
        source_column=source_column,
        source_row={key: _json_safe(value) for key, value in sorted(row.items())},
        raw_value=raw_value,
        normalized_value=value,
        unit=unit,
        resolver="c13_5_p2_live_geometry_probe",
    )
    return FeatureValue(
        feature_name=feature_id,
        value=value,
        unit=unit,
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )


def _first_present(row: Mapping[str, object], keys: Sequence[str]) -> tuple[str | None, object | None]:
    for key in keys:
        if key in row:
            return key, row[key]
    return None, None


def _feature_status_counts(snapshots: Sequence[FeatureSnapshot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for snapshot in snapshots:
        for feature in snapshot.features.values():
            status = feature.status.value
            counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


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
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "GeometryRowProvider",
    "LiveGeometryProbeDiagnostic",
    "LiveGeometryProbeResult",
    "MappingGeometryRowProvider",
    "create_live_etabs_geometry_provider",
    "load_mapping_provider_from_json",
    "probe_geometry_feature_snapshots",
    "write_com_attach_failure_probe_outputs",
]
