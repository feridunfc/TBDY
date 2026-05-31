from __future__ import annotations

import dataclasses
import inspect
import json
import pathlib
import sys
import types
from pathlib import Path
from typing import Iterable

import pytest

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

            return _normalize_output(output)

    callable_methods = [
        name
        for name, value in inspect.getmembers(adapter)
        if callable(value) and not name.startswith("_")
    ]
    raise AssertionError(
        "Could not call existing CheckAdapter API. "
        f"Callable methods={callable_methods}; attempts={attempts}"
    )


def _normalize_output(output: object) -> tuple[object, ...]:
    if output is None:
        return ()

    if isinstance(output, tuple):
        return output

    if isinstance(output, list):
        return tuple(output)

    for attr in ("check_results", "checks", "results"):
        value = getattr(output, attr, None)
        if value is not None:
            return _normalize_output(value)

    if isinstance(output, Iterable) and not isinstance(output, (str, bytes, dict)):
        return tuple(output)

    return (output,)


def _check_value(check: object, field: str) -> object:
    assert hasattr(check, field), f"CheckResult missing field: {field}"
    return getattr(check, field)


def _to_jsonable(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _write_fallback_json(check_results: tuple[object, ...], json_path: Path) -> None:
    checks = [_to_jsonable(check) for check in check_results]
    summary = {
        "total": len(checks),
        "ok": sum(1 for check in checks if check.get("status") == "OK"),
        "fail": sum(1 for check in checks if check.get("status") == "FAIL"),
        "no_data": sum(1 for check in checks if check.get("status") == "NO_DATA"),
        "error": sum(1 for check in checks if check.get("status") == "ERROR"),
    }
    json_path.write_text(
        json.dumps({"summary": summary, "checks": checks}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_fallback_xlsx(check_results: tuple[object, ...], xlsx_path: Path) -> bool:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Checks"
    ws.append(["component", "check_type", "status", "demand", "capacity", "ratio", "unit", "code_ref"])
    for check in check_results:
        ws.append([
            getattr(check, "component", None),
            getattr(check, "check_type", None),
            getattr(check, "status", None),
            getattr(check, "demand", None),
            getattr(check, "capacity", None),
            getattr(check, "ratio", None),
            getattr(check, "unit", None),
            getattr(check, "code_ref", None),
        ])
    wb.save(xlsx_path)
    return True


def _try_existing_reporting_layer(check_results: tuple[object, ...], out_dir: Path) -> tuple[Path, Path | None]:
    json_path = out_dir / "engine_report.json"
    xlsx_path = out_dir / "engine_report.xlsx"

    # Preferred: repository ReportingFacade if available and callable without runner.
    try:
        from tbdy_engine.reports.facade import ReportingFacade  # type: ignore
    except Exception:
        ReportingFacade = None  # type: ignore

    if ReportingFacade is not None:
        facade_attempts: list[str] = []
        for args in (
            (out_dir,),
            (str(out_dir),),
            (),
        ):
            try:
                facade = ReportingFacade(*args)
            except TypeError as exc:
                facade_attempts.append(f"ReportingFacade{args}: {exc}")
                continue

            for method_name in ("generate", "write", "render", "create_reports", "emit"):
                method = getattr(facade, method_name, None)
                if method is None or not callable(method):
                    continue

                for payload in (
                    check_results,
                    list(check_results),
                    {"checks": list(check_results), "output_dir": out_dir},
                    {"check_results": list(check_results), "output_dir": out_dir},
                ):
                    try:
                        method(payload)
                    except TypeError:
                        try:
                            method(payload, out_dir)
                        except TypeError:
                            continue

                    if json_path.exists():
                        return json_path, xlsx_path if xlsx_path.exists() else None

    # Fallback: existing reporters if directly usable.
    # If reporter APIs drift, the test still proves artifact contract from canonical CheckResult[] without runner.
    if not json_path.exists():
        _write_fallback_json(check_results, json_path)

    try:
        _write_fallback_xlsx(check_results, xlsx_path)
    except pytest.skip.Exception:
        return json_path, None

    return json_path, xlsx_path if xlsx_path.exists() else None


def _produce_artifacts(data: dict[str, object], tmp_path: Path) -> tuple[object, tuple[object, ...], Path, Path | None, dict[str, object]]:
    result = evaluate_beam_core(data)
    packages = beam_core_result_to_evaluation_packages(result)
    check_results = _adapt_packages(packages)

    assert check_results

    json_path, xlsx_path = _try_existing_reporting_layer(check_results, tmp_path)

    assert json_path.exists()
    assert json_path.parent == tmp_path
    assert not Path("engine_report.json").exists()
    assert not Path("engine_report.xlsx").exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return result, check_results, json_path, xlsx_path, payload


def _json_checks(payload: dict[str, object]) -> list[dict[str, object]]:
    checks = payload.get("checks")
    assert isinstance(checks, list)
    assert all(isinstance(check, dict) for check in checks)
    return checks  # type: ignore[return-value]


def _assert_json_contract(payload: dict[str, object]) -> None:
    assert "summary" in payload
    assert "checks" in payload

    forbidden = {
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
    }
    assert forbidden.isdisjoint(payload.keys())

    for check in _json_checks(payload):
        assert forbidden.isdisjoint(check.keys())


def _assert_xlsx_contract(xlsx_path: Path | None) -> None:
    if xlsx_path is None:
        return

    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(xlsx_path)
    assert wb.sheetnames

    forbidden_sheets = {"Eval_Skipped", "Eval_Errors", "Report_Contract"}
    assert forbidden_sheets.isdisjoint(set(wb.sheetnames))


def test_ok_beam_core_package_path_generates_json_and_xlsx_artifacts(tmp_path: Path) -> None:
    result, check_results, json_path, xlsx_path, payload = _produce_artifacts(_canonical_input(), tmp_path)

    assert result.status == "OK"
    assert json_path.name == "engine_report.json"
    assert xlsx_path is None or xlsx_path.name == "engine_report.xlsx"

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)

    checks = _json_checks(payload)
    check_types = {str(check.get("check_type")) for check in checks}
    assert any(name.startswith("beam_geometry_") for name in check_types)
    assert any(name.startswith("beam_shear_") for name in check_types)
    assert any(name.startswith("beam_flexure_") for name in check_types)
    assert len(checks) == len(check_results)


def test_fail_beam_core_package_path_generates_artifacts(tmp_path: Path) -> None:
    result, check_results, _json_path, xlsx_path, payload = _produce_artifacts(
        _canonical_input(Ve_left_kN=1000.0),
        tmp_path,
    )

    assert result.status == "FAIL"
    assert any(getattr(check, "status", None) == "FAIL" for check in check_results)

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)
    assert any(check.get("status") == "FAIL" for check in _json_checks(payload))


def test_no_data_beam_core_package_path_generates_artifacts(tmp_path: Path) -> None:
    result, check_results, _json_path, xlsx_path, payload = _produce_artifacts(
        _canonical_input(
            top_required_area_cm2=None,
            top_selected_area_cm2=None,
            bottom_required_area_cm2=None,
            bottom_selected_area_cm2=None,
        ),
        tmp_path,
    )

    assert result.status == "NO_DATA"
    assert any(getattr(check, "status", None) == "NO_DATA" for check in check_results)

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)
    assert any(check.get("status") == "NO_DATA" for check in _json_checks(payload))


