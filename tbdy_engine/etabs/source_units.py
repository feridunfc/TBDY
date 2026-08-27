"""Import-safe factual CSI force/length unit decoding.

This module is deliberately smaller than the regulatory unit system.  It only
turns explicit CSI eForce/eLength identities into neutral source-unit tokens
and performs the few exact conversions required at ETABS factual-acquisition
boundaries.  It never inspects magnitudes and never mutates ETABS state.
"""
from __future__ import annotations

from enum import StrEnum
from decimal import Decimal, InvalidOperation
from typing import Any


class EtabsSourceUnitError(ValueError):
    """Raised when a CSI source-unit identity is absent or outside reviewed scope."""


class EtabsForceUnit(StrEnum):
    N = "N"
    KN = "kN"


class EtabsLengthUnit(StrEnum):
    MM = "mm"
    M = "m"


# Reviewed CSI enum identities already used by the accepted P7 factual path.
CSI_EFORCE_N = 3
CSI_EFORCE_KN = 4
CSI_ELENGTH_MM = 4
CSI_ELENGTH_M = 6


def _enum_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    candidate = getattr(value, "value", None)
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return candidate
    try:
        return int(value)
    except Exception:
        return None


def _enum_name(value: Any) -> str | None:
    candidate = getattr(value, "name", None)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip().split(".")[-1]
    if isinstance(value, str) and value.strip():
        return value.strip().split(".")[-1]
    return None


def decode_csi_force_unit(value: Any) -> EtabsForceUnit:
    numeric = _enum_value(value)
    name = _enum_name(value)
    if numeric == CSI_EFORCE_N or name == "N":
        return EtabsForceUnit.N
    if numeric == CSI_EFORCE_KN or name == "kN":
        return EtabsForceUnit.KN
    raise EtabsSourceUnitError("CSI eForce source identity is unavailable or outside reviewed scope")


def decode_csi_length_unit(value: Any) -> EtabsLengthUnit:
    numeric = _enum_value(value)
    name = _enum_name(value)
    if numeric == CSI_ELENGTH_MM or name == "mm":
        return EtabsLengthUnit.MM
    if numeric == CSI_ELENGTH_M or name == "m":
        return EtabsLengthUnit.M
    raise EtabsSourceUnitError("CSI eLength source identity is unavailable or outside reviewed scope")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise EtabsSourceUnitError("source value must be a finite decimal scalar")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EtabsSourceUnitError("source value must be a finite decimal scalar") from exc
    if not result.is_finite():
        raise EtabsSourceUnitError("source value must be finite")
    return result


def convert_force(value: Any, *, source: EtabsForceUnit, target: EtabsForceUnit) -> Decimal:
    """Exact bounded N<->kN conversion from an explicit factual source unit."""
    source = EtabsForceUnit(source)
    target = EtabsForceUnit(target)
    scalar = _decimal(value)
    if source is target:
        return scalar
    if source is EtabsForceUnit.N and target is EtabsForceUnit.KN:
        return scalar / Decimal("1000")
    if source is EtabsForceUnit.KN and target is EtabsForceUnit.N:
        return scalar * Decimal("1000")
    raise EtabsSourceUnitError(f"unsupported reviewed force conversion {source.value}->{target.value}")


def convert_length(value: Any, *, source: EtabsLengthUnit, target: EtabsLengthUnit) -> Decimal:
    """Exact bounded mm<->m conversion from an explicit factual source unit."""
    source = EtabsLengthUnit(source)
    target = EtabsLengthUnit(target)
    scalar = _decimal(value)
    if source is target:
        return scalar
    if source is EtabsLengthUnit.MM and target is EtabsLengthUnit.M:
        return scalar / Decimal("1000")
    if source is EtabsLengthUnit.M and target is EtabsLengthUnit.MM:
        return scalar * Decimal("1000")
    raise EtabsSourceUnitError(f"unsupported reviewed length conversion {source.value}->{target.value}")


__all__ = [
    "CSI_EFORCE_KN", "CSI_EFORCE_N", "CSI_ELENGTH_M", "CSI_ELENGTH_MM",
    "EtabsForceUnit", "EtabsLengthUnit", "EtabsSourceUnitError",
    "convert_force", "convert_length", "decode_csi_force_unit", "decode_csi_length_unit",
]
