from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.features.feature_snapshot_artifacts import (
    ARTIFACT_CONTRACT_VERSION,
    build_feature_snapshot_artifact_manifest,
    build_feature_snapshot_report_payload,
    render_feature_snapshot_html_report,
    render_feature_snapshot_markdown_report,
)
from tbdy_engine.features.readiness import FORBIDDEN_ENGINEERING_VERDICT_TOKENS
from tbdy_engine.features.resolver_feature_snapshot import build_feature_snapshot_from_source_rows, source_family_projection_report
from tbdy_engine.features.source_feature_snapshot_builder import INTERNAL_SOURCE_TABLE_KEY, fixture_source_rows
import tools.smoke_c13_3_p2_feature_snapshot_artifacts as smoke

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FILES = smoke.OUTPUT_FILES
LOCKED_IDS = {
    "material_compliance_locked",
    "story_drift_torsion_force_locked",
    "pier_wall_force_capacity_detailing_locked",
}


def snapshot():
    return build_feature_snapshot_from_source_rows(
        fixture_source_rows(),
        live_etabs_connected=True,
        model_path="C:/tmp/B-BLOK_Revised.EDB",
        etabs_version="23.2.0",
        target_family="all",
        generated_at="2026-06-17T00:00:00+00:00",
    )


def payload():
    return build_feature_snapshot_report_payload(snapshot())


def manifest():
    return build_feature_snapshot_artifact_manifest(
        snapshot=snapshot(),
        output_files=OUTPUT_FILES,
        generated_at="2026-06-17T00:00:00+00:00",
    )


def test_report_payload_contains_required_root_fields():
    report = payload()
    required = {
        "sprint",
        "generated_at",
        "source_contract_baseline",
        "live_etabs_connected",
        "model_path",
        "etabs_version",
        "target_family",
        "feature_record_count",
        "feature_status_counts",
        "readiness_status_counts",
        "source_family_counts",
        "numeric_feature_count",
        "raw_values_preserved",
        "all_numeric_have_units",
        "all_numeric_have_quantity_kind",
        "all_numeric_have_conversion_provenance",
        "unit_policy_closed",
        "safe_to_implement_checks_now",
        "check_unlock_allowed",
        "source_families",
        "blocked_guardrails",
        "representative_features",
    }
    assert required.issubset(report)
    assert report["sprint"] == "C13.3-P2"
    assert report["feature_record_count"] > 3
    assert report["numeric_feature_count"] > 0
    assert report["raw_values_preserved"] is True
    assert report["all_numeric_have_units"] is True
    assert report["all_numeric_have_quantity_kind"] is True
    assert report["all_numeric_have_conversion_provenance"] is True
    assert report["safe_to_implement_checks_now"] is False
    assert report["check_unlock_allowed"] is False


def test_source_family_counts_and_entries_are_included():
    report = payload()
    assert {"material_properties", "story_definitions", "pier_section_properties"}.issubset(report["source_family_counts"])
    by_family = {item["source_family"]: item for item in report["source_families"]}
    for family in {"material_properties", "story_definitions", "pier_section_properties"}:
        assert family in by_family
        entry = by_family[family]
        assert entry["feature_record_count"] > 0
        assert entry["source_tables"]
        assert entry["representative_feature_ids"]
        assert "feature_status_counts" in entry
        assert "readiness_status_counts" in entry
        assert isinstance(entry["has_resolved_records"], bool)
        assert isinstance(entry["has_partial_records"], bool)
        assert isinstance(entry["has_blocked_records"], bool)


def test_blocked_guardrails_are_included():
    report = payload()
    ids = {item["feature_id"] for item in report["blocked_guardrails"]}
    assert LOCKED_IDS.issubset(ids)
    for item in report["blocked_guardrails"]:
        assert item["safe_to_use_for_check"] is False
        assert item["check_unlock_allowed"] is False


def test_representative_features_are_included_and_not_check_usable():
    representatives = payload()["representative_features"]
    assert representatives
    for item in representatives:
        assert item["feature_id"]
        assert item["source_family"]
        assert item["feature_status"] in {"RESOLVED", "PARTIAL"}
        assert item["safe_to_use_for_check"] is False
        assert item["check_unlock_allowed"] is False


