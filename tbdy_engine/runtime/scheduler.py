from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from tbdy_engine.runtime.evaluation_dag import EvaluationDAG
from tbdy_engine.runtime.evaluation_result import EvaluationRecord, EvaluationResult, EvaluationStatus


class EvaluationCallable(Protocol):
    def __call__(self, context: object) -> Mapping[str, object]: ...


EvaluationRunStatus = EvaluationStatus
EvaluationRunRecord = EvaluationRecord
SchedulerResult = EvaluationResult


@dataclass(frozen=True)
class RuntimeScheduler:
    dag: EvaluationDAG
    evaluators: Mapping[str, EvaluationCallable]

    def run(self, context: object, *, enabled_only: bool = True) -> SchedulerResult:
        records: list[EvaluationRecord] = []

        for evaluation in self.dag.topological_order(enabled_only=enabled_only):
            evaluator = self.evaluators.get(evaluation)
            if evaluator is None:
                records.append(
                    EvaluationRecord(
                        evaluation=evaluation,
                        status=EvaluationStatus.SKIPPED,
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
                    EvaluationRecord(
                        evaluation=evaluation,
                        status=EvaluationStatus.ERROR,
                        result=None,
                        error=message,
                    )
                )
                continue

            records.append(
                EvaluationRecord(
                    evaluation=evaluation,
                    status=EvaluationStatus.OK,
                    result=result,
                    error=None,
                )
            )

        return EvaluationResult.from_records(records)


Scheduler = RuntimeScheduler
