"""B1 causal analysis-lineage contract and negative authority proofs."""
from __future__ import annotations

from dataclasses import fields
import inspect
from pathlib import Path

import pytest

import tbdy_engine.integration.etabs_analysis_lineage as subject
from tbdy_engine.analysis_basis.contracts import AnalysisBasisSnapshot
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.integration.live_etabs_acquisition_context import SourceModelIdentity
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "etabs-source-model-ref:sha256:" + "1" * 64
EXECUTION_STATE = "source-execution-state:source-model-ref:1"
STATE_BASIS = (
    "analysis-state-fact:geometry:1",
    "analysis-state-fact:stiffness:1",
    "analysis-state-fact:cases:1",
)
GENERATION = "analysis-generation:controlled-run:1"
SCOPE = ("analysis-case:LC_G", "analysis-case:LC_EQX")


def _state(*, source_model_ref: str = SOURCE, execution_state_ref: str = EXECUTION_STATE):
    return subject.build_analysis_state_identity(
        source_model_ref=source_model_ref,
        execution_state_ref=execution_state_ref,
        state_basis_refs=STATE_BASIS,
        provenance_refs=("state-proof:1",),
    )


def _result(state=None, *, source_model_ref: str = SOURCE, generation: str = GENERATION):
    state = state or _state(source_model_ref=source_model_ref)
    return subject.build_analysis_result_identity(
        source_model_ref=source_model_ref,
        parent_analysis_state_ref=state.identity_ref,
        analysis_generation_ref=generation,
        result_scope_refs=SCOPE,
        provenance_refs=("result-fact:1",),
    )


def _proof(state, result, *, source_model_ref=None, execution_state_ref=None):
    return subject._VerifiedAnalysisExecutionProof(
        _token=subject._EXECUTION_PROOF_FACTORY_TOKEN,
        proof_ref="analysis-execution-proof:controlled:1",
        source_model_ref=source_model_ref or state.source_model_ref,
        execution_state_ref=execution_state_ref or state.execution_state_ref,
        analysis_state_ref=state.identity_ref,
        analysis_result_ref=result.identity_ref,
        analysis_generation_ref=result.analysis_generation_ref,
        provenance_refs=("run-analysis:return-code:0", "analysis-result-readback:verified"),
    )


def _qualified(state=None, result=None, proof=None, *, capture_refs=()):
    state = state or _state()
    result = result or _result(state)
    proof = proof or _proof(state, result)
    return subject._build_qualified_analysis_lineage(
        _token=subject._QUALIFICATION_FACTORY_TOKEN,
        analysis_state=state,
        analysis_result=result,
        execution_proof=proof,
        qualification_provenance_refs=("qualification-authority:controlled-analysis-execution",),
        capture_provenance_refs=capture_refs,
    )


def test_identity_contracts_are_deterministic_and_evidence_epoch_independent():
    one = _state()
    two = subject.build_analysis_state_identity(
        source_model_ref=SOURCE,
        execution_state_ref=EXECUTION_STATE,
        state_basis_refs=tuple(reversed(STATE_BASIS)),
        provenance_refs=("different-observation:2",),
    )
    assert one.identity_ref == two.identity_ref
    assert one.canonical_json() == one.canonical_json()

    r1 = _result(one)
    r2 = subject.build_analysis_result_identity(
        source_model_ref=SOURCE,
        parent_analysis_state_ref=one.identity_ref,
        analysis_generation_ref=GENERATION,
        result_scope_refs=tuple(reversed(SCOPE)),
        provenance_refs=("different-observation:3",),
    )
    assert r1.identity_ref == r2.identity_ref
    assert r1.canonical_json() == r1.canonical_json()
    assert "epoch" not in {item.name for item in fields(subject.AnalysisStateIdentity)}
    assert "epoch" not in {item.name for item in fields(subject.AnalysisResultIdentity)}
    assert "evidence_epoch" not in inspect.signature(subject.build_analysis_state_identity).parameters
    assert "evidence_epoch" not in inspect.signature(subject.build_analysis_result_identity).parameters


def test_source_root_and_execution_state_are_distinct_future_compatible_fields():
    state = _state(execution_state_ref="future-derived-state:abc")
    assert state.source_model_ref == SOURCE
    assert state.execution_state_ref == "future-derived-state:abc"
    assert state.source_model_ref != state.execution_state_ref


def test_unqualified_is_fail_closed_and_cannot_expose_result_identity():
    state = _state()
    epoch = EvidenceEpoch(
        epoch_id="epoch:live:1",
        model_fingerprint="model-ref-only:1",
        origin=EvidenceEpochOrigin.LIVE_CAPTURE,
        provenance_refs=("capture:1",),
    )
    lineage = subject.build_unqualified_analysis_lineage(
        source_model_ref=SOURCE,
        analysis_state=state,
        blockers=("PRE_EXISTING_LIVE_RESULT_GENERATION_NOT_PROVEN",),
        qualification_provenance_refs=("current-read-surface:census",),
        capture_provenance_refs=(epoch.epoch_id, "acquisition-context:1"),
    )
    assert lineage.status is subject.AnalysisLineageQualificationStatus.UNQUALIFIED
    assert lineage.qualified is False
    assert lineage.analysis_result is None
    assert lineage.blockers
    assert epoch.epoch_id in lineage.capture_provenance_refs
    with pytest.raises(subject.AnalysisLineageQualificationError):
        lineage.require_qualified_result()


