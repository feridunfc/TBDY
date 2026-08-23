from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
import json

import pytest

import tbdy_engine.regulatory.authority as authority_module
from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.regulatory import (
    ApplicabilityBinding,
    ApplicabilityState,
    ApprovedImplementationBinding,
    AuthorityReviewRecord,
    AuthorityReviewStatus,
    CheckEvaluatorBinding,
    CheckSpec,
    Grain,
    RegulatoryAuthorityCatalog,
    RegulatoryAuthorityError,
    RegulatoryClaim,
    RegulatoryRegistry,
    RegulatorySourceDocument,
    RuleId,
    SourceAnchor,
    implementation_fingerprint,
    regulatory_claim_fingerprint,
    validate_rule_authority,
)
from tbdy_engine.regulatory.kernel import (
    KernelCompileError,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RuleExecutionEnvelope,
    RuleScopeTarget,
)


@dataclass(frozen=True, slots=True)
class AppInput:
    applies: bool = True


@dataclass(frozen=True, slots=True)
class ExecInput:
    envelope: RuleExecutionEnvelope

    @classmethod
    def from_declared_dependencies(cls, envelope, dependencies):
        assert tuple(dependencies) == ()
        return cls(envelope)


def _app(value: AppInput) -> ApplicabilityState:
    return ApplicabilityState.APPLIES if value.applies else ApplicabilityState.PROVEN_NOT_APPLICABLE


def _evaluate(inp: ExecInput) -> CheckResult:
    return CheckResult(
        check_id=inp.envelope.rule_id.value,
        component=inp.envelope.instance_id.scope_ref,
        component_type="synthetic_f0_9",
        status=CheckStatus.OK,
        value=1.0,
        code_ref="SYNTHETIC-SOURCE-REF",
    )


def _spec(
    rule_id: str = "SYNTHETIC_AUTHORITY_RULE",
    *,
    rule_version: str = "v1",
    evaluator_binding_id: str | None = None,
) -> CheckSpec:
    rid = RuleId(rule_id)
    return CheckSpec(
        rule_id=rid,
        code_refs=("SYNTHETIC-SOURCE-REF",),
        rule_version=rule_version,
        formal_result_type=CheckResult,
        dependencies=(),
        applicability=ApplicabilityBinding(f"app:{rule_id}", AppInput, _app),
        evaluator=CheckEvaluatorBinding(evaluator_binding_id or f"eval:{rule_id}", ExecInput, _evaluate),
    )


@pytest.fixture
def module_sources(monkeypatch):
    sources = {
        __name__: b"reviewed-implementation-v1",
        "synthetic.helper": b"reviewed-helper-v1",
        "synthetic.unrelated": b"unrelated-v1",
    }

    def read_module(module_name: str) -> bytes:
        try:
            return sources[module_name]
        except KeyError as exc:
            raise AssertionError(f"unexpected module fingerprint request: {module_name}") from exc

    monkeypatch.setattr(authority_module, "_module_source_bytes", read_module)
    return sources


def _fingerprint(spec: CheckSpec, modules=(__name__,)) -> str:
    return implementation_fingerprint(
        rule_id=spec.rule_id,
        rule_version=spec.rule_version,
        evaluator_binding_id=spec.evaluator.binding_id,
        implementation_modules=modules,
    )


