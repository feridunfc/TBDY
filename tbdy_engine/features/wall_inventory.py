"""Evidence/identity-only ETABS area-object inventory (Wall Slice 1)."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Callable

from tbdy_engine.contracts.models import freeze_data

AREA_SOURCE = "area_assignments_summary"
PROPERTY_SOURCE = "wall_section_properties"
PIER_SOURCE = "pier_assignments"


class WallInventoryStatus(StrEnum):
    STRUCTURAL_WALL_CANDIDATE = "STRUCTURAL_WALL_CANDIDATE"
    POSITIVELY_EXCLUDED = "POSITIVELY_EXCLUDED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class WallInventorySourceRef:
    source_family: str
    row_digest: str
    row: Mapping[str, Any]
    area_row_token: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "row", freeze_data(dict(self.row)))

    def as_dict(self) -> dict[str, Any]:
        return {"source_family": self.source_family, "row_digest": self.row_digest,
                "area_row_token": self.area_row_token, "row": dict(self.row)}


@dataclass(frozen=True, slots=True)
class WallInventoryDiagnostic:
    code: str
    message: str
    source_families: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message,
                "source_families": list(self.source_families)}


@dataclass(frozen=True, slots=True)
class WallInventoryRecord:
    wall_object_id: str | None
    anonymous_inventory_record_id: str | None
    model_fingerprint: str
    etabs_area_unique_name: str | None
    area_label: str | None
    story: str | None
    assigned_area_property: str | None
    material_reference: str | None
    pier_assignment: str | None
    classification_status: WallInventoryStatus | str
    classification_evidence: tuple[str, ...]
    source_row_references: tuple[WallInventorySourceRef, ...]
    diagnostics: tuple[WallInventoryDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        status = WallInventoryStatus(str(self.classification_status))
        object.__setattr__(self, "classification_status", status)
        identified = self.wall_object_id is not None
        anonymous = self.anonymous_inventory_record_id is not None
        if identified == anonymous:
            raise ValueError("Exactly one inventory record identity is required")
        if identified and _identifier_text(self.wall_object_id) is None:
            raise ValueError("Identified record requires nonblank wall_object_id")
        if anonymous and _identifier_text(self.anonymous_inventory_record_id) is None:
            raise ValueError("Anonymous record requires nonblank anonymous ID")
        if identified and _identifier_text(self.etabs_area_unique_name) is None:
            raise ValueError("Identified record requires nonblank authoritative UniqueName")
        if anonymous and self.etabs_area_unique_name is not None:
            raise ValueError("Anonymous record cannot carry authoritative UniqueName")
        if anonymous and status != WallInventoryStatus.UNRESOLVED:
            raise ValueError("Anonymous record must be UNRESOLVED")

    @property
    def inventory_record_id(self) -> str:
        if self.wall_object_id is not None:
            return self.wall_object_id
        if self.anonymous_inventory_record_id is not None:
            return self.anonymous_inventory_record_id
        raise RuntimeError("Invalid WallInventoryRecord identity")

    def as_dict(self) -> dict[str, Any]:
        return {"wall_object_id": self.wall_object_id,
                "anonymous_inventory_record_id": self.anonymous_inventory_record_id,
                "model_fingerprint": self.model_fingerprint,
                "etabs_area_unique_name": self.etabs_area_unique_name,
                "area_label": self.area_label, "story": self.story,
                "assigned_area_property": self.assigned_area_property,
                "material_reference": self.material_reference,
                "pier_assignment": self.pier_assignment,
                "classification_status": self.classification_status.value,
                "classification_evidence": list(self.classification_evidence),
                "source_row_references": [ref.as_dict() for ref in self.source_row_references],
                "diagnostics": [item.as_dict() for item in self.diagnostics]}


@dataclass(frozen=True, slots=True)
class WallInventoryReconciliation:
    discovered_inventory_objects: int
    identified_object_count: int
    anonymous_record_count: int
    structural_wall_candidates: int
    positively_excluded_objects: int
    unresolved_objects: int
    input_area_source_row_count: int
    accounted_area_source_row_count: int
    unique_accounted_area_reference_count: int
    duplicate_area_reference_count: int
    object_reconciled: bool
    area_source_rows_reconciled: bool

    def __post_init__(self) -> None:
        classified = self.structural_wall_candidates + self.positively_excluded_objects + self.unresolved_objects
        if classified != self.discovered_inventory_objects or not self.object_reconciled:
            raise ValueError("Object reconciliation failed")
        if self.identified_object_count + self.anonymous_record_count != self.discovered_inventory_objects:
            raise ValueError("Identity counts do not reconcile")
        if self.accounted_area_source_row_count != self.input_area_source_row_count or not self.area_source_rows_reconciled:
            raise ValueError("Area-source-row reconciliation failed")
        if self.unique_accounted_area_reference_count != self.input_area_source_row_count or self.duplicate_area_reference_count:
            raise ValueError("Area rows are not accounted exactly once")

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class WallInventory:
    model_fingerprint: str
    records: tuple[WallInventoryRecord, ...]
    reconciliation: WallInventoryReconciliation
    source_contract_status: Mapping[str, str]

    def __post_init__(self) -> None:
        if _generic_text(self.model_fingerprint) is None:
            raise ValueError("model_fingerprint is required")
        if len(self.records) != self.reconciliation.discovered_inventory_objects:
            raise ValueError("Record count does not reconcile")
        object.__setattr__(self, "source_contract_status",
                           MappingProxyType(dict(self.source_contract_status)))

    def as_dict(self) -> dict[str, Any]:
        return {"inventory_contract": "WALL_INVENTORY_V1",
                "model_fingerprint": self.model_fingerprint,
                "source_contract_status": dict(self.source_contract_status),
                "source_contract_status_note":
                    "Contract metadata only; does not assert live acquisition provenance for input rows.",
                "records": [record.as_dict() for record in self.records],
                "reconciliation": self.reconciliation.as_dict()}


@dataclass(frozen=True, slots=True)
class _AreaRow:
    row: Mapping[str, Any]
    token: str
    unique_name: str | None


_UNIQUE = ("UniqueName", "Unique Name", "ObjectUniqueName", "Object Unique Name")
_LABEL = ("Label", "Area", "Area Label", "Object Label")
_STORY = ("Story", "Story Name")
_PROPERTY = ("SectionProperty", "Section Property", "SectProp", "Property", "Property Name")
_PROPERTY_NAME = ("Name", "SectionProperty", "Section Property", "SectProp", "Property")
_MATERIAL = ("Material", "Material Name", "MatProp")
_PIER = ("Pier", "Pier Label", "PierName", "Pier Name")
_TYPE = ("PropertyType", "Property Type", "PropType", "Type", "ObjectType", "Object Type", "Classification")
_WALL_TYPES = {"wall", "shear wall", "structural wall", "pier"}
_EXCLUDED_TYPES = {"deck", "floor", "opening", "ramp", "slab", "nonstructural", "non-structural"}


def build_wall_inventory(*, model_fingerprint: str,
                         area_assignment_rows: Sequence[Mapping[str, Any]],
                         wall_property_rows: Sequence[Mapping[str, Any]] = (),
                         pier_assignment_rows: Sequence[Mapping[str, Any]] = ()) -> WallInventory:
    fingerprint = _generic_text(model_fingerprint)
    if fingerprint is None:
        raise ValueError("model_fingerprint is required")
    prepared = _prepare_area_rows(area_assignment_rows)
    identified: defaultdict[str, list[_AreaRow]] = defaultdict(list)
    anonymous: list[_AreaRow] = []
    for item in prepared:
        if item.unique_name is None:
            anonymous.append(item)
        else:
            identified[item.unique_name].append(item)
    properties = _index_exact(wall_property_rows, _PROPERTY_NAME)
    piers_by_unique = _index_exact(pier_assignment_rows, _UNIQUE)
    piers_by_story_label = _index_story_label_fallback(pier_assignment_rows)
    records = [_build_record(fingerprint, tuple(rows), unique, None, properties,
                             piers_by_unique, piers_by_story_label)
               for unique, rows in sorted(identified.items())]
    records.extend(_build_record(
        fingerprint, (item,), None,
        "anonymous-area:" + _sha(f"{fingerprint}\x1f{item.token}"), properties,
        piers_by_unique, piers_by_story_label)
        for item in sorted(anonymous, key=lambda value: value.token))
    records.sort(key=lambda record: record.inventory_record_id)
    area_tokens = [ref.area_row_token for record in records
                   for ref in record.source_row_references
                   if ref.source_family == AREA_SOURCE and ref.area_row_token is not None]
    counts, statuses = Counter(area_tokens), Counter(record.classification_status for record in records)
    reconciliation = WallInventoryReconciliation(
        len(records), sum(r.wall_object_id is not None for r in records),
        sum(r.wall_object_id is None for r in records),
        statuses[WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE],
        statuses[WallInventoryStatus.POSITIVELY_EXCLUDED], statuses[WallInventoryStatus.UNRESOLVED],
        len(area_assignment_rows), len(area_tokens), len(counts),
        sum(n - 1 for n in counts.values() if n > 1), True,
        len(area_tokens) == len(area_assignment_rows))
    return WallInventory(fingerprint, tuple(records), reconciliation,
                         {AREA_SOURCE: "VERIFIED_LIVE", PROPERTY_SOURCE: "VERIFIED_LIVE",
                          PIER_SOURCE: "VERIFIED_LIVE"})


def _build_record(fingerprint: str, area_rows: Sequence[_AreaRow], unique: str | None,
                  anonymous_id: str | None,
                  properties: Mapping[str, tuple[Mapping[str, Any], ...]],
                  piers_by_unique: Mapping[str, tuple[Mapping[str, Any], ...]],
                  piers_by_story_label: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]]) -> WallInventoryRecord:
    diagnostics: list[WallInventoryDiagnostic] = []
    evidence: set[str] = set()
    refs = [_ref(AREA_SOURCE, item.row, item.token) for item in area_rows]
    labels, stories = _values(area_rows, _LABEL), _values(area_rows, _STORY)
    property_values = _values(area_rows, _PROPERTY)
    types = _values(area_rows, _TYPE, identifier=False)
    for values, code in ((labels, "CONFLICTING_AREA_LABEL"),
                         (stories, "CONFLICTING_STORY"),
                         (property_values, "CONFLICTING_AREA_PROPERTY"),
                         (types, "CONFLICTING_AREA_CLASSIFICATION")):
        if len(values) > 1:
            diagnostics.append(_diag(code, "Grouped area rows contain conflicting identity facts", AREA_SOURCE))
    if unique is None:
        diagnostics.append(_diag("AREA_UNIQUE_NAME_MISSING", "Missing authoritative string UniqueName", AREA_SOURCE))
    label, story, prop, observed_type = map(_only, (labels, stories, property_values, types))
    if story is None:
        diagnostics.append(_diag("STORY_MISSING", "Area object has no resolved string story", AREA_SOURCE))

    property_matches = properties.get(prop, ()) if prop is not None else ()
    material = None
    if property_matches:
        refs.extend(_ref(PROPERTY_SOURCE, row) for row in property_matches)
        evidence.add("ASSIGNED_PROPERTY_MATCHES_VERIFIED_WALL_PROPERTY")
        materials = {_first_identifier(row, _MATERIAL) for row in property_matches} - {None}
        if len(materials) > 1:
            diagnostics.append(_diag("CONFLICTING_PROPERTY_JOIN", "Conflicting material references", PROPERTY_SOURCE))
        else:
            material = _only(materials)

    pier_matches = piers_by_unique.get(unique, ()) if unique is not None else ()
    if not pier_matches and story is not None and label is not None:
        pier_matches = piers_by_story_label.get((story, label), ())
    pier = None
    if pier_matches:
        refs.extend(_ref(PIER_SOURCE, row) for row in pier_matches)
        evidence.add("PIER_ASSIGNMENT_PRESENT")
        piers = {_first_identifier(row, _PIER) for row in pier_matches} - {None}
        if len(piers) > 1:
            diagnostics.append(_diag("CONFLICTING_PIER_JOIN", "Conflicting pier assignments", PIER_SOURCE))
        else:
            pier = _only(piers)

    token = (observed_type or "").casefold()
    explicit_wall, explicit_excluded = token in _WALL_TYPES, token in _EXCLUDED_TYPES
    if explicit_wall:
        evidence.add("EXPLICIT_WALL_CLASSIFICATION")
    if explicit_excluded:
        evidence.add("EXPLICIT_NON_WALL_CLASSIFICATION")
    positive_wall = bool(property_matches or pier_matches or explicit_wall)
    if explicit_excluded and positive_wall:
        diagnostics.append(_diag("CONFLICTING_CLASSIFICATION_EVIDENCE", "Non-wall and wall evidence conflict", AREA_SOURCE))
    if positive_wall and prop is None:
        diagnostics.append(_diag("WALL_PROPERTY_ASSIGNMENT_MISSING", "Wall candidate lacks a string property assignment", AREA_SOURCE))
    elif positive_wall and not property_matches:
        diagnostics.append(_diag("WALL_PROPERTY_JOIN_MISSING", "No exact wall-property join", AREA_SOURCE, PROPERTY_SOURCE))

    if diagnostics:
        status = WallInventoryStatus.UNRESOLVED
    elif explicit_excluded:
        status = WallInventoryStatus.POSITIVELY_EXCLUDED
    elif positive_wall:
        status = WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE
    else:
        status = WallInventoryStatus.UNRESOLVED
        diagnostics.append(_diag("CLASSIFICATION_EVIDENCE_MISSING", "No wall or exclusion evidence", AREA_SOURCE))
    object_id = None if unique is None else "wall-area:" + _sha(f"{fingerprint}\x1f{unique}")
    return WallInventoryRecord(
        object_id, anonymous_id, fingerprint, unique, label, story, prop, material, pier,
        status, tuple(sorted(evidence)),
        tuple(sorted(refs, key=lambda ref: (ref.source_family, ref.area_row_token or "", ref.row_digest))),
        tuple(diagnostics))


def _prepare_area_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[_AreaRow, ...]:
    canonical_rows = [(_canonical(row), dict(row)) for row in rows]
    canonical_rows.sort(key=lambda item: item[0])
    occurrences: Counter[str] = Counter()
    prepared = []
    for canonical, row in canonical_rows:
        digest = _sha(canonical)
        occurrences[digest] += 1
        prepared.append(_AreaRow(freeze_data(row),
                                 f"{AREA_SOURCE}:{digest}:{occurrences[digest]}",
                                 _first_identifier(row, _UNIQUE)))
    return tuple(prepared)


def _index_exact(rows: Sequence[Mapping[str, Any]], aliases: Sequence[str]) -> dict[str, tuple[Mapping[str, Any], ...]]:
    index: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for raw in rows:
        value = _first_identifier(raw, aliases)
        if value is not None:
            index[value].append(dict(raw))
    return {key: tuple(sorted(values, key=_canonical)) for key, values in index.items()}


def _index_story_label_fallback(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], tuple[Mapping[str, Any], ...]]:
    index: defaultdict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for raw in rows:
        unique_present, unique_raw = _raw_alias(raw, _UNIQUE)
        if unique_present and unique_raw is not None and unique_raw != "":
            # Valid strings are exact-only; invalid non-strings are not permission for fallback.
            if not isinstance(unique_raw, str) or unique_raw.strip():
                continue
        story, label = _first_identifier(raw, _STORY), _first_identifier(raw, _LABEL)
        if story is not None and label is not None:
            index[(story, label)].append(dict(raw))
    return {key: tuple(sorted(values, key=_canonical)) for key, values in index.items()}


def _values(rows: Sequence[_AreaRow], aliases: Sequence[str], *, identifier: bool = True) -> set[str]:
    getter = _first_identifier if identifier else _first_generic
    return {value for row in rows if (value := getter(row.row, aliases)) is not None}


def _first_identifier(row: Mapping[str, Any], aliases: Sequence[str]) -> str | None:
    return _first(row, aliases, _identifier_text)


def _first_generic(row: Mapping[str, Any], aliases: Sequence[str]) -> str | None:
    return _first(row, aliases, _generic_text)


def _first(row: Mapping[str, Any], aliases: Sequence[str], converter: Callable[[Any], str | None]) -> str | None:
    columns = {str(key).strip().casefold(): value for key, value in row.items()}
    for alias in aliases:
        value = converter(columns.get(alias.casefold()))
        if value is not None:
            return value
    return None


def _raw_alias(row: Mapping[str, Any], aliases: Sequence[str]) -> tuple[bool, Any]:
    columns = {str(key).strip().casefold(): value for key, value in row.items()}
    for alias in aliases:
        key = alias.casefold()
        if key in columns:
            return True, columns[key]
    return False, None


def _identifier_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _generic_text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _only(values: set[str]) -> str | None:
    return next(iter(values)) if len(values) == 1 else None


def _ref(source: str, row: Mapping[str, Any], token: str | None = None) -> WallInventorySourceRef:
    return WallInventorySourceRef(source, _sha(_canonical(row)), row, token)


def _diag(code: str, message: str, *sources: str) -> WallInventoryDiagnostic:
    return WallInventoryDiagnostic(code, message, tuple(sources))


def _canonical(row: Mapping[str, Any]) -> str:
    return json.dumps(dict(row), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["AREA_SOURCE", "PIER_SOURCE", "PROPERTY_SOURCE", "WallInventory",
           "WallInventoryDiagnostic", "WallInventoryRecord", "WallInventoryReconciliation",
           "WallInventorySourceRef", "WallInventoryStatus", "build_wall_inventory"]
