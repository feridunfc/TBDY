from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.integration.f0_evidence_adapter import (
    EvidenceAuthorityAdapterError,
    EvidenceBindingSource,
    F0EvidenceBinding,
    build_component_f0_authorities,
    build_f0_compile_inputs,
)
from tbdy_engine.regulatory.beam_min_width import (
    BEAM_WIDTH_KEY,
    EVIDENCE_TRACE_KEY,
    F0_2_BEAM_MIN_WIDTH_REGISTRY,
    RULE_ID,
    SECTION_KEY,
    STORY_KEY,
    BeamMinWidthApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencyKey,
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
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_MM

COMPONENT_ID = "B1"
STORY = "STORY1"
SECTION = "B300x500"


def _epoch(epoch_id: str = "E17", *, predecessor: str | None = None) -> EvidenceEpoch:
    return EvidenceEpoch(
        epoch_id=epoch_id,
        model_fingerprint="model:fixture:sha256:abc",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
        source_fingerprint="source:fixture:sha256:def",
        predecessor_epoch_ref=predecessor,
        provenance_refs=("capture:fixture:beam-B1",),
    )


def _evidence(
    width_mm: float,
    *,
    status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    unit: str = "mm",
) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=status,
        source_table="frame_section_assignments",
        actual_table_name="Frame Section Assignments",
        source_column="Width",
        source_row={"Story": STORY, "Label": COMPONENT_ID, "Section": SECTION, "Width": width_mm},
        raw_value=width_mm,
        normalized_value=width_mm,
        unit=unit,
        resolver="fixture-explicit-beam-width",
        reason=None if status is FeatureEvidenceStatus.FULL else "fixture incomplete evidence",
    )


def _snapshot(
    width_mm: float = 250.0,
    *,
    feature_status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
    evidence_status: FeatureEvidenceStatus = FeatureEvidenceStatus.FULL,
    feature_unit: str = "mm",
    include_story: bool = True,
    include_section: bool = True,
) -> FeatureSnapshot:
    evidence = _evidence(width_mm, status=evidence_status, unit=feature_unit)
    feature = FeatureValue(
        feature_name="beam_width_mm",
        value=width_mm if feature_status is not FeatureValueStatus.MISSING else None,
        unit=feature_unit,
        semantic_role="GEOMETRY",
        status=feature_status,
        evidence=(evidence,),
    )
    identity: dict[str, object] = {}
    if include_story:
        identity["story"] = STORY
    if include_section:
        identity["section"] = SECTION
    return FeatureSnapshot(
        component_type="beam",
        component_id=COMPONENT_ID,
        identity=identity,
        features={"beam_width_mm": feature},
    )


def _bindings() -> tuple[F0EvidenceBinding, ...]:
    return (
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_width_mm",
            dependency_key=BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
            source_key="story",
            dependency_key=STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            unit=UNIT_ENUM_STATE,
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
            source_key="section",
            dependency_key=SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            physical_dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            unit=UNIT_ENUM_STATE,
        ),
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.EVIDENCE_TRACE,
            source_key="beam_width_mm",
            dependency_key=EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            physical_dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT,
            unit=UNIT_DIMENSIONLESS,
        ),
    )


def _target() -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=RULE_ID,
        grain=Grain.COMPONENT,
        scope_ref=COMPONENT_ID,
        direction=None,
        applicability_input=BeamMinWidthApplicabilityInput(
            component_type="beam",
            tbdy_7411_applies=True,
        ),
    )


def _run(width_mm: float):
    epoch = _epoch()
    snapshot = _snapshot(width_mm)
    authorities = build_component_f0_authorities(
        epoch=epoch,
        snapshot=snapshot,
        bindings=_bindings(),
    )
    inputs = build_f0_compile_inputs(
        rule_targets=(_target(),),
        external_authorities=authorities,
    )
    program = RegulatoryCompiler.compile(F0_2_BEAM_MIN_WIDTH_REGISTRY, inputs)
    store = RegulatoryEngine.execute(program)
    instance = program.plan.compiled_rule_instances[0]
    results = store.formal_results_for(instance)
    assert len(results) == 1
    return epoch, snapshot, authorities, inputs, program, store, results[0]


