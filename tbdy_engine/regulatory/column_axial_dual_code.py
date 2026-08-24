"""VS5 source-bound dual-code reinforced-concrete column axial checks.

Demand selection is completed before this module is entered. This module owns
only the formal TBDY 2018 7.3.1.2 and TS 500 7.4.1 compliance checks and emits
canonical CheckResult objects through the F0 regulatory kernel.
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
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_KN, UNIT_M, UNIT_MPA

TBDY_RULE_ID = RuleId("TBDY_7_3_1_2_COLUMN_AXIAL")
TS500_RULE_ID = RuleId("TS500_7_4_1_COLUMN_AXIAL")
TBDY_RULE_VERSION = "vs5-column-axial-tbdy-v1"
TS500_RULE_VERSION = "vs5-column-axial-ts500-v1"

TBDY_CODE_REF = "TBDY 2018 7.3.1.2"
TS500_CODE_REF = "TS 500 6.2.5, 6.2.6, 7.4.1"

COLUMN_WIDTH_M_KEY = DependencyKey("column_width_m")
COLUMN_DEPTH_M_KEY = DependencyKey("column_depth_m")
CONCRETE_FCK_MPA_KEY = DependencyKey("concrete_fck_mpa")
TBDY_NDM_KN_KEY = DependencyKey("tbdy_ndm_kn")
TS500_ND_KN_KEY = DependencyKey("ts500_nd_kn")
TS500_GAMMA_MC_KEY = DependencyKey("ts500_gamma_mc")
STORY_KEY = DependencyKey("story")
SECTION_KEY = DependencyKey("section")
EVIDENCE_TRACE_KEY = DependencyKey("column_axial_evidence_trace")

# Exact source-bound constants. They are deliberately not catalog/YAML data.
_TBDY_AXIAL_COEFFICIENT = 0.40
_TS500_AXIAL_COEFFICIENT = 0.90
_MPA_M2_TO_KN = 1000.0


def _finite_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and > 0")
    return result


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and >= 0")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TypeError(f"{label} must be a nonblank canonical string")
    return value


def _evidence(value: object) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise TypeError("column axial evidence trace must materialize as immutable tuple")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class ColumnAxialApplicabilityInput:
    component_type: str
    reinforced_concrete: bool | None

    def __post_init__(self) -> None:
        _text(self.component_type, "component_type")
        if self.reinforced_concrete is not None and type(self.reinforced_concrete) is not bool:
            raise TypeError("reinforced_concrete must be bool or None")


def column_axial_applicability(value: ColumnAxialApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, ColumnAxialApplicabilityInput):
        raise TypeError("column axial applicability requires ColumnAxialApplicabilityInput")
    if value.component_type.casefold() != "column":
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.reinforced_concrete is None:
        return ApplicabilityState.UNRESOLVED
    return ApplicabilityState.APPLIES if value.reinforced_concrete else ApplicabilityState.PROVEN_NOT_APPLICABLE


@dataclass(frozen=True, slots=True)
class TbdyColumnAxialExecutionInput:
    envelope: RuleExecutionEnvelope
    width_m: float
    depth_m: float
    fck_mpa: float
    ndm_kn: float
    story: str
    section: str
    evidence: tuple[object, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "TbdyColumnAxialExecutionInput":
        deps = tuple(dependencies)
        by_key = {item.key: item for item in deps}
        expected = {
            COLUMN_WIDTH_M_KEY,
            COLUMN_DEPTH_M_KEY,
            CONCRETE_FCK_MPA_KEY,
            TBDY_NDM_KN_KEY,
            STORY_KEY,
            SECTION_KEY,
            EVIDENCE_TRACE_KEY,
        }
        if len(by_key) != len(deps) or set(by_key) != expected:
            raise ValueError("TBDY column axial execution received unexpected dependency keys")
        return cls(
            envelope=envelope,
            width_m=_finite_positive(by_key[COLUMN_WIDTH_M_KEY].value, "column_width_m"),
            depth_m=_finite_positive(by_key[COLUMN_DEPTH_M_KEY].value, "column_depth_m"),
            fck_mpa=_finite_positive(by_key[CONCRETE_FCK_MPA_KEY].value, "concrete_fck_mpa"),
            ndm_kn=_finite_nonnegative(by_key[TBDY_NDM_KN_KEY].value, "tbdy_ndm_kn"),
            story=_text(by_key[STORY_KEY].value, "story"),
            section=_text(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


@dataclass(frozen=True, slots=True)
class Ts500ColumnAxialExecutionInput:
    envelope: RuleExecutionEnvelope
    width_m: float
    depth_m: float
    fck_mpa: float
    nd_kn: float
    gamma_mc: float
    story: str
    section: str
    evidence: tuple[object, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "Ts500ColumnAxialExecutionInput":
        deps = tuple(dependencies)
        by_key = {item.key: item for item in deps}
        expected = {
            COLUMN_WIDTH_M_KEY,
            COLUMN_DEPTH_M_KEY,
            CONCRETE_FCK_MPA_KEY,
            TS500_ND_KN_KEY,
            TS500_GAMMA_MC_KEY,
            STORY_KEY,
            SECTION_KEY,
            EVIDENCE_TRACE_KEY,
        }
        if len(by_key) != len(deps) or set(by_key) != expected:
            raise ValueError("TS500 column axial execution received unexpected dependency keys")
        return cls(
            envelope=envelope,
            width_m=_finite_positive(by_key[COLUMN_WIDTH_M_KEY].value, "column_width_m"),
            depth_m=_finite_positive(by_key[COLUMN_DEPTH_M_KEY].value, "column_depth_m"),
            fck_mpa=_finite_positive(by_key[CONCRETE_FCK_MPA_KEY].value, "concrete_fck_mpa"),
            nd_kn=_finite_nonnegative(by_key[TS500_ND_KN_KEY].value, "ts500_nd_kn"),
            gamma_mc=_finite_positive(by_key[TS500_GAMMA_MC_KEY].value, "ts500_gamma_mc"),
            story=_text(by_key[STORY_KEY].value, "story"),
            section=_text(by_key[SECTION_KEY].value, "section"),
            evidence=_evidence(by_key[EVIDENCE_TRACE_KEY].value),
        )


def evaluate_tbdy_column_axial(inp: TbdyColumnAxialExecutionInput) -> CheckResult:
    if not isinstance(inp, TbdyColumnAxialExecutionInput):
        raise TypeError("TBDY column axial evaluator requires TbdyColumnAxialExecutionInput")
    ac_m2 = inp.width_m * inp.depth_m
    capacity_kn = _TBDY_AXIAL_COEFFICIENT * ac_m2 * inp.fck_mpa * _MPA_M2_TO_KN
    ratio = inp.ndm_kn / capacity_kn
    satisfied = inp.ndm_kn <= capacity_kn
    return CheckResult(
        check_id=TBDY_RULE_ID.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="column",
        story=inp.story,
        section=inp.section,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=inp.ndm_kn,
        limit=capacity_kn,
        demand=inp.ndm_kn,
        capacity=capacity_kn,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule="Ndm <= 0.40 * Ac * fck",
        unit="kN",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=("TBDY_7_3_1_2_SATISFIED" if satisfied else "TBDY_7_3_1_2_NOT_SATISFIED",),
        code_ref=TBDY_CODE_REF,
        diagnostics=(),
    )


def evaluate_ts500_column_axial(inp: Ts500ColumnAxialExecutionInput) -> CheckResult:
    if not isinstance(inp, Ts500ColumnAxialExecutionInput):
        raise TypeError("TS500 column axial evaluator requires Ts500ColumnAxialExecutionInput")
    ac_m2 = inp.width_m * inp.depth_m
    fcd_mpa = inp.fck_mpa / inp.gamma_mc
    capacity_kn = _TS500_AXIAL_COEFFICIENT * ac_m2 * fcd_mpa * _MPA_M2_TO_KN
    ratio = inp.nd_kn / capacity_kn
    satisfied = inp.nd_kn <= capacity_kn
    return CheckResult(
        check_id=TS500_RULE_ID.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="column",
        story=inp.story,
        section=inp.section,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=inp.nd_kn,
        limit=capacity_kn,
        demand=inp.nd_kn,
        capacity=capacity_kn,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule="Nd <= 0.90 * Ac * fcd; fcd = fck / gamma_mc",
        unit="kN",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=("TS500_7_4_1_SATISFIED" if satisfied else "TS500_7_4_1_NOT_SATISFIED",),
        code_ref=TS500_CODE_REF,
        diagnostics=(),
    )


def _dependency(
    *,
    key: DependencyKey,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    unit,
    source_kind: DependencySourceKind,
    population: PopulationRequirement = PopulationRequirement.ANY_RESOLVED,
) -> DependencySpec:
    return DependencySpec(
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=unit,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=population,
    )


_COMMON_DEPENDENCIES = (
    _dependency(
        key=COLUMN_WIDTH_M_KEY,
        semantic_type=SemanticType.COLUMN_WIDTH,
        dimension=PhysicalDimension.LENGTH,
        unit=UNIT_M,
        source_kind=DependencySourceKind.FACT,
    ),
    _dependency(
        key=COLUMN_DEPTH_M_KEY,
        semantic_type=SemanticType.COLUMN_DEPTH,
        dimension=PhysicalDimension.LENGTH,
        unit=UNIT_M,
        source_kind=DependencySourceKind.FACT,
    ),
    _dependency(
        key=CONCRETE_FCK_MPA_KEY,
        semantic_type=SemanticType.CONCRETE_FCK,
        dimension=PhysicalDimension.STRESS,
        unit=UNIT_MPA,
        source_kind=DependencySourceKind.FACT,
    ),
    _dependency(
        key=STORY_KEY,
        semantic_type=SemanticType.COMPONENT_STORY,
        dimension=PhysicalDimension.ENUM_STATE,
        unit=UNIT_ENUM_STATE,
        source_kind=DependencySourceKind.CONTEXT,
    ),
    _dependency(
        key=SECTION_KEY,
        semantic_type=SemanticType.COMPONENT_SECTION,
        dimension=PhysicalDimension.ENUM_STATE,
        unit=UNIT_ENUM_STATE,
        source_kind=DependencySourceKind.CONTEXT,
    ),
    _dependency(
        key=EVIDENCE_TRACE_KEY,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        dimension=PhysicalDimension.DIMENSIONLESS,
        unit=UNIT_DIMENSIONLESS,
        source_kind=DependencySourceKind.CONTEXT,
        population=PopulationRequirement.FULL,
    ),
)

_TBDY_DEPENDENCIES = _COMMON_DEPENDENCIES + (
    _dependency(
        key=TBDY_NDM_KN_KEY,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        dimension=PhysicalDimension.FORCE,
        unit=UNIT_KN,
        source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
        population=PopulationRequirement.FULL,
    ),
)

_TS500_DEPENDENCIES = _COMMON_DEPENDENCIES + (
    _dependency(
        key=TS500_ND_KN_KEY,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        dimension=PhysicalDimension.FORCE,
        unit=UNIT_KN,
        source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
        population=PopulationRequirement.FULL,
    ),
    _dependency(
        key=TS500_GAMMA_MC_KEY,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        dimension=PhysicalDimension.DIMENSIONLESS,
        unit=UNIT_DIMENSIONLESS,
        source_kind=DependencySourceKind.CONTEXT,
    ),
)

_APPLICABILITY = ApplicabilityBinding(
    "vs5:column_axial:applicability",
    ColumnAxialApplicabilityInput,
    column_axial_applicability,
)

TBDY_COLUMN_AXIAL_CHECK_SPEC = CheckSpec(
    rule_id=TBDY_RULE_ID,
    code_refs=(TBDY_CODE_REF,),
    rule_version=TBDY_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=_TBDY_DEPENDENCIES,
    applicability=_APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        "vs5:tbdy_7_3_1_2:column_axial",
        TbdyColumnAxialExecutionInput,
        evaluate_tbdy_column_axial,
    ),
)

TS500_COLUMN_AXIAL_CHECK_SPEC = CheckSpec(
    rule_id=TS500_RULE_ID,
    code_refs=(TS500_CODE_REF,),
    rule_version=TS500_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=_TS500_DEPENDENCIES,
    applicability=_APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        "vs5:ts500_7_4_1:column_axial",
        Ts500ColumnAxialExecutionInput,
        evaluate_ts500_column_axial,
    ),
)

VS5_COLUMN_AXIAL_REGISTRY = RegulatoryRegistry(
    checks=(TBDY_COLUMN_AXIAL_CHECK_SPEC, TS500_COLUMN_AXIAL_CHECK_SPEC)
)

__all__ = [
    "TBDY_RULE_ID",
    "TS500_RULE_ID",
    "TBDY_RULE_VERSION",
    "TS500_RULE_VERSION",
    "TBDY_CODE_REF",
    "TS500_CODE_REF",
    "COLUMN_WIDTH_M_KEY",
    "COLUMN_DEPTH_M_KEY",
    "CONCRETE_FCK_MPA_KEY",
    "TBDY_NDM_KN_KEY",
    "TS500_ND_KN_KEY",
    "TS500_GAMMA_MC_KEY",
    "STORY_KEY",
    "SECTION_KEY",
    "EVIDENCE_TRACE_KEY",
    "ColumnAxialApplicabilityInput",
    "TbdyColumnAxialExecutionInput",
    "Ts500ColumnAxialExecutionInput",
    "evaluate_tbdy_column_axial",
    "evaluate_ts500_column_axial",
    "TBDY_COLUMN_AXIAL_CHECK_SPEC",
    "TS500_COLUMN_AXIAL_CHECK_SPEC",
    "VS5_COLUMN_AXIAL_REGISTRY",
]
