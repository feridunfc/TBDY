from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.runtime.dataset_validator import DatasetValidator
from tbdy_engine.runtime.evaluation_dag import EvaluationDAG, EvaluationNode
from tbdy_engine.runtime.scheduler import EvaluationRunStatus, RuntimeScheduler


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.etabs",
    "tbdy_engine.engine.context_builder",
    "tbdy_engine.adapters",
    "tbdy_engine.reports",
    "tbdy_engine.runner",
    "tbdy_engine.runner_v2",
)


def _dag(*nodes: EvaluationNode) -> EvaluationDAG:
    return EvaluationDAG(nodes=tuple(sorted(nodes, key=lambda node: node.evaluation)))


def _ok_payload() -> Mapping[str, object]:
    return {"outputs": []}


def test_scheduler_runs_evaluators_in_dag_order():
    dag = _dag(
        EvaluationNode(evaluation="A", depends_on=(), enabled=True, experimental=False),
        EvaluationNode(evaluation="B", depends_on=("A",), enabled=True, experimental=False),
        EvaluationNode(evaluation="C", depends_on=("B",), enabled=True, experimental=False),
    )
    call_order: list[str] = []

    def evaluator(name: str):
        def run(context: object) -> Mapping[str, object]:
            call_order.append(name)
            return _ok_payload()

        return run

    result = RuntimeScheduler(
        dag=dag,
        evaluators={"A": evaluator("A"), "B": evaluator("B"), "C": evaluator("C")},
    ).run(context={})

    assert call_order == ["A", "B", "C"]
    assert result.ok is True
    assert set(result.results) == {"A", "B", "C"}
    assert result.errors == {}
    assert result.skipped == {}
    assert result.execution_order == ("A", "B", "C")


def test_missing_evaluator_becomes_skipped():
    dag = _dag(
        EvaluationNode(evaluation="A", depends_on=(), enabled=True, experimental=False),
        EvaluationNode(evaluation="B", depends_on=(), enabled=True, experimental=False),
    )

    result = RuntimeScheduler(dag=dag, evaluators={"A": lambda context: _ok_payload()}).run(context={})
    by_name = {record.evaluation: record for record in result.records}

    assert by_name["A"].status is EvaluationRunStatus.OK
    assert by_name["B"].status is EvaluationRunStatus.SKIPPED
    assert result.skipped["B"] == "No evaluator registered for 'B'."
    assert result.ok is True


def test_evaluator_exception_becomes_error_and_scheduler_continues():
    dag = _dag(
        EvaluationNode(evaluation="A", depends_on=(), enabled=True, experimental=False),
        EvaluationNode(evaluation="B", depends_on=("A",), enabled=True, experimental=False),
        EvaluationNode(evaluation="C", depends_on=("B",), enabled=True, experimental=False),
    )
    call_order: list[str] = []

    def run_a(context: object) -> Mapping[str, object]:
        call_order.append("A")
        return _ok_payload()

    def run_b(context: object) -> Mapping[str, object]:
        call_order.append("B")
        raise RuntimeError("boom")

    def run_c(context: object) -> Mapping[str, object]:
        call_order.append("C")
        return _ok_payload()

    result = RuntimeScheduler(
        dag=dag,
        evaluators={"A": run_a, "B": run_b, "C": run_c},
    ).run(context={})
    by_name = {record.evaluation: record for record in result.records}

    assert by_name["B"].status is EvaluationRunStatus.ERROR
    assert result.errors["B"] == "boom"
    assert call_order == ["A", "B", "C"]
    assert result.ok is False


def test_to_eval_results_shape_matches_adapter_report_boundary():
    dag = _dag(EvaluationNode(evaluation="A", depends_on=(), enabled=True, experimental=False))

    result = RuntimeScheduler(dag=dag, evaluators={"A": lambda context: _ok_payload()}).run(context={})
    payload = result.to_eval_results()

    assert list(payload) == ["results", "errors", "skipped", "execution_order", "cache_stats"]
    assert isinstance(payload["execution_order"], list)
    assert payload["cache_stats"] == {}


def test_check_adapter_can_consume_scheduler_output():
    dag = _dag(
        EvaluationNode(
            evaluation="COLUMN_DESIGN",
            depends_on=(),
            enabled=True,
            experimental=False,
        )
    )

    def column_design(context: object) -> Mapping[str, object]:
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
                            "message": "scheduler fixture",
                            "source": "runtime_scheduler_test",
                            "evaluation_level": "DESIGN_LEVEL",
                            "evidence": {"source": "scheduler"},
                        }
                    },
                }
            ]
        }

    scheduler_result = RuntimeScheduler(
        dag=dag,
        evaluators={"COLUMN_DESIGN": column_design},
    ).run(context={})
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    rows = CheckAdapter(catalog).adapt_all(scheduler_result.to_eval_results())

    assert any(row.check_id == "column_geometry" for row in rows)


def test_scheduler_does_not_mutate_context_or_results():
    context = {"geometry": {"section_dims": {"C1": "30x60"}}}
    expected_context = {"geometry": {"section_dims": {"C1": "30x60"}}}
    returned_mapping: Mapping[str, object] = {"outputs": []}
    dag = _dag(EvaluationNode(evaluation="A", depends_on=(), enabled=True, experimental=False))

    result = RuntimeScheduler(dag=dag, evaluators={"A": lambda ctx: returned_mapping}).run(context)

    assert context == expected_context
    assert returned_mapping == {"outputs": []}
    assert result.results["A"] == returned_mapping


def test_runtime_scheduler_has_no_forbidden_imports():
    source_path = ROOT / "tbdy_engine" / "runtime" / "scheduler.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

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


def test_runtime_interface_audit_sees_scheduler_importable():
    from tests import test_runtime_interface_audit as audit

    assert audit.RUNTIME_INTERFACE_STATUS["Scheduler"] == "PRESENT_IMPORTABLE"


def test_scheduler_evaluation_dag_and_dataset_validator_import_independently():
    assert DatasetValidator.__name__ == "DatasetValidator"
    assert EvaluationDAG.__name__ == "EvaluationDAG"
    assert RuntimeScheduler.__name__ == "RuntimeScheduler"
