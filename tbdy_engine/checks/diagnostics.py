"""Minimal CheckEngine diagnostics for C6."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from tbdy_engine.contracts.models import freeze_data


class CheckDiagnosticSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CheckDiagnosticCode(StrEnum):
    COVERAGE_BLOCKED = "COVERAGE_BLOCKED"
    COVERAGE_PARTIAL = "COVERAGE_PARTIAL"
    FEATURE_MISSING = "FEATURE_MISSING"
    UNKNOWN_RATIO_TYPE = "UNKNOWN_RATIO_TYPE"
    UNKNOWN_PASS_RULE = "UNKNOWN_PASS_RULE"
    PASS_RULE_DEPRECATED = "PASS_RULE_DEPRECATED"
    FORMULA_FORBIDDEN = "FORMULA_FORBIDDEN"
    FORMULA_ERROR = "FORMULA_ERROR"
    CHECK_NOT_ALLOWED = "CHECK_NOT_ALLOWED"
    CHECK_DEFINITION_INVALID = "CHECK_DEFINITION_INVALID"


@dataclass(frozen=True, slots=True)
class CheckDiagnostic:
    severity: CheckDiagnosticSeverity | str
    code: CheckDiagnosticCode | str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", CheckDiagnosticSeverity(str(self.severity)))
        object.__setattr__(self, "code", CheckDiagnosticCode(str(self.code)))
        object.__setattr__(self, "details", freeze_data(dict(self.details or {})))

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code.value,
            "message": self.message,
            "details": dict(self.details),
        }


__all__ = ["CheckDiagnostic", "CheckDiagnosticCode", "CheckDiagnosticSeverity"]
