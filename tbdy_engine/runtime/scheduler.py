from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tbdy_engine.runtime.evaluation_dag import EvaluationDAG


class EvaluationCallable(Protocol):
    def __call__(self, context: object) -> Mapping[str, object]: ...


class EvaluationRunStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class EvaluationRunRecord:
    evaluation: str
    status: EvaluationRunStatus
    result: Mapping[str, object] | None
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "evaluation": self.evaluation,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
        }


@dataclass(frozen=True)
class SchedulerResult:
    records: tuple[EvaluationRunRecord, ...]

    @property
    def results(self) -> dict[str, Mapping[str, object]]:
        return {
            record.evaluation: record.result
            for record in self.records
            if record.status is EvaluationRunStatus.OK and record.result is not None
        }

    @property
    def errors(self) -> dict[str, str]:
        return {
            record.evaluation: record.error or "ERROR"
            for record in self.records
            if record.status is EvaluationRunStatus.ERROR
        }

    @property
    def skipped(self) -> dict[str, str]:
        return {
            record.evaluation: record.error or "SKIPPED"
            for record in self.records
            if record.status is EvaluationRunStatus.SKIPPED
        }

    @property
    def execution_order(self) -> tuple[str, ...]:
        return tuple(record.evaluation for record in self.records)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_eval_results(self) -> dict[str, object]:
        return {
            "results": self.results,
            "errors": self.errors,
            "skipped": self.skipped,
            "execution_order": list(self.execution_order),
            "cache_stats": {},
        }


@dataclass(frozen=True)
class RuntimeScheduler:
    dag: EvaluationDAG
    evaluators: Mapping[str, EvaluationCallable]

    def run(self, context: object, *, enabled_only: bool = True) -> SchedulerResult:
        records: list[EvaluationRunRecord] = []

        for evaluation in self.dag.topological_order(enabled_only=enabled_only):
            evaluator = self.evaluators.get(evaluation)
            if evaluator is None:
                records.append(
                    EvaluationRunRecord(
                        evaluation=evaluation,
                        status=EvaluationRunStatus.SKIPPED,
                        result=None,
                        error=f"No evaluator registered for '{evaluation}'.",
                    )
                )
                continue

            try:
                result = evaluator(context)
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                records.append(
                    EvaluationRunRecord(
                        evaluation=evaluation,
                        status=EvaluationRunStatus.ERROR,
                        result=None,
                        error=message,
                    )
                )
                continue

            records.append(
                EvaluationRunRecord(
                    evaluation=evaluation,
                    status=EvaluationRunStatus.OK,
                    result=result,
                    error=None,
                )
            )

        return SchedulerResult(records=tuple(records))
Scheduler = RuntimeScheduler