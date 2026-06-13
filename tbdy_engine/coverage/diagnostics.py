"""Coverage diagnostics for C5.

Coverage diagnostics describe runnability only. They are not CheckResult objects
and never encode engineering pass/fail decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from tbdy_engine.contracts.models import freeze_data


class CoverageDiagnosticSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CoverageDiagnosticCode(StrEnum):
    CHECK_UNKNOWN = "CHECK_UNKNOWN"
    FEATURE_MISSING = "FEATURE_MISSING"
    EVIDENCE_PARTIAL = "EVIDENCE_PARTIAL"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    DESIGN_CONTEXT_MISSING = "DESIGN_CONTEXT_MISSING"
    COMPONENT_TYPE_UNKNOWN = "COMPONENT_TYPE_UNKNOWN"
    CONTRACT_ALIGNMENT_MISSING = "CONTRACT_ALIGNMENT_MISSING"
    FORBIDDEN_CHECK_RESULT = "FORBIDDEN_CHECK_RESULT"
    FORBIDDEN_DECISION_STATUS = "FORBIDDEN_DECISION_STATUS"
    EXPECTED_SOURCE_RECORDED = "EXPECTED_SOURCE_RECORDED"
    EXPECTED_SOURCE_MISSING = "EXPECTED_SOURCE_MISSING"


@dataclass(frozen=True, slots=True)
class CoverageDiagnostic:
    severity: CoverageDiagnosticSeverity | str
    code: CoverageDiagnosticCode | str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", CoverageDiagnosticSeverity(str(self.severity)))
        object.__setattr__(self, "code", CoverageDiagnosticCode(str(self.code)))
        object.__setattr__(self, "details", freeze_data(dict(self.details)))
        if not self.message:
            raise ValueError("CoverageDiagnostic.message is required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code.value,
            "message": self.message,
            "details": dict(self.details),
        }


__all__ = ["CoverageDiagnostic", "CoverageDiagnosticCode", "CoverageDiagnosticSeverity"]
