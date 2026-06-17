"""Canonical CheckResult DTO for C13.4-P1 minimal CheckEngine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from tbdy_engine.contracts.models import freeze_data
from tbdy_engine.checks.diagnostics import CheckDiagnostic


class CheckStatus(StrEnum):
    OK = "OK"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NO_DATA = "NO_DATA"
    BLOCKED = "BLOCKED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class EvaluationLevel(StrEnum):
    DESIGN_LEVEL = "DESIGN_LEVEL"
    ETABS_DESIGN_RESULT = "ETABS_DESIGN_RESULT"
    SCREENING = "SCREENING"
    NO_DATA = "NO_DATA"


_ALLOWED_RATIO_TYPES = {
    None,
    "demand_over_capacity",
    "actual_over_minimum",
    "selected_over_required",
    "required_over_selected",
    "value_over_maximum",
    "value_over_minimum",
    "value_over_limit",
    "actual_over_required",
    "availability",
    "boolean",
}
_FORBIDDEN_EXTRA = {"id", "check_type"}
_NO_DATA_LEVEL_STATUSES = {CheckStatus.NO_DATA, CheckStatus.BLOCKED, CheckStatus.OUT_OF_SCOPE}


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    component: str
    component_type: str
    story: str | None
    section: str | None
    status: CheckStatus
    value: Any = None
    limit: Any = None
    demand: Any = None
    capacity: Any = None
    ratio: float | None = None
    ratio_type: str | None = None
    pass_rule: str | None = None
    unit: str | None = None
    evaluation_level: EvaluationLevel = EvaluationLevel.SCREENING
    evidence: tuple[Any, ...] = field(default_factory=tuple)
    messages: tuple[str, ...] = field(default_factory=tuple)
    code_ref: str | None = None
    diagnostics: tuple[CheckDiagnostic, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        check_id: str,
        component: str,
        component_type: str,
        status: CheckStatus | str,
        story: str | None = None,
        section: str | None = None,
        value: Any = None,
        limit: Any = None,
        demand: Any = None,
        capacity: Any = None,
        ratio: float | None = None,
        ratio_type: str | None = None,
        pass_rule: str | None = None,
        unit: str | None = None,
        evaluation_level: EvaluationLevel | str = EvaluationLevel.SCREENING,
        evidence: Sequence[Any] | None = None,
        messages: Sequence[str] | None = None,
        code_ref: str | None = None,
        diagnostics: Sequence[CheckDiagnostic] | None = None,
        **extra: Any,
    ) -> None:
        if extra:
            legacy = sorted(set(extra) & _FORBIDDEN_EXTRA)
            if legacy:
                raise ValueError("CheckResult uses canonical check_id/component_type fields; legacy id/check_type forbidden")
            raise TypeError("Unexpected CheckResult field(s): " + ", ".join(sorted(extra)))
        if not check_id or not component or not component_type:
            raise ValueError("CheckResult requires check_id, component, and component_type")
        if ratio_type not in _ALLOWED_RATIO_TYPES:
            raise ValueError(f"Unknown ratio_type for CheckResult: {ratio_type}")
        normalized_status = CheckStatus(str(status))
        normalized_level = EvaluationLevel(str(evaluation_level))
        if normalized_status in _NO_DATA_LEVEL_STATUSES and normalized_level != EvaluationLevel.NO_DATA:
            normalized_level = EvaluationLevel.NO_DATA
        object.__setattr__(self, "check_id", check_id)
        object.__setattr__(self, "component", component)
        object.__setattr__(self, "component_type", component_type)
        object.__setattr__(self, "story", story)
        object.__setattr__(self, "section", section)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "limit", limit)
        object.__setattr__(self, "demand", demand)
        object.__setattr__(self, "capacity", capacity)
        object.__setattr__(self, "ratio", None if ratio is None else float(ratio))
        object.__setattr__(self, "ratio_type", ratio_type)
        object.__setattr__(self, "pass_rule", pass_rule)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "evaluation_level", normalized_level)
        object.__setattr__(self, "evidence", freeze_data(list(evidence or ())))
        object.__setattr__(self, "messages", tuple(str(m) for m in (messages or ())))
        object.__setattr__(self, "code_ref", code_ref)
        object.__setattr__(self, "diagnostics", tuple(diagnostics or ()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "component": self.component,
            "component_type": self.component_type,
            "story": self.story,
            "section": self.section,
            "status": self.status.value,
            "value": self.value,
            "limit": self.limit,
            "demand": self.demand,
            "capacity": self.capacity,
            "ratio": self.ratio,
            "ratio_type": self.ratio_type,
            "pass_rule": self.pass_rule,
            "unit": self.unit,
            "evaluation_level": self.evaluation_level.value,
            "evidence": list(self.evidence),
            "messages": list(self.messages),
            "code_ref": self.code_ref,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }


__all__ = ["CheckResult", "CheckStatus", "EvaluationLevel"]
