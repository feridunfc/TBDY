"""Explicit unit contracts for the frozen F0 regulatory type system."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from .contracts import PhysicalDimension


def _require_nonblank(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonblank string")
    if value != value.strip():
        raise ValueError(f"{label} must not contain leading or trailing whitespace")
    return value


@dataclass(frozen=True, slots=True)
class Unit:
    """Immutable reviewed unit identity; it does not infer units from data."""

    identifier: str
    physical_dimension: PhysicalDimension

    def __post_init__(self) -> None:
        _require_nonblank(self.identifier, "unit identifier")
        if not isinstance(self.physical_dimension, PhysicalDimension):
            raise TypeError("physical_dimension must be PhysicalDimension")


class UnitConversionError(ValueError):
    """Raised when no explicit reviewed unit conversion exists."""


UNIT_DIMENSIONLESS = Unit("dimensionless", PhysicalDimension.DIMENSIONLESS)
UNIT_BOOLEAN_STATE = Unit("boolean_state", PhysicalDimension.BOOLEAN_STATE)
UNIT_ENUM_STATE = Unit("enum_state", PhysicalDimension.ENUM_STATE)
UNIT_N = Unit("N", PhysicalDimension.FORCE)
UNIT_KN = Unit("kN", PhysicalDimension.FORCE)
UNIT_MM = Unit("mm", PhysicalDimension.LENGTH)
UNIT_M = Unit("m", PhysicalDimension.LENGTH)
UNIT_N_MM = Unit("N*mm", PhysicalDimension.MOMENT)
UNIT_KN_M = Unit("kN*m", PhysicalDimension.MOMENT)
UNIT_MPA = Unit("MPa", PhysicalDimension.STRESS)


# target_value = source_value * factor. Only explicit reviewed pairs exist here.
_EXPLICIT_CONVERSIONS: Mapping[tuple[Unit, Unit], Fraction] = MappingProxyType(
    {
        (UNIT_N, UNIT_KN): Fraction(1, 1000),
        (UNIT_KN, UNIT_N): Fraction(1000, 1),
        (UNIT_MM, UNIT_M): Fraction(1, 1000),
        (UNIT_M, UNIT_MM): Fraction(1000, 1),
        (UNIT_N_MM, UNIT_KN_M): Fraction(1, 1_000_000),
        (UNIT_KN_M, UNIT_N_MM): Fraction(1_000_000, 1),
    }
)


def conversion_factor(source: Unit, target: Unit) -> Fraction:
    """Return an explicit exact factor; never infer compatibility or a unit."""

    if not isinstance(source, Unit) or not isinstance(target, Unit):
        raise TypeError("source and target must be Unit")
    if source.physical_dimension is not target.physical_dimension:
        raise UnitConversionError(
            f"incompatible physical dimensions: {source.physical_dimension} -> {target.physical_dimension}"
        )
    if source == target:
        return Fraction(1, 1)
    try:
        return _EXPLICIT_CONVERSIONS[(source, target)]
    except KeyError as exc:
        raise UnitConversionError(
            f"no explicit reviewed conversion: {source.identifier} -> {target.identifier}"
        ) from exc


def units_convertible(source: Unit, target: Unit) -> bool:
    try:
        conversion_factor(source, target)
    except (TypeError, UnitConversionError):
        return False
    return True


__all__ = [
    "Unit",
    "UnitConversionError",
    "UNIT_DIMENSIONLESS",
    "UNIT_BOOLEAN_STATE",
    "UNIT_ENUM_STATE",
    "UNIT_N",
    "UNIT_KN",
    "UNIT_MM",
    "UNIT_M",
    "UNIT_N_MM",
    "UNIT_KN_M",
    "UNIT_MPA",
    "conversion_factor",
    "units_convertible",
]
