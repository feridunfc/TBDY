"""Strict rectangular-column longitudinal rebar candidate generation for VS6.

This module retains the legacy VS6 regulatory-filtered population for backward
compatibility and also exposes a regulation-neutral rectangular perimeter
geometry kernel for FND-COL-1.  It does not read ETABS, select final
reinforcement, or invent cover, aggregate size, tie diameter, or bar
availability.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


class ColumnRebarLayoutError(ValueError):
    """Raised when a reviewed rebar-layout input is incomplete or impossible."""


# LEGACY COMPATIBILITY CONSTANTS.
# FND-COL-1 canonical regulatory authority lives in
# tbdy_engine.regulatory.column_longitudinal_rebar.  These values remain only
# so existing VS6 callers keep their frozen behavior until P8A-B integration.
TBDY_COLUMN_RHO_MIN = 0.01
TBDY_COLUMN_RHO_MAX = 0.04
TBDY_COLUMN_MIN_BAR_DIAMETER_MM = 14.0


def _positive_finite(value: float, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnRebarLayoutError(f"{label} must be finite and > 0") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnRebarLayoutError(f"{label} must be finite and > 0")
    return result


@dataclass(frozen=True, slots=True)
class ColumnRebarGeometryInputs:
    """Factual/project placement geometry only; contains no regulatory limit."""

    width_mm: float
    depth_mm: float
    clear_cover_mm: float
    tie_diameter_mm: float

    def __post_init__(self) -> None:
        for name in ("width_mm", "depth_mm", "clear_cover_mm", "tie_diameter_mm"):
            object.__setattr__(self, name, _positive_finite(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class ColumnRebarLayoutInputs:
    """Legacy VS6 filtered-layout inputs; regulatory fields are compatibility-only."""

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
            object.__setattr__(self, name, _positive_finite(getattr(self, name), name))

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
class ColumnRebarGeometryCandidate:
    """Pure equal-diameter rectangular-perimeter geometry candidate."""

    candidate_id: str
    bar_diameter_mm: float
    n_bars_dir2: int
    n_bars_dir3: int
    bars: tuple[ColumnBarPoint, ...]
    as_total_mm2: float
    rho: float
    min_clear_spacing_mm: float
    authority: str = "CANDIDATE_GEOMETRY_ONLY"

    @property
    def bar_count(self) -> int:
        return len(self.bars)

    @property
    def rho_pct(self) -> float:
        return self.rho * 100.0


@dataclass(frozen=True, slots=True)
class ColumnRebarGeometryPopulation:
    inputs: ColumnRebarGeometryInputs
    candidates: tuple[ColumnRebarGeometryCandidate, ...]
    status: str
    authority: str = "CANDIDATE_GEOMETRY_ONLY"


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
    diameter = _positive_finite(diameter_mm, "bar diameter")
    return math.pi * diameter * diameter / 4.0


def ts500_min_clear_spacing_mm(*, bar_diameter_mm: float, aggregate_max_mm: float) -> float:
    """Legacy pure formula retained for approved FND-COL-1 binding.

    Regulatory ownership is established by the F0.9 source/review/binding
    chain in ``tbdy_engine.regulatory.sources.fnd_col_1_longitudinal``.
    """
    diameter = _positive_finite(bar_diameter_mm, "bar_diameter_mm")
    aggregate = _positive_finite(aggregate_max_mm, "aggregate_max_mm")
    return max(1.5 * diameter, 4.0 * aggregate / 3.0, 40.0)


def _linspace(start: float, stop: float, count: int) -> tuple[float, ...]:
    if count < 2:
        raise ColumnRebarLayoutError("face bar count must be >= 2")
    step = (stop - start) / float(count - 1)
    return tuple(start + step * index for index in range(count))


def _max_face_bar_count(center_span_mm: float, required_center_spacing_mm: float) -> int:
    if center_span_mm < required_center_spacing_mm:
        return 0
    return int(math.floor(center_span_mm / required_center_spacing_mm + 1e-12)) + 1


def build_rectangular_column_rebar_geometry_candidate(
    inputs: ColumnRebarGeometryInputs,
    *,
    diameter_mm: float,
    n_bars_dir2: int,
    n_bars_dir3: int,
) -> ColumnRebarGeometryCandidate:
    """Build one geometry candidate without applying any regulatory eligibility."""

    if not isinstance(inputs, ColumnRebarGeometryInputs):
        raise TypeError("inputs must be ColumnRebarGeometryInputs")
    diameter = _positive_finite(diameter_mm, "diameter_mm")
    if isinstance(n_bars_dir2, bool) or not isinstance(n_bars_dir2, int) or n_bars_dir2 < 2:
        raise ColumnRebarLayoutError("n_bars_dir2 must be an integer >= 2")
    if isinstance(n_bars_dir3, bool) or not isinstance(n_bars_dir3, int) or n_bars_dir3 < 2:
        raise ColumnRebarLayoutError("n_bars_dir3 must be an integer >= 2")

    area_one = bar_area_mm2(diameter)
    offset = inputs.clear_cover_mm + inputs.tie_diameter_mm + diameter / 2.0
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
        ColumnBarPoint(index=index + 1, x2_mm=x2, x3_mm=x3, diameter_mm=diameter, area_mm2=area_one)
        for index, (x2, x3) in enumerate(raw_points)
    )
    as_total = expected_count * area_one
    gross_area = inputs.width_mm * inputs.depth_mm
    rho = as_total / gross_area
    spacing2 = (2.0 * half2) / float(n_bars_dir2 - 1) - diameter
    spacing3 = (2.0 * half3) / float(n_bars_dir3 - 1) - diameter
    min_clear = min(spacing2, spacing3)
    if min_clear < -1e-9:
        raise ColumnRebarLayoutError("candidate geometry causes overlapping longitudinal bars")

    return ColumnRebarGeometryCandidate(
        candidate_id=(
            f"RECT-PERIMETER-{expected_count}D{diameter:g}-"
            f"N2{n_bars_dir2}-N3{n_bars_dir3}"
        ),
        bar_diameter_mm=diameter,
        n_bars_dir2=n_bars_dir2,
        n_bars_dir3=n_bars_dir3,
        bars=bars,
        as_total_mm2=as_total,
        rho=rho,
        min_clear_spacing_mm=min_clear,
    )


def generate_rectangular_column_rebar_geometry_candidates(
    inputs: ColumnRebarGeometryInputs,
    *,
    bar_diameters_mm: Iterable[float],
) -> ColumnRebarGeometryPopulation:
    """Generate deterministic geometry candidates from explicit factual diameters."""

    if not isinstance(inputs, ColumnRebarGeometryInputs):
        raise TypeError("inputs must be ColumnRebarGeometryInputs")
    diameters = tuple(_positive_finite(value, "bar_diameters_mm") for value in bar_diameters_mm)
    if not diameters:
        raise ColumnRebarLayoutError("bar_diameters_mm must be nonempty")
    if len(set(diameters)) != len(diameters):
        raise ColumnRebarLayoutError("bar_diameters_mm must not contain duplicates")

    candidates: list[ColumnRebarGeometryCandidate] = []
    for diameter in sorted(diameters):
        center_span2 = inputs.width_mm - 2.0 * (
            inputs.clear_cover_mm + inputs.tie_diameter_mm + diameter / 2.0
        )
        center_span3 = inputs.depth_mm - 2.0 * (
            inputs.clear_cover_mm + inputs.tie_diameter_mm + diameter / 2.0
        )
        # Geometry-only bound: bar centers may not be closer than one diameter.
        max_n2 = _max_face_bar_count(center_span2, diameter)
        max_n3 = _max_face_bar_count(center_span3, diameter)
        if max_n2 < 2 or max_n3 < 2:
            continue
        for n2 in range(2, max_n2 + 1):
            for n3 in range(2, max_n3 + 1):
                candidates.append(
                    build_rectangular_column_rebar_geometry_candidate(
                        inputs,
                        diameter_mm=diameter,
                        n_bars_dir2=n2,
                        n_bars_dir3=n3,
                    )
                )

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
    return ColumnRebarGeometryPopulation(
        inputs=inputs,
        candidates=tuple(candidates),
        status="PROVEN" if candidates else "NO_GEOMETRIC_CANDIDATE",
    )


def _build_candidate(
    inputs: ColumnRebarLayoutInputs,
    *,
    diameter_mm: float,
    n_bars_dir2: int,
    n_bars_dir3: int,
) -> ColumnRebarCandidate:
    geometry = build_rectangular_column_rebar_geometry_candidate(
        ColumnRebarGeometryInputs(
            width_mm=inputs.width_mm,
            depth_mm=inputs.depth_mm,
            clear_cover_mm=inputs.clear_cover_mm,
            tie_diameter_mm=inputs.tie_diameter_mm,
        ),
        diameter_mm=diameter_mm,
        n_bars_dir2=n_bars_dir2,
        n_bars_dir3=n_bars_dir3,
    )
    required_clear = ts500_min_clear_spacing_mm(
        bar_diameter_mm=diameter_mm,
        aggregate_max_mm=inputs.aggregate_max_mm,
    )
    if geometry.min_clear_spacing_mm + 1e-9 < required_clear:
        raise ColumnRebarLayoutError("internal candidate construction violated reviewed clear-spacing bound")

    return ColumnRebarCandidate(
        candidate_id=geometry.candidate_id,
        bar_diameter_mm=geometry.bar_diameter_mm,
        n_bars_dir2=geometry.n_bars_dir2,
        n_bars_dir3=geometry.n_bars_dir3,
        bars=geometry.bars,
        as_total_mm2=geometry.as_total_mm2,
        rho=geometry.rho,
        min_clear_spacing_mm=geometry.min_clear_spacing_mm,
        required_min_clear_spacing_mm=required_clear,
    )


def generate_rectangular_column_rebar_candidates(
    inputs: ColumnRebarLayoutInputs,
) -> ColumnRebarCandidatePopulation:
    """Generate the frozen legacy VS6 regulatory-filtered candidate population."""

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
    "ColumnRebarGeometryCandidate",
    "ColumnRebarGeometryInputs",
    "ColumnRebarGeometryPopulation",
    "ColumnRebarLayoutError",
    "ColumnRebarLayoutInputs",
    "TBDY_COLUMN_MIN_BAR_DIAMETER_MM",
    "TBDY_COLUMN_RHO_MAX",
    "TBDY_COLUMN_RHO_MIN",
    "bar_area_mm2",
    "build_rectangular_column_rebar_geometry_candidate",
    "generate_rectangular_column_rebar_candidates",
    "generate_rectangular_column_rebar_geometry_candidates",
    "ts500_min_clear_spacing_mm",
]
