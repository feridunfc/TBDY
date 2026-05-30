from __future__ import annotations

import math
import pathlib
from dataclasses import is_dataclass

import pytest

from tbdy_engine.design.beams import BeamModelContext
from tbdy_engine.design.beams.calculators.shear import (
    ShearCheck,
    ShearResult,
    TBDYShearCalculator,
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