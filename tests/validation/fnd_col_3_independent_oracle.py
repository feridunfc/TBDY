"""Independent numerical oracle for FND-COL-3 section-capacity validation.

This module intentionally does not import tbdy_engine.design.columns.section_capacity.
It uses an independent strip-integration path, an all-bracket fixed-P scan/root solver,
and a dense independent convex-domain reconstruction rather than production hull/ray helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

# 8-point Gauss-Legendre nodes/weights on [-1, 1].  Exact for polynomials up to degree 15.
_GL8 = (
    (-0.9602898564975363, 0.1012285362903763),
    (-0.7966664774136267, 0.2223810344533745),
    (-0.5255324099163290, 0.3137066458778873),
    (-0.1834346424956498, 0.3626837833783620),
    (0.1834346424956498, 0.3626837833783620),
    (0.5255324099163290, 0.3137066458778873),
    (0.7966664774136267, 0.2223810344533745),
    (0.9602898564975363, 0.1012285362903763),
)

CONCRETE_BLOCK_FACTOR = 0.85
ES_MPA = 200_000.0
EPSILON_CU = 0.003


@dataclass(frozen=True, slots=True)
class OracleBar:
    index: int
    x2_mm: float
    x3_mm: float
    diameter_mm: float
    area_mm2: float


@dataclass(frozen=True, slots=True)
class OracleMaterial:
    fck_mpa: float
    fcd_mpa: float
    fyd_mpa: float
    k1: float
    es_mpa: float = ES_MPA
    epsilon_cu: float = EPSILON_CU


@dataclass(frozen=True, slots=True)
class OracleState:
    theta_deg: float
    c_mm: float
    n_n: float
    m2_nmm: float
    m3_nmm: float
    concrete_area_mm2: float
    concrete_first_x2_mm3: float
    concrete_first_x3_mm3: float


@dataclass(frozen=True, slots=True)
class RootAudit:
    target_n: float
    theta_deg: float
    brackets: tuple[tuple[float, float], ...]
    roots_mm: tuple[float, ...]
    min_sample_residual_n: float
    max_negative_delta_n: float

    @property
    def root_count(self) -> int:
        return len(self.roots_mm)


@dataclass(frozen=True, slots=True)
class OracleRadialCapacity:
    status: str
    capacity_nmm: float
    boundary_m2_nmm: float
    boundary_m3_nmm: float
    demand_angle_deg: float
    theta_deg: float | None
    axial_residual_n: float | None


def _q_extreme(width_mm: float, depth_mm: float, nx: float, ny: float) -> float:
    return 0.5 * (abs(nx) * width_mm + abs(ny) * depth_mm)


def _slice_values(
    x: float,
    *,
    depth_mm: float,
    nx: float,
    ny: float,
    q_block: float,
) -> tuple[float, float, float]:
    """Return area density, first-x2 density, first-x3 density for a vertical strip."""
    y_lo = -depth_mm / 2.0
    y_hi = depth_mm / 2.0
    eps = 1e-15
    if abs(ny) <= eps:
        if nx * x < q_block:
            return 0.0, 0.0, 0.0
    elif ny > 0.0:
        y_lo = max(y_lo, (q_block - nx * x) / ny)
    else:
        y_hi = min(y_hi, (q_block - nx * x) / ny)
    if y_hi <= y_lo:
        return 0.0, 0.0, 0.0
    length = y_hi - y_lo
    first_y = 0.5 * (y_hi * y_hi - y_lo * y_lo)
    return length, x * length, first_y


def _integrate_compression_region(
    *,
    width_mm: float,
    depth_mm: float,
    nx: float,
    ny: float,
    q_block: float,
) -> tuple[float, float, float]:
    """Integrate concrete area and first moments by independent vertical strips."""
    x_min = -width_mm / 2.0
    x_max = width_mm / 2.0
    breaks = [x_min, x_max]
    eps = 1e-15

    # Split exactly where the clipping line crosses top/bottom section edges.
    if abs(nx) > eps:
        for y in (-depth_mm / 2.0, depth_mm / 2.0):
            x = (q_block - ny * y) / nx
            if x_min < x < x_max:
                breaks.append(x)
        # When ny ~= 0 the full/empty vertical strip transition is here.
        if abs(ny) <= eps:
            x = q_block / nx
            if x_min < x < x_max:
                breaks.append(x)

    points = sorted(set(round(v, 13) for v in breaks))
    area = first_x2 = first_x3 = 0.0
    for left, right in zip(points, points[1:]):
        if right <= left:
            continue
        mid = 0.5 * (left + right)
        half = 0.5 * (right - left)
        for node, weight in _GL8:
            x = mid + half * node
            a_density, x2_density, x3_density = _slice_values(
                x,
                depth_mm=depth_mm,
                nx=nx,
                ny=ny,
                q_block=q_block,
            )
            factor = half * weight
            area += factor * a_density
            first_x2 += factor * x2_density
            first_x3 += factor * x3_density
    # Round microscopic quadrature noise only at empty/full geometric limits.
    if abs(area) < 1e-10:
        return 0.0, 0.0, 0.0
    return area, first_x2, first_x3


def evaluate_state(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[OracleBar],
    material: OracleMaterial,
    theta_deg: float,
    c_mm: float,
) -> OracleState:
    if width_mm <= 0.0 or depth_mm <= 0.0 or c_mm <= 0.0 or not bars:
        raise ValueError("positive section dimensions/c and nonempty bars are required")
    theta = math.radians(theta_deg)
    nx = math.cos(theta)
    ny = math.sin(theta)
    q_extreme = _q_extreme(width_mm, depth_mm, nx, ny)
    q_na = q_extreme - c_mm
    q_block = q_extreme - material.k1 * c_mm
    area, first_x2, first_x3 = _integrate_compression_region(
        width_mm=width_mm,
        depth_mm=depth_mm,
        nx=nx,
        ny=ny,
        q_block=q_block,
    )
    concrete_stress = CONCRETE_BLOCK_FACTOR * material.fcd_mpa
    n_total = concrete_stress * area
    m2_total = concrete_stress * first_x3
    m3_total = -concrete_stress * first_x2

    for bar in bars:
        q_bar = bar.x2_mm * nx + bar.x3_mm * ny
        strain = material.epsilon_cu * (q_bar - q_na) / c_mm
        steel_stress = max(-material.fyd_mpa, min(material.fyd_mpa, material.es_mpa * strain))
        net_stress = steel_stress
        if q_bar >= q_block - 1e-12:
            net_stress -= concrete_stress
        force = net_stress * bar.area_mm2
        n_total += force
        m2_total += force * bar.x3_mm
        m3_total += -force * bar.x2_mm

    return OracleState(
        theta_deg=theta_deg % 360.0,
        c_mm=c_mm,
        n_n=n_total,
        m2_nmm=m2_total,
        m3_nmm=m3_total,
        concrete_area_mm2=area,
        concrete_first_x2_mm3=first_x2,
        concrete_first_x3_mm3=first_x3,
    )


def axial_limits(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[OracleBar],
    material: OracleMaterial,
) -> tuple[float, float]:
    """Analytic asymptotic tension/compression limits for the supported point-bar model."""
    steel_area = sum(bar.area_mm2 for bar in bars)
    concrete_stress = CONCRETE_BLOCK_FACTOR * material.fcd_mpa
    n_min = -material.fyd_mpa * steel_area
    n_max = (
        concrete_stress * width_mm * depth_mm
        + (material.fyd_mpa - concrete_stress) * steel_area
    )
    return n_min, n_max


def _scan_grid(diagonal_mm: float, count: int) -> tuple[float, ...]:
    # Much broader and denser than production's 180-sample [1e-6,1e4]*diagonal scan.
    c_min = max(diagonal_mm * 1e-8, 1e-8)
    c_max = diagonal_mm * 1e6
    ratio = (c_max / c_min) ** (1.0 / (count - 1))
    values = []
    c = c_min
    for _ in range(count):
        values.append(c)
        c *= ratio
    return tuple(values)


def _bisect_root(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[OracleBar],
    material: OracleMaterial,
    theta_deg: float,
    target_n: float,
    left_c: float,
    right_c: float,
    axial_tolerance_n: float,
    max_iterations: int = 120,
) -> OracleState:
    left_state = evaluate_state(
        width_mm=width_mm, depth_mm=depth_mm, bars=bars, material=material,
        theta_deg=theta_deg, c_mm=left_c,
    )
    right_state = evaluate_state(
        width_mm=width_mm, depth_mm=depth_mm, bars=bars, material=material,
        theta_deg=theta_deg, c_mm=right_c,
    )
    left_r = left_state.n_n - target_n
    right_r = right_state.n_n - target_n
    if left_r == 0.0:
        return left_state
    if right_r == 0.0:
        return right_state
    if left_r * right_r > 0.0:
        raise ValueError("root bracket does not change sign")
    best = left_state if abs(left_r) <= abs(right_r) else right_state
    best_r = min(abs(left_r), abs(right_r))
    for _ in range(max_iterations):
        mid_c = 0.5 * (left_c + right_c)
        mid = evaluate_state(
            width_mm=width_mm, depth_mm=depth_mm, bars=bars, material=material,
            theta_deg=theta_deg, c_mm=mid_c,
        )
        mid_r = mid.n_n - target_n
        if abs(mid_r) < best_r:
            best = mid
            best_r = abs(mid_r)
        if abs(mid_r) <= axial_tolerance_n:
            return mid
        if left_r * mid_r <= 0.0:
            right_c = mid_c
            right_r = mid_r
        else:
            left_c = mid_c
            left_r = mid_r
    return best


def audit_fixed_p_roots(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[OracleBar],
    material: OracleMaterial,
    theta_deg: float,
    target_n: float,
    scan_count: int = 1200,
    axial_tolerance_n: float = 1.0,
) -> RootAudit:
    diagonal = math.hypot(width_mm, depth_mm)
    grid = _scan_grid(diagonal, scan_count)
    samples: list[tuple[float, float]] = []
    min_abs = math.inf
    max_negative_delta = 0.0
    last_n: float | None = None
    for c in grid:
        n = evaluate_state(
            width_mm=width_mm, depth_mm=depth_mm, bars=bars, material=material,
            theta_deg=theta_deg, c_mm=c,
        ).n_n
        residual = n - target_n
        samples.append((c, residual))
        min_abs = min(min_abs, abs(residual))
        if last_n is not None:
            max_negative_delta = min(max_negative_delta, n - last_n)
        last_n = n

    brackets: list[tuple[float, float]] = []
    for (c1, r1), (c2, r2) in zip(samples, samples[1:]):
        if r1 == 0.0:
            brackets.append((c1, c1))
        elif r2 == 0.0:
            brackets.append((c2, c2))
        elif r1 * r2 < 0.0:
            brackets.append((c1, c2))

    # De-duplicate touching exact-root brackets.
    dedup: list[tuple[float, float]] = []
    for bracket in brackets:
        if not dedup or abs(bracket[0] - dedup[-1][0]) > 1e-12 or abs(bracket[1] - dedup[-1][1]) > 1e-12:
            dedup.append(bracket)

    roots: list[float] = []
    for left, right in dedup:
        if left == right:
            roots.append(left)
            continue
        root = _bisect_root(
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=bars,
            material=material,
            theta_deg=theta_deg,
            target_n=target_n,
            left_c=left,
            right_c=right,
            axial_tolerance_n=axial_tolerance_n,
        )
        roots.append(root.c_mm)

    return RootAudit(
        target_n=target_n,
        theta_deg=theta_deg,
        brackets=tuple(dedup),
        roots_mm=tuple(roots),
        min_sample_residual_n=min_abs,
        max_negative_delta_n=max_negative_delta,
    )


def solve_fixed_p_state(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[OracleBar],
    material: OracleMaterial,
    theta_deg: float,
    target_n: float,
    axial_tolerance_n: float = 1.0,
    scan_count: int = 360,
) -> OracleState | None:
    audit = audit_fixed_p_roots(
        width_mm=width_mm,
        depth_mm=depth_mm,
        bars=bars,
        material=material,
        theta_deg=theta_deg,
        target_n=target_n,
        scan_count=scan_count,
        axial_tolerance_n=axial_tolerance_n,
    )
    if audit.root_count == 0:
        return None
    if audit.root_count != 1:
        raise RuntimeError("MULTIPLE_FIXED_P_ROOTS_UNRESOLVED")
    c = audit.roots_mm[0]
    return evaluate_state(
        width_mm=width_mm, depth_mm=depth_mm, bars=bars, material=material,
        theta_deg=theta_deg, c_mm=c,
    )


def _orientation(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _gift_wrap_hull(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """Independent Jarvis-march convex hull; intentionally unlike production monotone chain."""
    unique = list(dict.fromkeys(points))
    if len(unique) <= 2:
        return tuple(unique)
    start = min(unique, key=lambda p: (p[0], p[1]))
    hull: list[tuple[float, float]] = []
    current = start
    while True:
        hull.append(current)
        candidate = unique[0] if unique[0] != current else unique[1]
        for point in unique:
            if point == current or point == candidate:
                continue
            turn = _orientation(current, candidate, point)
            if turn < -1e-9:
                candidate = point
            elif abs(turn) <= 1e-9:
                dc = (candidate[0] - current[0]) ** 2 + (candidate[1] - current[1]) ** 2
                dp = (point[0] - current[0]) ** 2 + (point[1] - current[1]) ** 2
                if dp > dc:
                    candidate = point
        current = candidate
        if current == start:
            break
        if len(hull) > len(unique) + 1:
            raise RuntimeError("independent convex hull failed to close")
    return tuple(hull)


def _ray_intersection_with_hull(
    hull: Sequence[tuple[float, float]],
    *,
    demand_m2_nmm: float,
    demand_m3_nmm: float,
) -> tuple[float, float, float] | None:
    """Independent ray-to-convex-boundary intersection."""
    magnitude = math.hypot(demand_m2_nmm, demand_m3_nmm)
    if magnitude <= 1e-12:
        return math.inf, 0.0, 0.0
    ux = demand_m2_nmm / magnitude
    uy = demand_m3_nmm / magnitude
    hits: list[tuple[float, float, float]] = []
    for i, p1 in enumerate(hull):
        p2 = hull[(i + 1) % len(hull)]
        sx = p2[0] - p1[0]
        sy = p2[1] - p1[1]
        den = ux * sy - uy * sx
        if abs(den) <= 1e-18:
            continue
        t = (p1[0] * sy - p1[1] * sx) / den
        v = (p1[0] * uy - p1[1] * ux) / den
        if t >= -1e-8 and -1e-8 <= v <= 1.0 + 1e-8:
            t = max(0.0, t)
            hits.append((t, t * ux, t * uy))
    if not hits:
        return None
    # Convex domain containing origin has a single positive-ray exit; tolerate vertex duplicates.
    return min(hits, key=lambda item: item[0])


def radial_capacity_dense_convex(
    *,
    width_mm: float,
    depth_mm: float,
    bars: Sequence[OracleBar],
    material: OracleMaterial,
    target_n: float,
    demand_m2_nmm: float,
    demand_m3_nmm: float,
    angle_count: int = 1440,
    root_scan_count: int = 160,
    axial_tolerance_n: float = 1.0,
) -> OracleRadialCapacity:
    """Dense independent fixed-P boundary -> Jarvis hull -> radial capacity."""
    magnitude = math.hypot(demand_m2_nmm, demand_m3_nmm)
    angle = math.degrees(math.atan2(demand_m3_nmm, demand_m2_nmm)) % 360.0 if magnitude > 1e-12 else 0.0
    if magnitude <= 1e-12:
        return OracleRadialCapacity("ZERO_MOMENT_DEMAND", math.inf, 0.0, 0.0, angle, None, None)
    if angle_count < 8 or angle_count % 4:
        raise ValueError("angle_count must be >= 8 and divisible by 4")

    states: list[OracleState] = []
    step = 360.0 / angle_count
    max_axial_residual = 0.0
    for i in range(angle_count):
        state = solve_fixed_p_state(
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=bars,
            material=material,
            theta_deg=i * step,
            target_n=target_n,
            axial_tolerance_n=axial_tolerance_n,
            scan_count=root_scan_count,
        )
        if state is None:
            return OracleRadialCapacity("NO_CAPACITY_ENVELOPE", 0.0, 0.0, 0.0, angle, None, None)
        max_axial_residual = max(max_axial_residual, abs(state.n_n - target_n))
        states.append(state)

    hull = _gift_wrap_hull(tuple((state.m2_nmm, state.m3_nmm) for state in states))
    hit = _ray_intersection_with_hull(
        hull,
        demand_m2_nmm=demand_m2_nmm,
        demand_m3_nmm=demand_m3_nmm,
    )
    if hit is None:
        return OracleRadialCapacity("NO_RAY_INTERSECTION", 0.0, 0.0, 0.0, angle, None, max_axial_residual)
    radius, m2, m3 = hit
    return OracleRadialCapacity("PROVEN", radius, m2, m3, angle, None, max_axial_residual)
