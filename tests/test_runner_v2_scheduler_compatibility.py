from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import tbdy_engine.runner_v2 as runner_v2
from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.runner_v2 import TBDYEngineV2
from tbdy_engine.runtime.evaluation_dag import EvaluationDAG, EvaluationNode
from tbdy_engine.runtime.scheduler import RuntimeScheduler, Scheduler


ROOT = Path(__file__).resolve().parents[1]
RUNNER_V2_PATH = ROOT / "tbdy_engine" / "runner_v2.py"
SCHEDULER_PATH = ROOT / "tbdy_engine" / "runtime" / "scheduler.py"
RUNNER_V2_TEST_FILES = (
    ROOT / "tests" / "test_runner_v2_reporting_contract.py",
    ROOT / "tests" / "test_runner_v2_bridge_contract_only.py",
)
RUNNER_V2_TEST_COVERAGE = (
    "PRESENT" if any(path.exists() for path in RUNNER_V2_TEST_FILES) else "MISSING"
)
FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.etabs",
    "tbdy_engine.engine.context_builder",
)


def _runner_v2_source() -> str:
    return RUNNER_V2_PATH.read_text(encoding="utf-8")


def _runner_v2_tree() -> ast.Module:
    return ast.parse(_runner_v2_source())


def _scheduler_source() -> str:
    return SCHEDULER_PATH.read_text(encoding="utf-8")


def _column_design_payload() -> Mapping[str, object]:
    return {
        "outputs": [
            {
                "label": "C1",
                "story": "S1",
                "checks": {
                    "geometry": {
                        "status": "OK",
                        "ratio": 0.1,
                        "value": 0.1,
                        "limit": 1.0,
                        "unit": "ratio",
                        "message": "runner_v2 scheduler compatibility fixture",
                        "source": "runner_v2_scheduler_compatibility_test",
                        "evaluation_level": "DESIGN_LEVEL",
                        "evidence": {"source": "scheduler"},
                    }
                },
            }
        ]
    }


def test_runner_v2_no_longer_uses_old_scheduler_constructor_or_run_all_active_path():
    tree = _runner_v2_tree()
    scheduler_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RuntimeScheduler"
    ]
    run_all_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run_all"
    ]

    assert scheduler_calls
    for call in scheduler_calls:
        assert {keyword.arg for keyword in call.keywords} == {"dag", "evaluators"}
    assert run_all_calls == []


def test_runner_v2_imports_new_runtime_pieces():
    source = _runner_v2_source()

    assert "EvaluationDAG" in source
    assert "RuntimeScheduler" in source
    assert "SchedulerResult" in source


def test_runner_v2_can_build_evaluator_mapping_or_skip_missing_evaluators(tmp_path):
    engine = TBDYEngineV2(object(), report_dir=tmp_path)

    assert callable(engine._build_evaluators)

    original_ids = engine.enabled_evaluation_ids
    engine.enabled_evaluation_ids = lambda: {"MISSING_EVALUATION"}  # type: ignore[method-assign]
    evaluators = engine._build_evaluators(engine.runtime_catalog)
    engine.enabled_evaluation_ids = original_ids  # type: ignore[method-assign]

    assert evaluators == {}


def test_runner_v2_scheduler_path_produces_adapter_compatible_eval_results(tmp_path, monkeypatch):
    class DummySchedulerResult:
        def to_eval_results(self):
            return {
                "results": {
                    "COLUMN_DESIGN": _column_design_payload(),
                },
                "errors": {},
                "skipped": {},
                "execution_order": ["COLUMN_DESIGN"],
                "cache_stats": {},
            }

    monkeypatch.setattr(
        runner_v2.TBDYEngineV2,
        "_build_evaluators",
        lambda self, catalog: {"COLUMN_DESIGN": lambda context: _column_design_payload()},
    )
    monkeypatch.setattr(
        runner_v2.TBDYEngineV2,
        "enabled_evaluation_ids",
        lambda self: {"COLUMN_DESIGN"},
    )

    engine = TBDYEngineV2(object(), report_dir=tmp_path)
    eval_results = engine._run_scheduler().to_eval_results()

    assert list(eval_results) == ["results", "errors", "skipped", "execution_order", "cache_stats"]
    rows = CheckAdapter(engine.runtime_catalog).adapt_all(eval_results)
    assert any(row.check_id == "column_geometry" for row in rows)


def test_runtime_scheduler_public_compatibility_surface_is_explicit():
    assert RuntimeScheduler.__name__ == "RuntimeScheduler"
    assert Scheduler is RuntimeScheduler
    assert hasattr(RuntimeScheduler, "run")
    assert not hasattr(RuntimeScheduler, "run_all")


def test_runner_v2_import_does_not_fail():
    assert hasattr(runner_v2, "TBDYEngineV2")
    assert hasattr(runner_v2, "run_engine_v2")


def test_runner_v2_test_coverage_status_is_explicit():
    assert RUNNER_V2_TEST_COVERAGE == "PRESENT"
    assert any(path.exists() for path in RUNNER_V2_TEST_FILES)


def test_scheduler_output_remains_check_adapter_compatible():
    dag = EvaluationDAG(
        nodes=(
            EvaluationNode(
                evaluation="COLUMN_DESIGN",
                depends_on=(),
                enabled=True,
                experimental=False,
            ),
        )
    )

    result = RuntimeScheduler(
        dag=dag,
        evaluators={"COLUMN_DESIGN": lambda context: _column_design_payload()},
    ).run(context={})

    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    rows = CheckAdapter(catalog).adapt_all(result.to_eval_results())

    assert any(row.check_id == "column_geometry" for row in rows)


def test_scheduler_source_has_no_forbidden_imports():
    tree = ast.parse(_scheduler_source())

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_imports = sorted(
        module_name
        for module_name in imported_modules
        if any(
            module_name == prefix or module_name.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    )

    assert forbidden_imports == []


def test_runner_v2_does_not_add_forbidden_imports():
    tree = _runner_v2_tree()

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    forbidden_imports = sorted(
        module_name
        for module_name in imported_modules
        if any(
            module_name == prefix or module_name.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    )

    assert forbidden_imports == []


def test_no_combo_family_uses_combo_or_message_parsing_changes():
    combined = _runner_v2_source() + "\n" + _scheduler_source()

    assert "combo_family" not in combined
    assert "uses_combo" not in combined
    assert "message_text" not in combined
    assert ".message" not in combined
