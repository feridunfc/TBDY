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
from tbdy_engine.design.beams.etabs_input_adapter import (
    build_normalized_beam_input_from_etabs_payload,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_json(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8-sig"))
    assert isinstance(payload, dict)
    return payload


def _jsonable(value: object) -> object:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _runner_check_types(json_path: Path) -> tuple[str, ...]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    checks = payload.get("checks")
    assert isinstance(checks, list)
    return tuple(str(check.get("check_type")) for check in checks if isinstance(check, dict))


def _pipeline_snapshot(raw: dict[str, object]) -> tuple[object, ...]:
    normalized = build_normalized_beam_input_from_etabs_payload(raw)
    canonical = build_canonical_beam_input_from_normalized(normalized)
    result = evaluate_beam_core(canonical)

    return (
        normalized,
        canonical,
        result.status,
        tuple(
            (check.id, check.name, check.status, check.demand, check.capacity, check.ratio)
            for check in result.core_checks
            if check.name in {
                "beam_shear_capacity_design_ve_le_vr",
                "beam_shear_capacity_design_ve_le_085_vmax",
            }
        ),
    )


def test_p4_etabs_payload_adapter_maps_static_payload_to_normalized_shape() -> None:
    raw = _load_json("beam_etabs_payload_full.json")
    normalized = build_normalized_beam_input_from_etabs_payload(raw)

    assert normalized["id"] == "B-P4-ETABS-RAW"
    assert normalized["story"] == "+1.00"
    assert normalized["section"] == "B60x60"

    assert normalized["geometry"]["bw_mm"] == 600.0
    assert normalized["geometry"]["h_mm"] == 600.0
    assert normalized["geometry"]["d_mm"] == 550.0
    assert normalized["geometry"]["cover_mm"] == 40.0
    assert normalized["geometry"]["Ln_mm"] == 5000.0

    assert normalized["materials"]["fck_mpa"] == 30.0
    assert normalized["materials"]["fcd_mpa"] == 20.0
    assert normalized["materials"]["fctd_mpa"] == 1.27
    assert normalized["materials"]["fyk_mpa"] == 420.0
    assert normalized["materials"]["fyd_mpa"] == 365.0
    assert normalized["materials"]["fywd_mpa"] == 365.0

    assert normalized["actions"]["Vd_left_kN"] == 90.0
    assert normalized["actions"]["Ve_left_kN"] == 107.2
    assert normalized["actions"]["Md_left_neg_kNm"] == 120.0
    assert normalized["actions"]["Md_mid_pos_kNm"] == 90.0
    assert normalized["actions"]["Md_right_neg_kNm"] == 110.0
    assert normalized["actions"]["axial_kN"] == 0.0

    assert normalized["reinforcement"]["stirrup_legs"] == 2
    assert normalized["reinforcement"]["stirrup_diameter_mm"] == 10.0
    assert normalized["reinforcement"]["stirrup_spacing_mm"] == 100.0
    assert normalized["reinforcement"]["longitudinal_bar_diameter_mm"] == 16.0
    assert normalized["reinforcement"]["top_selected_area_cm2"] == 10.0
    assert normalized["reinforcement"]["bottom_selected_area_cm2"] == 10.0
    assert normalized["reinforcement"]["top_required_area_cm2"] is None
    assert normalized["reinforcement"]["bottom_required_area_cm2"] is None

    assert normalized["metadata"]["source"]["origin"] == "etabs_payload_adapter"
    assert normalized["metadata"]["source"]["raw_source_kind"] == "etabs_static_fixture"
    assert normalized["metadata"]["source"]["raw_model_name"] == "fixture_only_no_live_etabs"
    assert normalized["missing_inputs"] == ()


def test_p4_etabs_payload_adapter_matches_expected_normalized_fixture() -> None:
    raw = _load_json("beam_etabs_payload_full.json")
    expected = _load_json("beam_normalized_from_etabs_expected_full.json")

    normalized = build_normalized_beam_input_from_etabs_payload(raw)

    assert _jsonable(normalized) == expected


def test_p4_missing_required_raw_field_is_explicit_and_not_fabricated() -> None:
    raw = _load_json("beam_etabs_payload_missing_required.json")
    normalized = build_normalized_beam_input_from_etabs_payload(raw)

    assert normalized["geometry"]["d_mm"] is None
    assert "geometry.d_mm" in normalized["missing_inputs"]

    canonical = build_canonical_beam_input_from_normalized(normalized)

    assert canonical["d_mm"] is None
    assert "d_mm" in canonical["missing_inputs"]

    result = evaluate_beam_core(canonical)

    assert result.status == "INVALID_INPUT"
    assert "d_mm" in result.validation_errors
    assert result.geometry is None
    assert result.shear is None
    assert result.flexure is None


def test_p4_etabs_payload_runs_through_normalized_canonical_beamcore_path() -> None:
    raw = _load_json("beam_etabs_payload_full.json")
    normalized = build_normalized_beam_input_from_etabs_payload(raw)
    canonical = build_canonical_beam_input_from_normalized(normalized)
    result = evaluate_beam_core(canonical)

    assert result.status == "OK"
    assert result.geometry is not None
    assert result.geometry.status == "OK"
    assert result.flexure is not None
    assert result.shear is not None

    names = {check.name for check in result.core_checks}
    assert "beam_shear_capacity_design_ve_le_vr" in names
    assert "beam_shear_capacity_design_ve_le_085_vmax" in names
    assert "beam_shear_ve_le_vr" in names
    assert "beam_shear_ve_le_085_vmax" in names


def test_p4_etabs_payload_runs_through_runner_artifact_path(tmp_path: Path) -> None:
    raw = _load_json("beam_etabs_payload_full.json")
    normalized = build_normalized_beam_input_from_etabs_payload(raw)
    canonical = build_canonical_beam_input_from_normalized(normalized)

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

    check_types = _runner_check_types(result.json_path)
    assert "beam_shear_capacity_design_ve_le_vr" in check_types
    assert "beam_shear_capacity_design_ve_le_085_vmax" in check_types


def test_p4_etabs_payload_boundary_pipeline_is_deterministic_for_repeated_runs() -> None:
    raw = _load_json("beam_etabs_payload_full.json")
    first_snapshot = _pipeline_snapshot(raw)

    assert first_snapshot[2] == "OK"

    for _ in range(100):
        assert _pipeline_snapshot(raw) == first_snapshot


def test_p4_etabs_input_adapter_source_guard_has_no_live_dependencies() -> None:
    adapter_source = pathlib.Path("tbdy_engine/design/beams/etabs_input_adapter.py").read_text(encoding="utf-8")

    forbidden = (
        "com" + "types",
        "Sap" + "Model",
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
    )

    for text in forbidden:
        assert text not in adapter_source