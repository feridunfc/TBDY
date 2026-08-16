"""Generic canonical wall-geometry fact resolver for P2.10 and later wall packs."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.diagnostics import FeatureDiagnostic, FeatureDiagnosticCode, FeatureDiagnosticSeverity
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.unit_metadata import normalize_length_to_mm, trusted_length_unit_from_context
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.features.wall_geometry_contract import (
    WALL_ALL_FEATURE_DEFINITIONS,
    WALL_ALL_SUPPLEMENTAL_FEATURE_DEFINITIONS,
)
from tbdy_engine.features.wall_inventory import WallInventory, WallInventoryRecord, WallInventoryStatus

_BASE_FACTS = ("wall_thickness_mm", "wall_length_mm", "story_height_mm")
_SUPPLEMENTAL_FACTS = tuple(WALL_ALL_SUPPLEMENTAL_FEATURE_DEFINITIONS)
_ALL_FACTS = (*_BASE_FACTS, *_SUPPLEMENTAL_FACTS)
_THICKNESS_TABLE_KEYS = ("wall_section_properties",)
_LENGTH_TABLE_KEYS = ("pier_section_properties",)
_STORY_TABLE_KEYS = ("story_definitions", "story_data")
_PROPERTY_NAME_ALIASES = ("Name", "Property", "PropName", "WallProp")
_STORY_ALIASES = ("Story", "Name", "Story Name")
_PIER_ALIASES = ("Pier", "PierName", "Pier Label")
_RESOLVER = "p2_10_wall_geometry_fact_resolver"


class WallGeometryFactResolver:
    """Resolve canonical factual wall geometry/context without engineering verdicts."""

    def __init__(self, contract_bundle: ContractBundle, tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]) -> None:
        self.contract_bundle = contract_bundle
        base_features = dict(contract_bundle.catalog("feature_catalog.yaml").get("features", {}))
        self.feature_defs = {**base_features, **dict(WALL_ALL_FEATURE_DEFINITIONS)}
        missing = [name for name in _BASE_FACTS if name not in self.feature_defs]
        if missing:
            raise ValueError("Missing existing canonical wall feature(s): " + ", ".join(missing))
        if "wall_special_branch_7_6_1_3_applies" in self.feature_defs:
            raise ValueError("Engineering-derived §7.6.1.3 eligibility must not enter FeatureSnapshot facts")
        self.tables = self._table_map(tables)
        self.thickness_table = self._first_table(_THICKNESS_TABLE_KEYS)
        self.length_table = self._first_table(_LENGTH_TABLE_KEYS)
        self.story_table = self._first_table(_STORY_TABLE_KEYS)
        self._property_rows = self._index_exact(self.thickness_table, _PROPERTY_NAME_ALIASES)

    def build_snapshots(self, inventory: WallInventory, *, provided_features_by_wall: Mapping[str, Mapping[str, FeatureValue]] | None = None) -> tuple[FeatureSnapshot, ...]:
        supplied = provided_features_by_wall or {}
        return tuple(
            self.resolve_record(record, provided_features=supplied.get(str(record.wall_object_id), {}))
            for record in inventory.records
            if record.classification_status == WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE
        )

    def resolve_record(self, record: WallInventoryRecord, *, provided_features: Mapping[str, FeatureValue] | None = None) -> FeatureSnapshot:
        if record.classification_status != WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE:
            raise ValueError("WallGeometryFactResolver accepts structural-wall candidates only")
        if not record.wall_object_id:
            raise ValueError("Structural-wall candidate must retain wall_object_id")
        supplied = dict(provided_features or {})
        unknown = set(supplied) - set(_SUPPLEMENTAL_FACTS)
        if unknown:
            raise ValueError("Only factual supplemental wall context may be supplied externally: " + ", ".join(sorted(unknown)))
        facts: dict[str, FeatureValue] = {
            "wall_thickness_mm": self._wall_thickness_fact(record),
            "wall_length_mm": self._wall_length_fact(record),
            "story_height_mm": self._story_height_fact(record),
        }
        for feature_id in _SUPPLEMENTAL_FACTS:
            facts[feature_id] = self._provided_fact(feature_id, supplied[feature_id]) if feature_id in supplied else self._missing(feature_id, record, "Canonical factual context has not been resolved")
        return FeatureSnapshot(
            component_type="wall", component_id=str(record.wall_object_id), identity=self._identity(record),
            features={name: facts[name] for name in _ALL_FACTS},
        )

    def _wall_thickness_fact(self, record: WallInventoryRecord) -> FeatureValue:
        feature_id = "wall_thickness_mm"; table = self.thickness_table
        if table is None:
            return self._missing(feature_id, record, "Verified wall-property thickness table is unavailable")
        prop = self._identifier(record.assigned_area_property)
        if prop is None:
            return self._missing(feature_id, record, "Wall candidate has no exact assigned wall-property identity")
        rows = self._property_rows.get(prop, ())
        if not rows:
            return self._missing(feature_id, record, "No exact wall-property row matches the assigned property")
        if len(rows) != 1:
            return self._partial(feature_id, record, "Exact wall-property thickness evidence is ambiguous")
        row = rows[0]; column, raw = self._field(row, self._aliases(feature_id))
        if column is None:
            return self._partial(feature_id, record, "Declared wall thickness column is unavailable")
        return self._normalized_length(feature_id, record, table, row, column, raw)

    def _wall_length_fact(self, record: WallInventoryRecord) -> FeatureValue:
        feature_id = "wall_length_mm"; table = self.length_table
        if table is None:
            return self._missing(feature_id, record, "Verified pier-section wall-length table is unavailable")
        story = self._identifier(record.story); pier = self._identifier(record.pier_assignment)
        if story is None or pier is None:
            return self._missing(feature_id, record, "Wall length requires exact story and pier identity; no unrelated total length is substituted")
        rows = tuple(row for row in table.rows if self._identifier(self._field(row, _STORY_ALIASES)[1]) == story and self._identifier(self._field(row, _PIER_ALIASES)[1]) == pier)
        if not rows:
            return self._missing(feature_id, record, "No exact Pier Section Properties row matches story+pier identity")
        if len(rows) != 1:
            return self._partial(feature_id, record, "Exact story+pier wall-length evidence is ambiguous")
        row = rows[0]; column, raw = self._field(row, self._aliases(feature_id))
        if column is None:
            return self._partial(feature_id, record, "Declared pier-section width column is unavailable")
        return self._normalized_length(feature_id, record, table, row, column, raw)

    def _story_height_fact(self, record: WallInventoryRecord) -> FeatureValue:
        feature_id = "story_height_mm"; table = self.story_table; story = self._identifier(record.story)
        if table is None or story is None:
            return self._missing(feature_id, record, "Story definition or exact story identity is unavailable")
        rows = [row for row in table.rows if self._identifier(self._field(row, _STORY_ALIASES)[1]) == story]
        if not rows:
            return self._missing(feature_id, record, "No exact story-definition row matches wall story")
        if len(rows) != 1:
            return self._partial(feature_id, record, "Story-height evidence is ambiguous")
        row = rows[0]; column, raw = self._field(row, self._aliases(feature_id))
        if column is None:
            return self._partial(feature_id, record, "Declared story-height column is unavailable")
        return self._normalized_length(feature_id, record, table, row, column, raw)

    def _normalized_length(self, feature_id: str, record: WallInventoryRecord, table: CanonicalTable, row: Mapping[str, Any], column: str, raw: Any) -> FeatureValue:
        raw_unit = trusted_length_unit_from_context(table.units)
        normalized = normalize_length_to_mm(raw, raw_unit=raw_unit, unit_context_trusted=raw_unit is not None)
        resolved = normalized.normalized_value is not None and normalized.provenance.get("normalization_status") == "RESOLVED"
        reason = None if resolved else "Source UnitContext is missing/untrusted or value is not safely normalizable"
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL if resolved else FeatureEvidenceStatus.PARTIAL,
            source_table=table.table_key, actual_table_name=table.actual_table_name or table.table_key,
            source_column=column, source_row=self._source_payload(record, table, row, normalized.as_dict()),
            raw_value=raw, normalized_value=normalized.normalized_value if resolved else None,
            unit="mm", resolver=_RESOLVER, reason=reason,
        )
        diagnostics = [] if resolved else [FeatureDiagnostic(
            FeatureDiagnosticSeverity.WARNING, FeatureDiagnosticCode.UNIT_CONTEXT_MISSING,
            reason or "Unit normalization unavailable", {"feature": feature_id, "source_table": table.table_key},
        )]
        return FeatureValue(
            feature_name=feature_id, value=normalized.normalized_value if resolved else None, unit="mm",
            semantic_role=self._semantic_role(feature_id),
            status=FeatureValueStatus.RESOLVED if resolved else FeatureValueStatus.PARTIAL,
            evidence=[evidence], diagnostics=diagnostics,
        )

    def _provided_fact(self, feature_id: str, value: FeatureValue) -> FeatureValue:
        if not isinstance(value, FeatureValue) or value.feature_name != feature_id:
            raise TypeError(f"Provided fact for {feature_id} must be a same-name FeatureValue")
        if value.status == FeatureValueStatus.RESOLVED and not value.evidence:
            raise ValueError(f"Resolved provided fact requires evidence: {feature_id}")
        return value

    def _missing(self, feature_id: str, record: WallInventoryRecord, reason: str) -> FeatureValue:
        return self._unresolved(feature_id, record, FeatureValueStatus.MISSING, FeatureEvidenceStatus.MISSING, reason)

    def _partial(self, feature_id: str, record: WallInventoryRecord, reason: str) -> FeatureValue:
        return self._unresolved(feature_id, record, FeatureValueStatus.PARTIAL, FeatureEvidenceStatus.PARTIAL, reason)

    def _unresolved(self, feature_id: str, record: WallInventoryRecord, status: FeatureValueStatus, evidence_status: FeatureEvidenceStatus, reason: str) -> FeatureValue:
        unit = self._unit(feature_id)
        evidence = FeatureEvidence(
            evidence_status=evidence_status, source_table=(self.feature_defs.get(feature_id, {}).get("source") or {}).get("table_key"),
            source_row=self._source_payload(record, None, None, None), unit=unit, resolver=_RESOLVER, reason=reason,
        )
        diagnostic = FeatureDiagnostic(
            FeatureDiagnosticSeverity.WARNING, FeatureDiagnosticCode.ROW_MISSING, reason,
            {"feature": feature_id, "wall_object_id": record.wall_object_id},
        )
        return FeatureValue(feature_name=feature_id, value=None, unit=unit, semantic_role=self._semantic_role(feature_id), status=status, evidence=[evidence], diagnostics=[diagnostic])

    def _source_payload(self, record: WallInventoryRecord, table: CanonicalTable | None, row: Mapping[str, Any] | None, normalization: Mapping[str, Any] | None) -> dict[str, Any]:
        return {
            "wall_object_id": record.wall_object_id, "etabs_area_unique_name": record.etabs_area_unique_name,
            "story": record.story, "area_label": record.area_label, "assigned_wall_property": record.assigned_area_property,
            "pier_assignment": record.pier_assignment,
            "inventory_source_references": [ref.as_dict() for ref in record.source_row_references],
            "source_table": table.table_key if table is not None else None,
            "source_row": dict(row or {}), "unit_context": dict(table.units) if table is not None else {},
            "normalization": dict(normalization or {}),
        }

    def _aliases(self, feature_id: str) -> tuple[str, ...]:
        source = self.feature_defs.get(feature_id, {}).get("source") or {}
        return tuple(str(value) for value in source.get("field_aliases", ()) or ())

    def _unit(self, feature_id: str) -> str:
        return str(self.feature_defs.get(feature_id, {}).get("unit") or "")

    def _semantic_role(self, feature_id: str) -> str:
        return str(self.feature_defs.get(feature_id, {}).get("semantic_role") or "GEOMETRY")

    def _first_table(self, keys: Sequence[str]) -> CanonicalTable | None:
        for key in keys:
            table = self.tables.get(key)
            if table is not None:
                return table
        return None

    @staticmethod
    def _table_map(tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]) -> dict[str, CanonicalTable]:
        values = tables.values() if isinstance(tables, Mapping) else tables
        return {table.table_key: table for table in values if isinstance(table, CanonicalTable)}

    @classmethod
    def _index_exact(cls, table: CanonicalTable | None, aliases: Sequence[str]) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        if table is not None:
            for row in table.rows:
                value = cls._identifier(cls._field(row, aliases)[1])
                if value is not None:
                    grouped[value].append(row)
        return {key: tuple(rows) for key, rows in grouped.items()}

    @staticmethod
    def _field(row: Mapping[str, Any], aliases: Sequence[str]) -> tuple[str | None, Any]:
        keys = {str(key).strip().casefold(): key for key in row}
        for alias in aliases:
            actual = keys.get(str(alias).strip().casefold())
            if actual is not None:
                return str(actual), row[actual]
        return None, None

    @staticmethod
    def _identifier(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip(); return text or None

    @staticmethod
    def _identity(record: WallInventoryRecord) -> Mapping[str, Any]:
        return {
            "wall_object_id": record.wall_object_id, "etabs_area_unique_name": record.etabs_area_unique_name,
            "story": record.story, "area_label": record.area_label, "assigned_wall_property": record.assigned_area_property,
            "pier_assignment": record.pier_assignment, "model_fingerprint": record.model_fingerprint,
        }


__all__ = ["WallGeometryFactResolver"]
