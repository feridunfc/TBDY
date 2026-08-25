"""TS500 strain-compatibility capacity kernel for rectangular RC columns.

Bounded VS6-P5 scope:
- rectangular concrete section,
- discrete longitudinal bars supplied by the strict layout kernel,
- biaxial neutral-axis orientation,
- TS500 Section 7.1 strain assumptions and equivalent rectangular block,
- no demand selection and no PASS/FAIL decision.

The legacy simplified PMM checker is intentionally not used here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint


class ColumnSectionCapacityError(ValueError):
    """Raised when section-capacity inputs are unsupported or incomplete."""


TS500_ES_MPA = 200_000.0
TS500_EPSILON_CU = 0.003
TS500_CONCRETE_BLOCK_FACTOR = 0.85
_TS500_K1_BY_FCK = {
    16.0: 0.85,
    18.0: 0.85,
    20.0: 0.85,
    25.0: 0.85,
    30.0: 0.82,
    35.0: 0.79,
    40.0: 0.76,
    45.0: 0.73,
    50.0: 0.70,
}


def ts500_k1_for_fck_mpa(fck_mpa: float) -> float:
    value = float(fck_mpa)
    for concrete_class, k1 in _TS500_K1_BY_FCK.items():
        if abs(value - concrete_class) <= 1e-9:
            return k1
    raise ColumnSectionCapacityError(
        f"fck={value:g} MPa is outside the source-bound TS500 k1 table implemented by this kernel"
    )


@dataclass(frozen=True, slots=True)
class ColumnSectionMaterial:
    fck_mpa: float
    fcd_mpa: float
    fyd_mpa: float
    k1: float | None = None
    es_mpa: float = TS500_ES_MPA
    epsilon_cu: float = TS500_EPSILON_CU

    def __post_init__(self) -> None:
        for name in ("fck_mpa", "fcd_mpa", "fyd_mpa", "es_mpa", "epsilon_cu"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ColumnSectionCapacityError(f"{name} must be finite and > 0")
            object.__setattr__(self, name, value)
        source_k1 = ts500_k1_for_fck_mpa(self.fck_mpa)
        if self.k1 is None:
            object.__setattr__(self, "k1", source_k1)
        else:
            provided = float(self.k1)
            if abs(provided - source_k1) > 1e-12:
                raise ColumnSectionCapacityError(
                    f"k1={provided:g} does not match source-bound TS500 value {source_k1:g} for fck={self.fck_mpa:g}"
                )
            object.__setattr__(self, "k1", provided)


@dataclass(frozen=True, slots=True)
class ColumnSectionCapacityState:
    neutral_axis_angle_deg: float
    neutral_axis_depth_c_mm: float
    block_depth_a_mm: float
    n_compression_n: float
    m2_nmm: float
    m3_nmm: float
    concrete_force_n: float
    steel_force_n: float
    concrete_area_mm2: float
    concrete_centroid_x2_mm: float
    concrete_centroid_x3_mm: float
    max_steel_compression_strain: float
    max_steel_tension_strain: float
    authority: str = "TS500_STRAIN_COMPATIBILITY_CAPACITY"


@dataclass(frozen=True, slots=True)
class ColumnInteractionEnvelope:
    target_n_compression_n: float
    states: tuple[ColumnSectionCapacityState, ...]
    status: str
    angle_step_deg: float
    authority: str = "TS500_STRAIN_COMPATIBILITY_CAPACITY"


@dataclass(frozen=True, slots=True)
class RadialMomentCapacity:
    demand_angle_deg: float
    capacity_nmm: float
    boundary_m2_nmm: float
    boundary_m3_nmm: float
    status: str


def _dot(point: tuple[float, float], nx: float, ny: float) -> float:
    return point[0] * nx + point[1] * ny


def _clip_polygon_halfplane(
    polygon: Sequence[tuple[float, float]],
    *,
    nx: float,
    ny: float,
    q_min: float,
) -> tuple[tuple[float, float], ...]:
    if not polygon:
        return ()
    result: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_value = _dot(previous, nx, ny) - q_min
    previous_inside = previous_value >= -1e-12

    for current in polygon:
        current_value = _dot(current, nx, ny) - q_min
        current_inside = current_value >= -1e-12
        if current_inside != previous_inside:
            denominator = previous_value - current_value
            if abs(denominator) <= 1e-18:
                raise ColumnSectionCapacityError("degenerate half-plane clipping intersection")
            t = previous_value / denominator
            intersection = (
                previous[0] + t * (current[0] - previous[0]),
                previous[1] + t * (current[1] - previous[1]),
            )
            result.append(intersection)
        if current_inside:
            result.append(current)
        previous = current
        previous_value = current_value
        previous_inside = current_inside
    return tuple(result)


def _polygon_area_centroid(
    polygon: Sequence[tuple[float, float]],
) -> tuple[float, float, float]:
    if len(polygon) < 3:
        return 0.0, 0.0, 0.0
    twice_area = 0.0
    cx_numerator = 0.0
    cy_numerator = 0.0
    for index, p1 in enumerate(polygon):
        p2 = polygon[(index + 1) % len(polygon)]
        cross = p1[0] * p2[1] - p2[0] * p1[1]
        twice_area += cross
        cx_numerator += (p1[0] + p2[0]) * cross
        cy_numerator += (p1[1] + p2[1]) * cross
    if abs(twice_area) <= 1e-12:
        return 0.0, 0.0, 0.0
    signed_area = twice_area / 2.0
    cx = cx_numerator / (3.0 * twice_area)
    cy = cy_numerator / (3.0 * twice_area)
    if signed_area < 0.0:
        signed_area = -signed_area
    return signed_area, cx, cy


def evaluate_rectangular_column_capacity_state(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    material: ColumnSectionMaterial,
    neutral_axis_angle_deg: float,
    neutral_axis_depth_c_mm: float,
) -> ColumnSectionCapacityState:
    width = float(width_mm)
    depth = float(depth_mm)
    c = float(neutral_axis_depth_c_mm)
    if not math.isfinite(width) or width <= 0.0 or not math.isfinite(depth) or depth <= 0.0:
        raise ColumnSectionCapacityError("section dimensions must be finite and > 0")
    if not bars:
        raise ColumnSectionCapacityError("bars must be nonempty")
    if not math.isfinite(c) or c <= 0.0:
        raise ColumnSectionCapacityError("neutral_axis_depth_c_mm must be finite and > 0")

    theta = math.radians(float(neutral_axis_angle_deg))
    nx = math.cos(theta)
    ny = math.sin(theta)
    rectangle = (
        (-width / 2.0, -depth / 2.0),
        (width / 2.0, -depth / 2.0),
        (width / 2.0, depth / 2.0),
        (-width / 2.0, depth / 2.0),
    )
    q_extreme = max(_dot(point, nx, ny) for point in rectangle)
    q_na = q_extreme - c
    a = float(material.k1) * c
    q_block = q_extreme - a
    compression_polygon = _clip_polygon_halfplane(rectangle, nx=nx, ny=ny, q_min=q_block)
    concrete_area, concrete_x2, concrete_x3 = _polygon_area_centroid(compression_polygon)

    concrete_stress = TS500_CONCRETE_BLOCK_FACTOR * material.fcd_mpa
    concrete_force = concrete_stress * concrete_area
    n_total = concrete_force
    m2_total = concrete_force * concrete_x3
    m3_total = -concrete_force * concrete_x2

    steel_force_total = 0.0
    max_compression_strain = 0.0
    max_tension_strain = 0.0
    for bar in bars:
        q_bar = bar.x2_mm * nx + bar.x3_mm * ny
        strain = material.epsilon_cu * (q_bar - q_na) / c
        steel_stress = max(-material.fyd_mpa, min(material.fyd_mpa, material.es_mpa * strain))

        # The equivalent concrete block is based on the gross concrete polygon.
        # Use net steel stress where a bar centre lies inside that block to avoid
        # counting the replaced concrete area twice.
        net_stress = steel_stress
        if q_bar >= q_block - 1e-12:
            net_stress -= concrete_stress
        force = net_stress * bar.area_mm2
        steel_force_total += force
        n_total += force
        m2_total += force * bar.x3_mm
        m3_total += -force * bar.x2_mm
        max_compression_strain = max(max_compression_strain, strain)
        max_tension_strain = min(max_tension_strain, strain)

    return ColumnSectionCapacityState(
        neutral_axis_angle_deg=float(neutral_axis_angle_deg) % 360.0,
        neutral_axis_depth_c_mm=c,
        block_depth_a_mm=a,
        n_compression_n=n_total,
        m2_nmm=m2_total,
        m3_nmm=m3_total,
        concrete_force_n=concrete_force,
        steel_force_n=steel_force_total,
        concrete_area_mm2=concrete_area,
        concrete_centroid_x2_mm=concrete_x2,
        concrete_centroid_x3_mm=concrete_x3,
        max_steel_compression_strain=max_compression_strain,
        max_steel_tension_strain=max_tension_strain,
    )


def solve_capacity_state_for_axial_force(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    material: ColumnSectionMaterial,
    neutral_axis_angle_deg: float,
    target_n_compression_n: float,
    axial_tolerance_n: float = 1.0,
    max_iterations: int = 100,
) -> ColumnSectionCapacityState | None:
    target = float(target_n_compression_n)
    diagonal = math.hypot(float(width_mm), float(depth_mm))
    c_min = max(diagonal * 1e-6, 1e-6)
    c_max = diagonal * 1e4

    # Logarithmic scan finds a deterministic sign-change bracket without
    # assuming a particular global derivative for N(c).
    samples: list[tuple[float, ColumnSectionCapacityState, float]] = []
    sample_count = 180
    ratio = (c_max / c_min) ** (1.0 / float(sample_count - 1))
    c = c_min
    for _ in range(sample_count):
        state = evaluate_rectangular_column_capacity_state(
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=bars,
            material=material,
            neutral_axis_angle_deg=neutral_axis_angle_deg,
            neutral_axis_depth_c_mm=c,
        )
        residual = state.n_compression_n - target
        if abs(residual) <= axial_tolerance_n:
            return state
        samples.append((c, state, residual))
        c *= ratio

    bracket: tuple[tuple[float, ColumnSectionCapacityState, float], tuple[float, ColumnSectionCapacityState, float]] | None = None
    for left, right in zip(samples, samples[1:]):
        if left[2] == 0.0 or right[2] == 0.0 or left[2] * right[2] < 0.0:
            bracket = (left, right)
            break
    if bracket is None:
        return None

    left, right = bracket
    for _ in range(max_iterations):
        c_mid = 0.5 * (left[0] + right[0])
        mid_state = evaluate_rectangular_column_capacity_state(
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=bars,
            material=material,
            neutral_axis_angle_deg=neutral_axis_angle_deg,
            neutral_axis_depth_c_mm=c_mid,
        )
        mid_residual = mid_state.n_compression_n - target
        if abs(mid_residual) <= axial_tolerance_n:
            return mid_state
        mid = (c_mid, mid_state, mid_residual)
        if left[2] * mid_residual <= 0.0:
            right = mid
        else:
            left = mid
    final = left[1] if abs(left[2]) <= abs(right[2]) else right[1]
    return final if abs(final.n_compression_n - target) <= max(axial_tolerance_n, 1e-6 * max(1.0, abs(target))) else None


def build_interaction_envelope_at_axial_force(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[ColumnBarPoint],
    material: ColumnSectionMaterial,
    target_n_compression_n: float,
    angle_count: int = 72,
    axial_tolerance_n: float = 1.0,
) -> ColumnInteractionEnvelope:
    if angle_count < 8 or angle_count % 4 != 0:
        raise ColumnSectionCapacityError("angle_count must be >= 8 and divisible by 4")
    states: list[ColumnSectionCapacityState] = []
    step = 360.0 / float(angle_count)
    for index in range(angle_count):
        state = solve_capacity_state_for_axial_force(
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=bars,
            material=material,
            neutral_axis_angle_deg=index * step,
            target_n_compression_n=target_n_compression_n,
            axial_tolerance_n=axial_tolerance_n,
        )
        if state is not None:
            states.append(state)
    return ColumnInteractionEnvelope(
        target_n_compression_n=float(target_n_compression_n),
        states=tuple(states),
        status="PROVEN" if len(states) == angle_count else "OUTSIDE_AXIAL_CAPACITY",
        angle_step_deg=step,
    )


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_hull(points: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return tuple(unique)
    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def radial_moment_capacity(
    envelope: ColumnInteractionEnvelope,
    *,
    demand_m2_nmm: float,
    demand_m3_nmm: float,
) -> RadialMomentCapacity:
    if envelope.status != "PROVEN" or len(envelope.states) < 3:
        return RadialMomentCapacity(0.0, 0.0, 0.0, 0.0, "NO_CAPACITY_ENVELOPE")
    m2 = float(demand_m2_nmm)
    m3 = float(demand_m3_nmm)
    magnitude = math.hypot(m2, m3)
    if magnitude <= 1e-12:
        return RadialMomentCapacity(0.0, math.inf, 0.0, 0.0, "ZERO_MOMENT_DEMAND")
    ux = m2 / magnitude
    uy = m3 / magnitude
    hull = _convex_hull((state.m2_nmm, state.m3_nmm) for state in envelope.states)
    best_t: float | None = None
    best_point: tuple[float, float] | None = None

    # Ray r=t*u, t>=0 intersected with each convex-hull segment.
    for index, p1 in enumerate(hull):
        p2 = hull[(index + 1) % len(hull)]
        sx = p2[0] - p1[0]
        sy = p2[1] - p1[1]
        denominator = ux * sy - uy * sx
        if abs(denominator) <= 1e-18:
            continue
        t = (p1[0] * sy - p1[1] * sx) / denominator
        v = (p1[0] * uy - p1[1] * ux) / denominator
        if t >= -1e-9 and -1e-9 <= v <= 1.0 + 1e-9:
            t = max(0.0, t)
            if best_t is None or t < best_t:
                best_t = t
                best_point = (t * ux, t * uy)

    angle = math.degrees(math.atan2(m3, m2)) % 360.0
    if best_t is None or best_point is None:
        return RadialMomentCapacity(angle, 0.0, 0.0, 0.0, "NO_RAY_INTERSECTION")
    return RadialMomentCapacity(angle, best_t, best_point[0], best_point[1], "PROVEN")


__all__ = [
    "ColumnInteractionEnvelope",
    "ColumnSectionCapacityError",
    "ColumnSectionCapacityState",
    "ColumnSectionMaterial",
    "RadialMomentCapacity",
    "TS500_CONCRETE_BLOCK_FACTOR",
    "TS500_EPSILON_CU",
    "TS500_ES_MPA",
    "build_interaction_envelope_at_axial_force",
    "evaluate_rectangular_column_capacity_state",
    "radial_moment_capacity",
    "solve_capacity_state_for_axial_force",
    "ts500_k1_for_fck_mpa",
]