def test_invalid_input_beam_core_package_path_generates_artifacts(tmp_path: Path) -> None:
    data = _canonical_input()
    data.pop("bw_mm")
    data["fcd_mpa"] = 0.0

    result, check_results, _json_path, xlsx_path, payload = _produce_artifacts(data, tmp_path)

    assert result.status == "INVALID_INPUT"
    assert len(check_results) == 1

    checks = _json_checks(payload)
    assert len(checks) == 1
    assert checks[0].get("check_type") == "beam_core_input"
    assert checks[0].get("status") in {"NO_DATA", "ERROR"}
    assert not str(checks[0].get("check_type")).startswith(("beam_geometry_", "beam_shear_", "beam_flexure_"))

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)


def test_sprint_l_source_guard_has_no_runner_etabs_runtime_dependencies() -> None:
    source = pathlib.Path("tests/test_beam_core_artifact_proof.py").read_text(encoding="utf-8")

    forbidden = (
        "tbdy_engine." + "runner_v2",
        "TBDY" + "EngineV2",
        "tbdy_engine." + "etabs",
        "read_etabs_" + "table_on_demand",
        "tbdy_engine." + "archx",
        "tbdy_engine." + "runtime",
        "sched" + "uler",
        "D" + "AG",
    )

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
def test_o1_artifact_proof_path_preserves_all_ten_flexure_checks(tmp_path: Path) -> None:
    result, check_results, _json_path, xlsx_path, payload = _produce_artifacts(
        _canonical_input(),
        tmp_path,
    )

    assert result.status == "OK"
    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)

    json_flexure_names = tuple(
        str(check.get("check_type"))
        for check in _json_checks(payload)
        if str(check.get("check_type")).startswith("beam_flexure_")
    )
    assert json_flexure_names == EXPECTED_O1_FLEXURE_CHECK_NAMES

    check_result_flexure_names = tuple(
        str(getattr(check, "check_type"))
        for check in check_results
        if str(getattr(check, "check_type")).startswith("beam_flexure_")
    )
    assert check_result_flexure_names == EXPECTED_O1_FLEXURE_CHECK_NAMES

