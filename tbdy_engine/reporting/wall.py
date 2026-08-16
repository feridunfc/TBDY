"""Serialization-only wall reporter."""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.assessment.wall import WallAssessment
from tbdy_engine.checks.result import CheckResult


def serialize_wall_results(results: Sequence[CheckResult], assessment: WallAssessment, *, report_contract: str) -> dict[str, object]:
    if any(not isinstance(result, CheckResult) for result in results):
        raise TypeError("Reporter accepts canonical CheckResult objects only")
    if not isinstance(assessment, WallAssessment):
        raise TypeError("Reporter accepts canonical WallAssessment")
    return {
        "report_contract": str(report_contract),
        "results": [result.as_dict() for result in results],
        "assessment": assessment.as_dict(),
    }


__all__ = ["serialize_wall_results"]
