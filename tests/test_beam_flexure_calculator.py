from __future__ import annotations

import sys
import types
from pathlib import Path

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

import pathlib
from dataclasses import is_dataclass

import pytest

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
        "bottom_selected_area_cm2": 8.0,
        "missing_inputs": (),
        "source": {"origin": "unit_test"},
    }
    values.update(overrides)
    return BeamModelContext(**values)


def test_flexure_calculator_returns_deterministic_ok_result() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())

    assert is_dataclass(FlexureCheck)
    assert is_dataclass(FlexureResult)
    assert FlexureCheck.__dataclass_params__.frozen is True
    assert FlexureResult.__dataclass_params__.frozen is True

    assert result.status == "OK"
    assert result.Md_left_neg_kNm == 108.7
    assert result.Md_mid_pos_kNm == 84.8
    assert result.Md_right_neg_kNm == 92.4
    assert result.required_top_area_cm2 == 8.0
    assert result.provided_top_area_cm2 == 10.0
    assert result.required_bottom_area_cm2 == 6.0
    assert result.provided_bottom_area_cm2 == 8.0
    assert result.top_ratio == pytest.approx(0.8)
    assert result.bottom_ratio == pytest.approx(0.75)
    assert len(result.checks) == 2
    assert all(check.status == "OK" for check in result.checks)


def test_failing_top_area() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_required_area_cm2=12.0, top_selected_area_cm2=10.0)
    )
    checks = {check.name: check for check in result.checks}

    assert result.status == "FAIL"
    assert checks["beam_flexure_top_area_provided_ge_required"].status == "FAIL"


def test_failing_bottom_area() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(bottom_required_area_cm2=9.0, bottom_selected_area_cm2=8.0)
    )
    checks = {check.name: check for check in result.checks}

    assert result.status == "FAIL"
    assert checks["beam_flexure_bottom_area_provided_ge_required"].status == "FAIL"


def test_no_data_behavior() -> None:
    result = TBDYFlexureCalculator().calculate(
        _ctx(top_required_area_cm2=None, bottom_selected_area_cm2=0.0)
    )
    checks = {check.name: check for check in result.checks}

    assert result.status == "NO_DATA"
    assert checks["beam_flexure_top_area_provided_ge_required"].status == "NO_DATA"
    assert checks["beam_flexure_top_area_provided_ge_required"].ratio is None
    assert checks["beam_flexure_bottom_area_provided_ge_required"].status == "NO_DATA"
    assert checks["beam_flexure_bottom_area_provided_ge_required"].ratio is None


def test_evidence_contains_required_values_and_formula() -> None:
    result = TBDYFlexureCalculator().calculate(_ctx())
    checks = {check.name: check for check in result.checks}

    top = checks["beam_flexure_top_area_provided_ge_required"]
    bottom = checks["beam_flexure_bottom_area_provided_ge_required"]

    assert top.evidence["top_required_area_cm2"] == 8.0
    assert top.evidence["top_selected_area_cm2"] == 10.0
    assert top.evidence["formula"] == "top_selected_area_cm2 >= top_required_area_cm2"

    assert bottom.evidence["bottom_required_area_cm2"] == 6.0
    assert bottom.evidence["bottom_selected_area_cm2"] == 8.0
    assert bottom.evidence["formula"] == "bottom_selected_area_cm2 >= bottom_required_area_cm2"


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