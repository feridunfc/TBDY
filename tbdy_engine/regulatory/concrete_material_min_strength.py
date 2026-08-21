"""F0.7 formal TBDY concrete material minimum-strength check."""
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
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_MPA

RULE_ID = RuleId("CONCRETE_MATERIAL_MIN_STRENGTH")
RULE_VERSION = "f0.7-v1"
CODE_REF = "TBDY-2018-7.2.5.1"
MIN_FCK_MPA = 25.0

FCK_KEY = DependencyKey("concrete_fck_mpa")
EVIDENCE_TRACE_KEY = DependencyKey("check_evidence_trace")


@dataclass(frozen=True, slots=True)
class ConcreteMaterialMinStrengthApplicabilityInput:
    """Reviewed compile-time applicability truth; no runtime discovery."""

    is_concrete_material: bool | None
    used_in_scope_rc_building: bool | None

    def __post_init__(self) -> None:
        for label, value in (
            ("is_concrete_material", self.is_concrete_material),
            ("used_in_scope_rc_building", self.used_in_scope_rc_building),
        ):
            if value is not None and type(value) is not bool:
                raise TypeError(f"{label} must be bool or None")


def concrete_material_min_strength_applicability(
    value: ConcreteMaterialMinStrengthApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, ConcreteMaterialMinStrengthApplicabilityInput):
        raise TypeError("applicability requires ConcreteMaterialMinStrengthApplicabilityInput")
    if value.is_concrete_material is False or value.used_in_scope_rc_building is False:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.is_concrete_material is True and value.used_in_scope_rc_building is True:
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class ConcreteMaterialMinStrengthExecutionInput:
    """Narrow typed runtime view for the single F0.7 formal check."""

    envelope: RuleExecutionEnvelope
    material_ref: str
    fck_mpa: float
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, RuleExecutionEnvelope):
            raise TypeError("envelope must be RuleExecutionEnvelope")
        if self.envelope.instance_id.grain is not Grain.MATERIAL_DEFINITION:
            raise ValueError("concrete material minimum-strength execution requires Grain.MATERIAL_DEFINITION")
        if self.envelope.instance_id.direction is not None:
            raise ValueError("Grain.MATERIAL_DEFINITION concrete material minimum-strength execution requires direction=None")
        if not isinstance(self.material_ref, str) or not self.material_ref.strip():
            raise ValueError("material_ref must be a nonblank string")
        if self.material_ref != self.envelope.instance_id.scope_ref:
            raise ValueError("material_ref must match envelope instance scope_ref")
        if isinstance(self.fck_mpa, bool) or not isinstance(self.fck_mpa, (int, float)):
            raise TypeError("fck_mpa must be a numeric scalar")
        fck = float(self.fck_mpa)
        if not math.isfinite(fck):
            raise ValueError("fck_mpa must be finite")
        if type(self.evidence) is not tuple:
            raise TypeError("check_evidence_trace must materialize as an immutable tuple")
        object.__setattr__(self, "fck_mpa", fck)
        object.__setattr__(self, "evidence", tuple(self.evidence))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ConcreteMaterialMinStrengthExecutionInput":
        deps = tuple(dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("concrete material minimum-strength execution requires MaterializedDependency inputs")
        by_key = {item.key: item for item in deps}
        expected = {FCK_KEY, EVIDENCE_TRACE_KEY}
        if len(by_key) != len(deps) or set(by_key) != expected:
            raise ValueError("concrete material minimum-strength execution received unexpected dependency keys")

        fck = by_key[FCK_KEY].value
        if isinstance(fck, bool) or not isinstance(fck, (int, float)):
            raise TypeError("fck_mpa must be a numeric scalar")
        fck_value = float(fck)
        if not math.isfinite(fck_value):
            raise ValueError("fck_mpa must be finite")

        evidence = by_key[EVIDENCE_TRACE_KEY].value
        if type(evidence) is not tuple:
            raise TypeError("check_evidence_trace must materialize as an immutable tuple")

        return cls(
            envelope=envelope,
            material_ref=envelope.instance_id.scope_ref,
            fck_mpa=fck_value,
            evidence=evidence,
        )


def evaluate_concrete_material_min_strength(
    inp: ConcreteMaterialMinStrengthExecutionInput,
) -> CheckResult:
    if not isinstance(inp, ConcreteMaterialMinStrengthExecutionInput):
        raise TypeError("evaluator requires ConcreteMaterialMinStrengthExecutionInput")
    is_satisfied = inp.fck_mpa >= MIN_FCK_MPA
    return CheckResult(
        check_id=RULE_ID.value,
        component=inp.material_ref,
        component_type="concrete_material",
        story=None,
        section=None,
        status=CheckStatus.OK if is_satisfied else CheckStatus.FAIL,
        value=inp.fck_mpa,
        limit=MIN_FCK_MPA,
        demand=None,
        capacity=None,
        ratio=inp.fck_mpa / MIN_FCK_MPA,
        ratio_type="actual_over_minimum",
        pass_rule="fck_mpa >= 25.0",
        unit="MPa",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=("Formal TBDY concrete material minimum-strength CheckResult",),
        code_ref=CODE_REF,
        diagnostics=(),
    )


CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES = (
    DependencySpec(
        key=FCK_KEY,
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.CONCRETE_FCK,
        physical_dimension=PhysicalDimension.STRESS,
        grain=Grain.MATERIAL_DEFINITION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_MPA,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
    DependencySpec(
        key=EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.MATERIAL_DEFINITION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
)

CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC = CheckSpec(
    rule_id=RULE_ID,
    code_refs=(CODE_REF,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.7:concrete_material_min_strength:applicability",
        ConcreteMaterialMinStrengthApplicabilityInput,
        concrete_material_min_strength_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.7:concrete_material_min_strength:evaluator",
        ConcreteMaterialMinStrengthExecutionInput,
        evaluate_concrete_material_min_strength,
    ),
)

F0_7_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY = RegulatoryRegistry(
    checks=(CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,)
)


__all__ = [
    "RULE_ID",
    "RULE_VERSION",
    "CODE_REF",
    "MIN_FCK_MPA",
    "FCK_KEY",
    "EVIDENCE_TRACE_KEY",
    "ConcreteMaterialMinStrengthApplicabilityInput",
    "ConcreteMaterialMinStrengthExecutionInput",
    "concrete_material_min_strength_applicability",
    "evaluate_concrete_material_min_strength",
    "CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES",
    "CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC",
    "F0_7_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY",
]
