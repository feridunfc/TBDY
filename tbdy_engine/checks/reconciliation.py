"""Small structural CheckResult reconciliation primitive.

This module is intentionally non-engineering.  It compares an expected
component x check-id inventory with emitted canonical CheckResult identities.
It never evaluates formulas, applicability, coverage, limits, or verdicts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from tbdy_engine.checks.result import CheckResult


ResultIdentity = tuple[str, str]


@dataclass(frozen=True, slots=True)
class CheckResultReconciliation:
    expected_result_count: int
    actual_result_count: int
    missing_result_count: int
    duplicate_result_count: int
    missing: tuple[ResultIdentity, ...]
    duplicates: tuple[ResultIdentity, ...]

    @property
    def structurally_complete(self) -> bool:
        return (
            self.actual_result_count == self.expected_result_count
            and self.missing_result_count == 0
            and self.duplicate_result_count == 0
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "expected_result_count": self.expected_result_count,
            "actual_result_count": self.actual_result_count,
            "missing_result_count": self.missing_result_count,
            "duplicate_result_count": self.duplicate_result_count,
            "missing": [list(item) for item in self.missing],
            "duplicates": [list(item) for item in self.duplicates],
            "structurally_complete": self.structurally_complete,
        }


def reconcile_check_results(
    *,
    component_ids: Iterable[str],
    check_ids: Iterable[str],
    results: Sequence[CheckResult],
) -> CheckResultReconciliation:
    """Reconcile exactly the supplied canonical inventory, deterministically."""
    components = tuple(sorted({str(item) for item in component_ids}))
    checks = tuple(sorted({str(item) for item in check_ids}))
    expected = tuple((component_id, check_id) for component_id in components for check_id in checks)
    expected_set = set(expected)

    counts: Counter[ResultIdentity] = Counter()
    for result in results:
        if not isinstance(result, CheckResult):
            raise TypeError("results must contain canonical CheckResult objects")
        identity = (result.component, result.check_id)
        if identity in expected_set:
            counts[identity] += 1

    missing = tuple(identity for identity in expected if counts[identity] == 0)
    duplicates = tuple(identity for identity in expected if counts[identity] > 1)
    actual_count = sum(counts.values())
    duplicate_count = sum(max(0, counts[identity] - 1) for identity in expected)
    return CheckResultReconciliation(
        expected_result_count=len(expected),
        actual_result_count=actual_count,
        missing_result_count=len(missing),
        duplicate_result_count=duplicate_count,
        missing=missing,
        duplicates=duplicates,
    )


__all__ = [
    "CheckResultReconciliation",
    "ResultIdentity",
    "reconcile_check_results",
]
