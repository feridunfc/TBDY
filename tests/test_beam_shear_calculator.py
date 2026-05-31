from __future__ import annotations

import math
import pathlib
from dataclasses import is_dataclass

import pytest

from tbdy_engine.design.beams import BeamModelContext
from tbdy_engine.design.beams.calculators.shear import (
    CapacityShearDemandResult,
    ShearCheck,
    ShearResult,
    TBDYShearCalculator,
    calculate_capacity_shear_demand,
    capacity_design_ve_le_vr_check,
)
from tbdy_engine.design.beams.core_check import shear_check_to_core_check


def _ctx(**overrides: object) -> BeamModelContext:
    values = {
        "beam_id": "B175",
        "story": "+14.50",
        "section_name": "B60x60",
        "bw_mm": 600.0,
        "h_mm": 600.0,
        "d_mm": 550.0,
        "cover_mm": 40.0,
        "Ln_mm": 4600.0,
        "fck_mpa": 30.0,
        "fcd_mpa": 20.0,
        "fctd_mpa": 1.27,
        "fyk_mpa": 420.0,
        "fyd_mpa": 365.0,
        "fywd_mpa": 365.0,
        "Vd_left_kN": 90.0,
        "Ve_left_kN": 107.2,
        "Md_left_neg_kNm": 108.7,
        "Md_mid_pos_kNm": 84.8,
        "Md_right_neg_kNm": 92.4,
        "axial_kN": 0.0,
        "stirrup_legs": 2,
        "stirrup_diameter_mm": 10.0,
        "stirrup_spacing_mm": 100.0,
        "longitudinal_bar_diameter_mm": 16.0,
        "missing_inputs": (),
        "source": {"origin": "unit_test"},
    }
    values.update(overrides)
    return BeamModelContext(**values)


def test_shear_calculator_returns_deterministic_result() -> None:
    result = TBDYShearCalculator().calculate(_ctx())

    assert is_dataclass(ShearCheck)
    assert is_dataclass(ShearResult)
    assert ShearCheck.__dataclass_params__.frozen is True
    assert ShearResult.__dataclass_params__.frozen is True

    single_bar_area = math.pi * 10.0**2 / 4.0
    expected_asw = 2 * single_bar_area
    expected_vw = expected_asw * 365.0 * 550.0 / 100.0 / 1000.0
    expected_vmax = 0.85 * 0.22 * 20.0 * 600.0 * 550.0 / 1000.0

    assert result.Ve_kN == 107.2
    assert result.Vc_kN == 0.0
    assert result.Asw_mm2 == pytest.approx(expected_asw)
    assert result.Asw_cm2 == pytest.approx(expected_asw / 100.0)
    assert result.Vw_kN == pytest.approx(expected_vw)
    assert result.Vr_kN == pytest.approx(expected_vw)
    assert result.Vmax_kN == pytest.approx(expected_vmax)
    assert result.status == "OK"


def test_shear_result_has_exactly_eight_checks() -> None:
    result = TBDYShearCalculator().calculate(_ctx())

    assert [check.name for check in result.checks] == [
        "beam_shear_ve_le_vr",
        "beam_shear_ve_le_085_vmax",
        "beam_shear_spacing_le_d_over_4",
        "beam_shear_spacing_le_150",
        "beam_shear_spacing_le_8_longitudinal_diameter",
        "beam_shear_stirrup_diameter_ge_8",
        "beam_shear_stirrup_legs_ge_2",
        "beam_shear_asw_ge_asw_min",
    ]
    assert len(result.checks) == 8
    assert all(check.status == "OK" for check in result.checks)


def test_failing_shear_demand_fails_ve_le_vr() -> None:
    result = TBDYShearCalculator().calculate(_ctx(Ve_left_kN=500.0))
    statuses = {check.name: check.status for check in result.checks}

    assert result.status == "FAIL"
    assert statuses["beam_shear_ve_le_vr"] == "FAIL"


def test_failing_spacing_checks() -> None:
    result = TBDYShearCalculator().calculate(_ctx(stirrup_spacing_mm=200.0))
    statuses = {check.name: check.status for check in result.checks}

    assert statuses["beam_shear_spacing_le_d_over_4"] == "FAIL"
    assert statuses["beam_shear_spacing_le_150"] == "FAIL"


def test_failing_stirrup_diameter_and_legs() -> None:
    result = TBDYShearCalculator().calculate(_ctx(stirrup_diameter_mm=6.0, stirrup_legs=1))
    statuses = {check.name: check.status for check in result.checks}

    assert statuses["beam_shear_stirrup_diameter_ge_8"] == "FAIL"
    assert statuses["beam_shear_stirrup_legs_ge_2"] == "FAIL"


