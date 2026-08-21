"""F0.8 exact-parity migration for accepted B1 beam/column geometry checks.

Engineering math remains in ``tbdy_engine.checks.member_geometry``.  This
module owns only typed F0 dependencies/applicability, narrow execution inputs,
and canonical CheckResult construction.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.checks.member_geometry import (
    BEAM_DEPTH_WIDTH_RATIO,
    BEAM_MIN_DEPTH_300,
    COLUMN_MIN_DIMENSION,
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

RULE_VERSION = "f0.8-parity-v1"

COLUMN_MIN_DIMENSION_RULE_ID = RuleId(COLUMN_MIN_DIMENSION)
BEAM_MIN_DEPTH_RULE_ID = RuleId(BEAM_MIN_DEPTH_300)
BEAM_DEPTH_WIDTH_RATIO_RULE_ID = RuleId(BEAM_DEPTH_WIDTH_RATIO)

COLUMN_WIDTH_KEY = DependencyKey("column_width_mm")
COLUMN_DEPTH_KEY = DependencyKey("column_depth_mm")
BEAM_DEPTH_KEY = DependencyKey("beam_depth_mm")
BEAM_WIDTH_KEY = DependencyKey("beam_width_mm")
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
        raise ValueError("F0.8 B1 geometry execution requires Grain.COMPONENT")
    if envelope.instance_id.direction is not None:
        raise ValueError("Grain.COMPONENT F0.8 B1 geometry execution requires direction=None")


def _dependency_map(
    dependencies: Sequence[MaterializedDependency],
    expected: set[DependencyKey],
) -> dict[DependencyKey, MaterializedDependency]:
    deps = tuple(dependencies)
    if any(not isinstance(item, MaterializedDependency) for item in deps):
        raise TypeError("F0.8 B1 execution requires MaterializedDependency inputs")
    by_key = {item.key: item for item in deps}
    if len(by_key) != len(deps) or set(by_key) != expected:
        raise ValueError("F0.8 B1 execution received unexpected dependency keys")
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
class Beam7411ApplicabilityInput:
    is_beam: bool | None
    tbdy_7411_applies: bool | None

    def __post_init__(self) -> None:
        _optional_bool(self.is_beam, "is_beam")
        _optional_bool(self.tbdy_7411_applies, "tbdy_7411_applies")


def beam_7411_applicability(value: Beam7411ApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, Beam7411ApplicabilityInput):
        raise TypeError("applicability requires Beam7411ApplicabilityInput")
    if value.is_beam is False or value.tbdy_7411_applies is False:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.is_beam is True and value.tbdy_7411_applies is True:
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class ColumnMinDimensionApplicabilityInput:
    is_column: bool | None
    is_rectangular_section: bool | None

    def __post_init__(self) -> None:
        _optional_bool(self.is_column, "is_column")
        _optional_bool(self.is_rectangular_section, "is_rectangular_section")


def column_min_dimension_applicability(
    value: ColumnMinDimensionApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, ColumnMinDimensionApplicabilityInput):
        raise TypeError("applicability requires ColumnMinDimensionApplicabilityInput")
    if value.is_column is False or value.is_rectangular_section is False:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.is_column is True and value.is_rectangular_section is True:
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class ColumnMinDimensionExecutionInput:
    envelope: RuleExecutionEnvelope
    component_id: str
    column_width_mm: float
    column_depth_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _component_envelope(self.envelope)
        if self.component_id != self.envelope.instance_id.scope_ref:
            raise ValueError("component_id must match envelope instance scope_ref")
        object.__setattr__(self, "column_width_mm", _positive_geometry(self.column_width_mm, "column_width_mm"))
        object.__setattr__(self, "column_depth_mm", _positive_geometry(self.column_depth_mm, "column_depth_mm"))
        object.__setattr__(self, "story", _context_string(self.story, "story"))
        object.__setattr__(self, "section", _context_string(self.section, "section"))
        object.__setattr__(self, "evidence", _evidence(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ColumnMinDimensionExecutionInput":
        by_key = _dependency_map(
            dependencies,
            {COLUMN_WIDTH_KEY, COLUMN_DEPTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY},
        )
        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            column_width_mm=_positive_geometry(by_key[COLUMN_WIDTH_KEY].value, "column_width_mm"),
            column_depth_mm=_positive_geometry(by_key[COLUMN_DEPTH_KEY].value, "column_depth_mm"),
            story=_context_string(by_key[STORY_KEY].value, "story"),
            section=_context_string(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


@dataclass(frozen=True, slots=True)
class BeamMinDepthExecutionInput:
    envelope: RuleExecutionEnvelope
    component_id: str
    beam_depth_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _component_envelope(self.envelope)
        if self.component_id != self.envelope.instance_id.scope_ref:
            raise ValueError("component_id must match envelope instance scope_ref")
        object.__setattr__(self, "beam_depth_mm", _positive_geometry(self.beam_depth_mm, "beam_depth_mm"))
        object.__setattr__(self, "story", _context_string(self.story, "story"))
        object.__setattr__(self, "section", _context_string(self.section, "section"))
        object.__setattr__(self, "evidence", _evidence(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "BeamMinDepthExecutionInput":
        by_key = _dependency_map(
            dependencies,
            {BEAM_DEPTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY},
        )
        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            beam_depth_mm=_positive_geometry(by_key[BEAM_DEPTH_KEY].value, "beam_depth_mm"),
            story=_context_string(by_key[STORY_KEY].value, "story"),
            section=_context_string(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


@dataclass(frozen=True, slots=True)
class BeamDepthWidthRatioExecutionInput:
    envelope: RuleExecutionEnvelope
    component_id: str
    beam_depth_mm: float
    beam_width_mm: float
    story: str
    section: str
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        _component_envelope(self.envelope)
        if self.component_id != self.envelope.instance_id.scope_ref:
            raise ValueError("component_id must match envelope instance scope_ref")
        object.__setattr__(self, "beam_depth_mm", _positive_geometry(self.beam_depth_mm, "beam_depth_mm"))
        object.__setattr__(self, "beam_width_mm", _positive_geometry(self.beam_width_mm, "beam_width_mm"))
        object.__setattr__(self, "story", _context_string(self.story, "story"))
        object.__setattr__(self, "section", _context_string(self.section, "section"))
        object.__setattr__(self, "evidence", _evidence(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "BeamDepthWidthRatioExecutionInput":
        by_key = _dependency_map(
            dependencies,
            {BEAM_DEPTH_KEY, BEAM_WIDTH_KEY, STORY_KEY, SECTION_KEY, EVIDENCE_TRACE_KEY},
        )
        return cls(
            envelope=envelope,
            component_id=envelope.instance_id.scope_ref,
            beam_depth_mm=_positive_geometry(by_key[BEAM_DEPTH_KEY].value, "beam_depth_mm"),
            beam_width_mm=_positive_geometry(by_key[BEAM_WIDTH_KEY].value, "beam_width_mm"),
            story=_context_string(by_key[STORY_KEY].value, "story"),
            section=_context_string(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


def _b1_result(
    *,
    registration_id: str,
    component_id: str,
    story: str,
    section: str,
    evidence: tuple[object, ...],
    variables: dict[str, float],
) -> CheckResult:
    registration = MEMBER_GEOMETRY_REGISTRATIONS[registration_id]
    rule = evaluate_member_rule(registration, variables)
    return CheckResult(
        check_id=registration.check_id,
        component=component_id,
        component_type=registration.component_type,
        story=story,
        section=section,
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
        evidence=evidence,
        messages=("Formal canonical beam/column geometry CheckResult",),
        code_ref=registration.code_ref,
        diagnostics=(),
    )


def evaluate_column_min_dimension(inp: ColumnMinDimensionExecutionInput) -> CheckResult:
    if not isinstance(inp, ColumnMinDimensionExecutionInput):
        raise TypeError("evaluator requires ColumnMinDimensionExecutionInput")
    return _b1_result(
        registration_id=COLUMN_MIN_DIMENSION,
        component_id=inp.component_id,
        story=inp.story,
        section=inp.section,
        evidence=inp.evidence,
        variables={
            "column_width_mm": inp.column_width_mm,
            "column_depth_mm": inp.column_depth_mm,
        },
    )


def evaluate_beam_min_depth(inp: BeamMinDepthExecutionInput) -> CheckResult:
    if not isinstance(inp, BeamMinDepthExecutionInput):
        raise TypeError("evaluator requires BeamMinDepthExecutionInput")
    return _b1_result(
        registration_id=BEAM_MIN_DEPTH_300,
        component_id=inp.component_id,
        story=inp.story,
        section=inp.section,
        evidence=inp.evidence,
        variables={"beam_depth_mm": inp.beam_depth_mm},
    )


def evaluate_beam_depth_width_ratio(inp: BeamDepthWidthRatioExecutionInput) -> CheckResult:
    if not isinstance(inp, BeamDepthWidthRatioExecutionInput):
        raise TypeError("evaluator requires BeamDepthWidthRatioExecutionInput")
    return _b1_result(
        registration_id=BEAM_DEPTH_WIDTH_RATIO,
        component_id=inp.component_id,
        story=inp.story,
        section=inp.section,
        evidence=inp.evidence,
        variables={
            "beam_depth_mm": inp.beam_depth_mm,
            "beam_width_mm": inp.beam_width_mm,
        },
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


COLUMN_MIN_DIMENSION_DEPENDENCIES = (
    _fact(COLUMN_WIDTH_KEY, SemanticType.COLUMN_WIDTH),
    _fact(COLUMN_DEPTH_KEY, SemanticType.COLUMN_DEPTH),
    _story_dependency(),
    _section_dependency(),
    _evidence_dependency(),
)

BEAM_MIN_DEPTH_DEPENDENCIES = (
    _fact(BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH),
    _story_dependency(),
    _section_dependency(),
    _evidence_dependency(),
)

BEAM_DEPTH_WIDTH_RATIO_DEPENDENCIES = (
    _fact(BEAM_DEPTH_KEY, SemanticType.BEAM_DEPTH),
    _fact(BEAM_WIDTH_KEY, SemanticType.BEAM_WIDTH),
    _story_dependency(),
    _section_dependency(),
    _evidence_dependency(),
)

COLUMN_MIN_DIMENSION_CHECK_SPEC = CheckSpec(
    rule_id=COLUMN_MIN_DIMENSION_RULE_ID,
    code_refs=(MEMBER_GEOMETRY_REGISTRATIONS[COLUMN_MIN_DIMENSION].code_ref,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=COLUMN_MIN_DIMENSION_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.8:column_min_dimension:applicability",
        ColumnMinDimensionApplicabilityInput,
        column_min_dimension_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.8:column_min_dimension:evaluator",
        ColumnMinDimensionExecutionInput,
        evaluate_column_min_dimension,
    ),
)

BEAM_MIN_DEPTH_CHECK_SPEC = CheckSpec(
    rule_id=BEAM_MIN_DEPTH_RULE_ID,
    code_refs=(MEMBER_GEOMETRY_REGISTRATIONS[BEAM_MIN_DEPTH_300].code_ref,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=BEAM_MIN_DEPTH_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.8:beam_min_depth:applicability",
        Beam7411ApplicabilityInput,
        beam_7411_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.8:beam_min_depth:evaluator",
        BeamMinDepthExecutionInput,
        evaluate_beam_min_depth,
    ),
)

BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC = CheckSpec(
    rule_id=BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    code_refs=(MEMBER_GEOMETRY_REGISTRATIONS[BEAM_DEPTH_WIDTH_RATIO].code_ref,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=BEAM_DEPTH_WIDTH_RATIO_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.8:beam_depth_width_ratio:applicability",
        Beam7411ApplicabilityInput,
        beam_7411_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.8:beam_depth_width_ratio:evaluator",
        BeamDepthWidthRatioExecutionInput,
        evaluate_beam_depth_width_ratio,
    ),
)

B1_GEOMETRY_PARITY_CHECK_SPECS = (
    COLUMN_MIN_DIMENSION_CHECK_SPEC,
    BEAM_MIN_DEPTH_CHECK_SPEC,
    BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
)

F0_8_B1_GEOMETRY_REGISTRY = RegulatoryRegistry(checks=B1_GEOMETRY_PARITY_CHECK_SPECS)


__all__ = [
    "RULE_VERSION",
    "COLUMN_MIN_DIMENSION_RULE_ID",
    "BEAM_MIN_DEPTH_RULE_ID",
    "BEAM_DEPTH_WIDTH_RATIO_RULE_ID",
    "COLUMN_WIDTH_KEY",
    "COLUMN_DEPTH_KEY",
    "BEAM_DEPTH_KEY",
    "BEAM_WIDTH_KEY",
    "STORY_KEY",
    "SECTION_KEY",
    "EVIDENCE_TRACE_KEY",
    "Beam7411ApplicabilityInput",
    "ColumnMinDimensionApplicabilityInput",
    "ColumnMinDimensionExecutionInput",
    "BeamMinDepthExecutionInput",
    "BeamDepthWidthRatioExecutionInput",
    "beam_7411_applicability",
    "column_min_dimension_applicability",
    "evaluate_column_min_dimension",
    "evaluate_beam_min_depth",
    "evaluate_beam_depth_width_ratio",
    "COLUMN_MIN_DIMENSION_DEPENDENCIES",
    "BEAM_MIN_DEPTH_DEPENDENCIES",
    "BEAM_DEPTH_WIDTH_RATIO_DEPENDENCIES",
    "COLUMN_MIN_DIMENSION_CHECK_SPEC",
    "BEAM_MIN_DEPTH_CHECK_SPEC",
    "BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC",
    "B1_GEOMETRY_PARITY_CHECK_SPECS",
    "F0_8_B1_GEOMETRY_REGISTRY",
]