def test_evidence_epoch_is_immutable_validated_and_deterministic() -> None:
    first = _epoch("E17", predecessor="E16")
    second = _epoch("E17", predecessor="E16")
    assert first == second
    assert first.as_dict() == second.as_dict()
    assert json.dumps(first.as_dict(), sort_keys=True) == json.dumps(second.as_dict(), sort_keys=True)
    assert first.predecessor_epoch_ref == "E16"
    with pytest.raises(FrozenInstanceError):
        first.epoch_id = "MUTATED"  # type: ignore[misc]
    with pytest.raises(ValueError):
        EvidenceEpoch(epoch_id="", model_fingerprint="model", origin="LIVE_CAPTURE")
    with pytest.raises(ValueError):
        EvidenceEpoch(epoch_id="E", model_fingerprint="", origin="LIVE_CAPTURE")
    with pytest.raises(ValueError):
        EvidenceEpoch(epoch_id="E", model_fingerprint="model", origin="UNKNOWN")


def test_new_epoch_preserves_old_epoch_as_immutable_history() -> None:
    old = _epoch("E17")
    before = old.as_dict()
    new = _epoch("E18", predecessor="E17")
    assert old.as_dict() == before
    assert old.epoch_id == "E17"
    assert new.epoch_id == "E18"
    assert new.predecessor_epoch_ref == "E17"


def test_resolved_full_feature_maps_to_resolved_fact_and_preserves_exact_value_unit() -> None:
    authorities = build_component_f0_authorities(epoch=_epoch(), snapshot=_snapshot(249.0), bindings=_bindings())
    width = next(item for item in authorities if item.key == BEAM_WIDTH_KEY)
    assert width.source_kind is DependencySourceKind.FACT
    assert width.value == 249.0
    assert width.unit == UNIT_MM
    assert width.availability is AvailabilityState.RESOLVED
    assert width.population_completeness is PopulationCompleteness.FULL
    assert "epoch:E17" in width.provenance_refs
    assert "snapshot:beam:B1" in width.provenance_refs
    assert "feature:beam_width_mm" in width.provenance_refs
    assert any(ref.startswith("evidence:") for ref in width.provenance_refs)


@pytest.mark.parametrize(
    ("feature_status", "evidence_status", "expected"),
    [
        (FeatureValueStatus.PARTIAL, FeatureEvidenceStatus.PARTIAL, AvailabilityState.BLOCKED),
        (FeatureValueStatus.MISSING, FeatureEvidenceStatus.MISSING, AvailabilityState.NO_DATA),
        (FeatureValueStatus.RESOLVED, FeatureEvidenceStatus.PARTIAL, AvailabilityState.BLOCKED),
    ],
)
def test_feature_readiness_fails_closed(
    feature_status: FeatureValueStatus,
    evidence_status: FeatureEvidenceStatus,
    expected: AvailabilityState,
) -> None:
    snapshot = _snapshot(
        250.0,
        feature_status=feature_status,
        evidence_status=evidence_status,
    )
    width_binding = (_bindings()[0],)
    authority = build_component_f0_authorities(epoch=_epoch(), snapshot=snapshot, bindings=width_binding)[0]
    assert authority.availability is expected
    if expected is not AvailabilityState.RESOLVED:
        assert authority.population_completeness is PopulationCompleteness.INCOMPLETE


def test_wrong_feature_source_unit_fails_closed_without_conversion_or_guessing() -> None:
    snapshot = _snapshot(25.0, feature_unit="cm")
    with pytest.raises(EvidenceAuthorityAdapterError, match="source unit mismatch"):
        build_component_f0_authorities(epoch=_epoch(), snapshot=snapshot, bindings=(_bindings()[0],))


