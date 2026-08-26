"""Exact selected-bar effective-depth resolution for VS6-P7 column shear.

This module owns geometry resolution only. It contains no TBDY/TS500
upper-bound formula and emits no compliance verdict; those belong exclusively
to ``tbdy_engine.regulatory.column_shear_p7`` through the canonical F0 engine.

Working geometry unit: mm.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.design.columns.column_shear_demand import M2, M3, associated_moment_axis
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint


class ColumnShearUpperBoundError(ValueError):
    """Raised when exact P7 effective-depth inputs are unavailable or malformed."""


EFFECTIVE_DEPTH_PROVEN = "PROVEN_EXACT_TS500_EFFECTIVE_DEPTH"
EFFECTIVE_DEPTH_BLOCKED = "BLOCKED_EFFECTIVE_DEPTH_BASIS"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearUpperBoundError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearUpperBoundError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnShearUpperBoundError(f"{label} must be finite and > 0")
    return result


@dataclass(frozen=True, slots=True)
class ColumnEffectiveDepthResolution:
    component_id: str
    direction: str
    moment_axis: str
    moment_sign: int
    effective_depth_d_mm: float | None
    web_width_bw_mm: float | None
    tension_bar_coordinate_mm: float | None
    status: str
    source_refs: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        return (
            self.status == EFFECTIVE_DEPTH_PROVEN
            and self.effective_depth_d_mm is not None
            and self.web_width_bw_mm is not None
        )


def resolve_exact_rectangular_column_effective_depth(
    *,
    component_id: str,
    direction: str,
    moment_sign: int,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    source_refs: Sequence[str],
) -> ColumnEffectiveDepthResolution:
    """Resolve TS500 d from selected-bar coordinates; never use d=0.9h."""
    component = _text(component_id, "component_id")
    axis = associated_moment_axis(direction)
    if moment_sign not in {-1, 1}:
        raise ColumnShearUpperBoundError("moment_sign must be -1 or +1")
    width = _positive(width_mm, "width_mm")
    depth = _positive(depth_mm, "depth_mm")
    refs = tuple(_text(ref, "source_ref") for ref in source_refs)
    if not refs or len(refs) != len(set(refs)):
        raise ColumnShearUpperBoundError("source_refs must be nonempty and unique")
    items = tuple(bars)
    if not items:
        return ColumnEffectiveDepthResolution(
            component_id=component,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            effective_depth_d_mm=None,
            web_width_bw_mm=None,
            tension_bar_coordinate_mm=None,
            status=EFFECTIVE_DEPTH_BLOCKED,
            source_refs=refs,
        )

    if axis == M3:
        coords = tuple(float(bar.x2_mm) for bar in items)
        tension = max(coords) if moment_sign > 0 else min(coords)
        compression_face = -width / 2.0 if moment_sign > 0 else width / 2.0
        d = abs(tension - compression_face)
        bw = depth
    elif axis == M2:
        coords = tuple(float(bar.x3_mm) for bar in items)
        tension = min(coords) if moment_sign > 0 else max(coords)
        compression_face = depth / 2.0 if moment_sign > 0 else -depth / 2.0
        d = abs(tension - compression_face)
        bw = width
    else:  # pragma: no cover
        raise ColumnShearUpperBoundError("unsupported associated moment axis")

    member_depth = width if axis == M3 else depth
    if not math.isfinite(d) or d <= 0.0 or d >= member_depth + 1e-9:
        return ColumnEffectiveDepthResolution(
            component_id=component,
            direction=direction,
            moment_axis=axis,
            moment_sign=moment_sign,
            effective_depth_d_mm=None,
            web_width_bw_mm=None,
            tension_bar_coordinate_mm=tension,
            status=EFFECTIVE_DEPTH_BLOCKED,
            source_refs=refs,
        )

    return ColumnEffectiveDepthResolution(
        component_id=component,
        direction=direction,
        moment_axis=axis,
        moment_sign=moment_sign,
        effective_depth_d_mm=d,
        web_width_bw_mm=bw,
        tension_bar_coordinate_mm=tension,
        status=EFFECTIVE_DEPTH_PROVEN,
        source_refs=refs,
    )


__all__ = [
    "EFFECTIVE_DEPTH_PROVEN",
    "EFFECTIVE_DEPTH_BLOCKED",
    "ColumnEffectiveDepthResolution",
    "ColumnShearUpperBoundError",
    "resolve_exact_rectangular_column_effective_depth",
]
