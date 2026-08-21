from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.findings import (
    FindingSourceKind,
    build_finding_from_check_result,
    build_finding_from_rule_closure,
)
from tbdy_engine.integration.f0_evidence_adapter import (
    EvidenceBindingSource,
    F0EvidenceBinding,
    build_component_f0_authorities,
    build_f0_compile_inputs,
)
from tbdy_engine.regulatory.b1_geometry_parity import (
    BEAM_DEPTH_KEY,
    BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    BEAM_MIN_DEPTH_CHECK_SPEC,
    BEAM_MIN_DEPTH_RULE_ID,
    BEAM_WIDTH_KEY as F08_BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY as F08_EVIDENCE_TRACE_KEY,
    SECTION_KEY as F08_SECTION_KEY,
    STORY_KEY as F08_STORY_KEY,
    Beam7411ApplicabilityInput,
)
from tbdy_engine.regulatory.beam_min_width import (
    BEAM_MIN_WIDTH_CHECK_SPEC,
    BEAM_WIDTH_KEY as F02_BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY as F02_EVIDENCE_TRACE_KEY,
    RULE_ID as BEAM_MIN_WIDTH_RULE_ID,
    SECTION_KEY as F02_SECTION_KEY,
    STORY_KEY as F02_STORY_KEY,
    BeamMinWidthApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    ClosureExecutionStatus,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AssessmentEngine,
    KernelCompileError,
    PopulationCompleteness,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleScopeTarget,
    StructuralAssessmentStatus,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM

COMPONENT_ID = "B42"
STORY = "S3"
SECTION = "B_TEST"

VS0_BEAM_REGISTRY = RegulatoryRegistry(
    checks=(
        BEAM_MIN_WIDTH_CHECK_SPEC,
        BEAM_MIN_DEPTH_CHECK_SPEC,
        BEAM_DEPTH_WIDTH_RATIO_CHECK_SPEC,
    )
)


@dataclass(frozen=True, slots=True)
class SliceRun:
    epoch: EvidenceEpoch
    snapshot: FeatureSnapshot
    bindings: tuple[F0EvidenceBinding, ...]
    authorities: tuple[object, ...]
    inputs: object
    registry: RegulatoryRegistry
    program: object
    store: object
    assessment: object


def _evidence(
    *,
    column: str,
    raw: object,
    width: object,
    depth: object,
    status: FeatureEvidenceStatus,
    trace: bool = False,
) -> FeatureEvidence:
    row = {"Story": STORY, "Label": COMPONENT_ID, "Section": SECTION, "Width": width, "Depth": depth}
    reason = None if status is FeatureEvidenceStatus.FULL else (
        "fixture width value unavailable" if status is FeatureEvidenceStatus.MISSING and column == "Width"
        else "fixture evidence partial"
    )
    return FeatureEvidence(
        evidence_status=status,
        source_table="vs0_fixture_frame_section_geometry",
        actual_table_name="VS0 Fixture Frame Section Geometry",
        source_column=column,
        source_row=row,
        raw_value=row if trace else raw,
        normalized_value=row if trace else raw,
        unit="" if trace else "mm",
        resolver="vs0-fixture-component-capture" if trace else "vs0-fixture-frame-geometry",
        reason=reason,
    )


def _snapshot(
    *,
    width: float | None = 249.0,
    depth: float | None = 600.0,
    width_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    width_evidence: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    depth_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    depth_evidence: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    trace_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    trace_evidence: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
) -> FeatureSnapshot:
    width_ev = _evidence(column="Width", raw=width, width=width, depth=depth, status=width_evidence)
    depth_ev = _evidence(column="Depth", raw=depth, width=width, depth=depth, status=depth_evidence)
    trace_ev = _evidence(
        column="ComponentGeometryCapture",
        raw="CAPTURED",
        width=width,
        depth=depth,
        status=trace_evidence,
        trace=True,
    )
    return FeatureSnapshot(
        component_type="beam",
        component_id=COMPONENT_ID,
        identity={"story": STORY, "section": SECTION},
        features={
            "beam_width_mm": FeatureValue(
                feature_name="beam_width_mm",
                value=width,
                unit="mm",
                semantic_role="GEOMETRY",
                status=width_status,
                evidence=(width_ev,),
            ),
            "beam_depth_mm": FeatureValue(
                feature_name="beam_depth_mm",
                value=depth,
                unit="mm",
                semantic_role="GEOMETRY",
                status=depth_status,
                evidence=(depth_ev,),
            ),
            "beam_geometry_trace": FeatureValue(
                feature_name="beam_geometry_trace",
                value="CAPTURED",
                unit="",
                semantic_role="TRACEABILITY",
                status=trace_status,
                evidence=(trace_ev,),
            ),
        },
    )


def _epoch(
    epoch_id: str = "VS0-E1",
    *,
    origin: EvidenceEpochOrigin = EvidenceEpochOrigin.FIXTURE_REPLAY,
    predecessor: str | None = None,
) -> EvidenceEpoch:
    suffix = epoch_id.removeprefix("VS0-").casefold()
    return EvidenceEpoch(
        epoch_id=epoch_id,
        origin=origin,
        model_fingerprint=f"model:fixture:vs0:{suffix}",
        source_fingerprint=f"source:fixture:vs0:{suffix}",
        predecessor_epoch_ref=predecessor,
        provenance_refs=(f"capture:vs0:B42:{epoch_id.removeprefix('VS0-')}",),
    )


def _bindings(*, reverse: bool = False) -> tuple[F0EvidenceBinding, ...]:
    bindings = (
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_width_mm",
            dependency_key=F02_BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_depth_mm",
            dependency_key=BEAM_DEPTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_DEPTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
            source_key="story",
            dependency_key=F02_STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            unit=UNIT_ENUM_STATE,
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
            source_key="section",
            dependency_key=F02_SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            unit=UNIT_ENUM_STATE,
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.EVIDENCE_TRACE,
            source_key="beam_geometry_trace",
            dependency_key=F02_EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            unit=UNIT_DIMENSIONLESS,
        ),
    )
    return tuple(reversed(bindings)) if reverse else bindings


