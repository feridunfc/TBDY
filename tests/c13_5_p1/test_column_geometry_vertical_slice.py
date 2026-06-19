from __future__ import annotations

import json
from pathlib import Path

import yaml

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.geometry_vertical_slice import run_geometry_vertical_slice_from_file
from tbdy_engine.checks.input_adapter import build_geometry_check_inputs_from_feature_snapshot
from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke
from tbdy_engine.product.golden_regression import run_geometry_golden_regression
from tbdy_engine.product.offline_acceptance import build_offline_acceptance_command_plan
from tbdy_engine.reports.geometry_markdown_report import render_geometry_markdown_report_from_artifact_dir

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"
CHECK_OVERLAY = CATALOG_DIR / "check_catalog_c13_5_p1_column_geometry.yaml"
FEATURE_OVERLAY = CATALOG_DIR / "feature_catalog_c13_5_p1_column_geometry.yaml"
CANONICAL_FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
COLUMN_FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p1" / "column_geometry_feature_snapshots.json"
GOLDEN = ROOT / "tests" / "fixtures" / "c13_4_p8" / "golden_geometry_product_fingerprint.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _snapshot_by_component(component_id: str):
    payload = _read_json(COLUMN_FIXTURE)
    for snapshot in payload["snapshots"]:
        if snapshot["component_id"] == component_id:
            return snapshot
    raise AssertionError(f"missing fixture component {component_id}")


def test_new_check_ids_are_present_in_modular_check_catalog():
    checks = _read_yaml(CHECK_OVERLAY)["checks"]

    assert "column_geometry_min_width" in checks
    assert "column_geometry_min_depth" in checks
    assert checks["column_geometry_min_width"]["required_features"] == ["column_width_mm"]
    assert checks["column_geometry_min_depth"]["required_features"] == ["column_depth_mm"]
    assert checks["column_geometry_min_width"]["output"]["unit"] == "mm"
    assert checks["column_geometry_min_depth"]["output"]["unit"] == "mm"


def test_column_width_depth_features_are_present_in_modular_feature_catalog():
    features = _read_yaml(FEATURE_OVERLAY)["features"]

    assert features["column_width_mm"]["unit"] == "mm"
    assert features["column_depth_mm"]["unit"] == "mm"
    assert features["column_width_mm"]["unit_policy"]["conversion"] == "none"
    assert features["column_depth_mm"]["unit_policy"]["conversion"] == "none"


def test_adapter_builds_explicit_column_width_depth_inputs_for_resolved_column():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot_by_component("C_OK"))
    check_ids = {item.check_id for item in result.check_inputs}

    assert "column_geometry_min_dimension" in check_ids
    assert "column_geometry_min_width" in check_ids
    assert "column_geometry_min_depth" in check_ids
    assert result.diagnostics == ()


def test_adapter_diagnostics_never_emit_ok_or_fail_for_missing_or_wrong_unit():
    for component_id in ("C_MISSING_WIDTH", "C_WRONG_WIDTH_UNIT"):
        result = build_geometry_check_inputs_from_feature_snapshot(_snapshot_by_component(component_id))
        assert {diagnostic.status for diagnostic in result.diagnostics}.isdisjoint({"OK", "FAIL"})


def test_engine_returns_ok_for_column_width_depth_at_or_above_300_mm():
    snapshot = _snapshot_by_component("C_OK")
    adapter = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    definitions = _read_yaml(CHECK_OVERLAY)["checks"]
    definitions["column_geometry_min_dimension"] = {
        "element_type": "column",
        "required_features": ["column_width_mm", "column_depth_mm"],
        "code_ref": "contract",
    }
    engine = MinimalCheckEngine(definitions)

    statuses = {
        check_input.check_id: engine.run_check(check_input.check_id, check_input.snapshot, check_input.coverage).status.value
        for check_input in adapter.check_inputs
    }

    assert statuses["column_geometry_min_width"] == "OK"
    assert statuses["column_geometry_min_depth"] == "OK"


