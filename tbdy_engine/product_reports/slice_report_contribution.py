"""Render-neutral report contribution contract for product vertical slices.

A slice report contribution is a projection of already-resolved factual,
regulatory, design, or formal-check results.  This module owns no engineering
formula, limit, selection rule, PASS/FAIL decision, or ETABS acquisition.

Renderers (JSON/Excel/PDF/engineering calculation sheets) consume the same
contract so presentation cannot become a second engineering authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class SliceReportContributionError(ValueError):
    """Raised when a report contribution is structurally invalid."""


_ALLOWED_KINDS = frozenset({"FACTUAL", "REGULATORY", "DESIGN", "CHECK", "COMPOSITE"})
_ALLOWED_STATUSES = frozenset(
    {
        "PROVEN",
        "PASS",
        "FAIL",
        "BLOCKED",
        "NO_DATA",
        "PARTIAL",
        "NOT_EVALUATED",
        "OUT_OF_SCOPE",
        "REANALYSIS_REQUIRED",
    }
)
_ALLOWED_ROLES = frozenset({"IDENTITY", "INPUT", "RESULT", "LIMIT", "STATUS", "AUTHORITY", "NOTE"})
_ALLOWED_VIEWS = frozenset({"EXECUTIVE", "ENGINEERING", "AUDIT"})


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SliceReportContributionError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _scalar(value: Any, label: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SliceReportContributionError(f"{label} must be finite")
        return value
    raise SliceReportContributionError(
        f"{label} must be a report scalar (str/int/float/bool/null), got {type(value).__name__}"
    )


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(value, f"{label}[{index}]") for index, value in enumerate(values))
    if len(set(refs)) != len(refs):
        raise SliceReportContributionError(f"{label} must not contain duplicates")
    return refs


def _freeze_row(row: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, value in row.items():
        canonical_key = _text(str(key), f"{label}.key")
        frozen[canonical_key] = _scalar(value, f"{label}.{canonical_key}")
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class ReportField:
    key: str
    label: str
    value: str | int | float | bool | None
    unit: str | None = None
    role: str = "RESULT"
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _text(self.key, "field.key"))
        object.__setattr__(self, "label", _text(self.label, "field.label"))
        object.__setattr__(self, "value", _scalar(self.value, f"field {self.key}.value"))
        object.__setattr__(self, "unit", _optional_text(self.unit, f"field {self.key}.unit"))
        object.__setattr__(self, "note", _optional_text(self.note, f"field {self.key}.note"))
        if self.role not in _ALLOWED_ROLES:
            raise SliceReportContributionError(
                f"field {self.key}.role must be one of {sorted(_ALLOWED_ROLES)}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "role": self.role,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ReportTable:
    table_id: str
    title: str
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    purpose: str = "DETAIL"

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_id", _text(self.table_id, "table.table_id"))
        object.__setattr__(self, "title", _text(self.title, "table.title"))
        columns = tuple(_text(value, "table.columns[]") for value in self.columns)
        if not columns or len(set(columns)) != len(columns):
            raise SliceReportContributionError("table.columns must be nonempty and unique")
        object.__setattr__(self, "columns", columns)
        frozen_rows: list[Mapping[str, Any]] = []
        expected = set(columns)
        for index, row in enumerate(self.rows):
            frozen = _freeze_row(row, f"table {self.table_id}.rows[{index}]")
            extras = set(frozen) - expected
            if extras:
                raise SliceReportContributionError(
                    f"table {self.table_id}.rows[{index}] has undeclared columns: {sorted(extras)}"
                )
            frozen_rows.append(frozen)
        object.__setattr__(self, "rows", tuple(frozen_rows))
        object.__setattr__(self, "purpose", _text(self.purpose, "table.purpose"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "title": self.title,
            "purpose": self.purpose,
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class ReportCalculation:
    calculation_id: str
    title: str
    formula: str | None
    inputs: tuple[ReportField, ...]
    outputs: tuple[ReportField, ...]
    authority_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    governing_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "calculation_id", _text(self.calculation_id, "calculation.calculation_id"))
        object.__setattr__(self, "title", _text(self.title, "calculation.title"))
        object.__setattr__(self, "formula", _optional_text(self.formula, "calculation.formula"))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "authority_refs", _refs(self.authority_refs, "calculation.authority_refs"))
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs, "calculation.evidence_refs"))
        object.__setattr__(self, "governing_ref", _optional_text(self.governing_ref, "calculation.governing_ref"))
        if not self.outputs:
            raise SliceReportContributionError("calculation.outputs must contain already-resolved output(s)")

    def as_dict(self) -> dict[str, Any]:
        return {
            "calculation_id": self.calculation_id,
            "title": self.title,
            "formula": self.formula,
            "inputs": [field.as_dict() for field in self.inputs],
            "outputs": [field.as_dict() for field in self.outputs],
            "authority_refs": list(self.authority_refs),
            "evidence_refs": list(self.evidence_refs),
            "governing_ref": self.governing_ref,
        }


@dataclass(frozen=True, slots=True)
class SliceReportContribution:
    slice_id: str
    title: str
    contribution_kind: str
    status: str
    component_type: str | None = None
    component_id: str | None = None
    summary_fields: tuple[ReportField, ...] = ()
    tables: tuple[ReportTable, ...] = ()
    calculations: tuple[ReportCalculation, ...] = ()
    authority_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    render_views: tuple[str, ...] = ("EXECUTIVE", "ENGINEERING", "AUDIT")

    def __post_init__(self) -> None:
        object.__setattr__(self, "slice_id", _text(self.slice_id, "slice.slice_id"))
        object.__setattr__(self, "title", _text(self.title, "slice.title"))
        if self.contribution_kind not in _ALLOWED_KINDS:
            raise SliceReportContributionError(
                f"slice.contribution_kind must be one of {sorted(_ALLOWED_KINDS)}"
            )
        if self.status not in _ALLOWED_STATUSES:
            raise SliceReportContributionError(f"slice.status must be one of {sorted(_ALLOWED_STATUSES)}")
        object.__setattr__(self, "component_type", _optional_text(self.component_type, "slice.component_type"))
        object.__setattr__(self, "component_id", _optional_text(self.component_id, "slice.component_id"))
        object.__setattr__(self, "summary_fields", tuple(self.summary_fields))
        object.__setattr__(self, "tables", tuple(self.tables))
        object.__setattr__(self, "calculations", tuple(self.calculations))
        object.__setattr__(self, "authority_refs", _refs(self.authority_refs, "slice.authority_refs"))
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs, "slice.evidence_refs"))
        object.__setattr__(self, "warnings", _refs(self.warnings, "slice.warnings"))
        views = tuple(_text(value, "slice.render_views[]") for value in self.render_views)
        if not views or len(set(views)) != len(views) or any(value not in _ALLOWED_VIEWS for value in views):
            raise SliceReportContributionError(
                f"slice.render_views must be unique values from {sorted(_ALLOWED_VIEWS)}"
            )
        object.__setattr__(self, "render_views", views)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "slice_report_contribution.v1",
            "artifact_type": "SLICE_REPORT_CONTRIBUTION",
            "slice_id": self.slice_id,
            "title": self.title,
            "contribution_kind": self.contribution_kind,
            "status": self.status,
            "component_type": self.component_type,
            "component_id": self.component_id,
            "summary_fields": [field.as_dict() for field in self.summary_fields],
            "tables": [table.as_dict() for table in self.tables],
            "calculations": [item.as_dict() for item in self.calculations],
            "authority_refs": list(self.authority_refs),
            "evidence_refs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "render_views": list(self.render_views),
            "presentation_contract": {
                "engineering_recalculation_allowed": False,
                "renderer_may_change_status": False,
                "renderer_may_change_governing_selection": False,
            },
        }


__all__ = [
    "ReportCalculation",
    "ReportField",
    "ReportTable",
    "SliceReportContribution",
    "SliceReportContributionError",
]
