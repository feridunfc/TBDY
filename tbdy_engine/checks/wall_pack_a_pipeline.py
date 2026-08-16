"""Pack A compatibility wrapper over the single reusable wall-check pipeline."""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.checks.wall_pack_a_contract import PACK_A_CHECK_IDS
from tbdy_engine.checks.wall_pipeline import (
    WallCheckRun,
    WallExecutionEvidence,
    build_wall_check_input,
    run_wall_checks,
    wall_coverage_builder,
)
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.snapshot import FeatureSnapshot

WallPackARun = WallCheckRun
pack_a_coverage_builder = wall_coverage_builder
build_wall_pack_a_check_input = build_wall_check_input


def run_wall_check_pack_a(
    contract_bundle: ContractBundle,
    snapshots: Sequence[FeatureSnapshot],
    *,
    execution_evidence: WallExecutionEvidence | None = None,
) -> WallPackARun:
    return run_wall_checks(
        contract_bundle,
        snapshots,
        PACK_A_CHECK_IDS,
        execution_evidence=execution_evidence,
    )


__all__ = ["WallPackARun", "build_wall_pack_a_check_input", "pack_a_coverage_builder", "run_wall_check_pack_a"]
