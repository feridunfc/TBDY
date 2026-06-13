"""ETABS table fit audit for C5.2.

This module audits provider table metadata against the contract constitution. It
is intentionally data-contract fit only: no checks, no engineering ratios, no
pass/fail decisions, and no live ETABS integration.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tbdy_engine.audit.models import (
    AuditDiagnostic,
    AuditSeverity,
    AuditStatus,
    ComboFamilyFitReport,
    ElementIdentityFitReport,
    EtabsTableInventory,
    FeatureSourceFitReport,
    MissingRequiredSourcesReport,
    TableContractFitReport,
    TableHeadersReport,
)
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageExpectedSource, ExpectedSourceKind
from tbdy_engine.providers.table_registry import TableRegistry, normalize_table_name
from tbdy_engine.providers.table_client import TableClient

_COMBO_COLUMN_EXACT = {
    "outputcase",
    "output case",
    "combo",
    "designcombo",
    "design combo",
    "loadcombo",
    "load combo",
    "load combination",
    "astopcombo",
    "asbotcombo",
    "vcombo",
    "pmmcombo",
    "vmajcombo",
    "vmincombo",
}
_MODAL_CASE_COLUMNS = {"case"}
_NON_COMBO_MARKERS = {"max", "combination", "min", "avg", "absolute max", "absolute min"}
_DIAGNOSTIC_CRACKED_SEISMIC_PATTERNS = (
    (re.compile(r"^Crack_SeisX(?:_.*)?$", re.IGNORECASE), "DUCTILE_X"),
    (re.compile(r"^Crack_SeisY(?:_.*)?$", re.IGNORECASE), "DUCTILE_Y"),
    (re.compile(r"^Crack_.*_UpSoil$", re.IGNORECASE), "SOIL"),
)
_COLUMN_EQUIVALENTS: Mapping[str, tuple[str, ...]] = {
    "section": ("DesignSect", "AnalysisSect", "Section"),
    "sectionname": ("DesignSect", "AnalysisSect", "Section", "Name"),
    "width": ("Width", "t2"),
    "depth": ("Depth", "t3"),
    "beam": ("Label", "UniqueName", "Frame", "Beam"),
    "frame": ("Label", "UniqueName", "Frame"),
    "column": ("Label", "UniqueName", "Frame", "Column"),
    "astop": ("AsTop", "AsMinTop", "totTopRebar", "TopArea"),
    "toparea": ("AsTop", "AsMinTop", "totTopRebar", "TopArea"),
    "asbot": ("AsBot", "AsMinBot", "totBotRebar", "BotArea"),
    "botarea": ("AsBot", "AsMinBot", "totBotRebar", "BotArea"),
    "asshear": ("VRebar", "totTrnRebar", "AsShear"),
    "output case": ("OutputCase", "Output Case"),
    "widthbottom": ("WidthBot", "WidthTop", "WidthBottom", "Width Bottom"),
    "thicknessbottom": ("ThickBot", "ThickTop", "ThicknessBottom", "Thickness Bottom"),
    "maxdrift": ("Max Drift", "MaxDrift"),
    "avgdrift": ("Avg Drift", "AvgDrift"),
}
_IDENTITY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "component": ("UniqueName", "Unique Name", "Frame", "Object", "Label", "Story"),
    "beam_id": ("UniqueName", "Unique Name", "Frame", "Label"),
    "unique_name": ("UniqueName", "Unique Name", "Frame", "Element"),
    "story": ("Story", "StoryName", "story_name"),
    "label": ("Label", "Frame", "Beam", "Column", "Wall", "Pier"),
    "section": ("DesignSect", "AnalysisSect", "Section", "SectionName", "Section Name", "Property", "PierSection"),
    "section_name": ("DesignSect", "AnalysisSect", "Section", "SectionName", "Section Name", "Property"),
    "pier_label": ("Pier", "PierName", "Pier Name", "Pier Label"),
    "material_name": ("Material", "Name"),
}
_REBAR_ROLE_MARKERS = ("REBAR", "ENGINE_SELECTED", "USER_PROVIDED", "GOVERNING_REQUIRED", "ETABS_REQUIRED")


class EtabsTableFitAuditor:
    """Audit table/column/combo/identity fit using ContractBundle + provider data."""

    def __init__(self, contract_bundle: ContractBundle, tables: Sequence[CanonicalTable] | None = None) -> None:
        self.contract_bundle = contract_bundle
        self.table_registry_catalog: Mapping[str, Any] = contract_bundle.catalog("table_registry.yaml").get("tables", {})
        self.feature_catalog: Mapping[str, Any] = contract_bundle.catalog("feature_catalog.yaml").get("features", {})
        self.load_combo_policy: Mapping[str, Any] = contract_bundle.catalog("load_combo_policy.yaml")
        self.design_combo_matrix: Mapping[str, Any] = contract_bundle.catalog("design_combo_matrix.yaml")
        self.element_registry: Mapping[str, Any] = contract_bundle.catalog("element_registry.yaml").get("element_types", {})
        self.coverage_policy: Mapping[str, Any] = contract_bundle.catalog("coverage_policy.yaml")
        self.registry = TableRegistry.from_dict(contract_bundle.catalog("table_registry.yaml"))
        self._tables = tuple(tables or ())

    @classmethod
    def from_provider(cls, contract_bundle: ContractBundle, provider: TableClient) -> "EtabsTableFitAuditor":
        registry = TableRegistry.from_dict(contract_bundle.catalog("table_registry.yaml"))
        tables: list[CanonicalTable] = []
        seen: set[str] = set()
        for actual_name in provider.list_tables():
            canonical = registry.canonical_key_for_alias(actual_name) or actual_name
            if canonical in seen:
                continue
            seen.add(canonical)
            table = provider.get_table(canonical)
            if table.is_missing and hasattr(provider, "_tables"):
                raw_rows = getattr(provider, "_tables", {}).get(actual_name, ())
                if raw_rows is not None:
                    rows = tuple(dict(row) for row in raw_rows)
                    table = CanonicalTable(
                        table_key=canonical,
                        actual_table_name=actual_name,
                        columns=tuple(rows[0].keys()) if rows else tuple(),
                        rows=rows,
                        units=provider.get_units(),
                        source=getattr(provider, "source", "PROVIDER"),
                    )
            tables.append(table)
        return cls(contract_bundle, tables)

    def table_inventory(self) -> tuple[EtabsTableInventory, ...]:
        rows: list[EtabsTableInventory] = []
        for table in self._tables:
            actual = table.actual_table_name or table.table_key
            canonical_by_alias = self.registry.canonical_key_for_alias(actual)
            if table.table_key in self.table_registry_catalog:
                canonical = table.table_key
                matched_by = "exact" if actual == table.table_key else "alias"
            elif canonical_by_alias:
                canonical = canonical_by_alias
                matched_by = "alias"
            else:
                canonical = None
                matched_by = "none"
            diagnostics = [] if canonical else [
                AuditDiagnostic(
                    severity=AuditSeverity.WARNING,
                    code="TABLE_UNMATCHED",
                    message="Provider table does not match any canonical table_key or alias",
                    details={"actual_table_name": actual},
                )
            ]
            rows.append(
                EtabsTableInventory(
                    actual_table_name=actual,
                    canonical_table_key=canonical,
                    matched_by=matched_by,
                    available_columns=table.columns,
                    row_count=len(table.rows),
                    diagnostics=tuple(diagnostics),
                )
            )
        return tuple(rows)

    def table_headers_report(self) -> tuple[TableHeadersReport, ...]:
        """Report matched table headers and optional small row samples.

        This is audit metadata only. It is populated from CanonicalTable column
        metadata/rows already supplied by the provider or manual smoke.
        """
        reports: list[TableHeadersReport] = []
        for item in self.table_inventory():
            table = self._table_for_inventory_item(item)
            sample_rows = tuple(dict(row) for row in (table.rows[:3] if table else ()))
            diagnostics = item.diagnostics
            if table and not table.columns:
                diagnostics = diagnostics + (
                    AuditDiagnostic(
                        severity=AuditSeverity.WARNING,
                        code="TABLE_HEADERS_MISSING",
                        message="No table headers/columns were available for this provider table",
                        details={"actual_table_name": item.actual_table_name, "table_key": item.canonical_table_key},
                    ),
                )
            reports.append(
                TableHeadersReport(
                    table_key=item.canonical_table_key,
                    actual_table_name=item.actual_table_name,
                    matched_by=item.matched_by,
                    available_columns=item.available_columns,
                    row_count=item.row_count,
                    sample_rows=sample_rows,
                    diagnostics=diagnostics,
                )
            )
        return tuple(reports)

    def table_contract_fit(self) -> tuple[TableContractFitReport, ...]:
        inventory_by_key = {item.canonical_table_key: item for item in self.table_inventory() if item.canonical_table_key}
        reports: list[TableContractFitReport] = []
        for table_key, table_def in self.table_registry_catalog.items():
            aliases = self.registry.aliases_for_key(table_key)
            inventory = inventory_by_key.get(table_key)
            required = self._required_columns_for_table(table_def, inventory.available_columns if inventory else ())
            if inventory is None:
                reports.append(
                    TableContractFitReport(
                        table_key=table_key,
                        expected_aliases=aliases,
                        matched_actual_table_name=None,
                        required_columns=required,
                        matched_columns=(),
                        missing_columns=required,
                        extra_columns=(),
                        status=AuditStatus.MISSING,
                        diagnostics=(
                            AuditDiagnostic(
                                severity=AuditSeverity.ERROR,
                                code="TABLE_MISSING",
                                message="Required canonical table is not available from provider inventory",
                                details={"table_key": table_key, "expected_aliases": list(aliases)},
                            ),
                        ),
                    )
                )
                continue
            matched, missing = _match_columns(required, inventory.available_columns)
            extra = tuple(col for col in inventory.available_columns if _casefold(col) not in {_casefold(x) for x in matched})
            status = AuditStatus.MATCHED if not missing else AuditStatus.PARTIAL
            diagnostics = () if not missing else (
                AuditDiagnostic(
                    severity=AuditSeverity.WARNING,
                    code="COLUMN_MISSING",
                    message="Provider table is available but required columns are missing",
                    details={"table_key": table_key, "missing_columns": list(missing)},
                ),
            )
            reports.append(
                TableContractFitReport(
                    table_key=table_key,
                    expected_aliases=aliases,
                    matched_actual_table_name=inventory.actual_table_name,
                    required_columns=required,
                    matched_columns=matched,
                    missing_columns=missing,
                    extra_columns=extra,
                    status=status,
                    diagnostics=diagnostics,
                )
            )
        return tuple(reports)

    def feature_source_fit(self) -> tuple[FeatureSourceFitReport, ...]:
        table_reports = {report.table_key: report for report in self.table_contract_fit()}
        reports: list[FeatureSourceFitReport] = []
        for feature_name, feature_def in self.feature_catalog.items():
            reports.append(self._feature_source_fit_one(feature_name, feature_def, table_reports))
        return tuple(reports)

    def combo_family_fit(self) -> tuple[ComboFamilyFitReport, ...]:
        reports: list[ComboFamilyFitReport] = []
        seen: set[tuple[str, str, str]] = set()
        rebar_table_keys = self._reinforcement_feature_table_keys()
        table_key_by_actual = {item.actual_table_name: item.canonical_table_key for item in self.table_inventory()}
        for table in self._tables:
            table_key = table.table_key if table.table_key in self.table_registry_catalog else table_key_by_actual.get(table.actual_table_name or "")
            is_rebar_table = bool(table_key and table_key in rebar_table_keys)
            for column in table.columns:
                if not _looks_like_combo_column(column, table.actual_table_name or table.table_key):
                    continue
                for raw in _values_for_column(table.rows, column):
                    if _ignore_combo_like_value(raw):
                        continue
                    raw_name = str(raw)
                    key = (table.actual_table_name or table.table_key, column, raw_name)
                    if key in seen:
                        continue
                    seen.add(key)
                    family, matched_by = self._match_combo_family(raw_name)
                    needs_review = matched_by == "diagnostic_pattern"
                    if family is None:
                        reports.append(
                            ComboFamilyFitReport(
                                raw_combo_name=raw_name,
                                matched_combo_family=None,
                                matched_by="none",
                                reinforcement_design_allowed=None,
                                read_only=None,
                                status=AuditStatus.UNKNOWN,
                                source_table=table.actual_table_name or table.table_key,
                                source_column=column,
                                diagnostics=(
                                    AuditDiagnostic(
                                        severity=AuditSeverity.WARNING,
                                        code="COMBO_UNKNOWN",
                                        message="Raw combo/output case did not match load_combo_policy",
                                        details={"raw_combo_name": raw_name, "source_table": table.actual_table_name or table.table_key},
                                    ),
                                ),
                            )
                        )
                        continue
                    family_def = self.load_combo_policy.get("combo_families", {}).get(family, {})
                    reinforcement_allowed = bool(family_def.get("reinforcement_design_allowed", False))
                    read_only = bool(family_def.get("read_only", False))
                    status = AuditStatus.FORBIDDEN_FOR_PURPOSE if is_rebar_table and not reinforcement_allowed else AuditStatus.MATCHED
                    diagnostics = () if status == AuditStatus.MATCHED else (
                        AuditDiagnostic(
                            severity=AuditSeverity.ERROR,
                            code="COMBO_FORBIDDEN_FOR_PURPOSE",
                            message="Combo family is not allowed for reinforcement-purpose source table",
                            details={"raw_combo_name": raw_name, "family": family, "table_key": table_key},
                        ),
                    )
                    reports.append(
                        ComboFamilyFitReport(
                            raw_combo_name=raw_name,
                            matched_combo_family=family,
                            matched_by="pattern" if matched_by == "diagnostic_pattern" else matched_by,
                            reinforcement_design_allowed=reinforcement_allowed,
                            read_only=read_only,
                            status=status,
                            source_table=table.actual_table_name or table.table_key,
                            source_column=column,
                            diagnostics=diagnostics + ((AuditDiagnostic(severity=AuditSeverity.WARNING, code="COMBO_NEEDS_ENGINEERING_REVIEW", message="Project-specific cracked seismic combo matched diagnostic pattern; engineering review required before production use", details={"raw_combo_name": raw_name, "family": family}),) if needs_review and status == AuditStatus.MATCHED else ()),
                        )
                    )
        return tuple(reports)

    def element_identity_fit(self) -> tuple[ElementIdentityFitReport, ...]:
        all_columns = tuple(dict.fromkeys(col for table in self._tables for col in table.columns))
        reports: list[ElementIdentityFitReport] = []
        for element_type, definition in self.element_registry.items():
            required = tuple(str(x) for x in definition.get("identity_fields", ()) or ())
            mapping: dict[str, str] = {}
            for field in required:
                match = _first_column_match(_identity_aliases(field), all_columns)
                if match:
                    mapping[field] = match
            available = tuple(mapping.values())
            if not required:
                status = AuditStatus.MISSING
            elif len(mapping) == len(required):
                status = AuditStatus.MATCHED
            elif mapping:
                status = AuditStatus.PARTIAL
            else:
                status = AuditStatus.MISSING
            diagnostics = () if status == AuditStatus.MATCHED else (
                AuditDiagnostic(
                    severity=AuditSeverity.WARNING if status == AuditStatus.PARTIAL else AuditSeverity.ERROR,
                    code="IDENTITY_FIELD_MISSING",
                    message="Some required identity fields are not available in provider table columns",
                    details={"element_type": element_type, "missing_identity_fields": [x for x in required if x not in mapping]},
                ),
            )
            reports.append(
                ElementIdentityFitReport(
                    element_type=element_type,
                    required_identity_fields=required,
                    available_identity_columns=available,
                    identity_mapping=mapping,
                    status=status,
                    diagnostics=diagnostics,
                )
            )
        return tuple(reports)

    def missing_required_sources(self) -> MissingRequiredSourcesReport:
        feature_reports = self.feature_source_fit()
        identity_reports = self.element_identity_fit()
        missing_tables = []
        missing_columns = []
        missing_identity = []
        missing_combo = []
        design_context = []
        known_families = set(self.load_combo_policy.get("combo_families", {})) | set(self.load_combo_policy.get("combo_family_aliases", {}))
        for report in feature_reports:
            if report.source_kind == "design_context" and report.status != AuditStatus.RESOLVABLE:
                design_context.append({"feature_name": report.feature_name, "reason": report.reason or "design context unavailable"})
            if report.table_status == AuditStatus.MISSING.value:
                aliases = self.registry.aliases_for_key(report.table_key or "") if report.table_key else tuple()
                missing_tables.append({"feature_name": report.feature_name, "table_key": report.table_key, "expected_aliases": list(aliases)})
            if report.missing_columns:
                missing_columns.append({"feature_name": report.feature_name, "field_aliases": list(report.field_aliases), "missing_columns": list(report.missing_columns)})
            if report.combo_family and report.combo_family not in known_families:
                missing_combo.append({"feature_name": report.feature_name, "combo_family": report.combo_family})
        for report in identity_reports:
            if report.status != AuditStatus.MATCHED:
                missing_identity.append({"element_type": report.element_type, "missing_identity_fields": [x for x in report.required_identity_fields if x not in report.identity_mapping]})
        return MissingRequiredSourcesReport(
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            missing_identity_fields=missing_identity,
            missing_combo_policies=missing_combo,
            missing_design_context=design_context,
        )

    def _table_for_inventory_item(self, item: EtabsTableInventory) -> CanonicalTable | None:
        for table in self._tables:
            actual = table.actual_table_name or table.table_key
            canonical = table.table_key if table.table_key in self.table_registry_catalog else self.registry.canonical_key_for_alias(actual)
            if actual == item.actual_table_name and canonical == item.canonical_table_key:
                return table
        return None

    def coverage_expected_source_for_feature(self, feature_name: str) -> CoverageExpectedSource:
        """Reuse coverage expected-source metadata without running checks."""
        return CoverageBuilder(self.contract_bundle)._expected_source_for_feature(feature_name)  # contract metadata only

    def _feature_source_fit_one(
        self,
        feature_name: str,
        feature_def: Mapping[str, Any],
        table_reports: Mapping[str, TableContractFitReport],
    ) -> FeatureSourceFitReport:
        source = feature_def.get("source", {}) or {}
        table_key = source.get("table_key")
        field_aliases = tuple(str(x) for x in source.get("field_aliases", ()) or ())
        filters = tuple(source.get("filters", ()) or ())
        combo_family = source.get("combo_family")
        unit = feature_def.get("unit")
        evidence_fields = tuple(str(x) for x in feature_def.get("evidence_fields", ()) or ())
        element_type = str(feature_def.get("element_type", "global"))
        identity_required = tuple(str(x) for x in self.element_registry.get(element_type, {}).get("identity_fields", ()) or ())
        identity_available = self._available_identity_for_element(element_type)
        source_kind = self._source_kind(feature_def)
        if source_kind in {"computed", "manual", "design_context"}:
            status = AuditStatus.RESOLVABLE if source_kind != "design_context" else AuditStatus.PARTIAL
            return FeatureSourceFitReport(
                feature_name=feature_name,
                element_type=element_type,
                source_kind=source_kind,
                table_key=None,
                table_status="NOT_APPLICABLE",
                field_aliases=field_aliases,
                matched_column=None,
                missing_columns=(),
                required_filters=filters,
                identity_fields_required=identity_required,
                identity_fields_available=identity_available,
                combo_family=combo_family,
                status=status,
                reason="Feature is not sourced from an ETABS/canonical table" if source_kind != "design_context" else "Design context source must be supplied outside provider tables",
                custom_resolver=self._custom_resolver_name(feature_name, feature_def) if source_kind == "computed" else None,
                required_inputs=self._required_inputs(feature_def),
                unit=unit,
                expected_evidence_requirements=evidence_fields,
            )
        table_report = table_reports.get(str(table_key)) if table_key else None
        if table_report is None or table_report.status == AuditStatus.MISSING:
            return FeatureSourceFitReport(
                feature_name=feature_name,
                element_type=element_type,
                source_kind="etabs_table",
                table_key=str(table_key) if table_key else None,
                table_status=AuditStatus.MISSING.value,
                field_aliases=field_aliases,
                matched_column=None,
                missing_columns=field_aliases,
                required_filters=filters,
                identity_fields_required=identity_required,
                identity_fields_available=identity_available,
                combo_family=combo_family,
                status=AuditStatus.MISSING,
                reason="Source table is missing from provider inventory",
                unit=unit,
                expected_evidence_requirements=evidence_fields,
            )
        matched = _first_column_match(field_aliases, table_report.matched_columns + table_report.extra_columns)
        if not matched and field_aliases:
            return FeatureSourceFitReport(
                feature_name=feature_name,
                element_type=element_type,
                source_kind="etabs_table",
                table_key=str(table_key),
                table_status=table_report.status.value,
                field_aliases=field_aliases,
                matched_column=None,
                missing_columns=field_aliases,
                required_filters=filters,
                identity_fields_required=identity_required,
                identity_fields_available=identity_available,
                combo_family=combo_family,
                status=AuditStatus.PARTIAL,
                reason="Source table exists but feature field aliases are missing",
                unit=unit,
                expected_evidence_requirements=evidence_fields,
            )
        status = AuditStatus.RESOLVABLE if table_report.status == AuditStatus.MATCHED or matched else AuditStatus.PARTIAL
        return FeatureSourceFitReport(
            feature_name=feature_name,
            element_type=element_type,
            source_kind="etabs_table",
            table_key=str(table_key),
            table_status=table_report.status.value,
            field_aliases=field_aliases,
            matched_column=matched,
            missing_columns=(),
            required_filters=filters,
            identity_fields_required=identity_required,
            identity_fields_available=identity_available,
            combo_family=combo_family,
            status=status,
            reason=None if status == AuditStatus.RESOLVABLE else "Table is partial but feature column was found",
            unit=unit,
            expected_evidence_requirements=evidence_fields,
        )

    def _required_columns_for_table(self, table_def: Mapping[str, Any], available_columns: Sequence[str] = ()) -> tuple[str, ...]:
        groups = table_def.get("required_columns_any", ()) or ()
        if not groups:
            return tuple()
        if not available_columns:
            return tuple(str(x) for x in groups[0])
        # Choose the alternative required-column group that best fits the actual
        # provider columns. This supports real ETABS naming variants while keeping
        # explicit contract alternatives in table_registry.yaml.
        best = max(groups, key=lambda group: len(_match_columns(tuple(str(x) for x in group), available_columns)[0]))
        return tuple(str(x) for x in best)

    def write_deep_fit_reports(self, out_dir: str | Path) -> None:
        """Write audit-only deep-fit reports as JSON files.

        The reports are contract-fit diagnostics only: no CheckResult, no ratios,
        no pass_rule execution, and no OK/FAIL statuses.
        """
        target = Path(out_dir)
        target.mkdir(parents=True, exist_ok=True)
        payloads = {
            "table_headers_report.json": [r.as_dict() for r in self.table_headers_report()],
            "table_contract_fit_report.json": [r.as_dict() for r in self.table_contract_fit()],
            "feature_source_fit_report.json": [r.as_dict() for r in self.feature_source_fit()],
            "combo_family_fit_report.json": [r.as_dict() for r in self.combo_family_fit()],
            "element_identity_fit_report.json": [r.as_dict() for r in self.element_identity_fit()],
            "missing_required_sources.json": self.missing_required_sources().as_dict(),
        }
        for name, payload in payloads.items():
            (target / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _source_kind(self, feature_def: Mapping[str, Any]) -> str:
        source = feature_def.get("source", {}) or {}
        if source.get("table_key"):
            return "etabs_table"
        role = str(feature_def.get("semantic_role", ""))
        fallback = feature_def.get("fallback", {}) or {}
        if role == "DESIGN_BASIS":
            return "design_context"
        if fallback.get("method") == "manual_input":
            return "manual"
        if fallback.get("method") == "custom_resolver" or str(feature_def.get("unit_policy", {}).get("conversion", "")).startswith("contract_defined"):
            return "computed"
        return "unknown"

    def _custom_resolver_name(self, feature_name: str, feature_def: Mapping[str, Any]) -> str | None:
        explicit = feature_def.get("custom_resolver")
        if explicit:
            return str(explicit)
        if self._source_kind(feature_def) == "computed":
            return f"{feature_name}_resolver"
        return None

    def _required_inputs(self, feature_def: Mapping[str, Any]) -> tuple[str, ...]:
        raw = feature_def.get("required_inputs") or feature_def.get("design_context_dependencies") or ()
        return tuple(str(x) for x in raw)

    def _available_identity_for_element(self, element_type: str) -> tuple[str, ...]:
        all_columns = tuple(dict.fromkeys(col for table in self._tables for col in table.columns))
        fields = self.element_registry.get(element_type, {}).get("identity_fields", ()) or ()
        found: list[str] = []
        for field in fields:
            match = _first_column_match(_identity_aliases(str(field)), all_columns)
            if match:
                found.append(match)
        return tuple(found)

    def _match_combo_family(self, raw_name: str) -> tuple[str | None, str]:
        families = self.load_combo_policy.get("combo_families", {})
        if raw_name in families:
            return raw_name, "alias"
        for pattern, family in _DIAGNOSTIC_CRACKED_SEISMIC_PATTERNS:
            if pattern.search(raw_name):
                return family, "diagnostic_pattern"
        for rule in self.load_combo_policy.get("matching_rules", ()) or ():
            family = rule.get("family")
            includes = rule.get("include_patterns", ()) or ()
            excludes = rule.get("exclude_patterns", ()) or ()
            if includes and not any(re.search(str(pattern), raw_name, flags=re.IGNORECASE) for pattern in includes):
                continue
            if any(re.search(str(pattern), raw_name, flags=re.IGNORECASE) for pattern in excludes):
                continue
            return str(family), "pattern"
        return None, "none"

    def _reinforcement_feature_table_keys(self) -> set[str]:
        keys: set[str] = set()
        for feature_def in self.feature_catalog.values():
            role = str(feature_def.get("semantic_role", ""))
            name = str(feature_def.get("feature_name", ""))
            table_key = (feature_def.get("source", {}) or {}).get("table_key")
            if table_key and (any(marker in role for marker in _REBAR_ROLE_MARKERS) or "rebar" in name.lower()):
                keys.add(str(table_key))
        # ETABS design-summary tables in this contract are reinforcement-purpose sources.
        keys.update(k for k in self.table_registry_catalog if "design_summary" in k)
        return keys


def _casefold(value: str) -> str:
    return normalize_table_name(value)


def _aliases_for_required_column(column: str) -> tuple[str, ...]:
    aliases = _COLUMN_EQUIVALENTS.get(_casefold(column), (column,))
    if column not in aliases:
        aliases = (column,) + aliases
    return tuple(str(x) for x in aliases)


def _first_column_match(aliases: Sequence[str], columns: Sequence[str]) -> str | None:
    lookup = {_casefold(col): str(col) for col in columns}
    expanded: list[str] = []
    for alias in aliases:
        expanded.extend(_aliases_for_required_column(str(alias)))
    for alias in expanded:
        found = lookup.get(_casefold(alias))
        if found:
            return found
    return None


def _match_columns(required: Sequence[str], columns: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    matched: list[str] = []
    missing: list[str] = []
    for column in required:
        found = _first_column_match((str(column),), columns)
        if found:
            matched.append(found)
        else:
            missing.append(str(column))
    return tuple(dict.fromkeys(matched)), tuple(missing)


def _normalize_combo_column_name(column: str) -> str:
    return re.sub(r"[_\s]+", " ", str(column)).strip().casefold().replace(" ", "")


def _looks_like_combo_column(column: str, table_name: str | None = None) -> bool:
    normalized_spaced = re.sub(r"[_\s]+", " ", str(column)).strip().casefold()
    normalized = normalized_spaced.replace(" ", "")
    if normalized in {_normalize_combo_column_name(x) for x in _COMBO_COLUMN_EXACT}:
        return True
    if normalized in _MODAL_CASE_COLUMNS and table_name and "modal" in table_name.casefold():
        return True
    return False


def _ignore_combo_like_value(value: Any) -> bool:
    text = str(value).strip()
    if not text:
        return True
    if text.casefold() in _NON_COMBO_MARKERS:
        return True
    # Numeric modal periods/modes/drifts are not combo names.
    try:
        float(text)
        return True
    except ValueError:
        return False


def _values_for_column(rows: Sequence[Mapping[str, Any]], column: str) -> tuple[Any, ...]:
    values: list[Any] = []
    for row in rows:
        for key, value in row.items():
            if _casefold(key) == _casefold(column) and value not in {None, ""}:
                values.append(value)
                break
    return tuple(values)


def _identity_aliases(field: str) -> tuple[str, ...]:
    normalized = _casefold(field)
    aliases = _IDENTITY_ALIASES.get(normalized, (field,))
    if field not in aliases:
        aliases = (field,) + aliases
    return aliases


__all__ = ["EtabsTableFitAuditor"]
