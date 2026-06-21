"""C14.0-P1 live concrete-material FeatureSnapshot evidence probe.

The production source is locked to proven ETABS display tables. Direct frame or
material property APIs are outside this production boundary.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import json
import math
import re

from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STRATEGIES,
    EtabsAttachFailure,
    EtabsAttachResult,
    attach_to_running_etabs,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.live_etabs_geometry_probe import (
    DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
    LiveEtabsLengthUnitEvidence,
    LiveGeometryProbeDiagnostic,
    read_live_etabs_length_unit_evidence,
    read_live_etabs_table_for_geometry,
    read_live_frame_component_type_source,
    resolve_geometry_rows_from_accepted_mapping,
)
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

_SCOPE = "C14_0_P1_LIVE_CONCRETE_MATERIAL_FEATURE_EVIDENCE"
_RUNNER = "C14.0-P1 Live Concrete Material Feature Evidence Probe"
_ALLOWED_STATUSES = frozenset({"OK", "PARTIAL", "FAIL"})
_ALLOWED_DIAGNOSTIC_STATUSES = frozenset({"NO_DATA", "BLOCKED", "WARNING"})
_OUTPUT_FILES = (
    "feature_snapshot.json",
    "concrete_material_probe_summary.json",
    "concrete_material_probe_diagnostics.json",
    "concrete_material_probe_manifest.json",
)
_ATTACH_FAILURE_OUTPUT_FILES = _OUTPUT_FILES[1:]
_ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
_SECTION_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
_MATERIAL_TABLE = "Material Properties - Concrete Data"
_COMPONENT_TYPE_TABLE = "Frame Assignments - Summary"
_FEATURE_ID = "concrete_fck_mpa"
_TARGET_STRENGTH_UNIT = "MPa"
_SOURCE_STRESS_UNIT = "kN/m²"
_NORMALIZATION_FACTOR_TO_MPA = 0.001
_NORMALIZATION_BASIS = "EXPLICIT_LIVE_SOURCE_LOCK_FC_KN_PER_M2_TO_MPA"
_NUMERIC_LITERAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_NON_FINITE_TOKENS = frozenset(
    {
        "nan",
        "+nan",
        "-nan",
        "inf",
        "+inf",
        "-inf",
        "infinity",
        "+infinity",
        "-infinity",
    }
)
_GEOMETRY_FEATURES = {
    "beam": ("beam_width_mm", "beam_depth_mm"),
    "column": ("column_width_mm", "column_depth_mm"),
}


@dataclass(frozen=True, slots=True)
class AcceptedConcreteMaterialMapping:
    section_table_key: str
    section_name_column: str
    section_material_column: str
    material_table_key: str
    material_name_column: str
    concrete_strength_column: str
    source_force_unit: str
    source_length_unit: str
    source_stress_unit: str
    target_strength_unit: str
    normalization_factor_to_mpa: float
    mapping_basis: str

    def __post_init__(self) -> None:
        expected = {
            "section_table_key": _SECTION_TABLE,
            "section_name_column": "Name",
            "section_material_column": "Material",
            "material_table_key": _MATERIAL_TABLE,
            "material_name_column": "Material",
            "concrete_strength_column": "Fc",
            "source_force_unit": "kN",
            "source_length_unit": "m",
            "source_stress_unit": _SOURCE_STRESS_UNIT,
            "target_strength_unit": _TARGET_STRENGTH_UNIT,
            "normalization_factor_to_mpa": _NORMALIZATION_FACTOR_TO_MPA,
            "mapping_basis": "explicit_live_source_lock",
        }
        for field_name, expected_value in expected.items():
            if getattr(self, field_name) != expected_value:
                raise ValueError(
                    f"AcceptedConcreteMaterialMapping.{field_name} must equal {expected_value!r}"
                )

    def as_dict(self) -> dict[str, object]:
        return {
            "section_table_key": self.section_table_key,
            "section_name_column": self.section_name_column,
            "section_material_column": self.section_material_column,
            "material_table_key": self.material_table_key,
            "material_name_column": self.material_name_column,
            "concrete_strength_column": self.concrete_strength_column,
            "source_force_unit": self.source_force_unit,
            "source_length_unit": self.source_length_unit,
            "source_stress_unit": self.source_stress_unit,
            "target_strength_unit": self.target_strength_unit,
            "normalization_factor_to_mpa": self.normalization_factor_to_mpa,
            "mapping_basis": self.mapping_basis,
        }


DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING = AcceptedConcreteMaterialMapping(
    section_table_key=_SECTION_TABLE,
    section_name_column="Name",
    section_material_column="Material",
    material_table_key=_MATERIAL_TABLE,
    material_name_column="Material",
    concrete_strength_column="Fc",
    source_force_unit="kN",
    source_length_unit="m",
    source_stress_unit=_SOURCE_STRESS_UNIT,
    target_strength_unit=_TARGET_STRENGTH_UNIT,
    normalization_factor_to_mpa=_NORMALIZATION_FACTOR_TO_MPA,
    mapping_basis="explicit_live_source_lock",
)


@dataclass(frozen=True, slots=True)
class ConcreteMaterialProbeDiagnostic:
    status: str
    code: str
    message: str
    component_id: str | None = None
    component_type: str | None = None
    feature_id: str | None = None
    source_table: str | None = None
    details: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_DIAGNOSTIC_STATUSES:
            raise ValueError("Unsupported concrete-material diagnostic status")
        if not self.code or not self.message:
            raise ValueError("ConcreteMaterialProbeDiagnostic requires code and message")
        object.__setattr__(self, "details", dict(self.details or {}))

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "component_id": self.component_id,
            "component_type": self.component_type,
            "feature_id": self.feature_id,
            "source_table": self.source_table,
            "details": dict(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class ConcreteMaterialProbeInput:
    geometry_rows: tuple[Mapping[str, object], ...]
    section_columns: tuple[str, ...]
    material_rows: tuple[Mapping[str, object], ...]
    material_columns: tuple[str, ...]
    material_table_status: str
    unit_evidence: LiveEtabsLengthUnitEvidence | None
    source_diagnostics: tuple[ConcreteMaterialProbeDiagnostic, ...]

    def __init__(
        self,
        *,
        geometry_rows: Sequence[Mapping[str, object]],
        section_columns: Sequence[str],
        material_rows: Sequence[Mapping[str, object]],
        material_columns: Sequence[str],
        unit_evidence: LiveEtabsLengthUnitEvidence | None,
        material_table_status: str = "FETCHED",
        source_diagnostics: Sequence[ConcreteMaterialProbeDiagnostic] = (),
    ) -> None:
        object.__setattr__(self, "geometry_rows", tuple(dict(row) for row in geometry_rows))
        object.__setattr__(self, "section_columns", tuple(str(value) for value in section_columns))
        object.__setattr__(self, "material_rows", tuple(dict(row) for row in material_rows))
        object.__setattr__(self, "material_columns", tuple(str(value) for value in material_columns))
        object.__setattr__(self, "material_table_status", str(material_table_status))
        object.__setattr__(self, "unit_evidence", unit_evidence)
        object.__setattr__(self, "source_diagnostics", tuple(source_diagnostics))


class ConcreteMaterialProbeProvider(Protocol):
    def read_probe_input(self) -> ConcreteMaterialProbeInput:
        """Read the locked source evidence without mutating ETABS."""


@dataclass(frozen=True, slots=True)
class FixtureConcreteMaterialProbeProvider:
    probe_input: ConcreteMaterialProbeInput

    def read_probe_input(self) -> ConcreteMaterialProbeInput:
        return self.probe_input


@dataclass(frozen=True, slots=True)
class ConcreteMaterialProbeResult:
    status: str
    output_dir: Path
    feature_snapshot_path: Path
    summary_path: Path
    diagnostics_path: Path
    manifest_path: Path
    snapshot_count: int
    diagnostic_count: int

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError("Unsupported concrete-material probe result status")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "feature_snapshot_path", Path(self.feature_snapshot_path))
        object.__setattr__(self, "summary_path", Path(self.summary_path))
        object.__setattr__(self, "diagnostics_path", Path(self.diagnostics_path))
        object.__setattr__(self, "manifest_path", Path(self.manifest_path))


@dataclass(slots=True)
class _ResolutionCounts:
    section_material_resolved_count: int = 0
    material_join_matched_count: int = 0
    material_join_missing_count: int = 0
    material_join_duplicate_count: int = 0
    fc_resolved_count: int = 0
    fc_missing_count: int = 0
    fc_blocked_count: int = 0


@dataclass(frozen=True, slots=True)
class _ResolvedConcreteFeature:
    feature: FeatureValue
    raw_material_name: object


class _LockedMaterialTableAdapter:
    """Expose the exact material table as a mapping to the existing row parser."""

    def __init__(self, database_tables: object) -> None:
        self._database_tables = database_tables

    def GetTableForDisplayArray(self, table_key: str, *args: object) -> object:
        raw_result = self._database_tables.GetTableForDisplayArray(table_key, *args)
        return _locked_material_table_mapping(raw_result)


class _LiveEtabsConcreteMaterialProvider:
    def __init__(
        self,
        *,
        attach_result: EtabsAttachResult | None = None,
        mapping: AcceptedConcreteMaterialMapping = DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING,
    ) -> None:
        self._attach_result = attach_result
        self._mapping = mapping
        self._cached: ConcreteMaterialProbeInput | None = None

    def read_probe_input(self) -> ConcreteMaterialProbeInput:
        if self._cached is None:
            self._cached = self._read_probe_input()
        return self._cached

    def _read_probe_input(self) -> ConcreteMaterialProbeInput:
        attach_result = self._attach_result or attach_to_running_etabs()
        if attach_result.status != "ATTACHED":
            raise EtabsAttachFailure(attach_result)
        sap_model = attach_result.sap_model
        if sap_model is None:
            raise RuntimeError("ETABS attach succeeded without SapModel")

        database_tables = sap_model.DatabaseTables
        assignment_result = read_live_etabs_table_for_geometry(
            database_tables,
            DEFAULT_ACCEPTED_GEOMETRY_MAPPING.assignment_table_key,
        )
        section_result = read_live_etabs_table_for_geometry(
            database_tables,
            self._mapping.section_table_key,
        )
        material_result = read_live_etabs_table_for_geometry(
            _LockedMaterialTableAdapter(database_tables),
            self._mapping.material_table_key,
        )
        component_source = read_live_frame_component_type_source(database_tables)
        unit_evidence, _unit_diagnostics = read_live_etabs_length_unit_evidence(sap_model)

        source_diagnostics = list(
            _source_table_diagnostics(
                role="ASSIGNMENT",
                status=assignment_result.status,
                table_key=assignment_result.table_key,
                message=assignment_result.message,
            )
        )
        source_diagnostics.extend(
            _source_table_diagnostics(
                role="SECTION",
                status=section_result.status,
                table_key=section_result.table_key,
                message=section_result.message,
            )
        )
        source_diagnostics.extend(_convert_geometry_diagnostics(component_source.diagnostics))

        unsupported_component_ids = frozenset(
            diagnostic.component_id
            for diagnostic in component_source.diagnostics
            if diagnostic.code == "COMPONENT_TYPE_VALUE_UNSUPPORTED" and diagnostic.component_id
        )
        geometry_rows: tuple[Mapping[str, object], ...] = ()
        if (
            assignment_result.status == "FETCHED"
            and section_result.status == "FETCHED"
            and component_source.status == "FETCHED"
            and component_source.evidence_by_unique_name
        ):
            need_length_evidence = any(
                isinstance(row.get(DEFAULT_ACCEPTED_GEOMETRY_MAPPING.width_column), str)
                or isinstance(row.get(DEFAULT_ACCEPTED_GEOMETRY_MAPPING.depth_column), str)
                for row in section_result.rows
            )
            geometry_rows, geometry_diagnostics = resolve_geometry_rows_from_accepted_mapping(
                assignment_rows=assignment_result.rows,
                property_rows=section_result.rows,
                mapping=DEFAULT_ACCEPTED_GEOMETRY_MAPPING,
                component_type_evidence_by_unique_name=component_source.evidence_by_unique_name,
                component_type_unsupported_unique_names=unsupported_component_ids,
                length_unit_evidence=unit_evidence,
                require_length_unit_evidence=need_length_evidence,
            )
            source_diagnostics.extend(_convert_geometry_diagnostics(geometry_diagnostics))

        return ConcreteMaterialProbeInput(
            geometry_rows=geometry_rows,
            section_columns=section_result.columns,
            material_rows=material_result.rows,
            material_columns=material_result.columns,
            material_table_status=material_result.status,
            unit_evidence=unit_evidence,
            source_diagnostics=source_diagnostics,
        )


def create_live_etabs_concrete_material_provider(
    *,
    attach_result: EtabsAttachResult | None = None,
) -> ConcreteMaterialProbeProvider:
    return _LiveEtabsConcreteMaterialProvider(attach_result=attach_result)


def probe_concrete_material_feature_snapshots(
    *,
    provider: ConcreteMaterialProbeProvider,
    output_dir: Path,
    target_story: str | None = None,
    target_label: str | None = None,
    target_component: str | None = None,
    max_rows: int = 20,
    mapping: AcceptedConcreteMaterialMapping = DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING,
) -> ConcreteMaterialProbeResult:
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")

    out_dir = Path(output_dir)
    _prepare_owned_output_files(out_dir)
    feature_snapshot_path = out_dir / _OUTPUT_FILES[0]
    summary_path = out_dir / _OUTPUT_FILES[1]
    diagnostics_path = out_dir / _OUTPUT_FILES[2]
    manifest_path = out_dir / _OUTPUT_FILES[3]

    probe_input = provider.read_probe_input()
    candidate_rows = tuple(probe_input.geometry_rows)
    selected_rows, truncation_applied = _select_rows(
        candidate_rows,
        target_story=target_story,
        target_label=target_label,
        target_component=target_component,
        max_rows=max_rows,
    )
    diagnostics = list(probe_input.source_diagnostics)
    counts = _ResolutionCounts()
    snapshots: list[FeatureSnapshot] = []

    schema_blocked = _validate_locked_source_schema(
        probe_input=probe_input,
        mapping=mapping,
        diagnostics=diagnostics,
    )
    unit_blocked = False
    if not schema_blocked:
        unit_blocked = _validate_material_units(
            unit_evidence=probe_input.unit_evidence,
            mapping=mapping,
            diagnostics=diagnostics,
        )

    if not schema_blocked and not unit_blocked:
        for row in selected_rows:
            resolved = _resolve_concrete_feature(
                geometry_row=row,
                material_rows=probe_input.material_rows,
                unit_evidence=probe_input.unit_evidence,
                mapping=mapping,
                diagnostics=diagnostics,
                counts=counts,
            )
            if resolved is not None:
                snapshots.append(
                    _snapshot_from_resolved_row(
                        geometry_row=row,
                        concrete_feature=resolved.feature,
                        raw_material_name=resolved.raw_material_name,
                    )
                )
    elif selected_rows:
        counts.fc_blocked_count += len(selected_rows)

    if truncation_applied:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="WARNING",
                code="ROW_LIMIT_TRUNCATED",
                message=f"Probe row selection was capped at max_rows={max_rows}",
            )
        )

    status = "FAIL" if not snapshots else ("PARTIAL" if diagnostics else "OK")
    source_force_unit = (
        probe_input.unit_evidence.present_force_unit
        if probe_input.unit_evidence is not None
        else None
    )
    source_length_unit = (
        probe_input.unit_evidence.present_length_unit
        if probe_input.unit_evidence is not None
        else None
    )
    source_stress_unit = (
        _stress_unit(source_force_unit, source_length_unit)
        if source_force_unit and source_length_unit
        else None
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(feature_snapshot_path, {"snapshots": [item.as_dict() for item in snapshots]})
    _write_json(diagnostics_path, [item.as_dict() for item in diagnostics])
    _write_json(
        summary_path,
        {
            "status": status,
            "candidate_row_count": len(candidate_rows),
            "selected_row_count": len(selected_rows),
            "snapshot_count": len(snapshots),
            "diagnostic_count": len(diagnostics),
            "material_definition_row_count": len(probe_input.material_rows),
            "section_material_resolved_count": counts.section_material_resolved_count,
            "material_join_matched_count": counts.material_join_matched_count,
            "material_join_missing_count": counts.material_join_missing_count,
            "material_join_duplicate_count": counts.material_join_duplicate_count,
            "fc_resolved_count": counts.fc_resolved_count,
            "fc_missing_count": counts.fc_missing_count,
            "fc_blocked_count": counts.fc_blocked_count,
            "feature_status_counts": _feature_status_counts(snapshots),
            "source_force_unit": source_force_unit,
            "source_length_unit": source_length_unit,
            "source_stress_unit": source_stress_unit,
            "target_strength_unit": mapping.target_strength_unit,
            "normalization_factor_to_mpa": mapping.normalization_factor_to_mpa,
            "truncation_applied": truncation_applied,
        },
    )
    _write_json(
        manifest_path,
        {
            "scope": _SCOPE,
            "runner": _RUNNER,
            "probe_is_read_only": True,
            "live_etabs_required_for_ci": False,
            "live_etabs_explicit_opt_in_required": True,
            "production_source_tables": [
                _COMPONENT_TYPE_TABLE,
                _ASSIGNMENT_TABLE,
                _SECTION_TABLE,
                _MATERIAL_TABLE,
            ],
            "accepted_material_mapping": mapping.as_dict(),
            "direct_material_api_used": False,
            "existing_p7_pipeline_modified": False,
            "checks_executed": False,
            "output_files": list(_OUTPUT_FILES),
            "selectors": {
                "target_story": target_story,
                "target_label": target_label,
                "target_component": target_component,
                "max_rows": max_rows,
            },
        },
    )
    return ConcreteMaterialProbeResult(
        status=status,
        output_dir=out_dir,
        feature_snapshot_path=feature_snapshot_path,
        summary_path=summary_path,
        diagnostics_path=diagnostics_path,
        manifest_path=manifest_path,
        snapshot_count=len(snapshots),
        diagnostic_count=len(diagnostics),
    )


def write_concrete_material_attach_failure_outputs(
    *,
    output_dir: Path,
    attach_result: EtabsAttachResult,
) -> ConcreteMaterialProbeResult:
    out_dir = Path(output_dir)
    _prepare_owned_output_files(out_dir)
    feature_snapshot_path = out_dir / _OUTPUT_FILES[0]
    summary_path = out_dir / _OUTPUT_FILES[1]
    diagnostics_path = out_dir / _OUTPUT_FILES[2]
    manifest_path = out_dir / _OUTPUT_FILES[3]
    attempts = [attempt.as_dict() for attempt in attach_result.attempts]
    diagnostic = ConcreteMaterialProbeDiagnostic(
        status="BLOCKED",
        code="ETABS_COM_ATTACH_FAILED",
        message="No attach strategy succeeded.",
        details={"attempts": attempts},
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        summary_path,
        {
            "status": "FAIL",
            "candidate_row_count": 0,
            "selected_row_count": 0,
            "snapshot_count": 0,
            "diagnostic_count": 1,
            "material_definition_row_count": 0,
            "section_material_resolved_count": 0,
            "material_join_matched_count": 0,
            "material_join_missing_count": 0,
            "material_join_duplicate_count": 0,
            "fc_resolved_count": 0,
            "fc_missing_count": 0,
            "fc_blocked_count": 0,
            "feature_status_counts": {},
            "source_force_unit": None,
            "source_length_unit": None,
            "source_stress_unit": None,
            "target_strength_unit": _TARGET_STRENGTH_UNIT,
            "normalization_factor_to_mpa": _NORMALIZATION_FACTOR_TO_MPA,
            "truncation_applied": False,
            "failure_stage": "COM_ATTACH",
        },
    )
    _write_json(diagnostics_path, [diagnostic.as_dict()])
    _write_json(
        manifest_path,
        {
            "scope": _SCOPE,
            "runner": _RUNNER,
            "probe_is_read_only": True,
            "live_etabs_required_for_ci": False,
            "live_etabs_explicit_opt_in_required": True,
            "production_source_tables": [
                _COMPONENT_TYPE_TABLE,
                _ASSIGNMENT_TABLE,
                _SECTION_TABLE,
                _MATERIAL_TABLE,
            ],
            "accepted_material_mapping": DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING.as_dict(),
            "direct_material_api_used": False,
            "existing_p7_pipeline_modified": False,
            "checks_executed": False,
            "output_files": list(_ATTACH_FAILURE_OUTPUT_FILES),
            "selectors": {
                "target_story": None,
                "target_label": None,
                "target_component": None,
                "max_rows": None,
            },
            "attach_strategies": list(ATTACH_STRATEGIES),
            "attach_attempt_count": len(attempts),
        },
    )
    return ConcreteMaterialProbeResult(
        status="FAIL",
        output_dir=out_dir,
        feature_snapshot_path=feature_snapshot_path,
        summary_path=summary_path,
        diagnostics_path=diagnostics_path,
        manifest_path=manifest_path,
        snapshot_count=0,
        diagnostic_count=1,
    )


def _locked_material_table_mapping(raw_result: object) -> object:
    if isinstance(raw_result, Mapping):
        return raw_result
    if not isinstance(raw_result, Sequence) or isinstance(raw_result, (str, bytes, bytearray)):
        return raw_result
    sequences = tuple(
        item
        for item in raw_result
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray))
    )
    required = {"Material", "Fc"}
    for index, sequence in enumerate(sequences):
        if not all(isinstance(value, str) for value in sequence):
            continue
        columns = tuple(str(value) for value in sequence)
        if not required.issubset(set(columns)):
            continue
        for data_sequence in sequences[index + 1 :]:
            if tuple(data_sequence) == columns:
                continue
            return {"columns": list(columns), "flat_data": list(data_sequence)}
        return {"columns": list(columns), "flat_data": []}
    return raw_result


def _validate_locked_source_schema(
    *,
    probe_input: ConcreteMaterialProbeInput,
    mapping: AcceptedConcreteMaterialMapping,
    diagnostics: list[ConcreteMaterialProbeDiagnostic],
) -> bool:
    blocked = False
    if probe_input.material_table_status != "FETCHED" or not probe_input.material_rows:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="NO_DATA",
                code="MATERIAL_TABLE_MISSING_OR_EMPTY",
                message="Locked concrete material table is unavailable or contains zero rows",
                source_table=mapping.material_table_key,
                details={"table_status": probe_input.material_table_status},
            )
        )
        blocked = True

    missing_section_columns = [
        column
        for column in (mapping.section_name_column, mapping.section_material_column)
        if column not in probe_input.section_columns
    ]
    if missing_section_columns:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code="MATERIAL_TABLE_REQUIRED_COLUMN_MISSING",
                message="Locked section definition table is missing required material columns",
                source_table=mapping.section_table_key,
                details={"missing_columns": missing_section_columns},
            )
        )
        blocked = True

    if probe_input.material_table_status == "FETCHED":
        missing_material_columns = [
            column
            for column in (mapping.material_name_column, mapping.concrete_strength_column)
            if column not in probe_input.material_columns
        ]
        if missing_material_columns:
            diagnostics.append(
                ConcreteMaterialProbeDiagnostic(
                    status="BLOCKED",
                    code="MATERIAL_TABLE_REQUIRED_COLUMN_MISSING",
                    message="Locked concrete material table is missing required columns",
                    source_table=mapping.material_table_key,
                    details={"missing_columns": missing_material_columns},
                )
            )
            blocked = True
    return blocked


def _validate_material_units(
    *,
    unit_evidence: LiveEtabsLengthUnitEvidence | None,
    mapping: AcceptedConcreteMaterialMapping,
    diagnostics: list[ConcreteMaterialProbeDiagnostic],
) -> bool:
    if unit_evidence is None:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code="MATERIAL_UNIT_EVIDENCE_MISSING",
                message="Runtime ETABS force and length unit evidence is required",
                source_table=mapping.material_table_key,
            )
        )
        return True
    actual_pairs = (
        (unit_evidence.present_force_unit, unit_evidence.present_length_unit),
        (unit_evidence.database_force_unit, unit_evidence.database_length_unit),
    )
    expected_pair = (mapping.source_force_unit, mapping.source_length_unit)
    if any(pair != expected_pair for pair in actual_pairs):
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code="MATERIAL_STRESS_UNIT_UNSUPPORTED",
                message="Runtime ETABS force/length unit evidence is not the locked kN/m pair",
                source_table=mapping.material_table_key,
                details={
                    "present_force_unit": unit_evidence.present_force_unit,
                    "present_length_unit": unit_evidence.present_length_unit,
                    "present_stress_unit": _stress_unit(
                        unit_evidence.present_force_unit,
                        unit_evidence.present_length_unit,
                    ),
                    "database_force_unit": unit_evidence.database_force_unit,
                    "database_length_unit": unit_evidence.database_length_unit,
                    "database_stress_unit": _stress_unit(
                        unit_evidence.database_force_unit,
                        unit_evidence.database_length_unit,
                    ),
                    "supported_force_unit": mapping.source_force_unit,
                    "supported_length_unit": mapping.source_length_unit,
                },
            )
        )
        return True
    return False


def _resolve_concrete_feature(
    *,
    geometry_row: Mapping[str, object],
    material_rows: Sequence[Mapping[str, object]],
    unit_evidence: LiveEtabsLengthUnitEvidence | None,
    mapping: AcceptedConcreteMaterialMapping,
    diagnostics: list[ConcreteMaterialProbeDiagnostic],
    counts: _ResolutionCounts,
) -> _ResolvedConcreteFeature | None:
    component_id = _optional_text(geometry_row.get("component_id"))
    component_type = _optional_text(geometry_row.get("component_type"))
    assignment_row = geometry_row.get("assignment_source_row")
    section_row = geometry_row.get("property_source_row")
    if not isinstance(assignment_row, Mapping):
        assignment_row = {}
    if not isinstance(section_row, Mapping):
        section_row = {}

    assignment_section_column = geometry_row.get("assignment_section_column") or "SectProp"
    raw_assigned_section = assignment_row.get(assignment_section_column)
    raw_defined_section = section_row.get(mapping.section_name_column)
    if raw_assigned_section != raw_defined_section:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="NO_DATA",
                code="SECTION_DEFINITION_EXACT_JOIN_MISMATCH",
                message="Assignment SectProp and section Name are not exactly equal as raw values",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.section_table_key,
                details={
                    "raw_assigned_section": raw_assigned_section,
                    "raw_defined_section": raw_defined_section,
                },
            )
        )
        counts.fc_blocked_count += 1
        return None

    raw_material_name = section_row.get(mapping.section_material_column)
    if raw_material_name is None or raw_material_name == "":
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="NO_DATA",
                code="SECTION_MATERIAL_VALUE_MISSING",
                message="Accepted section definition row has no assigned material value",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.section_table_key,
            )
        )
        counts.fc_blocked_count += 1
        return None
    counts.section_material_resolved_count += 1

    matches = tuple(
        row
        for row in material_rows
        if row.get(mapping.material_name_column) == raw_material_name
    )
    if not matches:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="NO_DATA",
                code="MATERIAL_DEFINITION_NOT_FOUND",
                message="No concrete material definition exactly matched the raw assigned material value",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.material_table_key,
                details={"raw_material_name": raw_material_name},
            )
        )
        counts.material_join_missing_count += 1
        counts.fc_blocked_count += 1
        return None
    if len(matches) > 1:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code="MATERIAL_DEFINITION_DUPLICATE",
                message="More than one concrete material definition exactly matched the raw material value",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.material_table_key,
                details={"raw_material_name": raw_material_name, "match_count": len(matches)},
            )
        )
        counts.material_join_duplicate_count += 1
        counts.fc_blocked_count += 1
        return None

    counts.material_join_matched_count += 1
    material_row = matches[0]
    raw_fc = material_row.get(mapping.concrete_strength_column)
    if raw_fc is None or raw_fc == "":
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="NO_DATA",
                code="CONCRETE_FC_VALUE_MISSING",
                message="Matched material definition has no Fc value",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.material_table_key,
            )
        )
        counts.fc_missing_count += 1
        return None

    parsed_fc, parse_code = _parse_plain_finite_numeric(raw_fc)
    if parse_code is not None:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code=parse_code,
                message=(
                    "Concrete Fc value is non-finite"
                    if parse_code == "CONCRETE_FC_VALUE_NON_FINITE"
                    else "Concrete Fc value is not a plain numeric literal"
                ),
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.material_table_key,
                details={"raw_fc_value": raw_fc, "raw_fc_value_type": type(raw_fc).__name__},
            )
        )
        counts.fc_blocked_count += 1
        return None
    if parsed_fc is None or unit_evidence is None:
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code="CONCRETE_FC_NORMALIZATION_FAILED",
                message="Concrete Fc normalization could not be completed",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.material_table_key,
            )
        )
        counts.fc_blocked_count += 1
        return None

    try:
        normalized_fc = parsed_fc * mapping.normalization_factor_to_mpa
    except (ArithmeticError, TypeError, ValueError):
        normalized_fc = math.nan
    if not math.isfinite(normalized_fc):
        diagnostics.append(
            ConcreteMaterialProbeDiagnostic(
                status="BLOCKED",
                code="CONCRETE_FC_NORMALIZATION_FAILED",
                message="Concrete Fc normalization produced a non-finite result",
                component_id=component_id,
                component_type=component_type,
                feature_id=_FEATURE_ID,
                source_table=mapping.material_table_key,
            )
        )
        counts.fc_blocked_count += 1
        return None

    evidence_details = {
        "assignment_source_table": geometry_row.get("source_table_assignment"),
        "assignment_source_row": dict(assignment_row),
        "assignment_section_column": assignment_section_column,
        "assigned_section_name": raw_assigned_section,
        "section_definition_source_table": mapping.section_table_key,
        "section_definition_source_row": dict(section_row),
        "section_name_column": mapping.section_name_column,
        "section_material_column": mapping.section_material_column,
        "raw_material_name": raw_material_name,
        "raw_material_name_type": type(raw_material_name).__name__,
        "material_definition_source_table": mapping.material_table_key,
        "material_definition_source_row": dict(material_row),
        "material_name_column": mapping.material_name_column,
        "concrete_strength_column": mapping.concrete_strength_column,
        "raw_fc_value": raw_fc,
        "raw_fc_value_type": type(raw_fc).__name__,
        "parsed_value": parsed_fc,
        "present_units_raw": list(unit_evidence.present_units_raw),
        "database_units_raw": list(unit_evidence.database_units_raw),
        "source_force_unit": mapping.source_force_unit,
        "source_length_unit": mapping.source_length_unit,
        "source_stress_unit": mapping.source_stress_unit,
        "normalization_factor_to_mpa": mapping.normalization_factor_to_mpa,
        "normalized_fc_value": normalized_fc,
        "normalized_fc_unit": mapping.target_strength_unit,
        "normalization_basis": _NORMALIZATION_BASIS,
    }
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=mapping.material_table_key,
        actual_table_name=mapping.material_table_key,
        source_column=mapping.concrete_strength_column,
        source_row=evidence_details,
        raw_value=raw_fc,
        normalized_value=normalized_fc,
        unit=mapping.target_strength_unit,
        resolver="c14_0_p1_locked_concrete_fc_table_resolver",
    )
    feature = FeatureValue(
        feature_name=_FEATURE_ID,
        value=normalized_fc,
        unit=mapping.target_strength_unit,
        semantic_role="MATERIAL",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )
    counts.fc_resolved_count += 1
    return _ResolvedConcreteFeature(feature=feature, raw_material_name=raw_material_name)


def _snapshot_from_resolved_row(
    *,
    geometry_row: Mapping[str, object],
    concrete_feature: FeatureValue,
    raw_material_name: object,
) -> FeatureSnapshot:
    component_type = str(geometry_row.get("component_type"))
    component_id = str(geometry_row.get("component_id"))
    width_feature_id, depth_feature_id = _GEOMETRY_FEATURES[component_type]
    features = {
        width_feature_id: _geometry_feature(
            geometry_row=geometry_row,
            feature_id=width_feature_id,
            value_key="width_mm",
            details_key="width_normalization",
        ),
        depth_feature_id: _geometry_feature(
            geometry_row=geometry_row,
            feature_id=depth_feature_id,
            value_key="depth_mm",
            details_key="depth_normalization",
        ),
        _FEATURE_ID: concrete_feature,
    }
    identity = {
        key: geometry_row[key]
        for key in ("label", "story", "section", "unique_name", "section_name")
        if key in geometry_row and geometry_row[key] is not None
    }
    identity["assigned_material_name"] = raw_material_name
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity=identity,
        features=features,
    )


def _geometry_feature(
    *,
    geometry_row: Mapping[str, object],
    feature_id: str,
    value_key: str,
    details_key: str,
) -> FeatureValue:
    value = float(geometry_row[value_key])
    details = dict(geometry_row.get(details_key) or {})
    source_column = geometry_row.get(f"{value_key}_source_column") or value_key
    source_table = geometry_row.get("source_table_property") or geometry_row.get("source_table") or _SECTION_TABLE
    source_row = dict(geometry_row.get("property_source_row") or {})
    source_row.update(details)
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=str(source_table),
        actual_table_name=str(source_table),
        source_column=str(source_column),
        source_row=source_row,
        raw_value=details.get("raw_value", geometry_row[value_key]),
        normalized_value=value,
        unit="mm",
        resolver="c13_5_geometry_mapping_reused_by_c14_0_p1",
    )
    return FeatureValue(
        feature_name=feature_id,
        value=value,
        unit="mm",
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )


def _parse_plain_finite_numeric(raw_value: object) -> tuple[float | None, str | None]:
    if isinstance(raw_value, bool):
        return None, "CONCRETE_FC_VALUE_NOT_NUMERIC"
    if isinstance(raw_value, (int, float)):
        parsed = float(raw_value)
        if not math.isfinite(parsed):
            return None, "CONCRETE_FC_VALUE_NON_FINITE"
        return parsed, None
    if not isinstance(raw_value, str):
        return None, "CONCRETE_FC_VALUE_NOT_NUMERIC"
    if raw_value.casefold() in _NON_FINITE_TOKENS:
        return None, "CONCRETE_FC_VALUE_NON_FINITE"
    if not _NUMERIC_LITERAL_RE.fullmatch(raw_value):
        return None, "CONCRETE_FC_VALUE_NOT_NUMERIC"
    parsed = float(raw_value)
    if not math.isfinite(parsed):
        return None, "CONCRETE_FC_VALUE_NON_FINITE"
    return parsed, None


def _source_table_diagnostics(
    *,
    role: str,
    status: str,
    table_key: str,
    message: str | None,
) -> tuple[ConcreteMaterialProbeDiagnostic, ...]:
    if status == "FETCHED":
        return ()
    return (
        ConcreteMaterialProbeDiagnostic(
            status="NO_DATA" if status == "EMPTY" else "BLOCKED",
            code=f"{role}_TABLE_SOURCE_UNAVAILABLE",
            message=message or f"{role.title()} source table could not be read",
            source_table=table_key,
            details={"table_status": status},
        ),
    )


def _convert_geometry_diagnostics(
    diagnostics: Sequence[LiveGeometryProbeDiagnostic],
) -> tuple[ConcreteMaterialProbeDiagnostic, ...]:
    return tuple(
        ConcreteMaterialProbeDiagnostic(
            status=item.status,
            code=item.code,
            message=item.message,
            component_id=item.component_id,
            component_type=item.component_type,
            feature_id=item.feature_id,
            source_table=item.source_table,
        )
        for item in diagnostics
    )


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
    return tuple(selected[:max_rows]), len(selected) > max_rows


def _stress_unit(force_unit: str, length_unit: str) -> str:
    return f"{force_unit}/{length_unit}²"


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _feature_status_counts(snapshots: Sequence[FeatureSnapshot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for snapshot in snapshots:
        for feature in snapshot.features.values():
            status = feature.status.value
            counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _prepare_owned_output_files(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in _OUTPUT_FILES:
        path = output_dir / file_name
        if path.is_file() or path.is_symlink():
            path.unlink()


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "AcceptedConcreteMaterialMapping",
    "ConcreteMaterialProbeDiagnostic",
    "ConcreteMaterialProbeInput",
    "ConcreteMaterialProbeProvider",
    "ConcreteMaterialProbeResult",
    "DEFAULT_ACCEPTED_CONCRETE_MATERIAL_MAPPING",
    "FixtureConcreteMaterialProbeProvider",
    "create_live_etabs_concrete_material_provider",
    "probe_concrete_material_feature_snapshots",
    "write_concrete_material_attach_failure_outputs",
]
