import math

import pytest

from tbdy_engine.design.columns.moment_magnification import (
    ColumnMomentMagnificationAxisBasis,
    ColumnMomentMagnificationError,
    STIFFNESS_METHOD_EQ_7_21,
    evaluate_ts500_axis_moment_magnification,
    magnify_concurrent_column_demand_state,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import SWAY_PERMITTED, SWAY_PREVENTED


def _axis(*, axis, state_id="S1", sway=SWAY_PREVENTED, nd=500_000.0, lk=4000.0, radius=150.0, **overrides):
    values = dict(
        demand_state_id=state_id,
        axis=axis,
        sway_classification=sway,
        nd_compression_n=nd,
        m1_over_m2=-0.5,
        effective_length_lk_mm=lk,
        radius_i_mm=radius,
        ec_mpa=30_000.0,
        ic_mm4=8.0e9,
        creep_ratio_rm=0.20,
        stiffness_method=STIFFNESS_METHOD_EQ_7_21,
        source_refs=(f"{axis}-basis",),
    )
    values.update(overrides)
    if sway == SWAY_PERMITTED:
        values.setdefault("story_sum_nd_n", 2_000_000.0)
        values.setdefault("story_sum_nk_n", 12_000_000.0)
        values.setdefault("fck_mpa", 30.0)
        values.setdefault("concrete_area_mm2", 300_000.0)
    return ColumnMomentMagnificationAxisBasis(**values)


def _state():
    return ColumnDemandState(
        state_id="S1",
        component_id="Story1:C1:1",
        output_case="COMB1",
        case_type="Combination",
        step_type=None,
        step_number=None,
        station_m=0.0,
        end_tag="I_END",
        nd_compression_n=500_000.0,
        m2_nmm=100_000_000.0,
        m3_nmm=40_000_000.0,
        source_identity="B5:COMB1:I_END",
    )


def test_sway_prevented_eq724_computes_individual_beta():
    result = evaluate_ts500_axis_moment_magnification(_axis(axis="M2"))
    expected_ei = 0.4 * 30_000.0 * 8.0e9 / 1.2
    expected_nk = math.pi**2 * expected_ei / 4000.0**2
    expected_cm = max(0.4, 0.6 + 0.4 * -0.5)
    expected_beta = max(1.0, expected_cm / (1.0 - 500_000.0 / (1.3 * expected_nk)))
    assert result.applied
    assert math.isclose(result.effective_ei_nmm2, expected_ei)
    assert math.isclose(result.critical_load_nk_n, expected_nk)
    assert math.isclose(result.cm, expected_cm)
    assert math.isclose(result.final_magnification_factor, expected_beta)


def test_horizontal_load_between_ends_forces_cm_one_without_ratio():
    result = evaluate_ts500_axis_moment_magnification(
        _axis(
            axis="M2",
            horizontal_load_between_ends=True,
            m1_over_m2=None,
        )
    )

    assert result.cm == 1.0


def test_sway_permitted_uses_individual_and_story_beta_without_ratio():
    result = evaluate_ts500_axis_moment_magnification(
        _axis(
            axis="M3",
            sway=SWAY_PERMITTED,
            m1_over_m2=None,
        )
    )
    assert result.applied
    assert result.cm == 1.0
    assert result.beta_story is not None
    assert result.beta_individual is not None
    assert result.final_magnification_factor >= max(result.beta_story, result.beta_individual)


def test_sway_permitted_eq728_fails_closed():
    result = evaluate_ts500_axis_moment_magnification(
        _axis(
            axis="M2",
            sway=SWAY_PERMITTED,
            story_sum_nd_n=6_000_000.0,
            story_sum_nk_n=10_000_000.0,
        )
    )
    assert not result.applied
    assert result.blockers == ("TS500_EQ_7_28_STORY_CRITICAL_LOAD_LIMIT_EXCEEDED",)


def test_biaxial_application_keeps_m2_and_m3_factors_separate():
    state = _state()
    m2 = evaluate_ts500_axis_moment_magnification(
        _axis(
            axis="M2",
            nd=500_000.0,
            m1_over_m2=1.0,
        )
    )
    m3 = evaluate_ts500_axis_moment_magnification(
        _axis(
            axis="M3",
            nd=900_000.0,
            lk=5200.0,
            radius=120.0,
            m1_over_m2=1.0,
        )
    )
    assert m2.final_magnification_factor != m3.final_magnification_factor
    magnified = magnify_concurrent_column_demand_state(state, m2=m2, m3=m3)
    assert math.isclose(magnified.nd_compression_n, state.nd_compression_n)
    assert math.isclose(magnified.m2_nmm, state.m2_nmm * m2.final_magnification_factor)
    assert math.isclose(magnified.m3_nmm, state.m3_nmm * m3.final_magnification_factor)


def test_magnification_result_cannot_be_applied_to_another_demand_state():
    state = _state()
    result = evaluate_ts500_axis_moment_magnification(_axis(axis="M2", state_id="OTHER"))
    with pytest.raises(ColumnMomentMagnificationError):
        magnify_concurrent_column_demand_state(state, m2=result, m3=None)



def test_sway_prevented_without_horizontal_load_requires_exact_ratio():
    with pytest.raises(
        ColumnMomentMagnificationError,
        match="requires exact signed m1_over_m2",
    ):
        _axis(
            axis="M2",
            horizontal_load_between_ends=False,
            m1_over_m2=None,
        )
