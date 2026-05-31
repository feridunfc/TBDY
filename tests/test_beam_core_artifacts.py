from __future__ import annotations

import json
import pathlib
import sys
import types
from pathlib import Path

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.beam_core_artifacts import (
    BeamCoreArtifactResult,
    generate_beam_core_artifacts,
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


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _checks(payload: dict[str, object]) -> list[dict[str, object]]:
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

    for check in _checks(payload):
        assert forbidden.isdisjoint(check.keys())


def _assert_artifact_location(result: BeamCoreArtifactResult, tmp_path: Path) -> None:
    assert result.json_path.parent == tmp_path
    assert result.json_path.name == "engine_report.json"
    assert result.json_path.exists()

    if result.xlsx_path is not None:
        assert result.xlsx_path.parent == tmp_path
        assert result.xlsx_path.name == "engine_report.xlsx"
        assert result.xlsx_path.exists()

    assert not Path("engine_report.json").exists()
    assert not Path("engine_report.xlsx").exists()


def test_ok_path_generates_json_and_xlsx_artifacts(tmp_path: Path) -> None:
    result = generate_beam_core_artifacts(_canonical_input(), tmp_path)

    assert result.status == "OK"
    assert result.beam_core.status == "OK"
    assert result.packages
    assert result.checks
    assert result.json_path.exists()
    assert result.json_path.name == "engine_report.json"

    if result.xlsx_path is not None:
        assert result.xlsx_path.exists()
        assert result.xlsx_path.name == "engine_report.xlsx"

    _assert_artifact_location(result, tmp_path)

    payload = _load_json(result.json_path)
    _assert_json_contract(payload)

    check_types = {str(check.get("check_type")) for check in _checks(payload)}
    assert any(name.startswith("beam_geometry_") for name in check_types)
    assert any(name.startswith("beam_shear_") for name in check_types)
    assert any(name.startswith("beam_flexure_") for name in check_types)


def test_fail_path_generates_json_with_fail_status(tmp_path: Path) -> None:
    result = generate_beam_core_artifacts(_canonical_input(Ve_left_kN=1000.0), tmp_path)

    assert result.status == "FAIL"
    payload = _load_json(result.json_path)
    _assert_json_contract(payload)
    assert any(check.get("status") == "FAIL" for check in _checks(payload))


def test_no_data_path_generates_json_with_no_data_status(tmp_path: Path) -> None:
    result = generate_beam_core_artifacts(
        _canonical_input(
            top_required_area_cm2=None,
            top_selected_area_cm2=None,
            bottom_required_area_cm2=None,
            bottom_selected_area_cm2=None,
        ),
        tmp_path,
    )

    assert result.status == "NO_DATA"
    payload = _load_json(result.json_path)
    _assert_json_contract(payload)
    assert any(check.get("status") == "NO_DATA" for check in _checks(payload))


def test_invalid_input_path_generates_beam_core_input_artifact(tmp_path: Path) -> None:
    data = _canonical_input()
    data.pop("bw_mm")
    data["fcd_mpa"] = 0.0

    result = generate_beam_core_artifacts(data, tmp_path)

    assert result.status == "INVALID_INPUT"
    payload = _load_json(result.json_path)
    _assert_json_contract(payload)

    checks = _checks(payload)
    assert len(checks) == 1
    assert checks[0].get("check_type") == "beam_core_input"
    assert checks[0].get("status") in {"NO_DATA", "ERROR"}
    assert not str(checks[0].get("check_type")).startswith(
        ("beam_geometry_", "beam_shear_", "beam_flexure_")
    )


def test_beam_core_artifacts_source_guard_has_no_runner_or_etabs() -> None:
    source = pathlib.Path("tbdy_engine/design/beams/beam_core_artifacts.py").read_text(encoding="utf-8")

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

EXPECTED_N6_FLEXURE_CHECK_NAMES = (
    "beam_flexure_top_area_provided_ge_required",
    "beam_flexure_bottom_area_provided_ge_required",
    "beam_flexure_top_rho_ge_rho_min",
    "beam_flexure_bottom_rho_ge_rho_min",
    "beam_flexure_top_rho_le_rho_max",
    "beam_flexure_bottom_rho_le_rho_max",
)
def test_n6_artifact_json_contains_all_six_flexure_checks(tmp_path: Path) -> None:
    result = generate_beam_core_artifacts(_canonical_input(), tmp_path)

    assert result.status == "OK"

    payload = _load_json(result.json_path)
    flexure_check_types = tuple(
        str(check.get("check_type"))
        for check in _checks(payload)
        if str(check.get("check_type")).startswith("beam_flexure_")
    )

    assert flexure_check_types == EXPECTED_N6_FLEXURE_CHECK_NAMES
    assert len(result.checks) == 18