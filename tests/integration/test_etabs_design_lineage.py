"""B2 causal design-lineage identity and fail-closed qualification proofs."""
from __future__ import annotations

from dataclasses import fields
import inspect
from pathlib import Path

import pytest

import tbdy_engine.integration.etabs_analysis_lineage as analysis
import tbdy_engine.integration.etabs_design_lineage as subject


ROOT = Path(__file__).resolve().parents[2]

SOURCE = "etabs-source-model-ref:sha256:" + "1" * 64
OTHER_SOURCE = "etabs-source-model-ref:sha256:" + "2" * 64
EXECUTION_STATE = "source-execution-state:source-model-ref:1"
ANALYSIS_STATE_BASIS = (
    "analysis-state-fact:geometry:1",
    "analysis-state-fact:stiffness:1",
    "analysis-state-fact:cases:1",
)
ANALYSIS_SCOPE = ("analysis-case:LC_G", "analysis-case:LC_EQX")
ANALYSIS_GENERATION = "analysis-generation:controlled-run:1"

MODEL_FINGERPRINT = "etabs-model-fingerprint:source-reference-only:sha256:" + "3" * 64
EVIDENCE_EPOCH = "epoch:live-design-evidence:1"
DESIGN_CODE = "design-code:TBDY-TS500:reviewed:1"
DESIGN_DOMAIN = "design-domain:concrete-column:1"
DESIGN_PROCEDURE = "design-procedure:etabs-concrete-column:1"
SELECTED_COMBO_POPULATION = "selected-design-combo-population:sha256:" + "4" * 64
COMBO_DEFINITION_REFS = (
    "combo-definition-population:sha256:" + "5" * 64,
)
COMBO_BINDINGS = (
    "combo-grain-binding:component:C1|type:STRENGTH|combo:COMB_A|definition:5|analysis-basis:MATCH",
    "combo-grain-binding:component:C1|type:STRENGTH|combo:COMB_B|definition:6|analysis-basis:MATCH",
)
COMPONENT_POPULATION_REFS = (
    "design-component-population:column:C1",
)
DESIGN_OPTIONS = ("design-option:overwrite-set:reviewed:1",)
DESIGN_STATE_BASIS = (
    "design-state-basis:section-population:1",
    "design-state-basis:combo-population:1",
)
RESULT_SCOPE = (
    "design-result-scope:component:C1|type:STRENGTH|combo:COMB_A",
    "design-result-scope:component:C1|type:STRENGTH|combo:COMB_B",
)
DESIGN_GENERATION = "design-generation:controlled-start-design:1"
DESIGN_ATTEMPT = "design-attempt:1"


def _analysis_state(*, source_model_ref: str = SOURCE, execution_state_ref: str = EXECUTION_STATE):
    return analysis.build_analysis_state_identity(
        source_model_ref=source_model_ref,
        execution_state_ref=execution_state_ref,
        state_basis_refs=ANALYSIS_STATE_BASIS,
        provenance_refs=("analysis-state-proof:1",),
    )


def _analysis_result(
    state=None,
    *,
    source_model_ref: str = SOURCE,
    generation: str = ANALYSIS_GENERATION,
):
    state = state or _analysis_state(source_model_ref=source_model_ref)
    return analysis.build_analysis_result_identity(
        source_model_ref=source_model_ref,
        parent_analysis_state_ref=state.identity_ref,
        analysis_generation_ref=generation,
        result_scope_refs=ANALYSIS_SCOPE,
        provenance_refs=("analysis-result-proof:1",),
    )


