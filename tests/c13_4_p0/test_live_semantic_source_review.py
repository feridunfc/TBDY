from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.features.semantic_source_review import (
    build_combo_semantic_review,
    build_design_output_semantic_review,
    build_drift_story_semantic_review,
    build_force_result_semantic_review,
    build_rebar_role_semantic_review,
    build_semantic_source_review_report,
    classify_semantic_source_table,
    scan_semantic_outputs_for_forbidden_verdicts,
)

ROOT = Path(__file__).resolve().parents[2]


def force_classification():
    return classify_semantic_source_table(
        source_family="frame_forces",
        table_name="Element Forces - Beams",
        fetch_status="FETCHED",
        columns=["Story", "Frame", "UniqueName", "Station", "OutputCase", "StepType", "P", "V2", "V3", "T", "M2", "M3"],
        rows=[{"Story": "+14.5", "Frame": "B1", "UniqueName": "297", "Station": 0.0, "OutputCase": "EQX", "P": 1.0, "V2": 2.0, "M3": 3.0}],
    )


def drift_classification():
    return classify_semantic_source_table(
        source_family="story_drifts",
        table_name="Story Drifts",
        fetch_status="FETCHED",
        columns=["Story", "OutputCase", "Direction", "Drift", "Label"],
        rows=[{"Story": "+14.5", "OutputCase": "EQX", "Direction": "X", "Drift": 0.001}],
    )


def design_classification():
    return classify_semantic_source_table(
        source_family="design_outputs",
        table_name="Concrete Beam Design Summary",
        fetch_status="FETCHED",
        columns=["Label", "Story", "Station", "Combo", "AsTop", "AsBot", "VRebar"],
        rows=[{"Label": "B1", "Story": "+14.5", "Station": 0.0, "Combo": "D1", "AsTop": 10.0, "AsBot": 8.0, "VRebar": 4.0}],
    )


def rebar_classification():
    return classify_semantic_source_table(
        source_family="rebar_outputs",
        table_name="Concrete Beam Design Summary",
        fetch_status="FETCHED",
        columns=["Label", "Story", "Station", "AsTop", "AsBot", "AsShear", "Rebar", "Area"],
        rows=[{"Label": "B1", "Story": "+14.5", "Station": 0.0, "AsTop": 10.0, "AsBot": 8.0, "AsShear": 4.0, "Area": 10.0}],
    )


