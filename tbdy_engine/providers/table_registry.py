"""Read-only alias resolver for ``tbdy_engine/catalogs/table_registry.yaml``."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import re

import yaml

from tbdy_engine.canonical_tables.diagnostics import DiagnosticCode, DiagnosticSeverity, ProviderDiagnostic
from tbdy_engine.contracts.models import freeze_data
from tbdy_engine.tools.validate_contract_constitution import DEFAULT_CATALOG_DIR


@dataclass(frozen=True, slots=True)
class TableRegistry:
    tables: Mapping[str, Any]

    @classmethod
    def from_catalog_dir(cls, catalog_dir: str | Path = DEFAULT_CATALOG_DIR) -> "TableRegistry":
        path = Path(catalog_dir) / "table_registry.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("table_registry.yaml must contain a YAML object")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TableRegistry":
        return cls(tables=freeze_data(dict(data.get("tables", {}))))

    def canonical_keys(self) -> tuple[str, ...]:
        return tuple(self.tables.keys())

    def aliases_for_key(self, table_key: str, *, provider: str = "etabs") -> tuple[str, ...]:
        row = self.tables.get(table_key)
        if not row:
            return tuple()
        provider_sources = row.get("provider_sources", {})
        aliases = tuple(str(v) for v in provider_sources.get(provider, ()) or ())
        logical = row.get("logical_name")
        if logical and logical not in aliases:
            aliases = (str(logical),) + aliases
        return aliases

    def preferred_actual_name(self, table_key: str, *, provider: str = "etabs") -> str | None:
        aliases = self.aliases_for_key(table_key, provider=provider)
        return aliases[0] if aliases else None

    def canonical_key_for_alias(self, actual_table_name: str, *, provider: str = "etabs") -> str | None:
        """Return canonical key for an actual ETABS table name.

        Matching is intentionally conservative: explicit aliases are required,
        but leading/trailing whitespace, duplicate spaces, and case drift are
        normalized. This handles ETABS variants such as ``" -  TS 500"``
        without introducing fuzzy table-name guessing.
        """
        normalized = normalize_table_name(actual_table_name)
        for table_key in self.tables:
            if normalize_table_name(table_key) == normalized:
                return table_key
            for alias in self.aliases_for_key(table_key, provider=provider):
                if normalize_table_name(alias) == normalized:
                    return table_key
        return None

    def diagnostic_for_unknown_alias(self, actual_table_name: str) -> ProviderDiagnostic:
        return ProviderDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code=DiagnosticCode.ALIAS_NOT_FOUND,
            message=f"No canonical table_key found for alias: {actual_table_name}",
            details={"actual_table_name": actual_table_name},
        )


def normalize_table_name(name: str) -> str:
    """Normalize safe ETABS table-name drift without fuzzy matching."""
    return re.sub(r"\s+", " ", str(name).strip()).casefold()


__all__ = ["TableRegistry", "normalize_table_name"]
