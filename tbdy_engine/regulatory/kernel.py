"""Deterministic F0.1 regulatory DAG kernel; no TBDY engineering authority."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus
from .contracts import (
    ApplicabilityState,
    AvailabilityState,
    CheckSpec,
    ClosureExecutionStatus,
    CompiledClosureRecord,
    DependencyBindingRef,
    DependencyKey,
    DependencySourceKind,
    DependencySpec,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    PopulationRequirement,
    RegulatoryDerivationSpec,
    RegulatoryQuantity,
    RuleClosureOutcome,
    RuleId,
    RuleInstanceId,
    ScopePolicy,
    SemanticType,
    TBDYExecutionPlan,
    TypedDagContract,
)
from .registry import RegulatoryRegistry
from .units import Unit, conversion_factor, units_convertible

RuleDefinition = RegulatoryDerivationSpec | CheckSpec


class KernelCompileError(ValueError):
    """Static F0.1 failure; no plan is emitted."""


class KernelExecutionError(RuntimeError):
    """Fail-closed execution or output-contract failure."""


class PopulationCompleteness(StrEnum):
    FULL = "FULL"
    INCOMPLETE = "INCOMPLETE"


class AnalysisBasisStatus(StrEnum):
    MATCH = "MATCH"
    REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
    UNRESOLVED = "UNRESOLVED"
    INVALID = "INVALID"


class BindingAuthorityKind(StrEnum):
    EXTERNAL_AUTHORITY = "EXTERNAL_AUTHORITY"
    REGULATORY_PRODUCER = "REGULATORY_PRODUCER"


class StructuralAssessmentStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _directional(grain: Grain) -> bool:
    return grain in {Grain.DIRECTION, Grain.COMPONENT_DIRECTION, Grain.COMPONENT_END_DIRECTION}


def _scope_direction(grain: Grain, direction: str | None, label: str) -> None:
    if _directional(grain):
        if direction is None:
            raise ValueError(f"{label} requires direction for {grain.value}")
        _text(direction, f"{label}.direction")
    elif direction is not None:
        raise ValueError(f"{label} forbids direction for {grain.value}")


def _freeze(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if type(value) in (dict, MappingProxyType):
        out: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("payload mapping keys must be strings")
            out[key] = _freeze(item)
        return MappingProxyType(out)
    if type(value) in (tuple, list):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"unsupported payload type: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class RuleScopeTarget:
    rule_id: RuleId
    grain: Grain
    scope_ref: str
    direction: str | None = None
    mandatory: bool = True
    applicability_input: object = None
    analysis_basis_status: AnalysisBasisStatus = AnalysisBasisStatus.MATCH

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, RuleId) or not isinstance(self.grain, Grain):
            raise TypeError("RuleScopeTarget requires RuleId and Grain")
        _text(self.scope_ref, "scope_ref")
        _scope_direction(self.grain, self.direction, "RuleScopeTarget")
        if not isinstance(self.mandatory, bool):
            raise TypeError("mandatory must be bool")
        if not isinstance(self.analysis_basis_status, AnalysisBasisStatus):
            raise TypeError("analysis_basis_status must be AnalysisBasisStatus")

    @property
    def instance_id(self) -> RuleInstanceId:
        return RuleInstanceId.build(
            rule_id=self.rule_id, grain=self.grain, scope_ref=self.scope_ref, direction=self.direction
        )

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return self.rule_id.value, self.grain.value, self.scope_ref, self.direction or ""


@dataclass(frozen=True, slots=True)
class ExternalDependencyAuthority:
    authority_id: str
    key: DependencyKey
    source_kind: DependencySourceKind
    semantic_type: SemanticType
    physical_dimension: PhysicalDimension
    grain: Grain
    scope_ref: str
    direction: str | None
    unit: Unit
    availability: AvailabilityState
    population_completeness: PopulationCompleteness
    value: object = None
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _text(self.authority_id, "authority_id")
        typed = (
            (self.key, DependencyKey), (self.source_kind, DependencySourceKind),
            (self.semantic_type, SemanticType), (self.physical_dimension, PhysicalDimension),
            (self.grain, Grain), (self.unit, Unit), (self.availability, AvailabilityState),
            (self.population_completeness, PopulationCompleteness),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise TypeError("ExternalDependencyAuthority requires bounded typed metadata")
        if self.source_kind is DependencySourceKind.REGULATORY_QUANTITY:
            raise ValueError("REGULATORY_QUANTITY must bind to a registered producer")
        _text(self.scope_ref, "scope_ref")
        _scope_direction(self.grain, self.direction, "ExternalDependencyAuthority")
        if self.unit.physical_dimension is not self.physical_dimension:
            raise ValueError("external authority unit/dimension mismatch")
        object.__setattr__(self, "value", _freeze(self.value))
        refs = tuple(_text(item, "provenance_ref") for item in self.provenance_refs)
        object.__setattr__(self, "provenance_refs", refs)

    @property
    def sort_key(self) -> tuple[str, str, str, str, str]:
        return self.key.value, self.source_kind.value, self.scope_ref, self.direction or "", self.authority_id


@dataclass(frozen=True, slots=True)
class RegulatoryCompileInputs:
    rule_targets: tuple[RuleScopeTarget, ...]
    external_authorities: tuple[ExternalDependencyAuthority, ...] = field(default_factory=tuple)

    def __init__(
        self, *, rule_targets: Sequence[RuleScopeTarget],
        external_authorities: Sequence[ExternalDependencyAuthority] = (),
    ) -> None:
        targets = tuple(rule_targets)
        authorities = tuple(external_authorities)
        if any(not isinstance(item, RuleScopeTarget) for item in targets):
            raise TypeError("rule_targets must contain RuleScopeTarget")
        if any(not isinstance(item, ExternalDependencyAuthority) for item in authorities):
            raise TypeError("external_authorities must contain ExternalDependencyAuthority")
        ids = [item.authority_id for item in authorities]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate external authority_id")
        object.__setattr__(self, "rule_targets", tuple(sorted(targets, key=lambda x: x.sort_key)))
        object.__setattr__(self, "external_authorities", tuple(sorted(authorities, key=lambda x: x.sort_key)))


@dataclass(frozen=True, slots=True)
class CompiledDependencyBinding:
    consumer_instance_id: RuleInstanceId
    dependency: DependencySpec
    authority_kind: BindingAuthorityKind
    external_authority_id: str | None = None
    producer_instance_id: RuleInstanceId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.consumer_instance_id, RuleInstanceId) or not isinstance(self.dependency, DependencySpec):
            raise TypeError("compiled binding requires typed consumer/dependency")
        if not isinstance(self.authority_kind, BindingAuthorityKind):
            raise TypeError("authority_kind must be BindingAuthorityKind")
        external = self.authority_kind is BindingAuthorityKind.EXTERNAL_AUTHORITY
        if external != (self.external_authority_id is not None) or external == (self.producer_instance_id is not None):
            raise ValueError("compiled binding must name exactly one authority kind")

    @property
    def producer_ref(self) -> str:
        if self.external_authority_id is not None:
            return f"external:{self.external_authority_id}"
        assert self.producer_instance_id is not None
        return f"regulatory:{self.producer_instance_id.value}"

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.consumer_instance_id.value, self.dependency.key.value, self.producer_ref


@dataclass(frozen=True, slots=True)
class CompiledRuleNode:
    instance_id: RuleInstanceId
    spec: RuleDefinition
    closure_record: CompiledClosureRecord
    dependency_bindings: tuple[CompiledDependencyBinding, ...]
    analysis_basis_status: AnalysisBasisStatus

    @property
    def is_derivation(self) -> bool:
        return isinstance(self.spec, RegulatoryDerivationSpec)


@dataclass(frozen=True, slots=True)
class CompiledRegulatoryProgram:
    plan: TBDYExecutionPlan
    nodes: tuple[CompiledRuleNode, ...]
    external_authorities: tuple[ExternalDependencyAuthority, ...]

    def node(self, instance_id: RuleInstanceId) -> CompiledRuleNode:
        return next(item for item in self.nodes if item.instance_id == instance_id)

    def authority(self, authority_id: str) -> ExternalDependencyAuthority:
        return next(item for item in self.external_authorities if item.authority_id == authority_id)


@dataclass(frozen=True, slots=True)
class MaterializedDependency:
    key: DependencyKey
    source_kind: DependencySourceKind
    semantic_type: SemanticType
    physical_dimension: PhysicalDimension
    grain: Grain
    scope_ref: str
    direction: str | None
    unit: Unit
    availability: AvailabilityState
    population_completeness: PopulationCompleteness
    value: object
    authority_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _freeze(self.value))


@dataclass(frozen=True, slots=True)
class DeclaredDependencyView:
    dependencies: tuple[MaterializedDependency, ...]

    def __post_init__(self) -> None:
        deps = tuple(self.dependencies)
        if any(not isinstance(item, MaterializedDependency) for item in deps):
            raise TypeError("dependencies must contain MaterializedDependency")
        if len({item.key for item in deps}) != len(deps):
            raise ValueError("duplicate declared dependency")
        object.__setattr__(self, "dependencies", tuple(sorted(deps, key=lambda x: x.key.value)))

    def one(self, key: DependencyKey) -> MaterializedDependency:
        for item in self.dependencies:
            if item.key == key:
                return item
        raise KeyError(f"undeclared dependency is unavailable: {key.value}")

    def value(self, key: DependencyKey) -> object:
        return self.one(key).value


@dataclass(frozen=True, slots=True)
class RuleExecutionEnvelope:
    plan_identity: str
    instance_id: RuleInstanceId
    rule_id: RuleId
    rule_version: str
    declared_dependency_refs: tuple[DependencyKey, ...]


@dataclass(frozen=True, slots=True)
class ReadinessDecision:
    executable: bool
    execution_status: ClosureExecutionStatus
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FormalResultRecord:
    instance_id: RuleInstanceId
    result: CheckResult


@dataclass(frozen=True, slots=True)
class RegulatoryStoreSnapshot:
    plan_identity: str
    regulatory_quantities: tuple[RegulatoryQuantity, ...]
    formal_results: tuple[FormalResultRecord, ...]
    closure_outcomes: tuple[RuleClosureOutcome, ...]
    diagnostics: tuple[str, ...]

    def quantities_for(self, instance_id: RuleInstanceId) -> tuple[RegulatoryQuantity, ...]:
        return tuple(x for x in self.regulatory_quantities if x.producer_instance_id == instance_id)

    def formal_results_for(self, instance_id: RuleInstanceId) -> tuple[CheckResult, ...]:
        return tuple(x.result for x in self.formal_results if x.instance_id == instance_id)

    def outcome_for(self, instance_id: RuleInstanceId) -> RuleClosureOutcome | None:
        matches = tuple(x for x in self.closure_outcomes if x.compiled_record_ref == instance_id)
        if len(matches) > 1:
            raise ValueError("duplicate closure outcomes in store snapshot")
        return matches[0] if matches else None


class RegulatoryStore:
    def __init__(self, *, plan_identity: str) -> None:
        self._plan_identity = _text(plan_identity, "plan_identity")
        self._quantities: dict[tuple[str, str], RegulatoryQuantity] = {}
        self._formal: dict[str, FormalResultRecord] = {}
        self._outcomes: dict[str, RuleClosureOutcome] = {}
        self._diagnostics: list[str] = []

    def record_regulatory_quantity(self, quantity: RegulatoryQuantity) -> None:
        if type(quantity) is not RegulatoryQuantity:
            raise KernelExecutionError("store accepts canonical RegulatoryQuantity only")
        key = quantity.producer_instance_id.value, quantity.quantity_key.value
        if key in self._quantities:
            raise KernelExecutionError("duplicate RegulatoryQuantity authority output")
        self._quantities[key] = quantity

    def record_check_result(self, instance_id: RuleInstanceId, result: CheckResult) -> None:
        if type(result) is not CheckResult:
            raise KernelExecutionError("store accepts canonical CheckResult only")
        if instance_id.value in self._formal:
            raise KernelExecutionError("duplicate formal output for compiled instance")
        self._formal[instance_id.value] = FormalResultRecord(instance_id, result)

    def record_outcome(self, outcome: RuleClosureOutcome) -> None:
        key = outcome.compiled_record_ref.value
        if key in self._outcomes:
            raise KernelExecutionError("duplicate closure outcome for compiled instance")
        self._outcomes[key] = outcome

    def quantity(self, producer: RuleInstanceId, key: DependencyKey) -> RegulatoryQuantity | None:
        return self._quantities.get((producer.value, key.value))

    def outcome(self, instance_id: RuleInstanceId) -> RuleClosureOutcome | None:
        return self._outcomes.get(instance_id.value)

    def snapshot(self) -> RegulatoryStoreSnapshot:
        return RegulatoryStoreSnapshot(
            plan_identity=self._plan_identity,
            regulatory_quantities=tuple(sorted(self._quantities.values(), key=lambda x: (x.producer_instance_id.value, x.quantity_key.value))),
            formal_results=tuple(sorted(self._formal.values(), key=lambda x: x.instance_id.value)),
            closure_outcomes=tuple(sorted(self._outcomes.values(), key=lambda x: x.compiled_record_ref.value)),
            diagnostics=tuple(self._diagnostics),
        )


@dataclass(frozen=True, slots=True)
class StructuralAssessment:
    plan_identity: str
    structural_status: StructuralAssessmentStatus
    closure_outcomes: tuple[RuleClosureOutcome, ...]
    incomplete_mandatory_instances: tuple[RuleInstanceId, ...]
    diagnostics: tuple[str, ...]
    full_tbdy_compliance_status: str = "NOT_EVALUATED"


class ReadinessEngine:
    @staticmethod
    def assess(node: CompiledRuleNode, deps: DeclaredDependencyView) -> ReadinessDecision:
        app = node.closure_record.applicability
        if app is ApplicabilityState.PROVEN_NOT_APPLICABLE:
            return ReadinessDecision(False, ClosureExecutionStatus.PROVEN_NOT_APPLICABLE, ("PROVEN_NOT_APPLICABLE",))
        if app is ApplicabilityState.UNRESOLVED:
            return ReadinessDecision(False, ClosureExecutionStatus.BLOCKED, ("applicability UNRESOLVED",))
        if app is ApplicabilityState.INVALID_CONTEXT:
            return ReadinessDecision(False, ClosureExecutionStatus.INVALID, ("applicability INVALID_CONTEXT",))
        basis = node.analysis_basis_status
        if basis is not AnalysisBasisStatus.MATCH:
            status = ClosureExecutionStatus.INVALID if basis is AnalysisBasisStatus.INVALID else ClosureExecutionStatus.BLOCKED
            return ReadinessDecision(False, status, (f"analysis basis {basis.value}",))
        diagnostics: list[str] = []
        status = ClosureExecutionStatus.EXECUTED
        for spec in node.spec.dependencies:
            item = deps.one(spec.key)
            if item.availability is not spec.required_availability:
                diagnostics.append(f"{spec.key.value}: availability {item.availability.value}")
                status = ClosureExecutionStatus.NO_DATA if item.availability is AvailabilityState.NO_DATA else ClosureExecutionStatus.BLOCKED
            if spec.population_completeness_requirement is PopulationRequirement.FULL and item.population_completeness is not PopulationCompleteness.FULL:
                diagnostics.append(f"{spec.key.value}: incomplete population")
                status = ClosureExecutionStatus.BLOCKED
        return ReadinessDecision(not diagnostics, status, tuple(diagnostics))


class RegulatoryCompiler:
    """Pure compiler. Topological ties use lexical RuleInstanceId.value; no engineering meaning."""

    @classmethod
    def compile(cls, registry: RegulatoryRegistry, inputs: RegulatoryCompileInputs) -> CompiledRegulatoryProgram:
        if not isinstance(registry, RegulatoryRegistry) or not isinstance(inputs, RegulatoryCompileInputs):
            raise TypeError("compile requires RegulatoryRegistry and RegulatoryCompileInputs")
        specs, targets = cls._expand(registry, inputs)
        nodes: list[CompiledRuleNode] = []
        bindings: list[CompiledDependencyBinding] = []
        for instance_id in sorted(specs, key=lambda x: x.value):
            spec, target = specs[instance_id], targets[instance_id]
            applicability = cls._applicability(spec, target)
            closure = CompiledClosureRecord(
                instance_id=instance_id, rule_id=instance_id.rule_id, grain=instance_id.grain,
                scope_ref=instance_id.scope_ref, mandatory=target.mandatory, applicability=applicability,
                declared_dependency_refs=tuple(d.key for d in spec.dependencies),
                code_refs=spec.code_refs, rule_version=spec.rule_version,
            )
            node_bindings = tuple(
                cls._bind(instance_id, dep, registry, specs, inputs) for dep in spec.dependencies
            )
            bindings.extend(node_bindings)
            nodes.append(CompiledRuleNode(instance_id, spec, closure, node_bindings, target.analysis_basis_status))
        bindings.sort(key=lambda x: x.sort_key)
        cls._validate_bindings(tuple(bindings), registry, specs, inputs)
        order = cls._topological(tuple(nodes), tuple(bindings))
        refs = tuple(DependencyBindingRef(x.consumer_instance_id, x.dependency.key, x.producer_ref) for x in bindings)
        edges = tuple(ref for ref, binding in zip(refs, bindings) if binding.authority_kind is BindingAuthorityKind.REGULATORY_PRODUCER)
        instances = tuple(sorted(specs, key=lambda x: x.value))
        plan = TBDYExecutionPlan(
            registry_version=registry.registry_version,
            plan_identity=cls._identity(registry, tuple(nodes), tuple(bindings), order, inputs.external_authorities),
            compiled_rule_instances=instances,
            compiled_dependency_bindings=refs,
            typed_dag=TypedDagContract(node_refs=instances, edge_refs=edges),
            compiled_closure_inventory=tuple(sorted((n.closure_record for n in nodes), key=lambda x: x.instance_id.value)),
            deterministic_execution_order=order,
            analysis_basis_compatibility_refs=tuple(f"{n.instance_id.value}:{n.analysis_basis_status.value}" for n in sorted(nodes, key=lambda x: x.instance_id.value)),
            compile_diagnostics=("F0.1_COMPILE_OK", "TOPOLOGICAL_TIE_BREAK=RuleInstanceId.value lexical order"),
        )
        return CompiledRegulatoryProgram(plan, tuple(sorted(nodes, key=lambda x: x.instance_id.value)), inputs.external_authorities)

    @staticmethod
    def _expand(registry: RegulatoryRegistry, inputs: RegulatoryCompileInputs) -> tuple[dict[RuleInstanceId, RuleDefinition], dict[RuleInstanceId, RuleScopeTarget]]:
        registered = {spec.rule_id: spec for spec in (*registry.derivations, *registry.checks)}
        seen_rules: set[RuleId] = set()
        specs: dict[RuleInstanceId, RuleDefinition] = {}
        targets: dict[RuleInstanceId, RuleScopeTarget] = {}
        for target in inputs.rule_targets:
            if target.rule_id not in registered:
                raise KernelCompileError(f"unregistered RuleId target: {target.rule_id.value}")
            seen_rules.add(target.rule_id)
            instance = target.instance_id
            if instance in specs:
                raise KernelCompileError(f"duplicate RuleInstanceId: {instance.value}")
            spec = registered[target.rule_id]
            if isinstance(spec, RegulatoryDerivationSpec) and instance.grain is not spec.output_contract.grain:
                raise KernelCompileError(f"derivation output grain mismatch for {instance.value}")
            specs[instance], targets[instance] = spec, target
        missing = sorted(rule.value for rule in set(registered) - seen_rules)
        if missing:
            raise KernelCompileError("registered rule has no compile target: " + ", ".join(missing))
        return specs, targets

    @staticmethod
    def _applicability(spec: RuleDefinition, target: RuleScopeTarget) -> ApplicabilityState:
        if not isinstance(target.applicability_input, spec.applicability.input_type):
            raise KernelCompileError(f"applicability input type mismatch for {target.instance_id.value}")
        state = spec.applicability.evaluator(target.applicability_input)
        if not isinstance(state, ApplicabilityState):
            raise KernelCompileError(f"invalid applicability state for {target.instance_id.value}")
        return state

    @classmethod
    def _bind(
        cls, consumer: RuleInstanceId, dep: DependencySpec, registry: RegulatoryRegistry,
        instances: Mapping[RuleInstanceId, RuleDefinition], inputs: RegulatoryCompileInputs,
    ) -> CompiledDependencyBinding:
        # Binding establishes one authority identity. Contract compatibility is
        # validated later in the frozen F0 order, before graph cycle validation.
        if dep.source_kind is DependencySourceKind.REGULATORY_QUANTITY:
            producers = tuple(s for s in registry.derivations if s.output_contract.authority_key == dep.key)
            if not producers:
                raise cls._error(consumer, dep, "missing regulatory producer")
            if len(producers) != 1:
                raise cls._error(consumer, dep, "multiple regulatory producers")
            candidates = tuple(i for i, spec in instances.items() if spec.rule_id == producers[0].rule_id)
            chosen = cls._choose_regulatory_instance(consumer, dep, candidates)
            return CompiledDependencyBinding(
                consumer, dep, BindingAuthorityKind.REGULATORY_PRODUCER, producer_instance_id=chosen
            )
        candidates = tuple(
            a for a in inputs.external_authorities
            if a.key == dep.key and a.source_kind is dep.source_kind
        )
        if not candidates:
            raise cls._error(consumer, dep, "missing declared external source authority")
        chosen = cls._choose_external_authority(consumer, dep, candidates)
        return CompiledDependencyBinding(
            consumer, dep, BindingAuthorityKind.EXTERNAL_AUTHORITY, external_authority_id=chosen.authority_id
        )

    @classmethod
    def _choose_regulatory_instance(
        cls, consumer: RuleInstanceId, dep: DependencySpec, candidates: tuple[RuleInstanceId, ...]
    ) -> RuleInstanceId:
        if len(candidates) == 1:
            return candidates[0]
        exact = tuple(
            item for item in candidates
            if cls._scope(dep.scope_policy, consumer, item)
            and cls._direction(dep.direction_policy, consumer.direction, item.direction)
        )
        if len(exact) == 1:
            return exact[0]
        raise cls._error(consumer, dep, "multiple regulatory producer instances cannot resolve uniquely")

    @classmethod
    def _choose_external_authority(
        cls, consumer: RuleInstanceId, dep: DependencySpec,
        candidates: tuple[ExternalDependencyAuthority, ...],
    ) -> ExternalDependencyAuthority:
        if len(candidates) == 1:
            return candidates[0]
        exact = tuple(
            item for item in candidates
            if cls._scope_external(dep.scope_policy, consumer, item)
            and cls._direction(dep.direction_policy, consumer.direction, item.direction)
        )
        if len(exact) == 1:
            return exact[0]
        raise cls._error(consumer, dep, "multiple external source authorities cannot resolve uniquely")

    @classmethod
    def _validate_bindings(
        cls, bindings: tuple[CompiledDependencyBinding, ...], registry: RegulatoryRegistry,
        instances: Mapping[RuleInstanceId, RuleDefinition], inputs: RegulatoryCompileInputs,
    ) -> None:
        authorities = {item.authority_id: item for item in inputs.external_authorities}

        def source(binding: CompiledDependencyBinding):
            if binding.external_authority_id is not None:
                return authorities[binding.external_authority_id]
            assert binding.producer_instance_id is not None
            producer_spec = instances[binding.producer_instance_id]
            assert isinstance(producer_spec, RegulatoryDerivationSpec)
            return producer_spec.output_contract

        # Frozen normative order from F0 architecture §§8–8.1. Existence and
        # single-authority checks occur during _bind above. The remaining
        # compatibility classes are validated as ordered passes over all bindings.
        for binding in bindings:
            src = source(binding)
            if src.semantic_type is not binding.dependency.semantic_type:
                raise cls._error(binding.consumer_instance_id, binding.dependency, "semantic type mismatch")
        for binding in bindings:
            src = source(binding)
            if src.physical_dimension is not binding.dependency.physical_dimension:
                raise cls._error(binding.consumer_instance_id, binding.dependency, "physical dimension mismatch")
        for binding in bindings:
            src = source(binding)
            if src.grain is not binding.dependency.grain:
                raise cls._error(binding.consumer_instance_id, binding.dependency, "grain mismatch")
        for binding in bindings:
            dep = binding.dependency
            if binding.external_authority_id is not None:
                ok = cls._scope_external(dep.scope_policy, binding.consumer_instance_id, authorities[binding.external_authority_id])
            else:
                assert binding.producer_instance_id is not None
                ok = cls._scope(dep.scope_policy, binding.consumer_instance_id, binding.producer_instance_id)
            if not ok:
                raise cls._error(binding.consumer_instance_id, dep, "scope mismatch")
        for binding in bindings:
            dep = binding.dependency
            source_direction = (
                authorities[binding.external_authority_id].direction
                if binding.external_authority_id is not None
                else binding.producer_instance_id.direction
            )
            if not cls._direction(dep.direction_policy, binding.consumer_instance_id.direction, source_direction):
                raise cls._error(binding.consumer_instance_id, dep, "direction mismatch")
        for binding in bindings:
            src = source(binding)
            if not units_convertible(src.unit, binding.dependency.unit_requirement):
                raise cls._error(
                    binding.consumer_instance_id, binding.dependency,
                    f"unit mismatch: {src.unit.identifier}->{binding.dependency.unit_requirement.identifier}",
                )
        for binding in bindings:
            dep = binding.dependency
            if dep.population_completeness_requirement is not PopulationRequirement.FULL:
                continue
            if binding.external_authority_id is None:
                continue
            authority = authorities[binding.external_authority_id]
            if authority.population_completeness is not PopulationCompleteness.FULL:
                raise cls._error(binding.consumer_instance_id, dep, "FULL population requirement is not satisfiable")

    @staticmethod
    def _scope(policy: ScopePolicy, consumer: RuleInstanceId, producer: RuleInstanceId) -> bool:
        if policy in {ScopePolicy.EXACT_SCOPE, ScopePolicy.SAME_SCOPE}:
            return consumer.scope_ref == producer.scope_ref
        return policy is ScopePolicy.GLOBAL_SCOPE and producer.grain is Grain.MODEL and producer.scope_ref == "MODEL"

    @staticmethod
    def _scope_external(policy: ScopePolicy, consumer: RuleInstanceId, source: ExternalDependencyAuthority) -> bool:
        if policy in {ScopePolicy.EXACT_SCOPE, ScopePolicy.SAME_SCOPE}:
            return consumer.scope_ref == source.scope_ref
        return policy is ScopePolicy.GLOBAL_SCOPE and source.grain is Grain.MODEL and source.scope_ref == "MODEL"

    @staticmethod
    def _direction(policy: DirectionPolicy, consumer: str | None, source: str | None) -> bool:
        if policy is DirectionPolicy.NO_DIRECTION:
            return source is None
        if policy in {DirectionPolicy.EXACT_DIRECTION, DirectionPolicy.SAME_DIRECTION}:
            return consumer is not None and consumer == source
        return policy is DirectionPolicy.ANY_DIRECTION

    @staticmethod
    def _error(instance: RuleInstanceId, dep: DependencySpec, reason: str) -> KernelCompileError:
        return KernelCompileError(f"{reason}; consumer={instance.value}; dependency={dep.key.value}; source_kind={dep.source_kind.value}")

    @staticmethod
    def _topological(nodes: tuple[CompiledRuleNode, ...], bindings: tuple[CompiledDependencyBinding, ...]) -> tuple[RuleInstanceId, ...]:
        ids = {n.instance_id for n in nodes}
        edges: dict[RuleInstanceId, set[RuleInstanceId]] = {i: set() for i in ids}
        indegree = {i: 0 for i in ids}
        for binding in bindings:
            if binding.producer_instance_id is None:
                continue
            if binding.consumer_instance_id not in edges[binding.producer_instance_id]:
                edges[binding.producer_instance_id].add(binding.consumer_instance_id)
                indegree[binding.consumer_instance_id] += 1
        ready = sorted((i for i, count in indegree.items() if count == 0), key=lambda x: x.value)
        order: list[RuleInstanceId] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for consumer in sorted(edges[current], key=lambda x: x.value):
                indegree[consumer] -= 1
                if indegree[consumer] == 0:
                    ready.append(consumer)
                    ready.sort(key=lambda x: x.value)
        if len(order) != len(ids):
            remaining = sorted(i.value for i, count in indegree.items() if count)
            cycle_edges = sorted(
                f"{b.producer_instance_id.value}->{b.consumer_instance_id.value}"
                for b in bindings if b.producer_instance_id is not None
                and b.producer_instance_id.value in remaining and b.consumer_instance_id.value in remaining
            )
            raise KernelCompileError("dependency cycle prevents plan creation; nodes=" + ",".join(remaining) + "; edges=" + ",".join(cycle_edges))
        return tuple(order)

    @staticmethod
    def _identity(
        registry: RegulatoryRegistry, nodes: tuple[CompiledRuleNode, ...], bindings: tuple[CompiledDependencyBinding, ...],
        order: tuple[RuleInstanceId, ...], authorities: tuple[ExternalDependencyAuthority, ...],
    ) -> str:
        payload = {
            "kernel": "F0.1", "registry": registry.registry_version,
            "nodes": [(n.instance_id.value, n.closure_record.mandatory, n.closure_record.applicability.value, n.analysis_basis_status.value, n.spec.rule_version) for n in sorted(nodes, key=lambda x: x.instance_id.value)],
            "bindings": [(b.consumer_instance_id.value, b.dependency.key.value, b.authority_kind.value, b.producer_ref) for b in sorted(bindings, key=lambda x: x.sort_key)],
            "external": [(a.authority_id, a.key.value, a.source_kind.value, a.semantic_type.value, a.physical_dimension.value, a.grain.value, a.scope_ref, a.direction, a.unit.identifier, a.availability.value, a.population_completeness.value) for a in sorted(authorities, key=lambda x: x.sort_key)],
            "order": [item.value for item in order],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        return "f0.1:" + hashlib.sha256(encoded).hexdigest()


class RegulatoryEngine:
    @classmethod
    def execute(cls, program: CompiledRegulatoryProgram) -> RegulatoryStoreSnapshot:
        store = RegulatoryStore(plan_identity=program.plan.plan_identity)
        for instance_id in program.plan.deterministic_execution_order:
            node = program.node(instance_id)
            if node.closure_record.applicability is not ApplicabilityState.APPLIES or node.analysis_basis_status is not AnalysisBasisStatus.MATCH:
                decision = ReadinessEngine.assess(node, DeclaredDependencyView(()))
                store.record_outcome(RuleClosureOutcome(instance_id, decision.execution_status, diagnostic_refs=decision.diagnostics))
                continue
            deps = cls._materialize(program, node, store)
            ready = ReadinessEngine.assess(node, deps)
            if not ready.executable:
                store.record_outcome(RuleClosureOutcome(instance_id, ready.execution_status, diagnostic_refs=ready.diagnostics))
                continue
            envelope = RuleExecutionEnvelope(program.plan.plan_identity, instance_id, instance_id.rule_id, node.spec.rule_version, tuple(d.key for d in node.spec.dependencies))
            inp = cls._input(node, envelope, deps)
            if isinstance(node.spec, RegulatoryDerivationSpec):
                quantity = node.spec.evaluator.evaluator(inp)
                cls._validate_quantity(node, deps, quantity)
                store.record_regulatory_quantity(quantity)
                status = ClosureExecutionStatus.EXECUTED if quantity.availability is AvailabilityState.RESOLVED else (ClosureExecutionStatus.NO_DATA if quantity.availability is AvailabilityState.NO_DATA else ClosureExecutionStatus.BLOCKED)
                store.record_outcome(RuleClosureOutcome(instance_id, status, regulatory_quantity_refs=(quantity.quantity_key,)))
            else:
                result = node.spec.evaluator.evaluator(inp)
                cls._validate_result(node, result)
                store.record_check_result(instance_id, result)
                status = ClosureExecutionStatus.NO_DATA if result.status is CheckStatus.NO_DATA else (ClosureExecutionStatus.BLOCKED if result.status is CheckStatus.BLOCKED else ClosureExecutionStatus.EXECUTED)
                store.record_outcome(RuleClosureOutcome(instance_id, status, formal_result_ref=f"{instance_id.value}:CheckResult"))
        return store.snapshot()

    @classmethod
    def _materialize(cls, program: CompiledRegulatoryProgram, node: CompiledRuleNode, store: RegulatoryStore) -> DeclaredDependencyView:
        out: list[MaterializedDependency] = []
        for binding in node.dependency_bindings:
            dep = binding.dependency
            if binding.external_authority_id is not None:
                authority = program.authority(binding.external_authority_id)
                value = cls._convert(authority.value, authority.unit, dep.unit_requirement)
                out.append(MaterializedDependency(dep.key, dep.source_kind, authority.semantic_type, authority.physical_dimension, authority.grain, authority.scope_ref, authority.direction, dep.unit_requirement, authority.availability, authority.population_completeness, value, f"external:{authority.authority_id}"))
                continue
            assert binding.producer_instance_id is not None
            quantity = store.quantity(binding.producer_instance_id, dep.key)
            if quantity is None:
                upstream = store.outcome(binding.producer_instance_id)
                availability = AvailabilityState.NO_DATA if upstream and upstream.execution_status is ClosureExecutionStatus.NO_DATA else AvailabilityState.BLOCKED
                out.append(MaterializedDependency(dep.key, dep.source_kind, dep.semantic_type, dep.physical_dimension, dep.grain, node.instance_id.scope_ref, node.instance_id.direction if dep.direction_policy is not DirectionPolicy.NO_DIRECTION else None, dep.unit_requirement, availability, PopulationCompleteness.FULL, None, f"regulatory:{binding.producer_instance_id.value}"))
            else:
                value = cls._convert(quantity.value, quantity.unit, dep.unit_requirement)
                out.append(MaterializedDependency(dep.key, dep.source_kind, quantity.semantic_type, quantity.physical_dimension, quantity.grain, quantity.scope_ref, quantity.direction, dep.unit_requirement, quantity.availability, PopulationCompleteness.FULL, value, f"regulatory:{binding.producer_instance_id.value}"))
        return DeclaredDependencyView(tuple(out))

    @staticmethod
    def _convert(value: object, source: Unit, target: Unit) -> object:
        factor: Fraction = conversion_factor(source, target)
        if factor == 1:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise KernelExecutionError("unit conversion requires numeric scalar")
        return float(value) * float(factor)

    @staticmethod
    def _input(node: CompiledRuleNode, envelope: RuleExecutionEnvelope, deps: DeclaredDependencyView) -> object:
        input_type = node.spec.evaluator.input_type
        if isinstance(deps, input_type):
            return deps
        factory = getattr(input_type, "from_declared_dependencies", None)
        if not callable(factory):
            raise KernelExecutionError(f"cannot materialize typed evaluator input for {node.instance_id.value}")
        value = factory(envelope, deps.dependencies)
        if not isinstance(value, input_type):
            raise KernelExecutionError("typed evaluator input factory returned wrong type")
        return value

    @staticmethod
    def _validate_quantity(node: CompiledRuleNode, deps: DeclaredDependencyView, quantity: object) -> None:
        if type(quantity) is not RegulatoryQuantity:
            raise KernelExecutionError("derivation evaluator must return canonical RegulatoryQuantity")
        assert isinstance(node.spec, RegulatoryDerivationSpec)
        contract = node.spec.output_contract
        checks = (
            (quantity.quantity_key == contract.authority_key, "quantity key"),
            (quantity.producer_instance_id == node.instance_id, "producer RuleInstanceId"),
            (quantity.semantic_type is contract.semantic_type, "semantic type"),
            (quantity.physical_dimension is contract.physical_dimension, "physical dimension"),
            (quantity.grain is contract.grain, "grain"),
            (quantity.scope_ref == node.instance_id.scope_ref, "scope"),
            (quantity.direction == node.instance_id.direction, "direction"),
            (quantity.unit == contract.unit, "unit"),
            (quantity.rule_version == node.spec.rule_version, "rule version"),
            (tuple(sorted(k.value for k in quantity.dependency_refs)) == tuple(sorted(d.key.value for d in deps.dependencies)), "dependency refs"),
        )
        errors = [label for ok, label in checks if not ok]
        if errors:
            raise KernelExecutionError("invalid derivation output contract: " + ", ".join(errors))

    @staticmethod
    def _validate_result(node: CompiledRuleNode, result: object) -> None:
        if type(result) is not CheckResult:
            raise KernelExecutionError("check evaluator must return canonical CheckResult")
        if result.check_id != node.instance_id.rule_id.value or result.component != node.instance_id.scope_ref:
            raise KernelExecutionError("CheckResult identity does not reconcile to compiled instance")


class AssessmentEngine:
    @staticmethod
    def reconcile(program: CompiledRegulatoryProgram, snapshot: RegulatoryStoreSnapshot) -> StructuralAssessment:
        if snapshot.plan_identity != program.plan.plan_identity:
            raise KernelExecutionError("store snapshot plan identity mismatch")
        outcomes: list[RuleClosureOutcome] = []
        incomplete: list[RuleInstanceId] = []
        for record in program.plan.compiled_closure_inventory:
            observed = tuple(x for x in snapshot.closure_outcomes if x.compiled_record_ref == record.instance_id)
            formal = snapshot.formal_results_for(record.instance_id)
            quantities = snapshot.quantities_for(record.instance_id)
            node = program.node(record.instance_id)
            if len(observed) > 1 or len(formal) > 1 or len(quantities) > (1 if node.is_derivation else 0):
                outcome = RuleClosureOutcome(record.instance_id, ClosureExecutionStatus.DUPLICATE, diagnostic_refs=("duplicate runtime output/outcome",))
            elif observed:
                outcome = observed[0]
            elif record.applicability is ApplicabilityState.PROVEN_NOT_APPLICABLE:
                outcome = RuleClosureOutcome(record.instance_id, ClosureExecutionStatus.PROVEN_NOT_APPLICABLE)
            else:
                outcome = RuleClosureOutcome(record.instance_id, ClosureExecutionStatus.MISSING, diagnostic_refs=("compiled closure has no runtime outcome",))
            outcomes.append(outcome)
            if record.mandatory and outcome.execution_status not in {ClosureExecutionStatus.EXECUTED, ClosureExecutionStatus.PROVEN_NOT_APPLICABLE}:
                incomplete.append(record.instance_id)
        diagnostics = (f"incomplete mandatory closure count={len(incomplete)}",) if incomplete else ()
        return StructuralAssessment(
            plan_identity=program.plan.plan_identity,
            structural_status=StructuralAssessmentStatus.INCOMPLETE if incomplete else StructuralAssessmentStatus.COMPLETE,
            closure_outcomes=tuple(sorted(outcomes, key=lambda x: x.compiled_record_ref.value)),
            incomplete_mandatory_instances=tuple(sorted(incomplete, key=lambda x: x.value)),
            diagnostics=diagnostics,
            full_tbdy_compliance_status="NOT_EVALUATED",
        )


__all__ = [
    "KernelCompileError", "KernelExecutionError", "PopulationCompleteness", "AnalysisBasisStatus",
    "BindingAuthorityKind", "StructuralAssessmentStatus", "RuleScopeTarget", "ExternalDependencyAuthority",
    "RegulatoryCompileInputs", "CompiledDependencyBinding", "CompiledRuleNode", "CompiledRegulatoryProgram",
    "MaterializedDependency", "DeclaredDependencyView", "RuleExecutionEnvelope", "ReadinessDecision",
    "FormalResultRecord", "RegulatoryStoreSnapshot", "RegulatoryStore", "StructuralAssessment",
    "ReadinessEngine", "RegulatoryCompiler", "RegulatoryEngine", "AssessmentEngine",
]