def _qualified_analysis(
    *,
    source_model_ref: str = SOURCE,
    execution_state_ref: str = EXECUTION_STATE,
    generation: str = ANALYSIS_GENERATION,
):
    state = _analysis_state(
        source_model_ref=source_model_ref,
        execution_state_ref=execution_state_ref,
    )
    result = _analysis_result(
        state,
        source_model_ref=source_model_ref,
        generation=generation,
    )
    proof = analysis._VerifiedAnalysisExecutionProof(
        _token=analysis._EXECUTION_PROOF_FACTORY_TOKEN,
        proof_ref=f"analysis-execution-proof:{source_model_ref[-4:]}:{generation}",
        source_model_ref=source_model_ref,
        execution_state_ref=state.execution_state_ref,
        analysis_state_ref=state.identity_ref,
        analysis_result_ref=result.identity_ref,
        analysis_generation_ref=result.analysis_generation_ref,
        provenance_refs=("run-analysis:return-code:0", "analysis-result-readback:verified"),
    )
    lineage = analysis._build_qualified_analysis_lineage(
        _token=analysis._QUALIFICATION_FACTORY_TOKEN,
        analysis_state=state,
        analysis_result=result,
        execution_proof=proof,
        qualification_provenance_refs=(
            "qualification-authority:controlled-analysis-execution",
        ),
    )
    return lineage


def _unqualified_analysis():
    state = _analysis_state()
    return analysis.build_unqualified_analysis_lineage(
        source_model_ref=SOURCE,
        analysis_state=state,
        blockers=("PRE_EXISTING_LIVE_RESULT_GENERATION_NOT_PROVEN",),
        qualification_provenance_refs=("current-read-surface:census",),
        capture_provenance_refs=("epoch:observed-only",),
    )


def _design_state(
    lineage=None,
    *,
    model_fingerprint: str = MODEL_FINGERPRINT,
    evidence_epoch_id: str = EVIDENCE_EPOCH,
    combo_bindings=COMBO_BINDINGS,
    provenance_refs=("design-state-proof:1",),
):
    lineage = lineage or _qualified_analysis()
    return subject.build_design_state_identity(
        analysis_lineage=lineage,
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=evidence_epoch_id,
        design_code_ref=DESIGN_CODE,
        design_domain_ref=DESIGN_DOMAIN,
        design_procedure_ref=DESIGN_PROCEDURE,
        selected_design_combo_population_ref=SELECTED_COMBO_POPULATION,
        combo_definition_population_refs=COMBO_DEFINITION_REFS,
        combo_grain_binding_refs=combo_bindings,
        design_component_population_refs=COMPONENT_POPULATION_REFS,
        design_option_refs=DESIGN_OPTIONS,
        state_basis_refs=DESIGN_STATE_BASIS,
        provenance_refs=provenance_refs,
    )


def _design_result(
    state=None,
    *,
    generation: str = DESIGN_GENERATION,
    scopes=RESULT_SCOPE,
    provenance_refs=("design-result-row-population:1",),
):
    state = state or _design_state()
    return subject.build_design_result_identity(
        design_state=state,
        design_generation_ref=generation,
        result_scope_refs=scopes,
        provenance_refs=provenance_refs,
    )


def _proof_ref(
    *,
    state,
    result,
    lineage,
    source_model_ref=None,
    parent_analysis_result_ref=None,
    analysis_lineage_qualification_ref=None,
    model_fingerprint=None,
    evidence_epoch_id=None,
    design_state_ref=None,
    design_result_ref=None,
    design_attempt_ref=DESIGN_ATTEMPT,
    design_generation_ref=None,
    requested_result_scope_refs=None,
    reconciled_result_scope_refs=None,
    combo_grain_binding_refs=None,
    provenance_refs=("start-design:return-code:0", "design-results:full-population-reconciled"),
):
    parent = lineage.require_qualified_result()
    values = {
        "source_model_ref": source_model_ref or state.source_model_ref,
        "parent_analysis_result_ref": (
            parent_analysis_result_ref or parent.identity_ref
        ),
        "analysis_lineage_qualification_ref": (
            analysis_lineage_qualification_ref or lineage.qualification_ref
        ),
        "model_fingerprint": model_fingerprint or state.model_fingerprint,
        "evidence_epoch_id": evidence_epoch_id or state.evidence_epoch_id,
        "design_state_ref": design_state_ref or state.identity_ref,
        "design_result_ref": design_result_ref or result.identity_ref,
        "design_attempt_ref": design_attempt_ref,
        "design_generation_ref": (
            design_generation_ref or result.design_generation_ref
        ),
        "requested_result_scope_refs": (
            tuple(requested_result_scope_refs)
            if requested_result_scope_refs is not None
            else result.result_scope_refs
        ),
        "reconciled_result_scope_refs": (
            tuple(reconciled_result_scope_refs)
            if reconciled_result_scope_refs is not None
            else result.result_scope_refs
        ),
        "combo_grain_binding_refs": (
            tuple(combo_grain_binding_refs)
            if combo_grain_binding_refs is not None
            else state.combo_grain_binding_refs
        ),
        "provenance_refs": tuple(provenance_refs),
    }
    return subject._design_execution_proof_ref(**values), values


