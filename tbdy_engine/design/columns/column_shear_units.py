"""Explicit source-unit conversion boundary for VS6-P7 column shear.

ETABS factual values reach this module only together with the actual source Unit
provenance. No magnitude inference and no ETABS unit mutation is permitted.

P7 working convention:
- force: kN
- moment: kN*m
- geometric/deformation lengths: mm
- stress: MPa
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tbdy_engine.regulatory.units import (
    Unit,
    UNIT_KN,
    UNIT_MM,
    conversion_factor,
)


class ColumnShearUnitBoundaryError(ValueError):
    """Raised when a source value cannot be explicitly converted."""


@dataclass(frozen=True, slots=True)
class SourceBoundScalar:
    value: float
    unit: Unit
    source_ref: str

    def __post_init__(self) -> None:
        value = float(self.value)
        if not math.isfinite(value):
            raise ColumnShearUnitBoundaryError("source value must be finite")
        object.__setattr__(self, "value", value)
        if not isinstance(self.unit, Unit):
            raise TypeError("unit must be Unit")
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ColumnShearUnitBoundaryError("source_ref must be nonblank")


def force_to_kn(source: SourceBoundScalar) -> float:
    """Convert explicit factual force units to the P7 working force unit kN."""
    if not isinstance(source, SourceBoundScalar):
        raise TypeError("source must be SourceBoundScalar")
    try:
        factor = conversion_factor(source.unit, UNIT_KN)
    except Exception as exc:
        raise ColumnShearUnitBoundaryError(
            f"no reviewed force conversion {source.unit.identifier} -> kN"
        ) from exc
    return source.value * float(factor)


def length_to_mm(source: SourceBoundScalar) -> float:
    if not isinstance(source, SourceBoundScalar):
        raise TypeError("source must be SourceBoundScalar")
    try:
        factor = conversion_factor(source.unit, UNIT_MM)
    except Exception as exc:
        raise ColumnShearUnitBoundaryError(
            f"no reviewed length conversion {source.unit.identifier} -> mm"
        ) from exc
    return source.value * float(factor)


__all__ = [
    "ColumnShearUnitBoundaryError",
    "SourceBoundScalar",
    "force_to_kn",
    "length_to_mm",
]
