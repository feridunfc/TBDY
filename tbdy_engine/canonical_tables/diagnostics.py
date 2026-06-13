"""Structured diagnostics for canonical table/provider infrastructure."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class DiagnosticSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class DiagnosticCode(StrEnum):
    TABLE_MISSING = "TABLE_MISSING"
    TABLE_EMPTY = "TABLE_EMPTY"
    COLUMN_MISSING = "COLUMN_MISSING"
    ALIAS_NOT_FOUND = "ALIAS_NOT_FOUND"
    UNIT_UNKNOWN = "UNIT_UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderDiagnostic:
    severity: DiagnosticSeverity | str
    code: DiagnosticCode | str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", DiagnosticSeverity(str(self.severity)))
        object.__setattr__(self, "code", DiagnosticCode(str(self.code)))
        object.__setattr__(self, "details", dict(self.details))
        if not self.message:
            raise ValueError("ProviderDiagnostic.message is required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code.value,
            "message": self.message,
            "details": dict(self.details),
        }


__all__ = ["DiagnosticCode", "DiagnosticSeverity", "ProviderDiagnostic"]
