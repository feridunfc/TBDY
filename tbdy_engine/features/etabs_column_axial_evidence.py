"""Live factual ETABS evidence for VS5 column axial checks.

This module performs read-only acquisition and normalization only. It does not
select Ndm/Nd, apply code coefficients, compute capacities, or emit compliance
verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.providers.etabs_display_table_fetcher import (
    DisplayTableFetchResult,
    fetch_display_table,
    fetch_display_table_for_output,
)

COLUMN_FORCE_IDENTITY_FIELDS = (
    "Story",
    "Column",
    "UniqueName",
    "OutputCase",
    "CaseType",
    "StepType",
    "StepNumber",
    "Station",
    "Element",
    "ElemStation",
)
COLUMN_FORCE_PAYLOAD_FIELDS = ("P",)

TABLE_COLUMN_CONNECTIVITY = "Column Object Connectivity"
TABLE_SECTION_ASSIGNMENTS = "Frame Assignments - Section Properties"
TABLE_CONCRETE_RECTANGULAR = "Frame Section Property Definitions - Concrete Rectangular"
TABLE_CONCRETE_DATA = "Material Properties - Concrete Data"
TABLE_LOAD_PATTERNS = "Load Pattern Definitions"
TABLE_LOAD_COMBINATIONS = "Load Combination Definitions"
TABLE_COLUMN_OVERWRITES = "Concrete Column Overwrites - TS 500-2000(R2018)"
TABLE_COLUMN_FORCES = "Element Forces - Columns"

FACTUAL_STATUS_PROVEN = "PROVEN"
FACTUAL_STATUS_BLOCKED = "BLOCKED"


class ColumnAxialEvidenceError(RuntimeError):
    def __init__(self, message: str, *, status: str = FACTUAL_STATUS_BLOCKED) -> None:
        super().__init__(message)
        self.status = status


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnAxialEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _float(value: Any, label: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ColumnAxialEvidenceError(f"{label} must be a finite decimal scalar")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        if not value or value != value.strip():
            raise ColumnAxialEvidenceError(f"{label} decimal text must be nonblank and unpadded")
        try:
            decimal = Decimal(value)
        except InvalidOperation as exc:
            raise ColumnAxialEvidenceError(f"{label} decimal text is invalid") from exc
        if not decimal.is_finite():
            raise ColumnAxialEvidenceError(f"{label} must be finite")
        result = float(decimal)
    else:
        raise ColumnAxialEvidenceError(f"{label} must be numeric")
    if not math.isfinite(result):
        raise ColumnAxialEvidenceError(f"{label} must be finite")
    return result


def _rows(fetch: DisplayTableFetchResult) -> tuple[dict[str, Any], ...]:
    return tuple(dict(row) for row in fetch.parsed.rows)


def _require_full(fetch: DisplayTableFetchResult, table: str) -> None:
    if fetch.capture_status is not RuntimeCaptureStatus.FULL:
        raise ColumnAxialEvidenceError(
            f"{table} requires runtime FULL acquisition; got {fetch.capture_status.value}"
        )
    if fetch.parsed.return_code not in (None, 0):
        raise ColumnAxialEvidenceError(f"{table} returned nonzero code {fetch.parsed.return_code}")
    reported = fetch.parsed.row_count_reported
    if reported is not None and len(fetch.parsed.rows) != int(reported):
        raise ColumnAxialEvidenceError(
            f"{table} FULL capture row mismatch: captured={len(fetch.parsed.rows)} reported={reported}"
        )


def _restore_ok(fetch: DisplayTableFetchResult) -> bool:
    return any(
        item.get("phase") == "restore_verify" and item.get("success") is True
        for item in fetch.state_diagnostics
    )


def _freeze_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(row))


@dataclass(frozen=True, slots=True)
class ColumnGeometryEvidence:
    unique_name: str
    story: str
    column_label: str
    section: str
    material: str
    width_m: float
    depth_m: float
    fck_mpa: float
    connectivity_row: Mapping[str, Any]
    assignment_row: Mapping[str, Any]
    section_row: Mapping[str, Any]
    material_row: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("unique_name", "story", "column_label", "section", "material"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("width_m", "depth_m", "fck_mpa"):
            value = _float(getattr(self, name), name)
            if value <= 0.0:
                raise ColumnAxialEvidenceError(f"{name} must be > 0")
            object.__setattr__(self, name, value)
        for name in ("connectivity_row", "assignment_row", "section_row", "material_row"):
            object.__setattr__(self, name, _freeze_row(getattr(self, name)))

    @property
    def gross_area_m2(self) -> float:
        return self.width_m * self.depth_m

    @property
    def component_id(self) -> str:
        return f"{self.story}:{self.column_label}:{self.unique_name}"

    def as_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "UniqueName": self.unique_name,
            "Story": self.story,
            "Column": self.column_label,
            "Section": self.section,
            "Material": self.material,
            "width_m": self.width_m,
            "depth_m": self.depth_m,
            "gross_area_m2": self.gross_area_m2,
            "fck_mpa": self.fck_mpa,
            "source_rows": {
                "connectivity": dict(self.connectivity_row),
                "section_assignment": dict(self.assignment_row),
                "section_definition": dict(self.section_row),
                "material_definition": dict(self.material_row),
            },
        }


@dataclass(frozen=True, slots=True)
class ColumnForceEvidenceBundle:
    rows: tuple[Mapping[str, Any], ...]
    output_names: tuple[str, ...]
    force_unit: str
    source_table: str = TABLE_COLUMN_FORCES
    runtime_capture_status: RuntimeCaptureStatus = RuntimeCaptureStatus.FULL

    def __post_init__(self) -> None:
        if self.source_table != TABLE_COLUMN_FORCES:
            raise ColumnAxialEvidenceError("Column force evidence source table identity mismatch")
        if self.force_unit != "kN":
            raise ColumnAxialEvidenceError("VS5 initial live force contract requires reviewed kN source unit")
        outputs = tuple(_text(item, "output_name") for item in self.output_names)
        if not outputs or len(outputs) != len(set(outputs)):
            raise ColumnAxialEvidenceError("output_names must be a nonempty unique sequence")
        frozen_rows: list[Mapping[str, Any]] = []
        expected = set(COLUMN_FORCE_IDENTITY_FIELDS + COLUMN_FORCE_PAYLOAD_FIELDS)
        identities: set[tuple[Any, ...]] = set()
        for index, row in enumerate(self.rows):
            missing = expected - set(row)
            if missing:
                raise ColumnAxialEvidenceError(
                    f"Column force row {index} missing required field(s): {', '.join(sorted(missing))}"
                )
            identity = tuple(row.get(field) for field in COLUMN_FORCE_IDENTITY_FIELDS)
            if identity in identities:
                raise ColumnAxialEvidenceError("Duplicate exact column force row identity is ambiguous")
            identities.add(identity)
            frozen_rows.append(_freeze_row(row))
        if self.runtime_capture_status is not RuntimeCaptureStatus.FULL:
            raise ColumnAxialEvidenceError("VS5 result-derived demands require FULL column force evidence")
        object.__setattr__(self, "rows", tuple(frozen_rows))
        object.__setattr__(self, "output_names", outputs)

    def rows_for_output(self, output_name: str) -> tuple[Mapping[str, Any], ...]:
        name = _text(output_name, "output_name")
        return tuple(row for row in self.rows if row.get("OutputCase") == name)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_table": self.source_table,
            "force_unit": self.force_unit,
            "runtime_capture_status": self.runtime_capture_status.value,
            "output_names": list(self.output_names),
            "row_count": len(self.rows),
            "rows": [dict(row) for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class LiveColumnAxialEvidenceBundle:
    model_fingerprint: str
    evidence_epoch_id: str
    columns: tuple[ColumnGeometryEvidence, ...]
    forces: ColumnForceEvidenceBundle
    load_pattern_rows: tuple[Mapping[str, Any], ...]
    load_combination_rows: tuple[Mapping[str, Any], ...]
    column_overwrite_rows: tuple[Mapping[str, Any], ...]
    review_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        columns = tuple(self.columns)
        if not columns:
            raise ColumnAxialEvidenceError("VS5 factual bundle requires at least one column")
        if len({item.unique_name for item in columns}) != len(columns):
            raise ColumnAxialEvidenceError("Duplicate column UniqueName in VS5 factual bundle")
        object.__setattr__(self, "columns", columns)
        for name in ("load_pattern_rows", "load_combination_rows", "column_overwrite_rows"):
            object.__setattr__(self, name, tuple(_freeze_row(row) for row in getattr(self, name)))
        for name in ("review_refs", "provenance_refs"):
            refs = tuple(_text(item, name[:-1]) for item in getattr(self, name))
            if not refs:
                raise ColumnAxialEvidenceError(f"{name} must contain at least one reviewed reference")
            object.__setattr__(self, name, refs)

    def column(self, unique_name: str) -> ColumnGeometryEvidence:
        uid = _text(unique_name, "unique_name")
        matches = tuple(item for item in self.columns if item.unique_name == uid)
        if len(matches) != 1:
            raise KeyError(f"expected exactly one column UniqueName={uid}, got {len(matches)}")
        return matches[0]

    def as_dict(self) -> dict[str, object]:
        return {
            "model_fingerprint": self.model_fingerprint,
            "evidence_epoch_id": self.evidence_epoch_id,
            "column_count": len(self.columns),
            "columns": [item.as_dict() for item in self.columns],
            "forces": self.forces.as_dict(),
            "load_pattern_rows": [dict(row) for row in self.load_pattern_rows],
            "load_combination_rows": [dict(row) for row in self.load_combination_rows],
            "column_overwrite_rows": [dict(row) for row in self.column_overwrite_rows],
            "review_refs": list(self.review_refs),
            "provenance_refs": list(self.provenance_refs),
        }


def _column_geometry(
    connectivity_rows: Sequence[Mapping[str, Any]],
    assignment_rows: Sequence[Mapping[str, Any]],
    section_rows: Sequence[Mapping[str, Any]],
    material_rows: Sequence[Mapping[str, Any]],
) -> tuple[ColumnGeometryEvidence, ...]:
    conn_by_uid = {str(row.get("UniqueName")): row for row in connectivity_rows}
    asg_by_uid = {str(row.get("UniqueName")): row for row in assignment_rows}
    if len(conn_by_uid) != len(connectivity_rows):
        raise ColumnAxialEvidenceError("Column Object Connectivity contains duplicate UniqueName")
    missing = sorted(set(conn_by_uid) - set(asg_by_uid))
    if missing:
        raise ColumnAxialEvidenceError(
            "Column section assignment missing for UniqueName(s): " + ",".join(missing)
        )
    section_by_name = {str(row.get("Name")): row for row in section_rows}
    material_by_name = {str(row.get("Material")): row for row in material_rows}
    out: list[ColumnGeometryEvidence] = []
    for uid in sorted(conn_by_uid, key=lambda value: (len(value), value)):
        conn = conn_by_uid[uid]
        asg = asg_by_uid[uid]
        story = _text(conn.get("Story"), "Column Object Connectivity.Story")
        label = _text(conn.get("ColumnBay"), "Column Object Connectivity.ColumnBay")
        if asg.get("Story") != story or asg.get("Label") != label:
            raise ColumnAxialEvidenceError(
                f"Column identity mismatch for UniqueName={uid}: connectivity and assignment disagree"
            )
        if asg.get("Shape") != "Concrete Rectangular":
            raise ColumnAxialEvidenceError(
                f"Unsupported VS5 column Shape for UniqueName={uid}: {asg.get('Shape')}"
            )
        section = _text(asg.get("SectProp"), "SectProp")
        section_row = section_by_name.get(section)
        if section_row is None:
            raise ColumnAxialEvidenceError(f"Missing concrete rectangular section definition: {section}")
        if str(section_row.get("DesignType") or "") != "Column":
            raise ColumnAxialEvidenceError(f"Section {section} is not DesignType=Column")
        material = _text(section_row.get("Material"), "section material")
        material_row = material_by_name.get(material)
        if material_row is None:
            raise ColumnAxialEvidenceError(f"Missing concrete material definition: {material}")
        width_m = _float(section_row.get("t2"), f"{section}.t2")
        depth_m = _float(section_row.get("t3"), f"{section}.t3")
        # Under the reviewed initial VS5 unit contract Concrete Data.Fc is kPa
        # while formal regulatory checks consume MPa.
        fck_mpa = _float(material_row.get("Fc"), f"{material}.Fc") / 1000.0
        out.append(
            ColumnGeometryEvidence(
                unique_name=uid,
                story=story,
                column_label=label,
                section=section,
                material=material,
                width_m=width_m,
                depth_m=depth_m,
                fck_mpa=fck_mpa,
                connectivity_row=conn,
                assignment_row=asg,
                section_row=section_row,
                material_row=material_row,
            )
        )
    return tuple(out)


def _epoch_payload(
    *,
    model_fingerprint: str,
    columns: Sequence[ColumnGeometryEvidence],
    force_rows: Sequence[Mapping[str, Any]],
    output_names: Sequence[str],
) -> str:
    payload = {
        "model_fingerprint": model_fingerprint,
        "columns": [
            [
                item.unique_name,
                item.story,
                item.column_label,
                item.section,
                item.material,
                item.width_m,
                item.depth_m,
                item.fck_mpa,
            ]
            for item in columns
        ],
        "output_names": list(output_names),
        "force_rows": [
            [row.get(field) for field in COLUMN_FORCE_IDENTITY_FIELDS + COLUMN_FORCE_PAYLOAD_FIELDS]
            for row in force_rows
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "epoch:vs5-column-axial:sha256:" + hashlib.sha256(encoded).hexdigest()


def capture_live_column_axial_evidence(
    *,
    database_tables: Any,
    model_fingerprint: str,
    output_names: Sequence[str],
    reviewed_force_unit: str,
    reviewed_length_unit: str,
    reviewed_concrete_fc_unit: str,
    review_refs: Sequence[str],
    provenance_refs: Sequence[str],
) -> LiveColumnAxialEvidenceBundle:
    """Capture the bounded live-proven VS5 factual population.

    The initial supported unit contract is exact and reviewed:
    Element Forces P -> kN, rectangular t2/t3 -> m, Concrete Data.Fc -> kPa.
    No present-unit mutation is performed here.
    """
    model_fingerprint = _text(model_fingerprint, "model_fingerprint")
    outputs = tuple(_text(item, "output_name") for item in output_names)
    if not outputs or len(outputs) != len(set(outputs)):
        raise ColumnAxialEvidenceError("output_names must be a nonempty unique sequence")
    if reviewed_force_unit != "kN":
        raise ColumnAxialEvidenceError("VS5 initial reviewed force unit must be kN")
    if reviewed_length_unit != "m":
        raise ColumnAxialEvidenceError("VS5 initial reviewed length unit must be m")
    if reviewed_concrete_fc_unit != "kPa":
        raise ColumnAxialEvidenceError("VS5 initial reviewed Concrete Data.Fc unit must be kPa")

    static_fetches = {
        TABLE_COLUMN_CONNECTIVITY: fetch_display_table(database_tables, TABLE_COLUMN_CONNECTIVITY, max_rows=None),
        TABLE_SECTION_ASSIGNMENTS: fetch_display_table(database_tables, TABLE_SECTION_ASSIGNMENTS, max_rows=None),
        TABLE_CONCRETE_RECTANGULAR: fetch_display_table(database_tables, TABLE_CONCRETE_RECTANGULAR, max_rows=None),
        TABLE_CONCRETE_DATA: fetch_display_table(database_tables, TABLE_CONCRETE_DATA, max_rows=None),
        TABLE_LOAD_PATTERNS: fetch_display_table(database_tables, TABLE_LOAD_PATTERNS, max_rows=None),
        TABLE_LOAD_COMBINATIONS: fetch_display_table(database_tables, TABLE_LOAD_COMBINATIONS, max_rows=None),
        TABLE_COLUMN_OVERWRITES: fetch_display_table(database_tables, TABLE_COLUMN_OVERWRITES, max_rows=None),
    }
    for table, fetch in static_fetches.items():
        _require_full(fetch, table)

    columns = _column_geometry(
        _rows(static_fetches[TABLE_COLUMN_CONNECTIVITY]),
        _rows(static_fetches[TABLE_SECTION_ASSIGNMENTS]),
        _rows(static_fetches[TABLE_CONCRETE_RECTANGULAR]),
        _rows(static_fetches[TABLE_CONCRETE_DATA]),
    )
    column_uids = {item.unique_name for item in columns}

    force_rows: list[dict[str, Any]] = []
    seen_identities: set[tuple[Any, ...]] = set()
    for output_name in outputs:
        fetch = fetch_display_table_for_output(
            database_tables,
            TABLE_COLUMN_FORCES,
            preferred_output_case=output_name,
            max_rows=None,
        )
        _require_full(fetch, f"{TABLE_COLUMN_FORCES}@{output_name}")
        if not _restore_ok(fetch):
            raise ColumnAxialEvidenceError(
                f"{TABLE_COLUMN_FORCES}@{output_name} output selection restore did not verify"
            )
        exact = tuple(row for row in _rows(fetch) if row.get("OutputCase") == output_name)
        if not exact:
            raise ColumnAxialEvidenceError(
                f"FULL column-force lookup found no exact rows for reviewed output {output_name}"
            )
        exact_uids = {str(row.get("UniqueName")) for row in exact}
        if exact_uids != column_uids:
            missing = sorted(column_uids - exact_uids)
            extra = sorted(exact_uids - column_uids)
            raise ColumnAxialEvidenceError(
                f"Column-force population mismatch for {output_name}: missing={missing} extra={extra}"
            )
        for row in exact:
            identity = tuple(row.get(field) for field in COLUMN_FORCE_IDENTITY_FIELDS)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            force_rows.append(row)

    forces = ColumnForceEvidenceBundle(
        rows=tuple(force_rows),
        output_names=outputs,
        force_unit=reviewed_force_unit,
    )
    epoch = _epoch_payload(
        model_fingerprint=model_fingerprint,
        columns=columns,
        force_rows=force_rows,
        output_names=outputs,
    )
    return LiveColumnAxialEvidenceBundle(
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=epoch,
        columns=columns,
        forces=forces,
        load_pattern_rows=_rows(static_fetches[TABLE_LOAD_PATTERNS]),
        load_combination_rows=_rows(static_fetches[TABLE_LOAD_COMBINATIONS]),
        column_overwrite_rows=_rows(static_fetches[TABLE_COLUMN_OVERWRITES]),
        review_refs=tuple(review_refs),
        provenance_refs=tuple(provenance_refs),
    )


__all__ = [
    "COLUMN_FORCE_IDENTITY_FIELDS",
    "COLUMN_FORCE_PAYLOAD_FIELDS",
    "TABLE_COLUMN_CONNECTIVITY",
    "TABLE_SECTION_ASSIGNMENTS",
    "TABLE_CONCRETE_RECTANGULAR",
    "TABLE_CONCRETE_DATA",
    "TABLE_LOAD_PATTERNS",
    "TABLE_LOAD_COMBINATIONS",
    "TABLE_COLUMN_OVERWRITES",
    "TABLE_COLUMN_FORCES",
    "FACTUAL_STATUS_PROVEN",
    "FACTUAL_STATUS_BLOCKED",
    "ColumnAxialEvidenceError",
    "ColumnGeometryEvidence",
    "ColumnForceEvidenceBundle",
    "LiveColumnAxialEvidenceBundle",
    "capture_live_column_axial_evidence",
]
