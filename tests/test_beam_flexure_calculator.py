from __future__ import annotations

import math
import pathlib
import sys
import types
from dataclasses import is_dataclass
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.context import BeamModelContext
from tbdy_engine.design.beams.calculators.flexure import (
    FlexureCheck,
    FlexureResult,
    TBDYFlexureCalculator,
)
from tbdy_engine.design.beams.core_check import flexure_check_to_core_check


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
        "top_required_area_cm2": 8.0,
        "top_selected_area_cm2": 10.0,
        "bottom_required_area_cm2": 6.0,
        "bottom_selected_area_cm2": 10.0,
        "missing_inputs": (),
        "source": {"origin": "unit_test"},
    }
    values.update(overrides)
    return BeamModelContext(**values)


def _expected_as_required_cm2(*, Md_kNm: float, fyd_mpa: float, fcd_mpa: float, bw_mm: float, d_mm: float) -> float:
    Mu_Nmm = abs(Md_kNm) * 1_000_000.0
    quadratic_a = (fyd_mpa * fyd_mpa) / (1.7 * fcd_mpa * bw_mm)
    quadratic_b = fyd_mpa * d_mm
    discriminant = quadratic_b * quadratic_b - 4.0 * quadratic_a * Mu_Nmm
    As_required_mm2 = (quadratic_b - math.sqrt(discriminant)) / (2.0 * quadratic_a)
    return As_required_mm2 / 100.0


def _checks(result: FlexureResult) -> dict[str, FlexureCheck]:
    return {check.name: check for check in result.checks}


def test_flexure_calculator_returns_deterministic_ok_result() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())

    assert is_dataclass(FlexureCheck)
    assert is_dataclass(FlexureResult)
    assert FlexureCheck.__dataclass_params__.frozen is True
    assert FlexureResult.__dataclass_params__.frozen is True

    expected_top = _expected_as_required_cm2(
        Md_kNm=108.7,
        fyd_mpa=365.0,
        fcd_mpa=20.0,
        bw_mm=600.0,
        d_mm=550.0,
    )
    expected_bottom = _expected_as_required_cm2(
        Md_kNm=84.8,
        fyd_mpa=365.0,
        fcd_mpa=20.0,
        bw_mm=600.0,
        d_mm=550.0,
    )

    assert result.status == "OK"
    assert len(result.checks) == 6
    assert [check.name for check in result.checks] == [
        "beam_flexure_top_area_provided_ge_required",
        "beam_flexure_bottom_area_provided_ge_required",
        "beam_flexure_top_rho_ge_rho_min",
        "beam_flexure_bottom_rho_ge_rho_min",
        "beam_flexure_top_rho_le_rho_max",
        "beam_flexure_bottom_rho_le_rho_max",
    ]
    assert result.top_design_moment_kNm == 108.7
    assert result.bottom_design_moment_kNm == 84.8
    assert result.required_top_area_cm2 == pytest.approx(expected_top)
    assert result.required_bottom_area_cm2 == pytest.approx(expected_bottom)
    assert result.top_required_area_source == "moment_derived"
    assert result.bottom_required_area_source == "moment_derived"


def test_required_rebar_area_from_moment_matches_independent_hand_calculation() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(
            Md_left_neg_kNm=120.0,
            Md_right_neg_kNm=0.0,
            Md_mid_pos_kNm=120.0,
            top_required_area_cm2=None,
            bottom_required_area_cm2=None,
            top_selected_area_cm2=10.0,
            bottom_selected_area_cm2=10.0,
            bw_mm=600.0,
            d_mm=550.0,
            fcd_mpa=20.0,
            fyd_mpa=365.0,
        )
    )

    expected = _expected_as_required_cm2(
        Md_kNm=120.0,
        fyd_mpa=365.0,
        fcd_mpa=20.0,
        bw_mm=600.0,
        d_mm=550.0,
    )

    assert result.top_required_area_from_moment_cm2 == pytest.approx(expected)
    assert result.bottom_required_area_from_moment_cm2 == pytest.approx(expected)
    assert result.required_top_area_cm2 == pytest.approx(expected)
    assert result.required_bottom_area_cm2 == pytest.approx(expected)

    top_check = _checks(result)["beam_flexure_top_area_provided_ge_required"]

    assert top_check.evidence["Md_kNm"] == 120.0
    assert top_check.evidence["Mu_Nmm"] == 120.0 * 1_000_000.0
    assert top_check.evidence["As_required_mm2"] == pytest.approx(expected * 100.0)
    assert top_check.evidence["As_required_cm2"] == pytest.approx(expected)
    assert top_check.evidence["required_area_source"] == "moment_derived"


