import math
import pytest

from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarLayoutInputs,
    generate_rectangular_column_rebar_candidates,
)
from tbdy_engine.design.columns.section_capacity import (
    ColumnSectionCapacityError,
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    evaluate_rectangular_column_capacity_state,
    radial_moment_capacity,
    solve_capacity_state_for_axial_force,
    ts500_k1_for_fck_mpa,
)


def _candidate():
    population = generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(
            width_mm=800.0,
            depth_mm=800.0,
            clear_cover_mm=40.0,
            tie_diameter_mm=10.0,
            aggregate_max_mm=22.0,
            allowed_bar_diameters_mm=(20.0,),
        )
    )
    return population.candidates[0]


def _material():
    return ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=23.3333333333, fyd_mpa=434.7826086957)


def test_ts500_k1_is_source_bound_and_unknown_class_blocks():
    assert ts500_k1_for_fck_mpa(35.0) == pytest.approx(0.79)
    with pytest.raises(ColumnSectionCapacityError, match="outside the source-bound"):
        ts500_k1_for_fck_mpa(37.0)


def test_opposite_neutral_axis_states_are_symmetric_for_square_symmetric_layout():
    candidate = _candidate()
    s0 = evaluate_rectangular_column_capacity_state(
        width_mm=800.0,
        depth_mm=800.0,
        bars=candidate.bars,
        material=_material(),
        neutral_axis_angle_deg=0.0,
        neutral_axis_depth_c_mm=300.0,
    )
    s180 = evaluate_rectangular_column_capacity_state(
        width_mm=800.0,
        depth_mm=800.0,
        bars=candidate.bars,
        material=_material(),
        neutral_axis_angle_deg=180.0,
        neutral_axis_depth_c_mm=300.0,
    )
    assert s0.n_compression_n == pytest.approx(s180.n_compression_n, rel=1e-9, abs=1e-6)
    assert s0.m2_nmm == pytest.approx(-s180.m2_nmm, rel=1e-9, abs=1e-4)
    assert s0.m3_nmm == pytest.approx(-s180.m3_nmm, rel=1e-9, abs=1e-4)


def test_axial_solver_hits_requested_force_without_legacy_pmm_approximation():
    candidate = _candidate()
    target = 3_000_000.0
    state = solve_capacity_state_for_axial_force(
        width_mm=800.0,
        depth_mm=800.0,
        bars=candidate.bars,
        material=_material(),
        neutral_axis_angle_deg=0.0,
        target_n_compression_n=target,
        axial_tolerance_n=5.0,
    )
    assert state is not None
    assert state.n_compression_n == pytest.approx(target, abs=5.0)


def test_biaxial_envelope_and_radial_capacity_are_resolved_for_supported_target_axial_force():
    candidate = _candidate()
    envelope = build_interaction_envelope_at_axial_force(
        width_mm=800.0,
        depth_mm=800.0,
        bars=candidate.bars,
        material=_material(),
        target_n_compression_n=3_000_000.0,
        angle_count=16,
        axial_tolerance_n=10.0,
    )
    assert envelope.status == "PROVEN"
    assert len(envelope.states) == 16

    radial = radial_moment_capacity(envelope, demand_m2_nmm=100e6, demand_m3_nmm=50e6)
    assert radial.status == "PROVEN"
    assert math.isfinite(radial.capacity_nmm)
    assert radial.capacity_nmm > 0.0


def test_material_k1_cannot_be_overridden_with_non_source_value():
    with pytest.raises(ColumnSectionCapacityError, match="does not match"):
        ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=23.3, fyd_mpa=434.8, k1=0.85)
