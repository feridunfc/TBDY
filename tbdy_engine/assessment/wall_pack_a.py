"""Minimal Pack A assessment authority.

Assessment consumes canonical CheckResults only. It never evaluates engineering
formulas and never upgrades Pack A into full TBDY compliance.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus


@dataclass(frozen=True, slots=True)
class WallPackAAssessment:
    total_results: int
    status_counts: Mapping[str, int]
    evaluated_results: int
    blocked_results: int
    coverage_complete: bool
    pack_a_status: str
    full_tbdy_compliance_status: str = "NOT_EVALUATED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_counts", MappingProxyType(dict(self.status_counts)))
        if self.full_tbdy_compliance_status != "NOT_EVALUATED":
            raise ValueError("Pack A cannot establish full TBDY compliance")

    def as_dict(self) -> dict[str, object]:
        return {
            "total_results": self.total_results,
            "status_counts": dict(self.status_counts),
            "evaluated_results": self.evaluated_results,
            "blocked_results": self.blocked_results,
            "coverage_complete": self.coverage_complete,
            "pack_a_status": self.pack_a_status,
            "full_tbdy_compliance_status": self.full_tbdy_compliance_status,
        }


def assess_wall_pack_a(results: Sequence[CheckResult]) -> WallPackAAssessment:
    if any(not isinstance(result, CheckResult) for result in results):
        raise TypeError("Assessment accepts canonical CheckResult objects only")
    counts = Counter(result.status.value for result in results)
    incomplete = counts[CheckStatus.BLOCKED.value] + counts[CheckStatus.NO_DATA.value] + counts[CheckStatus.WARNING.value]
    failures = counts[CheckStatus.FAIL.value]
    evaluated = counts[CheckStatus.OK.value] + counts[CheckStatus.FAIL.value] + counts[CheckStatus.OUT_OF_SCOPE.value]
    if failures:
        pack_status = "FAILURES_PRESENT"
    elif incomplete:
        pack_status = "INCOMPLETE"
    else:
        pack_status = "EVALUATED_NO_FAILURES"
    return WallPackAAssessment(
        total_results=len(results),
        status_counts=counts,
        evaluated_results=evaluated,
        blocked_results=counts[CheckStatus.BLOCKED.value] + counts[CheckStatus.NO_DATA.value],
        coverage_complete=incomplete == 0,
        pack_a_status=pack_status,
    )


__all__ = ["WallPackAAssessment", "assess_wall_pack_a"]
