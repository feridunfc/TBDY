"""Fake ETABS provider for tests/debug only.

C3 intentionally does not implement live ETABS integration.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from tbdy_engine.canonical_tables.diagnostics import DiagnosticCode, DiagnosticSeverity, ProviderDiagnostic
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.providers.table_registry import TableRegistry
from tbdy_engine.tools.validate_contract_constitution import DEFAULT_CATALOG_DIR


class FakeEtabsProvider:
    """Test-only provider returning CanonicalTable objects for requested keys."""

    source = "FAKE_PROVIDER"

    def __init__(
        self,
        *,
        registry: TableRegistry | None = None,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        units: Mapping[str, str] | None = None,
    ) -> None:
        self.registry = registry or TableRegistry.from_catalog_dir(DEFAULT_CATALOG_DIR)
        self._tables = {str(k): tuple(dict(r) for r in v) for k, v in (tables or {}).items()}
        self._units = dict(units or {})

    def list_tables(self) -> list[str]:
        return sorted(self._tables)

    def get_units(self) -> Mapping[str, str]:
        return dict(self._units)

    def get_table(self, table_key: str) -> CanonicalTable:
        preferred = self.registry.preferred_actual_name(table_key)
        found = self._lookup_rows(table_key, preferred)
        rows = None if found is None else found[1]
        actual_name = preferred if found is None else found[0]
        if rows is None:
            return CanonicalTable(
                table_key=table_key,
                actual_table_name=actual_name,
                columns=[],
                rows=[],
                units={},
                source=self.source,
                diagnostics=[
                    ProviderDiagnostic(
                        severity=DiagnosticSeverity.ERROR,
                        code=DiagnosticCode.TABLE_MISSING,
                        message=f"Table not supplied by fake provider: {table_key}",
                        details={"table_key": table_key, "actual_table_name": preferred},
                    )
                ],
            )
        columns = tuple(rows[0].keys()) if rows else tuple()
        diagnostics: list[ProviderDiagnostic] = []
        if not rows:
            diagnostics.append(
                ProviderDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    code=DiagnosticCode.TABLE_EMPTY,
                    message=f"Table is present but empty: {table_key}",
                    details={"table_key": table_key, "actual_table_name": preferred},
                )
            )
        return CanonicalTable(
            table_key=table_key,
            actual_table_name=actual_name,
            columns=columns,
            rows=rows,
            units=self._units,
            source=self.source,
            diagnostics=diagnostics,
        )

    def _lookup_rows(self, table_key: str, preferred: str | None) -> tuple[str, tuple[Mapping[str, Any], ...]] | None:
        candidates = [table_key]
        if preferred:
            candidates.append(preferred)
        candidates.extend(self.registry.aliases_for_key(table_key))
        for name in candidates:
            if name in self._tables:
                return name, self._tables[name]
        return None


__all__ = ["FakeEtabsProvider"]
