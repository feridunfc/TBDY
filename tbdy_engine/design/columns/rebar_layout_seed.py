"""Resolve factual ETABS section rebar intent into design-layout seed inputs.

This is a design-input promotion boundary, not reinforcement authority. A model's
column section can supply clear cover and named tie/longitudinal bar sizes for
candidate-layout geometry, while longitudinal reinforcement is still selected
independently from the full factual project bar catalog.

Using the seed never means that ETABS design intent is USER_PROVIDED_REBAR,
ENGINE_SELECTED_REBAR, final detailing or as-built reinforcement.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tbdy_engine.design.columns.rebar_catalog import RebarCatalog, RebarCatalogEntry


_ALLOWED_INTENT_AUTHORITIES = frozenset({"DESIGN_INTENT_ONLY", "SECTION_REBAR_CHECK_INPUT"})


class ColumnRebarLayoutSeedError(ValueError):
    """Raised when factual section intent cannot be bound to the factual bar catalog."""


@dataclass(frozen=True, slots=True)
class ColumnRebarLayoutSeed:
    section_name: str
    clear_cover_mm: float
    tie_diameter_mm: float
    tie_catalog_name: str
    intent_longitudinal_diameter_mm: float
    intent_longitudinal_catalog_name: str
    intent_authority: str
    source_refs: tuple[str, ...]
    authority: str = "ETABS_SECTION_REBAR_INTENT_LAYOUT_SEED"
    final_or_provided_rebar_authority: bool = False


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnRebarLayoutSeedError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnRebarLayoutSeedError(f"{label} must be finite and > 0")
    return result


def _entry_by_name(catalog: RebarCatalog, name: str, *, role: str) -> RebarCatalogEntry:
    matches = tuple(item for item in catalog.entries if item.name == name)
    if len(matches) != 1:
        raise ColumnRebarLayoutSeedError(
            f"{role} bar-size name {name!r} must resolve exactly once in factual project catalog; got {len(matches)}"
        )
    return matches[0]


def resolve_column_rebar_layout_seed(
    *,
    section_name: str,
    clear_cover_mm: float,
    tie_size_name: str,
    longitudinal_size_name: str,
    intent_authority: str,
    rebar_catalog: RebarCatalog,
    source_ref: str,
) -> ColumnRebarLayoutSeed:
    """Promote factual section intent to layout geometry only.

    The complete factual project catalog remains the longitudinal candidate
    source. The section's current longitudinal size is retained only as a model
    intent reference/comparator; it does not constrain or preselect the engine
    candidate family.
    """
    section = _text(section_name, "section_name")
    cover = _positive(clear_cover_mm, "clear_cover_mm")
    tie_name = _text(tie_size_name, "tie_size_name")
    long_name = _text(longitudinal_size_name, "longitudinal_size_name")
    authority = _text(intent_authority, "intent_authority")
    ref = _text(source_ref, "source_ref")

    if authority not in _ALLOWED_INTENT_AUTHORITIES:
        raise ColumnRebarLayoutSeedError(
            f"unsupported ETABS rebar intent authority for layout seed: {authority}"
        )
    if rebar_catalog.status != "PROVEN_FACTUAL_REBAR_CATALOG":
        raise ColumnRebarLayoutSeedError(
            f"layout seed requires PROVEN_FACTUAL_REBAR_CATALOG; got {rebar_catalog.status}"
        )

    tie = _entry_by_name(rebar_catalog, tie_name, role="tie")
    longitudinal = _entry_by_name(rebar_catalog, long_name, role="longitudinal intent")
    return ColumnRebarLayoutSeed(
        section_name=section,
        clear_cover_mm=cover,
        tie_diameter_mm=tie.diameter_mm,
        tie_catalog_name=tie.name,
        intent_longitudinal_diameter_mm=longitudinal.diameter_mm,
        intent_longitudinal_catalog_name=longitudinal.name,
        intent_authority=authority,
        source_refs=(ref, tie.source_identity, longitudinal.source_identity),
    )


__all__ = [
    "ColumnRebarLayoutSeed",
    "ColumnRebarLayoutSeedError",
    "resolve_column_rebar_layout_seed",
]