def test_supported_constructor_cannot_set_qualification_to_qualified():
    state = _state()
    result = _result(state)
    with pytest.raises(TypeError, match="factory-created only"):
        subject.AnalysisLineageQualification(
            status=subject.AnalysisLineageQualificationStatus.QUALIFIED,
            source_model_ref=SOURCE,
            analysis_state=state,
            analysis_result=result,
            qualification_ref=subject.ANALYSIS_LINEAGE_REF_PREFIX + "0" * 64,
            qualification_provenance_refs=("caller:asserted",),
            capture_provenance_refs=(),
            blockers=(),
        )
    assert "qualify" not in subject.__all__
    assert "_build_qualified_analysis_lineage" not in subject.__all__
    assert "_VerifiedAnalysisExecutionProof" not in subject.__all__


def test_positive_internal_invariant_requires_exact_verified_execution_proof():
    state = _state()
    result = _result(state)
    lineage = _qualified(state, result)
    assert lineage.status is subject.AnalysisLineageQualificationStatus.QUALIFIED
    assert lineage.qualified is True
    assert lineage.blockers == ()
    assert lineage.require_qualified_result() is result
    assert result.parent_analysis_state_ref == state.identity_ref
    assert lineage.source_model_ref == state.source_model_ref == result.source_model_ref
    assert lineage.qualification_provenance_refs
    assert lineage.canonical_json() == lineage.canonical_json()


def test_wrong_state_result_parent_binding_fails_closed():
    state_a = _state(execution_state_ref="state:A")
    state_b = _state(execution_state_ref="state:B")
    result = _result(state_a)
    proof = _proof(state_a, result)
    with pytest.raises(subject.AnalysisLineageQualificationError, match="parent state mismatch"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=state_b,
            analysis_result=result,
            execution_proof=proof,
            qualification_provenance_refs=("qualification:test",),
        )


def test_wrong_source_root_lineage_fails_closed():
    state = _state()
    result = _result(state)
    proof = _proof(state, result, source_model_ref="etabs-source-model-ref:sha256:" + "2" * 64)
    with pytest.raises(subject.AnalysisLineageQualificationError, match="source root mismatch"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=state,
            analysis_result=result,
            execution_proof=proof,
            qualification_provenance_refs=("qualification:test",),
        )


def test_wrong_execution_state_binding_fails_closed():
    state = _state()
    result = _result(state)
    proof = _proof(state, result, execution_state_ref="derived-state:wrong")
    with pytest.raises(subject.AnalysisLineageQualificationError, match="state binding mismatch"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=state,
            analysis_result=result,
            execution_proof=proof,
            qualification_provenance_refs=("qualification:test",),
        )


def test_source_model_identity_cannot_substitute_for_analysis_state_identity():
    source = SourceModelIdentity(
        source_model_ref=SOURCE,
        model_fingerprint="etabs-model-fingerprint:source-reference-only:sha256:" + "3" * 64,
        normalized_model_reference=r"c:\tmp\model.edb",
    )
    result = _result()
    with pytest.raises(TypeError, match="analysis_state must be AnalysisStateIdentity"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=source,
            analysis_result=result,
            execution_proof=object(),
            qualification_provenance_refs=("qualification:test",),
        )


def test_evidence_epoch_cannot_substitute_for_state_or_result_identity():
    epoch = EvidenceEpoch(
        epoch_id="epoch:test:1",
        model_fingerprint="model:1",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
    )
    state = _state()
    result = _result(state)
    proof = _proof(state, result)
    with pytest.raises(TypeError, match="analysis_state must be AnalysisStateIdentity"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=epoch,
            analysis_result=result,
            execution_proof=proof,
            qualification_provenance_refs=("qualification:test",),
        )
    with pytest.raises(TypeError, match="analysis_result must be AnalysisResultIdentity"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=state,
            analysis_result=epoch,
            execution_proof=proof,
            qualification_provenance_refs=("qualification:test",),
        )


def test_analysis_basis_snapshot_and_match_status_cannot_substitute_for_identity_or_proof():
    fake_snapshot = object.__new__(AnalysisBasisSnapshot)
    state = _state()
    result = _result(state)
    with pytest.raises(TypeError, match="analysis_state must be AnalysisStateIdentity"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=fake_snapshot,
            analysis_result=result,
            execution_proof=object(),
            qualification_provenance_refs=("qualification:test",),
        )
    with pytest.raises(TypeError, match="analysis_result must be AnalysisResultIdentity"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=state,
            analysis_result=fake_snapshot,
            execution_proof=object(),
            qualification_provenance_refs=("qualification:test",),
        )
    with pytest.raises(TypeError, match="verified causal execution proof"):
        subject._build_qualified_analysis_lineage(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            analysis_state=state,
            analysis_result=result,
            execution_proof=AnalysisBasisStatus.MATCH,
            qualification_provenance_refs=("qualification:test",),
        )


