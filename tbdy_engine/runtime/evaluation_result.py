from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType


class EvaluationStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class EvaluationRecord:
    evaluation: str
    status: EvaluationStatus
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
class EvaluationResult:
    records: tuple[EvaluationRecord, ...]
    cache_stats: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_records(
        cls,
        records: Iterable[EvaluationRecord],
        cache_stats: Mapping[str, object] | None = None,
    ) -> "EvaluationResult":
        return cls(
            records=tuple(records),
            cache_stats=dict(cache_stats or {}),
        )

    @property
    def results(self) -> dict[str, Mapping[str, object]]:
        return {
            record.evaluation: record.result
            for record in self.records
            if record.status is EvaluationStatus.OK and record.result is not None
        }

    @property
    def errors(self) -> dict[str, str]:
        return {
            record.evaluation: record.error or "ERROR"
            for record in self.records
            if record.status is EvaluationStatus.ERROR
        }

    @property
    def skipped(self) -> dict[str, str]:
        return {
            record.evaluation: record.error or "SKIPPED"
            for record in self.records
            if record.status is EvaluationStatus.SKIPPED
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
            "cache_stats": dict(self.cache_stats),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "records": [record.to_dict() for record in self.records],
            "results": self.results,
            "errors": self.errors,
            "skipped": self.skipped,
            "execution_order": list(self.execution_order),
            "cache_stats": dict(self.cache_stats),
        }