def _targets(*, reverse: bool = False) -> tuple[RuleScopeTarget, ...]:
    targets = (
        RuleScopeTarget(
            rule_id=BEAM_MIN_WIDTH_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=COMPONENT_ID,
            direction=None,
            applicability_input=BeamMinWidthApplicabilityInput(
                component_type="beam", tbdy_7411_applies=True
            ),
        ),
        RuleScopeTarget(
            rule_id=BEAM_MIN_DEPTH_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=COMPONENT_ID,
            direction=None,
            applicability_input=Beam7411ApplicabilityInput(
                is_beam=True, tbdy_7411_applies=True
            ),
        ),
        RuleScopeTarget(
            rule_id=BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=COMPONENT_ID,
            direction=None,
            applicability_input=Beam7411ApplicabilityInput(
                is_beam=True, tbdy_7411_applies=True
            ),
        ),
    )
    return tuple(reversed(targets)) if reverse else targets


def _run(
    *,
    epoch: EvidenceEpoch | None = None,
    snapshot: FeatureSnapshot | None = None,
    reverse_bindings: bool = False,
    reverse_targets: bool = False,
    reverse_registry: bool = False,
) -> SliceRun:
    epoch = epoch or _epoch()
    snapshot = snapshot or _snapshot()
    bindings = _bindings(reverse=reverse_bindings)
    authorities = build_component_f0_authorities(epoch=epoch, snapshot=snapshot, bindings=bindings)
    inputs = build_f0_compile_inputs(
        rule_targets=_targets(reverse=reverse_targets),
        external_authorities=authorities,
    )
    registry = (
        RegulatoryRegistry(checks=tuple(reversed(VS0_BEAM_REGISTRY.checks)))
        if reverse_registry
        else VS0_BEAM_REGISTRY
    )
    program = RegulatoryCompiler.compile(registry, inputs)
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)
    return SliceRun(epoch, snapshot, bindings, authorities, inputs, registry, program, store, assessment)


def _instance(run: SliceRun, rule_id):
    return next(item for item in run.program.plan.compiled_rule_instances if item.rule_id == rule_id)


def _result(run: SliceRun, rule_id):
    values = run.store.formal_results_for(_instance(run, rule_id))
    return values[0] if values else None


def _closure(run: SliceRun, rule_id):
    instance = _instance(run, rule_id)
    return next(item for item in run.assessment.closure_outcomes if item.compiled_record_ref == instance)


def _findings(run: SliceRun):
    records = {item.instance_id: item for item in run.program.plan.compiled_closure_inventory}
    check_findings = []
    for record in run.store.formal_results:
        finding = build_finding_from_check_result(instance_id=record.instance_id, result=record.result)
        if finding is not None:
            check_findings.append(finding)
    closure_findings = []
    for outcome in run.assessment.closure_outcomes:
        finding = build_finding_from_rule_closure(
            compiled_record=records[outcome.compiled_record_ref], outcome=outcome
        )
        if finding is not None:
            closure_findings.append(finding)
    return (
        tuple(sorted(check_findings, key=lambda item: item.finding_id)),
        tuple(sorted(closure_findings, key=lambda item: item.finding_id)),
    )


