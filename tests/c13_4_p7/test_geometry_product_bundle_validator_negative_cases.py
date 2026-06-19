from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke
from tools.audit_legacy_boundary import build_report

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_4_p4" / "geometry_feature_snapshots.json"
VALIDATOR_MODULE = ROOT / "tbdy_engine" / "product" / "bundle_validator.py"
CLI_SCRIPT = ROOT / "tools" / "validate_geometry_product_bundle.py"
FORBIDDEN_IMPORT_PATHS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
)
FORBIDDEN_DIRECT_CALLS = (
    "MinimalCheckEngine",
    "build_geometry_check_inputs_from_feature_snapshot",
    "run_geometry_vertical_slice_from_file",
    "render_geometry_markdown_report_from_artifact_dir",
)


def _bundle(tmp_path: Path) -> Path:
    bundle_dir = tmp_path / "bundle"
    run_geometry_product_smoke(feature_snapshot_path=FIXTURE, output_dir=bundle_dir)
    return bundle_dir


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate(bundle_dir: Path):
    return validate_geometry_product_bundle(
        bundle_dir=bundle_dir,
        validation_output_path=bundle_dir / "geometry_product_bundle_validation.json",
    )


def test_adapter_diagnostic_status_ok_or_fail_causes_validation_fail(tmp_path: Path):
    for status in ("OK", "FAIL"):
        bundle_dir = _bundle(tmp_path / status)
        _write_json(
            bundle_dir / "artifacts" / "adapter_diagnostics.json",
            [
                {
                    "check_id": "beam_geometry_min_width",
                    "component_id": "B1",
                    "component_type": "beam",
                    "invalid_features": [],
                    "missing_features": [],
                    "reason": "invalid fixture",
                    "status": status,
                }
            ],
        )
        run_summary = _read_json(bundle_dir / "artifacts" / "run_summary.json")
        run_summary["adapter_diagnostic_count"] = 1
        _write_json(bundle_dir / "artifacts" / "run_summary.json", run_summary)
        product_summary = _read_json(bundle_dir / "product_smoke_summary.json")
        product_summary["p4"]["adapter_diagnostic_count"] = 1
        _write_json(bundle_dir / "product_smoke_summary.json", product_summary)

        result = _validate(bundle_dir)

        assert result.status == "FAIL"
        assert result.error_count > 0
        validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
        assert any("Adapter diagnostic status" in message for message in validation["errors"])


def test_missing_required_file_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    (bundle_dir / "artifacts" / "run_manifest.json").unlink()

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert validation["required_files"]["artifacts/run_manifest.json"] == "MISSING"
    assert any("Missing required file" in message for message in validation["errors"])


def test_invalid_json_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    (bundle_dir / "artifacts" / "run_summary.json").write_text("{invalid", encoding="utf-8")

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert validation["checks"]["json_parse"] == "FAIL"
    assert any("Invalid JSON" in message for message in validation["errors"])


def test_wrong_report_title_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    report_path = bundle_dir / "reports" / "geometry_report.md"
    report_path.write_text(report_path.read_text(encoding="utf-8").replace("# TBDY Geometry Vertical Slice Report — C13.4-P5", "# Wrong Report"), encoding="utf-8")

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert validation["checks"]["p5_report_contract"] == "FAIL"
    assert any("report title" in message for message in validation["errors"])


def test_missing_table_name_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    report_path = bundle_dir / "reports" / "geometry_report.md"
    report_path.write_text(report_path.read_text(encoding="utf-8").replace("Table name: evidence_trace_detail", "Table name: removed_evidence_trace_detail"), encoding="utf-8")

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert any("Missing report table marker" in message for message in validation["errors"])


def test_out_of_order_table_names_cause_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    report_path = bundle_dir / "reports" / "geometry_report.md"
    report = report_path.read_text(encoding="utf-8")
    report = report.replace("Table name: executive_summary", "Table name: TEMP_TABLE")
    report = report.replace("Table name: geometry_check_summary", "Table name: executive_summary")
    report = report.replace("Table name: TEMP_TABLE", "Table name: geometry_check_summary")
    report_path.write_text(report, encoding="utf-8")

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert any("required order" in message for message in validation["errors"])


def test_wrong_guardrail_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    manifest_path = bundle_dir / "product_smoke_manifest.json"
    manifest = _read_json(manifest_path)
    manifest["guardrails"]["etabs_live_fetching_used"] = True
    _write_json(manifest_path, manifest)

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert validation["checks"]["guardrail_contract"] == "FAIL"
    assert any("Guardrail etabs_live_fetching_used" in message for message in validation["errors"])


def test_wrong_summary_count_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    summary_path = bundle_dir / "product_smoke_summary.json"
    summary = _read_json(summary_path)
    summary["p4"]["check_result_count"] = 999
    _write_json(summary_path, summary)

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert any("product_smoke_summary.p4.check_result_count" in message for message in validation["errors"])


def test_non_canonical_check_result_status_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    check_results_path = bundle_dir / "artifacts" / "check_results.json"
    check_results = _read_json(check_results_path)
    check_results[0]["status"] = "PASS"
    _write_json(check_results_path, check_results)

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert any("Non-canonical CheckResult status" in message for message in validation["errors"])


def test_forbidden_term_in_product_smoke_summary_causes_validation_fail(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    summary_path = bundle_dir / "product_smoke_summary.json"
    summary = _read_json(summary_path)
    summary["final_building_compliance"] = False
    _write_json(summary_path, summary)

    result = _validate(bundle_dir)

    assert result.status == "FAIL"
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert validation["checks"]["forbidden_scope_contract"] == "FAIL"
    assert any("final_building_compliance" in message for message in validation["errors"])


def test_extra_unrelated_file_produces_warning_not_error(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    (bundle_dir / "extra.txt").write_text("extra", encoding="utf-8")

    result = _validate(bundle_dir)

    assert result.status == "OK"
    assert result.error_count == 0
    assert result.warning_count == 1
    validation = _read_json(bundle_dir / "geometry_product_bundle_validation.json")
    assert any("Extra non-contract file" in message for message in validation["warnings"])


def test_validator_module_does_not_import_forbidden_legacy_paths():
    module_text = VALIDATOR_MODULE.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in module_text


def test_validator_cli_does_not_import_forbidden_legacy_paths():
    cli_text = CLI_SCRIPT.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in cli_text


def test_validator_module_does_not_import_or_call_lower_pipeline_apis():
    module_text = VALIDATOR_MODULE.read_text(encoding="utf-8")

    for forbidden_call in FORBIDDEN_DIRECT_CALLS:
        assert forbidden_call not in module_text


def test_legacy_boundary_audit_scans_bundle_validator_module():
    report = build_report()

    assert "tbdy_engine/product/bundle_validator.py" in report["checked_files"]
    validator_blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker["file"] == "tbdy_engine/product/bundle_validator.py"
    ]
    assert validator_blockers == []
