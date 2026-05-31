from __future__ import annotations

import pathlib
import sys
import types
from pathlib import Path

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from dataclasses import is_dataclass

from tbdy_engine.design.beams.beam_core import BeamCoreResult, evaluate_beam_core


def _canonical_input(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
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
    data.update(overrides)
    return data


def test_valid_complete_canonical_input_returns_ok_result() -> None:
    result = evaluate_beam_core(_canonical_input())

    assert is_dataclass(BeamCoreResult)
    assert BeamCoreResult.__dataclass_params__.frozen is True
    assert result.status == "OK"
    assert result.validation_errors == ()
    assert result.geometry is not None
    assert result.shear is not None
    assert result.flexure is not None
    assert len(result.geometry.checks) == 4
    assert len(result.shear.checks) == 8
    assert len(result.flexure.checks) == 6
    assert len(result.core_checks) == 18


def test_core_check_ordering_is_deterministic() -> None:
    result = evaluate_beam_core(_canonical_input())

    assert [check.check_type for check in result.core_checks[:4]] == ["geometry"] * 4
    assert [check.check_type for check in result.core_checks[4:12]] == ["shear"] * 8
    assert [check.check_type for check in result.core_checks[12:]] == ["flexure"] * 6


def test_invalid_input_does_not_run_calculators() -> None:
    data = _canonical_input()
    data.pop("bw_mm")
    data["fcd_mpa"] = 0.0

    result = evaluate_beam_core(data)

    assert result.status == "INVALID_INPUT"
    assert result.validation_errors != ()
    assert "bw_mm" in result.validation_errors
    assert "fcd_mpa" in result.validation_errors
    assert result.geometry is None
    assert result.shear is None
    assert result.flexure is None
    assert result.core_checks == ()


def test_flexure_no_data_propagates_to_beam_core_result() -> None:
    result = evaluate_beam_core(
        _canonical_input(
            top_required_area_cm2=None,
            top_selected_area_cm2=None,
            bottom_required_area_cm2=None,
            bottom_selected_area_cm2=None,
        )
    )

    assert result.status == "NO_DATA"
    assert result.geometry is not None
    assert result.shear is not None
    assert result.flexure is not None
    assert result.flexure.status == "NO_DATA"
    assert len(result.core_checks) == 18
    assert [check.status for check in result.core_checks[-6:]] == ["NO_DATA", "NO_DATA", "NO_DATA", "NO_DATA", "NO_DATA", "NO_DATA"]


def test_failing_shear_propagates_fail() -> None:
    result = evaluate_beam_core(_canonical_input(Ve_left_kN=1000.0))

    assert result.status == "FAIL"
    assert result.shear is not None
    assert result.shear.status == "FAIL"


def test_evidence_and_identity_are_preserved_for_all_core_checks() -> None:
    result = evaluate_beam_core(_canonical_input())

    assert result.core_checks
    for check in result.core_checks:
        assert check.component == "B175"
        assert check.id.startswith("B175:")
        assert check.evidence["story"] == "+14.50"
        assert check.evidence["section_name"] == "B60x60"


def test_beam_core_source_guard_has_no_forbidden_imports() -> None:
    source = pathlib.Path("tbdy_engine/design/beams/beam_core.py").read_text(encoding="utf-8")
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

EXPECTED_N6_FLEXURE_CHECK_NAMES = (
    "beam_flexure_top_area_provided_ge_required",
    "beam_flexure_bottom_area_provided_ge_required",
    "beam_flexure_top_rho_ge_rho_min",
    "beam_flexure_bottom_rho_ge_rho_min",
    "beam_flexure_top_rho_le_rho_max",
    "beam_flexure_bottom_rho_le_rho_max",
)
def test_n6_beam_core_aggregates_all_six_flexure_checks() -> None:
    result = evaluate_beam_core(_canonical_input())

    assert result.status == "OK"
    assert result.flexure is not None
    assert result.flexure.status == "OK"

    flexure_names = tuple(check.name for check in result.flexure.checks)
    assert flexure_names == EXPECTED_N6_FLEXURE_CHECK_NAMES

    core_flexure_names = tuple(
        check.name for check in result.core_checks if check.check_type == "flexure"
    )
    assert core_flexure_names == EXPECTED_N6_FLEXURE_CHECK_NAMES

    assert len(result.flexure.checks) == 6
    assert len(core_flexure_names) == 6
    assert len(result.core_checks) == 18

    area_check = next(
        check for check in result.core_checks
        if check.name == "beam_flexure_top_area_provided_ge_required"
    )
    rho_min_check = next(
        check for check in result.core_checks
        if check.name == "beam_flexure_top_rho_ge_rho_min"
    )
    rho_max_check = next(
        check for check in result.core_checks
        if check.name == "beam_flexure_top_rho_le_rho_max"
    )

    assert area_check.evidence["consolidated_flexure_evidence"] is True
    assert area_check.evidence["required_area_source"] == "moment_derived"
    assert "required_area_cm2" in area_check.evidence
    assert "provided_area_cm2" in area_check.evidence
    assert "rho" in area_check.evidence
    assert "rho_min" in area_check.evidence
    assert "rho_max" in area_check.evidence

    assert rho_min_check.evidence["consolidated_flexure_evidence"] is True
    assert rho_min_check.evidence["rho_min"] == result.flexure.rho_min
    assert rho_min_check.evidence["formula"].startswith("rho = selected_area_mm2")

    assert rho_max_check.evidence["consolidated_flexure_evidence"] is True
    assert rho_max_check.evidence["rho_max"] == result.flexure.rho_max
    assert rho_max_check.evidence["formula"].startswith("rho = selected_area_mm2")