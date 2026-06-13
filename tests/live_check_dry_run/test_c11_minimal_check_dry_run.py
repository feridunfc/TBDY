import ast
import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from tbdy_engine.checks.dry_run import C11_EXECUTABLE_CHECK_IDS, build_and_write_c11_outputs, build_c11_outputs
from tbdy_engine.checks.pass_rules import PassRuleEvaluator

FEATURE_SNAPSHOT = Path("local_out/c10_minimal_live_readiness/feature_snapshot_with_context.json")
COVERAGE_MATRIX = Path("local_out/c10_minimal_live_readiness/coverage_matrix.json")


def _outputs(tmp_path):
    out = tmp_path / "c11"
    payload = build_and_write_c11_outputs(FEATURE_SNAPSHOT, COVERAGE_MATRIX, out)
    return out, payload


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_c11_loads_c10_feature_snapshot_with_context_fixture(tmp_path):
    out, _ = _outputs(tmp_path)
    assert (out / "check_results.json").exists()
    assert _read(FEATURE_SNAPSHOT)["design_context_report"]["design_context"]["ductility_class"] == "HIGH"


def test_c11_loads_c10_coverage_matrix_fixture(tmp_path):
    out, _ = _outputs(tmp_path)
    summary = _read(out / "check_results_summary.json")
    assert summary["check_result_count"] == 3
    assert set(summary["executed_check_ids"]) == set(C11_EXECUTABLE_CHECK_IDS)


def test_c11_executes_only_runnable_rows(tmp_path):
    out, _ = _outputs(tmp_path)
    coverage = _read(COVERAGE_MATRIX)["checks"]
    runnable = {row["check_id"] for row in coverage if row["coverage_status"] == "RUNNABLE"}
    summary = _read(out / "check_results_summary.json")
    assert set(summary["executed_check_ids"]) == set(C11_EXECUTABLE_CHECK_IDS)
    assert set(summary["executed_check_ids"]).issubset(runnable)


def test_c11_does_not_execute_blocked_rows(tmp_path):
    out, _ = _outputs(tmp_path)
    skipped = _read(out / "skipped_coverage_rows_report.json")
    assert any(row["coverage_status"] == "BLOCKED" for row in skipped)
    blocked = [row for row in skipped if row["coverage_status"] == "BLOCKED"]
    assert all("must not be executed" in row["must_not_execute_reason"] or "outside C11" in row["must_not_execute_reason"] for row in blocked)
    assert _read(out / "c11_boundary_report.json")["blocked_rows_executed"] is False


def test_c11_does_not_silently_ok_partial_rows(tmp_path):
    out, _ = _outputs(tmp_path)
    skipped = _read(out / "skipped_coverage_rows_report.json")
    partial = [row for row in skipped if row["coverage_status"] == "PARTIAL"]
    assert partial
    assert all(row["reason_skipped"] == "partial_coverage" for row in partial)
    assert _read(out / "c11_boundary_report.json")["partial_rows_silent_OK"] is False


def test_c11_emits_schema_valid_check_results(tmp_path):
    out, _ = _outputs(tmp_path)
    schema = _read(Path("tbdy_engine/catalogs/schemas/check_result.schema.json"))
    validator = Draft202012Validator(schema)
    results = _read(out / "check_results.json")
    assert len(results) == 3
    for result in results:
        validator.validate(result)


def test_c11_summary_contains_exactly_executed_check_ids(tmp_path):
    out, _ = _outputs(tmp_path)
    summary = _read(out / "check_results_summary.json")
    assert summary["executed_check_ids"] == list(C11_EXECUTABLE_CHECK_IDS)
    assert summary["skipped_blocked_count"] == 8
    assert summary["skipped_partial_count"] == 2


def test_c11_skipped_report_explains_every_skipped_row(tmp_path):
    out, _ = _outputs(tmp_path)
    skipped = _read(out / "skipped_coverage_rows_report.json")
    assert len(skipped) == 10
    for row in skipped:
        assert row["check_id"]
        assert row["reason_skipped"]
        assert row["must_not_execute_reason"]


