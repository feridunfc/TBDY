"""Frozen F0.0 semantic and immutable regulatory contracts only."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, TypeVar

from tbdy_engine.checks.result import CheckResult

if TYPE_CHECKING:
    from .units import Unit

_T = TypeVar("_T")


def _nonblank(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonblank string")
    return value


def _canonical_identifier(value: str, label: str) -> str:
    _nonblank(value, label)
    if value != value.strip():
        raise ValueError(f"{label} must not contain leading or trailing whitespace")
    return value


def _rule_instance_value(
    *, rule_id: "RuleId", grain: "Grain", scope_ref: str, direction: str | None
) -> str:
    return json.dumps(
        [rule_id.value, grain.value, scope_ref, direction],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _freeze_regulatory_payload(value: object, label: str) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if type(value) in (dict, MappingProxyType):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{label} mapping keys must be strings")
            frozen[key] = _freeze_regulatory_payload(item, label)
        return MappingProxyType(frozen)
    if type(value) in (list, tuple):
        return tuple(_freeze_regulatory_payload(item, label) for item in value)
    if type(value) in (set, frozenset):
        return frozenset(_freeze_regulatory_payload(item, label) for item in value)
    raise TypeError(f"{label} contains unsupported payload type: {type(value).__name__}")


def _strings(values: tuple[str, ...] | list[str], label: str) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise TypeError(f"{label} values must be a tuple or list of strings")
    frozen = tuple(values)
    for value in frozen:
        if not isinstance(value, str):
            raise TypeError(f"{label} values must contain strings only")
        _nonblank(value, label)
    return frozen


def _typed_tuple(values: tuple[_T, ...] | list[_T], expected: type[_T], label: str) -> tuple[_T, ...]:
    frozen = tuple(values)
    if not all(isinstance(value, expected) for value in frozen):
        raise TypeError(f"{label} must contain {expected.__name__}")
    return frozen


@dataclass(frozen=True, slots=True, order=True)
class RuleId:
    value: str

    def __post_init__(self) -> None:
        _canonical_identifier(self.value, "RuleId")

    def __str__(self) -> str:
        return self.value


class Grain(StrEnum):
    MODEL = "MODEL"
    STRUCTURAL_ZONE = "STRUCTURAL_ZONE"
    DIRECTION = "DIRECTION"
    STORY = "STORY"
    COMPONENT = "COMPONENT"
    COMPONENT_DIRECTION = "COMPONENT_DIRECTION"
    COMPONENT_END = "COMPONENT_END"
    COMPONENT_END_DIRECTION = "COMPONENT_END_DIRECTION"
    MATERIAL_DEFINITION = "MATERIAL_DEFINITION"


class SemanticType(StrEnum):
    """Small neutral F0 vocabulary; future additions require code review."""

    TOY_INPUT = "TOY_INPUT"
    TOY_DERIVED_STATE = "TOY_DERIVED_STATE"
    TOY_RESULT = "TOY_RESULT"
    BEAM_WIDTH = "BEAM_WIDTH"
    COMPONENT_STORY = "COMPONENT_STORY"
    COMPONENT_SECTION = "COMPONENT_SECTION"
    CHECK_EVIDENCE_TRACE = "CHECK_EVIDENCE_TRACE"
    CONCRETE_FCK = "CONCRETE_FCK"
    BEAM_DEPTH = "BEAM_DEPTH"
    COLUMN_WIDTH = "COLUMN_WIDTH"
    COLUMN_DEPTH = "COLUMN_DEPTH"
    WALL_LENGTH = "WALL_LENGTH"
    WALL_THICKNESS = "WALL_THICKNESS"
    WALL_STORY_HEIGHT = "WALL_STORY_HEIGHT"
    WALL_UNRESTRAINED_PLAN_LENGTH = "WALL_UNRESTRAINED_PLAN_LENGTH"
    MODAL_CUMULATIVE_EFFECTIVE_MASS_RATIO = "MODAL_CUMULATIVE_EFFECTIVE_MASS_RATIO"
    TORSIONAL_IRREGULARITY_COEFFICIENT = "TORSIONAL_IRREGULARITY_COEFFICIENT"
    RC_TABLE_4_1_ROW = "RC_TABLE_4_1_ROW"
    RC_DTS = "RC_DTS"
    RC_BYS = "RC_BYS"
    RC_DUCTILITY_CLASS = "RC_DUCTILITY_CLASS"
    RC_BASE_R = "RC_BASE_R"
    RC_BASE_D = "RC_BASE_D"
    RC_BYS_POLICY = "RC_BYS_POLICY"
    RC_POST_ANALYSIS_QUALIFICATION_REQUIREMENT = "RC_POST_ANALYSIS_QUALIFICATION_REQUIREMENT"
    RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY = "RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY"
    RC_ORTHOGONAL_SYSTEM_DECLARATION = "RC_ORTHOGONAL_SYSTEM_DECLARATION"
    RC_A16_SPECIAL_CONTEXT = "RC_A16_SPECIAL_CONTEXT"
    RC_ANALYSIS_SYSTEM_ASSUMPTION = "RC_ANALYSIS_SYSTEM_ASSUMPTION"
    RC_ANALYSIS_BASIS_STATUS = "RC_ANALYSIS_BASIS_STATUS"


class PhysicalDimension(StrEnum):
    FORCE = "FORCE"
    MOMENT = "MOMENT"
    STRESS = "STRESS"
    AREA = "AREA"
    LENGTH = "LENGTH"
    DIMENSIONLESS = "DIMENSIONLESS"
    BOOLEAN_STATE = "BOOLEAN_STATE"
    ENUM_STATE = "ENUM_STATE"


@dataclass(frozen=True, slots=True, order=True)
class DependencyKey:
    value: str

    def __post_init__(self) -> None:
        _canonical_identifier(self.value, "DependencyKey")

    def __str__(self) -> str:
        return self.value


class DependencySourceKind(StrEnum):
    FACT = "FACT"
    SOURCE_POPULATION = "SOURCE_POPULATION"
    SELECTED_SOURCE_QUANTITY = "SELECTED_SOURCE_QUANTITY"
    REGULATORY_QUANTITY = "REGULATORY_QUANTITY"
    CONTEXT = "CONTEXT"


class ScopePolicy(StrEnum):
    EXACT_SCOPE = "EXACT_SCOPE"
    SAME_SCOPE = "SAME_SCOPE"
    GLOBAL_SCOPE = "GLOBAL_SCOPE"


class DirectionPolicy(StrEnum):
    EXACT_DIRECTION = "EXACT_DIRECTION"
    SAME_DIRECTION = "SAME_DIRECTION"
    ANY_DIRECTION = "ANY_DIRECTION"
    NO_DIRECTION = "NO_DIRECTION"


class ApplicabilityState(StrEnum):
    APPLIES = "APPLIES"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"
    INVALID_CONTEXT = "INVALID_CONTEXT"


class AvailabilityState(StrEnum):
    RESOLVED = "RESOLVED"
    BLOCKED = "BLOCKED"
    NO_DATA = "NO_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PopulationRequirement(StrEnum):
    ANY_RESOLVED = "ANY_RESOLVED"
    FULL = "FULL"


class ClosureExecutionStatus(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"
    EXECUTED = "EXECUTED"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"
    BLOCKED = "BLOCKED"
    NO_DATA = "NO_DATA"
    MISSING = "MISSING"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class RuleInstanceId:
    rule_id: RuleId
    grain: Grain
    scope_ref: str
    direction: str | None
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, RuleId) or not isinstance(self.grain, Grain):
            raise TypeError("RuleInstanceId requires typed rule_id and grain")
        _nonblank(self.scope_ref, "scope_ref")
        if self.direction is not None:
            _nonblank(self.direction, "direction")
        _nonblank(self.value, "RuleInstanceId")
        expected = _rule_instance_value(
            rule_id=self.rule_id, grain=self.grain, scope_ref=self.scope_ref, direction=self.direction
        )
        if self.value != expected:
            raise ValueError("RuleInstanceId value must match deterministic canonical construction")

    @classmethod
    def build(
        cls,
        *,
        rule_id: RuleId,
        grain: Grain,
        scope_ref: str,
        direction: str | None = None,
    ) -> "RuleInstanceId":
        _nonblank(scope_ref, "scope_ref")
        if direction is not None:
            _nonblank(direction, "direction")
        return cls(
            rule_id=rule_id,
            grain=grain,
            scope_ref=scope_ref,
            direction=direction,
            value=_rule_instance_value(
                rule_id=rule_id, grain=grain, scope_ref=scope_ref, direction=direction
            ),
        )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DependencySpec:
    key: DependencyKey
    source_kind: DependencySourceKind
    semantic_type: SemanticType
    physical_dimension: PhysicalDimension
    grain: Grain
    scope_policy: ScopePolicy
    direction_policy: DirectionPolicy
    unit_requirement: Unit
    required_availability: AvailabilityState = AvailabilityState.RESOLVED
    population_completeness_requirement: PopulationRequirement = PopulationRequirement.ANY_RESOLVED

    def __post_init__(self) -> None:
        required_types = (
            (self.key, DependencyKey),
            (self.source_kind, DependencySourceKind),
            (self.semantic_type, SemanticType),
            (self.physical_dimension, PhysicalDimension),
            (self.grain, Grain),
            (self.scope_policy, ScopePolicy),
            (self.direction_policy, DirectionPolicy),
            (self.required_availability, AvailabilityState),
            (self.population_completeness_requirement, PopulationRequirement),
        )
        if not all(isinstance(value, expected) for value, expected in required_types):
            raise TypeError("DependencySpec requires bounded typed contract values")
        from .units import Unit
        if not isinstance(self.unit_requirement, Unit):
            raise TypeError("unit_requirement must be Unit")
        if self.unit_requirement.physical_dimension is not self.physical_dimension:
            raise ValueError("unit_requirement physical dimension mismatch")


@dataclass(frozen=True, slots=True)
class RegulatoryOutputContract:
    authority_key: DependencyKey
    semantic_type: SemanticType
    physical_dimension: PhysicalDimension
    grain: Grain
    unit: Unit

    def __post_init__(self) -> None:
        if not isinstance(self.authority_key, DependencyKey):
            raise TypeError("authority_key must be DependencyKey")
        if not isinstance(self.semantic_type, SemanticType):
            raise TypeError("semantic_type must be SemanticType")
        if not isinstance(self.physical_dimension, PhysicalDimension) or not isinstance(self.grain, Grain):
            raise TypeError("output contract requires typed dimension and grain")
        from .units import Unit
        if not isinstance(self.unit, Unit):
            raise TypeError("unit must be Unit")
        if self.unit.physical_dimension is not self.physical_dimension:
            raise ValueError("output unit physical dimension mismatch")


@dataclass(frozen=True, slots=True)
class RegulatoryQuantity:
    quantity_key: DependencyKey
    producer_instance_id: RuleInstanceId
    semantic_type: SemanticType
    physical_dimension: PhysicalDimension
    grain: Grain
    scope_ref: str
    direction: str | None
    value: object
    unit: Unit
    availability: AvailabilityState
    rule_version: str
    code_refs: tuple[str, ...] = field(default_factory=tuple)
    dependency_refs: tuple[DependencyKey, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance: object = field(default_factory=tuple)
    derivation_trace: object = field(default_factory=tuple)
    governing_trace: object = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.quantity_key, DependencyKey) or not isinstance(self.producer_instance_id, RuleInstanceId):
            raise TypeError("RegulatoryQuantity requires typed quantity and producer identities")
        if not isinstance(self.semantic_type, SemanticType):
            raise TypeError("semantic_type must be SemanticType")
        if not isinstance(self.physical_dimension, PhysicalDimension) or not isinstance(self.grain, Grain):
            raise TypeError("RegulatoryQuantity requires typed dimension and grain")
        if not isinstance(self.availability, AvailabilityState):
            raise TypeError("availability must be AvailabilityState")
        _nonblank(self.scope_ref, "scope_ref")
        if self.direction is not None:
            _nonblank(self.direction, "direction")
        _nonblank(self.rule_version, "rule_version")
        from .units import Unit
        if not isinstance(self.unit, Unit):
            raise TypeError("unit must be Unit")
        if self.unit.physical_dimension is not self.physical_dimension:
            raise ValueError("unit physical dimension mismatch")
        object.__setattr__(self, "value", _freeze_regulatory_payload(self.value, "value"))
        object.__setattr__(self, "code_refs", _strings(self.code_refs, "code_ref"))
        object.__setattr__(self, "dependency_refs", _typed_tuple(self.dependency_refs, DependencyKey, "dependency_refs"))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_ref"))
        object.__setattr__(self, "provenance", _freeze_regulatory_payload(self.provenance, "provenance"))
        object.__setattr__(self, "derivation_trace", _freeze_regulatory_payload(self.derivation_trace, "derivation_trace"))
        object.__setattr__(self, "governing_trace", _freeze_regulatory_payload(self.governing_trace, "governing_trace"))


ApplicabilityCallable = Callable[[object], ApplicabilityState]
DerivationCallable = Callable[[object], RegulatoryQuantity]
CheckCallable = Callable[[object], CheckResult]


@dataclass(frozen=True, slots=True)
class ApplicabilityBinding:
    binding_id: str
    input_type: type
    evaluator: ApplicabilityCallable

    def __post_init__(self) -> None:
        _binding_validation(self.binding_id, self.input_type, self.evaluator, "applicability")


@dataclass(frozen=True, slots=True)
class DerivationEvaluatorBinding:
    binding_id: str
    input_type: type
    evaluator: DerivationCallable

    def __post_init__(self) -> None:
        _binding_validation(self.binding_id, self.input_type, self.evaluator, "derivation")


@dataclass(frozen=True, slots=True)
class CheckEvaluatorBinding:
    binding_id: str
    input_type: type
    evaluator: CheckCallable

    def __post_init__(self) -> None:
        _binding_validation(self.binding_id, self.input_type, self.evaluator, "check")


def _binding_validation(binding_id: str, input_type: type, evaluator: Callable[..., object], label: str) -> None:
    _nonblank(binding_id, f"{label} binding_id")
    if not isinstance(input_type, type):
        raise TypeError("input_type must be a type")
    if not callable(evaluator):
        raise TypeError(f"{label} evaluator must be callable")


def _dependencies(values: tuple[DependencySpec, ...] | list[DependencySpec]) -> tuple[DependencySpec, ...]:
    frozen = _typed_tuple(values, DependencySpec, "dependencies")
    keys = tuple(dep.key for dep in frozen)
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate DependencyKey within rule definition")
    return frozen


@dataclass(frozen=True, slots=True)
class RegulatoryDerivationSpec:
    rule_id: RuleId
    code_refs: tuple[str, ...]
    rule_version: str
    output_contract: RegulatoryOutputContract
    dependencies: tuple[DependencySpec, ...]
    applicability: ApplicabilityBinding
    evaluator: DerivationEvaluatorBinding

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, RuleId) or not isinstance(self.output_contract, RegulatoryOutputContract):
            raise TypeError("derivation spec requires typed rule and output contracts")
        if not isinstance(self.applicability, ApplicabilityBinding) or not isinstance(self.evaluator, DerivationEvaluatorBinding):
            raise TypeError("derivation spec requires typed bindings")
        _nonblank(self.rule_version, "rule_version")
        object.__setattr__(self, "code_refs", _strings(self.code_refs, "code_ref"))
        object.__setattr__(self, "dependencies", _dependencies(self.dependencies))


@dataclass(frozen=True, slots=True)
class CheckSpec:
    rule_id: RuleId
    code_refs: tuple[str, ...]
    rule_version: str
    formal_result_type: type[CheckResult]
    dependencies: tuple[DependencySpec, ...]
    applicability: ApplicabilityBinding
    evaluator: CheckEvaluatorBinding

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, RuleId):
            raise TypeError("rule_id must be RuleId")
        if self.formal_result_type is not CheckResult:
            raise ValueError("formal_result_type must be canonical CheckResult")
        if not isinstance(self.applicability, ApplicabilityBinding) or not isinstance(self.evaluator, CheckEvaluatorBinding):
            raise TypeError("check spec requires typed bindings")
        _nonblank(self.rule_version, "rule_version")
        object.__setattr__(self, "code_refs", _strings(self.code_refs, "code_ref"))
        object.__setattr__(self, "dependencies", _dependencies(self.dependencies))


@dataclass(frozen=True, slots=True)
class CompiledClosureRecord:
    instance_id: RuleInstanceId
    rule_id: RuleId
    grain: Grain
    scope_ref: str
    mandatory: bool
    applicability: ApplicabilityState
    declared_dependency_refs: tuple[DependencyKey, ...]
    code_refs: tuple[str, ...]
    rule_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, RuleInstanceId) or not isinstance(self.rule_id, RuleId):
            raise TypeError("closure record requires typed identities")
        if self.instance_id.rule_id != self.rule_id:
            raise ValueError("instance_id and rule_id mismatch")
        if not isinstance(self.grain, Grain):
            raise TypeError("grain must be Grain")
        _nonblank(self.scope_ref, "scope_ref")
        if self.instance_id.grain is not self.grain or self.instance_id.scope_ref != self.scope_ref:
            raise ValueError("closure identity fields must match instance_id")
        if not isinstance(self.mandatory, bool) or not isinstance(self.applicability, ApplicabilityState):
            raise TypeError("closure record requires typed mandatory/applicability fields")
        object.__setattr__(self, "declared_dependency_refs", _typed_tuple(self.declared_dependency_refs, DependencyKey, "declared_dependency_refs"))
        object.__setattr__(self, "code_refs", _strings(self.code_refs, "code_ref"))
        _nonblank(self.rule_version, "rule_version")


@dataclass(frozen=True, slots=True)
class RuleClosureOutcome:
    compiled_record_ref: RuleInstanceId
    execution_status: ClosureExecutionStatus
    formal_result_ref: str | None = None
    regulatory_quantity_refs: tuple[DependencyKey, ...] = field(default_factory=tuple)
    diagnostic_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.compiled_record_ref, RuleInstanceId) or not isinstance(self.execution_status, ClosureExecutionStatus):
            raise TypeError("closure outcome requires typed record/status")
        if self.formal_result_ref is not None:
            _nonblank(self.formal_result_ref, "formal_result_ref")
        object.__setattr__(self, "regulatory_quantity_refs", _typed_tuple(self.regulatory_quantity_refs, DependencyKey, "regulatory_quantity_refs"))
        object.__setattr__(self, "diagnostic_refs", _strings(self.diagnostic_refs, "diagnostic_ref"))


@dataclass(frozen=True, slots=True)
class DependencyBindingRef:
    consumer_instance_id: RuleInstanceId
    dependency_key: DependencyKey
    producer_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.consumer_instance_id, RuleInstanceId) or not isinstance(self.dependency_key, DependencyKey):
            raise TypeError("dependency binding requires typed identities")
        _nonblank(self.producer_ref, "producer_ref")


@dataclass(frozen=True, slots=True)
class TypedDagContract:
    node_refs: tuple[RuleInstanceId, ...] = field(default_factory=tuple)
    edge_refs: tuple[DependencyBindingRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_refs", _typed_tuple(self.node_refs, RuleInstanceId, "node_refs"))
        object.__setattr__(self, "edge_refs", _typed_tuple(self.edge_refs, DependencyBindingRef, "edge_refs"))


@dataclass(frozen=True, slots=True)
class TBDYExecutionPlan:
    registry_version: str
    plan_identity: str
    compiled_rule_instances: tuple[RuleInstanceId, ...]
    compiled_dependency_bindings: tuple[DependencyBindingRef, ...]
    typed_dag: TypedDagContract
    compiled_closure_inventory: tuple[CompiledClosureRecord, ...]
    deterministic_execution_order: tuple[RuleInstanceId, ...]
    analysis_basis_compatibility_refs: tuple[str, ...]
    compile_diagnostics: tuple[str, ...]
    regulatory_authority_catalog_version: str | None = None
    compiled_authority_binding_refs: tuple[str, ...] = field(default_factory=tuple)
    compiled_authority_fingerprints: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _nonblank(self.registry_version, "registry_version")
        _nonblank(self.plan_identity, "plan_identity")
        if not isinstance(self.typed_dag, TypedDagContract):
            raise TypeError("typed_dag must be TypedDagContract")
        object.__setattr__(self, "compiled_rule_instances", _typed_tuple(self.compiled_rule_instances, RuleInstanceId, "compiled_rule_instances"))
        object.__setattr__(self, "compiled_dependency_bindings", _typed_tuple(self.compiled_dependency_bindings, DependencyBindingRef, "compiled_dependency_bindings"))
        object.__setattr__(self, "compiled_closure_inventory", _typed_tuple(self.compiled_closure_inventory, CompiledClosureRecord, "compiled_closure_inventory"))
        object.__setattr__(self, "deterministic_execution_order", _typed_tuple(self.deterministic_execution_order, RuleInstanceId, "deterministic_execution_order"))
        object.__setattr__(self, "analysis_basis_compatibility_refs", _strings(self.analysis_basis_compatibility_refs, "analysis_basis_compatibility_ref"))
        object.__setattr__(self, "compile_diagnostics", _strings(self.compile_diagnostics, "compile_diagnostic"))
        if self.regulatory_authority_catalog_version is not None:
            _nonblank(self.regulatory_authority_catalog_version, "regulatory_authority_catalog_version")
        object.__setattr__(self, "compiled_authority_binding_refs", _strings(self.compiled_authority_binding_refs, "compiled_authority_binding_ref"))
        object.__setattr__(self, "compiled_authority_fingerprints", _strings(self.compiled_authority_fingerprints, "compiled_authority_fingerprint"))
        if self.regulatory_authority_catalog_version is None and (
            self.compiled_authority_binding_refs or self.compiled_authority_fingerprints
        ):
            raise ValueError("authority refs require regulatory_authority_catalog_version")
        if len(self.compiled_authority_binding_refs) != len(self.compiled_authority_fingerprints):
            raise ValueError("authority binding refs and fingerprints must have equal cardinality")


__all__ = [
    "RuleId",
    "RuleInstanceId",
    "Grain",
    "SemanticType",
    "PhysicalDimension",
    "DependencyKey",
    "DependencySourceKind",
    "ScopePolicy",
    "DirectionPolicy",
    "ApplicabilityState",
    "AvailabilityState",
    "PopulationRequirement",
    "ClosureExecutionStatus",
    "DependencySpec",
    "RegulatoryOutputContract",
    "RegulatoryQuantity",
    "ApplicabilityBinding",
    "DerivationEvaluatorBinding",
    "CheckEvaluatorBinding",
    "RegulatoryDerivationSpec",
    "CheckSpec",
    "CompiledClosureRecord",
    "RuleClosureOutcome",
    "DependencyBindingRef",
    "TypedDagContract",
    "TBDYExecutionPlan",
]
