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
        """Return deterministic provider aliases without crossing source boundaries.

        The production ETABS catalog evolved from ``provider_sources.etabs`` to
        the explicit ``live_table_name`` field.  Both remain supported, while
        Excel inventory aliases are available only through an explicit Excel
        provider namespace and never leak into live ETABS resolution.
        """
        row = self.tables.get(table_key)
        if not row:
            return tuple()

        provider_name = str(provider or "").strip().casefold()
        provider_sources = row.get("provider_sources", {})
        provider_sources = provider_sources if isinstance(provider_sources, Mapping) else {}
        candidates: list[Any] = []

        if provider_name == "etabs":
            candidates.append(row.get("live_table_name"))
            candidates.extend(_alias_values(provider_sources.get("etabs")))
            candidates.append(row.get("logical_name"))
        elif provider_name in {"excel", "excel_inventory"}:
            candidates.extend(_alias_values(row.get("excel_inventory_aliases")))
            candidates.extend(_alias_values(provider_sources.get(provider_name)))
            candidates.append(row.get("logical_name"))
        else:
            candidates.extend(_alias_values(provider_sources.get(provider_name)))
            candidates.append(row.get("logical_name"))

        return _ordered_unique_aliases(candidates)

    def primary_key_for_key(self, table_key: str) -> str | None:
        """Return the primary catalog key for a primary or legacy compatibility key."""
        if table_key not in self.tables:
            return None
        current = str(table_key)
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            row = self.tables.get(current)
            if not isinstance(row, Mapping):
                break
            if row.get("legacy_compatibility_alias") is not True:
                return current
            target = row.get("compatibility_alias_for")
            if target in (None, ""):
                return current
            target_key = str(target)
            if target_key not in self.tables:
                return current
            current = target_key
        raise ValueError(f"Cyclic table compatibility alias chain detected for {table_key!r}")

    def compatibility_keys_for_key(self, table_key: str) -> tuple[str, ...]:
        """Return deterministic primary/legacy keys belonging to one catalog table family."""
        primary = self.primary_key_for_key(table_key)
        if primary is None:
            return tuple()
        keys = [primary]
        for candidate in self.tables:
            if candidate == primary:
                continue
            if self.primary_key_for_key(str(candidate)) == primary:
                keys.append(str(candidate))
        return tuple(keys)

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
        for table_key in self.tables:
            for alias in self.aliases_for_key(table_key, provider=provider):
                if normalize_table_name(alias) == normalized:
                    return self.primary_key_for_key(str(table_key)) or str(table_key)
        return None

    def diagnostic_for_unknown_alias(self, actual_table_name: str) -> ProviderDiagnostic:
        return ProviderDiagnostic(
            severity=DiagnosticSeverity.WARNING,
            code=DiagnosticCode.ALIAS_NOT_FOUND,
            message=f"No canonical table_key found for alias: {actual_table_name}",
            details={"actual_table_name": actual_table_name},
        )


def _alias_values(value: Any) -> tuple[Any, ...]:
    if value in (None, ""):
        return tuple()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _ordered_unique_aliases(values: list[Any]) -> tuple[str, ...]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, ""):
            continue
        alias = str(value).strip()
        if not alias:
            continue
        normalized = normalize_table_name(alias)
        if normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(alias)
    return tuple(aliases)


def normalize_table_name(name: str) -> str:
    """Normalize safe ETABS table-name drift without fuzzy matching."""
    return re.sub(r"\s+", " ", str(name).strip()).casefold()


__all__ = ["TableRegistry", "normalize_table_name"]
