from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

from tbdy_engine.coverage.live_readiness import build_c10_outputs, load_design_context

C8_SNAPSHOT = Path("local_out/c8_feature_resolver_smoke/feature_snapshot.json")
C10_CONTEXT = Path("tests/fixtures/c10_design_context_fixture.json")
FORBIDDEN_OUTPUT_TOKENS = ('"OK"', '"FAIL"', "CheckResult")
C10_FILES = {
    "feature_snapshot_with_context.json",
    "design_context_report.json",
    "coverage_matrix.json",
    "coverage_summary.json",
    "runnable_rows_report.json",
    "blocked_rows_report.json",
    "partial_rows_report.json",
    "runnable_gap_report.json",
    "evidence_readiness_report.json",
    "c10_boundary_report.json",
    "optional_manual_etabs_feedback_report.json",
    "missing_required_features_report.json",
    "missing_design_context_report.json",
    "missing_expected_sources_report.json",
}


def _outputs():
    return build_c10_outputs(C8_SNAPSHOT, C10_CONTEXT)


def _rows(outputs=None):
    return (outputs or _outputs())["coverage_matrix.json"]["checks"]


def _text(outputs=None):
    return json.dumps(outputs or _outputs(), ensure_ascii=False, sort_keys=True)


def test_c10_builds_readiness_from_c8_snapshot_and_design_context():
    outputs = _outputs()
    summary = outputs["coverage_summary.json"]
    assert summary["metadata"]["input_feature_snapshot"] == str(C8_SNAPSHOT)
    assert summary["metadata"]["input_design_context"] == str(C10_CONTEXT)
    assert summary["coverage_row_count"] == len(_rows(outputs))
    assert summary["coverage_row_count"] > 0


def test_c10_design_context_fixture_supplies_ductility_class():
    design_context, provenance = load_design_context(C10_CONTEXT)
    assert design_context == {"ductility_class": "HIGH"}
    assert provenance["fields"]["ductility_class"]["provenance"] == "manual_design_context"


def test_c10_manual_design_context_has_provenance():
    report = _outputs()["design_context_report.json"]
    assert report["design_context"]["ductility_class"] == "HIGH"
    field = report["provenance"]["fields"]["ductility_class"]
    assert field["source"] == "manual_project_design_basis"
    assert field["source_file"] == str(C10_CONTEXT)
    assert report["provenance"]["silent_inference_used"] is False


def test_c10_at_least_one_safe_row_becomes_runnable():
    outputs = _outputs()
    counts = outputs["coverage_summary.json"]["coverage_status_counts"]
    assert counts["RUNNABLE"] >= 1
    runnable_ids = {row["check_id"] for row in outputs["runnable_rows_report.json"]}
    assert {"beam_geometry_min_width", "beam_depth_width_ratio", "modal_mass_participation"} <= runnable_ids


def test_c10_rebar_rows_remain_blocked():
    rows = _rows()
    rebar_related = [row for row in rows if "selected" in row["check_id"] or "governing" in row["check_id"]]
    assert rebar_related
    assert all(row["coverage_status"] != "RUNNABLE" for row in rebar_related)


def test_c10_flexure_shear_rows_remain_blocked():
    rows = _rows()
    guarded = [row for row in rows if "flexure" in row["check_id"] or "shear" in row["check_id"]]
    assert guarded
    assert all(row["coverage_status"] != "RUNNABLE" for row in guarded)


def test_c10_force_demand_rows_remain_blocked():
    rows = _rows()
    demand_ids = {"beam_shear_ve_le_vr", "beam_capacity_design_shear", "base_shear_scaling"}
    guarded = [row for row in rows if row["check_id"] in demand_ids]
    assert guarded
    assert all(row["coverage_status"] != "RUNNABLE" for row in guarded)


