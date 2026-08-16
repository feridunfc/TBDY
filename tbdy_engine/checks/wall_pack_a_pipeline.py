"""End-to-end orchestration for P2.10 Wall Check Pack A."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.assessment.wall_pack_a import WallPackAAssessment, assess_wall_pack_a
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import GeometryCheckInput
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.checks.wall_pack_a_contract import PACK_A_CHECK_DEFINITIONS, PACK_A_CHECK_IDS
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.wall_geometry_contract import WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS


@dataclass(frozen=True, slots=True)
class WallPackARun:
    snapshots: tuple[FeatureSnapshot, ...]
    coverage_rows: tuple[CoverageRow, ...]
    check_inputs: tuple[GeometryCheckInput, ...]
    check_results: tuple[CheckResult, ...]
    assessment: WallPackAAssessment


def pack_a_coverage_builder(contract_bundle: ContractBundle) -> CoverageBuilder:
    """Reuse the existing CoverageBuilder with additive Pack A contracts."""
    builder = CoverageBuilder(contract_bundle)
    existing_features = dict(builder.feature_catalog)
    missing_existing = [feature_id for feature_id in ("wall_thickness_mm", "wall_length_mm", "story_height_mm") if feature_id not in existing_features]
    if missing_existing:
        raise ValueError("Pack A requires existing canonical feature(s): " + ", ".join(missing_existing))
    builder.check_catalog = {**dict(builder.check_catalog), **dict(PACK_A_CHECK_DEFINITIONS)}
    builder.feature_catalog = {**existing_features, **dict(WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS)}
    return builder


def build_wall_pack_a_check_input(snapshot: FeatureSnapshot, coverage: CoverageRow) -> GeometryCheckInput:
    definition = PACK_A_CHECK_DEFINITIONS.get(coverage.check_id)
    if definition is None:
        raise ValueError("Coverage row is not a Pack A check")
    expected = tuple(str(name) for name in definition["required_features"])
    if tuple(coverage.required_features) != expected:
        raise ValueError("Coverage required_features differ from frozen Pack A contract")
    if coverage.component_id != snapshot.component_id:
        raise ValueError("Coverage and FeatureSnapshot component identity differ")
    if str(coverage.component_type).casefold() != "wall" or str(snapshot.component_type).casefold() != "wall":
        raise ValueError("Pack A CheckInput requires wall component type")
    evidence_by_feature: dict[str, tuple[FeatureEvidence, ...]] = {}
    for feature_id in expected:
        feature = snapshot.features.get(feature_id)
        evidence_by_feature[feature_id] = tuple(feature.evidence) if feature is not None else ()
    return GeometryCheckInput(
        check_id=coverage.check_id,
        component_id=snapshot.component_id,
        component_type=snapshot.component_type,
        story=None if snapshot.identity.get("story") is None else str(snapshot.identity.get("story")),
        section=None if snapshot.identity.get("section") is None else str(snapshot.identity.get("section")),
        required_features=expected,
        snapshot=snapshot,
        coverage=coverage,
        evidence_by_feature=evidence_by_feature,
    )


def run_wall_check_pack_a(contract_bundle: ContractBundle, snapshots: Sequence[FeatureSnapshot]) -> WallPackARun:
    """Execute all five formal checks through Coverage -> CheckInput -> CheckEngine."""
    coverage_builder = pack_a_coverage_builder(contract_bundle)
    engine = MinimalCheckEngine(coverage_builder.check_catalog)
    coverage_rows: list[CoverageRow] = []
    check_inputs: list[GeometryCheckInput] = []
    results: list[CheckResult] = []
    for snapshot in snapshots:
        if str(snapshot.component_type).casefold() != "wall":
            raise ValueError("Pack A accepts wall FeatureSnapshot objects only")
        for check_id in PACK_A_CHECK_IDS:
            coverage = coverage_builder.build_row(snapshot, check_id)
            check_input = build_wall_pack_a_check_input(snapshot, coverage)
            result = engine.run_input(check_input)
            coverage_rows.append(coverage)
            check_inputs.append(check_input)
            results.append(result)
    assessment = assess_wall_pack_a(results)
    return WallPackARun(
        snapshots=tuple(snapshots), coverage_rows=tuple(coverage_rows), check_inputs=tuple(check_inputs),
        check_results=tuple(results), assessment=assessment,
    )


__all__ = ["WallPackARun", "build_wall_pack_a_check_input", "pack_a_coverage_builder", "run_wall_check_pack_a"]