def test_shear_check_to_core_check_conversion() -> None:
    shear_check = TBDYShearCalculator().calculate(_ctx()).checks[0]
    original_evidence = dict(shear_check.evidence)

    core_check = shear_check_to_core_check(
        beam_id="B175",
        story="+14.50",
        section_name="B60x60",
        check=shear_check,
    )

    assert core_check.id == "B175:shear:beam_shear_ve_le_vr"
    assert core_check.component == "B175"
    assert core_check.check_type == "shear"
    assert core_check.evidence["story"] == "+14.50"
    assert core_check.evidence["section_name"] == "B60x60"
    assert shear_check.evidence == original_evidence


def test_shear_source_guard_has_no_forbidden_imports() -> None:
    source = pathlib.Path("tbdy_engine/design/beams/calculators/shear.py").read_text(encoding="utf-8")
    forbidden = [
        "tbdy_engine.etabs",
        "tbdy_engine.reports",
        "tbdy_engine.adapters",
        "tbdy_engine.runner_v2",
        "tbdy_engine.archx",
        "tbdy_engine.runtime",
        "tbdy_engine.contracts",
        "CheckResult",
        "BeamEvaluationPackage",
        "ReportingFacade",
        "CheckAdapter",
        "read_etabs_table_on_demand",
    ]
    for text in forbidden:
        assert text not in source
def test_spacing_le_8_longitudinal_diameter_passes_for_b175_like_context() -> None:
    result = TBDYShearCalculator().calculate(_ctx())
    checks = {check.name: check for check in result.checks}

    check = checks["beam_shear_spacing_le_8_longitudinal_diameter"]

    assert check.status == "OK"
    assert check.demand == 100.0
    assert check.capacity == 128.0
    assert check.ratio == pytest.approx(100.0 / 128.0)
    assert check.unit == "mm"
    assert check.code_ref == "TBDY 2018 7.4.4.1"
    assert check.evidence["stirrup_spacing_mm"] == 100.0
    assert check.evidence["longitudinal_bar_diameter_mm"] == 16.0
    assert check.evidence["limit_mm"] == 128.0
    assert check.evidence["formula"] == "stirrup_spacing_mm <= 8 * longitudinal_bar_diameter_mm"


def test_spacing_le_8_longitudinal_diameter_fails_when_spacing_exceeds_limit() -> None:
    result = TBDYShearCalculator().calculate(
        _ctx(stirrup_spacing_mm=150.0, longitudinal_bar_diameter_mm=14.0)
    )
    checks = {check.name: check for check in result.checks}

    check = checks["beam_shear_spacing_le_8_longitudinal_diameter"]

    assert check.status == "FAIL"
    assert check.demand == 150.0
    assert check.capacity == 112.0
    assert check.ratio == pytest.approx(150.0 / 112.0)


def test_spacing_le_8_longitudinal_diameter_returns_no_data_when_missing() -> None:
    result = TBDYShearCalculator().calculate(_ctx(longitudinal_bar_diameter_mm=None))
    checks = {check.name: check for check in result.checks}

    check = checks["beam_shear_spacing_le_8_longitudinal_diameter"]

    assert check.status == "NO_DATA"
    assert check.demand == 100.0
    assert check.capacity is None
    assert check.ratio is None
    assert check.unit == "mm"
    assert check.evidence["longitudinal_bar_diameter_mm"] is None
    assert check.evidence["limit_mm"] is None

def test_capacity_shear_demand_matches_hand_calculation() -> None:
    result = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )

    assert isinstance(result, CapacityShearDemandResult)
    assert result.status == "OK"
    assert result.Ln_m == pytest.approx(5.0)
    assert result.Ve_capacity_kN == pytest.approx(158.0)
    assert result.evidence["left_plastic_moment_kNm"] == 180.0
    assert result.evidence["right_plastic_moment_kNm"] == 160.0
    assert result.evidence["Ln_mm"] == 5000.0
    assert result.evidence["Ln_m"] == pytest.approx(5.0)
    assert result.evidence["gravity_shear_kN"] == 90.0
    assert result.evidence["Ve_capacity_kN"] == pytest.approx(158.0)
    assert result.evidence["capacity_design_shear_complete"] is False
    assert result.evidence["ve_capacity_check_against_vr"] is False


def test_capacity_shear_demand_returns_no_data_when_plastic_moment_missing() -> None:
    result = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=None,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )

    assert result.status == "NO_DATA"
    assert result.Ve_capacity_kN is None
    assert result.Ln_m == pytest.approx(5.0)
    assert result.evidence["Ve_capacity_kN"] is None


def test_capacity_shear_demand_returns_no_data_when_span_invalid() -> None:
    result = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=0.0,
        gravity_shear_kN=90.0,
    )

    assert result.status == "NO_DATA"
    assert result.Ln_m is None
    assert result.Ve_capacity_kN is None