def _catalog(
    spec: CheckSpec,
    *,
    fingerprint: str,
    review_status: AuthorityReviewStatus = AuthorityReviewStatus.APPROVED,
    normalized_statement: str = "Synthetic reviewed proposition for F0.9 infrastructure tests.",
    claim_version: str = "c1",
    anchor_locator: str = "clause TEST.1",
    source_edition: str = "test-edition",
    source_fingerprint: str = "sha256:synthetic-source",
    review_version: str = "r1",
    reviewed_claim_fingerprint: str | None = None,
    binding_id: str | None = None,
    binding_version: str = "b1",
    evaluator_binding_id: str | None = None,
    rule_version: str | None = None,
    rule_id: RuleId | None = None,
    implementation_modules=(__name__,),
) -> RegulatoryAuthorityCatalog:
    source = RegulatorySourceDocument(
        source_id="SRC",
        title="Synthetic Test Regulation",
        edition=source_edition,
        issuer="OpenAI test fixture",
        jurisdiction="TEST",
        source_fingerprint=source_fingerprint,
    )
    anchor = SourceAnchor(anchor_id="ANCHOR", source_id=source.source_id, locator=anchor_locator)
    claim = RegulatoryClaim(
        claim_id="CLAIM",
        claim_version=claim_version,
        anchor_refs=(anchor.anchor_id,),
        normalized_statement=normalized_statement,
    )
    current_claim_fingerprint = regulatory_claim_fingerprint(
        claim=claim,
        anchors=(anchor,),
        source_documents=(source,),
    )
    review = AuthorityReviewRecord(
        review_id="REVIEW",
        claim_id=claim.claim_id,
        status=review_status,
        review_version=review_version,
        reviewed_claim_fingerprint=reviewed_claim_fingerprint or current_claim_fingerprint,
        review_basis_refs=("review-package:test",),
    )
    binding = ApprovedImplementationBinding(
        binding_id=binding_id or f"BIND:{spec.rule_id.value}",
        rule_id=rule_id or spec.rule_id,
        claim_refs=(claim.claim_id,),
        review_refs=(review.review_id,),
        evaluator_binding_id=evaluator_binding_id or spec.evaluator.binding_id,
        rule_version=rule_version or spec.rule_version,
        implementation_modules=implementation_modules,
        approved_implementation_fingerprint=fingerprint,
        binding_version=binding_version,
    )
    return RegulatoryAuthorityCatalog(
        source_documents=(source,),
        anchors=(anchor,),
        claims=(claim,),
        review_records=(review,),
        implementation_bindings=(binding,),
    )


def _target(spec: CheckSpec, scope_ref: str = "C1") -> RuleScopeTarget:
    return RuleScopeTarget(
        rule_id=spec.rule_id,
        grain=Grain.COMPONENT,
        scope_ref=scope_ref,
        applicability_input=AppInput(),
    )


def _compile(spec: CheckSpec, catalog: RegulatoryAuthorityCatalog | None):
    return RegulatoryCompiler.compile(
        RegulatoryRegistry(checks=(spec,)),
        RegulatoryCompileInputs(
            rule_targets=(_target(spec),),
            regulatory_authority_catalog=catalog,
        ),
    )


def _old_review_fingerprint(catalog: RegulatoryAuthorityCatalog) -> str:
    return catalog.review_records[0].reviewed_claim_fingerprint


def test_A_source_catalog_is_immutable_deterministic_and_canonically_ordered(module_sources):
    spec = _spec()
    fp = _fingerprint(spec)
    first = _catalog(spec, fingerprint=fp)
    second = RegulatoryAuthorityCatalog(
        source_documents=tuple(reversed(first.source_documents)),
        anchors=tuple(reversed(first.anchors)),
        claims=tuple(reversed(first.claims)),
        review_records=tuple(reversed(first.review_records)),
        implementation_bindings=tuple(reversed(first.implementation_bindings)),
    )
    assert first.catalog_version == second.catalog_version
    assert first.source_documents == second.source_documents
    with pytest.raises(FrozenInstanceError):
        first.source_documents[0].title = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.review_records[0].reviewed_claim_fingerprint = "sha256:mutated"  # type: ignore[misc]


@pytest.mark.parametrize("family", ["source", "anchor", "claim", "review", "binding"])
def test_B_duplicate_authority_identities_fail(family):
    source = RegulatorySourceDocument("SRC", "Synthetic", "1", "Issuer", "TEST", "sha256:src")
    anchor = SourceAnchor("A", "SRC", "clause 1")
    claim = RegulatoryClaim(claim_id="C", claim_version="1", anchor_refs=("A",), normalized_statement="Claim")
    claim_fp = regulatory_claim_fingerprint(claim=claim, anchors=(anchor,), source_documents=(source,))
    review = AuthorityReviewRecord(
        review_id="R",
        claim_id="C",
        status=AuthorityReviewStatus.APPROVED,
        review_version="1",
        reviewed_claim_fingerprint=claim_fp,
        review_basis_refs=(),
    )
    binding = ApprovedImplementationBinding(
        binding_id="B",
        rule_id=RuleId("RULE"),
        claim_refs=("C",),
        review_refs=("R",),
        evaluator_binding_id="eval:RULE",
        rule_version="v1",
        implementation_modules=(__name__,),
        approved_implementation_fingerprint="sha256:test",
        binding_version="1",
    )
    kwargs = {
        "source_documents": (source,),
        "anchors": (anchor,),
        "claims": (claim,),
        "review_records": (review,),
        "implementation_bindings": (binding,),
    }
    key = {
        "source": "source_documents",
        "anchor": "anchors",
        "claim": "claims",
        "review": "review_records",
        "binding": "implementation_bindings",
    }[family]
    kwargs[key] = (kwargs[key][0], kwargs[key][0])
    with pytest.raises(ValueError, match="duplicate"):
        RegulatoryAuthorityCatalog(**kwargs)


