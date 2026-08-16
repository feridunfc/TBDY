"""Single wall assessment authority.

Consumes canonical CheckResult objects only. No engineering formula,
applicability rule, or source selection belongs in this module.
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
    expected_result_count: int
    actual_result_count: int
    missing_result_count: int
    duplicate_result_count: int
    full_tbdy_compliance_status: str = "NOT_EVALUATED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_counts", MappingProxyType(dict(self.status_counts)))
        object.__setattr__(self, "check_ids", tuple(self.check_ids))
        if self.total_results != self.actual_result_count:
            raise ValueError("WallAssessment.total_results must equal actual_result_count")
        for name in (
            "expected_result_count", "actual_result_count", "missing_result_count", "duplicate_result_count"
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.coverage_complete and (self.missing_result_count or self.duplicate_result_count):
            raise ValueError("coverage_complete cannot be true with missing/duplicate formal results")
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
            "expected_result_count": self.expected_result_count,
            "actual_result_count": self.actual_result_count,
            "missing_result_count": self.missing_result_count,
            "duplicate_result_count": self.duplicate_result_count,
            "full_tbdy_compliance_status": self.full_tbdy_compliance_status,
        }


def assess_wall_results(
    results: Sequence[CheckResult],
    *,
    check_ids: Sequence[str],
    component_ids: Sequence[str] | None = None,
) -> WallAssessment:
    normalized_results = tuple(results)
    expected_checks = tuple(str(check_id) for check_id in check_ids)
    if len(expected_checks) != len(set(expected_checks)):
        raise ValueError("Wall assessment check_ids must be unique")
    if any(not isinstance(result, CheckResult) for result in normalized_results):
        raise TypeError("Assessment accepts canonical CheckResult objects only")
    unexpected_checks = sorted({result.check_id for result in normalized_results} - set(expected_checks))
    if unexpected_checks:
        raise ValueError("Assessment received result outside requested wall check set: " + ", ".join(unexpected_checks))

    if component_ids is None:
        inferred: list[str] = []
        seen: set[str] = set()
        for result in normalized_results:
            component = str(result.component)
            if component not in seen:
                seen.add(component)
                inferred.append(component)
        expected_components = tuple(inferred)
    else:
        expected_components = tuple(str(component_id) for component_id in component_ids)
        if len(expected_components) != len(set(expected_components)):
            raise ValueError("Wall assessment component_ids must be unique")
        unexpected_components = sorted({str(result.component) for result in normalized_results} - set(expected_components))
        if unexpected_components:
            raise ValueError("Assessment received result for unexpected component: " + ", ".join(unexpected_components))

    expected_keys = {(component, check_id) for component in expected_components for check_id in expected_checks}
    actual_key_counts = Counter((str(result.component), result.check_id) for result in normalized_results)
    missing_result_count = sum(1 for key in expected_keys if actual_key_counts[key] == 0)
    duplicate_result_count = sum(max(count - 1, 0) for key, count in actual_key_counts.items() if key in expected_keys)
    expected_result_count = len(expected_keys)
    actual_result_count = len(normalized_results)

    counts = Counter(result.status.value for result in normalized_results)
    mandatory_incomplete = (
        counts[CheckStatus.BLOCKED.value]
        + counts[CheckStatus.NO_DATA.value]
        + counts[CheckStatus.WARNING.value]
    )
    failures = counts[CheckStatus.FAIL.value]
    evaluated = (
        counts[CheckStatus.OK.value]
        + counts[CheckStatus.FAIL.value]
        + counts[CheckStatus.OUT_OF_SCOPE.value]
    )
    reconciliation_incomplete = missing_result_count + duplicate_result_count
    if failures:
        status = "FAILURES_PRESENT"
    elif mandatory_incomplete or reconciliation_incomplete:
        status = "INCOMPLETE"
    else:
        status = "EVALUATED_NO_FAILURES"
    return WallAssessment(
        total_results=actual_result_count,
        status_counts=counts,
        evaluated_results=evaluated,
        blocked_results=counts[CheckStatus.BLOCKED.value] + counts[CheckStatus.NO_DATA.value],
        coverage_complete=(mandatory_incomplete == 0 and missing_result_count == 0 and duplicate_result_count == 0),
        wall_check_status=status,
        check_ids=expected_checks,
        expected_result_count=expected_result_count,
        actual_result_count=actual_result_count,
        missing_result_count=missing_result_count,
        duplicate_result_count=duplicate_result_count,
    )


__all__ = ["WallAssessment", "assess_wall_results"]