def test_rho_min_hand_calculation_for_top_and_bottom() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())

    expected_rho_min = max(0.8 * 1.27 / 365.0, 0.0015)
    expected_top_rho = (10.0 * 100.0) / (600.0 * 550.0)
    expected_bottom_rho = (10.0 * 100.0) / (600.0 * 550.0)

    assert result.rho_min == pytest.approx(expected_rho_min)
    assert result.top_rho == pytest.approx(expected_top_rho)
    assert result.bottom_rho == pytest.approx(expected_bottom_rho)
    assert result.top_rho_min_ratio == pytest.approx(expected_rho_min / expected_top_rho)
    assert result.bottom_rho_min_ratio == pytest.approx(expected_rho_min / expected_bottom_rho)
    assert result.rho_max == pytest.approx(0.04)
    assert result.top_rho_max_ratio == pytest.approx(expected_top_rho / 0.04)
    assert result.bottom_rho_max_ratio == pytest.approx(expected_bottom_rho / 0.04)
    checks = _checks(result)
    top = checks["beam_flexure_top_rho_ge_rho_min"]
    bottom = checks["beam_flexure_bottom_rho_ge_rho_min"]

    assert top.status == "OK"
    assert top.demand == pytest.approx(expected_rho_min)
    assert top.capacity == pytest.approx(expected_top_rho)
    assert top.ratio == pytest.approx(expected_rho_min / expected_top_rho)
    assert top.evidence["selected_area_cm2"] == 10.0
    assert top.evidence["selected_area_mm2"] == 1000.0
    assert top.evidence["rho"] == pytest.approx(expected_top_rho)
    assert top.evidence["rho_min"] == pytest.approx(expected_rho_min)

    assert bottom.status == "OK"
    assert bottom.capacity == pytest.approx(expected_bottom_rho)


def test_rho_min_fails_when_selected_area_is_too_small() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_selected_area_cm2=2.0, bottom_selected_area_cm2=2.0)
    )
    checks = _checks(result)

    assert result.status == "FAIL"
    assert checks["beam_flexure_top_rho_ge_rho_min"].status == "FAIL"
    assert checks["beam_flexure_bottom_rho_ge_rho_min"].status == "FAIL"


def test_rho_min_no_data_when_selected_area_or_materials_invalid() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_selected_area_cm2=None, bottom_selected_area_cm2=0.0)
    )
    checks = _checks(result)

    assert result.status == "NO_DATA"
    assert result.top_rho is None
    assert result.bottom_rho is None
    assert checks["beam_flexure_top_rho_ge_rho_min"].status == "NO_DATA"
    assert checks["beam_flexure_bottom_rho_ge_rho_min"].status == "NO_DATA"


def test_rho_max_hand_calculation_for_top_and_bottom() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())

    expected_top_rho = (10.0 * 100.0) / (600.0 * 550.0)
    expected_bottom_rho = (10.0 * 100.0) / (600.0 * 550.0)
    expected_rho_max = 0.04

    assert result.rho_max == pytest.approx(expected_rho_max)
    assert result.top_rho == pytest.approx(expected_top_rho)
    assert result.bottom_rho == pytest.approx(expected_bottom_rho)
    assert result.top_rho_max_ratio == pytest.approx(expected_top_rho / expected_rho_max)
    assert result.bottom_rho_max_ratio == pytest.approx(expected_bottom_rho / expected_rho_max)

    checks = _checks(result)
    top = checks["beam_flexure_top_rho_le_rho_max"]
    bottom = checks["beam_flexure_bottom_rho_le_rho_max"]

    assert top.status == "OK"
    assert top.demand == pytest.approx(expected_top_rho)
    assert top.capacity == pytest.approx(expected_rho_max)
    assert top.ratio == pytest.approx(expected_top_rho / expected_rho_max)
    assert top.evidence["selected_area_cm2"] == 10.0
    assert top.evidence["selected_area_mm2"] == 1000.0
    assert top.evidence["rho"] == pytest.approx(expected_top_rho)
    assert top.evidence["rho_max"] == pytest.approx(expected_rho_max)

    assert bottom.status == "OK"
    assert bottom.demand == pytest.approx(expected_bottom_rho)
    assert bottom.capacity == pytest.approx(expected_rho_max)