def test_artifact_manifest_contains_required_roles_and_guardrails():
    artifact_manifest = manifest()
    assert artifact_manifest["sprint"] == "C13.3-P2"
    assert artifact_manifest["artifact_contract_version"] == ARTIFACT_CONTRACT_VERSION
    assert artifact_manifest["source_snapshot_file"] == "feature_snapshot.json"
    assert artifact_manifest["output_files"] == OUTPUT_FILES
    assert set(OUTPUT_FILES).issubset(artifact_manifest["artifact_roles"])
    assert artifact_manifest["live_etabs_connected"] is True
    assert artifact_manifest["feature_values_faked"] is False
    assert artifact_manifest["safe_to_implement_checks_now"] is False
    assert artifact_manifest["check_unlock_allowed"] is False
    assert artifact_manifest["engineering_verdicts_emitted"] is False
    assert artifact_manifest["check_results_emitted"] is False
    assert artifact_manifest["excel_production_input_used"] is False


def test_markdown_report_contains_safe_sections():
    markdown = render_feature_snapshot_markdown_report(payload())
    assert "# C13.3-P2 FeatureSnapshot Evidence Report" in markdown
    assert "## Connection summary" in markdown
    assert "## Snapshot summary" in markdown
    assert "## Source family summary" in markdown
    assert "## Unit metadata summary" in markdown
    assert "## Representative features" in markdown
    assert "## Locked check guardrails" in markdown
    assert "## Explicit non-check disclaimer" in markdown
    assert "This report is source evidence only." in markdown
    assert "This report is not an engineering compliance report." in markdown
    assert "No TBDY/TS500 check verdicts are emitted." in markdown
    assert "CheckEngine is not invoked." in markdown
    assert "safe_to_implement_checks_now is false." in markdown
    assert "check_unlock_allowed is false." in markdown


def test_html_report_contains_safe_sections():
    html = render_feature_snapshot_html_report(payload())
    assert "<h1>C13.3-P2 FeatureSnapshot Evidence Report</h1>" in html
    assert "Static source evidence artifact" in html
    assert "This report is source evidence only." in html
    assert "This report is not an engineering compliance report." in html
    assert "No TBDY/TS500 check verdicts are emitted." in html
    assert "CheckEngine is not invoked." in html
    assert "safe_to_implement_checks_now is false." in html
    assert "check_unlock_allowed is false." in html


def test_artifact_rendering_is_deterministic():
    snap = snapshot()
    first_payload = build_feature_snapshot_report_payload(snap)
    second_payload = build_feature_snapshot_report_payload(snap)
    assert first_payload == second_payload
    first_manifest = build_feature_snapshot_artifact_manifest(
        snapshot=snap,
        output_files=OUTPUT_FILES,
        generated_at="2026-06-17T00:00:00+00:00",
    )
    second_manifest = build_feature_snapshot_artifact_manifest(
        snapshot=snap,
        output_files=OUTPUT_FILES,
        generated_at="2026-06-17T00:00:00+00:00",
    )
    assert first_manifest == second_manifest
    assert render_feature_snapshot_markdown_report(first_payload) == render_feature_snapshot_markdown_report(second_payload)
    assert render_feature_snapshot_html_report(first_payload) == render_feature_snapshot_html_report(second_payload)


def test_no_forbidden_verdict_strings_appear_in_generated_artifacts():
    rendered = json.dumps(payload(), sort_keys=True) + json.dumps(manifest(), sort_keys=True)
    rendered += render_feature_snapshot_markdown_report(payload())
    rendered += render_feature_snapshot_html_report(payload())
    for token in FORBIDDEN_ENGINEERING_VERDICT_TOKENS:
        assert token not in rendered