def _design_proof(state, result, lineage, **overrides):
    proof_ref, values = _proof_ref(
        state=state,
        result=result,
        lineage=lineage,
        **overrides,
    )
    return subject._VerifiedDesignExecutionProof(
        _token=subject._DESIGN_EXECUTION_PROOF_FACTORY_TOKEN,
        proof_ref=proof_ref,
        **values,
    )


def _qualified_design(
    lineage=None,
    state=None,
    result=None,
    proof=None,
    *,
    capture_refs=(),
):
    lineage = lineage or _qualified_analysis()
    state = state or _design_state(lineage)
    result = result or _design_result(state)
    proof = proof or _design_proof(state, result, lineage)
    return subject._build_qualified_design_lineage(
        _token=subject._DESIGN_QUALIFICATION_FACTORY_TOKEN,
        parent_analysis_lineage=lineage,
        design_state=state,
        design_result=result,
        execution_proof=proof,
        qualification_provenance_refs=(
            "qualification-authority:future-controlled-design-execution",
        ),
        capture_provenance_refs=capture_refs,
    )


def test_design_identity_contracts_are_deterministic_and_provenance_independent():
    lineage = _qualified_analysis()
    one = _design_state(lineage)
    two = subject.build_design_state_identity(
        analysis_lineage=lineage,
        model_fingerprint=MODEL_FINGERPRINT,
        evidence_epoch_id=EVIDENCE_EPOCH,
        design_code_ref=DESIGN_CODE,
        design_domain_ref=DESIGN_DOMAIN,
        design_procedure_ref=DESIGN_PROCEDURE,
        selected_design_combo_population_ref=SELECTED_COMBO_POPULATION,
        combo_definition_population_refs=tuple(reversed(COMBO_DEFINITION_REFS)),
        combo_grain_binding_refs=tuple(reversed(COMBO_BINDINGS)),
        design_component_population_refs=tuple(reversed(COMPONENT_POPULATION_REFS)),
        design_option_refs=tuple(reversed(DESIGN_OPTIONS)),
        state_basis_refs=tuple(reversed(DESIGN_STATE_BASIS)),
        provenance_refs=("different-observation:2",),
    )
    assert one.identity_ref == two.identity_ref
    assert one.provenance_refs != two.provenance_refs

    r1 = _design_result(one)
    r2 = subject.build_design_result_identity(
        design_state=one,
        design_generation_ref=DESIGN_GENERATION,
        result_scope_refs=tuple(reversed(RESULT_SCOPE)),
        provenance_refs=("different-observation:3",),
    )
    assert r1.identity_ref == r2.identity_ref
    assert r1.provenance_refs != r2.provenance_refs
    assert r1.canonical_json() == r1.canonical_json()


def test_design_state_requires_qualified_parent_analysis_result():
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="QUALIFIED parent AnalysisResultIdentity",
    ):
        _design_state(_unqualified_analysis())