def test_c10_runnable_rows_are_readiness_not_ok():
    runnable = _outputs()["runnable_rows_report.json"]
    assert runnable
    assert all(row["readiness_only"] is True for row in runnable)
    assert all(row["structural_verdict_emitted"] is False for row in runnable)
    assert '"OK"' not in json.dumps(runnable)
    assert '"FAIL"' not in json.dumps(runnable)


def test_c10_no_checkengine_execution():
    boundary = _outputs()["c10_boundary_report.json"]
    assert boundary["metadata"]["check_engine_executed"] is False


def test_c10_no_checkresult_output():
    outputs = _outputs()
    assert "CheckResult" not in _text(outputs)
    assert outputs["c10_boundary_report.json"]["metadata"]["check_result_emitted"] is False


def test_c10_no_ok_fail_verdicts():
    text = _text()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        assert token not in text


def test_c10_drift_torsion_semantic_lock_preserved():
    lock = _outputs()["c10_boundary_report.json"]["drift_torsion_semantic_lock"]
    assert lock["semantic_lock_preserved"] is True
    assert lock["story_drift_value_source"]["source_table"] == "story_drifts"
    assert lock["story_drift_value_source"]["source_column"] == "Drift"
    assert lock["story_torsion_a1_coefficient_source"]["source_table"] == "story_max_over_avg_drifts"
    assert lock["story_torsion_a1_coefficient_source"]["source_column"] == "Ratio"
    assert lock["drift_verdict_emitted"] is False


def test_c10_warnmsg_errmsg_evidence_only():
    evidence = _outputs()["evidence_readiness_report.json"]
    messages = evidence["warnmsg_errmsg_evidence_diagnostics"]
    assert any(item["feature_name"] == "beam_design_warn_msg" for item in messages)
    assert '"OK"' not in json.dumps(messages)
    assert '"FAIL"' not in json.dumps(messages)


def test_c10_combo_review_diagnostic_not_verdict():
    evidence = _outputs()["evidence_readiness_report.json"]
    combo = evidence["features_with_combo_engineering_review_diagnostic"]
    assert combo
    assert any(item["diagnostic"]["details"].get("needs_engineering_review") is True for item in combo)
    assert '"OK"' not in json.dumps(combo)
    assert '"FAIL"' not in json.dumps(combo)


def test_c10_legacy_feedback_report_reference_only():
    report = _outputs()["optional_manual_etabs_feedback_report.json"]
    assert report["metadata"]["reference_only"] is True
    assert report["legacy_feedback_only"]["structural_verdict_imported"] is False
    assert report["legacy_feedback_only"]["used_for_current_check_result"] is False
    assert report["legacy_feedback_only"]["old_tests_imported_or_executed"] is False


def test_c10_no_legacy_imports():
    paths = [Path("tools/build_minimal_live_readiness_slice.py"), Path("tbdy_engine/coverage/live_readiness.py")]
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


def test_c10_import_safe_without_etabs():
    import tools.build_minimal_live_readiness_slice as c10_tool
    assert callable(c10_tool.main)


def test_c10_output_deterministic(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    cmd = [
        sys.executable,
        "tools/build_minimal_live_readiness_slice.py",
        "--feature-snapshot",
        str(C8_SNAPSHOT),
        "--design-context",
        str(C10_CONTEXT),
    ]
    first = subprocess.run(cmd + ["--out", str(out_a)], text=True, capture_output=True, check=False)
    second = subprocess.run(cmd + ["--out", str(out_b)], text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert C10_FILES <= {p.name for p in out_a.glob("*.json")}
    assert C10_FILES <= {p.name for p in out_b.glob("*.json")}
    for filename in sorted(C10_FILES):
        assert (out_a / filename).read_text(encoding="utf-8") == (out_b / filename).read_text(encoding="utf-8")


def test_c10_coverage_matrix_schema_valid():
    schema = json.loads(Path("tbdy_engine/catalogs/schemas/coverage_matrix.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(_outputs()["coverage_matrix.json"], schema)
