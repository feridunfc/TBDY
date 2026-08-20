from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.analysis_basis import (
    AnalysisBasisCompatibility,
    RuleAnalysisBasisRequirement,
    resolve_rule_targets_for_analysis_basis,
)
from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    CheckEvaluatorBinding,
    CheckSpec,
    ClosureExecutionStatus,
    DependencyKey,
    DependencySourceKind,
    DependencySpec,
    DerivationEvaluatorBinding,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    RegulatoryDerivationSpec,
    RegulatoryOutputContract,
    RegulatoryQuantity,
    RuleId,
    ScopePolicy,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    AssessmentEngine,
    MaterializedDependency,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleExecutionEnvelope,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS


ZONE = "SUPERSTRUCTURE"
DERIVATION_RULE = RuleId("TEST_F0_5_TOY_ANALYSIS_DERIVATION")
DOWNSTREAM_RULE = RuleId("TEST_F0_5_TOY_DOWNSTREAM_CHECK")
INDEPENDENT_RULE = RuleId("TEST_F0_5_TOY_INDEPENDENT_CHECK")
TOY_DERIVED_KEY = DependencyKey("test_f0_5_toy_derived_state")
RULE_VERSION = "test-f0.5-v1"


@dataclass(frozen=True, slots=True)
class ToyExecutionInput:
    envelope: RuleExecutionEnvelope
    dependencies: tuple[MaterializedDependency, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: tuple[MaterializedDependency, ...],
    ) -> "ToyExecutionInput":
        return cls(envelope=envelope, dependencies=tuple(dependencies))


def _applies(_: bool) -> ApplicabilityState:
    return ApplicabilityState.APPLIES


def _derive(inp: ToyExecutionInput) -> RegulatoryQuantity:
    instance = inp.envelope.instance_id
    return RegulatoryQuantity(
        quantity_key=TOY_DERIVED_KEY,
        producer_instance_id=instance,
        semantic_type=SemanticType.TOY_DERIVED_STATE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.DIRECTION,
        scope_ref=instance.scope_ref,
        direction=instance.direction,
        value=1.0,
        unit=UNIT_DIMENSIONLESS,
        availability=AvailabilityState.RESOLVED,
        rule_version=RULE_VERSION,
        code_refs=("TEST_ONLY",),
        dependency_refs=(),
        evidence_refs=(),
        provenance=("TEST_ONLY",),
        derivation_trace=("neutral fixture",),
        governing_trace=(),
    )


def _downstream(inp: ToyExecutionInput) -> CheckResult:
    dependency = inp.dependencies[0]
    return CheckResult(
        check_id=DOWNSTREAM_RULE.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="toy_directional_scope",
        status=CheckStatus.OK,
        value=dependency.value,
        unit="dimensionless",
        messages=("TEST_ONLY neutral downstream check",),
        code_ref="TEST_ONLY",
    )


def _independent(inp: ToyExecutionInput) -> CheckResult:
    return CheckResult(
        check_id=INDEPENDENT_RULE.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="toy_independent_scope",
        status=CheckStatus.OK,
        value=1.0,
        unit="dimensionless",
        messages=("TEST_ONLY neutral independent check",),
        code_ref="TEST_ONLY",
    )


APPLICABILITY = ApplicabilityBinding(
    binding_id="test-f0.5:applies",
    input_type=bool,
    evaluator=_applies,
)

DERIVATION_SPEC = RegulatoryDerivationSpec(
    rule_id=DERIVATION_RULE,
    code_refs=("TEST_ONLY",),
    rule_version=RULE_VERSION,
    output_contract=RegulatoryOutputContract(
        authority_key=TOY_DERIVED_KEY,
        semantic_type=SemanticType.TOY_DERIVED_STATE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.DIRECTION,
        unit=UNIT_DIMENSIONLESS,
    ),
    dependencies=(),
    applicability=APPLICABILITY,
    evaluator=DerivationEvaluatorBinding(
        binding_id="test-f0.5:derive",
        input_type=ToyExecutionInput,
        evaluator=_derive,
    ),
)

