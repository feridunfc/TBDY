"""Focused FND-COL-4B1 PMM source and numerical-policy authority proofs."""
from __future__ import annotations

from dataclasses import replace
import ast
from pathlib import Path

import pytest

import tbdy_engine.regulatory.column_pmm_authority as subject
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.regulatory.authority import (
    ApprovedImplementationBinding,
    RegulatoryAuthorityCatalog,
    RegulatoryAuthorityError,
    implementation_fingerprint,
    regulatory_claim_fingerprint,
    validate_rule_authority,
)
from tbdy_engine.regulatory.column_pmm_authority import (
    FND_COL_4_PMM_ANGLE_COUNT,
    FND_COL_4_PMM_AXIAL_TOLERANCE_N,
    FND_COL_4_PMM_CHECK_SPEC,
    FND_COL_4_PMM_RULE_ID,
    FND_COL_4_PMM_SUPPORTED_FCK_MPA,
    FND_COL_4_PMM_VALIDATED_DOMAIN_REF,
    PMM_IMPLEMENTATION_MODULES,
    ColumnPmmRuleProbe,
    ValidatedPmmNumericalPolicy,
    authorize_pmm_numerical_policy,
)
from tbdy_engine.regulatory.contracts import Grain
from tbdy_engine.regulatory.kernel import (
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.sources.fnd_col_4_pmm import (
    APPROVED_IMPLEMENTATION_FINGERPRINT,
    CLAIM_DATA,
    CLAIMS_FOR_RULE,
    FND_COL_4_PMM_AUTHORITY_CATALOG,
    IMPLEMENTATION_MODULES,
)


def _copy_catalog(
    catalog: RegulatoryAuthorityCatalog,
    *,
    claims=None,
    reviews=None,
    bindings=None,
) -> RegulatoryAuthorityCatalog:
    return RegulatoryAuthorityCatalog(
        source_documents=catalog.source_documents,
        anchors=catalog.anchors,
        claims=(
            catalog.claims
            if claims is None
            else claims
        ),
        review_records=(
            catalog.review_records
            if reviews is None
            else reviews
        ),
        implementation_bindings=(
            catalog.implementation_bindings
            if bindings is None
            else bindings
        ),
    )


def _probe(
    fck: float = 30.0,
) -> ColumnPmmRuleProbe:
    return ColumnPmmRuleProbe(
        component_id="C1",
        fck_mpa=fck,
        fcd_mpa=20.0,
        fyd_mpa=365.0,
    )


def test_exact_claim_fingerprints_match_reviewed_literals():
    catalog = FND_COL_4_PMM_AUTHORITY_CATALOG

    assert set(CLAIMS_FOR_RULE) == set(CLAIM_DATA)
    assert len(CLAIMS_FOR_RULE) == 5

    for claim_id, (
        _anchor_refs,
        _version,
        _statement,
        expected,
    ) in CLAIM_DATA.items():
        claim = catalog.claim(claim_id)
        anchors = tuple(
            catalog.anchor(ref)
            for ref in claim.anchor_refs
        )

        source_ids = sorted(
            {
                anchor.source_id
                for anchor in anchors
            }
        )

        actual = regulatory_claim_fingerprint(
            claim=claim,
            anchors=anchors,
            source_documents=tuple(
                catalog.source(source_id)
                for source_id in source_ids
            ),
        )

        assert actual == expected

        review = catalog.review(
            f"FND_COL_4_PMM_REVIEW:{claim_id}:r1"
        )

        assert (
            review.reviewed_claim_fingerprint
            == expected
        )


def test_exact_implementation_fingerprint_matches_sealed_literal():
    assert (
        IMPLEMENTATION_MODULES
        == PMM_IMPLEMENTATION_MODULES
    )

    actual = implementation_fingerprint(
        rule_id=FND_COL_4_PMM_CHECK_SPEC.rule_id,
        rule_version=(
            FND_COL_4_PMM_CHECK_SPEC.rule_version
        ),
        evaluator_binding_id=(
            FND_COL_4_PMM_CHECK_SPEC.evaluator.binding_id
        ),
        implementation_modules=IMPLEMENTATION_MODULES,
    )

    assert actual == APPROVED_IMPLEMENTATION_FINGERPRINT

    assert APPROVED_IMPLEMENTATION_FINGERPRINT.startswith(
        "sha256:"
    )

    assert (
        "__FND_COL_4_PMM_IMPL_FP__"
        not in APPROVED_IMPLEMENTATION_FINGERPRINT
    )


def test_strict_compiler_accepts_actual_pmm_authority_catalog():
    registry = RegulatoryRegistry(
        checks=(FND_COL_4_PMM_CHECK_SPEC,)
    )

    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=FND_COL_4_PMM_RULE_ID,
                    grain=Grain.COMPONENT,
                    scope_ref="C1",
                    applicability_input=_probe(),
                ),
            ),
            regulatory_authority_catalog=(
                FND_COL_4_PMM_AUTHORITY_CATALOG
            ),
        ),
    )

    assert (
        "F0.9_SOURCE_AUTHORITY_OK"
        in program.plan.compile_diagnostics
    )

    assert (
        program.plan.regulatory_authority_catalog_version
        == FND_COL_4_PMM_AUTHORITY_CATALOG.catalog_version
    )

    assert program.plan.compiled_authority_fingerprints