def test_engine_returns_fail_for_resolved_width_or_depth_below_300_mm():
    definitions = _read_yaml(CHECK_OVERLAY)["checks"]
    definitions["column_geometry_min_dimension"] = {
        "element_type": "column",
        "required_features": ["column_width_mm", "column_depth_mm"],
        "code_ref": "contract",
    }
    engine = MinimalCheckEngine(definitions)

    width_adapter = build_geometry_check_inputs_from_feature_snapshot(_snapshot_by_component("C_BAD_WIDTH"))
    depth_adapter = build_geometry_check_inputs_from_feature_snapshot(_snapshot_by_component("C_BAD_DEPTH"))
    width_status = {
        item.check_id: engine.run_check(item.check_id, item.snapshot, item.coverage).status.value
        for item in width_adapter.check_inputs
    }
    depth_status = {
        item.check_id: engine.run_check(item.check_id, item.snapshot, item.coverage).status.value
        for item in depth_adapter.check_inputs
    }

    assert width_status["column_geometry_min_width"] == "FAIL"
    assert width_status["column_geometry_min_depth"] == "OK"
    assert depth_status["column_geometry_min_width"] == "OK"
    assert depth_status["column_geometry_min_depth"] == "FAIL"


def test_p4_geometry_vertical_slice_emits_six_canonical_check_results(tmp_path: Path):
    result = run_geometry_vertical_slice_from_file(feature_snapshot_path=CANONICAL_FIXTURE, output_dir=tmp_path)

    assert len(result.check_results) == 6
    assert result.run_summary["check_result_count"] == 6
    assert result.run_summary["check_result_status_counts"] == {"OK": 6}
    assert result.run_summary["adapter_diagnostic_count"] == 0


def test_p5_report_includes_new_column_check_rows(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    run_geometry_vertical_slice_from_file(feature_snapshot_path=CANONICAL_FIXTURE, output_dir=artifact_dir)
    report_path = tmp_path / "report.md"

    render_geometry_markdown_report_from_artifact_dir(artifact_dir=artifact_dir, output_path=report_path)
    report = report_path.read_text(encoding="utf-8")

    assert "Table name: column_geometry_detail" in report
    assert "column_geometry_min_dimension" in report
    assert "column_geometry_min_width" in report
    assert "column_geometry_min_depth" in report


def test_p6_product_smoke_p7_bundle_validator_and_p8_golden_regression_accept_six_checks(tmp_path: Path):
    product_dir = tmp_path / "product"
    product = run_geometry_product_smoke(feature_snapshot_path=CANONICAL_FIXTURE, output_dir=product_dir)

    assert product.p4_check_result_count == 6
    validation = validate_geometry_product_bundle(
        bundle_dir=product_dir,
        validation_output_path=product_dir / "geometry_product_bundle_validation.json",
    )
    assert validation.status == "OK"
    assert validation.check_result_count == 6

    regression = run_geometry_golden_regression(
        feature_snapshot_path=CANONICAL_FIXTURE,
        output_dir=tmp_path / "golden",
        golden_fingerprint_path=GOLDEN,
    )
    assert regression.status == "OK"
    assert len(regression.actual_fingerprint["checks"]) == 6


def test_p9_offline_acceptance_includes_c13_5_p1_before_golden_regression(tmp_path: Path):
    plan = build_offline_acceptance_command_plan(output_dir=tmp_path, python_executable="PY")

    assert len(plan) == 13
    assert plan[-2] == ("pytest_c13_5_p1", ("PY", "-m", "pytest", "-q", "tests/c13_5_p1"))
    assert plan[-1][0] == "p8_golden_regression"


def test_p10_workflow_still_delegates_to_p9_cli_only():
    workflow = (ROOT / ".github" / "workflows" / "c13_4_offline_acceptance.yml").read_text(encoding="utf-8")

    assert "python tools/run_offline_product_acceptance.py --out local_out/c13_4_ci_offline_acceptance" in workflow
    assert "tests/c13_5_p1" not in workflow
    assert "tools/run_geometry_golden_regression.py" not in workflow