def test_identity_shaped_design_result_is_not_qualified_lineage():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)

    assert isinstance(result, subject.DesignResultIdentity)
    assert not hasattr(result, "qualified")
    with pytest.raises(TypeError, match="factory-created only"):
        subject.DesignLineageQualification(
            status=subject.DesignLineageQualificationStatus.QUALIFIED,
            source_model_ref=SOURCE,
            parent_analysis_lineage=lineage,
            design_state=state,
            design_result=result,
            qualification_ref=subject.DESIGN_LINEAGE_REF_PREFIX + "0" * 64,
            qualification_provenance_refs=("caller:asserted",),
            capture_provenance_refs=(),
            blockers=(),
        )


def test_private_positive_qualification_requires_exact_complete_execution_proof():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    proof = _design_proof(state, result, lineage)
    qualified = _qualified_design(lineage, state, result, proof)

    assert qualified.status is subject.DesignLineageQualificationStatus.QUALIFIED
    assert qualified.qualified is True
    assert qualified.require_qualified_result() is result
    assert qualified.design_state is state
    assert qualified.parent_analysis_lineage is lineage
    assert qualified.blockers == ()
    assert result.parent_design_state_ref == state.identity_ref
    assert state.parent_analysis_result_ref == lineage.require_qualified_result().identity_ref


@pytest.mark.parametrize(
    "convenient_source",
    (
        SOURCE,
        EVIDENCE_EPOCH,
        MODEL_FINGERPRINT,
        "acquisition-context:sha256:" + "a" * 64,
        "component:C1",
        "COMB_A",
        "column-design-result-row:sha256:" + "b" * 64,
        {"status": "QUALIFIED"},
    ),
)
def test_convenient_observational_or_caller_shaped_data_cannot_substitute_for_causal_proof(
    convenient_source,
):
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    with pytest.raises(TypeError, match="verified causal design-execution proof"):
        subject._build_qualified_design_lineage(
            _token=subject._DESIGN_QUALIFICATION_FACTORY_TOKEN,
            parent_analysis_lineage=lineage,
            design_state=state,
            design_result=result,
            execution_proof=convenient_source,
            qualification_provenance_refs=("qualification:test",),
        )


def test_same_component_wrong_combo_binding_fails_closed_without_broadcast():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    wrong_combo_bindings = (
        "combo-grain-binding:component:C1|type:STRENGTH|combo:COMB_A|definition:5|analysis-basis:MATCH",
        "combo-grain-binding:component:C1|type:STRENGTH|combo:WRONG|definition:6|analysis-basis:MATCH",
    )
    proof = _design_proof(
        state,
        result,
        lineage,
        combo_grain_binding_refs=wrong_combo_bindings,
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="exact combo-grain binding mismatch",
    ):
        _qualified_design(lineage, state, result, proof)


def test_component_constant_but_combo_grain_change_changes_design_state_identity():
    lineage = _qualified_analysis()
    one = _design_state(lineage)
    changed = (
        COMBO_BINDINGS[0],
        "combo-grain-binding:component:C1|type:STRENGTH|combo:COMB_C|definition:7|analysis-basis:MATCH",
    )
    two = _design_state(lineage, combo_bindings=changed)
    assert one.design_component_population_refs == two.design_component_population_refs
    assert one.identity_ref != two.identity_ref


def test_wrong_parent_analysis_result_fails_closed():
    lineage_one = _qualified_analysis(generation="analysis-generation:one")
    lineage_two = _qualified_analysis(generation="analysis-generation:two")
    state = _design_state(lineage_one)
    result = _design_result(state)
    proof = _design_proof(state, result, lineage_one)
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="parent AnalysisResultIdentity mismatch",
    ):
        _qualified_design(lineage_two, state, result, proof)


def test_unqualified_parent_analysis_result_fails_closed():
    good_lineage = _qualified_analysis()
    state = _design_state(good_lineage)
    result = _design_result(state)
    proof = _design_proof(state, result, good_lineage)
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="QUALIFIED parent AnalysisResultIdentity",
    ):
        _qualified_design(_unqualified_analysis(), state, result, proof)


