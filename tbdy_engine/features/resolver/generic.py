"""Generic data-only feature resolver for C4.

This module resolves simple table/field/alias features from canonical tables. It
performs data selection, aggregation, and evidence attachment only. It does not
execute checks, compute ratios, apply pass rules, or make engineering decisions.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tbdy_engine.canonical_tables.diagnostics import DiagnosticCode as TableDiagnosticCode
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.diagnostics import FeatureDiagnostic, FeatureDiagnosticCode, FeatureDiagnosticSeverity
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus


class GenericFeatureResolver:
    """Resolve simple features from canonical tables using the feature catalog."""

    resolver_name = "generic_table_resolver"

    def __init__(self, contract_bundle: ContractBundle, tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]):
        self.contract_bundle = contract_bundle
        self.feature_catalog = contract_bundle.catalog("feature_catalog.yaml").get("features", {})
        self.tables = self._normalize_tables(tables)

    @staticmethod
    def _normalize_tables(tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]) -> dict[str, CanonicalTable]:
        if isinstance(tables, Mapping):
            return {str(key): value for key, value in tables.items()}
        normalized: dict[str, CanonicalTable] = {}
        for table in tables:
            normalized[table.table_key] = table
            if table.actual_table_name:
                normalized[table.actual_table_name] = table
        return normalized

    def resolve_feature(self, feature_name: str) -> FeatureValue:
        feature_def = self.feature_catalog.get(feature_name)
        if not feature_def:
            return self._missing_feature(feature_name, "Feature is not declared in feature_catalog")
        source = feature_def.get("source", {})
        table_key = source.get("table_key")
        unit = str(feature_def.get("unit", ""))
        semantic_role = str(feature_def.get("semantic_role", "UNKNOWN"))
        if not table_key:
            return self._missing_feature(feature_name, "Feature has no source table for generic resolution", unit, semantic_role)
        table = self.tables.get(table_key)
        if table is None:
            return self._missing_feature(feature_name, f"Source table is missing: {table_key}", unit, semantic_role, table_key=table_key)
        if table.is_missing:
            return self._table_diagnostic_feature(feature_name, table, unit, semantic_role, FeatureValueStatus.MISSING)
        if table.is_empty:
            return self._table_diagnostic_feature(feature_name, table, unit, semantic_role, FeatureValueStatus.MISSING)
        field_aliases = tuple(str(alias) for alias in source.get("field_aliases", ()) or ())
        column = self._select_column(table, field_aliases)
        if column is None:
            return self._missing_column(feature_name, table, field_aliases, unit, semantic_role)
        rows = self._apply_filters(table.rows, source.get("filters", ()))
        if not rows:
            return self._missing_row(feature_name, table, column, unit, semantic_role)
        aggregation = str(source.get("aggregation", "first"))
        try:
            row, raw_value = self._aggregate(rows, column, aggregation)
        except ValueError as exc:
            return self._unsupported_aggregation(feature_name, table, column, unit, semantic_role, aggregation, str(exc))
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name,
            source_column=column,
            source_row=self._row_identity(row),
            output_case=self._row_value(row, ("Output Case", "OutputCase", "Case", "Load Case")),
            combo_family=source.get("combo_family"),
            governing_combo=self._row_value(row, ("Combo", "DesignCombo", "Load Combination")),
            section_state=None,
            ductility_class=None,
            raw_value=raw_value,
            normalized_value=raw_value,
            unit=unit,
            resolver=self.resolver_name,
        )
        return FeatureValue(
            feature_name=feature_name,
            value=raw_value,
            unit=unit,
            semantic_role=semantic_role,
            status=FeatureValueStatus.RESOLVED,
            evidence=[evidence],
            diagnostics=[],
        )

    def _missing_feature(
        self,
        feature_name: str,
        reason: str,
        unit: str = "",
        semantic_role: str = "UNKNOWN",
        *,
        table_key: str | None = None,
    ) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.MISSING,
            source_table=table_key,
            unit=unit,
            resolver=self.resolver_name,
            reason=reason,
        )
        diagnostic = FeatureDiagnostic(
            severity=FeatureDiagnosticSeverity.ERROR,
            code=FeatureDiagnosticCode.FEATURE_MISSING if table_key is None else FeatureDiagnosticCode.TABLE_MISSING,
            message=reason,
            details={"feature_name": feature_name, "table_key": table_key},
        )
        return FeatureValue(
            feature_name=feature_name,
            value=None,
            unit=unit,
            semantic_role=semantic_role,
            status=FeatureValueStatus.MISSING,
            evidence=[evidence],
            diagnostics=[diagnostic],
        )

    def _table_diagnostic_feature(
        self,
        feature_name: str,
        table: CanonicalTable,
        unit: str,
        semantic_role: str,
        status: FeatureValueStatus,
    ) -> FeatureValue:
        reason = table.diagnostics[0].message if table.diagnostics else "Table did not contain usable data"
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.MISSING,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name,
            unit=unit,
            resolver=self.resolver_name,
            reason=reason,
        )
        diagnostics = tuple(
            FeatureDiagnostic(
                severity=str(d.severity.value),
                code=FeatureDiagnosticCode.TABLE_MISSING
                if d.code == TableDiagnosticCode.TABLE_MISSING
                else FeatureDiagnosticCode.ROW_MISSING,
                message=d.message,
                details=d.details,
            )
            for d in table.diagnostics
        )
        return FeatureValue(
            feature_name=feature_name,
            value=None,
            unit=unit,
            semantic_role=semantic_role,
            status=status,
            evidence=[evidence],
            diagnostics=diagnostics,
        )

    def _missing_column(
        self,
        feature_name: str,
        table: CanonicalTable,
        aliases: Sequence[str],
        unit: str,
        semantic_role: str,
    ) -> FeatureValue:
        reason = f"None of the declared field aliases are present in table {table.table_key}"
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.PARTIAL,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name,
            unit=unit,
            resolver=self.resolver_name,
            reason=reason,
        )
        diagnostic = FeatureDiagnostic(
            severity=FeatureDiagnosticSeverity.WARNING,
            code=FeatureDiagnosticCode.COLUMN_MISSING,
            message=reason,
            details={"feature_name": feature_name, "field_aliases": list(aliases), "columns": list(table.columns)},
        )
        return FeatureValue(
            feature_name=feature_name,
            value=None,
            unit=unit,
            semantic_role=semantic_role,
            status=FeatureValueStatus.PARTIAL,
            evidence=[evidence],
            diagnostics=[diagnostic],
        )

    def _missing_row(
        self,
        feature_name: str,
        table: CanonicalTable,
        column: str,
        unit: str,
        semantic_role: str,
    ) -> FeatureValue:
        reason = f"No source row matched feature filters for {feature_name}"
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.MISSING,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name,
            source_column=column,
            unit=unit,
            resolver=self.resolver_name,
            reason=reason,
        )
        diagnostic = FeatureDiagnostic(
            severity=FeatureDiagnosticSeverity.ERROR,
            code=FeatureDiagnosticCode.ROW_MISSING,
            message=reason,
            details={"feature_name": feature_name, "table_key": table.table_key},
        )
        return FeatureValue(
            feature_name=feature_name,
            value=None,
            unit=unit,
            semantic_role=semantic_role,
            status=FeatureValueStatus.MISSING,
            evidence=[evidence],
            diagnostics=[diagnostic],
        )

    def _unsupported_aggregation(
        self,
        feature_name: str,
        table: CanonicalTable,
        column: str,
        unit: str,
        semantic_role: str,
        aggregation: str,
        reason: str,
    ) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.PARTIAL,
            source_table=table.table_key,
            actual_table_name=table.actual_table_name,
            source_column=column,
            unit=unit,
            resolver=self.resolver_name,
            reason=reason,
        )
        diagnostic = FeatureDiagnostic(
            severity=FeatureDiagnosticSeverity.WARNING,
            code=FeatureDiagnosticCode.UNSUPPORTED_AGGREGATION,
            message=reason,
            details={"feature_name": feature_name, "aggregation": aggregation},
        )
        return FeatureValue(
            feature_name=feature_name,
            value=None,
            unit=unit,
            semantic_role=semantic_role,
            status=FeatureValueStatus.PARTIAL,
            evidence=[evidence],
            diagnostics=[diagnostic],
        )

    @staticmethod
    def _select_column(table: CanonicalTable, aliases: Sequence[str]) -> str | None:
        by_casefold = {column.casefold(): column for column in table.columns}
        for alias in aliases:
            match = by_casefold.get(alias.casefold())
            if match is not None:
                return match
        return None

    @staticmethod
    def _apply_filters(rows: Sequence[Mapping[str, Any]], filters: Any) -> tuple[Mapping[str, Any], ...]:
        if not filters:
            return tuple(rows)
        normalized_filters: list[tuple[str, Any]] = []
        if isinstance(filters, Mapping):
            normalized_filters = [(str(k), v) for k, v in filters.items()]
        else:
            for item in filters:
                if isinstance(item, Mapping) and "field" in item and "value" in item:
                    value = item["value"]
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        continue
                    normalized_filters.append((str(item["field"]), value))
        filtered = []
        for row in rows:
            keep = True
            for field, expected in normalized_filters:
                actual = GenericFeatureResolver._row_value(row, (field,))
                if actual != expected:
                    keep = False
                    break
            if keep:
                filtered.append(row)
        return tuple(filtered)

    @staticmethod
    def _aggregate(rows: Sequence[Mapping[str, Any]], column: str, aggregation: str) -> tuple[Mapping[str, Any], Any]:
        if aggregation in {"none", "first"}:
            return rows[0], rows[0].get(column)
        if aggregation == "last_row":
            return rows[-1], rows[-1].get(column)
        if aggregation in {"max", "max_over_modes"}:
            return max(((row, row.get(column)) for row in rows), key=lambda pair: float(pair[1]))
        if aggregation == "min":
            return min(((row, row.get(column)) for row in rows), key=lambda pair: float(pair[1]))
        if aggregation == "max_abs":
            return max(((row, row.get(column)) for row in rows), key=lambda pair: abs(float(pair[1])))
        if aggregation == "max_positive":
            positives = [(row, row.get(column)) for row in rows if float(row.get(column)) >= 0]
            if not positives:
                raise ValueError("No nonnegative value found for max_positive aggregation")
            return max(positives, key=lambda pair: float(pair[1]))
        if aggregation == "max_abs_negative":
            negatives = [(row, row.get(column)) for row in rows if float(row.get(column)) < 0]
            if not negatives:
                raise ValueError("No negative value found for max_abs_negative aggregation")
            return max(negatives, key=lambda pair: abs(float(pair[1])))
        raise ValueError(f"Unsupported feature aggregation: {aggregation}")

    @staticmethod
    def _row_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
        by_casefold = {str(key).casefold(): value for key, value in row.items()}
        for alias in aliases:
            if alias.casefold() in by_casefold:
                return by_casefold[alias.casefold()]
        return None

    @staticmethod
    def _row_identity(row: Mapping[str, Any]) -> dict[str, Any]:
        identity_aliases = ("Story", "Frame", "Section", "Name", "Label", "UniqueName", "Mode", "Station", "Output Case")
        identity = {alias: GenericFeatureResolver._row_value(row, (alias,)) for alias in identity_aliases}
        return {key: value for key, value in identity.items() if value is not None}


__all__ = ["GenericFeatureResolver"]
