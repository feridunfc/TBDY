"""Source-bound factual V2/V3 evidence for VS6-P7 column shear.

This module is acquisition/evidence only. It does not calculate TBDY/TS500
shear demand, section capacity, effective depth, reinforcement resistance, or a
compliance verdict. Display-table values are accepted only together with the
actual ETABS present-unit provenance captured from ``GetPresentUnits_2``; the
regulatory unit system is deliberately not used as an ETABS source-unit guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import RuntimeCaptureStatus, read_etabs_unit_snapshot
from tbdy_engine.providers.etabs_display_table_fetcher import (
    DisplayTableFetchResult,
    fetch_display_table_for_output,
)
from tbdy_engine.regulatory.units import Unit, UNIT_KN, UNIT_M, UNIT_MM, UNIT_N

TABLE_COLUMN_FORCES = "Element Forces - Columns"

COLUMN_SHEAR_IDENTITY_FIELDS: tuple[str, ...] = (
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
COLUMN_SHEAR_PAYLOAD_FIELDS: tuple[str, ...] = ("V2", "V3")

# CSI eForce/eLength numeric identities are source API identities, not unit
# conversion factors. Only units already supported by the canonical F0 Unit
# conversion table are accepted in this bounded slice.
CSI_EFORCE_N = 3
CSI_EFORCE_KN = 4
CSI_ELENGTH_MM = 4
CSI_ELENGTH_M = 6

CSI_GET_PRESENT_UNITS_2_REF = "CSI ETABS API GetPresentUnits_2"
CSI_EFORCE_ENUM_REF = "CSI ETABS API eForce: N=3, kN=4"
CSI_ELENGTH_ENUM_REF = "CSI ETABS API eLength: mm=4, m=6"
CSI_FRAME_FORCE_AXIS_REF = "CSI frame force convention: V2/M3 major; V3/M2 minor"


class ColumnShearDemandEvidenceError(RuntimeError):
    """Fail-closed factual V2/V3 acquisition or evidence error."""


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearDemandEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnShearDemandEvidenceError(f"{label} must be a finite decimal scalar")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ColumnShearDemandEvidenceError(f"{label} must be a finite decimal scalar") from exc
        if not decimal.is_finite():
            raise ColumnShearDemandEvidenceError(f"{label} must be finite")
        result = float(decimal)
    if not math.isfinite(result):
        raise ColumnShearDemandEvidenceError(f"{label} must be finite")
    return result


def _enum_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    candidate = getattr(value, "value", None)
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return int(candidate)
    try:
        return int(value)
    except Exception:
        return None


def _enum_name(value: Any) -> str | None:
    candidate = getattr(value, "name", None)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    if isinstance(value, str) and value.strip():
        return value.strip().split(".")[-1]
    return None


def resolve_etabs_present_force_unit(value: Any) -> Unit:
    """Resolve only explicitly reviewed CSI eForce identities supported by F0."""
    numeric = _enum_value(value)
    name = _enum_name(value)
    if numeric == CSI_EFORCE_N or name == "N":
        return UNIT_N
    if numeric == CSI_EFORCE_KN or name == "kN":
        return UNIT_KN
    raise ColumnShearDemandEvidenceError(
        "ETABS present force unit is unavailable or unsupported by the bounded P7 conversion contract"
    )


def resolve_etabs_present_length_unit(value: Any) -> Unit:
    """Resolve only explicitly reviewed CSI eLength identities supported by F0."""
    numeric = _enum_value(value)
    name = _enum_name(value)
    if numeric == CSI_ELENGTH_MM or name == "mm":
        return UNIT_MM
    if numeric == CSI_ELENGTH_M or name == "m":
        return UNIT_M
    raise ColumnShearDemandEvidenceError(
        "ETABS present length unit is unavailable or unsupported by the bounded P7 conversion contract"
    )


def _canonical_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ColumnShearDemandEvidenceError("evidence scalar must be finite")
        return value
    return str(value)


def _identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(field) for field in COLUMN_SHEAR_IDENTITY_FIELDS)


def column_shear_source_identity(row: Mapping[str, Any]) -> str:
    """Deterministic exact ETABS result-row identity; never fuzzy/name based."""
    return json.dumps(
        [_canonical_scalar(row.get(field)) for field in COLUMN_SHEAR_IDENTITY_FIELDS],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _rows(fetch: DisplayTableFetchResult) -> tuple[dict[str, Any], ...]:
    return tuple(dict(row) for row in fetch.parsed.rows)


def _require_full(fetch: DisplayTableFetchResult, table: str) -> None:
    if fetch.capture_status is not RuntimeCaptureStatus.FULL:
        raise ColumnShearDemandEvidenceError(
            f"{table} requires runtime FULL acquisition; got {fetch.capture_status.value}"
        )
    if fetch.parsed.return_code not in (None, 0):
        raise ColumnShearDemandEvidenceError(f"{table} returned nonzero code {fetch.parsed.return_code}")
    reported = fetch.parsed.row_count_reported
    if reported is not None and len(fetch.parsed.rows) != int(reported):
        raise ColumnShearDemandEvidenceError(
            f"{table} FULL capture row mismatch: captured={len(fetch.parsed.rows)} reported={reported}"
        )


def _restore_ok(fetch: DisplayTableFetchResult) -> bool:
    return any(
        item.get("phase") == "restore_verify" and item.get("success") is True
        for item in fetch.state_diagnostics
    )


@dataclass(frozen=True, slots=True)
class ColumnShearDemandEvidenceBundle:
    model_fingerprint: str
    evidence_epoch_id: str
    output_names: tuple[str, ...]
    force_unit: Unit
    length_unit: Unit
    unit_provenance_refs: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    source_table: str = TABLE_COLUMN_FORCES
    runtime_capture_status: RuntimeCaptureStatus = RuntimeCaptureStatus.FULL

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        outputs = tuple(_text(item, "output_name") for item in self.output_names)
        if not outputs or len(outputs) != len(set(outputs)):
            raise ColumnShearDemandEvidenceError("output_names must be a nonempty unique sequence")
        object.__setattr__(self, "output_names", outputs)
        if self.source_table != TABLE_COLUMN_FORCES:
            raise ColumnShearDemandEvidenceError("column shear source table identity mismatch")
        if self.force_unit not in {UNIT_N, UNIT_KN}:
            raise ColumnShearDemandEvidenceError("P7 force unit must be explicit N or kN")
        if self.length_unit not in {UNIT_MM, UNIT_M}:
            raise ColumnShearDemandEvidenceError("P7 length unit must be explicit mm or m")
        if self.runtime_capture_status is not RuntimeCaptureStatus.FULL:
            raise ColumnShearDemandEvidenceError("P7 V2/V3 evidence requires FULL runtime capture")
        refs = tuple(_text(item, "unit_provenance_ref") for item in self.unit_provenance_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnShearDemandEvidenceError("unit_provenance_refs must be nonempty and unique")
        object.__setattr__(self, "unit_provenance_refs", refs)

        expected = set(COLUMN_SHEAR_IDENTITY_FIELDS + COLUMN_SHEAR_PAYLOAD_FIELDS)
        identities: set[tuple[Any, ...]] = set()
        frozen_rows: list[Mapping[str, Any]] = []
        for index, raw in enumerate(self.rows):
            row = dict(raw)
            row.setdefault("StepNumber", None)
            missing = expected - set(row)
            if missing:
                raise ColumnShearDemandEvidenceError(
                    f"column shear row {index} missing required field(s): {', '.join(sorted(missing))}"
                )
            _finite(row.get("Station"), f"row[{index}].Station")
            _finite(row.get("V2"), f"row[{index}].V2")
            _finite(row.get("V3"), f"row[{index}].V3")
            identity = _identity(row)
            if identity in identities:
                raise ColumnShearDemandEvidenceError("duplicate exact column shear row identity")
            identities.add(identity)
            frozen_rows.append(MappingProxyType(row))
        if not frozen_rows:
            raise ColumnShearDemandEvidenceError("column shear evidence requires at least one row")
        object.__setattr__(self, "rows", tuple(frozen_rows))

    def rows_for_column(self, unique_name: str) -> tuple[Mapping[str, Any], ...]:
        uid = _text(unique_name, "unique_name")
        return tuple(row for row in self.rows if str(row.get("UniqueName")) == uid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "VS6_P7_COLUMN_SHEAR_DEMAND_EVIDENCE",
            "model_fingerprint": self.model_fingerprint,
            "evidence_epoch_id": self.evidence_epoch_id,
            "source_table": self.source_table,
            "output_names": list(self.output_names),
            "force_unit": self.force_unit.identifier,
            "length_unit": self.length_unit.identifier,
            "unit_provenance_refs": list(self.unit_provenance_refs),
            "runtime_capture_status": self.runtime_capture_status.value,
            "row_count": len(self.rows),
            "rows": [dict(row) for row in self.rows],
        }


def build_column_shear_demand_evidence(
    *,
    model_fingerprint: str,
    rows: Sequence[Mapping[str, Any]],
    output_names: Sequence[str],
    force_unit: Unit,
    length_unit: Unit,
    unit_provenance_refs: Sequence[str],
) -> ColumnShearDemandEvidenceBundle:
    """Bind exact V2/V3 rows and source units into one deterministic epoch."""
    fingerprint = _text(model_fingerprint, "model_fingerprint")
    outputs = tuple(_text(item, "output_name") for item in output_names)
    if not outputs or len(outputs) != len(set(outputs)):
        raise ColumnShearDemandEvidenceError("output_names must be a nonempty unique sequence")
    exact_rows: list[dict[str, Any]] = []
    for raw in rows:
        if raw.get("OutputCase") not in outputs:
            continue
        row = dict(raw)
        row.setdefault("StepNumber", None)
        exact_rows.append(row)
    if not exact_rows:
        raise ColumnShearDemandEvidenceError("no exact rows remained for reviewed output_names")

    provisional = ColumnShearDemandEvidenceBundle(
        model_fingerprint=fingerprint,
        evidence_epoch_id="epoch:vs6-p7-column-shear:pending",
        output_names=outputs,
        force_unit=force_unit,
        length_unit=length_unit,
        unit_provenance_refs=tuple(unit_provenance_refs),
        rows=tuple(exact_rows),
    )
    canonical_rows = sorted(
        [
            *[_canonical_scalar(row.get(field)) for field in COLUMN_SHEAR_IDENTITY_FIELDS],
            _finite(row.get("V2"), "V2"),
            _finite(row.get("V3"), "V3"),
        ]
        for row in provisional.rows
    )
    payload = {
        "model_fingerprint": fingerprint,
        "source_table": TABLE_COLUMN_FORCES,
        "output_names": list(outputs),
        "force_unit": force_unit.identifier,
        "length_unit": length_unit.identifier,
        "unit_provenance_refs": list(provisional.unit_provenance_refs),
        "fields": list(COLUMN_SHEAR_IDENTITY_FIELDS + COLUMN_SHEAR_PAYLOAD_FIELDS),
        "rows": canonical_rows,
        "local_axis_pairing": ["V2->M3", "V3->M2"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    epoch = "epoch:vs6-p7-column-shear:sha256:" + hashlib.sha256(encoded).hexdigest()
    return ColumnShearDemandEvidenceBundle(
        model_fingerprint=fingerprint,
        evidence_epoch_id=epoch,
        output_names=outputs,
        force_unit=force_unit,
        length_unit=length_unit,
        unit_provenance_refs=tuple(unit_provenance_refs),
        rows=tuple(exact_rows),
    )


def capture_live_column_shear_demand_evidence(
    *,
    sap_model: Any,
    model_fingerprint: str,
    output_names: Sequence[str],
    expected_column_unique_names: Sequence[str],
) -> ColumnShearDemandEvidenceBundle:
    """Read V2/V3 with exact ETABS present-unit provenance and no unit mutation."""
    fingerprint = _text(model_fingerprint, "model_fingerprint")
    outputs = tuple(_text(item, "output_name") for item in output_names)
    expected_uids = tuple(_text(item, "expected_column_unique_name") for item in expected_column_unique_names)
    if not outputs or len(outputs) != len(set(outputs)):
        raise ColumnShearDemandEvidenceError("output_names must be nonempty and unique")
    if not expected_uids or len(expected_uids) != len(set(expected_uids)):
        raise ColumnShearDemandEvidenceError("expected_column_unique_names must be nonempty and unique")

    before = read_etabs_unit_snapshot(sap_model)
    if before.present_units_api != "GetPresentUnits_2":
        raise ColumnShearDemandEvidenceError(
            "P7 requires source-specific GetPresentUnits_2 provenance for display-table force/length units"
        )
    force_unit = resolve_etabs_present_force_unit(before.present_force_unit)
    length_unit = resolve_etabs_present_length_unit(before.present_length_unit)

    force_rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    expected_set = set(expected_uids)
    database_tables = sap_model.DatabaseTables
    for output_name in outputs:
        fetch = fetch_display_table_for_output(
            database_tables,
            TABLE_COLUMN_FORCES,
            preferred_output_case=output_name,
            max_rows=None,
        )
        _require_full(fetch, f"{TABLE_COLUMN_FORCES}@{output_name}")
        if not _restore_ok(fetch):
            raise ColumnShearDemandEvidenceError(
                f"{TABLE_COLUMN_FORCES}@{output_name} output-selection restore did not verify"
            )
        exact = tuple(row for row in _rows(fetch) if row.get("OutputCase") == output_name)
        if not exact:
            raise ColumnShearDemandEvidenceError(
                f"FULL column-force lookup found no exact rows for reviewed output {output_name}"
            )
        observed_uids = {str(row.get("UniqueName")) for row in exact}
        if observed_uids != expected_set:
            missing = sorted(expected_set - observed_uids)
            extra = sorted(observed_uids - expected_set)
            raise ColumnShearDemandEvidenceError(
                f"column shear population mismatch for {output_name}: missing={missing} extra={extra}"
            )
        for raw in exact:
            row = dict(raw)
            row.setdefault("StepNumber", None)
            identity = _identity(row)
            if identity in seen:
                raise ColumnShearDemandEvidenceError("duplicate exact row across output captures")
            seen.add(identity)
            force_rows.append(row)

    after = read_etabs_unit_snapshot(sap_model)
    if after.present_units_api != "GetPresentUnits_2":
        raise ColumnShearDemandEvidenceError("ETABS present-unit provenance disappeared during P7 acquisition")
    if (
        _enum_value(after.present_force_unit) != _enum_value(before.present_force_unit)
        or _enum_value(after.present_length_unit) != _enum_value(before.present_length_unit)
    ):
        raise ColumnShearDemandEvidenceError("ETABS present units changed during P7 factual acquisition")

    provenance = (
        CSI_GET_PRESENT_UNITS_2_REF,
        CSI_EFORCE_ENUM_REF,
        CSI_ELENGTH_ENUM_REF,
        CSI_FRAME_FORCE_AXIS_REF,
        f"ETABS_PRESENT_FORCE_ENUM={_enum_value(before.present_force_unit)}",
        f"ETABS_PRESENT_LENGTH_ENUM={_enum_value(before.present_length_unit)}",
    )
    return build_column_shear_demand_evidence(
        model_fingerprint=fingerprint,
        rows=force_rows,
        output_names=outputs,
        force_unit=force_unit,
        length_unit=length_unit,
        unit_provenance_refs=provenance,
    )


__all__ = [
    "COLUMN_SHEAR_IDENTITY_FIELDS",
    "COLUMN_SHEAR_PAYLOAD_FIELDS",
    "CSI_EFORCE_N",
    "CSI_EFORCE_KN",
    "CSI_ELENGTH_MM",
    "CSI_ELENGTH_M",
    "CSI_FRAME_FORCE_AXIS_REF",
    "ColumnShearDemandEvidenceBundle",
    "ColumnShearDemandEvidenceError",
    "build_column_shear_demand_evidence",
    "capture_live_column_shear_demand_evidence",
    "column_shear_source_identity",
    "resolve_etabs_present_force_unit",
    "resolve_etabs_present_length_unit",
]