def test_context_story_and_section_are_explicit_identity_bindings() -> None:
    authorities = build_component_f0_authorities(epoch=_epoch(), snapshot=_snapshot(), bindings=_bindings())
    by_key = {item.key: item for item in authorities}
    assert by_key[STORY_KEY].value == STORY
    assert by_key[SECTION_KEY].value == SECTION
    assert by_key[STORY_KEY].source_kind is DependencySourceKind.CONTEXT
    assert by_key[SECTION_KEY].source_kind is DependencySourceKind.CONTEXT
    assert by_key[STORY_KEY].availability is AvailabilityState.RESOLVED
    assert by_key[SECTION_KEY].availability is AvailabilityState.RESOLVED


def test_missing_explicit_identity_key_emits_no_data_without_fabrication() -> None:
    snapshot = _snapshot(include_story=False)
    story_binding = next(item for item in _bindings() if item.dependency_key == STORY_KEY)
    authority = build_component_f0_authorities(epoch=_epoch(), snapshot=snapshot, bindings=(story_binding,))[0]
    assert authority.value is None
    assert authority.availability is AvailabilityState.NO_DATA
    assert authority.population_completeness is PopulationCompleteness.INCOMPLETE
    assert "identity:story" in authority.provenance_refs


def test_identity_binding_does_not_infer_an_alternate_key() -> None:
    snapshot = FeatureSnapshot(
        component_type="beam",
        component_id=COMPONENT_ID,
        identity={"Story": STORY, "section": SECTION},
        features={"beam_width_mm": _snapshot().features["beam_width_mm"]},
    )
    story_binding = next(item for item in _bindings() if item.dependency_key == STORY_KEY)
    authority = build_component_f0_authorities(epoch=_epoch(), snapshot=snapshot, bindings=(story_binding,))[0]
    assert authority.availability is AvailabilityState.NO_DATA
    assert authority.value is None


def test_evidence_trace_projects_real_feature_evidence_with_epoch_and_is_immutable() -> None:
    trace_binding = next(item for item in _bindings() if item.dependency_key == EVIDENCE_TRACE_KEY)
    authority = build_component_f0_authorities(epoch=_epoch(), snapshot=_snapshot(249.0), bindings=(trace_binding,))[0]
    assert authority.availability is AvailabilityState.RESOLVED
    assert authority.population_completeness is PopulationCompleteness.FULL
    assert isinstance(authority.value, tuple)
    assert len(authority.value) == 1
    row = authority.value[0]
    assert row["epoch_ref"] == "epoch:E17"
    assert row["component_type"] == "beam"
    assert row["component_id"] == COMPONENT_ID
    assert row["feature_name"] == "beam_width_mm"
    assert row["source_table"] == "frame_section_assignments"
    assert row["actual_table_name"] == "Frame Section Assignments"
    assert row["source_column"] == "Width"
    assert row["raw_value"] == 249.0
    assert row["normalized_value"] == 249.0
    assert row["unit"] == "mm"
    with pytest.raises(TypeError):
        row["raw_value"] = 999.0


def test_incomplete_evidence_trace_cannot_satisfy_full_population_dependency() -> None:
    snapshot = _snapshot(
        250.0,
        feature_status=FeatureValueStatus.PARTIAL,
        evidence_status=FeatureEvidenceStatus.PARTIAL,
    )
    authorities = build_component_f0_authorities(epoch=_epoch(), snapshot=snapshot, bindings=_bindings())
    trace = next(item for item in authorities if item.key == EVIDENCE_TRACE_KEY)
    assert trace.population_completeness is PopulationCompleteness.INCOMPLETE
    inputs = build_f0_compile_inputs(rule_targets=(_target(),), external_authorities=authorities)
    with pytest.raises(KernelCompileError, match="FULL population requirement is not satisfiable"):
        RegulatoryCompiler.compile(F0_2_BEAM_MIN_WIDTH_REGISTRY, inputs)


