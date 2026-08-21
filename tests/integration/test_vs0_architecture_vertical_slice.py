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
class _PreparedSlice:
    epoch: EvidenceEpoch
    snapshot: FeatureSnapshot
    authorities: tuple[object, ...]
    inputs: object


@dataclass(frozen=True, slots=True)
class _ExecutedSlice:
    prepared: _PreparedSlice
    registry: RegulatoryRegistry
    program: object
    store: object
    assessment: object
    check_findings: tuple[object, ...]
    closure_findings: tuple[object, ...]


def _reason(status: FeatureEvidenceStatus, label: str) -> str | None:
    if status is FeatureEvidenceStatus.FULL:
        return None
    return f"fixture {label} evidence unavailable" if status is FeatureEvidenceStatus.MISSING else f"fixture {label} evidence partial"


def _geometry_evidence(
    *,
    source_column: str,
    raw_value: object,
    normalized_value: object,
    width_value: object,
    depth_value: object,
    status: FeatureEvidenceStatus,
    resolver: str,
    label: str,
) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=status,
        source_table="vs0_fixture_frame_section_geometry",
        actual_table_name="VS0 Fixture Frame Section Geometry",
        source_column=source_column,
        source_row={
            "Story": STORY,
            "Label": COMPONENT_ID,
            "Section": SECTION,
            "Width": width_value,
            "Depth": depth_value,
        },
        raw_value=raw_value,
        normalized_value=normalized_value,
        unit="mm",
        resolver=resolver,
        reason=_reason(status, label),
    )


def _trace_evidence(
    *,
    width_value: object,
    depth_value: object,
    status: FeatureEvidenceStatus,
) -> FeatureEvidence:
    capture = {
        "Story": STORY,
        "Label": COMPONENT_ID,
        "Section": SECTION,
        "Width": width_value,
        "Depth": depth_value,
    }
    return FeatureEvidence(
        evidence_status=status,
        source_table="vs0_fixture_frame_section_geometry",
        actual_table_name="VS0 Fixture Frame Section Geometry",
        source_column="ComponentGeometryCapture",
        source_row=capture,
        raw_value=capture,
        normalized_value=capture,
        unit="",
        resolver="vs0-fixture-component-capture",
        reason=_reason(status, "component capture trace"),
    )


def _snapshot(
    *,
    width_value: float | None,
    depth_value: float | None,
    width_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    width_evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    depth_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    depth_evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    trace_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    trace_evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
) -> FeatureSnapshot:
    width_evidence = _geometry_evidence(
        source_column="Width",
        raw_value=width_value,
        normalized_value=width_value,
        width_value=width_value,
        depth_value=depth_value,
        status=width_evidence_status,
        resolver="vs0-fixture-frame-geometry",
        label="width value",
    )
    depth_evidence = _geometry_evidence(
        source_column="Depth",
        raw_value=depth_value,
        normalized_value=depth_value,
        width_value=width_value,
        depth_value=depth_value,
        status=depth_evidence_status,
        resolver="vs0-fixture-frame-geometry",
        label="depth value",
    )
    trace_evidence = _trace_evidence(
        width_value=width_value,
        depth_value=depth_value,
        status=trace_evidence_status,
    )
    return FeatureSnapshot(
        component_type="beam",
        component_id=COMPONENT_ID,
        identity={"story": STORY, "section": SECTION},
        features={
            "beam_width_mm": FeatureValue(
                feature_name="beam_width_mm",
                value=width_value,
                unit="mm",
                semantic_role="GEOMETRY",
                status=width_status,
                evidence=(width_evidence,),
            ),
            "beam_depth_mm": FeatureValue(
                feature_name="beam_depth_mm",
                value=depth_value,
                unit="mm",
                semantic_role="GEOMETRY",
                status=depth_status,
                evidence=(depth_evidence,),
            ),
            "beam_geometry_trace": FeatureValue(
                feature_name="beam_geometry_trace",
                value="CAPTURED",
                unit="",
                semantic_role="TRACEABILITY",
                status=trace_status,
                evidence=(trace_evidence,),
            ),
        },
    )


