from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Section:
    section_id: str
    width_mm: float | None
    depth_mm: float | None


@dataclass(frozen=True)
class Beam:
    element_id: str
    label: str
    story_id: str
    section_id: str


@dataclass(frozen=True)
class Column:
    element_id: str
    label: str
    story_id: str
    section_id: str


@dataclass(frozen=True)
class CanonicalSnapshot:
    sections: Mapping[str, Section]
    beams: Mapping[str, Beam]
    columns: Mapping[str, Column] = field(default_factory=dict)


@dataclass(frozen=True)
class FormulaTrace:
    display_expression: str
    lhs_label: str
    lhs_value: float | None
    operator: str
    rhs_value: float | None
    result: bool | None


@dataclass(frozen=True)
class Evidence:
    evidence_type: str
    confidence: str
    source_fields: list[str]
    source_values: Mapping[str, Any]
    unit_conversion_status: str
    combo_family_status: str
    notes: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SubCheckResult:
    step_id: str
    status: str
    value: float
    limit: float
    unit: str
    ratio: float
    message: str
    formula_trace: FormulaTrace
    evidence: Evidence


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    check_family: str
    element_type: str
    element_label: str
    story: str
    status: str
    ratio: float | None
    value: float | None
    limit: float | None
    unit: str
    evaluation_level: str
    tbdy_ref: str
    message: str
    action: str
    category: str
    severity: str
    report_section: str
    evidence: Evidence
    sub_checks: list[SubCheckResult]


@dataclass(frozen=True)
class WorkbenchCell:
    cell_id: str
    title: str
    check_id: str
    element_label: str
    story: str
    status: str
    evaluation_level: str
    input_panel: Mapping[str, Any]
    formula_panel: list[FormulaTrace]
    result_panel: Mapping[str, Any]
    evidence_panel: Evidence
    code_ref: Mapping[str, Any]