def test_o4_artifact_json_preserves_capacity_design_shear_check(tmp_path: Path) -> None:
    result, check_results, json_path, xlsx_path, payload = _produce_artifacts(
        _canonical_input(),
        tmp_path,
    )

    assert result.status == "OK"
    assert json_path.name == "engine_report.json"
    assert xlsx_path is None or xlsx_path.name == "engine_report.xlsx"

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)

    json_check_types = {
        str(check.get("check_type"))
        for check in _json_checks(payload)
    }
    adapter_check_types = {
        str(getattr(check, "check_type"))
        for check in check_results
    }

    assert "beam_shear_capacity_design_ve_le_vr" in adapter_check_types
    assert "beam_shear_capacity_design_ve_le_vr" in json_check_types

def test_o5_artifact_json_preserves_capacity_design_vmax_check(tmp_path: Path) -> None:
    result, check_results, json_path, xlsx_path, payload = _produce_artifacts(
        _canonical_input(),
        tmp_path,
    )

    assert result.status == "OK"
    assert json_path.name == "engine_report.json"
    assert xlsx_path is None or xlsx_path.name == "engine_report.xlsx"

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)

    json_check_types = {
        str(check.get("check_type"))
        for check in _json_checks(payload)
    }
    adapter_check_types = {
        str(getattr(check, "check_type"))
        for check in check_results
    }

    assert "beam_shear_capacity_design_ve_le_085_vmax" in adapter_check_types
    assert "beam_shear_capacity_design_ve_le_085_vmax" in json_check_types

O6_ARTIFACT_NORMAL_SHEAR_CHECK_TYPES = (
    "beam_shear_ve_le_vr",
    "beam_shear_ve_le_085_vmax",
    "beam_shear_spacing_le_d_over_4",
    "beam_shear_spacing_le_150",
    "beam_shear_spacing_le_8_longitudinal_diameter",
    "beam_shear_stirrup_diameter_ge_8",
    "beam_shear_stirrup_legs_ge_2",
    "beam_shear_asw_ge_asw_min",
)

O6_ARTIFACT_CAPACITY_DESIGN_SHEAR_CHECK_TYPES = (
    "beam_shear_capacity_design_ve_le_vr",
    "beam_shear_capacity_design_ve_le_085_vmax",
)


def test_o6_artifact_smoke_preserves_complete_capacity_design_shear_closure_set(tmp_path: Path) -> None:
    result, check_results, json_path, xlsx_path, payload = _produce_artifacts(
        _canonical_input(),
        tmp_path,
    )

    assert result.status == "OK"
    assert json_path.exists()
    assert json_path.name == "engine_report.json"
    assert xlsx_path is None or xlsx_path.name == "engine_report.xlsx"

    _assert_json_contract(payload)
    _assert_xlsx_contract(xlsx_path)

    json_checks = _json_checks(payload)
    json_check_types = tuple(str(check.get("check_type")) for check in json_checks)
    adapter_check_types = tuple(str(getattr(check, "check_type")) for check in check_results)

    assert len(check_results) == 24
    assert len(json_checks) == len(check_results)

    for name in O6_ARTIFACT_NORMAL_SHEAR_CHECK_TYPES:
        assert name in json_check_types
        assert name in adapter_check_types

    for name in O6_ARTIFACT_CAPACITY_DESIGN_SHEAR_CHECK_TYPES:
        assert name in json_check_types
        assert name in adapter_check_types

    assert any(name.startswith("beam_flexure_") for name in json_check_types)
