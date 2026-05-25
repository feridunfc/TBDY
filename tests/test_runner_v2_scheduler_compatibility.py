from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
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


def test_runner_v2_source_documents_old_scheduler_api_dependency():
    source = _runner_v2_source()

    old_api_markers = {
        "RuntimeScheduler(": "RuntimeScheduler(" in source,
        "run_all(": "run_all(" in source,
        "ctx=": "ctx=" in source,
        "evaluations_config=": "evaluations_config=" in source,
        "enabled_evaluation_ids=": "enabled_evaluation_ids=" in source,
    }

    assert old_api_markers == {
        "RuntimeScheduler(": True,
        "run_all(": True,
        "ctx=": True,
        "evaluations_config=": True,
        "enabled_evaluation_ids=": True,
    }


def test_runtime_scheduler_public_compatibility_surface_is_explicit():
    assert RuntimeScheduler.__name__ == "RuntimeScheduler"
    assert Scheduler is RuntimeScheduler
    assert hasattr(RuntimeScheduler, "run")
    assert not hasattr(RuntimeScheduler, "run_all")


def test_runner_v2_import_does_not_fail():
    import tbdy_engine.runner_v2 as runner_v2

    assert hasattr(runner_v2, "TBDYEngineV2")
    assert hasattr(runner_v2, "run_engine_v2")


def test_runner_v2_test_coverage_status_is_explicit():
    assert RUNNER_V2_TEST_COVERAGE in {"PRESENT", "MISSING"}
    if RUNNER_V2_TEST_COVERAGE == "MISSING":
        assert not any(path.exists() for path in RUNNER_V2_TEST_FILES)


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


def test_new_audit_test_has_no_forbidden_imports():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))

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