def test_binding_validation_is_bounded_explicit_and_rejects_unsupported_authority_shapes() -> None:
    width = _bindings()[0]
    duplicate = F0EvidenceBinding(
        source_location=EvidenceBindingSource.SNAPSHOT_IDENTITY,
        source_key="story",
        dependency_key=width.dependency_key,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=SemanticType.COMPONENT_STORY,
        physical_dimension=PhysicalDimension.ENUM_STATE,
        grain=Grain.COMPONENT,
        unit=UNIT_ENUM_STATE,
    )
    with pytest.raises(EvidenceAuthorityAdapterError, match="duplicate DependencyKey"):
        build_component_f0_authorities(epoch=_epoch(), snapshot=_snapshot(), bindings=(width, duplicate))

    with pytest.raises(EvidenceAuthorityAdapterError, match="FACT and CONTEXT only"):
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_width_mm",
            dependency_key=DependencyKey("bad"),
            source_kind=DependencySourceKind.SOURCE_POPULATION,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        )

    with pytest.raises(EvidenceAuthorityAdapterError, match="Grain.COMPONENT only"):
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_width_mm",
            dependency_key=DependencyKey("bad"),
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.STORY,
            unit=UNIT_MM,
            expected_source_unit="mm",
        )

    with pytest.raises(EvidenceAuthorityAdapterError, match="source_key"):
        F0EvidenceBinding(
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="",
            dependency_key=DependencyKey("bad"),
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.BEAM_WIDTH,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        )


def test_binding_contract_has_no_mutable_metadata_payload_or_direction_escape_hatch() -> None:
    fields = F0EvidenceBinding.__dataclass_fields__
    assert "direction" not in fields
    assert "metadata" not in fields
    assert "payload" not in fields
    binding = _bindings()[0]
    with pytest.raises(FrozenInstanceError):
        binding.source_key = "other"  # type: ignore[misc]


def test_no_automatic_semantic_or_unit_inference_api_exists() -> None:
    fields = F0EvidenceBinding.__dataclass_fields__
    assert "semantic_type" in fields
    assert "physical_dimension" in fields
    assert "unit" in fields
    assert "expected_source_unit" in fields
    with pytest.raises(TypeError):
        F0EvidenceBinding(  # type: ignore[call-arg]
            source_location=EvidenceBindingSource.FEATURE_VALUE,
            source_key="beam_width_mm",
            dependency_key=BEAM_WIDTH_KEY,
            source_kind=DependencySourceKind.FACT,
            physical_dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            unit=UNIT_MM,
            expected_source_unit="mm",
        )


def test_equivalent_inputs_and_binding_permutations_are_byte_stable_for_f0_plan_and_execution() -> None:
    epoch1 = _epoch()
    epoch2 = _epoch()
    snapshot1 = _snapshot(250.0)
    snapshot2 = _snapshot(250.0)
    forward = _bindings()
    reverse = tuple(reversed(_bindings()))
    authorities1 = build_component_f0_authorities(epoch=epoch1, snapshot=snapshot1, bindings=forward)
    authorities2 = build_component_f0_authorities(epoch=epoch2, snapshot=snapshot2, bindings=reverse)
    assert authorities1 == authorities2
    assert tuple(item.authority_id for item in authorities1) == tuple(item.authority_id for item in authorities2)
    assert tuple(item.provenance_refs for item in authorities1) == tuple(item.provenance_refs for item in authorities2)

    inputs1 = build_f0_compile_inputs(rule_targets=(_target(),), external_authorities=authorities1)
    inputs2 = build_f0_compile_inputs(rule_targets=(_target(),), external_authorities=tuple(reversed(authorities2)))
    assert inputs1 == inputs2
    program1 = RegulatoryCompiler.compile(F0_2_BEAM_MIN_WIDTH_REGISTRY, inputs1)
    program2 = RegulatoryCompiler.compile(F0_2_BEAM_MIN_WIDTH_REGISTRY, inputs2)
    assert program1.plan.plan_identity == program2.plan.plan_identity
    assert program1.plan.deterministic_execution_order == program2.plan.deterministic_execution_order
    store1 = RegulatoryEngine.execute(program1)
    store2 = RegulatoryEngine.execute(program2)
    assert store1 == store2
    assert store1.closure_outcomes == store2.closure_outcomes