def test_stale_pmm_implementation_binding_fails_closed():
    binding = (
        FND_COL_4_PMM_AUTHORITY_CATALOG
        .implementation_bindings[0]
    )

    stale_binding = ApprovedImplementationBinding(
        binding_id=binding.binding_id,
        rule_id=binding.rule_id,
        claim_refs=binding.claim_refs,
        review_refs=binding.review_refs,
        evaluator_binding_id=(
            binding.evaluator_binding_id
        ),
        rule_version=binding.rule_version,
        implementation_modules=(
            binding.implementation_modules
        ),
        approved_implementation_fingerprint=(
            "sha256:" + "0" * 64
        ),
        binding_version=binding.binding_version,
    )

    stale = _copy_catalog(
        FND_COL_4_PMM_AUTHORITY_CATALOG,
        bindings=(stale_binding,),
    )

    with pytest.raises(
        RegulatoryAuthorityError,
        match="STALE_REGULATORY_IMPLEMENTATION_BINDING",
    ):
        validate_rule_authority(
            FND_COL_4_PMM_CHECK_SPEC,
            stale,
        )


def test_stale_pmm_claim_review_fails_closed():
    claims = list(
        FND_COL_4_PMM_AUTHORITY_CATALOG.claims
    )

    target = claims[0]

    claims[0] = replace(
        target,
        normalized_statement=(
            target.normalized_statement
            + " Unreviewed drift."
        ),
    )

    stale = _copy_catalog(
        FND_COL_4_PMM_AUTHORITY_CATALOG,
        claims=tuple(claims),
    )

    with pytest.raises(
        RegulatoryAuthorityError,
        match="STALE_REGULATORY_CLAIM_REVIEW",
    ):
        validate_rule_authority(
            FND_COL_4_PMM_CHECK_SPEC,
            stale,
        )


def test_numerical_policy_is_authority_created_and_exactly_bounded():
    with pytest.raises(
        TypeError,
        match="authority-created only",
    ):
        ValidatedPmmNumericalPolicy()

    policy = authorize_pmm_numerical_policy(
        authority_catalog=(
            FND_COL_4_PMM_AUTHORITY_CATALOG
        )
    )

    assert (
        policy.authority
        == "VALIDATED_PMM_NUMERICAL_POLICY"
    )

    assert policy.angle_count == 1152
    assert (
        policy.angle_count
        == FND_COL_4_PMM_ANGLE_COUNT
    )

    assert policy.axial_tolerance_n == pytest.approx(
        1.0
    )

    assert (
        policy.axial_tolerance_n
        == FND_COL_4_PMM_AXIAL_TOLERANCE_N
    )

    assert policy.supported_fck_mpa == (
        25.0,
        30.0,
        35.0,
        40.0,
        45.0,
        50.0,
    )

    assert (
        policy.supported_fck_mpa
        == FND_COL_4_PMM_SUPPORTED_FCK_MPA
    )

    assert (
        policy.validated_domain_ref
        == FND_COL_4_PMM_VALIDATED_DOMAIN_REF
    )

    assert len(policy.validation_evidence_refs) == 5

    assert set(policy.source_claim_refs) == set(
        CLAIMS_FOR_RULE
    )

    assert (
        policy.implementation_fingerprint
        == APPROVED_IMPLEMENTATION_FINGERPRINT
    )

    assert policy.policy_fingerprint.startswith(
        "sha256:"
    )


def test_policy_does_not_silently_expand_domain():
    policy = authorize_pmm_numerical_policy(
        authority_catalog=(
            FND_COL_4_PMM_AUTHORITY_CATALOG
        )
    )

    assert 16.0 not in policy.supported_fck_mpa
    assert 18.0 not in policy.supported_fck_mpa
    assert 20.0 not in policy.supported_fck_mpa
    assert 55.0 not in policy.supported_fck_mpa

    supported = (
        FND_COL_4_PMM_CHECK_SPEC
        .evaluator
        .evaluator(_probe(50.0))
    )

    unsupported = (
        FND_COL_4_PMM_CHECK_SPEC
        .evaluator
        .evaluator(_probe(55.0))
    )

    assert supported.status is CheckStatus.OK
    assert unsupported.status is CheckStatus.NO_DATA


def test_pmm_authority_module_does_not_execute_rebar_selection():
    path = Path(subject.__file__).resolve()

    tree = ast.parse(
        path.read_text(encoding="utf-8-sig")
    )

    imported_modules = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name
                for alias in node.names
            )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)

    assert (
        "tbdy_engine.design.columns.rebar_selection"
        not in imported_modules
    )

    assert (
        "tbdy_engine.design.columns."
        "rebar_selection_authority"
        not in imported_modules
    )

    assert (
        "tbdy_engine.design.columns."
        "column_rebar_design_engine"
        not in imported_modules
    )