def test_no_live_command_exits_2_and_writes_safe_connection_report(tmp_path):
    out = tmp_path / "no_live"
    result = subprocess.run(
        [sys.executable, "tools/smoke_c13_4_p0_live_semantic_source_review.py", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert {path.name for path in out.iterdir()} == {"connection_report.json"}
    connection = json.loads((out / "connection_report.json").read_text(encoding="utf-8"))
    assert connection["live_etabs_requested"] is False
    assert connection["live_etabs_connected"] is False
    assert connection["connection_status"] == "NO_LIVE_REQUESTED"
    assert connection["feature_values_faked"] is False
    assert connection["safe_to_implement_checks_now"] is False
    assert connection["check_unlock_allowed"] is False
    assert connection["diagnostic_only"] is True
    assert connection["check_engine_invoked"] is False


def test_semantic_classifier_detects_force_and_combo_columns():
    item = force_classification()
    assert {"P", "V2", "V3", "T", "M2", "M3"}.intersection(item["force_component_columns_detected"])
    assert "OutputCase" in item["case_combo_columns_detected"]
    assert item["semantic_review_status"] == "BLOCKED_COMBO_GOVERNING_POLICY"
    assert item["safe_to_use_for_check"] is False
    assert item["check_unlock_allowed"] is False
    assert item["diagnostic_only"] is True


def test_combo_review_flags_future_policy_when_case_or_station_is_present():
    report = build_combo_semantic_review([force_classification()])
    statuses = set(report["entries"][0]["combo_review_statuses"])
    assert "LOAD_CASE_ONLY" in statuses or "GOVERNING_POLICY_REQUIRED" in statuses
    assert "ENVELOPE_POLICY_REQUIRED" in statuses
    assert report["entries"][0]["future_governing_row_policy_needed"] is True
    assert report["check_engine_invoked"] is False


def test_semantic_classifier_detects_drift_story_columns():
    item = drift_classification()
    assert "Story" in item["object_identity_columns_detected"]
    assert "Direction" in item["direction_columns_detected"]
    assert "Drift" in item["semantic_columns_detected"]
    assert item["semantic_review_status"] == "BLOCKED_COMBO_GOVERNING_POLICY"


def test_semantic_classifier_detects_design_and_rebar_role_columns():
    design = design_classification()
    rebar = rebar_classification()
    assert design["design_component_columns_detected"]
    assert design["semantic_review_status"] == "BLOCKED_DESIGN_OUTPUT_ROLE_POLICY"
    assert rebar["rebar_role_columns_detected"]
    assert rebar["semantic_review_status"] == "BLOCKED_REBAR_ROLE_POLICY"


def test_review_reports_remain_guarded_and_deterministic():
    classifications = [force_classification(), drift_classification(), design_classification(), rebar_classification()]
    first = build_semantic_source_review_report(classifications=classifications, generated_at="2026-06-17T00:00:00+00:00", live_etabs_requested=True, live_etabs_connected=True, target_family="all")
    second = build_semantic_source_review_report(classifications=classifications, generated_at="2026-06-17T00:00:00+00:00", live_etabs_requested=True, live_etabs_connected=True, target_family="all")
    assert first == second
    assert first["reviewed_table_count"] == 4
    assert first["fetched_table_count"] == 4
    assert first["table_with_rows_count"] == 4
    assert first["combo_governing_policy_required_count"] >= 2
    assert first["design_role_policy_required_count"] == 1
    assert first["rebar_role_policy_required_count"] == 1
    assert first["safe_to_implement_checks_now"] is False
    assert first["check_unlock_allowed"] is False
    assert first["diagnostic_only"] is True
    assert first["check_engine_invoked"] is False


def test_category_reports_filter_expected_tables():
    classifications = [force_classification(), drift_classification(), design_classification(), rebar_classification()]
    assert build_force_result_semantic_review(classifications)["table_count"] == 1
    assert build_drift_story_semantic_review(classifications)["table_count"] == 1
    assert build_design_output_semantic_review(classifications)["table_count"] == 1
    assert build_rebar_role_semantic_review(classifications)["table_count"] == 1


def test_forbidden_verdict_scanner_catches_terms_and_generated_reports_are_clean():
    bad = scan_semantic_outputs_for_forbidden_verdicts("this row is PASS and has capacity ratio text")
    assert {item["term"] for item in bad["forbidden_terms_found"]} == {"PASS", "capacity ratio"}
    classifications = [force_classification(), drift_classification(), design_classification(), rebar_classification()]
    payload = {
        "summary": build_semantic_source_review_report(classifications=classifications, generated_at="2026-06-17T00:00:00+00:00"),
        "combo": build_combo_semantic_review(classifications),
        "force": build_force_result_semantic_review(classifications),
        "drift": build_drift_story_semantic_review(classifications),
        "design": build_design_output_semantic_review(classifications),
        "rebar": build_rebar_role_semantic_review(classifications),
    }
    clean = scan_semantic_outputs_for_forbidden_verdicts(payload)
    assert clean["forbidden_terms_found"] == []


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_no_forbidden_imports_or_excel_path_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/semantic_source_review.py",
        ROOT / "tools/smoke_c13_4_p0_live_semantic_source_review.py",
    ]
    forbidden_imports = {"streamlit", "apps", "tbdy_engine.apps", "tbdy_engine.reporting", "tbdy_engine.report", "tbdy_engine.checks", "tbdy_engine.checks.engine"}
    for path in touched:
        imports = _imports_for(path)
        assert not forbidden_imports.intersection(imports)
        assert not any(item.startswith("tbdy_engine.checks") for item in imports)
    text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in touched)
    assert "read_excel" not in text
    assert "openpyxl" not in text
    assert "excel_production_input: true" not in text