DOWNSTREAM_SPEC = CheckSpec(
    rule_id=DOWNSTREAM_RULE,
    code_refs=("TEST_ONLY",),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(
        DependencySpec(
            key=TOY_DERIVED_KEY,
            source_kind=DependencySourceKind.REGULATORY_QUANTITY,
            semantic_type=SemanticType.TOY_DERIVED_STATE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.DIRECTION,
            scope_policy=ScopePolicy.SAME_SCOPE,
            direction_policy=DirectionPolicy.SAME_DIRECTION,
            unit_requirement=UNIT_DIMENSIONLESS,
        ),
    ),
    applicability=APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        binding_id="test-f0.5:downstream",
        input_type=ToyExecutionInput,
        evaluator=_downstream,
    ),
)

INDEPENDENT_SPEC = CheckSpec(
    rule_id=INDEPENDENT_RULE,
    code_refs=("TEST_ONLY",),
    rule_version=RULE_VERSION,
    formal_result_type=CheckResult,
    dependencies=(),
    applicability=APPLICABILITY,
    evaluator=CheckEvaluatorBinding(
        binding_id="test-f0.5:independent",
        input_type=ToyExecutionInput,
        evaluator=_independent,
    ),
)

REGISTRY = RegulatoryRegistry(
    derivations=(DERIVATION_SPEC,),
    checks=(DOWNSTREAM_SPEC, INDEPENDENT_SPEC),
)


def _epoch(epoch_id: str = "E17") -> EvidenceEpoch:
    return EvidenceEpoch(
        epoch_id=epoch_id,
        model_fingerprint="fixture:model",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
        source_fingerprint="fixture:source",
        provenance_refs=("fixture:capture",),
    )


def _compatibility(direction: str, status: AnalysisBasisStatus, epoch_id: str = "E17") -> AnalysisBasisCompatibility:
    return AnalysisBasisCompatibility(
        compatibility_id=f"fixture:compatibility:{direction}:{epoch_id}",
        epoch_ref=f"epoch:{epoch_id}",
        structural_zone_ref=ZONE,
        direction=direction,
        required_basis_ref=f"fixture:required:{direction}",
        analysis_assumption_ref=f"fixture:assumption:{direction}:{epoch_id}",
        status=status,
        provenance_refs=(f"fixture:compatibility-provenance:{direction}",),
    )


def _target(rule_id: RuleId, direction: str | None, grain: Grain) -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=rule_id,
        grain=grain,
        scope_ref=ZONE if grain is Grain.DIRECTION else "MODEL",
        direction=direction,
        applicability_input=True,
    )


def _targets() -> tuple[RuleScopeTarget, ...]:
    return (
        _target(DERIVATION_RULE, "X", Grain.DIRECTION),
        _target(DERIVATION_RULE, "Y", Grain.DIRECTION),
        _target(DOWNSTREAM_RULE, "X", Grain.DIRECTION),
        _target(DOWNSTREAM_RULE, "Y", Grain.DIRECTION),
        _target(INDEPENDENT_RULE, None, Grain.MODEL),
    )


def _requirements(
    targets: tuple[RuleScopeTarget, ...], x_ref: str, y_ref: str
) -> tuple[RuleAnalysisBasisRequirement, ...]:
    producers = {item.direction: item for item in targets if item.rule_id == DERIVATION_RULE}
    return (
        RuleAnalysisBasisRequirement(
            rule_instance_id=producers["X"].instance_id,
            structural_zone_ref=ZONE,
            direction="X",
            compatibility_ref=x_ref,
        ),
        RuleAnalysisBasisRequirement(
            rule_instance_id=producers["Y"].instance_id,
            structural_zone_ref=ZONE,
            direction="Y",
            compatibility_ref=y_ref,
        ),
    )


