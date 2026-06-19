from __future__ import annotations

from types import SimpleNamespace
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.product import golden_regression
from tbdy_engine.product.golden_regression import run_geometry_golden_regression
from tools.audit_legacy_boundary import build_report

ROOT = Path(__file__).resolve().parents[2]
FEATURE_SNAPSHOT = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
GOLDEN = ROOT / "tests" / "fixtures" / "c13_4_p8" / "golden_geometry_product_fingerprint.json"
MODULE_PATH = ROOT / "tbdy_engine" / "product" / "golden_regression.py"
CLI_PATH = ROOT / "tools" / "run_geometry_golden_regression.py"
FORBIDDEN_IMPORT_PATHS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)
FORBIDDEN_LOWER_PIPELINE_NAMES = (
    "MinimalCheckEngine",
    "build_geometry_check_inputs_from_feature_snapshot",
    "run_geometry_vertical_slice_from_file",
    "render_geometry_markdown_report_from_artifact_dir",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_modified_golden(tmp_path: Path, mutate) -> Path:
    payload = _read_json(GOLDEN)
    mutate(payload)
    path = tmp_path / "modified_golden.json"
    _write_json(path, payload)
    return path


def test_missing_golden_fingerprint_file_causes_fail_and_nonzero_cli_exit(tmp_path: Path):
    missing_golden = tmp_path / "missing_golden.json"
    out_dir = tmp_path / "missing_golden_run"

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=out_dir,
        golden_fingerprint_path=missing_golden,
    )
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_golden_regression.py",
            "--feature-snapshot",
            str(FEATURE_SNAPSHOT),
            "--golden",
            str(missing_golden),
            "--out",
            str(tmp_path / "missing_golden_cli"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.status == "FAIL"
    assert result.error_count > 0
    assert completed.returncode != 0
    assert "Geometry golden regression: FAIL" in completed.stdout


def test_invalid_golden_fingerprint_json_causes_fail_and_nonzero_cli_exit(tmp_path: Path):
    invalid_golden = tmp_path / "invalid_golden.json"
    invalid_golden.write_text("{invalid", encoding="utf-8")

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=tmp_path / "invalid_golden_run",
        golden_fingerprint_path=invalid_golden,
    )
    completed = subprocess.run(
        [
            sys.executable,
            "tools/run_geometry_golden_regression.py",
            "--feature-snapshot",
            str(FEATURE_SNAPSHOT),
            "--golden",
            str(invalid_golden),
            "--out",
            str(tmp_path / "invalid_golden_cli"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.status == "FAIL"
    assert any("Invalid golden fingerprint JSON" in message for message in _read_json(result.regression_report_path)["errors"])
    assert completed.returncode != 0
    assert "Geometry golden regression: FAIL" in completed.stdout


def test_modified_expected_golden_check_value_causes_fail(tmp_path: Path):
    golden = _copy_modified_golden(tmp_path, lambda payload: payload["checks"][0].update({"value": 999.0}))

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=tmp_path / "modified_value_run",
        golden_fingerprint_path=golden,
    )
    report = _read_json(result.regression_report_path)

    assert result.status == "FAIL"
    assert result.difference_count > 0
    assert "Golden fingerprint mismatch" in report["errors"]
    assert "Mismatch at key: checks" in report["differences"]


def test_modified_expected_table_name_order_causes_fail(tmp_path: Path):
    def mutate(payload):
        names = payload["report"]["table_names"]
        names[0], names[1] = names[1], names[0]

    golden = _copy_modified_golden(tmp_path, mutate)

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=tmp_path / "modified_table_run",
        golden_fingerprint_path=golden,
    )
    report = _read_json(result.regression_report_path)

    assert result.status == "FAIL"
    assert "Golden fingerprint mismatch" in report["errors"]
    assert "Mismatch at key: report" in report["differences"]


def test_p7_validation_failure_causes_p8_fail(tmp_path: Path, monkeypatch):
    original_validator = golden_regression.validate_geometry_product_bundle

    def fake_validator(*, bundle_dir: Path, validation_output_path: Path):
        result = original_validator(bundle_dir=bundle_dir, validation_output_path=validation_output_path)
        payload = _read_json(validation_output_path)
        payload["status"] = "FAIL"
        payload["counts"]["error_count"] = 1
        payload["errors"] = ["injected validation failure"]
        _write_json(validation_output_path, payload)
        return SimpleNamespace(status="FAIL")

    monkeypatch.setattr(golden_regression, "validate_geometry_product_bundle", fake_validator)

    result = run_geometry_golden_regression(
        feature_snapshot_path=FEATURE_SNAPSHOT,
        output_dir=tmp_path / "p7_fail_run",
        golden_fingerprint_path=GOLDEN,
    )
    report = _read_json(result.regression_report_path)

    assert result.status == "FAIL"
    assert any("P7 bundle validation failed" in message for message in report["errors"])


def test_p8_module_does_not_import_forbidden_legacy_paths():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in module_text


def test_p8_cli_does_not_import_forbidden_legacy_paths():
    cli_text = CLI_PATH.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in cli_text


def test_p8_module_does_not_import_lower_pipeline_apis():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden_name in FORBIDDEN_LOWER_PIPELINE_NAMES:
        assert forbidden_name not in module_text


def test_p8_module_imports_p6_and_p7_apis():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    assert "run_geometry_product_smoke" in module_text
    assert "validate_geometry_product_bundle" in module_text


def test_legacy_boundary_audit_scans_golden_regression_module():
    report = build_report()

    assert "tbdy_engine/product/golden_regression.py" in report["checked_files"]
    blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker["file"] == "tbdy_engine/product/golden_regression.py"
    ]
    assert blockers == []
