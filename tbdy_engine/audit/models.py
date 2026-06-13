"""Audit-only models for ETABS table/contract fit (C5.2).

These models describe whether provider table metadata can satisfy the current
contract constitution. They do not execute checks, compute ratios, or emit
engineering decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from tbdy_engine.contracts.models import freeze_data

_FORBIDDEN_TOKENS = ("CheckResult", "check_result", " OK", " FAIL", "'OK'", "'FAIL'", '"OK"', '"FAIL"', "pass_rule")


class AuditStatus(StrEnum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    RESOLVABLE = "RESOLVABLE"
    UNKNOWN = "UNKNOWN"
    FORBIDDEN_FOR_PURPOSE = "FORBIDDEN_FOR_PURPOSE"


class AuditSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class AuditDiagnostic:
    severity: AuditSeverity | str
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", AuditSeverity(str(self.severity)))
        object.__setattr__(self, "details", freeze_data(dict(self.details)))
        if not self.code:
            raise ValueError("AuditDiagnostic.code is required")
        if not self.message:
            raise ValueError("AuditDiagnostic.message is required")
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {"severity": self.severity.value, "code": self.code, "message": self.message, "details": dict(self.details)}


def _reject_forbidden(value: Any) -> None:
    text = repr(value)
    for token in _FORBIDDEN_TOKENS:
        if token in text:
            raise ValueError("Audit models must not contain CheckResult, OK/FAIL, ratios, or pass_rule semantics")


@dataclass(frozen=True, slots=True)
class EtabsTableInventory:
    actual_table_name: str
    canonical_table_key: str | None
    matched_by: str
    available_columns: tuple[str, ...]
    row_count: int
    diagnostics: tuple[AuditDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.matched_by not in {"exact", "alias", "none"}:
            raise ValueError("matched_by must be exact, alias, or none")
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "actual_table_name": self.actual_table_name,
            "canonical_table_key": self.canonical_table_key,
            "matched_by": self.matched_by,
            "available_columns": list(self.available_columns),
            "row_count": self.row_count,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class TableHeadersReport:
    table_key: str | None
    actual_table_name: str
    matched_by: str
    available_columns: tuple[str, ...]
    row_count: int
    sample_rows: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    diagnostics: tuple[AuditDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.matched_by not in {"exact", "alias", "none"}:
            raise ValueError("matched_by must be exact, alias, or none")
        object.__setattr__(self, "sample_rows", freeze_data([dict(x) for x in self.sample_rows]))
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_key": self.table_key,
            "actual_table_name": self.actual_table_name,
            "matched_by": self.matched_by,
            "available_columns": list(self.available_columns),
            "row_count": self.row_count,
            "sample_rows": [dict(x) for x in self.sample_rows],
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class TableContractFitReport:
    table_key: str
    expected_aliases: tuple[str, ...]
    matched_actual_table_name: str | None
    required_columns: tuple[str, ...]
    matched_columns: tuple[str, ...]
    missing_columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    status: AuditStatus | str
    diagnostics: tuple[AuditDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AuditStatus(str(self.status)))
        if self.status not in {AuditStatus.MATCHED, AuditStatus.PARTIAL, AuditStatus.MISSING}:
            raise ValueError("TableContractFitReport.status must be MATCHED, PARTIAL, or MISSING")
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_key": self.table_key,
            "expected_aliases": list(self.expected_aliases),
            "matched_actual_table_name": self.matched_actual_table_name,
            "required_columns": list(self.required_columns),
            "matched_columns": list(self.matched_columns),
            "missing_columns": list(self.missing_columns),
            "extra_columns": list(self.extra_columns),
            "status": self.status.value,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class FeatureSourceFitReport:
    feature_name: str
    element_type: str
    source_kind: str
    table_key: str | None
    table_status: str
    field_aliases: tuple[str, ...]
    matched_column: str | None
    missing_columns: tuple[str, ...]
    required_filters: tuple[Mapping[str, Any], ...]
    identity_fields_required: tuple[str, ...]
    identity_fields_available: tuple[str, ...]
    combo_family: str | None
    status: AuditStatus | str
    reason: str | None = None
    custom_resolver: str | None = None
    required_inputs: tuple[str, ...] = field(default_factory=tuple)
    unit: str | None = None
    expected_evidence_requirements: tuple[str, ...] = field(default_factory=tuple)
    diagnostics: tuple[AuditDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AuditStatus(str(self.status)))
        if self.status not in {AuditStatus.RESOLVABLE, AuditStatus.PARTIAL, AuditStatus.MISSING}:
            raise ValueError("FeatureSourceFitReport.status must be RESOLVABLE, PARTIAL, or MISSING")
        object.__setattr__(self, "required_filters", freeze_data([dict(x) for x in self.required_filters]))
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "feature_name": self.feature_name,
            "element_type": self.element_type,
            "source_kind": self.source_kind,
            "table_key": self.table_key,
            "table_status": self.table_status,
            "field_aliases": list(self.field_aliases),
            "matched_column": self.matched_column,
            "missing_columns": list(self.missing_columns),
            "required_filters": [dict(x) for x in self.required_filters],
            "identity_fields_required": list(self.identity_fields_required),
            "identity_fields_available": list(self.identity_fields_available),
            "combo_family": self.combo_family,
            "status": self.status.value,
            "reason": self.reason,
            "custom_resolver": self.custom_resolver,
            "required_inputs": list(self.required_inputs),
            "unit": self.unit,
            "expected_evidence_requirements": list(self.expected_evidence_requirements),
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }
        return payload


@dataclass(frozen=True, slots=True)
class ComboFamilyFitReport:
    raw_combo_name: str
    matched_combo_family: str | None
    matched_by: str
    reinforcement_design_allowed: bool | None
    read_only: bool | None
    status: AuditStatus | str
    source_table: str | None = None
    source_column: str | None = None
    diagnostics: tuple[AuditDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AuditStatus(str(self.status)))
        if self.status not in {AuditStatus.MATCHED, AuditStatus.UNKNOWN, AuditStatus.FORBIDDEN_FOR_PURPOSE}:
            raise ValueError("ComboFamilyFitReport.status must be MATCHED, UNKNOWN, or FORBIDDEN_FOR_PURPOSE")
        if self.matched_by not in {"pattern", "alias", "none"}:
            raise ValueError("matched_by must be pattern, alias, or none")
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_combo_name": self.raw_combo_name,
            "matched_combo_family": self.matched_combo_family,
            "matched_by": self.matched_by,
            "reinforcement_design_allowed": self.reinforcement_design_allowed,
            "read_only": self.read_only,
            "status": self.status.value,
            "source_table": self.source_table,
            "source_column": self.source_column,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ElementIdentityFitReport:
    element_type: str
    required_identity_fields: tuple[str, ...]
    available_identity_columns: tuple[str, ...]
    identity_mapping: Mapping[str, str]
    status: AuditStatus | str
    diagnostics: tuple[AuditDiagnostic, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AuditStatus(str(self.status)))
        if self.status not in {AuditStatus.MATCHED, AuditStatus.PARTIAL, AuditStatus.MISSING}:
            raise ValueError("ElementIdentityFitReport.status must be MATCHED, PARTIAL, or MISSING")
        object.__setattr__(self, "identity_mapping", freeze_data(dict(self.identity_mapping)))
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "element_type": self.element_type,
            "required_identity_fields": list(self.required_identity_fields),
            "available_identity_columns": list(self.available_identity_columns),
            "identity_mapping": dict(self.identity_mapping),
            "status": self.status.value,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class MissingRequiredSourcesReport:
    missing_tables: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    missing_columns: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    missing_identity_fields: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    missing_combo_policies: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    missing_design_context: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_tables", freeze_data([dict(x) for x in self.missing_tables]))
        object.__setattr__(self, "missing_columns", freeze_data([dict(x) for x in self.missing_columns]))
        object.__setattr__(self, "missing_identity_fields", freeze_data([dict(x) for x in self.missing_identity_fields]))
        object.__setattr__(self, "missing_combo_policies", freeze_data([dict(x) for x in self.missing_combo_policies]))
        object.__setattr__(self, "missing_design_context", freeze_data([dict(x) for x in self.missing_design_context]))
        _reject_forbidden(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "missing_tables": [dict(x) for x in self.missing_tables],
            "missing_columns": [dict(x) for x in self.missing_columns],
            "missing_identity_fields": [dict(x) for x in self.missing_identity_fields],
            "missing_combo_policies": [dict(x) for x in self.missing_combo_policies],
            "missing_design_context": [dict(x) for x in self.missing_design_context],
        }


__all__ = [
    "AuditDiagnostic",
    "AuditSeverity",
    "AuditStatus",
    "EtabsTableInventory",
    "TableHeadersReport",
    "TableContractFitReport",
    "FeatureSourceFitReport",
    "ComboFamilyFitReport",
    "ElementIdentityFitReport",
    "MissingRequiredSourcesReport",
]