def test_existing_f0_dag_proves_dependency_scoped_invalidation_without_global_shutdown() -> None:
    epoch = _epoch()
    x_comp = _compatibility("X", AnalysisBasisStatus.MATCH)
    y_comp = _compatibility("Y", AnalysisBasisStatus.REANALYSIS_REQUIRED)
    pre_targets = _targets()
    resolved_targets = resolve_rule_targets_for_analysis_basis(
        epoch=epoch,
        rule_targets=pre_targets,
        requirements=_requirements(pre_targets, x_comp.compatibility_id, y_comp.compatibility_id),
        compatibilities=(y_comp, x_comp),
    )

    by_rule_direction = {(item.rule_id, item.direction): item for item in resolved_targets}
    assert by_rule_direction[(DERIVATION_RULE, "X")].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert by_rule_direction[(DERIVATION_RULE, "Y")].analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED
    assert by_rule_direction[(DOWNSTREAM_RULE, "X")].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert by_rule_direction[(DOWNSTREAM_RULE, "Y")].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert by_rule_direction[(INDEPENDENT_RULE, None)].analysis_basis_status is AnalysisBasisStatus.MATCH

    program = RegulatoryCompiler.compile(
        REGISTRY,
        RegulatoryCompileInputs(rule_targets=resolved_targets),
    )
    compiled = {(node.instance_id.rule_id, node.instance_id.direction): node for node in program.nodes}
    assert compiled[(DERIVATION_RULE, "X")].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert compiled[(DERIVATION_RULE, "Y")].analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED

    store = RegulatoryEngine.execute(program)
    outcomes = {
        (item.compiled_record_ref.rule_id, item.compiled_record_ref.direction): item.execution_status
        for item in store.closure_outcomes
    }
    assert outcomes[(DERIVATION_RULE, "X")] is ClosureExecutionStatus.EXECUTED
    assert outcomes[(DERIVATION_RULE, "Y")] is ClosureExecutionStatus.BLOCKED
    assert outcomes[(DOWNSTREAM_RULE, "X")] is ClosureExecutionStatus.EXECUTED
    assert outcomes[(DOWNSTREAM_RULE, "Y")] is ClosureExecutionStatus.BLOCKED
    assert outcomes[(INDEPENDENT_RULE, None)] is ClosureExecutionStatus.EXECUTED

    producer_quantities = {
        item.producer_instance_id.direction: item for item in store.regulatory_quantities
    }
    assert set(producer_quantities) == {"X"}
    downstream_results = {
        item.instance_id.direction: item.result
        for item in store.formal_results
        if item.instance_id.rule_id == DOWNSTREAM_RULE
    }
    assert set(downstream_results) == {"X"}
    independent_results = [
        item.result for item in store.formal_results if item.instance_id.rule_id == INDEPENDENT_RULE
    ]
    assert len(independent_results) == 1

    assessment = AssessmentEngine.reconcile(program, store)
    assert assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"
    assert {item.direction for item in assessment.incomplete_mandatory_instances} == {"Y"}


def test_old_epoch_compatibility_marks_only_bound_target_unresolved() -> None:
    old_x = _compatibility("X", AnalysisBasisStatus.MATCH, epoch_id="E17")
    targets = (
        _target(DERIVATION_RULE, "X", Grain.DIRECTION),
        _target(DOWNSTREAM_RULE, "Y", Grain.DIRECTION),
        _target(INDEPENDENT_RULE, None, Grain.MODEL),
    )
    requirement = RuleAnalysisBasisRequirement(
        rule_instance_id=targets[0].instance_id,
        structural_zone_ref=ZONE,
        direction="X",
        compatibility_ref=old_x.compatibility_id,
    )
    resolved = resolve_rule_targets_for_analysis_basis(
        epoch=_epoch("E18"),
        rule_targets=targets,
        requirements=(requirement,),
        compatibilities=(old_x,),
    )
    by_key = {(item.rule_id, item.direction): item for item in resolved}
    assert by_key[(DERIVATION_RULE, "X")].analysis_basis_status is AnalysisBasisStatus.UNRESOLVED
    assert by_key[(DOWNSTREAM_RULE, "Y")].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert by_key[(INDEPENDENT_RULE, None)].analysis_basis_status is AnalysisBasisStatus.MATCH
    assert old_x.epoch_ref == "epoch:E17"
