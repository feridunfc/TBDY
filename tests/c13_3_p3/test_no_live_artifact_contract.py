from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.features.check_preflight_diagnostics import build_check_preflight_diagnostic_report
from tbdy_engine.features.feature_snapshot_artifact_validator import (
    REQUIRED_ARTIFACT_FILES,
    REQUIRED_GUARDRAILS,
    REQUIRED_SOURCE_FAMILIES,
    scan_for_forbidden_engineering_verdicts,
    validate_artifact_file_set,
    validate_check_preflight_diagnostic_report,
    validate_feature_snapshot_artifact_manifest,
    validate_feature_snapshot_report_payload,
)
from tbdy_engine.features.feature_snapshot_artifacts import (
    build_feature_snapshot_artifact_manifest,
    build_feature_snapshot_report_payload,
    render_feature_snapshot_html_report,
    render_feature_snapshot_markdown_report,
)
from tbdy_engine.features.resolver_feature_snapshot import build_feature_snapshot_from_source_rows, source_family_projection_report
from tbdy_engine.features.source_feature_snapshot_builder import fixture_source_rows
import tools.smoke_c13_3_p3_no_live_artifact_contract as smoke

ROOT = Path(__file__).resolve().parents[2]


def snapshot():
    return build_feature_snapshot_from_source_rows(
        fixture_source_rows(),
        live_etabs_connected=False,
        model_path=None,
        etabs_version=None,
        target_family="all",
        generated_at="2026-06-17T00:00:00+00:00",
    )


def report_payload():
    return build_feature_snapshot_report_payload(snapshot())


def artifact_manifest():
    manifest = build_feature_snapshot_artifact_manifest(
        snapshot=snapshot(),
        output_files=smoke.OUTPUT_FILES,
        generated_at="2026-06-17T00:00:00+00:00",
    )
    manifest["sprint"] = "C13.3-P3"
    manifest["artifact_roles"].update({
        "check_preflight_diagnostic_report.json": "diagnostic-only check preflight contract",
        "artifact_contract_validation_report.json": "no-live artifact contract validation report",
    })
    return manifest


def test_no_etabs_import_or_live_call_is_required():
    imports = _imports_for(ROOT / "tools/smoke_c13_3_p3_no_live_artifact_contract.py")
    assert "comtypes.client" not in imports
    assert "win32com.client" not in imports
    assert "tbdy_engine.providers.etabs_display_table_fetcher" not in imports


def test_report_payload_validates_and_keeps_guardrails_false():
    result = validate_feature_snapshot_report_payload(report_payload())
    assert result["validation_status"] == "VALID"
    assert result["missing_required_fields"] == []
    assert result["forbidden_terms_found"] == []
    assert result["guardrail_errors"] == []
    assert result["safe_to_implement_checks_now"] is False
    assert result["check_unlock_allowed"] is False
    assert result["engineering_verdicts_emitted"] is False
    payload = report_payload()
    for family in REQUIRED_SOURCE_FAMILIES:
        assert family in payload["source_family_counts"]
    guardrail_ids = {item["feature_id"] for item in payload["blocked_guardrails"]}
    assert set(REQUIRED_GUARDRAILS).issubset(guardrail_ids)


def test_artifact_manifest_validates_and_contains_roles():
    manifest = artifact_manifest()
    result = validate_feature_snapshot_artifact_manifest(manifest)
    assert result["validation_status"] == "VALID"
    assert set(smoke.OUTPUT_FILES).issubset(manifest["artifact_roles"])
    assert manifest["engineering_verdicts_emitted"] is False
    assert manifest["check_results_emitted"] is False
    assert manifest["excel_production_input_used"] is False
    assert manifest["safe_to_implement_checks_now"] is False
    assert manifest["check_unlock_allowed"] is False


def test_check_preflight_diagnostic_validates_and_is_diagnostic_only():
    report = build_check_preflight_diagnostic_report(report_payload())
    result = validate_check_preflight_diagnostic_report(report)
    assert result["validation_status"] == "VALID"
    assert report["diagnostic_only"] is True
    assert report["check_engine_invoked"] is False
    assert report["checks_locked"] is True
    assert report["source_evidence_only"] is True
    assert report["safe_to_implement_checks_now"] is False
    assert report["check_unlock_allowed"] is False
    assert report["engineering_verdicts_emitted"] is False
    assert report["check_results_emitted"] is False
    assert report["excel_production_input_used"] is False
    group_ids = {item["group_id"] for item in report["prospective_check_groups"]}
    assert {"material_compliance", "story_drift_torsion_force", "pier_wall_force_capacity_detailing"}.issubset(group_ids)
    for group in report["prospective_check_groups"]:
        assert group["current_status"] in {"CHECKS_LOCKED", "NOT_READY_FOR_CHECK"}
        assert group["check_engine_invoked"] is False
        assert group["engineering_verdict_emitted"] is False


def test_forbidden_verdict_scanner_catches_bad_strings():
    result = scan_for_forbidden_engineering_verdicts("member is PASS and utilization ratio is present")
    assert result["validation_status"] == "INVALID"
    terms = {item["term"] for item in result["forbidden_terms_found"]}
    assert "PASS" in terms
    assert "utilization ratio" in terms


