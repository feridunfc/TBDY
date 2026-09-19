"""F0.9 source-bound TBDY 2018 §7.7.5.2 limited-column shear upper bound.

This authority is deliberately separate from high-ductility §7.3.7 P7 Ve.
It consumes an exact reviewed §7.7.5.1 design Vd fact and executes only the
§7.7.5.2 Eq.(7.7) upper-bound verdict through the canonical F0 kernel.
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
from tbdy_engine.regulatory.units import (
    UNIT_DIMENSIONLESS,
    UNIT_ENUM_STATE,
    UNIT_KN,
    UNIT_MM,
    UNIT_MPA,
)

LIMITED_BRITTLE_RULE_ID = RuleId(
    "TBDY_7_7_5_2_COLUMN_SHEAR_BRITTLE_BOUND"
)
LIMITED_BRITTLE_RULE_VERSION = "column-r1-a37-limited-7752-v1"
LIMITED_BRITTLE_CODE_REF = "TBDY 2018 7.7.5.2 / Eq. (7.7)"

LIMITED_VD_KN_KEY = DependencyKey(
    "column_limited_shear_d_amplified_vertical_plus_earthquake_vd_kn"
)
COLUMN_WIDTH_MM_KEY = DependencyKey("column_width_mm")
COLUMN_DEPTH_MM_KEY = DependencyKey("column_depth_mm")
CONCRETE_FCK_MPA_KEY = DependencyKey("concrete_fck_mpa")
STORY_KEY = DependencyKey("story")
SECTION_KEY = DependencyKey("section")
EVIDENCE_TRACE_KEY = DependencyKey(
    "column_limited_shear_evidence_trace"
)


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise TypeError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and >= 0")
    return result


@dataclass(frozen=True, slots=True)
class ColumnShearLimitedApplicabilityInput:
    component_type: str
    reinforced_concrete: bool | None
    limited_ductility_applies: bool | None

    def __post_init__(self) -> None:
        _text(self.component_type, "component_type")
        for name in (
            "reinforced_concrete",
            "limited_ductility_applies",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(
                    f"{name} must be bool or None"
                )


def limited_775_applicability(
    value: ColumnShearLimitedApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(
        value,
        ColumnShearLimitedApplicabilityInput,
    ):
        raise TypeError(
            "limited applicability requires "
            "ColumnShearLimitedApplicabilityInput"
        )
    if value.component_type.casefold() != "column":
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.reinforced_concrete is None:
        return ApplicabilityState.UNRESOLVED
    if value.reinforced_concrete is False:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    if value.limited_ductility_applies is None:
        return ApplicabilityState.UNRESOLVED
    return (
        ApplicabilityState.APPLIES
        if value.limited_ductility_applies
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


@dataclass(frozen=True, slots=True)
class ColumnShearLimitedExecutionInput:
    envelope: RuleExecutionEnvelope
    dependencies: tuple[MaterializedDependency, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ColumnShearLimitedExecutionInput":
        deps = tuple(dependencies)
        if any(
            not isinstance(item, MaterializedDependency)
            for item in deps
        ):
            raise TypeError(
                "dependencies must contain MaterializedDependency"
            )
        if len({item.key for item in deps}) != len(deps):
            raise ValueError(
                "duplicate limited-shear declared dependency"
            )
        return cls(
            envelope=envelope,
            dependencies=deps,
        )

    def one(
        self,
        key: DependencyKey,
    ) -> MaterializedDependency:
        for item in self.dependencies:
            if item.key == key:
                return item
        raise KeyError(
            f"missing limited-shear dependency: {key.value}"
        )

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


def evaluate_limited_column_shear_brittle_bound(
    inp: ColumnShearLimitedExecutionInput,
) -> CheckResult:
    vd_kn = _nonnegative(
        inp.value(LIMITED_VD_KN_KEY),
        "limited_d_amplified_vd_kn",
    )
    width_mm = _positive(
        inp.value(COLUMN_WIDTH_MM_KEY),
        "column_width_mm",
    )
    depth_mm = _positive(
        inp.value(COLUMN_DEPTH_MM_KEY),
        "column_depth_mm",
    )
    fck_mpa = _positive(
        inp.value(CONCRETE_FCK_MPA_KEY),
        "concrete_fck_mpa",
    )
    story = _text(inp.value(STORY_KEY), "story")
    section = _text(inp.value(SECTION_KEY), "section")

    # §7.7.5.2 imports Eq.(7.7), but substitutes the
    # D-amplified limited-column Vd for high-ductility Ve.
    aw_mm2 = width_mm * depth_mm
    limit_kn = (
        0.85
        * aw_mm2
        * math.sqrt(fck_mpa)
        / 1000.0
    )
    ratio = vd_kn / limit_kn
    satisfied = vd_kn <= limit_kn

    return CheckResult(
        check_id=LIMITED_BRITTLE_RULE_ID.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="column",
        story=story,
        section=section,
        status=(
            CheckStatus.OK
            if satisfied
            else CheckStatus.FAIL
        ),
        value=vd_kn,
        limit=limit_kn,
        demand=vd_kn,
        capacity=limit_kn,
        ratio=ratio,
        ratio_type="demand_over_capacity",
        pass_rule=(
            "D-amplified limited Vd "
            "<= 0.85 * Aw * sqrt(fck)"
        ),
        unit="kN",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence_refs,
        messages=(
            (
                "TBDY_7_7_5_2_EQ7_7_BRITTLE_SATISFIED"
                if satisfied
                else
                "TBDY_7_7_5_2_EQ7_7_BRITTLE_NOT_"
                "SATISFIED_SECTION_ENLARGEMENT_AND_"
                "REANALYSIS_REQUIRED"
            ),
        ),
        code_ref=LIMITED_BRITTLE_CODE_REF,
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
        population_completeness_requirement=(
            PopulationRequirement.FULL
        ),
    )


LIMITED_VD_DEP = _dep(
    LIMITED_VD_KN_KEY,
    source_kind=(
        DependencySourceKind.SELECTED_SOURCE_QUANTITY
    ),
    semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
    dimension=PhysicalDimension.FORCE,
    grain=Grain.COMPONENT_DIRECTION,
    direction_policy=DirectionPolicy.SAME_DIRECTION,
    unit=UNIT_KN,
)
WIDTH_DEP = _dep(
    COLUMN_WIDTH_MM_KEY,
    source_kind=DependencySourceKind.FACT,
    semantic_type=SemanticType.COLUMN_WIDTH,
    dimension=PhysicalDimension.LENGTH,
    grain=Grain.COMPONENT,
    direction_policy=DirectionPolicy.NO_DIRECTION,
    unit=UNIT_MM,
)
DEPTH_DEP = _dep(
    COLUMN_DEPTH_MM_KEY,
    source_kind=DependencySourceKind.FACT,
    semantic_type=SemanticType.COLUMN_DEPTH,
    dimension=PhysicalDimension.LENGTH,
    grain=Grain.COMPONENT,
    direction_policy=DirectionPolicy.NO_DIRECTION,
    unit=UNIT_MM,
)
FCK_DEP = _dep(
    CONCRETE_FCK_MPA_KEY,
    source_kind=DependencySourceKind.FACT,
    semantic_type=SemanticType.CONCRETE_FCK,
    dimension=PhysicalDimension.STRESS,
    grain=Grain.COMPONENT,
    direction_policy=DirectionPolicy.NO_DIRECTION,
    unit=UNIT_MPA,
)
STORY_DEP = _dep(
    STORY_KEY,
    source_kind=DependencySourceKind.CONTEXT,
    semantic_type=SemanticType.COMPONENT_STORY,
    dimension=PhysicalDimension.ENUM_STATE,
    grain=Grain.COMPONENT,
    direction_policy=DirectionPolicy.NO_DIRECTION,
    unit=UNIT_ENUM_STATE,
)
SECTION_DEP = _dep(
    SECTION_KEY,
    source_kind=DependencySourceKind.CONTEXT,
    semantic_type=SemanticType.COMPONENT_SECTION,
    dimension=PhysicalDimension.ENUM_STATE,
    grain=Grain.COMPONENT,
    direction_policy=DirectionPolicy.NO_DIRECTION,
    unit=UNIT_ENUM_STATE,
)
EVIDENCE_DEP = _dep(
    EVIDENCE_TRACE_KEY,
    source_kind=DependencySourceKind.CONTEXT,
    semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
    dimension=PhysicalDimension.DIMENSIONLESS,
    grain=Grain.COMPONENT_DIRECTION,
    direction_policy=DirectionPolicy.SAME_DIRECTION,
    unit=UNIT_DIMENSIONLESS,
)

LIMITED_APPLICABILITY = ApplicabilityBinding(
    "column-r1-a37:tbdy-775:applicability",
    ColumnShearLimitedApplicabilityInput,
    limited_775_applicability,
)

LIMITED_BRITTLE_CHECK_SPEC = CheckSpec(
    rule_id=LIMITED_BRITTLE_RULE_ID,
    code_refs=(LIMITED_BRITTLE_CODE_REF,),
    rule_version=LIMITED_BRITTLE_RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(
        LIMITED_VD_DEP,
        WIDTH_DEP,
        DEPTH_DEP,
        FCK_DEP,
        STORY_DEP,
        SECTION_DEP,
        EVIDENCE_DEP,
    ),
    applicability=LIMITED_APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        "column-r1-a37:tbdy-7752:brittle-bound",
        ColumnShearLimitedExecutionInput,
        evaluate_limited_column_shear_brittle_bound,
    ),
)

COLUMN_SHEAR_LIMITED_775_REGISTRY = RegulatoryRegistry(
    checks=(LIMITED_BRITTLE_CHECK_SPEC,),
)

__all__ = [
    "COLUMN_DEPTH_MM_KEY",
    "COLUMN_SHEAR_LIMITED_775_REGISTRY",
    "COLUMN_WIDTH_MM_KEY",
    "CONCRETE_FCK_MPA_KEY",
    "EVIDENCE_TRACE_KEY",
    "LIMITED_BRITTLE_CHECK_SPEC",
    "LIMITED_BRITTLE_CODE_REF",
    "LIMITED_BRITTLE_RULE_ID",
    "LIMITED_BRITTLE_RULE_VERSION",
    "LIMITED_VD_KN_KEY",
    "SECTION_KEY",
    "STORY_KEY",
    "ColumnShearLimitedApplicabilityInput",
    "ColumnShearLimitedExecutionInput",
    "evaluate_limited_column_shear_brittle_bound",
    "limited_775_applicability",
]
