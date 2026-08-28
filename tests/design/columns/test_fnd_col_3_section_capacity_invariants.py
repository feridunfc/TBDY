from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from fnd_col_3_benchmarks import C35, SQ  # noqa: E402
from fnd_col_3_independent_oracle import axial_limits  # noqa: E402
from tbdy_engine.design.columns.rebar_layout import ColumnBarPoint  # noqa: E402
from tbdy_engine.design.columns.section_capacity import (  # noqa: E402
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    evaluate_rectangular_column_capacity_state,
    radial_moment_capacity,
    solve_capacity_state_for_axial_force,
)


def _bars(reverse: bool = False):
    values = tuple(
        ColumnBarPoint(bar.index, bar.x2_mm, bar.x3_mm, bar.diameter_mm, bar.area_mm2)
        for bar in SQ.bars
    )
    return tuple(reversed(values)) if reverse else values


def _material():
    m = C35.material
    return ColumnSectionMaterial(m.fck_mpa, m.fcd_mpa, m.fyd_mpa, k1=m.k1)


def _state(theta: float, c_mm: float = 300.0, reverse_bars: bool = False):
    return evaluate_rectangular_column_capacity_state(
        width_mm=SQ.width_mm,
        depth_mm=SQ.depth_mm,
        bars=_bars(reverse_bars),
        material=_material(),
        neutral_axis_angle_deg=theta,
        neutral_axis_depth_c_mm=c_mm,
    )


def test_theta_plus_360_equivalence():
    a = _state(33.0)
    b = _state(393.0)
    assert a.n_compression_n == pytest.approx(b.n_compression_n, rel=1e-12, abs=1e-6)
    assert a.m2_nmm == pytest.approx(b.m2_nmm, rel=1e-12, abs=1e-4)
    assert a.m3_nmm == pytest.approx(b.m3_nmm, rel=1e-12, abs=1e-4)


def test_180_degree_sign_reversal_for_square_symmetric_layout():
    a = _state(33.0)
    b = _state(213.0)
    assert a.n_compression_n == pytest.approx(b.n_compression_n, rel=1e-12, abs=1e-6)
    assert a.m2_nmm == pytest.approx(-b.m2_nmm, rel=1e-12, abs=1e-4)
    assert a.m3_nmm == pytest.approx(-b.m3_nmm, rel=1e-12, abs=1e-4)


def test_m2_m3_axis_symmetry_for_square_symmetric_layout():
    x = _state(0.0)
    y = _state(90.0)
    assert x.n_compression_n == pytest.approx(y.n_compression_n, rel=1e-12, abs=1e-6)
    assert abs(x.m2_nmm) <= 1.0
    assert abs(y.m3_nmm) <= 1.0
    assert abs(x.m3_nmm) == pytest.approx(abs(y.m2_nmm), rel=1e-12, abs=1e-4)


def test_90_degree_rotation_behavior_for_square_symmetric_layout():
    a = _state(33.0)
    b = _state(123.0)
    assert a.n_compression_n == pytest.approx(b.n_compression_n, rel=1e-12, abs=1e-6)
    assert b.m2_nmm == pytest.approx(-a.m3_nmm, rel=1e-12, abs=1e-4)
    assert b.m3_nmm == pytest.approx(a.m2_nmm, rel=1e-12, abs=1e-4)


