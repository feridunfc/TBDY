"""Authoritative runtime execution trace for geometry CoverageRows.

The trace records only linkage metadata from the existing in-memory
CoverageRow -> adapter -> MinimalCheckEngine -> CheckResult path. It does not
reconstruct coverage or expose engineering payloads.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TypeAlias

from tbdy_engine.checks.input_adapter import CheckInputBuildDiagnostic
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.models import CoverageRow

CoverageExecutionTraceKey: TypeAlias = tuple[str, str, str]
_ALLOWED_ADAPTER_STATUSES = frozenset({"READY", "BLOCKED", "NO_DATA", "OUT_OF_SCOPE"})
_ADAPTER_LEVEL_CHECK_ID = "geometry_check_input_adapter"


@dataclass(frozen=True, slots=True)
class CoverageExecutionTraceRow:
    component_type: str
    component_id: str
    check_id: str
    coverage_status: str
    check_input_emitted: bool
    adapter_status: str
    adapter_reason: str | None
    adapter_diagnostic_index: int | None
    check_result_emitted: bool
    check_result_index: int | None
    check_result_status: str | None

    def __post_init__(self) -> None:
        for field_name in ("component_type", "component_id", "check_id", "coverage_status"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"CoverageExecutionTraceRow.{field_name} must be a non-empty string")
        if not isinstance(self.check_input_emitted, bool):
            raise TypeError("CoverageExecutionTraceRow.check_input_emitted must be bool")
        if not isinstance(self.check_result_emitted, bool):
            raise TypeError("CoverageExecutionTraceRow.check_result_emitted must be bool")
        if self.adapter_status not in _ALLOWED_ADAPTER_STATUSES:
            raise ValueError("Unsupported coverage execution trace adapter_status")
        _validate_optional_index("adapter_diagnostic_index", self.adapter_diagnostic_index)
        _validate_optional_index("check_result_index", self.check_result_index)

        if self.check_input_emitted:
            if self.adapter_status != "READY":
                raise ValueError("Emitted CheckInput requires adapter_status READY")
            if self.adapter_reason is not None:
                raise ValueError("Emitted CheckInput requires adapter_reason null")
            if self.adapter_diagnostic_index is not None:
                raise ValueError("Emitted CheckInput requires adapter_diagnostic_index null")
            if not self.check_result_emitted:
                raise ValueError("Emitted CheckInput requires an emitted CheckResult")
            if self.check_result_index is None:
                raise ValueError("Emitted CheckResult requires check_result_index")
            if not isinstance(self.check_result_status, str) or not self.check_result_status:
                raise ValueError("Emitted CheckResult requires a non-empty check_result_status")
        else:
            if self.adapter_status == "READY":
                raise ValueError("Non-emitted CheckInput cannot have adapter_status READY")
            if not isinstance(self.adapter_reason, str) or not self.adapter_reason.strip():
                raise ValueError("Non-emitted CheckInput requires a non-empty adapter_reason")
            if self.adapter_diagnostic_index is None:
                raise ValueError("Non-emitted CheckInput requires adapter_diagnostic_index")
            if self.check_result_emitted:
                raise ValueError("Non-emitted CheckInput cannot emit a CheckResult")
            if self.check_result_index is not None:
                raise ValueError("Non-emitted CheckInput requires check_result_index null")
            if self.check_result_status is not None:
                raise ValueError("Non-emitted CheckInput requires check_result_status null")

    def as_dict(self) -> dict[str, object]:
        return {
            "component_type": self.component_type,
            "component_id": self.component_id,
            "check_id": self.check_id,
            "coverage_status": self.coverage_status,
            "check_input_emitted": self.check_input_emitted,
            "adapter_status": self.adapter_status,
            "adapter_reason": self.adapter_reason,
            "adapter_diagnostic_index": self.adapter_diagnostic_index,
            "check_result_emitted": self.check_result_emitted,
            "check_result_index": self.check_result_index,
            "check_result_status": self.check_result_status,
        }


def coverage_execution_trace_key(
    row: CoverageExecutionTraceRow,
) -> CoverageExecutionTraceKey:
    if not isinstance(row, CoverageExecutionTraceRow):
        raise TypeError("coverage execution trace rows must contain CoverageExecutionTraceRow objects")
    return (row.component_type, row.component_id, row.check_id)


def coverage_row_identity(row: CoverageRow) -> CoverageExecutionTraceKey:
    if not isinstance(row, CoverageRow):
        raise TypeError("coverage rows must contain CoverageRow objects")
    return (row.component_type, row.component_id, row.check_id)


def canonicalize_coverage_execution_trace(
    rows: Iterable[CoverageExecutionTraceRow],
    *,
    coverage_rows: Sequence[CoverageRow] | None = None,
    check_results: Sequence[CheckResult] | None = None,
    adapter_diagnostics: Sequence[CheckInputBuildDiagnostic] | None = None,
) -> tuple[CoverageExecutionTraceRow, ...]:
    """Fail closed on duplicate or inconsistent runtime linkage."""

    collected = tuple(rows)
    seen_keys: set[CoverageExecutionTraceKey] = set()
    result_indices: list[int] = []
    diagnostic_indices: list[int] = []
    for row in collected:
        key = coverage_execution_trace_key(row)
        if key in seen_keys:
            raise ValueError(
                "Duplicate coverage execution trace canonical key: "
                f"component_type={key[0]!r}, component_id={key[1]!r}, check_id={key[2]!r}"
            )
        seen_keys.add(key)
        if row.check_result_index is not None:
            result_indices.append(row.check_result_index)
        if row.adapter_diagnostic_index is not None:
            diagnostic_indices.append(row.adapter_diagnostic_index)

    _reject_duplicate_indices(result_indices, "CheckResult")
    _reject_duplicate_indices(diagnostic_indices, "adapter diagnostic")
    canonical = tuple(sorted(collected, key=coverage_execution_trace_key))

    if coverage_rows is not None:
        coverage_by_key: dict[CoverageExecutionTraceKey, CoverageRow] = {}
        for coverage_row in coverage_rows:
            key = coverage_row_identity(coverage_row)
            if key in coverage_by_key:
                raise ValueError(f"Duplicate authoritative CoverageRow canonical key in trace validation: {key!r}")
            coverage_by_key[key] = coverage_row
        if set(coverage_by_key) != seen_keys:
            raise ValueError("Coverage execution trace keys must exactly equal authoritative CoverageRow keys")
        for row in canonical:
            coverage_row = coverage_by_key[coverage_execution_trace_key(row)]
            if row.coverage_status != coverage_row.coverage_status.value:
                raise ValueError("Coverage execution trace coverage_status does not match authoritative CoverageRow")

    if check_results is not None:
        _validate_check_result_links(canonical, check_results)
    if adapter_diagnostics is not None:
        _validate_adapter_diagnostic_links(canonical, adapter_diagnostics)
    return canonical


def coverage_execution_trace_payload(
    rows: Iterable[CoverageExecutionTraceRow],
) -> list[dict[str, object]]:
    return [row.as_dict() for row in canonicalize_coverage_execution_trace(rows)]


def _validate_check_result_links(
    rows: Sequence[CoverageExecutionTraceRow],
    check_results: Sequence[CheckResult],
) -> None:
    referenced: set[int] = set()
    for row in rows:
        if row.check_result_index is None:
            continue
        index = row.check_result_index
        if index >= len(check_results):
            raise ValueError(f"Coverage execution trace CheckResult index out of range: {index}")
        result = check_results[index]
        if not isinstance(result, CheckResult):
            raise TypeError("check_results must contain CheckResult objects")
        if (
            result.check_id != row.check_id
            or result.component_type != row.component_type
            or result.component != row.component_id
        ):
            raise ValueError("Coverage execution trace CheckResult identity mismatch")
        if result.status.value != row.check_result_status:
            raise ValueError("Coverage execution trace CheckResult status mismatch")
        referenced.add(index)
    expected = set(range(len(check_results)))
    if referenced != expected:
        raise ValueError("Every CheckResult must be referenced exactly once by the coverage execution trace")


def _validate_adapter_diagnostic_links(
    rows: Sequence[CoverageExecutionTraceRow],
    diagnostics: Sequence[CheckInputBuildDiagnostic],
) -> None:
    referenced: set[int] = set()
    for row in rows:
        if row.adapter_diagnostic_index is None:
            continue
        index = row.adapter_diagnostic_index
        if index >= len(diagnostics):
            raise ValueError(f"Coverage execution trace adapter diagnostic index out of range: {index}")
        diagnostic = diagnostics[index]
        if not isinstance(diagnostic, CheckInputBuildDiagnostic):
            raise TypeError("adapter_diagnostics must contain CheckInputBuildDiagnostic objects")
        if (
            diagnostic.check_id != row.check_id
            or diagnostic.component_type != row.component_type
            or diagnostic.component_id != row.component_id
        ):
            raise ValueError("Coverage execution trace adapter diagnostic identity mismatch")
        if diagnostic.status != row.adapter_status:
            raise ValueError("Coverage execution trace adapter diagnostic status mismatch")
        if diagnostic.reason != row.adapter_reason:
            raise ValueError("Coverage execution trace adapter diagnostic reason mismatch")
        referenced.add(index)

    coverage_specific = {
        index
        for index, diagnostic in enumerate(diagnostics)
        if diagnostic.check_id != _ADAPTER_LEVEL_CHECK_ID
    }
    if referenced != coverage_specific:
        raise ValueError(
            "Every coverage-specific adapter diagnostic must be referenced exactly once by the trace"
        )


def _validate_optional_index(field_name: str, value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"CoverageExecutionTraceRow.{field_name} must be a non-negative integer or null")


def _reject_duplicate_indices(indices: Sequence[int], label: str) -> None:
    if len(indices) != len(set(indices)):
        raise ValueError(f"Coverage execution trace links one {label} index more than once")


__all__ = [
    "CoverageExecutionTraceKey",
    "CoverageExecutionTraceRow",
    "canonicalize_coverage_execution_trace",
    "coverage_execution_trace_key",
    "coverage_execution_trace_payload",
    "coverage_row_identity",
]