def _epoch(
    epoch_id: str = "VS0-E1",
    *,
    origin: EvidenceEpochOrigin = EvidenceEpochOrigin.FIXTURE_REPLAY,
    predecessor_epoch_ref: str | None = None,
) -> EvidenceEpoch:
    suffix = epoch_id.casefold().replace("vs0-", "")
    return EvidenceEpoch(
        epoch_id=epoch_id,
        origin=origin,
        model_fingerprint=f"model:fixture:vs0:{suffix}",
        source_fingerprint=f"source:fixture:vs0:{suffix}",
        predecessor_epoch_ref=predecessor_epoch_ref,
        provenance_refs=(f"capture:vs0:B42:{epoch_id.removeprefix('VS0-')}",),
    )


def _bindings(*, reverse: bool = False) -> tuple[F0EvidenceBinding, ...]:
    items = (
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
    return tuple(reversed(items)) if reverse else items


def _targets(*, reverse: bool = False) -> tuple[RuleScopeTarget, ...]:
    items = (
        RuleScopeTarget(
            rule_id=BEAM_MIN_WIDTH_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=COMPONENT_ID,
            direction=None,
            applicability_input=BeamMinWidthApplicabilityInput(
                component_type="beam",
                tbdy_7411_applies=True,
            ),
        ),
        RuleScopeTarget(
            rule_id=BEAM_MIN_DEPTH_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=COMPONENT_ID,
            direction=None,
            applicability_input=Beam7411ApplicabilityInput(
                is_beam=True,
                tbdy_7411_applies=True,
            ),
        ),
        RuleScopeTarget(
            rule_id=BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
            grain=Grain.COMPONENT,
            scope_ref=COMPONENT_ID,
            direction=None,
            applicability_input=Beam7411ApplicabilityInput(
                is_beam=True,
                tbdy_7411_applies=True,
            ),
        ),
    )
    return tuple(reversed(items)) if reverse else items


def _prepare(
    *,
    epoch: EvidenceEpoch | None = None,
    width_value: float | None = 249.0,
    depth_value: float | None = 600.0,
    width_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    width_evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    depth_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    depth_evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    trace_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    trace_evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    reverse_bindings: bool = False,
    reverse_targets: bool = False,
) -> _PreparedSlice:
    epoch = epoch or _epoch()
    snapshot = _snapshot(
        width_value=width_value,
        depth_value=depth_value,
        width_status=width_status,
        width_evidence_status=width_evidence_status,
        depth_status=depth_status,
        depth_evidence_status=depth_evidence_status,
        trace_status=trace_status,
        trace_evidence_status=trace_evidence_status,
    )
    authorities = build_component_f0_authorities(
        epoch=epoch,
        snapshot=snapshot,
        bindings=_bindings(reverse=reverse_bindings),
    )
    inputs = build_f0_compile_inputs(
        rule_targets=_targets(reverse=reverse_targets),
        external_authorities=authorities,
    )
    return _PreparedSlice(epoch, snapshot, authorities, inputs)


def _collect_findings(program, store) -> tuple[tuple[object, ...], tuple[object, ...]]:
    records = {
        item.instance_id: item
        for item in program.plan.compiled_closure_inventory
    }
    check_findings = []
    closure_findings = []
    for instance in program.plan.compiled_rule_instances:
        for result in store.formal_results_for(instance):
            finding = build_finding_from_check_result(
                instance_id=instance,
                result=result,
            )
            if finding is not None:
                check_findings.append(finding)
        outcome = store.outcome_for(instance)
        assert outcome is not None
        finding = build_finding_from_rule_closure(
            compiled_record=records[instance],
            outcome=outcome,
        )
        if finding is not None:
            closure_findings.append(finding)
    return (
        tuple(sorted(check_findings, key=lambda item: item.finding_id)),
        tuple(sorted(closure_findings, key=lambda item: item.finding_id)),
    )


def _execute(
    prepared: _PreparedSlice,
    *,
    registry: RegulatoryRegistry = VS0_BEAM_REGISTRY,
) -> _ExecutedSlice:
    program = RegulatoryCompiler.compile(registry, prepared.inputs)
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)
    check_findings, closure_findings = _collect_findings(program, store)
    return _ExecutedSlice(
        prepared,
        registry,
        program,
        store,
        assessment,
        check_findings,
        closure_findings,
    )