def test_c11_boundary_report_proves_no_live_etabs_provider_feature_resolver_call(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    assert boundary["live_etabs_called"] is False
    assert boundary["provider_called"] is False
    assert boundary["feature_resolver_called"] is False
    assert boundary["CheckEngine_executed"] is True
    assert boundary["CheckResult_emitted"] is True
    assert boundary["executed_only_runnable_rows"] is True


def test_c11_pass_rule_semantics_remain_c6_1_safe():
    evaluator = PassRuleEvaluator()
    assert evaluator.evaluate(ratio_type="value_over_maximum", ratio=1.2).status == "FAIL"
    assert evaluator.evaluate(ratio_type="value_over_minimum", ratio=0.8).status == "FAIL"
    assert evaluator.evaluate(ratio_type="actual_over_minimum", ratio=0.8).status == "FAIL"


def test_c11_rebar_flexure_shear_rows_not_executed(tmp_path):
    out, _ = _outputs(tmp_path)
    results = _read(out / "check_results.json")
    executed = {result["check_id"] for result in results}
    assert not any("flexure" in check_id for check_id in executed)
    assert not any("shear" in check_id for check_id in executed)
    assert not any("selected" in check_id or "governing" in check_id for check_id in executed)
    boundary = _read(out / "c11_boundary_report.json")
    assert boundary["rebar_selection_executed"] is False
    assert boundary["beam_flexure_executed"] is False
    assert boundary["beam_shear_executed"] is False


def test_c11_status_counts_and_pass_rule_types(tmp_path):
    out, _ = _outputs(tmp_path)
    results = _read(out / "check_results.json")
    summary = _read(out / "check_results_summary.json")
    assert Counter(result["status"] for result in results) == Counter({"OK": 3})
    assert summary["pass_rule_types_used"] == ["actual_over_minimum", "value_over_maximum", "value_over_minimum"]


def test_c11_no_legacy_imports():
    tree = ast.parse(Path("tbdy_engine/checks/dry_run.py").read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    text = "\n".join(imports)
    for forbidden in [
        "providers",
        "etabs",
        "runner_v2",
        "runtime",
        "archx",
        "full_engineering",
        "beam_checks_patch",
        "registry",
        "source.live_adapter",
    ]:
        assert forbidden not in text


def test_c11_no_excel_production_path():
    text = Path("tbdy_engine/checks/dry_run.py").read_text(encoding="utf-8").casefold()
    assert "openpyxl" not in text
    assert "pandas" not in text
    assert "excel_adapter" not in text


def test_c11_output_deterministic(tmp_path):
    out1, payload1 = _outputs(tmp_path / "one")
    out2, payload2 = _outputs(tmp_path / "two")
    assert payload1 == payload2
    for name in ["check_results.json", "check_results_summary.json", "skipped_coverage_rows_report.json", "c11_boundary_report.json"]:
        assert (out1 / name).read_text(encoding="utf-8") == (out2 / name).read_text(encoding="utf-8")


def test_c11_manual_next_machine_instructions_created(tmp_path):
    out, _ = _outputs(tmp_path)
    path = out / "manual_etabs_next_machine_instructions.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "C8 feature resolver smoke" in text
    assert "Do not run rebar" in text


def test_c11_boundary_report_includes_check_result_count(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    assert boundary["check_result_count"] == 3


def test_c11_boundary_report_count_matches_check_results_summary(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    summary = _read(out / "check_results_summary.json")
    assert boundary["check_result_count"] == summary["check_result_count"]
    assert boundary["status_counts"] == summary["status_counts"]
    assert boundary["skipped_partial_count"] == summary["skipped_partial_count"]
    assert boundary["skipped_blocked_count"] == summary["skipped_blocked_count"]
    assert boundary["skipped_reason_counts"] == summary["skipped_reason_counts"]


def test_c11_boundary_report_count_matches_check_results_len(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    results = _read(out / "check_results.json")
    assert boundary["check_result_count"] == len(results)


def test_c11_boundary_report_executed_ids_match_summary(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    summary = _read(out / "check_results_summary.json")
    assert boundary["executed_check_ids"] == summary["executed_check_ids"]


def test_c11_boundary_report_preserves_no_live_provider_resolver_calls(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    assert boundary["live_etabs_called"] is False
    assert boundary["provider_called"] is False
    assert boundary["feature_resolver_called"] is False
    assert boundary["check_engine_executed"] is True


def test_c11_boundary_report_preserves_rebar_flexure_shear_locks(tmp_path):
    out, _ = _outputs(tmp_path)
    boundary = _read(out / "c11_boundary_report.json")
    assert boundary["partial_rows_silent_OK"] is False
    assert boundary["rebar_selection_executed"] is False
    assert boundary["beam_flexure_executed"] is False
    assert boundary["beam_shear_executed"] is False
