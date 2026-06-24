"""Pure diagnostic construction helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import DiagnosticEvent, DiagnosticSeverity


def info_event(
    code: str,
    message: str,
    *,
    operation: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> DiagnosticEvent:
    return DiagnosticEvent(
        code=code,
        message=message,
        severity=DiagnosticSeverity.INFO,
        operation=operation,
        details=details or {},
    )


def error_event(
    code: str,
    message: str,
    *,
    operation: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> DiagnosticEvent:
    return DiagnosticEvent(
        code=code,
        message=message,
        severity=DiagnosticSeverity.ERROR,
        operation=operation,
        details=details or {},
    )
