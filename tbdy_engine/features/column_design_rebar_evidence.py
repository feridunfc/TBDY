"""Source-bound ETABS concrete-column longitudinal rebar requirement evidence.

The direct CSI ``DesignConcrete.GetSummaryResultsColumn`` API is factual/design
evidence only. No ETABS design ratio or status is promoted to a TBDY/TS500
compliance verdict here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import read_etabs_unit_snapshot
from tbdy_engine.features.column_shear_demand_evidence import resolve_etabs_present_length_unit
from tbdy_engine.regulatory.units import Unit, UNIT_M, UNIT_MM, conversion_factor

SOURCE_API = "DesignConcrete.GetSummaryResultsColumn"
SOURCE_API_REF = "CSI ETABS API GetSummaryResultsColumn"
SOURCE_UNIT_API_REF = "CSI ETABS API GetPresentUnits_2"
SELECTION_RULE = "MAX_REQUIRED_LONGITUDINAL_AREA_ACROSS_DESIGN_LOCATIONS"
STATUS_PROVEN = "PROVEN_ETABS_REQUIRED_REBAR"
STATUS_NO_DATA = "NO_DATA_ETABS_REQUIRED_REBAR"
STATUS_BLOCKED = "BLOCKED_ETABS_REQUIRED_REBAR"


class ColumnDesignRebarEvidenceError(RuntimeError):
    pass


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignRebarEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _finite(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnDesignRebarEvidenceError(f"{label} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnDesignRebarEvidenceError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ColumnDesignRebarEvidenceError(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class ColumnDesignRebarIdentity:
    component_id: str
    story: str
    object_name: str
    label: str
    unique_name: str
    section_identity: str

    def __post_init__(self) -> None:
        for name in ("component_id", "story", "object_name", "label", "unique_name", "section_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    def as_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _canonical_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        option = int(row.get("MyOption"))
    except (TypeError, ValueError) as exc:
        raise ColumnDesignRebarEvidenceError("MyOption must be CSI Check=1 or Design=2") from exc
    return {
        "FrameName": _text(row.get("FrameName"), "FrameName"),
        "MyOption": option,
        "Location": _finite(row.get("Location"), "Location"),
        "PMMCombo": _optional_text(row.get("PMMCombo")),
        "PMMArea": _finite(row.get("PMMArea"), "PMMArea"),
        "PMMRatio": None if row.get("PMMRatio") is None else _finite(row.get("PMMRatio"), "PMMRatio"),
        "ErrorSummary": _optional_text(row.get("ErrorSummary")),
        "WarningSummary": _optional_text(row.get("WarningSummary")),
    }


def _source_row_id(row: Mapping[str, Any]) -> str:
    encoded = json.dumps(_canonical_row_payload(row), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "etabs-design-column:sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ColumnDesignRebarEvidenceBundle:
    model_fingerprint: str
    evidence_epoch_id: str
    identity: ColumnDesignRebarIdentity
    source_length_unit: Unit
    unit_provenance_refs: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    source_api: str = SOURCE_API

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        if self.source_api != SOURCE_API:
            raise ColumnDesignRebarEvidenceError("source API identity mismatch")
        if self.source_length_unit not in {UNIT_MM, UNIT_M}:
            raise ColumnDesignRebarEvidenceError("source length unit must be explicit mm or m")
        refs = tuple(_text(item, "unit_provenance_ref") for item in self.unit_provenance_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnDesignRebarEvidenceError("unit_provenance_refs must be nonempty and unique")
        object.__setattr__(self, "unit_provenance_refs", refs)
        frozen: list[Mapping[str, Any]] = []
        ids: set[str] = set()
        for raw in self.rows:
            row = _canonical_row_payload(raw)
            if row["FrameName"] != self.identity.object_name:
                raise ColumnDesignRebarEvidenceError("design result FrameName does not match exact requested object_name")
            if row["MyOption"] not in (1, 2):
                raise ColumnDesignRebarEvidenceError("MyOption must be CSI Check=1 or Design=2")
            if row["Location"] < 0.0 or row["PMMArea"] < 0.0:
                raise ColumnDesignRebarEvidenceError("Location and PMMArea must be >= 0")
            row_id = _source_row_id(row)
            if row_id in ids:
                raise ColumnDesignRebarEvidenceError("duplicate exact design-result row identity")
            ids.add(row_id)
            row["source_row_id"] = row_id
            frozen.append(MappingProxyType(row))
        object.__setattr__(self, "rows", tuple(frozen))

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "VS6_P8A_COLUMN_DESIGN_REBAR_EVIDENCE",
            "model_fingerprint": self.model_fingerprint,
            "evidence_epoch_id": self.evidence_epoch_id,
            "identity": self.identity.as_dict(),
            "source_api": self.source_api,
            "source_length_unit": self.source_length_unit.identifier,
            "source_area_unit": f"{self.source_length_unit.identifier}2",
            "unit_provenance_refs": list(self.unit_provenance_refs),
            "row_count": len(self.rows),
            "rows": [dict(row) for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebar:
    component_id: str
    section_identity: str
    required_as_mm2: float | None
    status: str
    authority: str
    selection_rule: str
    governing_source_row_ids: tuple[str, ...]
    governing_combinations: tuple[str, ...]
    governing_locations_mm: tuple[float, ...]
    evidence_epoch_id: str
    model_fingerprint: str
    source_refs: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        return self.status == STATUS_PROVEN and self.authority == "ETABS_REQUIRED_REBAR" and self.required_as_mm2 is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "section_identity": self.section_identity,
            "required_as_mm2": self.required_as_mm2,
            "unit": "mm2",
            "status": self.status,
            "authority": self.authority,
            "selection_rule": self.selection_rule,
            "governing_source_row_ids": list(self.governing_source_row_ids),
            "governing_combinations": list(self.governing_combinations),
            "governing_locations_mm": list(self.governing_locations_mm),
            "evidence_epoch_id": self.evidence_epoch_id,
            "model_fingerprint": self.model_fingerprint,
            "source_refs": list(self.source_refs),
        }


def build_column_design_rebar_evidence(*, model_fingerprint: str, identity: ColumnDesignRebarIdentity, rows: Sequence[Mapping[str, Any]], source_length_unit: Unit, unit_provenance_refs: Sequence[str]) -> ColumnDesignRebarEvidenceBundle:
    fingerprint = _text(model_fingerprint, "model_fingerprint")
    provisional = ColumnDesignRebarEvidenceBundle(fingerprint, "epoch:vs6-p8a-column-design-rebar:pending", identity, source_length_unit, tuple(unit_provenance_refs), tuple(rows))
    canonical_rows = sorted(json.dumps(dict(row), sort_keys=True, separators=(",", ":"), ensure_ascii=True) for row in provisional.rows)
    payload = {"model_fingerprint": fingerprint, "identity": identity.as_dict(), "source_api": SOURCE_API, "source_length_unit": source_length_unit.identifier, "unit_provenance_refs": list(provisional.unit_provenance_refs), "rows": canonical_rows}
    epoch = "epoch:vs6-p8a-column-design-rebar:sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
    return ColumnDesignRebarEvidenceBundle(fingerprint, epoch, identity, source_length_unit, tuple(unit_provenance_refs), tuple(rows))


def resolve_etabs_required_rebar(evidence: ColumnDesignRebarEvidenceBundle | None, *, expected_model_fingerprint: str, expected_component_id: str, expected_section_identity: str) -> EtabsRequiredRebar:
    fingerprint = _text(expected_model_fingerprint, "expected_model_fingerprint")
    component = _text(expected_component_id, "expected_component_id")
    section = _text(expected_section_identity, "expected_section_identity")
    base_refs = (SOURCE_API_REF, SOURCE_UNIT_API_REF)
    if evidence is None:
        return EtabsRequiredRebar(component, section, None, STATUS_NO_DATA, "NOT_SELECTED", SELECTION_RULE, (), (), (), "NO_EVIDENCE_EPOCH", fingerprint, base_refs)
    refs = tuple(dict.fromkeys((*base_refs, *evidence.unit_provenance_refs)))
    if evidence.model_fingerprint != fingerprint or evidence.identity.component_id != component or evidence.identity.section_identity != section:
        return EtabsRequiredRebar(component, section, None, STATUS_BLOCKED, "NOT_SELECTED", SELECTION_RULE, (), (), (), evidence.evidence_epoch_id, evidence.model_fingerprint, refs)
    design_rows = tuple(row for row in evidence.rows if int(row["MyOption"]) == 2)
    if not design_rows:
        return EtabsRequiredRebar(component, section, None, STATUS_NO_DATA, "NOT_SELECTED", SELECTION_RULE, (), (), (), evidence.evidence_epoch_id, evidence.model_fingerprint, refs)
    if any(row.get("ErrorSummary") not in (None, "") for row in design_rows):
        return EtabsRequiredRebar(component, section, None, STATUS_BLOCKED, "NOT_SELECTED", SELECTION_RULE, (), (), (), evidence.evidence_epoch_id, evidence.model_fingerprint, refs)
    factor = conversion_factor(evidence.source_length_unit, UNIT_MM)
    area_factor = factor * factor
    converted = tuple((float(row["PMMArea"]) * float(area_factor), row) for row in design_rows)
    maximum = max(value for value, _ in converted)
    if maximum <= 0.0 or not math.isfinite(maximum):
        return EtabsRequiredRebar(component, section, None, STATUS_NO_DATA, "NOT_SELECTED", SELECTION_RULE, (), (), (), evidence.evidence_epoch_id, evidence.model_fingerprint, refs)
    governing = tuple(row for value, row in converted if math.isclose(value, maximum, rel_tol=0.0, abs_tol=1e-9))
    location_factor = conversion_factor(evidence.source_length_unit, UNIT_MM)
    combos = tuple(sorted({str(row["PMMCombo"]) for row in governing if row.get("PMMCombo")}))
    locations = tuple(sorted(float(row["Location"]) * float(location_factor) for row in governing))
    source_rows = tuple(sorted(str(row["source_row_id"]) for row in governing))
    refs = tuple(dict.fromkeys((*refs, evidence.evidence_epoch_id, *source_rows)))
    return EtabsRequiredRebar(component, section, maximum, STATUS_PROVEN, "ETABS_REQUIRED_REBAR", SELECTION_RULE, source_rows, combos, locations, evidence.evidence_epoch_id, evidence.model_fingerprint, refs)


def _parse_summary_results(raw: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, tuple) or len(raw) != 14:
        raise ColumnDesignRebarEvidenceError("GetSummaryResultsColumn returned an unsupported COM result shape; expected 14 values")
    number_items = int(raw[0])
    arrays = raw[1:13]
    ret = raw[13]
    if ret not in (None, 0):
        raise ColumnDesignRebarEvidenceError(f"GetSummaryResultsColumn returned nonzero code {ret}")
    if any(not isinstance(values, (tuple, list)) for values in arrays) or any(len(values) != number_items for values in arrays):
        raise ColumnDesignRebarEvidenceError("GetSummaryResultsColumn population shape mismatch")
    names = ("FrameName", "MyOption", "Location", "PMMCombo", "PMMArea", "PMMRatio", "VMajorCombo", "AVMajor", "VMinorCombo", "AVMinor", "ErrorSummary", "WarningSummary")
    return tuple({name: arrays[column][index] for column, name in enumerate(names)} for index in range(number_items))


def capture_live_column_design_rebar_evidence(*, sap_model: Any, model_fingerprint: str, identity: ColumnDesignRebarIdentity) -> ColumnDesignRebarEvidenceBundle:
    """Read already-generated design results; never runs design or mutates ETABS units."""
    before = read_etabs_unit_snapshot(sap_model)
    if before.present_units_api != "GetPresentUnits_2":
        raise ColumnDesignRebarEvidenceError("P8A requires source-specific GetPresentUnits_2 provenance for direct API data")
    source_length_unit = resolve_etabs_present_length_unit(before.present_length_unit)
    getter = getattr(getattr(sap_model, "DesignConcrete", None), "GetSummaryResultsColumn", None)
    if getter is None:
        raise ColumnDesignRebarEvidenceError("DesignConcrete.GetSummaryResultsColumn is unavailable")
    rows = _parse_summary_results(getter(identity.object_name))
    after = read_etabs_unit_snapshot(sap_model)
    before_key = (before.present_units_api, before.present_units, before.present_force_unit, before.present_length_unit, before.present_temperature_unit)
    after_key = (after.present_units_api, after.present_units, after.present_force_unit, after.present_length_unit, after.present_temperature_unit)
    if after_key != before_key:
        raise ColumnDesignRebarEvidenceError("ETABS present-unit provenance changed during design-result capture")
    refs = (SOURCE_API_REF, SOURCE_UNIT_API_REF, f"present_units={before.present_units}", f"present_length_unit={source_length_unit.identifier}")
    return build_column_design_rebar_evidence(model_fingerprint=model_fingerprint, identity=identity, rows=rows, source_length_unit=source_length_unit, unit_provenance_refs=refs)


__all__ = ["SOURCE_API", "SOURCE_API_REF", "SOURCE_UNIT_API_REF", "SELECTION_RULE", "STATUS_PROVEN", "STATUS_NO_DATA", "STATUS_BLOCKED", "ColumnDesignRebarEvidenceError", "ColumnDesignRebarIdentity", "ColumnDesignRebarEvidenceBundle", "EtabsRequiredRebar", "build_column_design_rebar_evidence", "resolve_etabs_required_rebar", "capture_live_column_design_rebar_evidence"]
