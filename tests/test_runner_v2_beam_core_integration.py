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

from tbdy_engine.design.beams.beam_core_runner import run_beam_core_artifact_path


def _canonical_beam_input(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "beam_id": "B-P1-CANONICAL",
        "story": "+0.00",
        "section_name": "B60x60",
        "bw_mm": 600.0,
        "h_mm": 600.0,
        "d_mm": 550.0,
        "cover_mm": 40.0,
        "Ln_mm": 5000.0,
        "fck_mpa": 30.0,
        "fcd_mpa": 20.0,
        "fctd_mpa": 1.27,
        "fyk_mpa": 420.0,
        "fyd_mpa": 365.0,
        "fywd_mpa": 365.0,
        "Vd_left_kN": 90.0,
        "Ve_left_kN": 107.2,
        "Md_left_neg_kNm": 120.0,
        "Md_mid_pos_kNm": 90.0,
        "Md_right_neg_kNm": 110.0,
        "axial_kN": 0.0,
        "stirrup_legs": 2,
        "stirrup_diameter_mm": 10.0,
        "stirrup_spacing_mm": 100.0,
        "longitudinal_bar_diameter_mm": 16.0,
        "top_required_area_cm2": 0.0,
        "top_selected_area_cm2": 10.0,
        "bottom_required_area_cm2": 0.0,
        "bottom_selected_area_cm2": 10.0,
        "missing_inputs": (),
        "source": {"origin": "p1_runner_canonical_input"},
    }
    data.update(overrides)
    return data


def _load_payload(path: pathlib.Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _checks(payload: dict[str, object]) -> list[dict[str, object]]:
    checks = payload.get("checks")
    assert isinstance(checks, list)
    assert all(isinstance(check, dict) for check in checks)
    return checks  # type: ignore[return-value]


def _check_types(payload: dict[str, object]) -> tuple[str, ...]:
    return tuple(str(check.get("check_type")) for check in _checks(payload))


def _normalized_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "summary": payload.get("summary"),
        "check_rows": [
            {
                "id": check.get("id"),
                "component": check.get("component"),
                "check_type": check.get("check_type"),
                "status": check.get("status"),
                "demand": check.get("demand"),
                "capacity": check.get("capacity"),
                "ratio": check.get("ratio"),
                "unit": check.get("unit"),
                "code_ref": check.get("code_ref"),
            }
            for check in _checks(payload)
        ],
    }


def test_p1_runner_beam_core_artifact_path_generates_json_and_xlsx(tmp_path: Path) -> None:
    result = run_beam_core_artifact_path(
        beam_input=_canonical_beam_input(),
        output_dir=tmp_path,
    )

    assert result.status == "OK"
    assert result.package_count == 1
    assert result.check_count == 24
    assert result.artifact_result.beam_core.status == "OK"

    assert result.json_path == tmp_path / "engine_report.json"
    assert result.xlsx_path == tmp_path / "engine_report.xlsx"
    assert result.json_path.exists()
    assert result.xlsx_path is not None
    assert result.xlsx_path.exists()

    payload = _load_payload(result.json_path)
    check_types = _check_types(payload)

    assert len(check_types) == result.check_count
    assert "beam_shear_capacity_design_ve_le_vr" in check_types
    assert "beam_shear_capacity_design_ve_le_085_vmax" in check_types
    assert "beam_shear_ve_le_vr" in check_types
    assert "beam_shear_ve_le_085_vmax" in check_types
    assert "beam_flexure_top_plastic_moment_available" in check_types
    assert "beam_flexure_bottom_plastic_moment_available" in check_types


def test_p1_runner_beam_core_artifact_path_is_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = run_beam_core_artifact_path(
        beam_input=_canonical_beam_input(),
        output_dir=first_dir,
    )
    second = run_beam_core_artifact_path(
        beam_input=_canonical_beam_input(),
        output_dir=second_dir,
    )

    assert first.status == second.status == "OK"
    assert first.package_count == second.package_count == 1
    assert first.check_count == second.check_count == 24

    first_payload = _normalized_payload(_load_payload(first.json_path))
    second_payload = _normalized_payload(_load_payload(second.json_path))

    assert first_payload == second_payload


def test_p1_runner_beam_core_path_source_guard_has_no_forbidden_dependencies() -> None:
    runner_source = pathlib.Path("tbdy_engine/design/beams/beam_core_runner.py").read_text(encoding="utf-8")
    test_source = pathlib.Path("tests/test_runner_v2_beam_core_integration.py").read_text(encoding="utf-8")

    forbidden = (
        "tbdy_engine." + "etabs",
        "read_" + "etabs" + "_table_on_demand",
        "ETABS " + "COM",
        "com" + "types",
        "Sap" + "Model",
    )

    for source in (runner_source, test_source):
        for text in forbidden:
            assert text not in source