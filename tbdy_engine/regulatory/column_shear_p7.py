"""F0.9 source-bound formal VS6-P7 column-shear rules.

This module is the only P7 regulatory engineering authority.  Acquisition,
capacity resolution and context promotion occur upstream; this module owns the
reviewed TBDY/TS500 derivation and formal upper-bound verdicts through the
canonical F0 RegulatoryEngine.

Working units at this boundary are kN, kN*m, mm and MPa.
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
from tbdy_engine.regulatory.kernel import MaterializedDependency, RuleExecutionEnvelope
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import (
    UNIT_DIMENSIONLESS,
    UNIT_ENUM_STATE,
    UNIT_KN,
    UNIT_KN_M,
    UNIT_MM,
    UNIT_MPA,
)

VE_RULE_ID = RuleId("TBDY_7_3_7_COLUMN_SHEAR_VE")
TBDY_BRITTLE_RULE_ID = RuleId("TBDY_7_3_7_5_COLUMN_SHEAR_BRITTLE_BOUND")
TS500_WEB_RULE_ID = RuleId("TS500_8_1_5_B_COLUMN_SHEAR_WEB_COMPRESSION")

VE_RULE_VERSION = "vs6-p7-ve-v1"
TBDY_BRITTLE_RULE_VERSION = "vs6-p7-tbdy-brittle-v1"
TS500_WEB_RULE_VERSION = "vs6-p7-ts500-web-v1"

VE_CODE_REFS = (
    "TBDY 2018 7.3.7.1 Eq. (7.5)",
    "TBDY 2018 7.3.7.3",
    "TBDY 2018 7.3.7.4",
    "TBDY 2018 7.3.7.5",
)
TBDY_BRITTLE_CODE_REF = "TBDY 2018 7.3.7.5 Eq. (7.7)"
TS500_WEB_CODE_REF = "TS 500 8.1.5(b) Eq. (8.7)"

BOTTOM_CAPACITY_KNM_KEY = DependencyKey("column_shear_bottom_end_capacity_knm")
TOP_CAPACITY_KNM_KEY = DependencyKey("column_shear_top_end_capacity_knm")
FREE_LENGTH_MM_KEY = DependencyKey("column_free_length_ln_mm")
D_AMPLIFIED_KN_KEY = DependencyKey("column_shear_d_amplified_candidate_kn")
TBDY_VD_KN_KEY = DependencyKey("column_shear_tbdy_vd_kn")
VE_KN_KEY = DependencyKey("column_shear_ve_kn")

COLUMN_WIDTH_MM_KEY = DependencyKey("column_width_mm")
COLUMN_DEPTH_MM_KEY = DependencyKey("column_depth_mm")
CONCRETE_FCK_MPA_KEY = DependencyKey("concrete_fck_mpa")
TS500_VD_KN_KEY = DependencyKey("column_shear_ts500_vd_kn")
TS500_FCD_MPA_KEY = DependencyKey("concrete_fcd_mpa")
EFFECTIVE_DEPTH_MM_KEY = DependencyKey("column_shear_effective_depth_d_mm")
STORY_KEY = DependencyKey("story")
SECTION_KEY = DependencyKey("section")
EVIDENCE_TRACE_KEY = DependencyKey("column_shear_evidence_trace")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TypeError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and >= 0")
    return result


@dataclass(frozen=True, slots=True)
class ColumnShearP7ApplicabilityInput:
    component_type: str
    reinforced_concrete: bool | None
    tbdy_737_high_ductility_applies: bool | None

    def __post_init__(self) -> None:
        _text(self.component_type, "component_type")
        if self.reinforced_concrete is not None and type(self.reinforced_concrete) is not bool:
            raise TypeError("reinforced_concrete must be bool or None")
        if (
            self.tbdy_737_high_ductility_applies is not None
            and type(self.tbdy_737_high_ductility_applies) is not bool
        ):
            raise TypeError("tbdy_737_high_ductility_applies must be bool or None")


def _rc_column_common(value: ColumnShearP7ApplicabilityInput) -> ApplicabilityState | None:
    if not isinstance(value, ColumnShearP7ApplicabilityInput):
        raise TypeError("P7 applicability requires ColumnShearP7ApplicabilityInput")
    if value.component_type.casefold() != "column":
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.reinforced_concrete is None:
        return ApplicabilityState.UNRESOLVED
    if value.reinforced_concrete is False:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    return None


def tbdy_737_applicability(value: ColumnShearP7ApplicabilityInput) -> ApplicabilityState:
    common = _rc_column_common(value)
    if common is not None:
        return common
    if value.tbdy_737_high_ductility_applies is None:
        return ApplicabilityState.UNRESOLVED
    return (
        ApplicabilityState.APPLIES
        if value.tbdy_737_high_ductility_applies
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


def ts500_815_applicability(value: ColumnShearP7ApplicabilityInput) -> ApplicabilityState:
    common = _rc_column_common(value)
    return ApplicabilityState.APPLIES if common is None else common


@dataclass(frozen=True, slots=True)
class ColumnShearP7ExecutionInput:
    envelope: RuleExecutionEnvelope
    dependencies: tuple[MaterializedDependency, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ColumnShearP7ExecutionInput":
        deps = tuple(dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("dependencies must contain MaterializedDependency")
        if len({item.key for item in deps}) != len(deps):
            raise ValueError("duplicate P7 declared dependency")
        return cls(envelope=envelope, dependencies=deps)

    def one(self, key: DependencyKey) -> MaterializedDependency:
        for item in self.dependencies:
            if item.key == key:
                return item
        raise KeyError(f"missing declared P7 dependency: {key.value}")

    def value(self, key: DependencyKey) -> object:
        return self.one(key).value

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                ref
                for dependency in self.dependencies
                for ref in dependency.evidence_refs
            )
        )

    @property
    def dependency_refs(self) -> tuple[DependencyKey, ...]:
        return tuple(item.key for item in self.dependencies)


def derive_tbdy_column_shear_ve(inp: ColumnShearP7ExecutionInput) -> RegulatoryQuantity:
    bottom_knm = _positive(inp.value(BOTTOM_CAPACITY_KNM_KEY), "bottom_capacity_knm")
    top_knm = _positive(inp.value(TOP_CAPACITY_KNM_KEY), "top_capacity_knm")
    ln_mm = _positive(inp.value(FREE_LENGTH_MM_KEY), "free_length_ln_mm")
    d_candidate_kn = _nonnegative(inp.value(D_AMPLIFIED_KN_KEY), "d_amplified_candidate_kn")
    vd_kn = _nonnegative(inp.value(TBDY_VD_KN_KEY), "tbdy_vd_kn")

    # kN*m * 1000 mm/m / mm = kN.
    ve_capacity_kn = (bottom_knm + top_knm) * 1000.0 / ln_mm
    pre_floor_kn = min(ve_capacity_kn, d_candidate_kn)
    ve_kn = max(pre_floor_kn, vd_kn)
    if vd_kn > pre_floor_kn:
        governing = "TBDY_7_3_7_5_VD_FLOOR"
    elif ve_capacity_kn <= d_candidate_kn:
        governing = "TBDY_7_3_7_1_EQ7_5"
    else:
        governing = "TBDY_7_3_7_1_D_AMPLIFIED_CANDIDATE"

    return RegulatoryQuantity(
        quantity_key=VE_KN_KEY,
        producer_instance_id=inp.envelope.instance_id,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.FORCE,
        grain=Grain.COMPONENT_DIRECTION,
        scope_ref=inp.envelope.instance_id.scope_ref,
        direction=inp.envelope.instance_id.direction,
        value=ve_kn,
        unit=UNIT_KN,
        availability=AvailabilityState.RESOLVED,
        rule_version=VE_RULE_VERSION,
        code_refs=VE_CODE_REFS,
        dependency_refs=inp.dependency_refs,
        evidence_refs=inp.evidence_refs,
        provenance=("VS6-P7:F0.9:SOURCE_BOUND",),
        derivation_trace=(
            ("ve_capacity_eq75_kn", ve_capacity_kn),
            ("d_amplified_candidate_kn", d_candidate_kn),
            ("vd_floor_kn", vd_kn),
            ("final_ve_kn", ve_kn),
        ),
        governing_trace=(governing,),
    )


def evaluate_tbdy_column_shear_brittle_bound(
    inp: ColumnShearP7ExecutionInput,
) -> CheckResult:
    ve_kn = _nonnegative(inp.value(VE_KN_KEY), "ve_kn")
    width_mm = _positive(inp.value(COLUMN_WIDTH_MM_KEY), "column_width_mm")
    depth_mm = _positive(inp.value(COLUMN_DEPTH_MM_KEY), "column_depth_mm")
    fck_mpa = _positive(inp.value(CONCRETE_FCK_MPA_KEY), "concrete_fck_mpa")
    story = _text(inp.value(STORY_KEY), "story")
    section = _text(inp.value(SECTION_KEY), "section")

    # Bounded P7 geometry is strict plain rectangular column; there are no
    # projections to exclude from Aw in this slice.
    aw_mm2 = width_mm * depth_mm
    limit_kn = 0.85 * aw_mm2 * math.sqrt(fck_mpa) / 1000.0
    ratio = ve_kn / limit_kn
    satisfied = ve_kn <= limit_kn
    return CheckResult(
        check_id=TBDY_BRITTLE_RULE_ID.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="column",
        story=story,
        section=section,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=ve_kn,
        limit=limit_kn,
        demand=ve_kn,
        capacity=limit_kn,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule="Ve <= 0.85 * Aw * sqrt(fck)",
        unit="kN",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence_refs,
        messages=(
            "TBDY_7_3_7_5_EQ7_7_BRITTLE_SATISFIED"
            if satisfied
            else "TBDY_7_3_7_5_EQ7_7_BRITTLE_NOT_SATISFIED_SECTION_ENLARGEMENT_AND_REANALYSIS_REQUIRED",
        ),
        code_ref=TBDY_BRITTLE_CODE_REF,
        diagnostics=(),
    )


def evaluate_ts500_column_shear_web_bound(
    inp: ColumnShearP7ExecutionInput,
) -> CheckResult:
    vd_kn = _nonnegative(inp.value(TS500_VD_KN_KEY), "ts500_vd_kn")
    fcd_mpa = _positive(inp.value(TS500_FCD_MPA_KEY), "concrete_fcd_mpa")
    width_mm = _positive(inp.value(COLUMN_WIDTH_MM_KEY), "column_width_mm")
    depth_mm = _positive(inp.value(COLUMN_DEPTH_MM_KEY), "column_depth_mm")
    d_mm = _positive(inp.value(EFFECTIVE_DEPTH_MM_KEY), "effective_depth_d_mm")
    story = _text(inp.value(STORY_KEY), "story")
    section = _text(inp.value(SECTION_KEY), "section")
    direction = _text(inp.envelope.instance_id.direction, "direction")

    if direction == "V2":
        bw_mm = depth_mm
        member_depth_mm = width_mm
    elif direction == "V3":
        bw_mm = width_mm
        member_depth_mm = depth_mm
    else:
        raise ValueError("P7 formal direction must be V2 or V3")
    if d_mm >= member_depth_mm + 1e-9:
        raise ValueError("effective depth is incompatible with the reviewed local-axis section depth")

    limit_kn = 0.22 * fcd_mpa * bw_mm * d_mm / 1000.0
    ratio = vd_kn / limit_kn
    satisfied = vd_kn <= limit_kn
    return CheckResult(
        check_id=TS500_WEB_RULE_ID.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="column",
        story=story,
        section=section,
        status=CheckStatus.OK if satisfied else CheckStatus.FAIL,
        value=vd_kn,
        limit=limit_kn,
        demand=vd_kn,
        capacity=limit_kn,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule="Vd <= 0.22 * fcd * bw * d",
        unit="kN",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence_refs,
        messages=(
            "TS500_8_1_5_WEB_COMPRESSION_SATISFIED"
            if satisfied
            else "TS500_8_1_5_WEB_COMPRESSION_NOT_SATISFIED",
        ),
        code_ref=TS500_WEB_CODE_REF,
        diagnostics=(),
    )


def _dep(
    key: DependencyKey,
    *,
    source_kind: DependencySourceKind,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    grain: Grain,
    direction_policy: DirectionPolicy,
    unit,
    population: PopulationRequirement = PopulationRequirement.FULL,
) -> DependencySpec:
    return DependencySpec(
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=grain,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=direction_policy,
        unit_requirement=unit,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=population,
    )


def _component_fact(
    key: DependencyKey,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    unit,
) -> DependencySpec:
    return _dep(
        key,
        source_kind=DependencySourceKind.FACT,
        semantic_type=semantic_type,
        dimension=dimension,
        grain=Grain.COMPONENT,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit=unit,
    )


def _component_context(
    key: DependencyKey,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    unit,
) -> DependencySpec:
    return _dep(
        key,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=semantic_type,
        dimension=dimension,
        grain=Grain.COMPONENT,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit=unit,
    )


def _direction_selected(
    key: DependencyKey,
    dimension: PhysicalDimension,
    unit,
) -> DependencySpec:
    return _dep(
        key,
        source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        dimension=dimension,
        grain=Grain.COMPONENT_DIRECTION,
        direction_policy=DirectionPolicy.SAME_DIRECTION,
        unit=unit,
    )


def _direction_context(
    key: DependencyKey,
    dimension: PhysicalDimension,
    unit,
) -> DependencySpec:
    return _dep(
        key,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        dimension=dimension,
        grain=Grain.COMPONENT_DIRECTION,
        direction_policy=DirectionPolicy.SAME_DIRECTION,
        unit=unit,
    )


WIDTH_DEP = _component_fact(
    COLUMN_WIDTH_MM_KEY, SemanticType.COLUMN_WIDTH, PhysicalDimension.LENGTH, UNIT_MM
)
DEPTH_DEP = _component_fact(
    COLUMN_DEPTH_MM_KEY, SemanticType.COLUMN_DEPTH, PhysicalDimension.LENGTH, UNIT_MM
)
FCK_DEP = _component_fact(
    CONCRETE_FCK_MPA_KEY, SemanticType.CONCRETE_FCK, PhysicalDimension.STRESS, UNIT_MPA
)
STORY_DEP = _component_context(
    STORY_KEY, SemanticType.COMPONENT_STORY, PhysicalDimension.ENUM_STATE, UNIT_ENUM_STATE
)
SECTION_DEP = _component_context(
    SECTION_KEY, SemanticType.COMPONENT_SECTION, PhysicalDimension.ENUM_STATE, UNIT_ENUM_STATE
)
EVIDENCE_DEP = _direction_context(
    EVIDENCE_TRACE_KEY, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS
)

BOTTOM_CAPACITY_DEP = _direction_selected(
    BOTTOM_CAPACITY_KNM_KEY, PhysicalDimension.MOMENT, UNIT_KN_M
)
TOP_CAPACITY_DEP = _direction_selected(
    TOP_CAPACITY_KNM_KEY, PhysicalDimension.MOMENT, UNIT_KN_M
)
FREE_LENGTH_DEP = _dep(
    FREE_LENGTH_MM_KEY,
    source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
    semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
    dimension=PhysicalDimension.LENGTH,
    grain=Grain.COMPONENT,
    direction_policy=DirectionPolicy.NO_DIRECTION,
    unit=UNIT_MM,
)
D_AMPLIFIED_DEP = _direction_selected(
    D_AMPLIFIED_KN_KEY, PhysicalDimension.FORCE, UNIT_KN
)
TBDY_VD_DEP = _direction_selected(
    TBDY_VD_KN_KEY, PhysicalDimension.FORCE, UNIT_KN
)
TS500_VD_DEP = _direction_selected(
    TS500_VD_KN_KEY, PhysicalDimension.FORCE, UNIT_KN
)
FCD_DEP = _component_context(
    TS500_FCD_MPA_KEY, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.STRESS, UNIT_MPA
)
EFFECTIVE_DEPTH_DEP = _direction_selected(
    EFFECTIVE_DEPTH_MM_KEY, PhysicalDimension.LENGTH, UNIT_MM
)
VE_REG_DEP = _dep(
    VE_KN_KEY,
    source_kind=DependencySourceKind.REGULATORY_QUANTITY,
    semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
    dimension=PhysicalDimension.FORCE,
    grain=Grain.COMPONENT_DIRECTION,
    direction_policy=DirectionPolicy.SAME_DIRECTION,
    unit=UNIT_KN,
)

TBDY_APPLICABILITY = ApplicabilityBinding(
    "vs6-p7:tbdy-737:applicability",
    ColumnShearP7ApplicabilityInput,
    tbdy_737_applicability,
)
TS500_APPLICABILITY = ApplicabilityBinding(
    "vs6-p7:ts500-815:applicability",
    ColumnShearP7ApplicabilityInput,
    ts500_815_applicability,
)

VE_DERIVATION_SPEC = RegulatoryDerivationSpec(
    rule_id=VE_RULE_ID,
    code_refs=VE_CODE_REFS,
    rule_version=VE_RULE_VERSION,
    output_contract=RegulatoryOutputContract(
        VE_KN_KEY,
        SemanticType.CHECK_EVIDENCE_TRACE,
        PhysicalDimension.FORCE,
        Grain.COMPONENT_DIRECTION,
        UNIT_KN,
    ),
    dependencies=(
        BOTTOM_CAPACITY_DEP,
        TOP_CAPACITY_DEP,
        FREE_LENGTH_DEP,
        D_AMPLIFIED_DEP,
        TBDY_VD_DEP,
        EVIDENCE_DEP,
    ),
    applicability=TBDY_APPLICABILITY,
    evaluator=DerivationEvaluatorBinding(
        "vs6-p7:tbdy-737:ve",
        ColumnShearP7ExecutionInput,
        derive_tbdy_column_shear_ve,
    ),
)

TBDY_BRITTLE_CHECK_SPEC = CheckSpec(
    rule_id=TBDY_BRITTLE_RULE_ID,
    code_refs=(TBDY_BRITTLE_CODE_REF,),
    rule_version=TBDY_BRITTLE_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(
        VE_REG_DEP,
        WIDTH_DEP,
        DEPTH_DEP,
        FCK_DEP,
        STORY_DEP,
        SECTION_DEP,
        EVIDENCE_DEP,
    ),
    applicability=TBDY_APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        "vs6-p7:tbdy-7375:brittle-bound",
        ColumnShearP7ExecutionInput,
        evaluate_tbdy_column_shear_brittle_bound,
    ),
)

TS500_WEB_CHECK_SPEC = CheckSpec(
    rule_id=TS500_WEB_RULE_ID,
    code_refs=(TS500_WEB_CODE_REF,),
    rule_version=TS500_WEB_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(
        TS500_VD_DEP,
        FCD_DEP,
        WIDTH_DEP,
        DEPTH_DEP,
        EFFECTIVE_DEPTH_DEP,
        STORY_DEP,
        SECTION_DEP,
        EVIDENCE_DEP,
    ),
    applicability=TS500_APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        "vs6-p7:ts500-815:web-bound",
        ColumnShearP7ExecutionInput,
        evaluate_ts500_column_shear_web_bound,
    ),
)

VS6_COLUMN_SHEAR_P7_REGISTRY = RegulatoryRegistry(
    derivations=(VE_DERIVATION_SPEC,),
    checks=(TBDY_BRITTLE_CHECK_SPEC, TS500_WEB_CHECK_SPEC),
)

__all__ = [
    "VE_RULE_ID",
    "TBDY_BRITTLE_RULE_ID",
    "TS500_WEB_RULE_ID",
    "VE_RULE_VERSION",
    "TBDY_BRITTLE_RULE_VERSION",
    "TS500_WEB_RULE_VERSION",
    "VE_CODE_REFS",
    "TBDY_BRITTLE_CODE_REF",
    "TS500_WEB_CODE_REF",
    "BOTTOM_CAPACITY_KNM_KEY",
    "TOP_CAPACITY_KNM_KEY",
    "FREE_LENGTH_MM_KEY",
    "D_AMPLIFIED_KN_KEY",
    "TBDY_VD_KN_KEY",
    "VE_KN_KEY",
    "COLUMN_WIDTH_MM_KEY",
    "COLUMN_DEPTH_MM_KEY",
    "CONCRETE_FCK_MPA_KEY",
    "TS500_VD_KN_KEY",
    "TS500_FCD_MPA_KEY",
    "EFFECTIVE_DEPTH_MM_KEY",
    "STORY_KEY",
    "SECTION_KEY",
    "EVIDENCE_TRACE_KEY",
    "ColumnShearP7ApplicabilityInput",
    "ColumnShearP7ExecutionInput",
    "tbdy_737_applicability",
    "ts500_815_applicability",
    "derive_tbdy_column_shear_ve",
    "evaluate_tbdy_column_shear_brittle_bound",
    "evaluate_ts500_column_shear_web_bound",
    "VE_DERIVATION_SPEC",
    "TBDY_BRITTLE_CHECK_SPEC",
    "TS500_WEB_CHECK_SPEC",
    "VS6_COLUMN_SHEAR_P7_REGISTRY",
]
