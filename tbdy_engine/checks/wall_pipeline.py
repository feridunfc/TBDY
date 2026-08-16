"""Single reusable wall-check orchestration authority for P2.10 and later packs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tbdy_engine.assessment.wall import WallAssessment, assess_wall_results
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import GeometryCheckInput
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.checks.wall_contract import WALL_CHECK_DEFINITIONS
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.wall_geometry_contract import (
    WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS,
    WALL_PACK_B_FEATURE_DEFINITIONS,
)


@dataclass(frozen=True, slots=True)
class WallCheckRun:
    snapshots: tuple[FeatureSnapshot, ...]
    coverage_rows: tuple[CoverageRow, ...]
    check_inputs: tuple[GeometryCheckInput, ...]
    check_results: tuple[CheckResult, ...]
    assessment: WallAssessment


def wall_coverage_builder(contract_bundle: ContractBundle) -> CoverageBuilder:
    builder = CoverageBuilder(contract_bundle)
    existing_features = dict(builder.feature_catalog)
    missing = [name for name in ("wall_thickness_mm", "wall_length_mm", "story_height_mm") if name not in existing_features]
    if missing:
        raise ValueError("Wall checks require existing canonical feature(s): " + ", ".join(missing))
    builder.check_catalog = {**dict(builder.check_catalog), **dict(WALL_CHECK_DEFINITIONS)}
    supplements = {
        **dict(WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS),
        **dict(WALL_PACK_B_FEATURE_DEFINITIONS),
    }
    for key, definition in supplements.items():
        existing_features.setdefault(key, definition)
    builder.feature_catalog = existing_features
    return builder


def build_wall_check_input(snapshot: FeatureSnapshot, coverage: CoverageRow) -> GeometryCheckInput:
    definition = WALL_CHECK_DEFINITIONS.get(coverage.check_id)
    if definition is None:
        raise ValueError("Coverage row is not a registered canonical wall check")
    expected = tuple(str(name) for name in definition.get("required_features", ()))
    if tuple(coverage.required_features) != expected:
        raise ValueError("Coverage required_features differ from registered wall check contract")
    if coverage.component_id != snapshot.component_id:
        raise ValueError("Coverage and FeatureSnapshot component identity differ")
    if str(coverage.component_type).casefold() != "wall" or str(snapshot.component_type).casefold() != "wall":
        raise ValueError("Wall CheckInput requires wall component type")
    evidence_by_feature: dict[str, tuple[FeatureEvidence, ...]] = {}
    for feature_id in expected:
        feature = snapshot.features.get(feature_id)
        evidence_by_feature[feature_id] = tuple(feature.evidence) if feature is not None else ()
    return GeometryCheckInput(
        check_id=coverage.check_id, component_id=snapshot.component_id, component_type=snapshot.component_type,
        story=None if snapshot.identity.get("story") is None else str(snapshot.identity.get("story")),
        section=None if snapshot.identity.get("assigned_wall_property") is None else str(snapshot.identity.get("assigned_wall_property")),
        required_features=expected, snapshot=snapshot, coverage=coverage, evidence_by_feature=evidence_by_feature,
    )


def run_wall_checks(
    contract_bundle: ContractBundle, snapshots: Sequence[FeatureSnapshot], check_ids: Sequence[str],
    *, engineering_context: Mapping[str, Any] | None = None,
) -> WallCheckRun:
    selected = tuple(str(check_id) for check_id in check_ids)
    unknown = sorted(set(selected) - set(WALL_CHECK_DEFINITIONS))
    if unknown:
        raise ValueError("Unknown wall check ID(s): " + ", ".join(unknown))
    builder = wall_coverage_builder(contract_bundle)
    engine = MinimalCheckEngine(builder.check_catalog)
    coverage_rows: list[CoverageRow] = []
    check_inputs: list[GeometryCheckInput] = []
    results: list[CheckResult] = []
    for snapshot in snapshots:
        if str(snapshot.component_type).casefold() != "wall":
            raise ValueError("run_wall_checks accepts wall FeatureSnapshot objects only")
        for check_id in selected:
            coverage = builder.build_row(snapshot, check_id)
            check_input = build_wall_check_input(snapshot, coverage)
            result = engine.run_input(check_input, engineering_context=engineering_context)
            coverage_rows.append(coverage); check_inputs.append(check_input); results.append(result)
    return WallCheckRun(
        snapshots=tuple(snapshots), coverage_rows=tuple(coverage_rows), check_inputs=tuple(check_inputs),
        check_results=tuple(results), assessment=assess_wall_results(results, check_ids=selected),
    )


__all__ = ["WallCheckRun", "build_wall_check_input", "run_wall_checks", "wall_coverage_builder"]
