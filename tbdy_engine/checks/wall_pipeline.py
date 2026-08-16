"""Single reusable wall-check orchestration authority for P2.10 and later packs."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.assessment.wall import WallAssessment, assess_wall_results
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import CheckExecutionContext, GeometryCheckInput
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.checks.ndm_selection import ReviewedNdmLoadBinding, ReviewedNdmPolicy
from tbdy_engine.checks.wall_applicability import (
    ReviewedWallSystemContext, derive_ndm_n, special_branch_context_readiness,
)
from tbdy_engine.checks.wall_contract import WALL_CHECK_DEFINITIONS
from tbdy_engine.contracts.models import ContractBundle, freeze_data
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageExecutionContextReadiness, CoverageExecutionContextStatus, CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.result_evidence import ResultRowEvidenceBundle
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.features.wall_critical_evidence import (
    WallCriticalHeightFactualEvidence,
    WallRegulatoryReferenceFacts,
)
from tbdy_engine.features.wall_geometry_contract import (
    WALL_GEOMETRY_SUPPLEMENTAL_FEATURE_DEFINITIONS,
    WALL_PACK_B_FEATURE_DEFINITIONS,
)


@dataclass(frozen=True, slots=True)
class WallExecutionEvidence:
    """Run-level evidence from which per-check canonical CheckInput context is frozen."""

    wall_system_context: ReviewedWallSystemContext | None = None
    highest_applicable_story_height_mm_by_component: Mapping[str, float] = field(default_factory=dict)
    result_bundles: Mapping[str, ResultRowEvidenceBundle] = field(default_factory=dict)
    wall_to_pier: Mapping[str, str] = field(default_factory=dict)
    ndm_load_binding: ReviewedNdmLoadBinding | None = None
    ndm_policy: ReviewedNdmPolicy | None = None
    net_section_topology_by_component: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    critical_height_facts_by_component: Mapping[str, WallCriticalHeightFactualEvidence] = field(default_factory=dict)
    pack_c_reference_facts: WallRegulatoryReferenceFacts | None = None

    def __post_init__(self) -> None:
        if self.wall_system_context is not None and not isinstance(self.wall_system_context, ReviewedWallSystemContext):
            raise TypeError("wall_system_context must be ReviewedWallSystemContext or None")
        if self.pack_c_reference_facts is not None and not isinstance(self.pack_c_reference_facts, WallRegulatoryReferenceFacts):
            raise TypeError("pack_c_reference_facts must be WallRegulatoryReferenceFacts or None")
        if self.ndm_load_binding is not None and not isinstance(self.ndm_load_binding, ReviewedNdmLoadBinding):
            raise TypeError("ndm_load_binding must be ReviewedNdmLoadBinding or None")
        if self.ndm_policy is not None and not isinstance(self.ndm_policy, ReviewedNdmPolicy):
            raise TypeError("ndm_policy must be ReviewedNdmPolicy or None")
        bundles = dict(self.result_bundles or {})
        if any(not isinstance(bundle, ResultRowEvidenceBundle) for bundle in bundles.values()):
            raise TypeError("result_bundles values must be ResultRowEvidenceBundle objects")
        critical = dict(self.critical_height_facts_by_component or {})
        if any(not isinstance(bundle, WallCriticalHeightFactualEvidence) for bundle in critical.values()):
            raise TypeError("critical_height_facts_by_component values must be WallCriticalHeightFactualEvidence")
        for component_id, bundle in critical.items():
            if str(component_id) != bundle.component_id:
                raise ValueError("Pack C factual-evidence mapping key must equal bundle.component_id")
        object.__setattr__(self, "highest_applicable_story_height_mm_by_component", freeze_data(dict(self.highest_applicable_story_height_mm_by_component or {})))
        object.__setattr__(self, "result_bundles", MappingProxyType(bundles))
        object.__setattr__(self, "wall_to_pier", freeze_data(dict(self.wall_to_pier or {})))
        object.__setattr__(self, "net_section_topology_by_component", freeze_data(dict(self.net_section_topology_by_component or {})))
        object.__setattr__(self, "critical_height_facts_by_component", MappingProxyType(critical))


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


def build_wall_check_input(
    snapshot: FeatureSnapshot,
    coverage: CoverageRow,
    execution_context: CheckExecutionContext | None = None,
) -> GeometryCheckInput:
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
        check_id=coverage.check_id,
        component_id=snapshot.component_id,
        component_type=snapshot.component_type,
        story=None if snapshot.identity.get("story") is None else str(snapshot.identity.get("story")),
        section=None if snapshot.identity.get("assigned_wall_property") is None else str(snapshot.identity.get("assigned_wall_property")),
        required_features=expected,
        snapshot=snapshot,
        coverage=coverage,
        evidence_by_feature=evidence_by_feature,
        execution_context=execution_context or CheckExecutionContext(),
    )


def _known_basement(snapshot: FeatureSnapshot) -> bool:
    feature = snapshot.features.get("wall_is_basement")
    return bool(
        feature is not None
        and feature.status == FeatureValueStatus.RESOLVED
        and feature.value is True
    )


def _system_context_readiness(
    system_context: ReviewedWallSystemContext | None,
    *,
    known_out_of_scope: bool,
) -> CoverageExecutionContextReadiness:
    if known_out_of_scope:
        return CoverageExecutionContextReadiness(
            context_name="wall_system_context",
            status=CoverageExecutionContextStatus.READY,
        )
    ready, reason = special_branch_context_readiness(system_context)
    if not ready:
        return CoverageExecutionContextReadiness(
            context_name="wall_system_context",
            status=CoverageExecutionContextStatus.BLOCKED,
            reason=reason or "System-level §7.6.1.3 execution context is unresolved",
        )
    return CoverageExecutionContextReadiness(
        context_name="wall_system_context",
        status=CoverageExecutionContextStatus.READY,
    )


def _pack_c_readiness(
    context_name: str,
    facts: WallCriticalHeightFactualEvidence | None,
    component_id: str,
    reference_facts: WallRegulatoryReferenceFacts | None,
) -> CoverageExecutionContextReadiness:
    def blocked(reason: str) -> CoverageExecutionContextReadiness:
        return CoverageExecutionContextReadiness(
            context_name=context_name,
            status=CoverageExecutionContextStatus.BLOCKED,
            reason=reason,
        )
    if facts is None:
        return blocked("Canonical Pack C wall factual evidence is absent")
    if facts.component_id != component_id:
        return blocked("Pack C factual evidence component identity does not match wall candidate")
    if context_name == "wall_vertical_profile":
        if not facts.story_geometry:
            return blocked("Story-by-story wall geometry is unavailable")
        if facts.vertical_continuity_proven is not True:
            return blocked("Wall vertical continuity is not proven by factual source evidence")
    elif context_name == "wall_section_reduction_evidence":
        if facts.section_reduction_evidence_complete is not True:
            return blocked("Story-by-story plan-length/section-width reduction evidence is incomplete")
    elif context_name == "wall_regulatory_reference_facts":
        ref = reference_facts
        if ref is None or ref.foundation_top_elevation_mm is None:
            return blocked("Run-level foundation-top/regulatory reference factual evidence is unavailable")
        perimeter = ref.rigid_basement_perimeter_walls
        diaphragm = ref.rigid_basement_diaphragm
        rigid_false_proven = perimeter is False or diaphragm is False
        rigid_true_proven = perimeter is True and diaphragm is True
        if not rigid_false_proven and not rigid_true_proven:
            return blocked("Run-level rigid-basement applicability facts are incomplete")
        if rigid_true_proven and ref.ground_floor_elevation_mm is None:
            return blocked("Rigid-basement case requires proven run-level ground-floor elevation")
        if rigid_true_proven and ref.first_basement_story_height_mm is None:
            return blocked("Rigid-basement case requires proven run-level first-basement story height")
    else:
        return blocked("Unknown Pack C execution-context contract")
    return CoverageExecutionContextReadiness(
        context_name=context_name,
        status=CoverageExecutionContextStatus.READY,
    )


def _execution_materialization(
    *,
    snapshot: FeatureSnapshot,
    check_id: str,
    execution_evidence: WallExecutionEvidence,
) -> tuple[Mapping[str, CoverageExecutionContextReadiness], CheckExecutionContext]:
    component_id = snapshot.component_id
    definition = WALL_CHECK_DEFINITIONS[check_id]
    required = tuple(str(name) for name in (definition.get("required_execution_context", ()) or ()))
    readiness: dict[str, CoverageExecutionContextReadiness] = {}
    values: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    pack_c_names = {
        "wall_vertical_profile", "wall_regulatory_reference_facts",
        "wall_section_reduction_evidence",
    }
    critical_facts = execution_evidence.critical_height_facts_by_component.get(component_id)
    reference_facts = execution_evidence.pack_c_reference_facts
    if critical_facts is not None:
        evidence["wall_critical_height_facts"] = critical_facts
    if "wall_regulatory_reference_facts" in required and reference_facts is not None:
        values["wall_regulatory_reference_facts"] = reference_facts
    for name in required:
        if name in pack_c_names:
            readiness[name] = _pack_c_readiness(name, critical_facts, component_id, reference_facts)
        elif name == "wall_system_context":
            row = _system_context_readiness(
                execution_evidence.wall_system_context,
                known_out_of_scope=_known_basement(snapshot),
            )
            readiness[name] = row
            if execution_evidence.wall_system_context is not None:
                values[name] = execution_evidence.wall_system_context
        elif name == "highest_applicable_story_height_mm":
            if _known_basement(snapshot):
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                continue
            value = execution_evidence.highest_applicable_story_height_mm_by_component.get(component_id)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name,
                    status=CoverageExecutionContextStatus.BLOCKED,
                    reason="Highest applicable story height is absent or unproven for this wall",
                )
            else:
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                values[name] = float(value)
        elif name == "pier_forces_result_bundle":
            if _known_basement(snapshot):
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                continue
            bundle = execution_evidence.result_bundles.get("pier_forces")
            if bundle is None:
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name,
                    status=CoverageExecutionContextStatus.BLOCKED,
                    reason="Pier Forces raw result bundle is absent",
                )
            elif not bundle.is_full_capture:
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name,
                    status=CoverageExecutionContextStatus.PARTIAL,
                    reason="Pier Forces runtime acquisition is not FULL",
                )
                evidence[name] = bundle
            else:
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                evidence[name] = bundle
        elif name == "wall_to_pier_binding":
            if _known_basement(snapshot):
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                continue
            pier = execution_evidence.wall_to_pier.get(component_id)
            if not isinstance(pier, str) or not pier:
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name,
                    status=CoverageExecutionContextStatus.BLOCKED,
                    reason="Wall-to-pier result identity is unavailable",
                )
            else:
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                values[name] = pier
        elif name == "ndm_demand":
            if _known_basement(snapshot):
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                continue
            bundle = execution_evidence.result_bundles.get("pier_forces")
            pier = execution_evidence.wall_to_pier.get(component_id)
            story = snapshot.identity.get("story")
            demand = derive_ndm_n(
                component_id=component_id,
                story_name=None if story is None else str(story),
                pier_name=None if pier is None else str(pier),
                pier_forces=bundle,
                load_binding=execution_evidence.ndm_load_binding,
                policy=execution_evidence.ndm_policy,
            )
            if demand.status == "BLOCKED":
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name, status=CoverageExecutionContextStatus.BLOCKED,
                    reason=demand.diagnostic or "Ndm result selection is blocked",
                )
            else:
                # RESOLVED and authoritative NO_DATA are both completed selection outcomes.
                # The latter is propagated by CheckEngine as NO_DATA rather than guessed BLOCKED.
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name, status=CoverageExecutionContextStatus.READY
                )
                values[name] = demand
                if demand.evidence:
                    evidence["ndm_selection_trace"] = demand.evidence[0]
        elif name == "net_section_topology":
            if _known_basement(snapshot):
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                continue
            topology = execution_evidence.net_section_topology_by_component.get(component_id)
            if not isinstance(topology, Mapping):
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name,
                    status=CoverageExecutionContextStatus.BLOCKED,
                    reason="Exact wall net-section/opening topology is unavailable",
                )
            elif topology.get("topology_verified") is not True or topology.get("section_semantics_verified") is not True:
                readiness[name] = CoverageExecutionContextReadiness(
                    context_name=name,
                    status=CoverageExecutionContextStatus.PARTIAL,
                    reason="Wall net-section/opening topology exists but is not fully verified",
                )
                values[name] = topology
            else:
                readiness[name] = CoverageExecutionContextReadiness(context_name=name, status=CoverageExecutionContextStatus.READY)
                values[name] = topology
        else:
            readiness[name] = CoverageExecutionContextReadiness(
                context_name=name,
                status=CoverageExecutionContextStatus.BLOCKED,
                reason="Unknown mandatory wall execution context contract",
            )
    return MappingProxyType(readiness), CheckExecutionContext(values=values, evidence=evidence)


def run_wall_checks(
    contract_bundle: ContractBundle,
    snapshots: Sequence[FeatureSnapshot],
    check_ids: Sequence[str],
    *,
    execution_evidence: WallExecutionEvidence | None = None,
) -> WallCheckRun:
    selected = tuple(str(check_id) for check_id in check_ids)
    unknown = sorted(set(selected) - set(WALL_CHECK_DEFINITIONS))
    if unknown:
        raise ValueError("Unknown wall check ID(s): " + ", ".join(unknown))
    normalized_snapshots = tuple(snapshots)
    component_ids = tuple(snapshot.component_id for snapshot in normalized_snapshots)
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("run_wall_checks requires unique wall component_id values")
    builder = wall_coverage_builder(contract_bundle)
    engine = MinimalCheckEngine(builder.check_catalog)
    run_evidence = execution_evidence or WallExecutionEvidence()
    coverage_rows: list[CoverageRow] = []
    check_inputs: list[GeometryCheckInput] = []
    results: list[CheckResult] = []
    for snapshot in normalized_snapshots:
        if str(snapshot.component_type).casefold() != "wall":
            raise ValueError("run_wall_checks accepts wall FeatureSnapshot objects only")
        for check_id in selected:
            readiness, frozen_context = _execution_materialization(
                snapshot=snapshot,
                check_id=check_id,
                execution_evidence=run_evidence,
            )
            coverage = builder.build_row(snapshot, check_id, execution_context_readiness=readiness)
            check_input = build_wall_check_input(snapshot, coverage, frozen_context)
            result = engine.run_input(check_input)
            coverage_rows.append(coverage)
            check_inputs.append(check_input)
            results.append(result)
    return WallCheckRun(
        snapshots=normalized_snapshots,
        coverage_rows=tuple(coverage_rows),
        check_inputs=tuple(check_inputs),
        check_results=tuple(results),
        assessment=assess_wall_results(results, check_ids=selected, component_ids=component_ids),
    )


__all__ = [
    "WallCheckRun", "WallExecutionEvidence", "build_wall_check_input",
    "run_wall_checks", "wall_coverage_builder",
]
