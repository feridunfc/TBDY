"""Generic canonical wall-geometry fact resolution for P2.10 Pack A.

One resolver preserves WallInventory identity and resolves reusable facts. It is
not an engineering rule engine: no TBDY limits, applicability verdicts, ratios,
or PASS/FAIL decisions live here.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.unit_metadata import normalize_length_to_mm, trusted_length_unit_from_context
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.features.wall_inventory import WallInventory, WallInventoryRecord, WallInventoryStatus
from tbdy_engine.features.wall_geometry_contract import WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS

RESOLVER_NAME = "wall_geometry_fact_resolver"
_BASE_FACTS = ("wall_thickness_mm", "wall_length_mm", "story_height_mm")
_ALL_FACTS = _BASE_FACTS + tuple(WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS)
_PROPERTY_TABLE_KEYS = ("wall_section_properties", "wall_section_data")
_STORY_TABLE_KEYS = ("story_definitions",)
_PROPERTY_NAME_ALIASES = ("Name", "SectionProperty", "Section Property", "SectProp", "Property")
_THICKNESS_LIVE_ALIASES = ("Thickness", "Wall Thickness", "Total Thickness")
_STORY_NAME_ALIASES = ("Story", "Name")
_STORY_HEIGHT_ALIASES = ("Height", "Story Height")


def _identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _columns(table: CanonicalTable) -> dict[str, str]:
    found: dict[str, str] = {}
    for column in table.columns:
        found.setdefault(str(column).casefold(), str(column))
    for row in table.rows:
        for key in row:
            found.setdefault(str(key).casefold(), str(key))
    return found


def _column(table: CanonicalTable, aliases: Sequence[str]) -> str | None:
    available = _columns(table)
    for alias in aliases:
        match = available.get(str(alias).casefold())
        if match is not None:
            return match
    return None


def _row_value(row: Mapping[str, Any], column: str | None) -> Any:
    if column is None:
        return None
    if column in row:
        return row[column]
    folded = column.casefold()
    for key, value in row.items():
        if str(key).casefold() == folded:
            return value
    return None


def _table_index(tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]) -> dict[str, CanonicalTable]:
    indexed: dict[str, CanonicalTable] = {}
    items = tables.items() if isinstance(tables, Mapping) else ((table.table_key, table) for table in tables)
    for key, table in items:
        indexed[str(key)] = table
        indexed.setdefault(table.table_key, table)
        if table.actual_table_name:
            indexed.setdefault(table.actual_table_name, table)
    return indexed


def _first_table(index: Mapping[str, CanonicalTable], keys: Sequence[str]) -> CanonicalTable | None:
    for key in keys:
        if key in index:
            return index[key]
    return None


class WallGeometryFactResolver:
    """Resolve Pack A facts without changing WallInventory classification."""

    def __init__(self, contract_bundle: ContractBundle, tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]) -> None:
        self.contract_bundle = contract_bundle
        self.tables = _table_index(tables)
        catalog = contract_bundle.catalog("feature_catalog.yaml").get("features", {})
        self.feature_defs: dict[str, Mapping[str, Any]] = {}
        for feature_id in _BASE_FACTS:
            feature = catalog.get(feature_id)
            if not isinstance(feature, Mapping):
                raise ValueError(f"Existing canonical feature is required: {feature_id}")
            self.feature_defs[feature_id] = feature
        self.feature_defs.update(WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS)
        self.property_table = _first_table(self.tables, _PROPERTY_TABLE_KEYS)
        self.story_table = _first_table(self.tables, _STORY_TABLE_KEYS)
        self._property_rows = self._index_property_rows()

    def build_snapshots(self, inventory: WallInventory, *, provided_features_by_wall: Mapping[str, Mapping[str, FeatureValue]] | None = None) -> tuple[FeatureSnapshot, ...]:
        provided = provided_features_by_wall or {}
        snapshots: list[FeatureSnapshot] = []
        for record in inventory.records:
            if record.classification_status != WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE:
                continue
            if record.wall_object_id is None:
                raise ValueError("Structural-wall candidate must retain wall_object_id")
            snapshots.append(self.resolve_candidate(record, provided_features=provided.get(record.wall_object_id, {})))
        return tuple(snapshots)

    def resolve_candidate(self, record: WallInventoryRecord, *, provided_features: Mapping[str, FeatureValue] | None = None) -> FeatureSnapshot:
        if record.classification_status != WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE:
            raise ValueError("Wall geometry facts are resolved only for structural-wall candidates")
        if record.wall_object_id is None:
            raise ValueError("Structural-wall candidate must retain wall_object_id")
        provided = dict(provided_features or {})
        unknown = sorted(set(provided) - set(_ALL_FACTS))
        if unknown:
            raise ValueError("Unknown provided Pack A fact(s): " + ", ".join(unknown))
        for name, value in provided.items():
            if not isinstance(value, FeatureValue) or value.feature_name != name:
                raise TypeError("provided_features must map canonical feature names to matching FeatureValue objects")

        features: dict[str, FeatureValue] = {}
        for feature_id in _ALL_FACTS:
            if feature_id in provided:
                features[feature_id] = provided[feature_id]
            elif feature_id == "wall_thickness_mm":
                features[feature_id] = self._property_length_fact(record, feature_id, _THICKNESS_LIVE_ALIASES)
            elif feature_id == "wall_length_mm":
                features[feature_id] = self._property_length_fact(record, feature_id, ())
            elif feature_id == "story_height_mm":
                features[feature_id] = self._story_height_fact(record)
            else:
                definition = self.feature_defs[feature_id]
                features[feature_id] = self._missing(feature_id, str(definition.get("unit") or ""), str(definition.get("semantic_role") or "UNKNOWN"), "Canonical applicability/topology fact was not supplied; no inference is permitted")

        identity = {
            "wall_object_id": record.wall_object_id,
            "etabs_area_unique_name": record.etabs_area_unique_name,
            "story": record.story,
            "area_label": record.area_label,
            "section": record.assigned_area_property,
            "assigned_wall_property": record.assigned_area_property,
            "model_fingerprint": record.model_fingerprint,
        }
        return FeatureSnapshot(
            component_type="wall",
            component_id=record.wall_object_id,
            identity=identity,
            features=features,
            evidence_by_feature={name: value.evidence for name, value in features.items()},
            diagnostics=tuple(diag for value in features.values() for diag in value.diagnostics),
        )

    def _index_property_rows(self) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        table = self.property_table
        if table is None:
            return {}
        name_column = _column(table, _PROPERTY_NAME_ALIASES)
        if name_column is None:
            return {}
        indexed: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in table.rows:
            name = _identifier(_row_value(row, name_column))
            if name is not None:
                indexed[name].append(row)
        return {key: tuple(rows) for key, rows in indexed.items()}

    def _aliases_for(self, feature_id: str, extra: Sequence[str] = ()) -> tuple[str, ...]:
        source = self.feature_defs[feature_id].get("source") or {}
        aliases = tuple(str(value) for value in (source.get("field_aliases") or ()))
        return tuple(dict.fromkeys((*extra, *aliases)))

    def _property_length_fact(self, record: WallInventoryRecord, feature_id: str, extra_aliases: Sequence[str]) -> FeatureValue:
        definition = self.feature_defs[feature_id]
        role = str(definition.get("semantic_role") or "GEOMETRY")
        table = self.property_table
        if table is None:
            return self._missing(feature_id, "mm", role, "Canonical wall-property table is unavailable")
        assigned = _identifier(record.assigned_area_property)
        if assigned is None:
            return self._missing(feature_id, "mm", role, "Wall candidate has no authoritative string property assignment")
        matches = self._property_rows.get(assigned, ())
        if not matches:
            return self._missing(feature_id, "mm", role, "No exact wall-property identity match exists")
        if len(matches) != 1:
            return self._partial(feature_id, table, None, matches[0], None, "mm", role, "Exact wall-property identity is not unique; no row was selected arbitrarily")
        row = matches[0]
        column = _column(table, self._aliases_for(feature_id, extra_aliases))
        if column is None:
            return self._partial(feature_id, table, None, row, None, "mm", role, "No contracted source column is present for this canonical length fact")
        return self._normalized_length(feature_id, table, column, row, role)

    def _story_height_fact(self, record: WallInventoryRecord) -> FeatureValue:
        definition = self.feature_defs["story_height_mm"]
        role = str(definition.get("semantic_role") or "GEOMETRY")
        table = self.story_table
        if table is None:
            return self._missing("story_height_mm", "mm", role, "Canonical Story Definitions table is unavailable")
        story = _identifier(record.story)
        if story is None:
            return self._missing("story_height_mm", "mm", role, "WallInventory story identity is unavailable")
        name_column = _column(table, _STORY_NAME_ALIASES)
        height_column = _column(table, self._aliases_for("story_height_mm", _STORY_HEIGHT_ALIASES))
        if name_column is None or height_column is None:
            return self._partial("story_height_mm", table, height_column, None, None, "mm", role, "Story Definitions lacks a contracted story or height column")
        matches = tuple(row for row in table.rows if _identifier(_row_value(row, name_column)) == story)
        if not matches:
            return self._missing("story_height_mm", "mm", role, "No exact Story Definitions identity match exists")
        if len(matches) != 1:
            return self._partial("story_height_mm", table, height_column, matches[0], _row_value(matches[0], height_column), "mm", role, "Story identity is not unique; no height was selected arbitrarily")
        return self._normalized_length("story_height_mm", table, height_column, matches[0], role)

    def _normalized_length(self, feature_id: str, table: CanonicalTable, column: str, row: Mapping[str, Any], role: str) -> FeatureValue:
        raw = _row_value(row, column)
        length_unit = trusted_length_unit_from_context(table.units)
        if length_unit is None:
            return self._partial(feature_id, table, column, row, raw, "mm", role, "CanonicalTable.units does not contain a trusted resolved ETABS UnitContext; unit is not guessed")
        normalization = normalize_length_to_mm(raw, raw_unit=length_unit, unit_context_trusted=True)
        if normalization.normalized_value is None or normalization.normalized_unit != "mm":
            return self._partial(feature_id, table, column, row, raw, "mm", role, "Length cannot be normalized to mm from the explicit source UnitContext")
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name or table.table_key,
            source_column=column,
            source_row={"row": dict(row), "source_unit_authority": "CanonicalTable.units", "unit_context": dict(table.units or {}), "unit_normalization": normalization.as_dict()},
            raw_value=raw,
            normalized_value=normalization.normalized_value,
            unit="mm",
            resolver=RESOLVER_NAME,
        )
        return FeatureValue(feature_name=feature_id, value=normalization.normalized_value, unit="mm", semantic_role=role, status=FeatureValueStatus.RESOLVED, evidence=[evidence])

    @staticmethod
    def _missing(feature_id: str, unit: str, role: str, reason: str) -> FeatureValue:
        evidence = FeatureEvidence(evidence_status=FeatureEvidenceStatus.MISSING, unit=unit, resolver=RESOLVER_NAME, reason=reason)
        return FeatureValue(feature_name=feature_id, value=None, unit=unit, semantic_role=role, status=FeatureValueStatus.MISSING, evidence=[evidence])

    @staticmethod
    def _partial(feature_id: str, table: CanonicalTable, column: str | None, row: Mapping[str, Any] | None, raw_value: Any, unit: str, role: str, reason: str) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.PARTIAL,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name or table.table_key,
            source_column=column,
            source_row=dict(row or {}),
            raw_value=raw_value,
            normalized_value=None,
            unit=unit,
            resolver=RESOLVER_NAME,
            reason=reason,
        )
        return FeatureValue(feature_name=feature_id, value=None, unit=unit, semantic_role=role, status=FeatureValueStatus.PARTIAL, evidence=[evidence])


__all__ = ["RESOLVER_NAME", "WallGeometryFactResolver"]
