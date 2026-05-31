from __future__ import annotations

import pathlib
import sys
import types
from pathlib import Path

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.beam_core import evaluate_beam_core
from tbdy_engine.design.beams.core_package_adapter import (
    beam_core_result_to_evaluation_packages,
    core_check_to_beam_check_evaluation,
)


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
        "source": {"origin": "unit_test"},
    }
    data.update(overrides)
    return data


def test_valid_ok_beam_core_result_converts_to_one_package() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "OK"
    assert len(packages) == 1

    package = packages[0]
    assert package.component == "B175"
    assert package.story == "+14.50"
    assert package.section == "B60x60"
    assert package.messages == ()
    assert len(package.checks) == len(result.core_checks)

    assert [check.check_type for check in package.checks] == [
        check.name for check in result.core_checks
    ]
    assert package.checks[0].check_type.startswith("beam_geometry_")
    assert any(check.check_type.startswith("beam_shear_") for check in package.checks)
    assert any(check.check_type.startswith("beam_flexure_") for check in package.checks)

    assert package.evidence["story"] == "+14.50"
    assert package.evidence["section_name"] == "B60x60"
    assert package.evidence["status"] == "OK"
    assert len(package.evidence["core_check_evidence_by_id"]) == len(result.core_checks)


def test_core_check_fields_map_to_beam_check_evaluation() -> None:
    result = evaluate_beam_core(_canonical_input())
    shear_core_check = next(
        check for check in result.core_checks if check.name == "beam_shear_ve_le_vr"
    )

    beam_check = core_check_to_beam_check_evaluation(shear_core_check)

    assert beam_check.check_type == shear_core_check.name
    assert beam_check.status == shear_core_check.status
    assert beam_check.demand == shear_core_check.demand
    assert beam_check.capacity == shear_core_check.capacity
    assert beam_check.ratio == shear_core_check.ratio
    assert beam_check.unit == shear_core_check.unit
    assert beam_check.code_ref == shear_core_check.code_ref
    assert beam_check.messages == (shear_core_check.message,)


def test_core_check_evidence_is_preserved_at_package_level() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    package = packages[0]
    first_core_check = result.core_checks[0]
    evidence_by_id = package.evidence["core_check_evidence_by_id"]

    assert evidence_by_id[first_core_check.id] == first_core_check.evidence
    assert evidence_by_id[first_core_check.id] is not first_core_check.evidence


def test_fail_result_adds_package_message_and_failed_check() -> None:
    result = evaluate_beam_core(_canonical_input(Ve_left_kN=1000.0))
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "FAIL"
    package = packages[0]
    assert "Beam core result contains failing checks." in package.messages
    assert any(check.status == "FAIL" for check in package.checks)


def test_no_data_result_adds_package_message_and_no_data_checks() -> None:
    result = evaluate_beam_core(
        _canonical_input(
            top_required_area_cm2=None,
            top_selected_area_cm2=None,
            bottom_required_area_cm2=None,
            bottom_selected_area_cm2=None,
        )
    )
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "NO_DATA"
    package = packages[0]
    assert "Beam core result contains NO_DATA checks." in package.messages

    flexure_checks = [
        check for check in package.checks if check.check_type.startswith("beam_flexure_")
    ]
    assert flexure_checks
    statuses = {check.check_type: check.status for check in flexure_checks}
    assert statuses["beam_flexure_top_area_provided_ge_required"] == "NO_DATA"
    assert statuses["beam_flexure_bottom_area_provided_ge_required"] == "NO_DATA"
    assert statuses["beam_flexure_top_rho_ge_rho_min"] == "NO_DATA"
    assert statuses["beam_flexure_bottom_rho_ge_rho_min"] == "NO_DATA"
    assert statuses["beam_flexure_top_rho_le_rho_max"] == "NO_DATA"
    assert statuses["beam_flexure_bottom_rho_le_rho_max"] == "NO_DATA"
    assert statuses["beam_flexure_top_bar_selection"] == "OK"
    assert statuses["beam_flexure_bottom_bar_selection"] == "OK"


def test_invalid_input_creates_explicit_input_failure_package() -> None:
    data = _canonical_input()
    data.pop("bw_mm")
    data["fcd_mpa"] = 0.0

    result = evaluate_beam_core(data)
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "INVALID_INPUT"
    assert len(packages) == 1

    package = packages[0]
    assert package.component == "B175"
    assert len(package.checks) == 1
    assert package.evidence["validation_errors"] == result.validation_errors
    assert "bw_mm" in package.evidence["validation_errors"]
    assert "fcd_mpa" in package.evidence["validation_errors"]

    check = package.checks[0]
    assert check.check_type == "beam_core_input"
    assert check.status in ("NO_DATA", "ERROR")
    assert "bw_mm" in check.messages
    assert "fcd_mpa" in check.messages


def test_conversion_does_not_mutate_core_check_evidence() -> None:
    result = evaluate_beam_core(_canonical_input())
    core_check = result.core_checks[0]
    original_evidence = dict(core_check.evidence)

    beam_check = core_check_to_beam_check_evaluation(core_check)
    packages = beam_core_result_to_evaluation_packages(result)

    assert core_check.evidence == original_evidence
    assert beam_check.check_type == core_check.name
    assert packages[0].evidence["core_check_evidence_by_id"][core_check.id] == original_evidence


