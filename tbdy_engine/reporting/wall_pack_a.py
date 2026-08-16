"""Pack A compatibility serializer over the single wall reporter."""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.assessment.wall_pack_a import WallPackAAssessment
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.reporting.wall import serialize_wall_results


def serialize_wall_pack_a(results: Sequence[CheckResult], assessment: WallPackAAssessment) -> dict[str, object]:
    return serialize_wall_results(results, assessment, report_contract="P2_10_WALL_CHECK_PACK_A")


__all__ = ["serialize_wall_pack_a"]
