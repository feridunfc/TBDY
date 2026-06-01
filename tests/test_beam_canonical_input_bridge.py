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

from tbdy_engine.design.beams.beam_core import evaluate_beam_core
from tbdy_engine.design.beams.beam_core_runner import run_beam_core_artifact_path
from tbdy_engine.design.beams.canonical_input_bridge import (
    build_canonical_beam_input_from_normalized,
)


def _normalized_beam_input(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "B-P2-NORMALIZED",
        "story": "+0.00",
        "section": "B60x60",
        "geometry": {
            "bw_mm": 600.0,
            "h_mm": 600.0,
            "d_mm": 550.0,
            "cover_mm": 40.0,
            "Ln_mm": 5000.0,
        },
        "materials": {
            "fck_mpa": 30.0,
            "fcd_mpa": 20.0,
            "fctd_mpa": 1.27,
            "fyk_mpa": 420.0,
            "fyd_mpa": 365.0,
            "fywd_mpa": 365.0,
        },
        "actions": {
            "Vd_left_kN": 90.0,
            "Ve_left_kN": 107.2,
            "Md_left_neg_kNm": 120.0,
            "Md_mid_pos_kNm": 90.0,
            "Md_right_neg_kNm": 110.0,
            "axial_kN": 0.0,
        },
        "reinforcement": {
            "stirrup_legs": 2,
            "stirrup_diameter_mm": 10.0,
            "stirrup_spacing_mm": 100.0,
            "longitudinal_bar_diameter_mm": 16.0,
            "top_selected_area_cm2": 10.0,
            "bottom_selected_area_cm2": 10.0,
        },
        "metadata": {
            "source": "normalized_fixture",
        },
    }

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            updated = dict(data[key])  # type: ignore[index]
            updated.update(value)
            data[key] = updated
        else:
            data[key] = value

    return data


