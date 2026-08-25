import pytest

from tbdy_engine.design.columns.minimum_eccentricity import (
    apply_ts500_minimum_eccentricity,
    ts500_minimum_eccentricity_mm,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


COMP = "+0.00:C2:236"


def _state(*, n=1_000_000.0, m2=100_000_000.0, m3=50_000_000.0, state_id="s1"):
    return ColumnDemandState(
        state_id=state_id,
        component_id=COMP,
        output_case="ULS",
        case_type="DesignStaticLinearExact",
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity="fixture",
    )


def test_ts500_emin_formula_is_source_exact():
    assert ts500_minimum_eccentricity_mm(800.0) == pytest.approx(39.0)
    assert ts500_minimum_eccentricity_mm(500.0) == pytest.approx(30.0)


def test_existing_moments_above_directional_minimum_are_preserved():
    result = apply_ts500_minimum_eccentricity(
        component_id=COMP,
        width_mm=500.0,
        depth_mm=800.0,
        demands=(_state(m2=100_000_000.0, m3=-50_000_000.0),),
    )
    assert result.status == "PROVEN_TS500_MINIMUM_ECCENTRICITY"
    assert result.output_state_count == 1
    state = result.states[0]
    assert state.m2_nmm == pytest.approx(100_000_000.0)
    assert state.m3_nmm == pytest.approx(-50_000_000.0)
    assert result.adjustments[0].application_status == "ALREADY_SATISFIED"


def test_small_signed_moments_are_floored_without_changing_their_sign():
    # width=500 -> M3 emin=30 mm, depth=800 -> M2 emin=39 mm.
    result = apply_ts500_minimum_eccentricity(
        component_id=COMP,
        width_mm=500.0,
        depth_mm=800.0,
        demands=(_state(m2=-10_000_000.0, m3=20_000_000.0),),
    )
    assert result.output_state_count == 1
    state = result.states[0]
    assert state.m2_nmm == pytest.approx(-39_000_000.0)
    assert state.m3_nmm == pytest.approx(30_000_000.0)
    adjustment = result.adjustments[0]
    assert adjustment.m2_adjusted
    assert adjustment.m3_adjusted
    assert adjustment.application_status == "APPLIED_MOMENT_FLOOR"


def test_zero_moment_direction_branches_both_imperfection_signs():
    result = apply_ts500_minimum_eccentricity(
        component_id=COMP,
        width_mm=500.0,
        depth_mm=800.0,
        demands=(_state(m2=0.0, m3=100_000_000.0),),
    )
    assert result.output_state_count == 2
    assert {state.m2_nmm for state in result.states} == pytest.approx({-39_000_000.0, 39_000_000.0})
    assert {state.m3_nmm for state in result.states} == {100_000_000.0}
    assert result.sign_branch_source_state_count == 1
    assert result.adjustments[0].application_status == "APPLIED_WITH_SIGN_BRANCHING"


def test_zero_biaxial_moments_create_four_minimum_eccentricity_sign_states():
    result = apply_ts500_minimum_eccentricity(
        component_id=COMP,
        width_mm=500.0,
        depth_mm=800.0,
        demands=(_state(m2=0.0, m3=0.0),),
    )
    assert result.output_state_count == 4
    assert {(s.m2_nmm, s.m3_nmm) for s in result.states} == {
        (-39_000_000.0, -30_000_000.0),
        (-39_000_000.0, 30_000_000.0),
        (39_000_000.0, -30_000_000.0),
        (39_000_000.0, 30_000_000.0),
    }


def test_noncompression_state_is_preserved_and_marked_not_applicable():
    result = apply_ts500_minimum_eccentricity(
        component_id=COMP,
        width_mm=500.0,
        depth_mm=800.0,
        demands=(_state(n=-50_000.0, m2=0.0, m3=0.0),),
    )
    assert result.output_state_count == 1
    assert result.states[0].m2_nmm == 0.0
    assert result.states[0].m3_nmm == 0.0
    assert result.adjustments[0].application_status == "NOT_APPLICABLE_NONCOMPRESSION"