def test_content_row_hash_acquisition_context_and_uuid_are_not_positive_qualification_sources():
    state = _state()
    for convenient_source in (
        "column-design-result-row:sha256:" + "a" * 64,
        "acquisition-context:sha256:" + "b" * 64,
        "550e8400-e29b-41d4-a716-446655440000",
    ):
        result = _result(state, generation=convenient_source)
        assert result.analysis_generation_ref == convenient_source
        with pytest.raises(TypeError, match="verified causal execution proof"):
            subject._build_qualified_analysis_lineage(
                _token=subject._QUALIFICATION_FACTORY_TOKEN,
                analysis_state=state,
                analysis_result=result,
                execution_proof=convenient_source,
                qualification_provenance_refs=("qualification:test",),
            )


def test_capture_epoch_changes_qualification_artifact_not_state_or_result_identity():
    state = _state()
    result = _result(state)
    one = _qualified(state, result, capture_refs=("epoch:live-acquisition:1",))
    two = _qualified(state, result, capture_refs=("epoch:live-acquisition:2",))
    assert one.analysis_state.identity_ref == two.analysis_state.identity_ref
    assert one.analysis_result.identity_ref == two.analysis_result.identity_ref
    assert one.qualification_ref != two.qualification_ref


def test_public_module_has_no_design_lineage_or_mutation_capability():
    public = set(subject.__all__)
    assert "DesignStateIdentity" not in public
    assert "DesignResultIdentity" not in public
    source = (ROOT / "tbdy_engine/integration/etabs_analysis_lineage.py").read_text(encoding="utf-8")
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        ".Save(",
        "SaveAs(",
        "SetPresentUnits(",
        "SetModifiers(",
        "SapModel",
        "DatabaseTables",
        "DesignConcrete",
        "Results.Setup",
    ):
        assert forbidden not in source


def test_application_request_contracts_have_no_lineage_authority_injection_surface_if_present():
    path = ROOT / "tbdy_engine/application/contracts.py"
    if not path.exists():
        pytest.skip("PRODUCT-SPINE application contracts are not present in this local snapshot")
    source = path.read_text(encoding="utf-8")
    for forbidden in (
        "AnalysisStateIdentity",
        "AnalysisResultIdentity",
        "AnalysisLineageQualification",
        "analysis_state_identity",
        "analysis_result_identity",
        "qualified_lineage",
        "EvidenceEpoch",
        "model_fingerprint",
        "RegulatoryCompileInputs",
    ):
        assert forbidden not in source


def test_current_b1_has_no_public_positive_issuer():
    assert subject.AnalysisLineageQualificationStatus.QUALIFIED.value == "QUALIFIED"
    assert subject.AnalysisLineageQualificationStatus.UNQUALIFIED.value == "UNQUALIFIED"
    public_callables = {
        name
        for name in subject.__all__
        if callable(getattr(subject, name, None))
    }
    assert "build_unqualified_analysis_lineage" in public_callables
    assert not any(name.startswith("qualify") for name in public_callables)
    assert not any("execution_proof" in name.lower() for name in public_callables)



def test_qualification_rejects_noncanonical_contract_even_through_factory_boundary():
    state = _state()
    result = _result(state)
    with pytest.raises(subject.AnalysisLineageError, match="qualification contract mismatch"):
        subject.AnalysisLineageQualification(
            _token=subject._QUALIFICATION_FACTORY_TOKEN,
            status=subject.AnalysisLineageQualificationStatus.QUALIFIED,
            source_model_ref=SOURCE,
            analysis_state=state,
            analysis_result=result,
            qualification_ref=subject.ANALYSIS_LINEAGE_REF_PREFIX + "0" * 64,
            qualification_provenance_refs=("qualification:test",),
            capture_provenance_refs=(),
            blockers=(),
            contract="TBDY_ANALYSIS_LINEAGE_QUALIFICATION_V999",
        )


def test_private_qualification_issuance_symbols_are_negative_reachable_from_production_tree():
    owner = (ROOT / "tbdy_engine/integration/etabs_analysis_lineage.py").resolve()
    forbidden = (
        "_QUALIFICATION_FACTORY_TOKEN",
        "_EXECUTION_PROOF_FACTORY_TOKEN",
        "_VerifiedAnalysisExecutionProof",
        "_build_qualified_analysis_lineage",
    )
    violations = []
    for path in sorted((ROOT / "tbdy_engine").rglob("*.py")):
        if path.resolve() == owner:
            continue
        text = path.read_text(encoding="utf-8")
        for symbol in forbidden:
            if symbol in text:
                violations.append((path.relative_to(ROOT).as_posix(), symbol))
    assert violations == []