def test_C_missing_anchor_source_fails():
    with pytest.raises(ValueError, match="missing source document"):
        RegulatoryAuthorityCatalog(anchors=(SourceAnchor("A", "MISSING", "clause 1"),))


def test_D_missing_claim_anchor_fails():
    source = RegulatorySourceDocument("SRC", "Synthetic", "1", "Issuer", "TEST", "sha256:src")
    claim = RegulatoryClaim(claim_id="C", claim_version="1", anchor_refs=("MISSING",), normalized_statement="Claim")
    with pytest.raises(ValueError, match="missing anchor"):
        RegulatoryAuthorityCatalog(source_documents=(source,), claims=(claim,))


def test_E_missing_review_claim_fails():
    review = AuthorityReviewRecord(
        review_id="R",
        claim_id="MISSING",
        status=AuthorityReviewStatus.APPROVED,
        review_version="1",
        reviewed_claim_fingerprint="sha256:reviewed",
        review_basis_refs=(),
    )
    with pytest.raises(ValueError, match="missing claim for review"):
        RegulatoryAuthorityCatalog(review_records=(review,))


def test_F_approved_exact_review_produces_validated_authority(module_sources):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec))
    validated = validate_rule_authority(spec, catalog)
    assert validated.rule_id == spec.rule_id
    assert validated.binding_id == catalog.implementation_bindings[0].binding_id


@pytest.mark.parametrize(
    "status",
    [AuthorityReviewStatus.DRAFT, AuthorityReviewStatus.REJECTED, AuthorityReviewStatus.SUPERSEDED],
)
def test_G_H_I_nonapproved_reviews_never_produce_executable_authority(module_sources, status):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec), review_status=status)
    with pytest.raises(RegulatoryAuthorityError, match="UNAPPROVED_REGULATORY_CLAIM_REVIEW"):
        validate_rule_authority(spec, catalog)


def test_J_binding_rule_id_mismatch_is_rejected(module_sources):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec), rule_id=RuleId("OTHER_RULE"))
    with pytest.raises(RegulatoryAuthorityError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        validate_rule_authority(spec, catalog)


def test_K_evaluator_binding_mismatch_is_rejected(module_sources):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec), evaluator_binding_id="eval:wrong")
    with pytest.raises(RegulatoryAuthorityError, match="REGULATORY_EVALUATOR_BINDING_MISMATCH"):
        validate_rule_authority(spec, catalog)


def test_L_rule_version_mismatch_is_rejected(module_sources):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec), rule_version="v999")
    with pytest.raises(RegulatoryAuthorityError, match="REGULATORY_RULE_VERSION_MISMATCH"):
        validate_rule_authority(spec, catalog)


def test_M_missing_claim_or_review_binding_reference_is_rejected():
    source = RegulatorySourceDocument("SRC", "Synthetic", "1", "Issuer", "TEST", "sha256:src")
    binding = ApprovedImplementationBinding(
        binding_id="B",
        rule_id=RuleId("RULE"),
        claim_refs=("MISSING",),
        review_refs=("MISSING_REVIEW",),
        evaluator_binding_id="eval:RULE",
        rule_version="v1",
        implementation_modules=(__name__,),
        approved_implementation_fingerprint="sha256:test",
        binding_version="1",
    )
    with pytest.raises(ValueError, match="missing claim for implementation binding"):
        RegulatoryAuthorityCatalog(source_documents=(source,), implementation_bindings=(binding,))


