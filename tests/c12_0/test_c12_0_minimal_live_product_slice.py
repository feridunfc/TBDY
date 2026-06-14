from __future__ import annotations

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_live_minimal_product_slice.py"
OUT = ROOT / "local_out" / "c12_0_fixture_product_slice_test"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _run_fixture_slice() -> Path:
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--out",
            str(OUT),
            "--fixture-mode",
            "--design-context",
            "tests/fixtures/c10_design_context_fixture.json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return OUT


def test_c12_0_tool_exists():
    assert TOOL.is_file()


def test_c12_0_fixture_mode_does_not_call_live_etabs():
    out = _run_fixture_slice()
    manifest = _read_json(out / "product_slice_manifest.json")
    command_log = _read_json(out / "command_log.json")
    assert manifest["fixture_mode"] is True
    assert manifest["live_etabs_requested"] is False
    c8_commands = [entry["command"] for entry in command_log["commands"] if any("smoke_live_feature_resolver.py" in str(part) for part in entry["command"])]
    assert c8_commands
    flattened = " ".join(c8_commands[0])
    assert "--input" in flattened
    assert "--live-etabs" not in flattened


def test_c12_0_fixture_mode_writes_required_outputs():
    out = _run_fixture_slice()
    for filename in [
        "product_slice_manifest.json",
        "acceptance_summary.json",
        "feature_snapshot.json",
        "coverage_matrix.json",
        "feature_snapshot_with_context.json",
        "check_results.json",
        "c11_boundary_report.json",
        "baseline_guard_report.json",
        "command_log.json",
    ]:
        assert (out / filename).is_file(), filename


def test_c12_0_manifest_schema():
    manifest = _read_json(_run_fixture_slice() / "product_slice_manifest.json")
    required = {
        "sprint",
        "live_etabs_requested",
        "target_component",
        "target_label",
        "target_story",
        "target_section",
        "preferred_output_case",
        "design_context_path",
        "baseline_guard_passed",
        "feature_snapshot_path",
        "coverage_matrix_path",
        "check_results_path",
        "check_result_count",
        "ok_count",
        "fail_count",
        "no_data_count",
        "warning_count",
        "live_feature_status_counts",
        "coverage_status_counts",
        "c11_boundary",
        "rebar_flexure_shear_capacity_unlocked",
        "excel_production_path_used",
        "streamlit_ui_used",
        "legacy_runtime_used",
        "product_slice_passed",
    }
    assert required.issubset(manifest)
    assert manifest["sprint"] == "C12.0_MINIMAL_LIVE_PRODUCT_SLICE"
    assert manifest["product_slice_passed"] is True


def test_c12_0_acceptance_summary_schema():
    summary = _read_json(_run_fixture_slice() / "acceptance_summary.json")
    required = {
        "baseline_guard_passed",
        "feature_snapshot_all_resolved",
        "current_resolved_features_covered",
        "c11_dry_run_still_3_OK",
        "check_result_count",
        "ok_count",
        "fail_count",
        "legacy_import_audit_clean",
        "feature_snapshot_schema_valid",
        "etabs_feature_source_contract_valid",
        "no_new_engineering_unlocked",
        "product_slice_passed",
    }
    assert required.issubset(summary)
    assert summary["product_slice_passed"] is True


def test_c12_0_check_results_still_3_ok():
    out = _run_fixture_slice()
    manifest = _read_json(out / "product_slice_manifest.json")
    results = _read_json(out / "check_results.json")
    assert len(results) == 3
    assert manifest["check_result_count"] == 3
    assert manifest["ok_count"] == 3
    assert manifest["fail_count"] == 0


def test_c12_0_feature_snapshot_schema_still_valid():
    out = _run_fixture_slice()
    schema = _read_json(ROOT / "tbdy_engine/catalogs/schemas/feature_snapshot.schema.json")
    payload = _read_json(out / "feature_snapshot.json")
    Draft202012Validator(schema).validate(payload)


def test_c12_0_etabs_source_contract_still_valid():
    schema = _read_json(ROOT / "tbdy_engine/catalogs/schemas/etabs_feature_source_contract.schema.json")
    contract = yaml.safe_load((ROOT / "tbdy_engine/catalogs/etabs_feature_source_contract.yaml").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(contract)
    entries = {row["feature_id"] for row in contract["sources"]}
    snapshot = _read_json(_run_fixture_slice() / "feature_snapshot.json")
    resolved = {
        feature_id
        for item in snapshot["snapshots"]
        for feature_id, feature in item["features"].items()
        if feature.get("status") == "RESOLVED"
    }
    assert len(resolved) == 28
    assert resolved.issubset(entries)


def test_c12_0_legacy_import_audit_clean():
    baseline = _read_json(_run_fixture_slice() / "baseline_guard_report.json")
    assert baseline["legacy_import_audit_clean"] is True
    assert baseline["forbidden_imports_found"] is False
    assert baseline["active_runtime_violations"] == 0
    assert baseline["excel_production_path_violations"] == 0


def test_c12_0_no_rebar_flexure_shear_capacity_unlock():
    manifest = _read_json(_run_fixture_slice() / "product_slice_manifest.json")
    boundary = _read_json(_run_fixture_slice() / "c11_boundary_report.json")
    assert manifest["rebar_flexure_shear_capacity_unlocked"] is False
    assert boundary["rebar_selection_executed"] is False
    assert boundary["beam_flexure_executed"] is False
    assert boundary["beam_shear_executed"] is False


def test_c12_0_no_excel_production_path():
    manifest = _read_json(_run_fixture_slice() / "product_slice_manifest.json")
    assert manifest["excel_production_path_used"] is False


def test_c12_0_no_streamlit_ui_path():
    manifest = _read_json(_run_fixture_slice() / "product_slice_manifest.json")
    assert manifest["streamlit_ui_used"] is False


def test_c12_0_check_engine_boundary_preserved():
    boundary = _read_json(_run_fixture_slice() / "c11_boundary_report.json")
    assert boundary["live_etabs_called"] is False
    assert boundary["provider_called"] is False
    assert boundary["feature_resolver_called"] is False
    assert boundary["check_engine_executed"] is True
    assert boundary["partial_rows_silent_OK"] is False
