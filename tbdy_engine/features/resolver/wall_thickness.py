"""Canonical wall-thickness fact resolution for P2.10 Slice 2A.

This module consumes accepted WallInventory candidates and the already fetched
ETABS wall-property CanonicalTable. It resolves one factual
``wall_thickness_mm`` FeatureSnapshot per wall object. It does not execute
Coverage, checks, assessment, or regulatory logic.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.diagnostics import (
    FeatureDiagnostic,
    FeatureDiagnosticCode,
    FeatureDiagnosticSeverity,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.resolver.live_smoke import unit_context_from_payload
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.source_tables import source_reference, source_row_evidence
from tbdy_engine.features.unit_metadata import normalize_length_to_mm
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.features.wall_inventory import (
    WallInventory,
    WallInventoryRecord,
    WallInventoryStatus,
)
from tbdy_engine.providers.table_registry import TableRegistry

FEATURE_NAME = "wall_thickness_mm"
PRIMARY_TABLE_KEY = "wall_section_properties"
RESOLVER_NAME = "p2_10_wall_thickness_fact_resolver"


def _identifier(value: Any) -> str | None:
    """Preserve opaque identifier values; accept strings only and never case-fold."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _column_for_aliases(table: CanonicalTable, aliases: Sequence[str]) -> str | None:
    """Resolve column *names* case-insensitively without touching row values."""
    available: list[str] = list(table.columns)
    for row in table.rows:
        available.extend(str(key) for key in row.keys())
    by_casefold: dict[str, str] = {}
    for name in available:
        by_casefold.setdefault(name.casefold(), name)
    for alias in aliases:
        match = by_casefold.get(str(alias).casefold())
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


def _unit_context_from_table(table: CanonicalTable):
    """Resolve UnitContext from the exact CanonicalTable carrying Thickness."""
    units = dict(table.units or {})
    candidate = dict(units)
    candidate["source"] = (
        units.get("unit_context_source")
        or units.get("source")
        or f"{table.table_key}.units"
    )
    return unit_context_from_payload({"unit_context": candidate})


def _coerce_external_context(value: Any):
    if value is None:
        return None
    if isinstance(value, Mapping):
        candidate = dict(value)
    elif hasattr(value, "as_dict") and callable(value.as_dict):
        candidate = dict(value.as_dict())
    else:
        raise TypeError("external_unit_context must be a mapping, UnitContext-like object, or None")
    return unit_context_from_payload({"unit_context": candidate})


def _contexts_agree(source_context: Any, external_context: Any) -> tuple[bool, tuple[str, ...]]:
    """Validate compatibility context without allowing it to become authority."""
    if external_context is None:
        return True, tuple()
    if not source_context.resolved:
        return False, ("source_table_unit_context_not_resolved",)
    if not external_context.resolved:
        return False, ("external_unit_context_not_resolved",)

    mismatches: list[str] = []
    for field in ("force_unit", "length_unit", "temperature_unit"):
        source_value = getattr(source_context, field, None)
        external_value = getattr(external_context, field, None)
        if source_value not in (None, "") and external_value not in (None, ""):
            if str(source_value) != str(external_value):
                mismatches.append(field)
    return not mismatches, tuple(mismatches)


