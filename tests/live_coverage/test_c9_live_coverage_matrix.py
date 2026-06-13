from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

from tbdy_engine.coverage.live_matrix import build_c9_outputs, load_feature_snapshot_document

C8_SNAPSHOT = Path("local_out/c8_feature_resolver_smoke/feature_snapshot.json")
FORBIDDEN_OUTPUT_TOKENS = ('"OK"', '"FAIL"', "CheckResult")
C9_FILES = {
    "coverage_matrix.json",
    "coverage_summary.json",
    "missing_required_features_report.json",
    "missing_design_context_report.json",
    "missing_expected_sources_report.json",
    "evidence_readiness_report.json",
    "runnable_gap_report.json",
    "c9_boundary_report.json",
}


def _outputs():
    return build_c9_outputs(C8_SNAPSHOT)


def _rows(outputs=None):
    outputs = outputs or _outputs()
    return outputs["coverage_matrix.json"]["checks"]


def _text(outputs=None):
    return json.dumps(outputs or _outputs(), ensure_ascii=False, sort_keys=True)


def test_c9_builds_coverage_from_c8_feature_snapshot_fixture():
    raw, snapshots = load_feature_snapshot_document(C8_SNAPSHOT)
    outputs = _outputs()
    assert raw["metadata"]["check_engine_executed"] is False
    assert len(snapshots) == 4
    assert outputs["coverage_summary.json"]["coverage_row_count"] == len(_rows(outputs))
    assert len(_rows(outputs)) > 0