def test_demand_vector_sign_and_rotation_behavior():
    envelope = build_interaction_envelope_at_axial_force(
        width_mm=SQ.width_mm,
        depth_mm=SQ.depth_mm,
        bars=_bars(),
        material=_material(),
        target_n_compression_n=3_000_000.0,
        angle_count=144,
        axial_tolerance_n=1.0,
    )
    r = radial_moment_capacity(envelope, demand_m2_nmm=2.0, demand_m3_nmm=1.0)
    opposite = radial_moment_capacity(envelope, demand_m2_nmm=-2.0, demand_m3_nmm=-1.0)
    rotated = radial_moment_capacity(envelope, demand_m2_nmm=-1.0, demand_m3_nmm=2.0)
    assert r.status == opposite.status == rotated.status == "PROVEN"
    assert r.capacity_nmm == pytest.approx(opposite.capacity_nmm, rel=1e-12, abs=1e-4)
    assert r.capacity_nmm == pytest.approx(rotated.capacity_nmm, rel=1e-12, abs=1e-4)
    assert r.boundary_m2_nmm == pytest.approx(-opposite.boundary_m2_nmm, rel=1e-12, abs=1e-4)
    assert r.boundary_m3_nmm == pytest.approx(-opposite.boundary_m3_nmm, rel=1e-12, abs=1e-4)


def test_zero_moment_demand_semantics():
    envelope = build_interaction_envelope_at_axial_force(
        width_mm=SQ.width_mm,
        depth_mm=SQ.depth_mm,
        bars=_bars(),
        material=_material(),
        target_n_compression_n=3_000_000.0,
        angle_count=36,
        axial_tolerance_n=1.0,
    )
    result = radial_moment_capacity(envelope, demand_m2_nmm=0.0, demand_m3_nmm=0.0)
    assert result.status == "ZERO_MOMENT_DEMAND"
    assert math.isinf(result.capacity_nmm)


def test_bar_order_independence():
    a = _state(33.0, reverse_bars=False)
    b = _state(33.0, reverse_bars=True)
    assert a.n_compression_n == pytest.approx(b.n_compression_n, rel=1e-12, abs=1e-6)
    assert a.m2_nmm == pytest.approx(b.m2_nmm, rel=1e-12, abs=1e-4)
    assert a.m3_nmm == pytest.approx(b.m3_nmm, rel=1e-12, abs=1e-4)


def test_deterministic_state_ordering():
    kwargs = dict(
        width_mm=SQ.width_mm,
        depth_mm=SQ.depth_mm,
        bars=_bars(),
        material=_material(),
        target_n_compression_n=3_000_000.0,
        angle_count=72,
        axial_tolerance_n=1.0,
    )
    a = build_interaction_envelope_at_axial_force(**kwargs)
    b = build_interaction_envelope_at_axial_force(**kwargs)
    assert a.states == b.states
    assert tuple(state.neutral_axis_angle_deg for state in a.states) == tuple(i * 5.0 for i in range(72))


def test_fixed_p_axial_residual_is_within_one_newton():
    state = solve_capacity_state_for_axial_force(
        width_mm=SQ.width_mm,
        depth_mm=SQ.depth_mm,
        bars=_bars(),
        material=_material(),
        neutral_axis_angle_deg=37.0,
        target_n_compression_n=3_000_000.0,
        axial_tolerance_n=1.0,
    )
    assert state is not None
    assert abs(state.n_compression_n - 3_000_000.0) <= 1.0


def test_both_axial_domain_sides_fail_closed_without_partial_envelope():
    n_min, n_max = axial_limits(
        width_mm=SQ.width_mm,
        depth_mm=SQ.depth_mm,
        bars=SQ.bars,
        material=C35.material,
    )
    for target in (1.01 * n_max, 1.01 * n_min):
        envelope = build_interaction_envelope_at_axial_force(
            width_mm=SQ.width_mm,
            depth_mm=SQ.depth_mm,
            bars=_bars(),
            material=_material(),
            target_n_compression_n=target,
            angle_count=36,
            axial_tolerance_n=1.0,
        )
        assert envelope.status == "OUTSIDE_AXIAL_CAPACITY"
        assert len(envelope.states) == 0
        radial = radial_moment_capacity(envelope, demand_m2_nmm=1.0, demand_m3_nmm=1.0)
        assert radial.status == "NO_CAPACITY_ENVELOPE"
        assert radial.capacity_nmm == 0.0
