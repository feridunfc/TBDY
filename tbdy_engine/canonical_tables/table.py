"""Canonical table DTO used by provider foundation.

Data-only: no CheckResult, no OK/FAIL status, no formulas, no pass rules, and no
feature resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from tbdy_engine.canonical_tables.diagnostics import ProviderDiagnostic
from tbdy_engine.contracts.models import freeze_data


_FORBIDDEN_TABLE_KEYS = {"check_result", "checkresults", "pass_rule", "formula", "features"}
_FORBIDDEN_STATUS_VALUES = {"OK", "FAIL"}


@dataclass(frozen=True, slots=True)
class CanonicalTable:
    table_key: str
    actual_table_name: str | None
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    units: Mapping[str, str]
    source: str
    diagnostics: tuple[ProviderDiagnostic, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        table_key: str,
        actual_table_name: str | None = None,
        columns: Sequence[str] | None = None,
        rows: Sequence[Mapping[str, Any]] | None = None,
        units: Mapping[str, str] | None = None,
        source: str = "FAKE_PROVIDER",
        diagnostics: Sequence[ProviderDiagnostic] | None = None,
    ) -> None:
        if not table_key:
            raise ValueError("CanonicalTable.table_key is required")
        if any(term in table_key.lower() for term in _FORBIDDEN_TABLE_KEYS):
            raise ValueError("CanonicalTable must not represent CheckResult/pass_rule/formula/feature objects")
        normalized_columns = tuple(str(c) for c in (columns or ()))
        for column in normalized_columns:
            if column.lower() in _FORBIDDEN_TABLE_KEYS:
                raise ValueError("CanonicalTable columns must not contain CheckResult/formula/pass_rule/feature keys")
        normalized_rows = tuple(freeze_data(dict(row)) for row in (rows or ()))
        normalized_units = freeze_data(dict(units or {}))
        normalized_diagnostics = tuple(diagnostics or ())
        self._validate_no_ok_fail(normalized_rows)
        object.__setattr__(self, "table_key", table_key)
        object.__setattr__(self, "actual_table_name", actual_table_name)
        object.__setattr__(self, "columns", normalized_columns)
        object.__setattr__(self, "rows", normalized_rows)
        object.__setattr__(self, "units", normalized_units)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "diagnostics", normalized_diagnostics)

    @staticmethod
    def _validate_no_ok_fail(rows: Sequence[Mapping[str, Any]]) -> None:
        for row in rows:
            for key, value in row.items():
                if str(key).lower() in _FORBIDDEN_TABLE_KEYS:
                    raise ValueError("CanonicalTable rows must not contain CheckResult/formula/pass_rule/feature keys")
                if isinstance(value, str) and value in _FORBIDDEN_STATUS_VALUES:
                    raise ValueError("CanonicalTable/provider data must not emit OK/FAIL status values")

    @property
    def is_missing(self) -> bool:
        return any(d.code.value == "TABLE_MISSING" for d in self.diagnostics)

    @property
    def is_empty(self) -> bool:
        return any(d.code.value == "TABLE_EMPTY" for d in self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_key": self.table_key,
            "actual_table_name": self.actual_table_name,
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
            "units": dict(self.units),
            "source": self.source,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }


__all__ = ["CanonicalTable"]
