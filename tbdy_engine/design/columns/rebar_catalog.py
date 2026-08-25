"""Factual reinforcing-bar catalog normalization for column design.

This module converts an explicitly identified ETABS/table bar-size source into a
canonical catalog.  It does not invent a standard bar list.  The project source
must supply the rows and the caller must identify the factual name/diameter
fields and units.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.design.columns.rebar_layout import TBDY_COLUMN_MIN_BAR_DIAMETER_MM


class RebarCatalogError(ValueError):
    """Raised when factual rebar catalog evidence is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class RebarCatalogEntry:
    name: str
    diameter_mm: float
    source_identity: str


@dataclass(frozen=True, slots=True)
class RebarCatalog:
    entries: tuple[RebarCatalogEntry, ...]
    status: str
    authority: str = "FACTUAL_PROJECT_REBAR_CATALOG"

    @property
    def diameters_mm(self) -> tuple[float, ...]:
        return tuple(item.diameter_mm for item in self.entries)

    @property
    def column_longitudinal_diameters_mm(self) -> tuple[float, ...]:
        return tuple(
            item.diameter_mm
            for item in self.entries
            if item.diameter_mm + 1e-12 >= TBDY_COLUMN_MIN_BAR_DIAMETER_MM
        )

    @property
    def excluded_below_column_minimum(self) -> tuple[RebarCatalogEntry, ...]:
        return tuple(
            item for item in self.entries if item.diameter_mm < TBDY_COLUMN_MIN_BAR_DIAMETER_MM - 1e-12
        )


def _float(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise RebarCatalogError(f"{label} must be finite numeric")
    try:
        result = float(Decimal(str(value)))
    except (InvalidOperation, ValueError) as exc:
        raise RebarCatalogError(f"{label} must be finite numeric") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise RebarCatalogError(f"{label} must be finite and > 0")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RebarCatalogError(f"{label} must be a nonblank string")
    return value.strip()


def build_rebar_catalog_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    name_field: str,
    diameter_field: str,
    diameter_unit: str,
    source_name: str,
) -> RebarCatalog:
    """Normalize factual project bar-size rows without a hard-coded bar library."""
    if diameter_unit not in {"mm", "m"}:
        raise RebarCatalogError("diameter_unit must be explicitly 'mm' or 'm'")
    factual_rows = tuple(rows)
    if not factual_rows:
        raise RebarCatalogError("rebar catalog rows must be nonempty")
    source = _text(source_name, "source_name")

    entries: list[RebarCatalogEntry] = []
    seen_names: set[str] = set()
    seen_diameters: set[float] = set()
    for index, row in enumerate(factual_rows):
        name = _text(row.get(name_field), f"row[{index}].{name_field}")
        diameter = _float(row.get(diameter_field), f"row[{index}].{diameter_field}")
        diameter_mm = diameter if diameter_unit == "mm" else diameter * 1000.0
        canonical_diameter = round(diameter_mm, 9)
        if name in seen_names:
            raise RebarCatalogError(f"duplicate rebar catalog name: {name}")
        if canonical_diameter in seen_diameters:
            raise RebarCatalogError(f"duplicate rebar catalog diameter: {diameter_mm:g} mm")
        seen_names.add(name)
        seen_diameters.add(canonical_diameter)
        entries.append(
            RebarCatalogEntry(
                name=name,
                diameter_mm=diameter_mm,
                source_identity=f"{source}|row={index}|{name_field}={name}|{diameter_field}={row.get(diameter_field)}",
            )
        )

    entries.sort(key=lambda item: (item.diameter_mm, item.name))
    return RebarCatalog(entries=tuple(entries), status="PROVEN_FACTUAL_REBAR_CATALOG")


__all__ = [
    "RebarCatalog",
    "RebarCatalogEntry",
    "RebarCatalogError",
    "build_rebar_catalog_from_rows",
]
