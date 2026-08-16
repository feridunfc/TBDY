"""Dumb Pack A serialization.

No engineering threshold, ratio, applicability, or status computation is
allowed here. The serializer only renders canonical CheckResult + Assessment.
"""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.assessment.wall_pack_a import WallPackAAssessment
from tbdy_engine.checks.result import CheckResult


def serialize_wall_pack_a(results: Sequence[CheckResult], assessment: WallPackAAssessment) -> dict[str, object]:
    if any(not isinstance(result, CheckResult) for result in results):
        raise TypeError("Reporter accepts canonical CheckResult objects only")
    if not isinstance(assessment, WallPackAAssessment):
        raise TypeError("Reporter accepts WallPackAAssessment")
    return {
        "report_contract": "P2_10_WALL_CHECK_PACK_A",
        "results": [result.as_dict() for result in results],
        "assessment": assessment.as_dict(),
    }


__all__ = ["serialize_wall_pack_a"]