def test_no_live_mode_exits_2_and_writes_safe_artifacts(tmp_path):
    out = tmp_path / "c13_3_p2"
    result = subprocess.run(
        [sys.executable, "tools/smoke_c13_3_p2_feature_snapshot_artifacts.py", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert set(OUTPUT_FILES) == {path.name for path in out.iterdir()}
    connection = json.loads((out / "connection_report.json").read_text(encoding="utf-8"))
    assert connection["connection_status"] == "NO_LIVE_REQUESTED"
    assert connection["live_etabs_connected"] is False
    assert connection["feature_values_faked"] is False
    snap = json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert snap["check_unlock_allowed"] is False
    assert snap["safe_to_implement_checks_now"] is False
    artifact_manifest = json.loads((out / "feature_snapshot_artifact_manifest.json").read_text(encoding="utf-8"))
    assert artifact_manifest["engineering_verdicts_emitted"] is False
    assert artifact_manifest["check_results_emitted"] is False
    assert artifact_manifest["excel_production_input_used"] is False


def test_fake_live_fetcher_mode_creates_all_artifact_files(monkeypatch, tmp_path):
    rows = fixture_source_rows()
    connection_report = {
        "live_etabs_connected": True,
        "connection_status": "LIVE_CONNECTED",
        "model_path": "C:/tmp/B-BLOK_Revised.EDB",
        "etabs_version": "23.2.0",
        "tables_attempted": ["Material Properties - Basic Mechanical Properties"],
        "table_errors": {},
    }
    debug_tables = [
        {
            "table_name": "Material Properties - Basic Mechanical Properties",
            "source_family": "material_properties",
            "fetch_status": "FETCHED",
            "row_count": 1,
            "columns": ["Material", "Type", "E1"],
            "sample_rows": [{"Material": "C30", "Type": "Concrete", "E1": 32000.0}],
            "projected_feature_count": 0,
            "projection_status": "NOT_PROJECTED",
            "projection_blocker": None,
            "selected_signature": {"signature_name": "fake_shared_fetcher"},
            "selected_signature_reason": "fixture",
            "signature_attempts": [{"signature_name": "fake_shared_fetcher", "parser_status": "PARSED_ROWS"}],
            "parser_debug": {"parse_strategy_used": "fixture"},
            "parser_diagnostics": [],
        }
    ]

    def fake_collect_live_rows(target_family, max_rows_per_table):
        assert target_family == "all"
        assert max_rows_per_table == 25
        return rows, dict(connection_report), list(debug_tables)

    monkeypatch.setattr(smoke.p1_smoke, "_collect_live_rows", fake_collect_live_rows)
    out = tmp_path / "artifacts"
    exit_code = smoke.main([
        "--out",
        str(out),
        "--live-etabs",
        "--target-family",
        "all",
        "--max-rows-per-table",
        "25",
    ])
    assert exit_code == 0
    assert set(OUTPUT_FILES) == {path.name for path in out.iterdir()}
    report = json.loads((out / "feature_snapshot_report_payload.json").read_text(encoding="utf-8"))
    assert report["feature_record_count"] > 3
    assert report["numeric_feature_count"] > 0
    assert report["source_family_counts"]["material_properties"] > 0
    debug = json.loads((out / "source_table_projection_debug_report.json").read_text(encoding="utf-8"))
    assert debug["source_tables"][0]["projected_feature_count"] > 0
    assert debug["source_tables"][0]["projection_status"] == "PROJECTED"
    artifact_manifest = json.loads((out / "feature_snapshot_artifact_manifest.json").read_text(encoding="utf-8"))
    assert artifact_manifest["engineering_verdicts_emitted"] is False
    assert artifact_manifest["check_results_emitted"] is False
    assert artifact_manifest["excel_production_input_used"] is False


def test_p1_resolver_api_remains_backward_compatible():
    snap = snapshot()
    assert snap["sprint"] == "C13.3-P1"
    assert snap["feature_records"]
    assert snap["source_family_counts"]
    family_report = source_family_projection_report(snap)
    assert "material_properties" in family_report["projected_families"]
    assert family_report["check_unlock_allowed"] is False


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_no_check_engine_imports_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/feature_snapshot_artifacts.py",
        ROOT / "tools/smoke_c13_3_p2_feature_snapshot_artifacts.py",
    ]
    for path in touched:
        assert "tbdy_engine.checks.engine" not in _imports_for(path)


def test_no_streamlit_or_app_imports_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/feature_snapshot_artifacts.py",
        ROOT / "tools/smoke_c13_3_p2_feature_snapshot_artifacts.py",
    ]
    forbidden = {"streamlit", "apps", "tbdy_engine.apps", "tbdy_engine.reporting", "tbdy_engine.report"}
    for path in touched:
        assert not forbidden.intersection(_imports_for(path))


def test_no_excel_production_path_is_introduced():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "tbdy_engine/features/feature_snapshot_artifacts.py",
            ROOT / "tools/smoke_c13_3_p2_feature_snapshot_artifacts.py",
        ]
    ).casefold()
    assert "read_excel" not in text
    assert "openpyxl" not in text
    assert "excel_production_input: true" not in text