def test_core_package_adapter_source_guard_has_no_forbidden_imports() -> None:
    source = pathlib.Path("tbdy_engine/design/beams/core_package_adapter.py").read_text(encoding="utf-8")
    forbidden = [
        "tbdy_engine.etabs",
        "tbdy_engine.reports",
        "tbdy_engine.adapters",
        "tbdy_engine.runner_v2",
        "tbdy_engine.archx",
        "tbdy_engine.runtime",
        "tbdy_engine.contracts",
        "CheckResult",
        "CheckAdapter",
        "ReportingFacade",
        "read_etabs_table_on_demand",
    ]
    for text in forbidden:
        assert text not in source

EXPECTED_O1_FLEXURE_CHECK_NAMES = (
    "beam_flexure_top_area_provided_ge_required",
    "beam_flexure_bottom_area_provided_ge_required",
    "beam_flexure_top_rho_ge_rho_min",
    "beam_flexure_bottom_rho_ge_rho_min",
    "beam_flexure_top_rho_le_rho_max",
    "beam_flexure_bottom_rho_le_rho_max",
    "beam_flexure_top_bar_selection",
    "beam_flexure_bottom_bar_selection",
    "beam_flexure_top_plastic_moment_available",
    "beam_flexure_bottom_plastic_moment_available",
)

def test_n6_package_adapter_preserves_all_six_flexure_checks() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "OK"
    assert len(packages) == 1

    package = packages[0]
    package_flexure_names = tuple(
        check.check_type for check in package.checks
        if check.check_type.startswith("beam_flexure_")
    )
    assert package_flexure_names == EXPECTED_O1_FLEXURE_CHECK_NAMES

    evidence_by_id = package.evidence["core_check_evidence_by_id"]

    for name in EXPECTED_O1_FLEXURE_CHECK_NAMES:
        check_id = f"B175:flexure:{name}"
        assert check_id in evidence_by_id
        assert evidence_by_id[check_id]["consolidated_flexure_evidence"] is True

    top_area_id = "B175:flexure:beam_flexure_top_area_provided_ge_required"
    assert evidence_by_id[top_area_id]["required_area_source"] == "moment_derived"
    assert "required_area_cm2" in evidence_by_id[top_area_id]
    assert "provided_area_cm2" in evidence_by_id[top_area_id]
    assert "rho_min_status" in evidence_by_id[top_area_id]
    assert "rho_max_status" in evidence_by_id[top_area_id]

def test_n7_package_adapter_preserves_bar_selection_evidence() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    package = packages[0]
    flexure_names = tuple(
        check.check_type for check in package.checks
        if check.check_type.startswith("beam_flexure_")
    )

    assert flexure_names == EXPECTED_O1_FLEXURE_CHECK_NAMES

    evidence_by_id = package.evidence["core_check_evidence_by_id"]
    top_id = "B175:flexure:beam_flexure_top_bar_selection"
    bottom_id = "B175:flexure:beam_flexure_bottom_bar_selection"

    assert evidence_by_id[top_id]["selected_bar_area_cm2"] == result.flexure.top_selected_bar_area_cm2
    assert evidence_by_id[bottom_id]["selected_bar_area_cm2"] == result.flexure.bottom_selected_bar_area_cm2
    assert evidence_by_id[top_id]["prior_check_statuses"]["area_status"] == "OK"

def test_o1_package_adapter_preserves_plastic_moment_evidence() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    package = packages[0]
    flexure_names = tuple(
        check.check_type for check in package.checks
        if check.check_type.startswith("beam_flexure_")
    )
    assert flexure_names == EXPECTED_O1_FLEXURE_CHECK_NAMES

    evidence_by_id = package.evidence["core_check_evidence_by_id"]
    top_id = "B175:flexure:beam_flexure_top_plastic_moment_available"
    assert evidence_by_id[top_id]["plastic_moment_kNm"] == result.flexure.top_plastic_moment_kNm
    assert evidence_by_id[top_id]["source_of_area"] == "top_selected_area_cm2"

def test_o4_package_adapter_preserves_capacity_design_shear_check() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    assert len(packages) == 1
    package = packages[0]

    package_checks = {
        check.check_type: check
        for check in package.checks
    }

    assert "beam_shear_capacity_design_ve_le_vr" in package_checks
    assert "beam_shear_ve_le_vr" in package_checks
    assert "beam_flexure_top_plastic_moment_available" in package_checks
    assert "beam_flexure_bottom_plastic_moment_available" in package_checks

    core_check = next(
        check for check in result.core_checks
        if check.name == "beam_shear_capacity_design_ve_le_vr"
    )
    package_check = package_checks["beam_shear_capacity_design_ve_le_vr"]

    assert package_check.status == core_check.status
    assert package_check.demand == core_check.demand
    assert package_check.capacity == core_check.capacity
    assert package_check.ratio == core_check.ratio
    assert package_check.unit == core_check.unit
    assert package_check.code_ref == core_check.code_ref

    evidence_by_id = package.evidence["core_check_evidence_by_id"]
    assert evidence_by_id[core_check.id]["Ve_capacity_kN"] == core_check.evidence["Ve_capacity_kN"]
    assert evidence_by_id[core_check.id]["formula_capacity_check"] == "Ve_capacity_kN <= Vr_kN"