def test_rho_max_fails_when_selected_area_is_too_large() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_selected_area_cm2=140.0, bottom_selected_area_cm2=140.0)
    )
    checks = _checks(result)

    assert result.status == "FAIL"
    assert checks["beam_flexure_top_rho_le_rho_max"].status == "FAIL"
    assert checks["beam_flexure_bottom_rho_le_rho_max"].status == "FAIL"

def test_context_required_area_is_used_when_moment_required_is_not_available() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(Md_left_neg_kNm=0.0, Md_right_neg_kNm=0.0, Md_mid_pos_kNm=0.0)
    )

    assert result.required_top_area_cm2 == 8.0
    assert result.required_bottom_area_cm2 == 6.0
    assert result.top_required_area_from_moment_cm2 is None
    assert result.bottom_required_area_from_moment_cm2 is None
    assert result.top_required_area_source == "context_input"
    assert result.bottom_required_area_source == "context_input"


def test_no_data_when_no_moment_and_no_context_required_area() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(
            Md_left_neg_kNm=0.0,
            Md_right_neg_kNm=0.0,
            Md_mid_pos_kNm=0.0,
            top_required_area_cm2=None,
            bottom_required_area_cm2=None,
        )
    )

    assert result.status == "NO_DATA"
    assert result.required_top_area_cm2 is None
    assert result.required_bottom_area_cm2 is None
    assert result.top_required_area_source == "no_data"
    assert result.bottom_required_area_source == "no_data"


def test_stress_block_values_are_computed_for_top_and_bottom_rebar() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())

    assert result.beta1 == pytest.approx(0.85)

    expected_top_a = 10.0 * 100.0 * 365.0 / (0.85 * 20.0 * 600.0)
    expected_bottom_a = 10.0 * 100.0 * 365.0 / (0.85 * 20.0 * 600.0)

    assert result.top_stress_block_a_mm == pytest.approx(expected_top_a)
    assert result.top_neutral_axis_c_mm == pytest.approx(expected_top_a / 0.85)
    assert result.top_compression_block_kN == pytest.approx(
        0.85 * 20.0 * 600.0 * expected_top_a / 1000.0
    )

    assert result.bottom_stress_block_a_mm == pytest.approx(expected_bottom_a)
    assert result.bottom_neutral_axis_c_mm == pytest.approx(expected_bottom_a / 0.85)
    assert result.bottom_compression_block_kN == pytest.approx(
        0.85 * 20.0 * 600.0 * expected_bottom_a / 1000.0
    )


def test_stress_block_evidence_is_available_on_flexure_checks() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())
    checks = _checks(result)

    top = checks["beam_flexure_top_area_provided_ge_required"]
    bottom = checks["beam_flexure_bottom_area_provided_ge_required"]

    assert top.evidence["beta1"] == pytest.approx(0.85)
    assert top.evidence["stress_block_a_mm"] == pytest.approx(result.top_stress_block_a_mm)
    assert top.evidence["neutral_axis_c_mm"] == pytest.approx(result.top_neutral_axis_c_mm)
    assert top.evidence["compression_block_kN"] == pytest.approx(result.top_compression_block_kN)

    assert bottom.evidence["beta1"] == pytest.approx(0.85)
    assert bottom.evidence["stress_block_a_mm"] == pytest.approx(result.bottom_stress_block_a_mm)
    assert bottom.evidence["neutral_axis_c_mm"] == pytest.approx(result.bottom_neutral_axis_c_mm)
    assert bottom.evidence["compression_block_kN"] == pytest.approx(result.bottom_compression_block_kN)