def test_N_implementation_fingerprint_is_deterministic_and_module_order_independent(module_sources):
    spec = _spec()
    first = _fingerprint(spec, modules=(__name__, "synthetic.helper"))
    second = _fingerprint(spec, modules=("synthetic.helper", __name__))
    assert first == second


def test_O_reviewed_implementation_module_change_changes_fingerprint(module_sources):
    spec = _spec()
    before = _fingerprint(spec)
    module_sources[__name__] = b"reviewed-implementation-v2"
    after = _fingerprint(spec)
    assert before != after


def test_P_unrelated_module_change_does_not_change_fingerprint(module_sources):
    spec = _spec()
    before = _fingerprint(spec)
    module_sources["synthetic.unrelated"] = b"unrelated-v2"
    after = _fingerprint(spec)
    assert before == after


def test_Q_stale_implementation_binding_blocks_compilation_before_execution(module_sources):
    spec = _spec()
    approved = _fingerprint(spec)
    catalog = _catalog(spec, fingerprint=approved)
    module_sources[__name__] = b"reviewed-implementation-after-approval"
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_IMPLEMENTATION_BINDING"):
        _compile(spec, catalog)


def test_R_code_refs_without_authority_binding_block_catalog_enabled_compilation(module_sources):
    spec = _spec()
    empty_catalog = RegulatoryAuthorityCatalog()
    assert spec.code_refs
    with pytest.raises(KernelCompileError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        _compile(spec, empty_catalog)


def test_S_one_unbound_target_blocks_the_whole_plan(module_sources):
    bound = _spec("BOUND_RULE")
    unbound = _spec("UNBOUND_RULE")
    catalog = _catalog(bound, fingerprint=_fingerprint(bound))
    registry = RegulatoryRegistry(checks=(bound, unbound))
    inputs = RegulatoryCompileInputs(
        rule_targets=(_target(bound, "C1"), _target(unbound, "C2")),
        regulatory_authority_catalog=catalog,
    )
    with pytest.raises(KernelCompileError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        RegulatoryCompiler.compile(registry, inputs)


def test_T_same_authoritative_inputs_produce_identical_catalog_version(module_sources):
    spec = _spec()
    fp = _fingerprint(spec)
    assert _catalog(spec, fingerprint=fp).catalog_version == _catalog(spec, fingerprint=fp).catalog_version


def test_U_same_authoritative_compile_produces_identical_plan_identity(module_sources):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec))
    first = _compile(spec, catalog)
    second = _compile(spec, catalog)
    assert first.plan.plan_identity == second.plan.plan_identity
    assert first.plan.regulatory_authority_catalog_version == catalog.catalog_version
    assert first.plan.compiled_authority_binding_refs == second.plan.compiled_authority_binding_refs
    assert first.plan.compiled_authority_fingerprints == second.plan.compiled_authority_fingerprints
    assert "F0.9_SOURCE_AUTHORITY_OK" in first.plan.compile_diagnostics


def test_V_normalized_statement_change_with_old_review_is_stale(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        normalized_statement="Changed reviewed proposition.",
        reviewed_claim_fingerprint=_old_review_fingerprint(base),
    )
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        _compile(spec, changed)


def test_W_claim_version_change_with_old_review_is_stale(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        claim_version="c2",
        reviewed_claim_fingerprint=_old_review_fingerprint(base),
    )
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        _compile(spec, changed)


def test_X_anchor_locator_change_with_old_review_is_stale(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        anchor_locator="clause TEST.2",
        reviewed_claim_fingerprint=_old_review_fingerprint(base),
    )
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        _compile(spec, changed)


def test_Y_source_edition_change_with_old_review_is_stale(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        source_edition="test-edition-2",
        reviewed_claim_fingerprint=_old_review_fingerprint(base),
    )
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        _compile(spec, changed)


def test_Z_source_fingerprint_change_with_old_review_is_stale(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        source_fingerprint="sha256:synthetic-source-v2",
        reviewed_claim_fingerprint=_old_review_fingerprint(base),
    )
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        _compile(spec, changed)


