"""Source-bound VS6-P7 column-end capacity adapter and local-axis contract.

This module contains no TBDY shear-demand formula and no compliance verdict.
The only P7 regulatory demand authority lives in
``tbdy_engine.regulatory.column_shear_p7`` through the canonical F0 engine.

P7 working convention is kN, kN*m, mm and MPa. The pre-existing VS6-P5
section-capacity kernel internally uses N/N*mm; conversion is isolated to
``resolve_exact_column_end_moment_capacity``.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint
from tbdy_engine.design.columns.section_capacity import (
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    radial_moment_capacity,
)


class ColumnShearDemandError(ValueError):
    """Raised when a P7 capacity/local-axis input is malformed or loses authority."""


V2 = "V2"
V3 = "V3"
M2 = "M2"
M3 = "M3"
_ASSOCIATED_MOMENT_AXIS = {V2: M3, V3: M2}

CAPACITY_PROVEN = "PROVEN_EXACT_COLUMN_END_CAPACITY"
CAPACITY_BLOCKED = "BLOCKED_COLUMN_END_CAPACITY"
SECTION_CAPACITY_UNIT_ADAPTER_REF = "VS6_P5_CAPACITY_UNIT_ADAPTER:kN-kNm<->N-Nmm"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearDemandError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearDemandError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnShearDemandError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearDemandError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ColumnShearDemandError(f"{label} must be finite and >= 0")
    return result


def associated_moment_axis(direction: str) -> str:
    canonical = _text(direction, "direction")
    try:
        return _ASSOCIATED_MOMENT_AXIS[canonical]
    except KeyError as exc:
        raise ColumnShearDemandError("direction must be V2 or V3") from exc


@dataclass(frozen=True, slots=True)
class ColumnEndMomentCapacityBasis:
    component_id: str
    end_tag: str
    direction: str
    moment_axis: str
    moment_sign: int
    nd_compression_kn: float
    capacity_knm: float | None
    status: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        end = _text(self.end_tag, "end_tag")
        if end not in {"BOTTOM", "TOP"}:
            raise ColumnShearDemandError("end_tag must be BOTTOM or TOP")
        direction = _text(self.direction, "direction")
        expected_axis = associated_moment_axis(direction)
        if self.moment_axis != expected_axis:
            raise ColumnShearDemandError(
                f"{direction} must preserve associated bending axis {expected_axis}"
            )
        if self.moment_sign not in {-1, 1}:
            raise ColumnShearDemandError("moment_sign must be -1 or +1")
        _nonnegative(self.nd_compression_kn, "nd_compression_kn")
        if self.capacity_knm is not None:
            _positive(self.capacity_knm, "capacity_knm")
        _text(self.status, "status")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnShearDemandError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)

    @property
    def resolved(self) -> bool:
        return self.status == CAPACITY_PROVEN and self.capacity_knm is not None


def resolve_exact_column_end_moment_capacity(
    *,
    component_id: str,
    end_tag: str,
    direction: str,
    moment_sign: int,
    nd_compression_kn: float,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    material: ColumnSectionMaterial,
    source_refs: Sequence[str],
    angle_count: int = 72,
) -> ColumnEndMomentCapacityBasis:
    """Resolve exact #145 capacity and expose it to P7 as kN*m."""
    component = _text(component_id, "component_id")
    end = _text(end_tag, "end_tag")
    direction = _text(direction, "direction")
    axis = associated_moment_axis(direction)
    if moment_sign not in {-1, 1}:
        raise ColumnShearDemandError("moment_sign must be -1 or +1")
    nd_kn = _nonnegative(nd_compression_kn, "nd_compression_kn")
    width = _positive(width_mm, "width_mm")
    depth = _positive(depth_mm, "depth_mm")
    refs = tuple(_text(ref, "source_ref") for ref in source_refs)
    if not refs:
        raise ColumnShearDemandError("source_refs must be nonempty")
    if not bars:
        raise ColumnShearDemandError("bars must be nonempty")

    envelope = build_interaction_envelope_at_axial_force(
        width_mm=width,
        depth_mm=depth,
        bars=tuple(bars),
        material=material,
        target_n_compression_n=nd_kn * 1000.0,
        angle_count=angle_count,
    )
    resolved_refs = tuple(dict.fromkeys((*refs, SECTION_CAPACITY_UNIT_ADAPTER_REF)))
    if envelope.status != "PROVEN":
        return ColumnEndMomentCapacityBasis(
            component_id=component,
            end_tag=end,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            nd_compression_kn=nd_kn,
            capacity_knm=None,
            status=CAPACITY_BLOCKED,
            source_refs=resolved_refs,
        )

    demand_m2 = float(moment_sign) if axis == M2 else 0.0
    demand_m3 = float(moment_sign) if axis == M3 else 0.0
    radial = radial_moment_capacity(
        envelope,
        demand_m2_nmm=demand_m2,
        demand_m3_nmm=demand_m3,
    )
    if (
        radial.status != "PROVEN"
        or not math.isfinite(radial.capacity_nmm)
        or radial.capacity_nmm <= 0.0
    ):
        return ColumnEndMomentCapacityBasis(
            component_id=component,
            end_tag=end,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            nd_compression_kn=nd_kn,
            capacity_knm=None,
            status=CAPACITY_BLOCKED,
            source_refs=resolved_refs,
        )

    return ColumnEndMomentCapacityBasis(
        component_id=component,
        end_tag=end,
        direction=direction,
        moment_axis=axis,
        moment_sign=moment_sign,
        nd_compression_kn=nd_kn,
        capacity_knm=float(radial.capacity_nmm) / 1_000_000.0,
        status=CAPACITY_PROVEN,
        source_refs=resolved_refs,
    )


__all__ = [
    "V2",
    "V3",
    "M2",
    "M3",
    "CAPACITY_PROVEN",
    "CAPACITY_BLOCKED",
    "SECTION_CAPACITY_UNIT_ADAPTER_REF",
    "ColumnEndMomentCapacityBasis",
    "ColumnShearDemandError",
    "associated_moment_axis",
    "resolve_exact_column_end_moment_capacity",
]