def test_wrong_source_model_in_execution_proof_fails_closed():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    proof = _design_proof(
        state,
        result,
        lineage,
        source_model_ref=OTHER_SOURCE,
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="execution proof source root mismatch",
    ):
        _qualified_design(lineage, state, result, proof)


def test_wrong_model_fingerprint_or_evidence_epoch_in_execution_proof_fails_closed():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)

    wrong_fp = _design_proof(
        state,
        result,
        lineage,
        model_fingerprint="model-fingerprint:wrong",
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="model fingerprint mismatch",
    ):
        _qualified_design(lineage, state, result, wrong_fp)

    wrong_epoch = _design_proof(
        state,
        result,
        lineage,
        evidence_epoch_id="epoch:wrong",
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="EvidenceEpoch mismatch",
    ):
        _qualified_design(lineage, state, result, wrong_epoch)


def test_wrong_design_generation_fails_closed():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    proof = _design_proof(
        state,
        result,
        lineage,
        design_generation_ref="design-generation:wrong",
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="design-generation mismatch",
    ):
        _qualified_design(lineage, state, result, proof)


def test_result_rows_or_identity_without_causal_proof_fail_closed():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    for not_a_proof in (
        result,
        ("row:C1:COMB_A", "row:C1:COMB_B"),
        {"rows": ["row:C1:COMB_A"], "complete": True},
    ):
        with pytest.raises(
            TypeError,
            match="verified causal design-execution proof",
        ):
            subject._build_qualified_design_lineage(
                _token=subject._DESIGN_QUALIFICATION_FACTORY_TOKEN,
                parent_analysis_lineage=lineage,
                design_state=state,
                design_result=result,
                execution_proof=not_a_proof,
                qualification_provenance_refs=("qualification:test",),
            )


def test_partial_scope_cannot_be_disguised_as_complete_design_result():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    proof_ref, values = _proof_ref(
        state=state,
        result=result,
        lineage=lineage,
        requested_result_scope_refs=RESULT_SCOPE,
        reconciled_result_scope_refs=(RESULT_SCOPE[0],),
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="partial or failed design scope",
    ):
        subject._VerifiedDesignExecutionProof(
            _token=subject._DESIGN_EXECUTION_PROOF_FACTORY_TOKEN,
            proof_ref=proof_ref,
            **values,
        )


def test_requested_scope_must_equal_design_result_scope_even_when_proof_is_complete():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    result = _design_result(state)
    narrow_scope = (RESULT_SCOPE[0],)
    proof = _design_proof(
        state,
        result,
        lineage,
        requested_result_scope_refs=narrow_scope,
        reconciled_result_scope_refs=narrow_scope,
    )
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="requested result scope mismatch",
    ):
        _qualified_design(lineage, state, result, proof)


def test_unqualified_design_lineage_is_fail_closed_and_never_exposes_result_identity():
    lineage = _qualified_analysis()
    state = _design_state(lineage)
    unqualified = subject.build_unqualified_design_lineage(
        source_model_ref=SOURCE,
        parent_analysis_lineage=lineage,
        design_state=state,
        blockers=("DESIGN_EXECUTION_CAUSAL_PROOF_NOT_AVAILABLE",),
        qualification_provenance_refs=("b2:identity-only",),
        capture_provenance_refs=(EVIDENCE_EPOCH,),
    )
    assert unqualified.status is subject.DesignLineageQualificationStatus.UNQUALIFIED
    assert unqualified.qualified is False
    assert unqualified.design_result is None
    with pytest.raises(
        subject.DesignLineageQualificationError,
        match="not qualified",
    ):
        unqualified.require_qualified_result()


