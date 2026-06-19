from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
EXPECTED_TABLE_NAMES = [
    "executive_summary",
    "geometry_check_summary",
    "adapter_diagnostics",
    "beam_geometry_detail",
    "column_geometry_detail",
    "evidence_trace_detail",
    "artifact_manifest",
    "guardrails",
    "boundary_notes",
]


def _bundle(tmp_path: Path) -> Path:
    bundle_dir = tmp_path / "bundle"
    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=bundle_dir)
    return bundle_dir


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_validator_passes_on_p6_generated_bundle(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    validation_path = bundle_dir / "geometry_product_bundle_validation.json"

    result = validate_geometry_product_bundle(bundle_dir=bundle_dir, validation_output_path=validation_path)

    assert result.status == "OK"
    assert result.error_count == 0
    assert result.required_file_count == 7
    assert result.checked_table_count == 9
    assert result.check_result_count == 6
    assert result.adapter_diagnostic_count == 0


def test_validator_writes_geometry_product_bundle_validation_json(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    validation_path = bundle_dir / "geometry_product_bundle_validation.json"

    validate_geometry_product_bundle(bundle_dir=bundle_dir, validation_output_path=validation_path)
    payload = _read_json(validation_path)

    assert validation_path.is_file()
    assert payload["status"] == "OK"
    assert payload["scope"] == "GEOMETRY_PRODUCT_BUNDLE_VALIDATION"
    assert payload["bundle_dir"] == str(bundle_dir)
    assert payload["required_files"] == {
        "artifacts/adapter_diagnostics.json": "OK",
        "artifacts/check_results.json": "OK",
        "artifacts/run_manifest.json": "OK",
        "artifacts/run_summary.json": "OK",
        "product_smoke_manifest.json": "OK",
        "product_smoke_summary.json": "OK",
        "reports/geometry_report.md": "OK",
    }
    assert payload["counts"]["check_result_count"] == 6
    assert payload["counts"]["adapter_diagnostic_count"] == 0
    assert payload["counts"]["report_table_count"] == 9
    assert payload["counts"]["error_count"] == 0


def test_cli_validates_p6_generated_bundle(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)

    completed = subprocess.run(
        [sys.executable, "tools/validate_geometry_product_bundle.py", "--bundle-dir", str(bundle_dir)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Geometry product bundle validation: OK" in completed.stdout
    assert f"Bundle: {bundle_dir}" in completed.stdout
    assert "Required files: 7" in completed.stdout
    assert "CheckResults: 6" in completed.stdout
    assert "Adapter diagnostics: 0" in completed.stdout
    assert "Report tables: 9" in completed.stdout
    assert "Errors: 0" in completed.stdout
    assert f"Validation: {bundle_dir / 'geometry_product_bundle_validation.json'}" in completed.stdout


def test_summary_contract_values_are_validated(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)

    validate_geometry_product_bundle(
        bundle_dir=bundle_dir,
        validation_output_path=bundle_dir / "geometry_product_bundle_validation.json",
    )
    summary = _read_json(bundle_dir / "product_smoke_summary.json")
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")

    assert summary["status"] == "OK"
    assert summary["scope"] == "GEOMETRY_ONLY_PRODUCT_SMOKE"
    assert summary["p5"]["table_names"] == EXPECTED_TABLE_NAMES
    assert validation["checks"]["summary_contract"] == "OK"


def test_manifest_guardrails_are_validated(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)

    validate_geometry_product_bundle(
        bundle_dir=bundle_dir,
        validation_output_path=bundle_dir / "geometry_product_bundle_validation.json",
    )
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")

    assert validation["checks"]["manifest_contract"] == "OK"
    assert validation["checks"]["guardrail_contract"] == "OK"


def test_counts_match_run_summary_and_product_smoke_summary(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)

    validate_geometry_product_bundle(
        bundle_dir=bundle_dir,
        validation_output_path=bundle_dir / "geometry_product_bundle_validation.json",
    )
    check_results = _read_json(bundle_dir / "artifacts" / "check_results.json")
    adapter_diagnostics = _read_json(bundle_dir / "artifacts" / "adapter_diagnostics.json")
    run_summary = _read_json(bundle_dir / "artifacts" / "run_summary.json")
    product_summary = _read_json(bundle_dir / "product_smoke_summary.json")

    assert len(check_results) == run_summary["check_result_count"] == product_summary["p4"]["check_result_count"] == 6
    assert len(adapter_diagnostics) == run_summary["adapter_diagnostic_count"] == product_summary["p4"]["adapter_diagnostic_count"] == 0
    assert product_summary["p4"]["check_result_status_counts"] == run_summary["check_result_status_counts"]


def test_forbidden_terms_in_manifest_forbidden_scope_are_allowed(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)

    result = validate_geometry_product_bundle(
        bundle_dir=bundle_dir,
        validation_output_path=bundle_dir / "geometry_product_bundle_validation.json",
    )
    manifest = _read_json(bundle_dir / "product_smoke_manifest.json")

    assert result.status == "OK"
    assert "beam_flexure" in manifest["forbidden_scope"]
    assert "capacity_design" in manifest["forbidden_scope"]
    assert "modal_mass" in manifest["forbidden_scope"]


def test_output_validation_json_is_deterministic_across_repeated_runs(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    validation_path = bundle_dir / "geometry_product_bundle_validation.json"

    validate_geometry_product_bundle(bundle_dir=bundle_dir, validation_output_path=validation_path)
    first = validation_path.read_text(encoding="utf-8")
    validate_geometry_product_bundle(bundle_dir=bundle_dir, validation_output_path=validation_path)
    second = validation_path.read_text(encoding="utf-8")

    assert first == second
    assert first.endswith("\n")
