"""F0.2 exact-parity migration for the accepted beam minimum-width formal check.

This module owns only typed F0 declaration/wiring and canonical CheckResult
construction.  Engineering math remains in ``tbdy_engine.checks.member_geometry``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.checks.member_geometry import (
    BEAM_MIN_WIDTH,
    MEMBER_GEOMETRY_REGISTRATIONS,
    evaluate_member_rule,
)
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    DependencyKey,
    DependencySourceKind,
    DependencySpec,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    PopulationRequirement,
    RuleId,
    ScopePolicy,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import MaterializedDependency, RuleExecutionEnvelope
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM

RULE_VERSION = "f0.2-parity-v1"
RULE_ID = RuleId(BEAM_MIN_WIDTH)

BEAM_WIDTH_KEY = DependencyKey("beam_width_mm")
STORY_KEY = DependencyKey("story")
SECTION_KEY = DependencyKey("section")
EVIDENCE_TRACE_KEY = DependencyKey("check_evidence_trace")


@dataclass(frozen=True, slots=True)
class BeamMinWidthApplicabilityInput:
    """Compile-time applicability truth for the single F0.2 pilot check."""

    component_type: str
    tbdy_7411_applies: bool | None

    def __post_init__(self) -> None:
        if not isinstance(self.component_type, str) or not self.component_type.strip():
            raise ValueError("component_type must be a nonblank string")
        if self.tbdy_7411_applies is not None and not isinstance(self.tbdy_7411_applies, bool):
            raise TypeError("tbdy_7411_applies must be bool or None")


def beam_min_width_applicability(value: BeamMinWidthApplicabilityInput) -> ApplicabilityState:
    if value.component_type.strip().casefold() != "beam":
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.tbdy_7411_applies is None:
        return ApplicabilityState.UNRESOLVED
    return (
        ApplicabilityState.APPLIES
        if value.tbdy_7411_applies
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


@dataclass(frozen=True, slots=True)
class BeamMinWidthExecutionInput:
    """Narrow typed runtime view; no generic dependency lookup escapes this boundary."""

    envelope: RuleExecutionEnvelope
    component_id: str
    beam_width_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "BeamMinWidthExecutionInput":
        deps = tuple(dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("beam minimum-width execution requires MaterializedDependency inputs")
        by_key = {item.key: item for item in deps}
        expected = {BEAM_WIDTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY}
        if len(by_key) != len(deps) or set(by_key) != expected:
            raise ValueError("beam minimum-width execution received unexpected dependency keys")

        width = by_key[BEAM_WIDTH_KEY].value
        if isinstance(width, bool) or not isinstance(width, (int, float)):
            raise TypeError("beam_width_mm must be a numeric scalar")

        story = by_key[STORY_KEY].value
        section = by_key[SECTION_KEY].value
        if not isinstance(story, str) or not story.strip():
            raise TypeError("story must be a resolved nonblank string")
        if not isinstance(section, str) or not section.strip():
            raise TypeError("section must be a resolved nonblank string")

        evidence = by_key[EVIDENCE_TRACE_KEY].value
        if not isinstance(evidence, tuple):
            raise TypeError("check_evidence_trace must materialize as an immutable tuple")

        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            beam_width_mm=float(width),
            story=story,
            section=section,
            evidence=tuple(evidence),
        )


def evaluate_beam_min_width(inp: BeamMinWidthExecutionInput) -> CheckResult:
    """Construct the canonical parity result using the accepted numeric authority."""

    registration = MEMBER_GEOMETRY_REGISTRATIONS[BEAM_MIN_WIDTH]
    rule = evaluate_member_rule(
        registration,
        {"beam_width_mm": inp.beam_width_mm},
    )
    return CheckResult(
        check_id=registration.check_id,
        component=inp.component_id,
        component_type=registration.component_type,
        story=inp.story,
        section=inp.section,
        status=CheckStatus.OK if rule.is_satisfied else CheckStatus.FAIL,
        value=rule.value,
        limit=rule.limit,
        demand=None,
        capacity=None,
        ratio=rule.ratio,
        ratio_type=rule.ratio_type,
        pass_rule=rule.ratio_type,
        unit=rule.unit,
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=("Formal canonical beam/column geometry CheckResult",),
        code_ref=registration.code_ref,
        diagnostics=(),
    )


BEAM_MIN_WIDTH_DEPENDENCIES = (
    DependencySpec(
        key=BEAM_WIDTH_KEY,
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.BEAM_WIDTH,
        physical_dimension=PhysicalDimension.LENGTH,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_MM,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    ),
    DependencySpec(
        key=STORY_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.COMPONENT_STORY,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_ENUM_STATE,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    ),
    DependencySpec(
        key=SECTION_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.COMPONENT_SECTION,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_ENUM_STATE,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    ),
    DependencySpec(
        key=EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
)

BEAM_MIN_WIDTH_CHECK_SPEC = CheckSpec(
    rule_id=RULE_ID,
    code_refs=(MEMBER_GEOMETRY_REGISTRATIONS[BEAM_MIN_WIDTH].code_ref,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=BEAM_MIN_WIDTH_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.2:beam_min_width:applicability",
        BeamMinWidthApplicabilityInput,
        beam_min_width_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.2:beam_min_width:evaluator",
        BeamMinWidthExecutionInput,
        evaluate_beam_min_width,
    ),
)

F0_2_BEAM_MIN_WIDTH_REGISTRY = RegulatoryRegistry(checks=(BEAM_MIN_WIDTH_CHECK_SPEC,))


__all__ = [
    "RULE_VERSION",
    "RULE_ID",
    "BEAM_WIDTH_KEY",
    "STORY_KEY",
    "SECTION_KEY",
    "EVIDENCE_TRACE_KEY",
    "BeamMinWidthApplicabilityInput",
    "BeamMinWidthExecutionInput",
    "beam_min_width_applicability",
    "evaluate_beam_min_width",
    "BEAM_MIN_WIDTH_DEPENDENCIES",
    "BEAM_MIN_WIDTH_CHECK_SPEC",
    "F0_2_BEAM_MIN_WIDTH_REGISTRY",
]