def test_capacity_shear_demand_returns_no_data_when_gravity_shear_missing() -> None:
    result = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=None,
    )

    assert result.status == "NO_DATA"
    assert result.Ve_capacity_kN is None
    assert result.evidence["source_of_gravity_shear"] == "explicit gravity_shear_kN input"


def test_capacity_shear_demand_is_deterministic_for_repeated_runs() -> None:
    first = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )

    for _ in range(100):
        current = calculate_capacity_shear_demand(
            left_plastic_moment_kNm=180.0,
            right_plastic_moment_kNm=160.0,
            Ln_mm=5000.0,
            gravity_shear_kN=90.0,
        )
        assert current == first

def test_capacity_design_ve_le_vr_check_passes_hand_calculation() -> None:
    demand = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )
    check = capacity_design_ve_le_vr_check(
        capacity_shear_demand=demand,
        Vr_kN=200.0,
        Vc_kN=80.0,
        Vw_kN=120.0,
        Asw_mm2=157.08,
        fywd_mpa=365.0,
        d_mm=550.0,
        stirrup_spacing_mm=100.0,
    )

    assert check.name == "beam_shear_capacity_design_ve_le_vr"
    assert check.status == "OK"
    assert check.demand == pytest.approx(158.0)
    assert check.capacity == pytest.approx(200.0)
    assert check.ratio == pytest.approx(158.0 / 200.0)
    assert check.unit == "kN"
    assert check.evidence["Ve_capacity_kN"] == pytest.approx(158.0)
    assert check.evidence["Vr_kN"] == pytest.approx(200.0)
    assert check.evidence["formula_capacity_check"] == "Ve_capacity_kN <= Vr_kN"
    assert check.evidence["ve_capacity_check_against_vr"] is True
    assert check.evidence["capacity_design_shear_complete"] is False
    assert check.evidence["capacity_design_vmax_check"] is False


def test_capacity_design_ve_le_vr_check_fails_hand_calculation() -> None:
    demand = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )
    check = capacity_design_ve_le_vr_check(
        capacity_shear_demand=demand,
        Vr_kN=120.0,
        Vc_kN=50.0,
        Vw_kN=70.0,
        Asw_mm2=157.08,
        fywd_mpa=365.0,
        d_mm=550.0,
        stirrup_spacing_mm=100.0,
    )

    assert check.status == "FAIL"
    assert check.demand == pytest.approx(158.0)
    assert check.capacity == pytest.approx(120.0)
    assert check.ratio == pytest.approx(158.0 / 120.0)
    assert check.ratio > 1.0


def test_capacity_design_ve_le_vr_check_returns_no_data_when_demand_missing() -> None:
    demand = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=None,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )
    check = capacity_design_ve_le_vr_check(
        capacity_shear_demand=demand,
        Vr_kN=200.0,
        Vc_kN=80.0,
        Vw_kN=120.0,
        Asw_mm2=157.08,
        fywd_mpa=365.0,
        d_mm=550.0,
        stirrup_spacing_mm=100.0,
    )

    assert check.status == "NO_DATA"
    assert check.demand is None
    assert check.capacity == pytest.approx(200.0)
    assert check.ratio is None


def test_capacity_design_ve_le_vr_check_returns_no_data_when_vr_missing() -> None:
    demand = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )
    check = capacity_design_ve_le_vr_check(
        capacity_shear_demand=demand,
        Vr_kN=None,
        Vc_kN=None,
        Vw_kN=None,
        Asw_mm2=None,
        fywd_mpa=365.0,
        d_mm=550.0,
        stirrup_spacing_mm=100.0,
    )

    assert check.status == "NO_DATA"
    assert check.demand == pytest.approx(158.0)
    assert check.capacity is None
    assert check.ratio is None


def test_capacity_design_ve_le_vr_check_is_deterministic_for_repeated_runs() -> None:
    demand = calculate_capacity_shear_demand(
        left_plastic_moment_kNm=180.0,
        right_plastic_moment_kNm=160.0,
        Ln_mm=5000.0,
        gravity_shear_kN=90.0,
    )
    first = capacity_design_ve_le_vr_check(
        capacity_shear_demand=demand,
        Vr_kN=200.0,
        Vc_kN=80.0,
        Vw_kN=120.0,
        Asw_mm2=157.08,
        fywd_mpa=365.0,
        d_mm=550.0,
        stirrup_spacing_mm=100.0,
    )

    for _ in range(100):
        current = capacity_design_ve_le_vr_check(
            capacity_shear_demand=demand,
            Vr_kN=200.0,
            Vc_kN=80.0,
            Vw_kN=120.0,
            Asw_mm2=157.08,
            fywd_mpa=365.0,
            d_mm=550.0,
            stirrup_spacing_mm=100.0,
        )
        assert current == first