def _payload(path: pathlib.Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _check_types_from_payload(payload: dict[str, object]) -> tuple[str, ...]:
    checks = payload.get("checks")
    assert isinstance(checks, list)
    return tuple(str(check.get("check_type")) for check in checks if isinstance(check, dict))


def _capacity_snapshot(canonical: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    result = evaluate_beam_core(canonical)
    return tuple(
        (
            check.id,
            check.component,
            check.check_type,
            check.name,
            check.status,
            check.demand,
            check.capacity,
            check.ratio,
            tuple(sorted(check.evidence.keys())),
        )
        for check in result.core_checks
        if check.name in {
            "beam_shear_capacity_design_ve_le_vr",
            "beam_shear_capacity_design_ve_le_085_vmax",
        }
    )


def test_p2_bridge_maps_normalized_beam_data_to_canonical_shape() -> None:
    canonical = build_canonical_beam_input_from_normalized(_normalized_beam_input())

    assert canonical["beam_id"] == "B-P2-NORMALIZED"
    assert canonical["story"] == "+0.00"
    assert canonical["section_name"] == "B60x60"

    assert canonical["bw_mm"] == 600.0
    assert canonical["h_mm"] == 600.0
    assert canonical["d_mm"] == 550.0
    assert canonical["cover_mm"] == 40.0
    assert canonical["Ln_mm"] == 5000.0

    assert canonical["fck_mpa"] == 30.0
    assert canonical["fcd_mpa"] == 20.0
    assert canonical["fctd_mpa"] == 1.27
    assert canonical["fyk_mpa"] == 420.0
    assert canonical["fyd_mpa"] == 365.0
    assert canonical["fywd_mpa"] == 365.0

    assert canonical["Vd_left_kN"] == 90.0
    assert canonical["Ve_left_kN"] == 107.2
    assert canonical["Md_left_neg_kNm"] == 120.0
    assert canonical["Md_mid_pos_kNm"] == 90.0
    assert canonical["Md_right_neg_kNm"] == 110.0
    assert canonical["axial_kN"] == 0.0

    assert canonical["stirrup_legs"] == 2
    assert canonical["stirrup_diameter_mm"] == 10.0
    assert canonical["stirrup_spacing_mm"] == 100.0
    assert canonical["longitudinal_bar_diameter_mm"] == 16.0
    assert canonical["top_required_area_cm2"] is None
    assert canonical["bottom_required_area_cm2"] is None
    assert canonical["top_selected_area_cm2"] == 10.0
    assert canonical["bottom_selected_area_cm2"] == 10.0

    assert canonical["missing_inputs"] == ()
    assert canonical["source"] == {
        "origin": "normalized_bridge",
        "raw_source": "normalized_fixture",
    }


def test_p2_bridge_reports_missing_required_input_without_fabricating_value() -> None:
    normalized = _normalized_beam_input(geometry={"d_mm": None})
    canonical = build_canonical_beam_input_from_normalized(normalized)

    assert canonical["d_mm"] is None
    assert "d_mm" in canonical["missing_inputs"]

    result = evaluate_beam_core(canonical)

    assert result.status == "INVALID_INPUT"
    assert "d_mm" in result.validation_errors
    assert result.geometry is None
    assert result.shear is None
    assert result.flexure is None


def test_p2_bridge_output_runs_through_beam_core_and_preserves_capacity_design_checks() -> None:
    canonical = build_canonical_beam_input_from_normalized(_normalized_beam_input())
    result = evaluate_beam_core(canonical)

    assert result.status == "OK"
    assert result.geometry is not None
    assert result.geometry.status == "OK"
    assert result.flexure is not None
    assert result.shear is not None

    shear_check_names = {check.name for check in result.shear.checks}
    core_check_names = {check.name for check in result.core_checks}

    for name in (
        "beam_shear_capacity_design_ve_le_vr",
        "beam_shear_capacity_design_ve_le_085_vmax",
    ):
        assert name in shear_check_names
        assert name in core_check_names

    assert "beam_shear_ve_le_vr" in core_check_names
    assert "beam_shear_ve_le_085_vmax" in core_check_names
    assert "beam_flexure_top_plastic_moment_available" in core_check_names
    assert "beam_flexure_bottom_plastic_moment_available" in core_check_names


def test_p2_bridge_output_runs_through_p1_runner_artifact_path(tmp_path: Path) -> None:
    canonical = build_canonical_beam_input_from_normalized(_normalized_beam_input())

    result = run_beam_core_artifact_path(
        beam_input=canonical,
        output_dir=tmp_path,
    )

    assert result.status == "OK"
    assert result.package_count == 1
    assert result.check_count == 24
    assert result.json_path.exists()
    assert result.xlsx_path is not None
    assert result.xlsx_path.exists()

    payload = _payload(result.json_path)
    check_types = _check_types_from_payload(payload)

    assert "beam_shear_capacity_design_ve_le_vr" in check_types
    assert "beam_shear_capacity_design_ve_le_085_vmax" in check_types


def test_p2_bridge_and_beam_core_capacity_path_are_deterministic_for_repeated_runs() -> None:
    normalized = _normalized_beam_input()
    first_canonical = build_canonical_beam_input_from_normalized(normalized)
    first_snapshot = _capacity_snapshot(first_canonical)

    assert first_snapshot
    assert len(first_snapshot) == 2

    for _ in range(100):
        current_canonical = build_canonical_beam_input_from_normalized(normalized)
        assert current_canonical == first_canonical
        assert _capacity_snapshot(current_canonical) == first_snapshot


def test_p2_bridge_source_guard_has_no_forbidden_dependencies() -> None:
    bridge_source = pathlib.Path("tbdy_engine/design/beams/canonical_input_bridge.py").read_text(encoding="utf-8")

    forbidden = (
        "tbdy_engine." + "etabs",
        "ETABS",
        "com" + "types",
        "Sap" + "Model",
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
    )

    for text in forbidden:
        assert text not in bridge_source