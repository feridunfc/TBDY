"""VS-3 formal seismic response checks executed only by the regulatory kernel."""
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
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS

MODAL_RULE_ID = RuleId("modal_effective_mass_95_percent")
A1_RULE_ID = RuleId("torsional_irregularity_a1")
MODAL_RULE_VERSION = "vs3-modal-v1"
A1_RULE_VERSION = "vs3-a1-v1"
MODAL_CODE_REF = "TBDY 2018 4.8.1.2(a), Eq. (4.30)"
A1_CODE_REF = "TBDY 2018 Table 3.6 / 3.6.2.1"
MODAL_MIN_RATIO = 0.95
A1_PRESENT_LIMIT = 1.2

MODAL_RATIO_KEY = DependencyKey("modal_cumulative_effective_mass_ratio")
A1_RATIO_KEY = DependencyKey("torsional_irregularity_coefficient")
MODAL_EVIDENCE_TRACE_KEY = DependencyKey("modal_effective_mass_evidence_trace")
A1_EVIDENCE_TRACE_KEY = DependencyKey("torsional_irregularity_a1_evidence_trace")


def _finite_ratio(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _evidence_tuple(value: object, label: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{label} must materialize as an immutable tuple")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class Modal4812ApplicabilityInput:
    modal_4812_applies: bool | None
    modal_case_basis_verified: str

    def __post_init__(self) -> None:
        if self.modal_4812_applies is not None and type(self.modal_4812_applies) is not bool:
            raise TypeError("modal_4812_applies must be bool or None")
        if self.modal_case_basis_verified not in {"verified", "unknown"}:
            raise ValueError("modal_case_basis_verified must be verified or unknown")


def modal_4812_applicability(value: Modal4812ApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, Modal4812ApplicabilityInput):
        raise TypeError("modal applicability requires Modal4812ApplicabilityInput")
    if value.modal_4812_applies is False:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.modal_4812_applies is True and value.modal_case_basis_verified == "verified":
        return ApplicabilityState.APPLIES
    return ApplicabilityState.UNRESOLVED


@dataclass(frozen=True, slots=True)
class A1ApplicabilityInput:
    a1_eccentricity_basis: str

    def __post_init__(self) -> None:
        if self.a1_eccentricity_basis not in {"verified", "unknown"}:
            raise ValueError("a1_eccentricity_basis must be verified or unknown")


def a1_applicability(value: A1ApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, A1ApplicabilityInput):
        raise TypeError("A1 applicability requires A1ApplicabilityInput")
    return (
        ApplicabilityState.APPLIES
        if value.a1_eccentricity_basis == "verified"
        else ApplicabilityState.UNRESOLVED
    )


@dataclass(frozen=True, slots=True)
class ModalEffectiveMassExecutionInput:
    envelope: RuleExecutionEnvelope
    ratio: float
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, RuleExecutionEnvelope):
            raise TypeError("envelope must be RuleExecutionEnvelope")
        if self.envelope.instance_id.grain is not Grain.DIRECTION:
            raise ValueError("modal effective mass check requires Grain.DIRECTION")
        if self.envelope.instance_id.scope_ref != "BUILDING":
            raise ValueError("modal effective mass check requires BUILDING scope")
        if self.envelope.instance_id.direction not in {"X", "Y"}:
            raise ValueError("modal effective mass direction must be X or Y")
        object.__setattr__(self, "ratio", _finite_ratio(self.ratio, "modal cumulative ratio"))
        object.__setattr__(self, "evidence", _evidence_tuple(self.evidence, "modal evidence"))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ModalEffectiveMassExecutionInput":
        by_key = {item.key: item for item in dependencies}
        expected = {MODAL_RATIO_KEY, MODAL_EVIDENCE_TRACE_KEY}
        if len(by_key) != len(tuple(dependencies)) or set(by_key) != expected:
            raise ValueError("modal execution received unexpected dependency keys")
        return cls(
            envelope=envelope,
            ratio=_finite_ratio(by_key[MODAL_RATIO_KEY].value, "modal cumulative ratio"),
            evidence=_evidence_tuple(by_key[MODAL_EVIDENCE_TRACE_KEY].value, "modal evidence"),
        )


@dataclass(frozen=True, slots=True)
class A1ExecutionInput:
    envelope: RuleExecutionEnvelope
    eta_bi: float
    evidence: tuple[object, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, RuleExecutionEnvelope):
            raise TypeError("envelope must be RuleExecutionEnvelope")
        if self.envelope.instance_id.grain is not Grain.STORY:
            raise ValueError("A1 check requires Grain.STORY")
        if self.envelope.instance_id.direction not in {"X", "Y"}:
            raise ValueError("A1 direction must be X or Y")
        object.__setattr__(self, "eta_bi", _finite_ratio(self.eta_bi, "eta_bi"))
        object.__setattr__(self, "evidence", _evidence_tuple(self.evidence, "A1 evidence"))

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "A1ExecutionInput":
        by_key = {item.key: item for item in dependencies}
        expected = {A1_RATIO_KEY, A1_EVIDENCE_TRACE_KEY}
        if len(by_key) != len(tuple(dependencies)) or set(by_key) != expected:
            raise ValueError("A1 execution received unexpected dependency keys")
        return cls(
            envelope=envelope,
            eta_bi=_finite_ratio(by_key[A1_RATIO_KEY].value, "eta_bi"),
            evidence=_evidence_tuple(by_key[A1_EVIDENCE_TRACE_KEY].value, "A1 evidence"),
        )


def evaluate_modal_effective_mass_95_percent(inp: ModalEffectiveMassExecutionInput) -> CheckResult:
    if not isinstance(inp, ModalEffectiveMassExecutionInput):
        raise TypeError("modal evaluator requires ModalEffectiveMassExecutionInput")
    satisfied = inp.ratio >= MODAL_MIN_RATIO
    return CheckResult(
        check_id=MODAL_RULE_ID.value,
        component="BUILDING",
        component_type="building_direction",
        story=None,
        section=None,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=inp.ratio,
        limit=MODAL_MIN_RATIO,
        ratio=inp.ratio / MODAL_MIN_RATIO,
        ratio_type="value_over_minimum",
        pass_rule="cumulative_effective_mass_ratio >= 0.95",
        unit="ratio",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=(
            "MODAL_95_PERCENT_SUBCONDITION_SATISFIED"
            if satisfied
            else "MODAL_95_PERCENT_SUBCONDITION_NOT_SATISFIED",
        ),
        code_ref=MODAL_CODE_REF,
        diagnostics=(),
    )


def evaluate_torsional_irregularity_a1(inp: A1ExecutionInput) -> CheckResult:
    if not isinstance(inp, A1ExecutionInput):
        raise TypeError("A1 evaluator requires A1ExecutionInput")
    present = inp.eta_bi > A1_PRESENT_LIMIT
    return CheckResult(
        check_id=A1_RULE_ID.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="story",
        story=inp.envelope.instance_id.scope_ref,
        section=None,
        status=CheckStatus.WARNING if present else CheckStatus.OK,
        value=inp.eta_bi,
        limit=A1_PRESENT_LIMIT,
        ratio=inp.eta_bi / A1_PRESENT_LIMIT,
        ratio_type="value_over_limit",
        pass_rule="eta_bi <= 1.2 means A1 not present; eta_bi > 1.2 is WARNING classification",
        unit="ratio",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=("A1_PRESENT" if present else "A1_NOT_PRESENT",),
        code_ref=A1_CODE_REF,
        diagnostics=(),
    )


MODAL_EFFECTIVE_MASS_DEPENDENCIES = (
    DependencySpec(
        key=MODAL_RATIO_KEY,
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.MODAL_CUMULATIVE_EFFECTIVE_MASS_RATIO,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.DIRECTION,
        scope_policy=ScopePolicy.EXACT_SCOPE,
        direction_policy=DirectionPolicy.EXACT_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
    DependencySpec(
        key=MODAL_EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.DIRECTION,
        scope_policy=ScopePolicy.EXACT_SCOPE,
        direction_policy=DirectionPolicy.EXACT_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
)

A1_DEPENDENCIES = (
    DependencySpec(
        key=A1_RATIO_KEY,
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.TORSIONAL_IRREGULARITY_COEFFICIENT,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.STORY,
        scope_policy=ScopePolicy.EXACT_SCOPE,
        direction_policy=DirectionPolicy.EXACT_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
    DependencySpec(
        key=A1_EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.STORY,
        scope_policy=ScopePolicy.EXACT_SCOPE,
        direction_policy=DirectionPolicy.EXACT_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
)

MODAL_EFFECTIVE_MASS_95_PERCENT_CHECK_SPEC = CheckSpec(
    rule_id=MODAL_RULE_ID,
    code_refs=(MODAL_CODE_REF,),
    rule_version=MODAL_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=MODAL_EFFECTIVE_MASS_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "vs3:modal_effective_mass_95_percent:applicability",
        Modal4812ApplicabilityInput,
        modal_4812_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "vs3:modal_effective_mass_95_percent:evaluator",
        ModalEffectiveMassExecutionInput,
        evaluate_modal_effective_mass_95_percent,
    ),
)

TORSIONAL_IRREGULARITY_A1_CHECK_SPEC = CheckSpec(
    rule_id=A1_RULE_ID,
    code_refs=(A1_CODE_REF,),
    rule_version=A1_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=A1_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "vs3:torsional_irregularity_a1:applicability",
        A1ApplicabilityInput,
        a1_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "vs3:torsional_irregularity_a1:evaluator",
        A1ExecutionInput,
        evaluate_torsional_irregularity_a1,
    ),
)

VS3_SEISMIC_REGISTRY = RegulatoryRegistry(
    checks=(
        MODAL_EFFECTIVE_MASS_95_PERCENT_CHECK_SPEC,
        TORSIONAL_IRREGULARITY_A1_CHECK_SPEC,
    )
)


__all__ = [
    "MODAL_RULE_ID",
    "A1_RULE_ID",
    "MODAL_CODE_REF",
    "A1_CODE_REF",
    "MODAL_MIN_RATIO",
    "A1_PRESENT_LIMIT",
    "MODAL_RATIO_KEY",
    "A1_RATIO_KEY",
    "MODAL_EVIDENCE_TRACE_KEY",
    "A1_EVIDENCE_TRACE_KEY",
    "Modal4812ApplicabilityInput",
    "A1ApplicabilityInput",
    "ModalEffectiveMassExecutionInput",
    "A1ExecutionInput",
    "modal_4812_applicability",
    "a1_applicability",
    "evaluate_modal_effective_mass_95_percent",
    "evaluate_torsional_irregularity_a1",
    "MODAL_EFFECTIVE_MASS_95_PERCENT_CHECK_SPEC",
    "TORSIONAL_IRREGULARITY_A1_CHECK_SPEC",
    "VS3_SEISMIC_REGISTRY",
]
