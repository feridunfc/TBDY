"""Bounded source-bound TBDY 2018 §4.3.4.5 A15 post-analysis qualification.

This module contains regulatory evaluation only.  ETABS table discovery,
case selection, pier joins, mechanics projection, scaling review and result
operator reconciliation are factual/context responsibilities of the VS-4B
integration boundary.  The regulatory evaluator accepts a resolved evidence
contract and never rediscovers ETABS semantics.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
import math

from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    DependencyKey,
    DependencySourceKind,
    DependencySpec,
    DerivationEvaluatorBinding,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    PopulationRequirement,
    RegulatoryDerivationSpec,
    RegulatoryOutputContract,
    RegulatoryQuantity,
    RuleId,
    ScopePolicy,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    MaterializedDependency,
    RuleExecutionEnvelope,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.structural_system import (
    ASSUMED_D_KEY,
    ASSUMED_R_KEY,
    ASSUMED_ROW_KEY,
    BYS_KEY,
    DECLARED_ROW_KEY,
    table_4_1_policy,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE

SOURCE_ID = "TBDY2018_AFAD"
RULE_VERSION = "vs4b-a-v2"
BUILDING_SCOPE = "BUILDING"

BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH = (
    "BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH"
)
BLOCKED_RESULT_OPERATOR_AMBIGUITY = "BLOCKED_RESULT_OPERATOR_AMBIGUITY"


class A15QualificationBranch(StrEnum):
    LOWER = "LOWER"
    NOMINAL = "NOMINAL"
    UPPER = "UPPER"


@dataclass(frozen=True, slots=True)
class A15ApplicabilityInput:
    declared_row: str

    def __post_init__(self) -> None:
        if not isinstance(self.declared_row, str) or not self.declared_row.strip():
            raise ValueError("declared_row must be a nonblank Table 4.1 row")
        table_4_1_policy(self.declared_row)


def evaluate_a15_applicability(value: A15ApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, A15ApplicabilityInput):
        raise TypeError("A15 applicability requires A15ApplicabilityInput")
    return (
        ApplicabilityState.APPLIES
        if value.declared_row == "A15"
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


@dataclass(frozen=True, slots=True)
class A15ExecutionInput:
    envelope: RuleExecutionEnvelope
    dependencies: tuple[MaterializedDependency, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "A15ExecutionInput":
        deps = tuple(dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("dependencies must contain MaterializedDependency")
        if len({item.key for item in deps}) != len(deps):
            raise ValueError("duplicate materialized dependency")
        return cls(envelope, tuple(sorted(deps, key=lambda item: item.key.value)))

    def dep(self, key: DependencyKey) -> MaterializedDependency:
        for item in self.dependencies:
            if item.key == key:
                return item
        raise KeyError(key.value)

    def value(self, key: DependencyKey) -> object:
        return self.dep(key).value


A15_MDEV_MO_EVIDENCE_KEY = DependencyKey("rc_a15_mdev_mo_resolved_evidence")
A15_EFFECTIVE_POLICY_KEY = DependencyKey("rc_a15_4345_effective_policy")
A15_ANALYSIS_BASIS_STATUS_KEY = DependencyKey("rc_a15_4345_analysis_basis_status")

RC_A15_4345_EFFECTIVE_POLICY = RuleId("RC_A15_4345_EFFECTIVE_POLICY")
RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY = RuleId(
    "RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY"
)


_REQUIRED_COMPATIBILITY_FLAGS = (
    "mdev_population_resolved",
    "mo_resolved",
    "same_direction",
    "same_regulatory_base",
    "analysis_method_compatible",
    "same_result_realization",
    "same_scaling_state",
    "wall_population_complete",
    "result_operator_resolved",
)


def classify_alpha_m(alpha_m: float) -> A15QualificationBranch:
    """Return the exact §4.3.4.5 A15 branch including equality boundaries."""
    if isinstance(alpha_m, bool) or not isinstance(alpha_m, (int, float)):
        raise TypeError("alphaM must be numeric")
    value = float(alpha_m)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("alphaM must be finite and non-negative")
    if value <= 0.40:
        return A15QualificationBranch.LOWER
    if value < 0.75:
        return A15QualificationBranch.NOMINAL
    return A15QualificationBranch.UPPER


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _resolved_case_values(evidence: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    if evidence.get("regulatory_ready") is not True:
        status = str(evidence.get("blocking_status") or "UNRESOLVED_MDEV_MO_EVIDENCE")
        raise ValueError(status)
    compatibility = _mapping(evidence.get("compatibility"), "compatibility")
    missing = tuple(
        key for key in _REQUIRED_COMPATIBILITY_FLAGS if compatibility.get(key) is not True
    )
    if missing:
        if "analysis_method_compatible" in missing:
            raise ValueError(BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH)
        raise ValueError(BLOCKED_RESULT_OPERATOR_AMBIGUITY)

    cases = evidence.get("cases")
    if not isinstance(cases, (tuple, list)) or len(cases) != 2:
        raise ValueError(
            "A15 first slice requires exactly two independently reviewed eccentricity realizations"
        )
    realized: list[dict[str, object]] = []
    names: set[str] = set()
    for item in cases:
        row = _mapping(item, "case evidence")
        case_name = row.get("case_name")
        if not isinstance(case_name, str) or not case_name.strip() or case_name in names:
            raise ValueError("case evidence requires two unique exact case names")
        names.add(case_name)
        mdev = _finite(row.get("sum_mdev"), f"{case_name}.sum_mdev")
        mo = _finite(row.get("mo"), f"{case_name}.mo")
        if math.isclose(mo, 0.0, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(BLOCKED_RESULT_OPERATOR_AMBIGUITY)
        alpha = mdev / mo
        if not math.isfinite(alpha) or alpha < 0.0:
            raise ValueError(BLOCKED_RESULT_OPERATOR_AMBIGUITY)
        realized.append(
            {
                "case_name": case_name,
                "sum_mdev": mdev,
                "mo": mo,
                "alpha_m": alpha,
                "branch": classify_alpha_m(alpha).value,
            }
        )
    realized.sort(key=lambda item: str(item["case_name"]))
    return tuple(realized)


def resolve_a15_effective_policy(evidence: Mapping[str, object]) -> dict[str, object]:
    """Resolve one directional A15 branch from two exact eccentricity realizations."""
    case_values = _resolved_case_values(evidence)
    branches = {str(item["branch"]) for item in case_values}
    if len(branches) != 1:
        raise ValueError(BLOCKED_RESULT_OPERATOR_AMBIGUITY)
    branch = A15QualificationBranch(next(iter(branches)))
    if branch is A15QualificationBranch.LOWER:
        basis, r, d, minimum_bys = "A15", 7.0, 2.5, 3
    elif branch is A15QualificationBranch.NOMINAL:
        basis, r, d, minimum_bys = "A15", 7.0, 2.5, 2
    else:
        basis, r, d, minimum_bys = "A13", 6.0, 2.5, 2
    return {
        "declared_system_row": "A15",
        "qualification_branch": branch.value,
        "effective_parameter_basis": basis,
        "effective_r": r,
        "effective_d": d,
        "effective_bys_policy": minimum_bys,
        "eccentricity_realizations": case_values,
        "analysis_method": evidence.get("analysis_method"),
        "scaling_state_id": evidence.get("scaling_state_id"),
        "result_operator_id": evidence.get("result_operator_id"),
    }


def resolve_analysis_basis_status(
    policy: Mapping[str, object],
    *,
    assumed_row: str,
    assumed_r: float,
    assumed_d: float,
    building_bys: int,
) -> AnalysisBasisStatus:
    """Resolve the post-qualification VS-4A lifecycle status without rerunning ETABS."""
    table_4_1_policy(assumed_row)
    if isinstance(building_bys, bool) or not isinstance(building_bys, int):
        raise TypeError("building_bys must be an integer")
    minimum_bys = int(policy["effective_bys_policy"])
    if building_bys < minimum_bys:
        return AnalysisBasisStatus.INVALID
    expected_row = str(policy["effective_parameter_basis"])
    expected_r = float(policy["effective_r"])
    expected_d = float(policy["effective_d"])
    exact = (
        assumed_row == expected_row
        and math.isclose(float(assumed_r), expected_r, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(float(assumed_d), expected_d, rel_tol=0.0, abs_tol=1e-12)
    )
    return AnalysisBasisStatus.MATCH if exact else AnalysisBasisStatus.REANALYSIS_REQUIRED


def _quantity(
    inp: A15ExecutionInput,
    *,
    key: DependencyKey,
    semantic: SemanticType,
    value: object,
    governing_trace: tuple[str, ...],
) -> RegulatoryQuantity:
    evidence_refs = tuple(
        sorted({ref for dep in inp.dependencies for ref in dep.evidence_refs})
    )
    return RegulatoryQuantity(
        quantity_key=key,
        producer_instance_id=inp.envelope.instance_id,
        semantic_type=semantic,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=inp.envelope.instance_id.grain,
        scope_ref=inp.envelope.instance_id.scope_ref,
        direction=inp.envelope.instance_id.direction,
        value=value,
        unit=UNIT_ENUM_STATE,
        availability=AvailabilityState.RESOLVED,
        rule_version=inp.envelope.rule_version,
        code_refs=("TBDY 2018 4.3.4.5", "TBDY 2018 4.3.4.8", "TBDY 2018 Table 4.1"),
        dependency_refs=inp.envelope.declared_dependency_refs,
        evidence_refs=evidence_refs,
        provenance=(SOURCE_ID,),
        derivation_trace=(inp.envelope.rule_id.value,),
        governing_trace=governing_trace,
    )


def evaluate_a15_effective_policy(inp: A15ExecutionInput) -> RegulatoryQuantity:
    if str(inp.value(DECLARED_ROW_KEY)) != "A15":
        raise ValueError("RC_A15_4345_EFFECTIVE_POLICY only evaluates a reviewed A15 declaration")
    evidence = _mapping(inp.value(A15_MDEV_MO_EVIDENCE_KEY), "A15 MDEV/Mo evidence")
    policy = resolve_a15_effective_policy(evidence)
    return _quantity(
        inp,
        key=A15_EFFECTIVE_POLICY_KEY,
        semantic=SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,
        value=policy,
        governing_trace=(
            "TBDY2018_4_3_4_5_A15_BRANCHES",
            "TBDY2018_4_3_4_8_SOLID_WALL_MDEV",
            "TBDY2018_4_3_4_8_TOTAL_MO_MODAL",
        ),
    )


def evaluate_a15_analysis_basis_compatibility(inp: A15ExecutionInput) -> RegulatoryQuantity:
    policy = _mapping(inp.value(A15_EFFECTIVE_POLICY_KEY), "A15 effective policy")
    status = resolve_analysis_basis_status(
        policy,
        assumed_row=str(inp.value(ASSUMED_ROW_KEY)),
        assumed_r=_finite(inp.value(ASSUMED_R_KEY), "assumed_r"),
        assumed_d=_finite(inp.value(ASSUMED_D_KEY), "assumed_d"),
        building_bys=int(inp.value(BYS_KEY)),
    )
    return _quantity(
        inp,
        key=A15_ANALYSIS_BASIS_STATUS_KEY,
        semantic=SemanticType.RC_ANALYSIS_BASIS_STATUS,
        value=status.value,
        governing_trace=("TBDY2018_VS4B_A15_ANALYSIS_BASIS_COMPATIBILITY",),
    )


def _ctx_dep(
    key: DependencyKey,
    semantic: SemanticType,
    *,
    unit=UNIT_ENUM_STATE,
    dimension: PhysicalDimension = PhysicalDimension.ENUM_STATE,
) -> DependencySpec:
    return DependencySpec(
        key=key,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.DIRECTION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.SAME_DIRECTION,
        unit_requirement=unit,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    )


def _reg_dep(key: DependencyKey, semantic: SemanticType) -> DependencySpec:
    return DependencySpec(
        key=key,
        source_kind=DependencySourceKind.REGULATORY_QUANTITY,
        semantic_type=semantic,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.DIRECTION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.SAME_DIRECTION,
        unit_requirement=UNIT_ENUM_STATE,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    )


def _derivation(
    *,
    rule_id: RuleId,
    key: DependencyKey,
    semantic: SemanticType,
    dependencies: tuple[DependencySpec, ...],
    evaluator,
    code_refs: tuple[str, ...],
) -> RegulatoryDerivationSpec:
    return RegulatoryDerivationSpec(
        rule_id=rule_id,
        code_refs=code_refs,
        rule_version=RULE_VERSION,
        output_contract=RegulatoryOutputContract(
            key,
            semantic,
            PhysicalDimension.ENUM_STATE,
            Grain.DIRECTION,
            UNIT_ENUM_STATE,
        ),
        dependencies=dependencies,
        applicability=ApplicabilityBinding(
            f"vs4b-a:{rule_id.value}:applicability",
            A15ApplicabilityInput,
            evaluate_a15_applicability,
        ),
        evaluator=DerivationEvaluatorBinding(
            f"vs4b-a:{rule_id.value}:evaluator",
            A15ExecutionInput,
            evaluator,
        ),
    )


A15_EFFECTIVE_POLICY_SPEC = _derivation(
    rule_id=RC_A15_4345_EFFECTIVE_POLICY,
    key=A15_EFFECTIVE_POLICY_KEY,
    semantic=SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,
    dependencies=(
        _ctx_dep(DECLARED_ROW_KEY, SemanticType.RC_TABLE_4_1_ROW),
        _ctx_dep(A15_MDEV_MO_EVIDENCE_KEY, SemanticType.CHECK_EVIDENCE_TRACE),
    ),
    evaluator=evaluate_a15_effective_policy,
    code_refs=(
        "TBDY 2018 4.3.4.5",
        "TBDY 2018 4.3.4.8",
        "TBDY 2018 4.5.3.7(d)",
        "TBDY 2018 4.5.3.8(c)",
        "TBDY 2018 4.8.2.1",
        "TBDY 2018 4B.2.5",
        "TBDY 2018 Table 4.1 A13",
        "TBDY 2018 Table 4.1 A15",
    ),
)

A15_ANALYSIS_BASIS_SPEC = _derivation(
    rule_id=RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY,
    key=A15_ANALYSIS_BASIS_STATUS_KEY,
    semantic=SemanticType.RC_ANALYSIS_BASIS_STATUS,
    dependencies=(
        _reg_dep(A15_EFFECTIVE_POLICY_KEY, SemanticType.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY),
        _ctx_dep(ASSUMED_ROW_KEY, SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION),
        _ctx_dep(
            ASSUMED_R_KEY,
            SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
            unit=UNIT_DIMENSIONLESS,
            dimension=PhysicalDimension.DIMENSIONLESS,
        ),
        _ctx_dep(
            ASSUMED_D_KEY,
            SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
            unit=UNIT_DIMENSIONLESS,
            dimension=PhysicalDimension.DIMENSIONLESS,
        ),
        _ctx_dep(BYS_KEY, SemanticType.RC_BYS),
    ),
    evaluator=evaluate_a15_analysis_basis_compatibility,
    code_refs=("TBDY 2018 4.3.4.5", "TBDY 2018 Table 4.1 A13", "TBDY 2018 Table 4.1 A15"),
)

VS4B_A15_REGISTRY = RegulatoryRegistry(
    derivations=(A15_EFFECTIVE_POLICY_SPEC, A15_ANALYSIS_BASIS_SPEC)
)

ALL_VS4B_A15_RULE_IDS = (
    RC_A15_4345_EFFECTIVE_POLICY,
    RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY,
)


__all__ = [
    "A15QualificationBranch",
    "A15ApplicabilityInput",
    "A15ExecutionInput",
    "A15_MDEV_MO_EVIDENCE_KEY",
    "A15_EFFECTIVE_POLICY_KEY",
    "A15_ANALYSIS_BASIS_STATUS_KEY",
    "RC_A15_4345_EFFECTIVE_POLICY",
    "RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY",
    "A15_EFFECTIVE_POLICY_SPEC",
    "A15_ANALYSIS_BASIS_SPEC",
    "VS4B_A15_REGISTRY",
    "ALL_VS4B_A15_RULE_IDS",
    "BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH",
    "BLOCKED_RESULT_OPERATOR_AMBIGUITY",
    "classify_alpha_m",
    "resolve_a15_effective_policy",
    "resolve_analysis_basis_status",
    "evaluate_a15_effective_policy",
    "evaluate_a15_analysis_basis_compatibility",
]
