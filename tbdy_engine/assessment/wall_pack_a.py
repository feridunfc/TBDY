"""Pack A assessment compatibility wrapper over the single wall authority."""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.assessment.wall import WallAssessment, assess_wall_results
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.checks.wall_pack_a_contract import PACK_A_CHECK_IDS

WallPackAAssessment = WallAssessment


def assess_wall_pack_a(results: Sequence[CheckResult]) -> WallPackAAssessment:
    return assess_wall_results(results, check_ids=PACK_A_CHECK_IDS)


__all__ = ["WallPackAAssessment", "assess_wall_pack_a"]