class WallThicknessFeatureResolver:
    """Resolve canonical wall thickness facts from one authoritative source table."""

    def __init__(
        self,
        contract_bundle: ContractBundle,
        wall_property_table: CanonicalTable,
        *,
        external_unit_context: Any = None,
    ) -> None:
        self.contract_bundle = contract_bundle
        self.table = wall_property_table
        self.external_unit_context = _coerce_external_context(external_unit_context)

        feature_catalog = contract_bundle.catalog("feature_catalog.yaml").get("features", {})
        self.feature_def = feature_catalog.get(FEATURE_NAME)
        if not isinstance(self.feature_def, Mapping):
            raise ValueError(f"{FEATURE_NAME} must already exist in feature_catalog.yaml")

        self.table_registry = TableRegistry.from_dict(contract_bundle.catalog("table_registry.yaml"))
        source = self.feature_def.get("source") or {}
        contracted_key = str(source.get("table_key") or "")
        contracted_primary = self.table_registry.primary_key_for_key(contracted_key)
        if contracted_primary != PRIMARY_TABLE_KEY:
            raise ValueError(
                f"{FEATURE_NAME} source contract must resolve to {PRIMARY_TABLE_KEY}; "
                f"got {contracted_key!r}"
            )

        actual_primary = self.table_registry.primary_key_for_key(self.table.table_key)
        if actual_primary is None and self.table.actual_table_name:
            actual_primary = self.table_registry.canonical_key_for_alias(self.table.actual_table_name)
        if actual_primary != PRIMARY_TABLE_KEY:
            raise ValueError(
                "Wall thickness source table is outside the verified wall property table family: "
                f"table_key={self.table.table_key!r}, actual_table_name={self.table.actual_table_name!r}"
            )

        source_aliases = tuple(str(value) for value in (source.get("field_aliases") or ()))
        self.thickness_column = _column_for_aliases(self.table, source_aliases)

        registry_row = self.table_registry.tables[PRIMARY_TABLE_KEY]
        name_contract = (registry_row.get("required_columns") or {}).get("Name") or {}
        name_aliases = tuple(str(value) for value in (name_contract.get("aliases") or ("Name",)))
        self.property_name_column = _column_for_aliases(self.table, name_aliases)

        index: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
        if self.property_name_column is not None:
            for row in self.table.rows:
                property_name = _identifier(_row_value(row, self.property_name_column))
                if property_name is not None:
                    index[property_name].append(row)
        self.property_rows = {key: tuple(rows) for key, rows in index.items()}
        self.source_unit_context = _unit_context_from_table(self.table)
        self.contexts_agree, self.context_mismatches = _contexts_agree(
            self.source_unit_context,
            self.external_unit_context,
        )

    def build_snapshots(self, inventory: WallInventory) -> tuple[FeatureSnapshot, ...]:
        """Emit one FeatureSnapshot for every eligible structural-wall candidate."""
        return tuple(
            self.resolve_candidate(record)
            for record in inventory.records
            if record.classification_status == WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE
        )

    def resolve_candidate(self, record: WallInventoryRecord) -> FeatureSnapshot:
        if record.classification_status != WallInventoryStatus.STRUCTURAL_WALL_CANDIDATE:
            raise ValueError("Wall thickness facts are resolved only for structural-wall candidates")
        if record.wall_object_id is None:
            raise ValueError("Structural-wall candidate must retain authoritative wall_object_id")

        identity = {
            "wall_object_id": record.wall_object_id,
            "etabs_area_unique_name": record.etabs_area_unique_name,
            "story": record.story,
            "area_label": record.area_label,
            "assigned_wall_property": record.assigned_area_property,
            "model_fingerprint": record.model_fingerprint,
        }
        feature = self._resolve_feature(record)
        diagnostics = tuple(feature.diagnostics)
        return FeatureSnapshot(
            component_type="wall",
            component_id=record.wall_object_id,
            identity=identity,
            features={FEATURE_NAME: feature},
            diagnostics=diagnostics,
        )

    def _resolve_feature(self, record: WallInventoryRecord) -> FeatureValue:
        assigned_property = _identifier(record.assigned_area_property)
        if assigned_property is None:
            return self._unresolved(
                record,
                FeatureValueStatus.MISSING,
                FeatureEvidenceStatus.MISSING,
                "Wall candidate has no authoritative string wall-property assignment",
                FeatureDiagnosticCode.ROW_MISSING,
            )

        matches = self.property_rows.get(assigned_property, ())
        if not matches:
            return self._unresolved(
                record,
                FeatureValueStatus.MISSING,
                FeatureEvidenceStatus.MISSING,
                "No exact wall-property Name match exists for the candidate assignment",
                FeatureDiagnosticCode.ROW_MISSING,
                extra={"assigned_wall_property": assigned_property},
            )
        if len(matches) != 1:
            return self._unresolved(
                record,
                FeatureValueStatus.PARTIAL,
                FeatureEvidenceStatus.PARTIAL,
                "Exact wall-property identity is not unique; thickness is not selected arbitrarily",
                FeatureDiagnosticCode.UNIT_NORMALIZATION_UNVERIFIED,
                row=matches[0],
                extra={"assigned_wall_property": assigned_property, "exact_match_count": len(matches)},
            )

        row = matches[0]
        raw_thickness = _row_value(row, self.thickness_column)
        if self.thickness_column is None or raw_thickness in (None, ""):
            return self._unresolved(
                record,
                FeatureValueStatus.PARTIAL,
                FeatureEvidenceStatus.PARTIAL,
                "Matched wall-property row has no usable Thickness field",
                FeatureDiagnosticCode.COLUMN_MISSING,
                row=row,
                raw_value=raw_thickness,
            )

        if not self.source_unit_context.resolved:
            return self._unresolved(
                record,
                FeatureValueStatus.PARTIAL,
                FeatureEvidenceStatus.PARTIAL,
                "Source CanonicalTable UnitContext is missing or untrusted; thickness unit is not guessed",
                FeatureDiagnosticCode.UNIT_CONTEXT_MISSING,
                row=row,
                raw_value=raw_thickness,
                extra={"source_unit_context": self.source_unit_context.as_dict()},
            )

        if not self.contexts_agree:
            return self._unresolved(
                record,
                FeatureValueStatus.PARTIAL,
                FeatureEvidenceStatus.PARTIAL,
                "External UnitContext does not validate against source-table UnitContext",
                FeatureDiagnosticCode.UNIT_NORMALIZATION_UNVERIFIED,
                row=row,
                raw_value=raw_thickness,
                extra={
                    "source_unit_context": self.source_unit_context.as_dict(),
                    "external_unit_context": self.external_unit_context.as_dict()
                    if self.external_unit_context is not None else None,
                    "unit_context_mismatches": list(self.context_mismatches),
                },
            )

        normalization = normalize_length_to_mm(
            raw_thickness,
            raw_unit=self.source_unit_context.length_unit,
            unit_context_trusted=True,
        )
        if normalization.normalized_value is None or normalization.normalized_unit != "mm":
            return self._unresolved(
                record,
                FeatureValueStatus.PARTIAL,
                FeatureEvidenceStatus.PARTIAL,
                "Thickness could not be normalized to mm from explicit source-table UnitContext",
                FeatureDiagnosticCode.UNIT_NORMALIZATION_UNVERIFIED,
                row=row,
                raw_value=raw_thickness,
                extra={
                    "source_unit_context": self.source_unit_context.as_dict(),
                    "unit_normalization": normalization.as_dict(),
                },
            )

        source_row = self._source_row_payload(
            record,
            row,
            extra={
                "source_unit_authority": "CanonicalTable.units",
                "source_unit_context": self.source_unit_context.as_dict(),
                "external_unit_context_validation": (
                    "NOT_SUPPLIED" if self.external_unit_context is None else "MATCHED_SOURCE_TABLE"
                ),
                "unit_normalization": normalization.as_dict(),
            },
        )
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table=self.table.table_key,
            actual_table_name=self.table.actual_table_name,
            source_column=self.thickness_column,
            source_row=source_row,
            raw_value=raw_thickness,
            normalized_value=normalization.normalized_value,
            unit="mm",
            resolver=RESOLVER_NAME,
        )
        diagnostics: list[FeatureDiagnostic] = []
        if normalization.provenance.get("factor") not in (None, 1.0):
            diagnostics.append(
                FeatureDiagnostic(
                    severity=FeatureDiagnosticSeverity.INFO,
                    code=FeatureDiagnosticCode.UNIT_NORMALIZED,
                    message="Wall thickness normalized from explicit source-table UnitContext",
                    details={
                        "raw_unit": normalization.raw_unit,
                        "normalized_unit": normalization.normalized_unit,
                        "normalization_rule": normalization.provenance.get("normalization_rule"),
                    },
                )
            )
        return FeatureValue(
            feature_name=FEATURE_NAME,
            value=normalization.normalized_value,
            unit="mm",
            semantic_role=str(self.feature_def.get("semantic_role") or "GEOMETRY"),
            status=FeatureValueStatus.RESOLVED,
            evidence=[evidence],
            diagnostics=diagnostics,
        )

    def _source_row_payload(
        self,
        record: WallInventoryRecord,
        row: Mapping[str, Any] | None,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_extra = {
            "wall_object_id": record.wall_object_id,
            "etabs_area_unique_name": record.etabs_area_unique_name,
            "story": record.story,
            "area_label": record.area_label,
            "assigned_wall_property": record.assigned_area_property,
            "inventory_source_references": [ref.as_dict() for ref in record.source_row_references],
            "property_source_reference": source_reference(
                "wall_property",
                self.table.table_key,
                self.table,
                row,
                column=self.thickness_column,
                identity_fields=(self.property_name_column,) if self.property_name_column else (),
            ) if row is not None else None,
            **dict(extra or {}),
        }
        return source_row_evidence(
            self.table.table_key,
            self.table,
            row,
            source_column=self.thickness_column,
            selection_reason="exact opaque assigned wall-property identity match",
            extra=payload_extra,
        )

    def _unresolved(
        self,
        record: WallInventoryRecord,
        feature_status: FeatureValueStatus,
        evidence_status: FeatureEvidenceStatus,
        reason: str,
        diagnostic_code: FeatureDiagnosticCode,
        *,
        row: Mapping[str, Any] | None = None,
        raw_value: Any = None,
        extra: Mapping[str, Any] | None = None,
    ) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=evidence_status,
            source_table=self.table.table_key,
            actual_table_name=self.table.actual_table_name,
            source_column=self.thickness_column,
            source_row=self._source_row_payload(record, row, extra=extra),
            raw_value=raw_value,
            normalized_value=None,
            unit="mm",
            resolver=RESOLVER_NAME,
            reason=reason,
        )
        diagnostic = FeatureDiagnostic(
            severity=FeatureDiagnosticSeverity.WARNING,
            code=diagnostic_code,
            message=reason,
            details={
                "wall_object_id": record.wall_object_id,
                "assigned_wall_property": record.assigned_area_property,
                **dict(extra or {}),
            },
        )
        return FeatureValue(
            feature_name=FEATURE_NAME,
            value=None,
            unit="mm",
            semantic_role=str(self.feature_def.get("semantic_role") or "GEOMETRY"),
            status=feature_status,
            evidence=[evidence],
            diagnostics=[diagnostic],
        )


def build_wall_thickness_snapshots(
    contract_bundle: ContractBundle,
    inventory: WallInventory,
    wall_property_table: CanonicalTable,
    *,
    external_unit_context: Any = None,
) -> tuple[FeatureSnapshot, ...]:
    """Convenience API for the P2.10 Slice 2A factual projection."""
    return WallThicknessFeatureResolver(
        contract_bundle,
        wall_property_table,
        external_unit_context=external_unit_context,
    ).build_snapshots(inventory)


__all__ = [
    "FEATURE_NAME",
    "PRIMARY_TABLE_KEY",
    "RESOLVER_NAME",
    "WallThicknessFeatureResolver",
    "build_wall_thickness_snapshots",
]