def test_design_state_and_result_fields_preserve_required_causal_boundaries():
    state_fields = {item.name for item in fields(subject.DesignStateIdentity)}
    assert {
        "source_model_ref",
        "parent_analysis_result_ref",
        "analysis_lineage_qualification_ref",
        "model_fingerprint",
        "evidence_epoch_id",
        "design_code_ref",
        "design_domain_ref",
        "design_procedure_ref",
        "selected_design_combo_population_ref",
        "combo_definition_population_refs",
        "combo_grain_binding_refs",
        "design_component_population_refs",
        "design_option_refs",
        "state_basis_refs",
    }.issubset(state_fields)

    result_fields = {item.name for item in fields(subject.DesignResultIdentity)}
    assert {
        "source_model_ref",
        "parent_design_state_ref",
        "parent_analysis_result_ref",
        "design_generation_ref",
        "result_scope_refs",
    }.issubset(result_fields)


def test_public_design_lineage_api_has_no_positive_qualification_issuer():
    public = set(subject.__all__)
    assert {
        "DesignStateIdentity",
        "DesignResultIdentity",
        "DesignLineageQualification",
        "build_design_state_identity",
        "build_design_result_identity",
        "build_unqualified_design_lineage",
    }.issubset(public)
    assert "_VerifiedDesignExecutionProof" not in public
    assert "_build_qualified_design_lineage" not in public
    assert "_DESIGN_QUALIFICATION_FACTORY_TOKEN" not in public
    assert "_DESIGN_EXECUTION_PROOF_FACTORY_TOKEN" not in public

    public_callables = {
        name
        for name in public
        if callable(getattr(subject, name, None))
    }
    assert not any(name.startswith("qualify") for name in public_callables)
    assert not any("execution_proof" in name.lower() for name in public_callables)


def test_design_lineage_owner_contains_zero_execution_or_raw_boundary_capability():
    source = (
        ROOT / "tbdy_engine/integration/etabs_design_lineage.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SapModel",
        "DatabaseTables",
        "DesignConcrete",
        "Results.Setup",
        "GetSummaryResultsColumn",
    ):
        assert forbidden not in source


def test_private_design_qualification_symbols_are_negative_reachable_from_production_tree():
    owner = (
        ROOT / "tbdy_engine/integration/etabs_design_lineage.py"
    ).resolve()
    forbidden = (
        "_DESIGN_QUALIFICATION_FACTORY_TOKEN",
        "_DESIGN_EXECUTION_PROOF_FACTORY_TOKEN",
        "_VerifiedDesignExecutionProof",
        "_build_qualified_design_lineage",
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


def test_application_request_contracts_cannot_inject_design_lineage_authority():
    path = ROOT / "tbdy_engine/application/contracts.py"
    source = path.read_text(encoding="utf-8")
    for forbidden in (
        "DesignStateIdentity",
        "DesignResultIdentity",
        "DesignLineageQualification",
        "design_state_identity",
        "design_result_identity",
        "design_lineage_qualification",
        "qualified_design_lineage",
        "_VerifiedDesignExecutionProof",
    ):
        assert forbidden not in source


def test_private_design_proof_constructor_is_not_public_test_helper():
    signature = inspect.signature(subject._VerifiedDesignExecutionProof)
    assert "_token" in signature.parameters
    with pytest.raises(TypeError, match="issuer-created only"):
        subject._VerifiedDesignExecutionProof(
            proof_ref="design-execution-proof:sha256:" + "0" * 64,
            source_model_ref=SOURCE,
            parent_analysis_result_ref="analysis-result:sha256:" + "0" * 64,
            analysis_lineage_qualification_ref="analysis-lineage:0",
            model_fingerprint=MODEL_FINGERPRINT,
            evidence_epoch_id=EVIDENCE_EPOCH,
            design_state_ref="design-state:sha256:" + "0" * 64,
            design_result_ref="design-result:sha256:" + "0" * 64,
            design_attempt_ref=DESIGN_ATTEMPT,
            design_generation_ref=DESIGN_GENERATION,
            requested_result_scope_refs=RESULT_SCOPE,
            reconciled_result_scope_refs=RESULT_SCOPE,
            combo_grain_binding_refs=COMBO_BINDINGS,
            provenance_refs=("proof:test",),
        )