def _authority_by_key(run: _PreparedSlice) -> dict[object, object]:
    return {item.key: item for item in run.authorities}


def _instance(run: _ExecutedSlice, rule_id):
    return next(
        item
        for item in run.program.plan.compiled_rule_instances
        if item.rule_id == rule_id
    )


def _result_by_rule(run: _ExecutedSlice) -> dict[str, object]:
    return {
        record.result.check_id: record.result
        for record in run.store.formal_results
    }


def _outcome(run: _ExecutedSlice, rule_id):
    instance = _instance(run, rule_id)
    outcome = run.store.outcome_for(instance)
    assert outcome is not None
    return outcome


def test_vs0_complete_beam_slice_runs_from_snapshot_epoch_to_finding() -> None:
    assert VS0_BEAM_REGISTRY.rule_count == 3
    assert VS0_BEAM_REGISTRY.derivations == ()
    assert len({item.rule_id for item in VS0_BEAM_REGISTRY.checks}) == 3

    assert F02_BEAM_WIDTH_KEY == F08_BEAM_WIDTH_KEY
    assert F02_STORY_KEY == F08_STORY_KEY
    assert F02_SECTION_KEY == F08_SECTION_KEY
    assert F02_EVIDENCE_TRACE_KEY == F08_EVIDENCE_TRACE_KEY

    run = _execute(_prepare())
    authorities = _authority_by_key(run.prepared)
    assert len(run.prepared.authorities) == 5
    assert set(authorities) == {
        F02_BEAM_WIDTH_KEY,
        BEAM_DEPTH_KEY,
        F02_STORY_KEY,
        F02_SECTION_KEY,
        F02_EVIDENCE_TRACE_KEY,
    }
    assert all(item.grain is Grain.COMPONENT for item in run.prepared.authorities)
    assert all(item.scope_ref == COMPONENT_ID for item in run.prepared.authorities)
    assert all(item.direction is None for item in run.prepared.authorities)

    width = authorities[F02_BEAM_WIDTH_KEY]
    depth = authorities[BEAM_DEPTH_KEY]
    story = authorities[F02_STORY_KEY]
    section = authorities[F02_SECTION_KEY]
    trace = authorities[F02_EVIDENCE_TRACE_KEY]
    assert width.value == 249.0 and width.unit == UNIT_MM
    assert depth.value == 600.0 and depth.unit == UNIT_MM
    assert story.value == STORY
    assert section.value == SECTION
    assert all(
        item.availability is AvailabilityState.RESOLVED
        for item in (width, depth, story, section, trace)
    )
    assert trace.population_completeness is PopulationCompleteness.FULL

    for authority, feature_ref in (
        (width, "feature:beam_width_mm"),
        (depth, "feature:beam_depth_mm"),
        (trace, "feature:beam_geometry_trace"),
    ):
        assert "epoch:VS0-E1" in authority.provenance_refs
        assert "snapshot:beam:B42" in authority.provenance_refs
        assert feature_ref in authority.provenance_refs
        assert any(ref.startswith("evidence:") for ref in authority.provenance_refs)
    trace_row = trace.value[0]
    assert trace_row["epoch_ref"] == "epoch:VS0-E1"
    assert trace_row["component_type"] == "beam"
    assert trace_row["component_id"] == COMPONENT_ID
    assert trace_row["feature_name"] == "beam_geometry_trace"

    results = _result_by_rule(run)
    assert len(results) == 3
    assert results[BEAM_MIN_WIDTH_RULE_ID.value].status is CheckStatus.FAIL
    assert results[BEAM_MIN_DEPTH_RULE_ID.value].status is CheckStatus.OK
    assert results[BEAM_DEPTH_WIDTH_RATIO_RULE_ID.value].status is CheckStatus.OK
    assert results[BEAM_DEPTH_WIDTH_RATIO_RULE_ID.value].ratio == pytest.approx(
        (600.0 / 249.0) / 3.5
    )
    assert results[BEAM_DEPTH_WIDTH_RATIO_RULE_ID.value].value == pytest.approx(
        600.0 / 249.0
    )
    assert all(
        _outcome(run, rule_id).execution_status is ClosureExecutionStatus.EXECUTED
        for rule_id in (
            BEAM_MIN_WIDTH_RULE_ID,
            BEAM_MIN_DEPTH_RULE_ID,
            BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
        )
    )
    assert run.assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert run.assessment.incomplete_mandatory_instances == ()
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"

    assert len(run.check_findings) == 1
    assert run.closure_findings == ()
    finding = run.check_findings[0]
    assert finding.source_kind is FindingSourceKind.CHECK_RESULT
    assert finding.source_status is CheckStatus.FAIL
    assert finding.scope_ref == COMPONENT_ID
    assert finding.rule_instance_ref == _instance(run, BEAM_MIN_WIDTH_RULE_ID)