def test_stress_block_and_required_area_are_deterministic_for_repeated_runs() -> None:
    ctx = _ctx()
    first = TBDYFlexureCalculator().calculate(ctx)

    for _ in range(100):
        current = TBDYFlexureCalculator().calculate(ctx)
        assert current == first


def test_stress_block_returns_no_data_values_when_selected_rebar_missing() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_selected_area_cm2=None, bottom_selected_area_cm2=None)
    )

    assert result.status == "NO_DATA"
    assert result.top_stress_block_a_mm is None
    assert result.top_neutral_axis_c_mm is None
    assert result.top_compression_block_kN is None
    assert result.bottom_stress_block_a_mm is None
    assert result.bottom_neutral_axis_c_mm is None
    assert result.bottom_compression_block_kN is None


def test_failing_top_area() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(Md_left_neg_kNm=500.0, Md_right_neg_kNm=0.0, top_selected_area_cm2=2.0)
    )
    checks = _checks(result)

    assert result.status == "FAIL"
    assert checks["beam_flexure_top_area_provided_ge_required"].status == "FAIL"


def test_failing_bottom_area() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(Md_mid_pos_kNm=500.0, bottom_selected_area_cm2=2.0)
    )
    checks = _checks(result)

    assert result.status == "FAIL"
    assert checks["beam_flexure_bottom_area_provided_ge_required"].status == "FAIL"


def test_no_data_behavior() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_selected_area_cm2=None, bottom_selected_area_cm2=0.0)
    )
    checks = _checks(result)

    assert result.status == "NO_DATA"
    assert checks["beam_flexure_top_area_provided_ge_required"].status == "NO_DATA"
    assert checks["beam_flexure_top_area_provided_ge_required"].ratio is None
    assert checks["beam_flexure_bottom_area_provided_ge_required"].status == "NO_DATA"
    assert checks["beam_flexure_bottom_area_provided_ge_required"].ratio is None


def test_evidence_contains_required_values_and_formula() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())
    checks = _checks(result)

    top = checks["beam_flexure_top_area_provided_ge_required"]
    bottom = checks["beam_flexure_bottom_area_provided_ge_required"]

    assert top.evidence["top_required_area_cm2"] == pytest.approx(result.required_top_area_cm2)
    assert top.evidence["top_selected_area_cm2"] == 10.0
    assert top.evidence["formula"] == "provided_area_cm2 >= As_required_cm2"

    assert bottom.evidence["bottom_required_area_cm2"] == pytest.approx(result.required_bottom_area_cm2)
    assert bottom.evidence["bottom_selected_area_cm2"] == 10.0
    assert bottom.evidence["formula"] == "provided_area_cm2 >= As_required_cm2"


def test_flexure_check_to_core_check_conversion() -> None:
    flexure_check = TBDYFlexureCalculator().calculate(_ctx()).checks[0]
    original_evidence = dict(flexure_check.evidence)

    core_check = flexure_check_to_core_check(
        beam_id="B175",
        story="+14.50",
        section_name="B60x60",
        check=flexure_check,
    )

    assert core_check.id == "B175:flexure:beam_flexure_top_area_provided_ge_required"
    assert core_check.component == "B175"
    assert core_check.check_type == "flexure"
    assert core_check.evidence["story"] == "+14.50"
    assert core_check.evidence["section_name"] == "B60x60"
    assert core_check.evidence["stress_block_a_mm"] == pytest.approx(
        original_evidence["stress_block_a_mm"]
    )
    assert core_check.evidence["As_required_cm2"] == pytest.approx(
        original_evidence["As_required_cm2"]
    )
    assert flexure_check.evidence == original_evidence


def test_flexure_source_guard_has_no_forbidden_imports() -> None:
    source = pathlib.Path("tbdy_engine/design/beams/calculators/flexure.py").read_text(encoding="utf-8")
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