def test_generated_json_markdown_html_have_no_forbidden_terms():
    payload = report_payload()
    manifest = artifact_manifest()
    preflight = build_check_preflight_diagnostic_report(payload)
    rendered = json.dumps(payload, sort_keys=True)
    rendered += json.dumps(manifest, sort_keys=True)
    rendered += json.dumps(preflight, sort_keys=True)
    rendered += render_feature_snapshot_markdown_report(payload)
    rendered += render_feature_snapshot_html_report(payload)
    result = scan_for_forbidden_engineering_verdicts(rendered)
    assert result["validation_status"] == "VALID"
    assert result["forbidden_terms_found"] == []


def test_smoke_tool_exits_0_without_etabs_and_writes_required_files(tmp_path):
    out = tmp_path / "c13_3_p3"
    result = subprocess.run(
        [sys.executable, "tools/smoke_c13_3_p3_no_live_artifact_contract.py", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(REQUIRED_ARTIFACT_FILES) == {path.name for path in out.iterdir()}
    connection = json.loads((out / "connection_report.json").read_text(encoding="utf-8"))
    assert connection["live_etabs_requested"] is False
    assert connection["live_etabs_connected"] is False
    assert connection["connection_status"] == "NO_LIVE_REQUESTED"
    assert connection["feature_values_faked"] is False
    assert connection["fixture_values_used"] is True
    validation = json.loads((out / "artifact_contract_validation_report.json").read_text(encoding="utf-8"))
    assert validation["validation_status"] == "VALID"
    assert validation["forbidden_terms_found"] == []
    assert validation["safe_to_implement_checks_now"] is False
    assert validation["check_unlock_allowed"] is False


def test_validator_cli_accepts_generated_artifacts(tmp_path):
    out = tmp_path / "c13_3_p3"
    smoke.main(["--out", str(out), "--fixture", "minimal"])
    result = subprocess.run(
        [sys.executable, "tools/validate_c13_3_p3_artifact_contract.py", "--artifact-dir", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    validation = json.loads(result.stdout)
    assert validation["validation_status"] == "VALID"
    assert validation["missing_required_files"] == []
    assert validation["forbidden_terms_found"] == []


def test_artifact_file_set_validator_rejects_missing_files(tmp_path):
    out = tmp_path / "empty"
    out.mkdir()
    result = validate_artifact_file_set(out)
    assert result["validation_status"] == "INVALID"
    assert "connection_report.json" in result["missing_required_files"]


def test_deterministic_repeated_generation_for_same_inputs():
    payload_1 = report_payload()
    payload_2 = report_payload()
    assert payload_1 == payload_2
    manifest_1 = artifact_manifest()
    manifest_2 = artifact_manifest()
    assert manifest_1 == manifest_2
    assert render_feature_snapshot_markdown_report(payload_1) == render_feature_snapshot_markdown_report(payload_2)
    assert render_feature_snapshot_html_report(payload_1) == render_feature_snapshot_html_report(payload_2)
    assert build_check_preflight_diagnostic_report(payload_1) == build_check_preflight_diagnostic_report(payload_2)


def test_p2_artifact_api_remains_backward_compatible():
    payload = build_feature_snapshot_report_payload(snapshot())
    manifest = build_feature_snapshot_artifact_manifest(
        snapshot=snapshot(),
        output_files=["feature_snapshot.json", "feature_snapshot_report_payload.json"],
        generated_at="2026-06-17T00:00:00+00:00",
    )
    assert payload["sprint"] == "C13.3-P2"
    assert manifest["artifact_contract_version"]
    assert render_feature_snapshot_markdown_report(payload)
    assert render_feature_snapshot_html_report(payload)


def test_p1_resolver_api_remains_backward_compatible():
    snap = snapshot()
    assert snap["sprint"] == "C13.3-P1"
    assert snap["feature_records"]
    report = source_family_projection_report(snap)
    assert set(REQUIRED_SOURCE_FAMILIES).issubset(set(report["projected_families"]))
    assert report["check_unlock_allowed"] is False


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_no_imports_from_checks_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/feature_snapshot_artifact_validator.py",
        ROOT / "tbdy_engine/features/check_preflight_diagnostics.py",
        ROOT / "tools/smoke_c13_3_p3_no_live_artifact_contract.py",
        ROOT / "tools/validate_c13_3_p3_artifact_contract.py",
    ]
    for path in touched:
        assert not any(name.startswith("tbdy_engine.checks") for name in _imports_for(path))


def test_no_streamlit_app_or_excel_production_path_is_introduced():
    touched = [
        ROOT / "tbdy_engine/features/feature_snapshot_artifact_validator.py",
        ROOT / "tbdy_engine/features/check_preflight_diagnostics.py",
        ROOT / "tools/smoke_c13_3_p3_no_live_artifact_contract.py",
        ROOT / "tools/validate_c13_3_p3_artifact_contract.py",
    ]
    forbidden_imports = {"streamlit", "apps", "tbdy_engine.apps", "tbdy_engine.reporting", "tbdy_engine.report", "comtypes.client", "win32com.client"}
    for path in touched:
        assert not forbidden_imports.intersection(_imports_for(path))
    text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in touched)
    assert "read_excel" not in text
    assert "openpyxl" not in text
    assert "excel_production_input: true" not in text
