from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.runtime.evaluation_dag import EvaluationDAG, EvaluationNode
from tbdy_engine.runtime.evaluation_result import EvaluationRecord, EvaluationResult, EvaluationStatus
from tbdy_engine.runtime.scheduler import (
    EvaluationRunRecord,
    EvaluationRunStatus,
    RuntimeScheduler,
    SchedulerResult,
)


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


def _records() -> tuple[EvaluationRecord, ...]:
    return (
        EvaluationRecord(
            evaluation="A",
            status=EvaluationStatus.OK,
            result={"outputs": []},
            error=None,
        ),
        EvaluationRecord(
            evaluation="B",
            status=EvaluationStatus.ERROR,
            result=None,
            error="boom",
        ),
        EvaluationRecord(
            evaluation="C",
            status=EvaluationStatus.SKIPPED,
            result=None,
            error="no evaluator",
        ),
    )


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
                        "message": "evaluation result fixture",
                        "source": "evaluation_result_test",
                        "evaluation_level": "DESIGN_LEVEL",
                        "evidence": {"source": "evaluation_result"},
                    }
                },
            }
        ]
    }


def test_evaluation_result_properties():
    result = EvaluationResult(records=_records())

    assert result.results == {"A": {"outputs": []}}
    assert result.errors == {"B": "boom"}
    assert result.skipped == {"C": "no evaluator"}
    assert result.execution_order == ("A", "B", "C")
    assert result.ok is False


def test_to_eval_results_stable_adapter_report_shape():
    result = EvaluationResult(records=_records())
    payload = result.to_eval_results()

    assert list(payload) == ["results", "errors", "skipped", "execution_order", "cache_stats"]
    assert isinstance(payload["execution_order"], list)
    assert isinstance(payload["cache_stats"], dict)


def test_to_dict_stable_shape():
    result = EvaluationResult(records=_records())
    payload = result.to_dict()

    assert list(payload) == [
        "ok",
        "records",
        "results",
        "errors",
        "skipped",
        "execution_order",
        "cache_stats",
    ]
    assert payload["ok"] is False
    assert isinstance(payload["records"], list)


def test_from_records_supports_iterable_and_cache_stats():
    cache_stats = {"hits": 1, "misses": 2}
    result = EvaluationResult.from_records((record for record in _records()), cache_stats=cache_stats)

    assert result.records == _records()
    assert result.to_eval_results()["cache_stats"] == cache_stats


def test_check_adapter_consumes_evaluation_result_to_eval_results():
    result = EvaluationResult.from_records(
        (
            EvaluationRecord(
                evaluation="COLUMN_DESIGN",
                status=EvaluationStatus.OK,
                result=_column_design_payload(),
                error=None,
            ),
        )
    )
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    rows = CheckAdapter(catalog).adapt_all(result.to_eval_results())

    assert any(row.check_id == "column_geometry" for row in rows)


def test_scheduler_result_compatibility_aliases():
    result = SchedulerResult(
        records=(
            EvaluationRunRecord(
                evaluation="A",
                status=EvaluationRunStatus.OK,
                result={"outputs": []},
                error=None,
            ),
        )
    )

    assert SchedulerResult is EvaluationResult
    assert EvaluationRunRecord is EvaluationRecord
    assert EvaluationRunStatus is EvaluationStatus
    assert EvaluationRunStatus.OK is EvaluationStatus.OK
    assert list(result.to_eval_results()) == [
        "results",
        "errors",
        "skipped",
        "execution_order",
        "cache_stats",
    ]


def test_runtime_scheduler_run_returns_evaluation_result_compatible_object():
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
    payload = result.to_eval_results()
    catalog = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()
    rows = CheckAdapter(catalog).adapt_all(payload)

    assert isinstance(result, EvaluationResult)
    assert list(payload) == ["results", "errors", "skipped", "execution_order", "cache_stats"]
    assert any(row.check_id == "column_geometry" for row in rows)


def test_evaluation_result_and_scheduler_have_no_forbidden_imports():
    for relative_path in (
        "tbdy_engine/runtime/evaluation_result.py",
        "tbdy_engine/runtime/scheduler.py",
    ):
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
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


def test_runtime_interface_audit_sees_evaluation_result_importable():
    from tests import test_runtime_interface_audit as audit

    assert audit.RUNTIME_INTERFACE_STATUS["EvaluationResult"] == "PRESENT_IMPORTABLE"


def test_runner_v2_bridge_still_uses_to_eval_results_and_not_run_all():
    source = (ROOT / "tbdy_engine" / "runner_v2.py").read_text(encoding="utf-8")

    assert "to_eval_results()" in source
    assert "run_all(" not in source
