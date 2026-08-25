"""Strict rectangular-column longitudinal rebar candidate generation for VS6.

This module is a bounded design-candidate kernel.  It does not read ETABS,
does not select final reinforcement, and does not emit compliance verdicts.
All project-specific placement inputs are explicit reviewed inputs; no cover,
aggregate size, tie diameter, or usable bar set is invented here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


class ColumnRebarLayoutError(ValueError):
    """Raised when a reviewed rebar-layout input is incomplete or impossible."""


TBDY_COLUMN_RHO_MIN = 0.01
TBDY_COLUMN_RHO_MAX = 0.04
TBDY_COLUMN_MIN_BAR_DIAMETER_MM = 14.0


@dataclass(frozen=True, slots=True)
class ColumnRebarLayoutInputs:
    width_mm: float
    depth_mm: float
    clear_cover_mm: float
    tie_diameter_mm: float
    aggregate_max_mm: float
    allowed_bar_diameters_mm: tuple[float, ...]
    rho_min: float = TBDY_COLUMN_RHO_MIN
    rho_max: float = TBDY_COLUMN_RHO_MAX

    def __post_init__(self) -> None:
        for name in (
            "width_mm",
            "depth_mm",
            "clear_cover_mm",
            "tie_diameter_mm",
            "aggregate_max_mm",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ColumnRebarLayoutError(f"{name} must be finite and > 0")
            object.__setattr__(self, name, value)

        diameters = tuple(float(value) for value in self.allowed_bar_diameters_mm)
        if not diameters:
            raise ColumnRebarLayoutError("allowed_bar_diameters_mm must be nonempty")
        if any(not math.isfinite(value) or value < TBDY_COLUMN_MIN_BAR_DIAMETER_MM for value in diameters):
            raise ColumnRebarLayoutError(
                "allowed bar diameters must be finite and >= 14 mm; ineligible bars must not be silently filtered"
            )
        if len(set(diameters)) != len(diameters):
            raise ColumnRebarLayoutError("allowed_bar_diameters_mm must not contain duplicates")
        object.__setattr__(self, "allowed_bar_diameters_mm", tuple(sorted(diameters)))

        rho_min = float(self.rho_min)
        rho_max = float(self.rho_max)
        if not (0.0 < rho_min <= rho_max <= TBDY_COLUMN_RHO_MAX):
            raise ColumnRebarLayoutError("rho range must be positive and may not exceed the TBDY 4% normal-region ceiling")
        if rho_min < TBDY_COLUMN_RHO_MIN:
            raise ColumnRebarLayoutError("VS6 candidate generation may not reduce the TBDY 1% minimum")
        object.__setattr__(self, "rho_min", rho_min)
        object.__setattr__(self, "rho_max", rho_max)


@dataclass(frozen=True, slots=True)
class ColumnBarPoint:
    index: int
    x2_mm: float
    x3_mm: float
    diameter_mm: float
    area_mm2: float


@dataclass(frozen=True, slots=True)
class ColumnRebarCandidate:
    candidate_id: str
    bar_diameter_mm: float
    n_bars_dir2: int
    n_bars_dir3: int
    bars: tuple[ColumnBarPoint, ...]
    as_total_mm2: float
    rho: float
    min_clear_spacing_mm: float
    required_min_clear_spacing_mm: float
    authority: str = "DESIGN_CANDIDATE_ONLY"

    @property
    def bar_count(self) -> int:
        return len(self.bars)

    @property
    def rho_pct(self) -> float:
        return self.rho * 100.0


@dataclass(frozen=True, slots=True)
class ColumnRebarCandidatePopulation:
    inputs: ColumnRebarLayoutInputs
    candidates: tuple[ColumnRebarCandidate, ...]
    status: str
    authority: str = "DESIGN_CANDIDATE_ONLY"


def bar_area_mm2(diameter_mm: float) -> float:
    diameter = float(diameter_mm)
    if not math.isfinite(diameter) or diameter <= 0.0:
        raise ColumnRebarLayoutError("bar diameter must be finite and > 0")
    return math.pi * diameter * diameter / 4.0


def ts500_min_clear_spacing_mm(*, bar_diameter_mm: float, aggregate_max_mm: float) -> float:
    """TS500 column longitudinal-bar clear spacing lower bound.

    The bound is max(1.5 phi, 4/3 aggregate size, 40 mm).  Aggregate size is
    therefore an explicit reviewed input rather than a default.
    """
    return max(1.5 * float(bar_diameter_mm), 4.0 * float(aggregate_max_mm) / 3.0, 40.0)


def _linspace(start: float, stop: float, count: int) -> tuple[float, ...]:
    if count < 2:
        raise ColumnRebarLayoutError("face bar count must be >= 2")
    step = (stop - start) / float(count - 1)
    return tuple(start + step * index for index in range(count))


def _max_face_bar_count(center_span_mm: float, required_center_spacing_mm: float) -> int:
    if center_span_mm < required_center_spacing_mm:
        return 0
    return int(math.floor(center_span_mm / required_center_spacing_mm + 1e-12)) + 1


def _build_candidate(
    inputs: ColumnRebarLayoutInputs,
    *,
    diameter_mm: float,
    n_bars_dir2: int,
    n_bars_dir3: int,
) -> ColumnRebarCandidate:
    area_one = bar_area_mm2(diameter_mm)
    offset = inputs.clear_cover_mm + inputs.tie_diameter_mm + diameter_mm / 2.0
    half2 = inputs.width_mm / 2.0 - offset
    half3 = inputs.depth_mm / 2.0 - offset
    if half2 <= 0.0 or half3 <= 0.0:
        raise ColumnRebarLayoutError("reviewed cover/tie/bar geometry leaves no positive bar-center rectangle")

    x2_values = _linspace(-half2, half2, n_bars_dir2)
    x3_values = _linspace(-half3, half3, n_bars_dir3)

    raw_points: list[tuple[float, float]] = []
    for x2 in x2_values:
        raw_points.append((x2, -half3))
        raw_points.append((x2, half3))
    for x3 in x3_values[1:-1]:
        raw_points.append((-half2, x3))
        raw_points.append((half2, x3))

    expected_count = 2 * n_bars_dir2 + 2 * n_bars_dir3 - 4
    if len(raw_points) != expected_count or len(set(raw_points)) != expected_count:
        raise ColumnRebarLayoutError("candidate perimeter construction is not unique/deterministic")

    bars = tuple(
        ColumnBarPoint(index=index + 1, x2_mm=x2, x3_mm=x3, diameter_mm=diameter_mm, area_mm2=area_one)
        for index, (x2, x3) in enumerate(raw_points)
    )
    as_total = expected_count * area_one
    gross_area = inputs.width_mm * inputs.depth_mm
    rho = as_total / gross_area

    spacing2 = (2.0 * half2) / float(n_bars_dir2 - 1) - diameter_mm
    spacing3 = (2.0 * half3) / float(n_bars_dir3 - 1) - diameter_mm
    min_clear = min(spacing2, spacing3)
    required_clear = ts500_min_clear_spacing_mm(
        bar_diameter_mm=diameter_mm,
        aggregate_max_mm=inputs.aggregate_max_mm,
    )
    if min_clear + 1e-9 < required_clear:
        raise ColumnRebarLayoutError("internal candidate construction violated reviewed clear-spacing bound")

    return ColumnRebarCandidate(
        candidate_id=(
            f"RECT-PERIMETER-{expected_count}D{diameter_mm:g}-"
            f"N2{n_bars_dir2}-N3{n_bars_dir3}"
        ),
        bar_diameter_mm=diameter_mm,
        n_bars_dir2=n_bars_dir2,
        n_bars_dir3=n_bars_dir3,
        bars=bars,
        as_total_mm2=as_total,
        rho=rho,
        min_clear_spacing_mm=min_clear,
        required_min_clear_spacing_mm=required_clear,
    )


def generate_rectangular_column_rebar_candidates(
    inputs: ColumnRebarLayoutInputs,
) -> ColumnRebarCandidatePopulation:
    """Generate deterministic equal-diameter, symmetric perimeter candidates.

    This is intentionally narrower than a general detailing optimizer.  It
    creates only rectangular perimeter layouts with equal-diameter bars.  Tie
    leg/crosstie adequacy is not inferred here and remains a later dependency.
    """
    candidates: list[ColumnRebarCandidate] = []

    for diameter in inputs.allowed_bar_diameters_mm:
        required_clear = ts500_min_clear_spacing_mm(
            bar_diameter_mm=diameter,
            aggregate_max_mm=inputs.aggregate_max_mm,
        )
        required_center = diameter + required_clear
        center_span2 = inputs.width_mm - 2.0 * (
            inputs.clear_cover_mm + inputs.tie_diameter_mm + diameter / 2.0
        )
        center_span3 = inputs.depth_mm - 2.0 * (
            inputs.clear_cover_mm + inputs.tie_diameter_mm + diameter / 2.0
        )
        max_n2 = _max_face_bar_count(center_span2, required_center)
        max_n3 = _max_face_bar_count(center_span3, required_center)
        if max_n2 < 2 or max_n3 < 2:
            continue

        for n2 in range(2, max_n2 + 1):
            for n3 in range(2, max_n3 + 1):
                candidate = _build_candidate(
                    inputs,
                    diameter_mm=diameter,
                    n_bars_dir2=n2,
                    n_bars_dir3=n3,
                )
                if inputs.rho_min - 1e-12 <= candidate.rho <= inputs.rho_max + 1e-12:
                    candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            round(item.as_total_mm2, 9),
            item.bar_diameter_mm,
            item.bar_count,
            item.n_bars_dir2,
            item.n_bars_dir3,
            item.candidate_id,
        )
    )
    return ColumnRebarCandidatePopulation(
        inputs=inputs,
        candidates=tuple(candidates),
        status="PROVEN" if candidates else "NO_FEASIBLE_LAYOUT",
    )


__all__ = [
    "ColumnBarPoint",
    "ColumnRebarCandidate",
    "ColumnRebarCandidatePopulation",
    "ColumnRebarLayoutError",
    "ColumnRebarLayoutInputs",
    "TBDY_COLUMN_MIN_BAR_DIAMETER_MM",
    "TBDY_COLUMN_RHO_MAX",
    "TBDY_COLUMN_RHO_MIN",
    "bar_area_mm2",
    "generate_rectangular_column_rebar_candidates",
    "ts500_min_clear_spacing_mm",
]