def test_vs0_complete_beam_slice_runs_from_snapshot_epoch_to_finding() -> None:
    assert VS0_BEAM_REGISTRY.rule_count == 3
    assert VS0_BEAM_REGISTRY.derivations == ()
    assert len({item.rule_id for item in VS0_BEAM_REGISTRY.checks}) == 3
    assert F02_BEAM_WIDTH_KEY == F08_BEAM_WIDTH_KEY
    assert F02_STORY_KEY == F08_STORY_KEY
    assert F02_SECTION_KEY == F08_SECTION_KEY
    assert F02_EVIDENCE_TRACE_KEY == F08_EVIDENCE_TRACE_KEY

    run = _run()
    assert len(run.bindings) == 5
    by_key = {item.key: item for item in run.authorities}
    assert len(by_key) == 5
    assert set(by_key) == {F02_BEAM_WIDTH_KEY, BEAM_DEPTH_KEY, F02_STORY_KEY, F02_SECTION_KEY, F02_EVIDENCE_TRACE_KEY}
    assert all(item.grain is Grain.COMPONENT and item.scope_ref == COMPONENT_ID and item.direction is None for item in run.authorities)
    assert by_key[F02_BEAM_WIDTH_KEY].value == 249.0
    assert by_key[BEAM_DEPTH_KEY].value == 600.0
    assert by_key[F02_STORY_KEY].value == STORY
    assert by_key[F02_SECTION_KEY].value == SECTION
    assert all(item.availability is AvailabilityState.RESOLVED for item in run.authorities)
    assert by_key[F02_EVIDENCE_TRACE_KEY].population_completeness is PopulationCompleteness.FULL

    for key, feature_ref in (
        (F02_BEAM_WIDTH_KEY, "feature:beam_width_mm"),
        (BEAM_DEPTH_KEY, "feature:beam_depth_mm"),
        (F02_EVIDENCE_TRACE_KEY, "feature:beam_geometry_trace"),
    ):
        authority = by_key[key]
        assert "epoch:VS0-E1" in authority.provenance_refs
        assert "snapshot:beam:B42" in authority.provenance_refs
        assert feature_ref in authority.provenance_refs
        assert any(ref.startswith("evidence:") for ref in authority.provenance_refs)
    trace = by_key[F02_EVIDENCE_TRACE_KEY].value[0]
    assert (trace["epoch_ref"], trace["component_type"], trace["component_id"], trace["feature_name"]) == (
        "epoch:VS0-E1", "beam", COMPONENT_ID, "beam_geometry_trace"
    )

    width = _result(run, BEAM_MIN_WIDTH_RULE_ID)
    depth = _result(run, BEAM_MIN_DEPTH_RULE_ID)
    ratio = _result(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID)
    assert width.status is CheckStatus.FAIL
    assert depth.status is CheckStatus.OK
    assert ratio.status is CheckStatus.OK
    assert ratio.value == pytest.approx(600.0 / 249.0)
    assert len(run.store.formal_results) == 3
    assert all(_closure(run, rule).execution_status is ClosureExecutionStatus.EXECUTED for rule in (
        BEAM_MIN_WIDTH_RULE_ID, BEAM_MIN_DEPTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID
    ))
    assert run.assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert run.assessment.incomplete_mandatory_instances == ()
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"

    check_findings, closure_findings = _findings(run)
    assert len(check_findings) == 1 and closure_findings == ()
    finding = check_findings[0]
    assert finding.source_kind is FindingSourceKind.CHECK_RESULT
    assert finding.source_status is CheckStatus.FAIL
    assert finding.scope_ref == COMPONENT_ID
    assert finding.rule_instance_ref == _instance(run, BEAM_MIN_WIDTH_RULE_ID)


