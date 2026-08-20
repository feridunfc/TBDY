"""F0.3 DAG-native concrete minimum-strength formal rule.

The accepted used-RC material population remains factual authority.  This module
owns only the frozen §7.2.5.1 minimum-strength regulatory decision and the
bounded compile adapter needed to expose those facts to the F0 DAG.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.features.used_rc_material_population import (
    ConcreteStrengthFactStatus,
    MaterialPopulationReadiness,
    UsedMaterialDefinition,
    UsedRcMaterialPopulation,
)
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
from tbdy_engine.regulatory.kernel import (
    ExternalDependencyAuthority,
    MaterializedDependency,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RuleExecutionEnvelope,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MPA

MIN_FCK_MPA = 25.0
MIN_CONCRETE_CLASS_LABEL = "C25"
RULE_VERSION = "f0.3-v1"
CODE_REF = "TBDY-2018-7.2.5.1"
RULE_ID = RuleId("CONCRETE_MATERIAL_MIN_STRENGTH")

REVIEWED_ETABS_CONCRETE_TYPE_CODE = 2
REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID = "CSI_ETABS_MATERIAL_TYPE_CODE_2_CONCRETE_V1"

USED_RC_MATERIAL_POPULATION_KEY = DependencyKey("used_rc_material_population")
CONCRETE_FCK_KEY = DependencyKey("concrete_fck_mpa")
MATERIAL_NAME_KEY = DependencyKey("material_name")
MATERIAL_EVIDENCE_TRACE_KEY = DependencyKey("material_evidence_trace")


@dataclass(frozen=True, slots=True)
class ConcreteMaterialMinStrengthApplicabilityInput:
    material_type_code: int
    is_concrete: bool
    api_semantic_binding_id: str

    def __post_init__(self) -> None:
        if isinstance(self.material_type_code, bool) or not isinstance(self.material_type_code, int):
            raise TypeError("material_type_code must be int")
        if not isinstance(self.is_concrete, bool):
            raise TypeError("is_concrete must be bool")
        if not isinstance(self.api_semantic_binding_id, str) or not self.api_semantic_binding_id.strip():
            raise ValueError("api_semantic_binding_id must be a nonblank string")


def concrete_material_min_strength_applicability(
    value: ConcreteMaterialMinStrengthApplicabilityInput,
) -> ApplicabilityState:
    if value.api_semantic_binding_id != REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID:
        return ApplicabilityState.INVALID_CONTEXT
    code_is_concrete = value.material_type_code == REVIEWED_ETABS_CONCRETE_TYPE_CODE
    if code_is_concrete and value.is_concrete:
        return ApplicabilityState.APPLIES
    if not code_is_concrete and not value.is_concrete:
        return ApplicabilityState.PROVEN_NOT_APPLICABLE
    return ApplicabilityState.INVALID_CONTEXT


@dataclass(frozen=True, slots=True)
class ConcreteMaterialMinStrengthExecutionInput:
    envelope: RuleExecutionEnvelope
    material_id: str
    canonical_fck_mpa: float
    material_name: str
    evidence: tuple[object, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ConcreteMaterialMinStrengthExecutionInput":
        deps = tuple(dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("concrete material execution requires MaterializedDependency inputs")
        by_key = {item.key: item for item in deps}
        expected = {
            USED_RC_MATERIAL_POPULATION_KEY,
            CONCRETE_FCK_KEY,
            MATERIAL_NAME_KEY,
            MATERIAL_EVIDENCE_TRACE_KEY,
        }
        if len(by_key) != len(deps) or set(by_key) != expected:
            raise ValueError("concrete material execution received unexpected dependency keys")

        fck = by_key[CONCRETE_FCK_KEY].value
        if isinstance(fck, bool) or not isinstance(fck, (int, float)):
            raise TypeError("concrete_fck_mpa must be a numeric scalar")
        fck_value = float(fck)
        if not math.isfinite(fck_value):
            raise ValueError("concrete_fck_mpa must be finite")

        material_name = by_key[MATERIAL_NAME_KEY].value
        if not isinstance(material_name, str) or not material_name.strip():
            raise TypeError("material_name must be a resolved nonblank string")

        evidence = by_key[MATERIAL_EVIDENCE_TRACE_KEY].value
        if not isinstance(evidence, tuple):
            raise TypeError("material_evidence_trace must materialize as an immutable tuple")

        return cls(
            envelope=envelope,
            material_id=envelope.instance_id.scope_ref,
            canonical_fck_mpa=fck_value,
            material_name=material_name,
            evidence=tuple(evidence),
        )


def evaluate_concrete_material_min_strength(
    inp: ConcreteMaterialMinStrengthExecutionInput,
) -> CheckResult:
    fck = inp.canonical_fck_mpa
    is_satisfied = fck >= MIN_FCK_MPA
    ratio = fck / MIN_FCK_MPA
    return CheckResult(
        check_id=RULE_ID.value,
        component=inp.material_id,
        component_type="material_definition",
        story=None,
        section=None,
        status=CheckStatus.OK if is_satisfied else CheckStatus.FAIL,
        value=fck,
        limit=MIN_FCK_MPA,
        demand=None,
        capacity=None,
        ratio=ratio,
        ratio_type="actual_over_minimum",
        pass_rule="actual_over_minimum",
        unit="MPa",
        evaluation_level=EvaluationLevel.DESIGN_LEVEL,
        evidence=inp.evidence,
        messages=("Formal TBDY concrete material minimum-strength CheckResult",),
        code_ref=CODE_REF,
        diagnostics=(),
    )


CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES = (
    DependencySpec(
        key=USED_RC_MATERIAL_POPULATION_KEY,
        source_kind=DependencySourceKind.SOURCE_POPULATION,
        semantic_type=SemanticType.USED_RC_MATERIAL_POPULATION,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.MODEL,
        scope_policy=ScopePolicy.GLOBAL_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_ENUM_STATE,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.FULL,
    ),
    DependencySpec(
        key=CONCRETE_FCK_KEY,
        source_kind=DependencySourceKind.FACT,
        semantic_type=SemanticType.CONCRETE_FCK,
        physical_dimension=PhysicalDimension.STRESS,
        grain=Grain.MATERIAL_DEFINITION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_MPA,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    ),
    DependencySpec(
        key=MATERIAL_NAME_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.MATERIAL_NAME,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.MATERIAL_DEFINITION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_ENUM_STATE,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    ),
    DependencySpec(
        key=MATERIAL_EVIDENCE_TRACE_KEY,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.MATERIAL_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.MATERIAL_DEFINITION,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=UNIT_DIMENSIONLESS,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=PopulationRequirement.ANY_RESOLVED,
    ),
)

CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC = CheckSpec(
    rule_id=RULE_ID,
    code_refs=(CODE_REF,),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES,
    applicability=ApplicabilityBinding(
        "f0.3:concrete_material_min_strength:applicability",
        ConcreteMaterialMinStrengthApplicabilityInput,
        concrete_material_min_strength_applicability,
    ),
    evaluator=CheckEvaluatorBinding(
        "f0.3:concrete_material_min_strength:evaluator",
        ConcreteMaterialMinStrengthExecutionInput,
        evaluate_concrete_material_min_strength,
    ),
)

F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY = RegulatoryRegistry(
    checks=(CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC,)
)


def _population_completeness(readiness: MaterialPopulationReadiness) -> PopulationCompleteness:
    return (
        PopulationCompleteness.FULL
        if readiness is MaterialPopulationReadiness.COMPLETE
        else PopulationCompleteness.INCOMPLETE
    )


def _population_availability(readiness: MaterialPopulationReadiness) -> AvailabilityState:
    return (
        AvailabilityState.BLOCKED
        if readiness is MaterialPopulationReadiness.BLOCKED
        else AvailabilityState.RESOLVED
    )


def _fck_authority_state(
    material: UsedMaterialDefinition,
) -> tuple[AvailabilityState, float | None]:
    if not material.is_concrete:
        if material.concrete_strength_status is ConcreteStrengthFactStatus.NOT_APPLICABLE:
            return AvailabilityState.NOT_APPLICABLE, None
        return AvailabilityState.BLOCKED, None
    value = material.canonical_fck_mpa
    if (
        material.concrete_strength_status is ConcreteStrengthFactStatus.RESOLVED
        and not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    ):
        return AvailabilityState.RESOLVED, float(value)
    return AvailabilityState.BLOCKED, None


def _usage_evidence(material: UsedMaterialDefinition) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "usage_id": item.usage_id,
            "component_type": item.component_type,
            "component_identity": item.component_identity,
            "story": item.story,
            "label": item.label,
            "assigned_property": item.assigned_property,
            "material_name": item.material_name,
            "material_type_code": item.material_type_code,
            "status": item.status.value,
        }
        for item in sorted(material.usage_references, key=lambda x: x.usage_id)
    )


def _diagnostic_evidence(material: UsedMaterialDefinition) -> tuple[dict[str, object], ...]:
    ordered = sorted(
        material.diagnostics,
        key=lambda item: (
            item.code,
            item.domain or "",
            item.component_identity or "",
            item.material_name or "",
            item.message,
        ),
    )
    return tuple(
        {
            "code": item.code,
            "message": item.message,
            "domain": item.domain,
            "component_identity": item.component_identity,
            "material_name": item.material_name,
            "source_api": item.source_api,
        }
        for item in ordered
    )


def _unit_context_evidence(material: UsedMaterialDefinition) -> dict[str, object] | None:
    context = material.unit_context
    if context is None:
        return None
    return {
        "present_force_unit_code": context.present_force_unit_code,
        "present_length_unit_code": context.present_length_unit_code,
        "source_api": context.source_api,
    }


def _source_binding_evidence(population: UsedRcMaterialPopulation) -> dict[str, object] | None:
    binding = population.source_binding
    if binding is None:
        return None
    return {
        "binding_method": binding.binding_method,
        "model_full_path": binding.model_full_path,
        "process_id": binding.process_id,
        "attach_strategy": binding.attach_strategy,
        "program_version": binding.program_version,
        "inventory_identity_namespace": binding.inventory_identity_namespace,
    }


def _material_evidence(
    population: UsedRcMaterialPopulation,
    material: UsedMaterialDefinition,
) -> tuple[dict[str, object], ...]:
    payload: dict[str, object] = {
        "material_id": material.material_id,
        "material_name": material.material_name,
        "model_fingerprint": material.model_fingerprint,
        "material_type_code": material.material_type_code,
        "is_concrete": material.is_concrete,
        "canonical_fck_mpa": material.canonical_fck_mpa,
        "concrete_strength_status": material.concrete_strength_status.value,
        "unit_context": _unit_context_evidence(material),
        "usage_references": _usage_evidence(material),
        "diagnostics": _diagnostic_evidence(material),
    }
    source_binding = _source_binding_evidence(population)
    if source_binding is not None:
        payload["source_binding"] = source_binding
    return (payload,)


def build_concrete_material_min_strength_compile_inputs(
    population: UsedRcMaterialPopulation,
) -> RegulatoryCompileInputs:
    if not isinstance(population, UsedRcMaterialPopulation):
        raise TypeError("population must be UsedRcMaterialPopulation")
    if not isinstance(population.readiness, MaterialPopulationReadiness):
        raise TypeError("population readiness must be MaterialPopulationReadiness")

    definitions = tuple(population.used_material_definitions)
    if not definitions:
        raise ValueError("used-RC material population is empty; regulatory closure cannot be manufactured")
    if any(not isinstance(item, UsedMaterialDefinition) for item in definitions):
        raise TypeError("used_material_definitions must contain UsedMaterialDefinition")
    material_ids = tuple(item.material_id for item in definitions)
    if any(not isinstance(item, str) or not item.strip() for item in material_ids):
        raise ValueError("every used material definition requires a nonblank material_id")
    if len(set(material_ids)) != len(material_ids):
        raise ValueError("duplicate material_id in used-RC material population")

    ordered = tuple(sorted(definitions, key=lambda item: item.material_id))
    population_ref = f"used_rc_material_population:{population.model_fingerprint}"
    authorities: list[ExternalDependencyAuthority] = [
        ExternalDependencyAuthority(
            authority_id=f"f0.3:population:{population.model_fingerprint}",
            key=USED_RC_MATERIAL_POPULATION_KEY,
            source_kind=DependencySourceKind.SOURCE_POPULATION,
            semantic_type=SemanticType.USED_RC_MATERIAL_POPULATION,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.MODEL,
            scope_ref="MODEL",
            direction=None,
            unit=UNIT_ENUM_STATE,
            availability=_population_availability(population.readiness),
            population_completeness=_population_completeness(population.readiness),
            value=population.readiness.value,
            provenance_refs=(population_ref,),
        )
    ]
    targets: list[RuleScopeTarget] = []

    for material in ordered:
        if not isinstance(material.material_name, str) or not material.material_name.strip():
            raise ValueError(f"material {material.material_id!r} requires a nonblank material_name")
        fck_availability, fck_value = _fck_authority_state(material)
        material_ref = f"material_definition:{material.material_id}"
        evidence = _material_evidence(population, material)

        targets.append(
            RuleScopeTarget(
                rule_id=RULE_ID,
                grain=Grain.MATERIAL_DEFINITION,
                scope_ref=material.material_id,
                direction=None,
                applicability_input=ConcreteMaterialMinStrengthApplicabilityInput(
                    material_type_code=material.material_type_code,
                    is_concrete=material.is_concrete,
                    api_semantic_binding_id=REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID,
                ),
            )
        )
        authorities.extend(
            (
                ExternalDependencyAuthority(
                    authority_id=f"f0.3:fck:{material.material_id}",
                    key=CONCRETE_FCK_KEY,
                    source_kind=DependencySourceKind.FACT,
                    semantic_type=SemanticType.CONCRETE_FCK,
                    physical_dimension=PhysicalDimension.STRESS,
                    grain=Grain.MATERIAL_DEFINITION,
                    scope_ref=material.material_id,
                    direction=None,
                    unit=UNIT_MPA,
                    availability=fck_availability,
                    population_completeness=PopulationCompleteness.FULL,
                    value=fck_value,
                    provenance_refs=(material_ref, f"{material_ref}:canonical_fck_mpa"),
                ),
                ExternalDependencyAuthority(
                    authority_id=f"f0.3:name:{material.material_id}",
                    key=MATERIAL_NAME_KEY,
                    source_kind=DependencySourceKind.CONTEXT,
                    semantic_type=SemanticType.MATERIAL_NAME,
                    physical_dimension=PhysicalDimension.ENUM_STATE,
                    grain=Grain.MATERIAL_DEFINITION,
                    scope_ref=material.material_id,
                    direction=None,
                    unit=UNIT_ENUM_STATE,
                    availability=AvailabilityState.RESOLVED,
                    population_completeness=PopulationCompleteness.FULL,
                    value=material.material_name,
                    provenance_refs=(material_ref, f"{material_ref}:material_name"),
                ),
                ExternalDependencyAuthority(
                    authority_id=f"f0.3:evidence:{material.material_id}",
                    key=MATERIAL_EVIDENCE_TRACE_KEY,
                    source_kind=DependencySourceKind.CONTEXT,
                    semantic_type=SemanticType.MATERIAL_EVIDENCE_TRACE,
                    physical_dimension=PhysicalDimension.DIMENSIONLESS,
                    grain=Grain.MATERIAL_DEFINITION,
                    scope_ref=material.material_id,
                    direction=None,
                    unit=UNIT_DIMENSIONLESS,
                    availability=AvailabilityState.RESOLVED,
                    population_completeness=PopulationCompleteness.FULL,
                    value=evidence,
                    provenance_refs=(material_ref, f"{material_ref}:evidence"),
                ),
            )
        )

    return RegulatoryCompileInputs(rule_targets=targets, external_authorities=authorities)


__all__ = [
    "MIN_FCK_MPA",
    "MIN_CONCRETE_CLASS_LABEL",
    "RULE_VERSION",
    "CODE_REF",
    "RULE_ID",
    "REVIEWED_ETABS_CONCRETE_TYPE_CODE",
    "REVIEWED_ETABS_MATERIAL_TYPE_BINDING_ID",
    "USED_RC_MATERIAL_POPULATION_KEY",
    "CONCRETE_FCK_KEY",
    "MATERIAL_NAME_KEY",
    "MATERIAL_EVIDENCE_TRACE_KEY",
    "ConcreteMaterialMinStrengthApplicabilityInput",
    "ConcreteMaterialMinStrengthExecutionInput",
    "concrete_material_min_strength_applicability",
    "evaluate_concrete_material_min_strength",
    "CONCRETE_MATERIAL_MIN_STRENGTH_DEPENDENCIES",
    "CONCRETE_MATERIAL_MIN_STRENGTH_CHECK_SPEC",
    "F0_3_CONCRETE_MATERIAL_MIN_STRENGTH_REGISTRY",
    "build_concrete_material_min_strength_compile_inputs",
]
