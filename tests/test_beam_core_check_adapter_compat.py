from __future__ import annotations

import dataclasses
import inspect
import pathlib
import sys
import types
from pathlib import Path
from typing import Iterable

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.design.beams.beam_core import evaluate_beam_core
from tbdy_engine.design.beams.core_package_adapter import (
    beam_core_result_to_evaluation_packages,
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


def _adapt_packages(packages: object) -> tuple[object, ...]:
    adapter = CheckAdapter()

    candidates = (
        "adapt",
        "convert",
        "run",
        "to_check_results",
        "from_evaluation_packages",
        "convert_packages",
        "adapt_packages",
    )

    # Existing CheckAdapter.adapt expects one BeamEvaluationPackage.
    # Try the single package first; then broader payloads only if needed.
    payloads = (
        packages[0],  # type: ignore[index]
        packages,
        list(packages),  # type: ignore[arg-type]
        tuple(packages),  # type: ignore[arg-type]
        packages[0].checks,  # type: ignore[index]
    )

    attempts: list[str] = []
    for name in candidates:
        method = getattr(adapter, name, None)
        if method is None or not callable(method):
            continue

        for payload in payloads:
            try:
                output = method(payload)
            except (TypeError, ValueError) as exc:
                attempts.append(f"{name}({type(payload).__name__}): {exc}")
                continue

            return _normalize_adapter_output(output)

    callable_methods = [
        name
        for name, value in inspect.getmembers(adapter)
        if callable(value) and not name.startswith("_")
    ]
    raise AssertionError(
        "Could not call existing CheckAdapter API. "
        f"Callable methods={callable_methods}; attempts={attempts}"
    )


def _normalize_adapter_output(output: object) -> tuple[object, ...]:
    if output is None:
        return ()

    if isinstance(output, tuple):
        return output

    if isinstance(output, list):
        return tuple(output)

    for attr in ("check_results", "checks", "results"):
        value = getattr(output, attr, None)
        if value is not None:
            return _normalize_adapter_output(value)

    if isinstance(output, Iterable) and not isinstance(output, (str, bytes, dict)):
        return tuple(output)

    return (output,)


def _check_field(result: object, name: str) -> object:
    assert hasattr(result, name), f"CheckResult missing field: {name}"
    return getattr(result, name)


def _assert_canonical_check_result(result: object) -> None:
    required = (
        "check_type",
        "component",
        "status",
        "demand",
        "capacity",
        "ratio",
    )
    for field in required:
        _check_field(result, field)

    forbidden = (
        "report_metadata",
        "runtime_bridge",
        "report_contract",
        "evaluation_errors",
        "evaluation_skipped",
        "execution_order",
        "cache_stats",
        "coverage",
        "distributions",
        "json_snapshot",
        "excel_snapshot",
        "action_summary",
    )
    for field in forbidden:
        assert not hasattr(result, field), f"Forbidden CheckResult field present: {field}"

    if dataclasses.is_dataclass(result):
        field_names = {field.name for field in dataclasses.fields(result)}
        assert field_names.isdisjoint(set(forbidden))


def test_ok_beam_core_package_is_accepted_by_existing_check_adapter() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "OK"
    assert len(packages) == 1

    package = packages[0]
    package_check_types = [check.check_type for check in package.checks]
    assert any(name.startswith("beam_geometry_") for name in package_check_types)
    assert any(name.startswith("beam_shear_") for name in package_check_types)
    assert any(name.startswith("beam_flexure_") for name in package_check_types)

    check_results = _adapt_packages(packages)

    assert check_results
    assert len(check_results) == len(package.checks)

    result_check_types = [_check_field(check, "check_type") for check in check_results]
    assert any(str(name).startswith("beam_geometry_") for name in result_check_types)
    assert any(str(name).startswith("beam_shear_") for name in result_check_types)
    assert any(str(name).startswith("beam_flexure_") for name in result_check_types)

    for check in check_results:
        _assert_canonical_check_result(check)
        assert _check_field(check, "status") in {"OK", "FAIL", "NO_DATA", "ERROR"}


def test_fail_status_propagates_through_existing_check_adapter() -> None:
    result = evaluate_beam_core(_canonical_input(Ve_left_kN=1000.0))
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "FAIL"
    assert any(check.status == "FAIL" for check in packages[0].checks)

    check_results = _adapt_packages(packages)

    assert any(_check_field(check, "status") == "FAIL" for check in check_results)


def test_no_data_status_propagates_through_existing_check_adapter() -> None:
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
    assert any(
        check.check_type.startswith("beam_flexure_") and check.status == "NO_DATA"
        for check in packages[0].checks
    )

    check_results = _adapt_packages(packages)

    assert any(_check_field(check, "status") == "NO_DATA" for check in check_results)


def test_invalid_input_package_converts_to_canonical_check_result() -> None:
    data = _canonical_input()
    data.pop("bw_mm")
    data["fcd_mpa"] = 0.0

    result = evaluate_beam_core(data)
    packages = beam_core_result_to_evaluation_packages(result)

    assert result.status == "INVALID_INPUT"
    assert len(packages) == 1
    assert len(packages[0].checks) == 1
    assert packages[0].checks[0].check_type == "beam_core_input"
    assert packages[0].checks[0].status in {"NO_DATA", "ERROR"}
    assert packages[0].evidence["validation_errors"] == result.validation_errors

    check_results = _adapt_packages(packages)

    assert len(check_results) == 1
    check = check_results[0]
    _assert_canonical_check_result(check)
    assert _check_field(check, "check_type") == "beam_core_input"
    assert _check_field(check, "status") in {"NO_DATA", "ERROR"}
    assert not any(
        str(_check_field(item, "check_type")).startswith(("beam_geometry_", "beam_shear_", "beam_flexure_"))
        for item in check_results
    )


def test_sprint_k_source_guard_has_no_report_runner_etabs_dependencies() -> None:
    paths = (
        pathlib.Path("tests/test_beam_core_check_adapter_compat.py"),
        pathlib.Path("tbdy_engine/design/beams/core_package_adapter.py"),
    )

    forbidden = (
        "tbdy_engine." + "reports",
        "Reporting" + "Facade",
        "JSON" + "Reporter",
        "Excel" + "Reporter",
        "tbdy_engine." + "runner_v2",
        "TBDY" + "EngineV2",
        "tbdy_engine." + "etabs",
        "read_etabs_" + "table_on_demand",
        "tbdy_engine." + "archx",
        "tbdy_engine." + "runtime",
        "sched" + "uler",
        "D" + "AG",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
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
def test_n6_check_adapter_outputs_all_six_flexure_check_results() -> None:
    result = evaluate_beam_core(_canonical_input())
    packages = beam_core_result_to_evaluation_packages(result)
    check_results = _adapt_packages(packages)

    flexure_check_types = tuple(
        str(_check_field(check, "check_type"))
        for check in check_results
        if str(_check_field(check, "check_type")).startswith("beam_flexure_")
    )

    assert flexure_check_types == EXPECTED_N6_FLEXURE_CHECK_NAMES

    statuses = {
        str(_check_field(check, "check_type")): _check_field(check, "status")
        for check in check_results
        if str(_check_field(check, "check_type")).startswith("beam_flexure_")
    }
    assert set(statuses) == set(EXPECTED_N6_FLEXURE_CHECK_NAMES)
    assert all(status == "OK" for status in statuses.values())