"""F0.8 explicit parity migration for three READY Wall Pack A geometry checks.

The exact frozen formulas are intentionally local to this F0 regulatory module.
Production remains independent from the legacy wall runtime authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

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

RULE_VERSION = "f0.8-parity-v1"

WALL_GEOM_DEFINITION_LW_BW_GE6 = "WALL_GEOM_DEFINITION_LW_BW_GE6"
WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30 = "WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30"
WALL_GEOM_RESTRAINED_LEG_THICKNESS = "WALL_GEOM_RESTRAINED_LEG_THICKNESS"

WALL_DEFINITION_RULE_ID = RuleId(WALL_GEOM_DEFINITION_LW_BW_GE6)
WALL_UNRESTRAINED_RULE_ID = RuleId(WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30)
WALL_RESTRAINED_LEG_RULE_ID = RuleId(WALL_GEOM_RESTRAINED_LEG_THICKNESS)

WALL_DEFINITION_CODE_REF = "TBDY 2018 §7.6.1.2 first sentence"
WALL_UNRESTRAINED_CODE_REF = "TBDY 2018 §7.6.1.2(b)"
WALL_RESTRAINED_LEG_CODE_REF = "TBDY 2018 §7.6.1.2(c)"

WALL_LENGTH_KEY = DependencyKey("wall_length_mm")
WALL_THICKNESS_KEY = DependencyKey("wall_thickness_mm")
WALL_STORY_HEIGHT_KEY = DependencyKey("story_height_mm")
WALL_UNRESTRAINED_LENGTH_KEY = DependencyKey("unrestrained_plan_length_mm")
STORY_KEY = DependencyKey("story")
SECTION_KEY = DependencyKey("section")
EVIDENCE_TRACE_KEY = DependencyKey("check_evidence_trace")


def _optional_bool(value: bool | None, label: str) -> None:
    if value is not None and type(value) is not bool:
        raise TypeError(f"{label} must be bool or None")


def _component_envelope(envelope: RuleExecutionEnvelope) -> None:
    if not isinstance(envelope, RuleExecutionEnvelope):
        raise TypeError("envelope must be RuleExecutionEnvelope")
    if envelope.instance_id.grain is not Grain.COMPONENT:
        raise ValueError("F0.8 wall geometry execution requires Grain.COMPONENT")
    if envelope.instance_id.direction is not None:
        raise ValueError("Grain.COMPONENT F0.8 wall geometry execution requires direction=None")


def _dependency_map(
    dependencies: Sequence[MaterializedDependency],
    expected: set[DependencyKey],
) -> dict[DependencyKey, MaterializedDependency]:
    deps = tuple(dependencies)
    if any(not isinstance(item, MaterializedDependency) for item in deps):
        raise TypeError("F0.8 wall execution requires MaterializedDependency inputs")
    by_key = {item.key: item for item in deps}
    if len(by_key) != len(deps) or set(by_key) != expected:
        raise ValueError("F0.8 wall execution received unexpected dependency keys")
    return by_key


def _positive_geometry(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a numeric scalar")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if number <= 0.0:
        raise ValueError(f"{label} must be strictly positive")
    return number


def _context_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{label} must be a resolved nonblank string")
    return value


def _evidence(value: object) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise TypeError("check_evidence_trace must materialize as an immutable tuple")
    return value


@dataclass(frozen=True, slots=True)
class WallDefinitionGE6ApplicabilityInput:
    is_wall: bool | None
    is_basement: bool | None

    def __post_init__(self) -> None:
        _optional_bool(self.is_wall, "is_wall")
        _optional_bool(self.is_basement, "is_basement")


def wall_definition_ge6_applicability(
    value: WallDefinitionGE6ApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, WallDefinitionGE6ApplicabilityInput):
        raise TypeError("applicability requires WallDefinitionGE6ApplicabilityInput")
    if value.is_wall is False or value.is_basement is True:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.is_wall is True and value.is_basement is False:
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class WallUnrestrainedThicknessApplicabilityInput:
    is_wall: bool | None
    is_basement: bool | None
    geometry_classification_in_scope: bool | None

    def __post_init__(self) -> None:
        _optional_bool(self.is_wall, "is_wall")
        _optional_bool(self.is_basement, "is_basement")
        _optional_bool(self.geometry_classification_in_scope, "geometry_classification_in_scope")


def wall_unrestrained_thickness_applicability(
    value: WallUnrestrainedThicknessApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, WallUnrestrainedThicknessApplicabilityInput):
        raise TypeError("applicability requires WallUnrestrainedThicknessApplicabilityInput")
    if (
        value.is_wall is False
        or value.is_basement is True
        or value.geometry_classification_in_scope is False
    ):
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if (
        value.is_wall is True
        and value.is_basement is False
        and value.geometry_classification_in_scope is True
    ):
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class WallRestrainedLegApplicabilityInput:
    is_wall: bool | None
    is_basement: bool | None
    both_ends_laterally_restrained: bool | None

    def __post_init__(self) -> None:
        _optional_bool(self.is_wall, "is_wall")
        _optional_bool(self.is_basement, "is_basement")
        _optional_bool(self.both_ends_laterally_restrained, "both_ends_laterally_restrained")


def wall_restrained_leg_applicability(
    value: WallRestrainedLegApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, WallRestrainedLegApplicabilityInput):
        raise TypeError("applicability requires WallRestrainedLegApplicabilityInput")
    if (
        value.is_wall is False
        or value.is_basement is True
        or value.both_ends_laterally_restrained is False
    ):
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if (
        value.is_wall is True
        and value.is_basement is False
        and value.both_ends_laterally_restrained is True
    ):
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class WallDefinitionGE6ExecutionInput:
    envelope: RuleExecutionEnvelope
    component_id: str
    wall_length_mm: float
    wall_thickness_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _component_envelope(self.envelope)
        if self.component_id != self.envelope.instance_id.scope_ref:
            raise ValueError("component_id must match envelope instance scope_ref")
        object.__setattr__(self, "wall_length_mm", _positive_geometry(self.wall_length_mm, "wall_length_mm"))
        object.__setattr__(self, "wall_thickness_mm", _positive_geometry(self.wall_thickness_mm, "wall_thickness_mm"))
        object.__setattr__(self, "story", _context_string(self.story, "story"))
        object.__setattr__(self, "section", _context_string(self.section, "section"))
        object.__setattr__(self, "evidence", _evidence(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "WallDefinitionGE6ExecutionInput":
        by_key = _dependency_map(
            dependencies,
            {WALL_LENGTH_KEY, WALL_THICKNESS_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY},
        )
        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            wall_length_mm=_positive_geometry(by_key[WALL_LENGTH_KEY].value, "wall_length_mm"),
            wall_thickness_mm=_positive_geometry(by_key[WALL_THICKNESS_KEY].value, "wall_thickness_mm"),
            story=_context_string(by_key[STORY_KEY].value, "story"),
            section=_context_string(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


@dataclass(frozen=True, slots=True)
class WallUnrestrainedThicknessExecutionInput:
    envelope: RuleExecutionEnvelope
    component_id: str
    wall_thickness_mm: float
    unrestrained_plan_length_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _component_envelope(self.envelope)
        if self.component_id != self.envelope.instance_id.scope_ref:
            raise ValueError("component_id must match envelope instance scope_ref")
        object.__setattr__(self, "wall_thickness_mm", _positive_geometry(self.wall_thickness_mm, "wall_thickness_mm"))
        object.__setattr__(
            self,
            "unrestrained_plan_length_mm",
            _positive_geometry(self.unrestrained_plan_length_mm, "unrestrained_plan_length_mm"),
        )
        object.__setattr__(self, "story", _context_string(self.story, "story"))
        object.__setattr__(self, "section", _context_string(self.section, "section"))
        object.__setattr__(self, "evidence", _evidence(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "WallUnrestrainedThicknessExecutionInput":
        by_key = _dependency_map(
            dependencies,
            {WALL_THICKNESS_KEY, WALL_UNRESTRAINED_LENGTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY},
        )
        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            wall_thickness_mm=_positive_geometry(by_key[WALL_THICKNESS_KEY].value, "wall_thickness_mm"),
            unrestrained_plan_length_mm=_positive_geometry(
                by_key[WALL_UNRESTRAINED_LENGTH_KEY].value,
                "unrestrained_plan_length_mm",
            ),
            story=_context_string(by_key[STORY_KEY].value, "story"),
            section=_context_string(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


@dataclass(frozen=True, slots=True)
class WallRestrainedLegThicknessExecutionInput:
    envelope: RuleExecutionEnvelope
    component_id: str
    wall_thickness_mm: float
    story_height_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _component_envelope(self.envelope)
        if self.component_id != self.envelope.instance_id.scope_ref:
            raise ValueError("component_id must match envelope instance scope_ref")
        object.__setattr__(self, "wall_thickness_mm", _positive_geometry(self.wall_thickness_mm, "wall_thickness_mm"))
        object.__setattr__(self, "story_height_mm", _positive_geometry(self.story_height_mm, "story_height_mm"))
        object.__setattr__(self, "story", _context_string(self.story, "story"))
        object.__setattr__(self, "section", _context_string(self.section, "section"))
        object.__setattr__(self, "evidence", _evidence(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "WallRestrainedLegThicknessExecutionInput":
        by_key = _dependency_map(
            dependencies,
            {WALL_THICKNESS_KEY, WALL_STORY_HEIGHT_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY},
        )
        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            wall_thickness_mm=_positive_geometry(by_key[WALL_THICKNESS_KEY].value, "wall_thickness_mm"),
            story_height_mm=_positive_geometry(by_key[WALL_STORY_HEIGHT_KEY].value, "story_height_mm"),
            story=_context_string(by_key[STORY_KEY].value, "story"),
            section=_context_string(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


def _wall_result(
    *,
    rule_id: RuleId,
    code_ref: str,
    component_id: str,
    story: str,
    section: str,
    evidence: tuple[object, ...],
    value: float,
    limit: float,
    unit: str,
) -> CheckResult:
    ratio = value / limit
    return CheckResult(
        check_id=rule_id.value,
        component=component_id,
        component_type="wall",
        story=story,
        section=section,
        status=CheckStatus.OK if value >= limit else CheckStatus.FAIL,
        value=value,
        limit=limit,
        demand=None,
        capacity=None,
        ratio=ratio,
        ratio_type="actual_over_minimum",
        pass_rule="actual_over_minimum",
        unit=unit,
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=evidence,
        messages=("Formal canonical wall CheckResult",),
        code_ref=code_ref,
        diagnostics=(),
    )


def evaluate_wall_definition_ge6(inp: WallDefinitionGE6ExecutionInput) -> CheckResult:
    if not isinstance(inp, WallDefinitionGE6ExecutionInput):
        raise TypeError("evaluator requires WallDefinitionGE6ExecutionInput")
    value = inp.wall_length_mm / inp.wall_thickness_mm
    return _wall_result(
        rule_id=WALL_DEFINITION_RULE_ID,
        code_ref=WALL_DEFINITION_CODE_REF,
        component_id=inp.component_id,
        story=inp.story,
        section=inp.section,
        evidence=inp.evidence,
        value=value,
        limit=6.0,
        unit="",
    )


def evaluate_wall_unrestrained_thickness(
    inp: WallUnrestrainedThicknessExecutionInput,
) -> CheckResult:
    if not isinstance(inp, WallUnrestrainedThicknessExecutionInput):
        raise TypeError("evaluator requires WallUnrestrainedThicknessExecutionInput")
    minimum = inp.unrestrained_plan_length_mm / 30.0
    return _wall_result(
        rule_id=WALL_UNRESTRAINED_RULE_ID,
        code_ref=WALL_UNRESTRAINED_CODE_REF,
        component_id=inp.component_id,
        story=inp.story,
        section=inp.section,
        evidence=inp.evidence,
        value=inp.wall_thickness_mm,
        limit=minimum,
        unit="mm",
    )


def evaluate_wall_restrained_leg_thickness(
    inp: WallRestrainedLegThicknessExecutionInput,
) -> CheckResult:
    if not isinstance(inp, WallRestrainedLegThicknessExecutionInput):
        raise TypeError("evaluator requires WallRestrainedLegThicknessExecutionInput")
    minimum = max(inp.story_height_mm / 20.0, 250.0)
    return _wall_result(
        rule_id=WALL_RESTRAINED_LEG_RULE_ID,
        code_ref=WALL_RESTRAINED_LEG_CODE_REF,
        component_id=inp.component_id,
        story=inp.story,
        section=inp.section,
        evidence=inp.evidence,
        value=inp.wall_thickness_mm,
        limit=minimum,
        unit="mm",
    )


def _fact(key: DependencyKey, semantic: SemanticType) -> DependencySpec:
    return DependencySpec(
        key=key,
        source_kind=DependencySourceKind.FACT,
        semantic_type=semantic,
        physical_dimension=PhysicalDimension.LENGTH,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_MM,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    )


def _story_dependency() -> DependencySpec:
    return DependencySpec(
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
    )


def _section_dependency() -> DependencySpec:
    return DependencySpec(
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
    )


def _evidence_dependency() -> DependencySpec:
    return DependencySpec(
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
    )


WALL_DEFINITION_GE6_DEPENDENCIES = (
    _fact(WALL_LENGTH_KEY, SemanticType.WALL_LENGTH),
    _fact(WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS),
    _story_dependency(),
    _section_dependency(),
    _evidence_dependency(),
)

WALL_UNRESTRAINED_THICKNESS_DEPENDENCIES = (
    _fact(WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS),
    _fact(WALL_UNRESTRAINED_LENGTH_KEY, SemanticType.WALL_UNRESTRAINED_PLAN_LENGTH),
    _story_dependency(),
    _section_dependency(),
    _evidence_dependency(),
)

WALL_RESTRAINED_LEG_THICKNESS_DEPENDENCIES = (
    _fact(WALL_THICKNESS_KEY, SemanticType.WALL_THICKNESS),
    _fact(WALL_STORY_HEIGHT_KEY, SemanticType.WALL_STORY_HEIGHT),
    _story_dependency(),
    _section_dependency(),
    _evidence_dependency(),
)

WALL_DEFINITION_GE6_CHECK_SPEC = CheckSpec(
    rule_id=WALL_DEFINITION_RULE_ID,
    code_refs=(WALL_DEFINITION_CODE_REF,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=WALL_DEFINITION_GE6_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.8:wall_definition_ge6:applicability",
        WallDefinitionGE6ApplicabilityInput,
        wall_definition_ge6_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.8:wall_definition_ge6:evaluator",
        WallDefinitionGE6ExecutionInput,
        evaluate_wall_definition_ge6,
    ),
)

WALL_UNRESTRAINED_THICKNESS_CHECK_SPEC = CheckSpec(
    rule_id=WALL_UNRESTRAINED_RULE_ID,
    code_refs=(WALL_UNRESTRAINED_CODE_REF,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=WALL_UNRESTRAINED_THICKNESS_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.8:wall_unrestrained_thickness:applicability",
        WallUnrestrainedThicknessApplicabilityInput,
        wall_unrestrained_thickness_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.8:wall_unrestrained_thickness:evaluator",
        WallUnrestrainedThicknessExecutionInput,
        evaluate_wall_unrestrained_thickness,
    ),
)

WALL_RESTRAINED_LEG_THICKNESS_CHECK_SPEC = CheckSpec(
    rule_id=WALL_RESTRAINED_LEG_RULE_ID,
    code_refs=(WALL_RESTRAINED_LEG_CODE_REF,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=WALL_RESTRAINED_LEG_THICKNESS_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.8:wall_restrained_leg:applicability",
        WallRestrainedLegApplicabilityInput,
        wall_restrained_leg_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.8:wall_restrained_leg:evaluator",
        WallRestrainedLegThicknessExecutionInput,
        evaluate_wall_restrained_leg_thickness,
    ),
)

WALL_PACK_A_GEOMETRY_PARITY_CHECK_SPECS = (
    WALL_DEFINITION_GE6_CHECK_SPEC,
    WALL_UNRESTRAINED_THICKNESS_CHECK_SPEC,
    WALL_RESTRAINED_LEG_THICKNESS_CHECK_SPEC,
)

F0_8_WALL_PACK_A_GEOMETRY_REGISTRY = RegulatoryRegistry(
    checks=WALL_PACK_A_GEOMETRY_PARITY_CHECK_SPECS
)


__all__ = [
    "RULE_VERSION",
    "WALL_GEOM_DEFINITION_LW_BW_GE6",
    "WALL_GEOM_UNRESTRAINED_THICKNESS_GE_L30",
    "WALL_GEOM_RESTRAINED_LEG_THICKNESS",
    "WALL_DEFINITION_RULE_ID",
    "WALL_UNRESTRAINED_RULE_ID",
    "WALL_RESTRAINED_LEG_RULE_ID",
    "WALL_DEFINITION_CODE_REF",
    "WALL_UNRESTRAINED_CODE_REF",
    "WALL_RESTRAINED_LEG_CODE_REF",
    "WALL_LENGTH_KEY",
    "WALL_THICKNESS_KEY",
    "WALL_STORY_HEIGHT_KEY",
    "WALL_UNRESTRAINED_LENGTH_KEY",
    "STORY_KEY",
    "SECTION_KEY",
    "EVIDENCE_TRACE_KEY",
    "WallDefinitionGE6ApplicabilityInput",
    "WallUnrestrainedThicknessApplicabilityInput",
    "WallRestrainedLegApplicabilityInput",
    "WallDefinitionGE6ExecutionInput",
    "WallUnrestrainedThicknessExecutionInput",
    "WallRestrainedLegThicknessExecutionInput",
    "wall_definition_ge6_applicability",
    "wall_unrestrained_thickness_applicability",
    "wall_restrained_leg_applicability",
    "evaluate_wall_definition_ge6",
    "evaluate_wall_unrestrained_thickness",
    "evaluate_wall_restrained_leg_thickness",
    "WALL_DEFINITION_GE6_DEPENDENCIES",
    "WALL_UNRESTRAINED_THICKNESS_DEPENDENCIES",
    "WALL_RESTRAINED_LEG_THICKNESS_DEPENDENCIES",
    "WALL_DEFINITION_GE6_CHECK_SPEC",
    "WALL_UNRESTRAINED_THICKNESS_CHECK_SPEC",
    "WALL_RESTRAINED_LEG_THICKNESS_CHECK_SPEC",
    "WALL_PACK_A_GEOMETRY_PARITY_CHECK_SPECS",
    "F0_8_WALL_PACK_A_GEOMETRY_REGISTRY",
]
