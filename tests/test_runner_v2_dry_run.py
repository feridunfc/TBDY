from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import tbdy_engine.runner_v2 as runner_v2
from tbdy_engine.runner_v2 import TBDYEngineV2


ROOT = Path(__file__).resolve().parents[1]
DRY_RUN_KEYS = [
    "ok",
    "dataset_validation",
    "evaluation_order",
    "enabled_evaluations",
    "planned_checks",
    "report_contract",
    "warnings",
]
FORBIDDEN_MODULE_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.etabs",
    "tbdy_engine.engine.context_builder",
)
FORBIDDEN_DRY_RUN_CALLS = {
    "run",
    "_run_scheduler",
    "_build_evaluators",
    "_make_evaluator",
    "generate",
}


def _engine(tmp_path: Path, ctx: object | None = None) -> TBDYEngineV2:
    return TBDYEngineV2(ctx if ctx is not None else {}, report_dir=tmp_path)


def _dry_run_function_def() -> ast.FunctionDef:
    source = (ROOT / "tbdy_engine" / "runner_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "dry_run":
            return node
    raise AssertionError("dry_run function not found")


def test_dry_run_returns_exact_top_level_shape(tmp_path):
    result = _engine(tmp_path).dry_run()

    assert list(result) == DRY_RUN_KEYS


def test_dry_run_includes_dataset_validator_result(tmp_path):
    result = _engine(tmp_path, ctx={}).dry_run()
    dataset_validation = result["dataset_validation"]

    assert list(dataset_validation) == ["ok", "checks", "missing", "empty"]
    assert dataset_validation["missing"] or dataset_validation["empty"]
    assert result["ok"] is False


def test_dry_run_includes_deterministic_evaluation_dag_order(tmp_path):
    engine = _engine(tmp_path)

    first = engine.dry_run()
    second = engine.dry_run()

    assert isinstance(first["evaluation_order"], list)
    assert first["evaluation_order"] == second["evaluation_order"]
    assert set(first["evaluation_order"]).issubset(set(first["enabled_evaluations"]))


def test_dry_run_includes_planned_enabled_checks(tmp_path):
    engine = _engine(tmp_path)
    result = engine.dry_run()
    planned_checks = result["planned_checks"]

    assert planned_checks
    assert planned_checks == sorted(planned_checks)
    for check_id in planned_checks:
        assert engine.runtime_catalog.checks[check_id].runner_enabled

    known_checks = {"column_axial", "beam_flexure"} & set(engine.runtime_catalog.checks)
    if known_checks:
        assert known_checks & set(planned_checks)


def test_dry_run_includes_full_engine_report_contract(tmp_path):
    report_contract = _engine(tmp_path).dry_run()["report_contract"]

    assert report_contract["report_id"] == "full_engine_report"
    assert "evidence" in report_contract["include_fields"]
    for key in ("formats", "sections", "include_fields", "metrics"):
        assert isinstance(report_contract[key], list)


def test_dry_run_does_not_execute_scheduler_or_evaluators(tmp_path, monkeypatch):
    def forbidden_run(self, context, *, enabled_only=True):
        raise AssertionError("dry_run must not call RuntimeScheduler.run")

    def forbidden_build_evaluators(self, catalog):
        raise AssertionError("dry_run must not build evaluators")

    monkeypatch.setattr(runner_v2.RuntimeScheduler, "run", forbidden_run)
    monkeypatch.setattr(TBDYEngineV2, "_build_evaluators", forbidden_build_evaluators)

    _engine(tmp_path).dry_run()


def test_dry_run_writes_no_report_files(tmp_path):
    _engine(tmp_path).dry_run()

    assert not (tmp_path / "engine_report.json").exists()
    assert not (tmp_path / "engine_report.xlsx").exists()
    assert not (tmp_path / "action_summary.json").exists()


def test_dry_run_source_guard_avoids_execution_calls():
    dry_run_def = _dry_run_function_def()
    call_names: set[str] = set()

    for node in ast.walk(dry_run_def):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)

    assert not (FORBIDDEN_DRY_RUN_CALLS & call_names)


def test_dry_run_does_not_add_forbidden_runtime_imports(tmp_path):
    before = {
        name for name in sys.modules
        if name.startswith(FORBIDDEN_MODULE_PREFIXES)
    }

    _engine(tmp_path).dry_run()

    after = {
        name for name in sys.modules
        if name.startswith(FORBIDDEN_MODULE_PREFIXES)
    }
    assert after == before


def test_existing_execute_path_still_exposes_run(tmp_path):
    engine = _engine(tmp_path)

    assert callable(engine.run)
    assert callable(engine.dry_run)


def test_dry_run_report_missing_warning_path(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setattr(engine.runtime_catalog, "reports", {})

    result = engine.dry_run()

    assert result["report_contract"] == {"report_id": "full_engine_report", "missing": True}
    assert "Report contract 'full_engine_report' is missing." in result["warnings"]