def test_epoch_change_changes_authority_identity_and_plan_trace_without_stale_logic() -> None:
    snapshot = _snapshot(250.0)
    old_epoch = _epoch("E17")
    new_epoch = _epoch("E18", predecessor="E17")
    old_authorities = build_component_f0_authorities(epoch=old_epoch, snapshot=snapshot, bindings=_bindings())
    new_authorities = build_component_f0_authorities(epoch=new_epoch, snapshot=snapshot, bindings=_bindings())
    assert old_epoch.epoch_id == "E17"
    assert new_epoch.epoch_id == "E18"
    assert tuple(item.authority_id for item in old_authorities) != tuple(item.authority_id for item in new_authorities)
    assert all("epoch:E17" in item.provenance_refs for item in old_authorities)
    assert all("epoch:E18" in item.provenance_refs for item in new_authorities)
    old_program = RegulatoryCompiler.compile(
        F0_2_BEAM_MIN_WIDTH_REGISTRY,
        build_f0_compile_inputs(rule_targets=(_target(),), external_authorities=old_authorities),
    )
    new_program = RegulatoryCompiler.compile(
        F0_2_BEAM_MIN_WIDTH_REGISTRY,
        build_f0_compile_inputs(rule_targets=(_target(),), external_authorities=new_authorities),
    )
    assert old_program.plan.plan_identity != new_program.plan.plan_identity
    assert "stale" not in EvidenceEpoch.__dataclass_fields__
    assert "analysis_basis" not in EvidenceEpoch.__dataclass_fields__


@pytest.mark.parametrize(("width_mm", "expected"), [(249.0, CheckStatus.FAIL), (250.0, CheckStatus.OK)])
def test_f0_2_end_to_end_sentinel_uses_existing_rule_only(width_mm: float, expected: CheckStatus) -> None:
    epoch, snapshot, authorities, inputs, program, store, result = _run(width_mm)
    assert result.status is expected
    assert result.check_id == "beam_geometry_min_width"
    assert result.component == COMPONENT_ID
    assert result.story == STORY
    assert result.section == SECTION
    assert len(result.evidence) == 1
    assert result.evidence[0]["epoch_ref"] == f"epoch:{epoch.epoch_id}"
    assert result.evidence[0]["source_table"] == "frame_section_assignments"
    assert len(store.formal_results) == 1
    assert type(store.formal_results[0].result) is CheckResult
    assert store.regulatory_quantities == ()
    assert tuple(item.scope_ref for item in authorities) == (COMPONENT_ID,) * 4
    assert tuple(item.direction for item in authorities) == (None,) * 4
    assert inputs.external_authorities == tuple(sorted(authorities, key=lambda item: item.sort_key))
    assert program.plan.compiled_rule_instances[0].scope_ref == snapshot.component_id


def test_bounded_plan_assessment_never_claims_full_tbdy_compliance() -> None:
    _, _, _, _, program, store, _ = _run(250.0)
    assessment = AssessmentEngine.reconcile(program, store)
    assert assessment.structural_status is StructuralAssessmentStatus.COMPLETE
    assert assessment.full_tbdy_compliance_status == "NOT_EVALUATED"


def test_architecture_import_and_authority_guards() -> None:
    import tbdy_engine.features.evidence_epoch as epoch_module
    import tbdy_engine.integration.f0_evidence_adapter as adapter_module
    import tbdy_engine.regulatory.kernel as kernel_module

    epoch_source = Path(epoch_module.__file__).read_text(encoding="utf-8")
    adapter_source = Path(adapter_module.__file__).read_text(encoding="utf-8")
    kernel_source = Path(kernel_module.__file__).read_text(encoding="utf-8")

    assert "tbdy_engine.regulatory" not in epoch_source
    for forbidden in (
        "product_reports",
        "MinimalCheckEngine",
        "checks.engine",
        "result_evidence",
        "etabs_gateway",
        "tbdy_engine.etabs",
    ):
        assert forbidden not in adapter_source
    assert "CheckResult(" not in adapter_source
    assert "RegulatoryQuantity(" not in adapter_source
    assert "tbdy_engine.features" not in kernel_source
    assert "tbdy_engine.integration" not in kernel_source

    adapter_tree = ast.parse(adapter_source)
    imported = []
    for node in ast.walk(adapter_tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert all("product_reports" not in item for item in imported)
    assert all("checks.engine" not in item for item in imported)
