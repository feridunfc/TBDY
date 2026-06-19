from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.checks.input_adapter import build_geometry_check_inputs_from_feature_snapshot
from tbdy_engine.product.golden_regression import run_geometry_golden_regression
from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan

ROOT = Path(__file__).resolve().parents[2]
COLUMN_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p1" / "column_geometry_feature_snapshots.json"
CANONICAL_FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
GOLDEN = ROOT / "tests" / "fixtures" / "c13_4_p8" / "golden_geometry_product_fingerprint.json"
IMPLEMENTATION_PATHS = (
    ROOT / "tbdy_engine" / "checks" / "input_adapter.py",
    ROOT / "tbdy_engine" / "checks" / "engine.py",
    ROOT / "tbdy_engine" / "checks" / "geometry_vertical_slice.py",
    ROOT / "tbdy_engine" / "catalogs" / "check_catalog_c13_5_p1_column_geometry.yaml",
    ROOT / "tbdy_engine" / "catalogs" / "feature_catalog_c13_5_p1_column_geometry.yaml",
)
FORBIDDEN_IMPORT_PATHS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)
FORBIDDEN_LOGIC_TERMS = (
    "axial force",
    "shear force",
    "bending moment",
    "load combination",
    "design combination",
    "confinement",
    "column PMM",
    "strong-column weak-beam",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _snapshot_by_component(component_id: str):
    for snapshot in _read_json(COLUMN_FIXTURE)["snapshots"]:
        if snapshot["component_id"] == component_id:
            return snapshot
    raise AssertionError(f"missing fixture component {component_id}")


def test_missing_width_produces_adapter_diagnostic_not_fail():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot_by_component("C_MISSING_WIDTH"))
    diagnostics = {diagnostic.check_id: diagnostic for diagnostic in result.diagnostics}

    assert diagnostics["column_geometry_min_width"].status == "NO_DATA"
    assert diagnostics["column_geometry_min_dimension"].status == "NO_DATA"
    assert {diagnostic.status for diagnostic in result.diagnostics}.isdisjoint({"OK", "FAIL"})


def test_missing_depth_produces_adapter_diagnostic_not_fail():
    snapshot = _snapshot_by_component("C_MISSING_WIDTH")
    features = dict(snapshot["features"])
    features.pop("column_depth_mm")
    features["column_width_mm"] = {
        "evidence": [{"actual_table_name": "ETABS Geometry Source", "evidence_status": "FULL", "normalized_value": 400.0, "raw_value": 400.0, "resolver": "test", "source_column": "column_width_mm", "source_row": {"component": "C_MISSING_DEPTH"}, "source_table": "source_geometry_table", "unit": "mm"}],
        "semantic_role": "GEOMETRY",
        "status": "RESOLVED",
        "unit": "mm",
        "value": 400.0,
    }
    missing_depth = {**snapshot, "component_id": "C_MISSING_DEPTH", "features": features}

    result = build_geometry_check_inputs_from_feature_snapshot(missing_depth)
    diagnostics = {diagnostic.check_id: diagnostic for diagnostic in result.diagnostics}

    assert diagnostics["column_geometry_min_depth"].status == "NO_DATA"
    assert diagnostics["column_geometry_min_dimension"].status == "NO_DATA"
    assert {diagnostic.status for diagnostic in result.diagnostics}.isdisjoint({"OK", "FAIL"})


def test_wrong_width_unit_blocks_without_silent_conversion():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot_by_component("C_WRONG_WIDTH_UNIT"))
    diagnostics = {diagnostic.check_id: diagnostic for diagnostic in result.diagnostics}

    assert diagnostics["column_geometry_min_width"].status == "BLOCKED"
    assert "unit 'cm' does not match required unit 'mm'" in diagnostics["column_geometry_min_width"].reason
    assert {diagnostic.status for diagnostic in result.diagnostics}.isdisjoint({"OK", "FAIL"})


def test_wrong_depth_unit_blocks_without_silent_conversion():
    snapshot = _snapshot_by_component("C_OK")
    features = dict(snapshot["features"])
    depth = dict(features["column_depth_mm"])
    depth["unit"] = "cm"
    depth["value"] = 50.0
    depth["evidence"] = [dict(depth["evidence"][0], unit="cm", raw_value=50.0, normalized_value=50.0)]
    features["column_depth_mm"] = depth

    result = build_geometry_check_inputs_from_feature_snapshot({**snapshot, "component_id": "C_WRONG_DEPTH_UNIT", "features": features})
    diagnostics = {diagnostic.check_id: diagnostic for diagnostic in result.diagnostics}

    assert diagnostics["column_geometry_min_depth"].status == "BLOCKED"
    assert "unit 'cm' does not match required unit 'mm'" in diagnostics["column_geometry_min_depth"].reason
    assert {diagnostic.status for diagnostic in result.diagnostics}.isdisjoint({"OK", "FAIL"})


def test_golden_mismatch_fails_if_expected_count_remains_four(tmp_path: Path):
    stale_golden = _read_json(GOLDEN)
    stale_golden["p6"]["check_result_count"] = 4
    stale_golden["p6"]["check_result_status_counts"] = {"OK": 4}
    stale_golden["checks"] = stale_golden["checks"][:4]
    stale_path = tmp_path / "stale_golden.json"
    _write_json(stale_path, stale_golden)

    result = run_geometry_golden_regression(
        feature_snapshot_path=CANONICAL_FIXTURE,
        output_dir=tmp_path / "golden",
        golden_fingerprint_path=stale_path,
    )

    assert result.status == "FAIL"
    assert result.difference_count > 0


def test_acceptance_gate_fails_if_c13_5_p1_suite_is_removed_from_command_plan(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")
    without_c13_5 = tuple(item for item in plan if item[0] != "pytest_c13_5_p1")

    assert len(without_c13_5) == 12
    assert any(name == "pytest_c13_5_p1" for name, _command in plan)


def test_no_forbidden_legacy_imports_added_to_c13_5_implementation_paths():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in IMPLEMENTATION_PATHS)

    for forbidden in FORBIDDEN_IMPORT_PATHS:
        assert forbidden not in combined


def test_no_force_or_design_logic_terms_in_new_c13_5_implementation_paths():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in IMPLEMENTATION_PATHS).casefold()

    for forbidden in FORBIDDEN_LOGIC_TERMS:
        assert forbidden.casefold() not in combined