def test_vs0_missing_width_invalidates_only_width_consumers() -> None:
    run = _execute(
        _prepare(
            width_value=None,
            width_status=FeatureValueStatus.MISSING,
            width_evidence_status=FeatureEvidenceStatus.MISSING,
        )
    )
    authorities = _authority_by_key(run.prepared)
    width = authorities[F02_BEAM_WIDTH_KEY]
    depth = authorities[BEAM_DEPTH_KEY]
    trace = authorities[F02_EVIDENCE_TRACE_KEY]
    assert width.value is None
    assert width.availability is AvailabilityState.NO_DATA
    assert width.population_completeness is PopulationCompleteness.INCOMPLETE
    assert depth.availability is AvailabilityState.RESOLVED
    assert depth.population_completeness is PopulationCompleteness.FULL
    assert trace.availability is AvailabilityState.RESOLVED
    assert trace.population_completeness is PopulationCompleteness.FULL
    assert trace.value[0]["source_row"]["Width"] is None
    assert trace.value[0]["source_row"]["Depth"] == 600.0

    results = _result_by_rule(run)
    assert set(results) == {BEAM_MIN_DEPTH_RULE_ID.value}
    assert results[BEAM_MIN_DEPTH_RULE_ID.value].status is CheckStatus.OK
    assert _outcome(run, BEAM_MIN_WIDTH_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA
    assert _outcome(run, BEAM_MIN_DEPTH_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert _outcome(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA

    assert run.assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert {
        item.rule_id for item in run.assessment.incomplete_mandatory_instances
    } == {BEAM_MIN_WIDTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID}
    assert all(
        item.rule_id != BEAM_MIN_DEPTH_RULE_ID
        for item in run.assessment.incomplete_mandatory_instances
    )
    assert run.assessment.full_tbdy_compliance_status == "NOT_EVALUATED"

    assert run.check_findings == ()
    assert len(run.closure_findings) == 2
    assert {
        item.rule_instance_ref.rule_id for item in run.closure_findings
    } == {BEAM_MIN_WIDTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID}
    assert all(
        item.source_kind is FindingSourceKind.RULE_CLOSURE
        and item.source_status is ClosureExecutionStatus.NO_DATA
        for item in run.closure_findings
    )


def test_vs0_partial_width_blocks_only_width_consumers() -> None:
    run = _execute(
        _prepare(
            width_value=249.0,
            width_status=FeatureValueStatus.PARTIAL,
            width_evidence_status=FeatureEvidenceStatus.PARTIAL,
        )
    )
    width = _authority_by_key(run.prepared)[F02_BEAM_WIDTH_KEY]
    assert width.availability is AvailabilityState.BLOCKED
    assert width.population_completeness is PopulationCompleteness.INCOMPLETE

    results = _result_by_rule(run)
    assert set(results) == {BEAM_MIN_DEPTH_RULE_ID.value}
    assert results[BEAM_MIN_DEPTH_RULE_ID.value].status is CheckStatus.OK
    assert _outcome(run, BEAM_MIN_WIDTH_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert _outcome(run, BEAM_MIN_DEPTH_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert _outcome(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID).execution_status is ClosureExecutionStatus.BLOCKED
    assert run.assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE
    assert len(run.closure_findings) == 2
    assert all(
        item.source_kind is FindingSourceKind.RULE_CLOSURE
        and item.source_status is ClosureExecutionStatus.BLOCKED
        for item in run.closure_findings
    )


def test_vs0_missing_depth_invalidates_only_depth_consumers() -> None:
    run = _execute(
        _prepare(
            depth_value=None,
            depth_status=FeatureValueStatus.MISSING,
            depth_evidence_status=FeatureEvidenceStatus.MISSING,
        )
    )
    authorities = _authority_by_key(run.prepared)
    assert authorities[F02_BEAM_WIDTH_KEY].availability is AvailabilityState.RESOLVED
    assert authorities[BEAM_DEPTH_KEY].availability is AvailabilityState.NO_DATA
    assert authorities[BEAM_DEPTH_KEY].population_completeness is PopulationCompleteness.INCOMPLETE
    assert authorities[F02_EVIDENCE_TRACE_KEY].population_completeness is PopulationCompleteness.FULL

    results = _result_by_rule(run)
    assert set(results) == {BEAM_MIN_WIDTH_RULE_ID.value}
    assert results[BEAM_MIN_WIDTH_RULE_ID.value].status is CheckStatus.FAIL
    assert _outcome(run, BEAM_MIN_WIDTH_RULE_ID).execution_status is ClosureExecutionStatus.EXECUTED
    assert _outcome(run, BEAM_MIN_DEPTH_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA
    assert _outcome(run, BEAM_DEPTH_WIDTH_RATIO_RULE_ID).execution_status is ClosureExecutionStatus.NO_DATA

    assert len(run.check_findings) == 1
    assert run.check_findings[0].source_status is CheckStatus.FAIL
    assert run.check_findings[0].rule_instance_ref.rule_id == BEAM_MIN_WIDTH_RULE_ID
    assert len(run.closure_findings) == 2
    assert {
        item.rule_instance_ref.rule_id for item in run.closure_findings
    } == {BEAM_MIN_DEPTH_RULE_ID, BEAM_DEPTH_WIDTH_RATIO_RULE_ID}
    assert all(
        item.source_status is ClosureExecutionStatus.NO_DATA
        for item in run.closure_findings
    )


def test_vs0_incomplete_common_trace_rejects_compile() -> None:
    prepared = _prepare(
        trace_status=FeatureValueStatus.PARTIAL,
        trace_evidence_status=FeatureEvidenceStatus.PARTIAL,
    )
    authorities = _authority_by_key(prepared)
    assert authorities[F02_BEAM_WIDTH_KEY].availability is AvailabilityState.RESOLVED
    assert authorities[BEAM_DEPTH_KEY].availability is AvailabilityState.RESOLVED
    trace = authorities[F02_EVIDENCE_TRACE_KEY]
    assert trace.availability is AvailabilityState.BLOCKED
    assert trace.population_completeness is PopulationCompleteness.INCOMPLETE

    with pytest.raises(
        KernelCompileError,
        match="FULL population requirement is not satisfiable",
    ):
        RegulatoryCompiler.compile(VS0_BEAM_REGISTRY, prepared.inputs)


def test_vs0_reacquire_creates_new_epoch_plan_and_result_without_mutating_e1() -> None:
    e1 = _execute(_prepare())
    old_epoch_state = e1.prepared.epoch.as_dict()
    old_finding = e1.check_findings[0]
    old_finding_state = (
        old_finding.finding_id,
        old_finding.source_kind,
        old_finding.source_status,
        old_finding.scope_ref,
        old_finding.rule_instance_ref,
    )

    e2_epoch = _epoch(
        "VS0-E2",
        origin=EvidenceEpochOrigin.REACQUIRE,
        predecessor_epoch_ref="VS0-E1",
    )
    e2 = _execute(_prepare(epoch=e2_epoch, width_value=250.0, depth_value=600.0))

    assert e2.prepared.epoch.origin is EvidenceEpochOrigin.REACQUIRE
    assert e2.prepared.epoch.predecessor_epoch_ref == "VS0-E1"
    assert e1.prepared.epoch.as_dict() == old_epoch_state

    e1_ids = {item.authority_id for item in e1.prepared.authorities}
    e2_ids = {item.authority_id for item in e2.prepared.authorities}
    assert e1_ids.isdisjoint(e2_ids)
    assert e1.program.plan.plan_identity != e2.program.plan.plan_identity

    for result in _result_by_rule(e1).values():
        assert result.evidence[0]["epoch_ref"] == "epoch:VS0-E1"
    for result in _result_by_rule(e2).values():
        assert result.evidence[0]["epoch_ref"] == "epoch:VS0-E2"

    assert _result_by_rule(e1)[BEAM_MIN_WIDTH_RULE_ID.value].status is CheckStatus.FAIL
    assert _result_by_rule(e2)[BEAM_MIN_WIDTH_RULE_ID.value].status is CheckStatus.OK
    assert all(
        item.status is CheckStatus.OK
        for item in _result_by_rule(e2).values()
    )
    assert all(
        _outcome(e2, rule_id).execution_status is ClosureExecutionStatus.EXECUTED
        for rule_id in (
            BEAM_MIN_WIDTH_RULE_ID,
            BEAM_MIN_DEPTH_RULE_ID,
            BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
        )
    )
    assert e2.assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert e2.check_findings == ()
    assert e2.closure_findings == ()

    assert (
        old_finding.finding_id,
        old_finding.source_kind,
        old_finding.source_status,
        old_finding.scope_ref,
        old_finding.rule_instance_ref,
    ) == old_finding_state
    assert old_finding.source_status is CheckStatus.FAIL
    with pytest.raises(FrozenInstanceError):
        old_finding.source_status = CheckStatus.OK  # type: ignore[misc]


def test_vs0_equivalent_input_permutations_are_deterministic() -> None:
    first = _execute(_prepare())
    reverse_registry = RegulatoryRegistry(
        checks=tuple(reversed(VS0_BEAM_REGISTRY.checks))
    )
    second = _execute(
        _prepare(reverse_bindings=True, reverse_targets=True),
        registry=reverse_registry,
    )

    assert first.prepared.epoch == second.prepared.epoch
    assert first.prepared.snapshot == second.prepared.snapshot
    assert first.prepared.authorities == second.prepared.authorities
    assert tuple(item.authority_id for item in first.prepared.authorities) == tuple(
        item.authority_id for item in second.prepared.authorities
    )
    assert first.prepared.inputs == second.prepared.inputs
    assert first.registry.registry_version == second.registry.registry_version
    assert first.program.plan.plan_identity == second.program.plan.plan_identity
    assert (
        first.program.plan.deterministic_execution_order
        == second.program.plan.deterministic_execution_order
    )
    assert (
        first.program.plan.compiled_closure_inventory
        == second.program.plan.compiled_closure_inventory
    )
    assert first.store == second.store
    assert first.assessment == second.assessment
    assert first.check_findings == second.check_findings
    assert first.closure_findings == second.closure_findings


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
        "uuid" + ".",
        "random" + ".",
        "datetime" + ".now(",
        "time" + ".time(",
        "hash" + "(",
    )
    assert all(token not in source for token in nondeterministic)