def test_AA_changed_claim_with_new_matching_review_compiles(module_sources):
    spec = _spec()
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        normalized_statement="Changed and re-reviewed proposition.",
        review_version="r2",
    )
    program = _compile(spec, changed)
    assert "F0.9_SOURCE_AUTHORITY_OK" in program.plan.compile_diagnostics


def test_AB_successful_rereview_changes_catalog_version_and_plan_identity(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    changed = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        normalized_statement="Changed and re-reviewed proposition.",
        review_version="r2",
    )
    assert base.catalog_version != changed.catalog_version
    assert _compile(spec, base).plan.plan_identity != _compile(spec, changed).plan.plan_identity


def test_AC_review_fingerprint_participates_in_catalog_identity(module_sources):
    spec = _spec()
    base = _catalog(spec, fingerprint=_fingerprint(spec))
    altered_review = _catalog(
        spec,
        fingerprint=_fingerprint(spec),
        reviewed_claim_fingerprint="sha256:different-reviewed-snapshot",
    )
    assert base.catalog_version != altered_review.catalog_version


def test_AD_catalog_enabled_program_executes_through_existing_compiler_and_engine(module_sources):
    spec = _spec()
    catalog = _catalog(spec, fingerprint=_fingerprint(spec))
    program = _compile(spec, catalog)
    snapshot = RegulatoryEngine.execute(program)
    results = snapshot.formal_results_for(program.plan.compiled_rule_instances[0])
    assert len(results) == 1
    assert results[0].status is CheckStatus.OK
    binding_ref = json.loads(program.plan.compiled_authority_binding_refs[0])
    assert binding_ref[0] == program.plan.compiled_rule_instances[0].value
    assert binding_ref[1] == catalog.implementation_bindings[0].binding_id
    binding = catalog.binding(binding_ref[1])
    claim = catalog.claim(binding.claim_refs[0])
    anchor = catalog.anchor(claim.anchor_refs[0])
    source = catalog.source(anchor.source_id)
    assert source.source_id == "SRC"


def test_AE_no_catalog_preserves_legacy_compiler_path_identity_and_diagnostics():
    spec = _spec()
    first = _compile(spec, None)
    second = _compile(spec, None)
    assert first.plan.plan_identity == second.plan.plan_identity
    assert first.plan.regulatory_authority_catalog_version is None
    assert first.plan.compiled_authority_binding_refs == ()
    assert first.plan.compiled_authority_fingerprints == ()
    assert first.plan.compile_diagnostics == (
        "F0.1_COMPILE_OK",
        "TOPOLOGICAL_TIE_BREAK=RuleInstanceId.value lexical order",
    )
    result = RegulatoryEngine.execute(first).formal_results_for(first.plan.compiled_rule_instances[0])[0]
    assert result.status is CheckStatus.OK


def test_AF_evaluator_module_must_be_explicitly_reviewed(module_sources):
    spec = _spec()
    fp = _fingerprint(spec, modules=("synthetic.helper",))
    catalog = _catalog(
        spec,
        fingerprint=fp,
        implementation_modules=("synthetic.helper",),
    )
    with pytest.raises(RegulatoryAuthorityError, match="EVALUATOR_IMPLEMENTATION_MODULE_NOT_REVIEWED"):
        validate_rule_authority(spec, catalog)


def test_AG_regulatory_claim_fingerprint_is_deterministic_and_exact():
    source = RegulatorySourceDocument("SRC", "Synthetic", "1", "Issuer", "TEST", "sha256:src")
    anchor = SourceAnchor("A", "SRC", "clause 1")
    claim = RegulatoryClaim(
        claim_id="C",
        claim_version="1",
        anchor_refs=("A",),
        normalized_statement="Reviewed claim.",
    )
    first = regulatory_claim_fingerprint(claim=claim, anchors=(anchor,), source_documents=(source,))
    second = regulatory_claim_fingerprint(claim=claim, anchors=(anchor,), source_documents=(source,))
    assert first == second
    changed = RegulatoryClaim(
        claim_id="C",
        claim_version="1",
        anchor_refs=("A",),
        normalized_statement="Changed claim.",
    )
    assert first != regulatory_claim_fingerprint(claim=changed, anchors=(anchor,), source_documents=(source,))