def test_c9_coverage_matrix_schema_valid():
    schema = json.loads(Path("tbdy_engine/catalogs/schemas/coverage_matrix.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(_outputs()["coverage_matrix.json"], schema)


def test_c9_coverage_summary_has_blocked_partial_runnable_counts():
    counts = _outputs()["coverage_summary.json"]["coverage_status_counts"]
    assert set(counts) == {"RUNNABLE", "BLOCKED", "PARTIAL"}
    assert counts["BLOCKED"] > 0
    assert counts["PARTIAL"] > 0


def test_c9_explains_why_runnable_zero():
    summary = _outputs()["coverage_summary.json"]
    assert summary["coverage_status_counts"]["RUNNABLE"] == 0
    explanation = summary["runnable_zero_explanation"]
    assert explanation["runnable_count"] == 0
    assert explanation["reason_category_counts"]["check requires design context not present"] > 0
    assert explanation["reason_category_counts"]["check requires features outside C8 subset"] > 0


def test_c9_missing_required_features_report_created():
    report = _outputs()["missing_required_features_report.json"]
    assert report
    assert {item["feature_name"] for item in report} >= {"beam_clear_span_mm", "story_height_mm", "design_base_shear_kN"}


def test_c9_missing_design_context_report_created():
    report = _outputs()["missing_design_context_report.json"]
    assert report
    assert {item["context_field"] for item in report} == {"ductility_class"}


def test_c9_evidence_readiness_report_created():
    report = _outputs()["evidence_readiness_report.json"]
    assert report["summary"]["complete_evidence_count"] == 28
    assert report["summary"]["combo_review_count"] > 0
    assert report["summary"]["warnmsg_errmsg_diagnostic_count"] >= 1


def test_c9_runnable_gap_report_created():
    report = _outputs()["runnable_gap_report.json"]
    assert report
    assert all(row["coverage_status"] in {"BLOCKED", "PARTIAL"} for row in report)
    assert any("Design context policy" in row["gap_owner_categories"] for row in report)
    assert any("FeatureResolver" in row["gap_owner_categories"] for row in report)


def test_c9_preserves_feature_evidence_references():
    rows = _rows()
    beam_width = next(row for row in rows if row["check_id"] == "beam_geometry_min_width")
    assert "beam_width_mm" in beam_width["resolved_features"]
    evidence_report = _outputs()["evidence_readiness_report.json"]
    complete_names = {item["feature_name"] for item in evidence_report["features_with_complete_evidence"]}
    assert "beam_width_mm" in complete_names


def test_c9_drift_torsion_semantic_lock():
    boundary = _outputs()["c9_boundary_report.json"]
    lock = boundary["drift_torsion_semantic_lock"]
    assert lock["semantic_lock_preserved"] is True
    assert lock["story_drift_value_source"]["source_table"] == "story_drifts"
    assert lock["story_drift_value_source"]["source_column"] == "Drift"
    assert lock["story_torsion_a1_coefficient_source"]["source_table"] == "story_max_over_avg_drifts"
    assert lock["story_torsion_a1_coefficient_source"]["source_column"] == "Ratio"
    assert lock["drift_verdict_emitted"] is False


def test_c9_warnmsg_errmsg_are_evidence_diagnostics_only():
    evidence = _outputs()["evidence_readiness_report.json"]
    messages = evidence["warnmsg_errmsg_evidence_diagnostics"]
    assert any(item["feature_name"] == "beam_design_warn_msg" for item in messages)
    assert "CheckResult" not in json.dumps(messages)
    assert '"OK"' not in json.dumps(messages)
    assert '"FAIL"' not in json.dumps(messages)


def test_c9_combo_review_diagnostic_not_verdict():
    evidence = _outputs()["evidence_readiness_report.json"]
    combo = evidence["features_with_combo_engineering_review_diagnostic"]
    assert combo
    assert any(item["diagnostic"]["details"].get("needs_engineering_review") is True for item in combo)
    assert '"OK"' not in json.dumps(combo)
    assert '"FAIL"' not in json.dumps(combo)


def test_c9_no_checkengine_execution():
    boundary = _outputs()["c9_boundary_report.json"]
    assert boundary["metadata"]["check_engine_executed"] is False


def test_c9_no_checkresult_output():
    assert "CheckResult" not in _text()
    boundary = _outputs()["c9_boundary_report.json"]
    assert boundary["metadata"]["check_result_emitted"] is False


def test_c9_no_ok_fail_verdicts():
    text = _text()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        assert token not in text


def test_c9_import_safe_without_etabs():
    import tools.build_live_coverage_matrix as c9_tool
    assert callable(c9_tool.main)


def test_c9_forbidden_legacy_imports_absent():
    paths = [Path("tools/build_live_coverage_matrix.py"), Path("tbdy_engine/coverage/live_matrix.py")]
    forbidden = {
        "tbdy_engine.checks.engine",
        "tbdy_engine.checks.result",
        "tbdy_engine.providers.fake_etabs",
        "source.live_adapter",
        "source.excel_adapter",
        "runner_v2",
        "tbdy_engine.runtime",
        "tbdy_engine.archx",
        "archx",
        "runtime",
    }
    imported = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not (imported & forbidden)


def test_c9_output_deterministic(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    cmd_base = [sys.executable, "tools/build_live_coverage_matrix.py", "--feature-snapshot", str(C8_SNAPSHOT)]
    first = subprocess.run(cmd_base + ["--out", str(out_a)], text=True, capture_output=True, check=False)
    second = subprocess.run(cmd_base + ["--out", str(out_b)], text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert C9_FILES <= {p.name for p in out_a.glob("*.json")}
    assert C9_FILES <= {p.name for p in out_b.glob("*.json")}
    for filename in sorted(C9_FILES):
        assert (out_a / filename).read_text(encoding="utf-8") == (out_b / filename).read_text(encoding="utf-8")


def test_c9_tool_accepts_c8_probe_fixture_input(tmp_path):
    out = tmp_path / "from_probe"
    result = subprocess.run(
        [
            sys.executable,
            "tools/build_live_coverage_matrix.py",
            "--c8-probe-input",
            "tests/fixtures/c8_table_headers_fixture.json",
            "--out",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert C9_FILES <= {p.name for p in out.glob("*.json")}
    summary = json.loads((out / "coverage_summary.json").read_text(encoding="utf-8"))
    assert summary["coverage_row_count"] > 0
