"""Single wall assessment authority.

Consumes canonical CheckResult objects only. No engineering formula, applicability
rule, or source selection belongs in this module.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus


@dataclass(frozen=True, slots=True)
class WallAssessment:
    total_results: int
    status_counts: Mapping[str, int]
    evaluated_results: int
    blocked_results: int
    coverage_complete: bool
    wall_check_status: str
    check_ids: tuple[str, ...]
    full_tbdy_compliance_status: str = "NOT_EVALUATED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_counts", MappingProxyType(dict(self.status_counts)))
        object.__setattr__(self, "check_ids", tuple(self.check_ids))
        if self.full_tbdy_compliance_status != "NOT_EVALUATED":
            raise ValueError("Wall checks cannot establish full TBDY compliance")

    @property
    def pack_a_status(self) -> str:
        """Compatibility display alias; no Pack-A-specific calculation."""
        return self.wall_check_status

    def as_dict(self) -> dict[str, object]:
        return {
            "total_results": self.total_results,
            "status_counts": dict(self.status_counts),
            "evaluated_results": self.evaluated_results,
            "blocked_results": self.blocked_results,
            "coverage_complete": self.coverage_complete,
            "wall_check_status": self.wall_check_status,
            "check_ids": list(self.check_ids),
            "full_tbdy_compliance_status": self.full_tbdy_compliance_status,
        }


def assess_wall_results(results: Sequence[CheckResult], *, check_ids: Sequence[str]) -> WallAssessment:
    expected = tuple(str(check_id) for check_id in check_ids)
    if any(not isinstance(result, CheckResult) for result in results):
        raise TypeError("Assessment accepts canonical CheckResult objects only")
    unexpected = sorted({result.check_id for result in results} - set(expected))
    if unexpected:
        raise ValueError("Assessment received result outside requested wall check set: " + ", ".join(unexpected))
    counts = Counter(result.status.value for result in results)
    incomplete = counts[CheckStatus.BLOCKED.value] + counts[CheckStatus.NO_DATA.value] + counts[CheckStatus.WARNING.value]
    failures = counts[CheckStatus.FAIL.value]
    evaluated = counts[CheckStatus.OK.value] + counts[CheckStatus.FAIL.value] + counts[CheckStatus.OUT_OF_SCOPE.value]
    if failures:
        status = "FAILURES_PRESENT"
    elif incomplete:
        status = "INCOMPLETE"
    else:
        status = "EVALUATED_NO_FAILURES"
    return WallAssessment(
        total_results=len(results),
        status_counts=counts,
        evaluated_results=evaluated,
        blocked_results=counts[CheckStatus.BLOCKED.value] + counts[CheckStatus.NO_DATA.value],
        coverage_complete=incomplete == 0,
        wall_check_status=status,
        check_ids=expected,
    )


__all__ = ["WallAssessment", "assess_wall_results"]