def test_vs0_missing_width_invalidates_only_width_consumers() -> None:
    run = _run(snapshot=_snapshot(
        width=None,
        width_status=FeatureValueStatus.MISSING,
        width_evidence=FeatureEvidenceStatus.MISSING,
    ))
    by_key = {item.key: item for item in run.authorities}
    width = by_key[F02_BEAM_WIDTH_KEY]
    assert width.value is None
    assert (width.availability, width.population_completeness) == (
        AvailabilityState.NO_DATA, PopulationCompleteness.INCOMPLETE
    )
    assert (by_key[BEAM_DEPTH_KEY].availability, by_key[BEAM_DEPTH_KEY].population_completeness) == (
        AvailabilityState.RESOLVED, PopulationCompleteness.FULL
    )
    trace = by_key[F02_EVIDENCE_TRACE_KEY]
    assert (trace.availability, trace.population_completeness) == (
        AvailabilityState.RESOLVED, PopulationCompleteness.FULL
    )
    assert trace.value[0]["source_row"]["Width"] is None
    assert trace.value[0]["source_row"]["Depth"] == 600.0

    assert _result(run, BEAM_MIN_WIDTH_RULE_ID) is None
    assert _result(run, BEAM_MIN_DEPTH_RULE_ID).status is CheckStatus.OK
    assert _result(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID) is None
    assert _closure(run, BEAM_MIN_WIDTH_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA
    assert _closure(run, BEAM_MIN_DEPTH_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert _closure(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA
    assert run.assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert {item.rule_id for item in run.assessment.incomplete_mandatory_instances} == {
        BEAM_MIN_WIDTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID
    }
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"
    checks, closures = _findings(run)
    assert checks == () and len(closures) == 2
    assert {item.rule_instance_ref.rule_id for item in closures} == {
        BEAM_MIN_WIDTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID
    }
    assert all(item.source_kind is FindingSourceKind.RULE_CLOSURE and item.source_status is ClosureExecutionStatus.NO_DATA for item in closures)


def test_vs0_partial_width_blocks_only_width_consumers() -> None:
    run = _run(snapshot=_snapshot(
        width=249.0,
        width_status=FeatureValueStatus.PARTIAL,
        width_evidence=FeatureEvidenceStatus.PARTIAL,
    ))
    width = {item.key: item for item in run.authorities}[F02_BEAM_WIDTH_KEY]
    assert (width.availability, width.population_completeness) == (
        AvailabilityState.BLOCKED, PopulationCompleteness.INCOMPLETE
    )
    assert _result(run, BEAM_MIN_WIDTH_RULE_ID) is None
    assert _result(run, BEAM_MIN_DEPTH_RULE_ID).status is CheckStatus.OK
    assert _result(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID) is None
    assert _closure(run, BEAM_MIN_WIDTH_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _closure(run, BEAM_MIN_DEPTH_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert _closure(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert run.assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    checks, closures = _findings(run)
    assert checks == () and len(closures) == 2
    assert all(item.source_status is ClosureExecutionStatus.BLOCKED for item in closures)


def test_vs0_missing_depth_invalidates_only_depth_consumers() -> None:
    run = _run(snapshot=_snapshot(
        depth=None,
        depth_status=FeatureValueStatus.MISSING,
        depth_evidence=FeatureEvidenceStatus.MISSING,
    ))
    by_key = {item.key: item for item in run.authorities}
    assert by_key[F02_BEAM_WIDTH_KEY].availability is AvailabilityState.RESOLVED
    assert (by_key[BEAM_DEPTH_KEY].availability, by_key[BEAM_DEPTH_KEY].population_completeness) == (
        AvailabilityState.NO_DATA, PopulationCompleteness.INCOMPLETE
    )
    assert by_key[F02_EVIDENCE_TRACE_KEY].population_completeness is PopulationCompleteness.FULL
    assert _result(run, BEAM_MIN_WIDTH_RULE_ID).status is CheckStatus.FAIL
    assert _result(run, BEAM_MIN_DEPTH_RULE_ID) is None
    assert _result(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID) is None
    assert _closure(run, BEAM_MIN_WIDTH_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert _closure(run, BEAM_MIN_DEPTH_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA
    assert _closure(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA
    checks, closures = _findings(run)
    assert len(checks) == 1 and checks[0].rule_instance_ref.rule_id == BEAM_MIN_WIDTH_RULE_ID
    assert {item.rule_instance_ref.rule_id for item in closures} == {
        BEAM_MIN_DEPTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID
    }
    assert all(item.source_status is ClosureExecutionStatus.NO_DATA for item in closures)


def test_vs0_incomplete_common_trace_rejects_compile() -> None:
    epoch = _epoch()
    snapshot = _snapshot(
        trace_status=FeatureValueStatus.PARTIAL,
        trace_evidence=FeatureEvidenceStatus.PARTIAL,
    )
    bindings = _bindings()
    authorities = build_component_f0_authorities(epoch=epoch, snapshot=snapshot, bindings=bindings)
    trace = {item.key: item for item in authorities}[F02_EVIDENCE_TRACE_KEY]
    assert (trace.availability, trace.population_completeness) == (
        AvailabilityState.BLOCKED, PopulationCompleteness.INCOMPLETE
    )
    assert all(
        {item.key: item for item in authorities}[key].availability is AvailabilityState.RESOLVED
        for key in (F02_BEAM_WIDTH_KEY, BEAM_DEPTH_KEY)
    )
    inputs = build_f0_compile_inputs(rule_targets=_targets(), external_authorities=authorities)
    with pytest.raises(KernelCompileError, match="FULL population requirement is not satisfiable"):
        RegulatoryCompiler.compile(VS0_BEAM_REGISTRY, inputs)


def test_vs0_reacquire_creates_new_epoch_plan_and_result_without_mutating_e1() -> None:
    e1 = _run()
    e1_epoch_before = e1.epoch.as_dict()
    old_finding = _findings(e1)[0][0]
    old_finding_state = (
        old_finding.finding_id, old_finding.source_kind, old_finding.source_status,
        old_finding.scope_ref, old_finding.rule_instance_ref,
    )
    e2 = _run(
        epoch=_epoch("VS0-E2", origin=EvidenceEpochOrigin.REACQUIRE, predecessor="VS0-E1"),
        snapshot=_snapshot(width=250.0, depth=600.0),
    )
    assert e2.epoch.origin is EvidenceEpochOrigin.REACQUIRE
    assert e2.epoch.predecessor_epoch_ref == "VS0-E1"
    assert e1.epoch.as_dict() == e1_epoch_before
    assert {item.authority_id for item in e1.authorities}.isdisjoint(
        {item.authority_id for item in e2.authorities}
    )
    assert e1.program.plan.plan_identity != e2.program.plan.plan_identity
    assert all(result.result.evidence[0]["epoch_ref"] == "epoch:VS0-E1" for result in e1.store.formal_results)
    assert all(result.result.evidence[0]["epoch_ref"] == "epoch:VS0-E2" for result in e2.store.formal_results)
    assert _result(e1, BEAM_MIN_WIDTH_RULE_ID).status is CheckStatus.FAIL
    assert _result(e2, BEAM_MIN_WIDTH_RULE_ID).status is CheckStatus.OK
    assert all(record.result.status is CheckStatus.OK for record in e2.store.formal_results)
    assert all(outcome.execution_status is ClosureExecutionStatus.EXECUTED for outcome in e2.assessment.closure_outcomes)
    assert e2.assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert _findings(e2) == ((), ())
    assert (
        old_finding.finding_id, old_finding.source_kind, old_finding.source_status,
        old_finding.scope_ref, old_finding.rule_instance_ref,
    ) == old_finding_state
    assert old_finding.source_status is CheckStatus.FAIL
    with pytest.raises(FrozenInstanceError):
        old_finding.source_status = CheckStatus.OK  # type: ignore[misc]


def test_vs0_equivalent_input_permutations_are_deterministic() -> None:
    first = _run()
    second = _run(reverse_bindings=True, reverse_targets=True, reverse_registry=True)
    assert first.epoch == second.epoch
    assert first.snapshot == second.snapshot
    assert first.authorities == second.authorities
    assert tuple(item.authority_id for item in first.authorities) == tuple(item.authority_id for item in second.authorities)
    assert first.inputs == second.inputs
    assert first.registry.registry_version == second.registry.registry_version
    assert first.program.plan.plan_identity == second.program.plan.plan_identity
    assert first.program.plan.deterministic_execution_order == second.program.plan.deterministic_execution_order
    assert first.program.plan.compiled_closure_inventory == second.program.plan.compiled_closure_inventory
    assert first.store == second.store
    assert first.assessment == second.assessment
    assert _findings(first) == _findings(second)


def test_vs0_source_has_no_authority_or_legacy_bypass() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "ExternalDependency" + "Authority(",
        "RegulatoryCompile" + "Inputs(",
        "Check" + "Result(",
        "Find" + "ing(",
        "Minimal" + "CheckEngine",
        "tbdy_engine." + "product_" + "reports",
        "tbdy_engine.checks." + "engine",
        "tbdy_engine.checks." + "member_" + "geometry",
        "tbdy_engine.checks." + "wall_" + "evaluators",
        "tbdy_engine." + "cata" + "logs",
        "\n" + "import " + "ya" + "ml",
        "tbdy_engine." + "eta" + "bs",
        "packages." + "etabs_" + "gateway",
        "Mutation" + "Executor",
        "Remediation" + "Plan",
        "evaluate_beam_min_" + "width(",
        "evaluate_beam_min_" + "depth(",
        "evaluate_beam_depth_width_" + "ratio(",
        "evaluate_member_" + "rule(",
    )
    assert all(token not in source for token in forbidden)
    nondeterministic = (
        "uuid" + ".", "random" + ".", "datetime" + ".now(",
        "time" + ".time(", "hash" + "(",
    )
    assert all(token not in source for token in nondeterministic)
