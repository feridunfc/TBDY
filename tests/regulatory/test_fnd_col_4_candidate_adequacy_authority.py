"""Focused FND-COL-4C1A candidate adequacy authority proofs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import ast
from pathlib import Path

import pytest

import tbdy_engine.regulatory.column_candidate_adequacy_authority as subject

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.regulatory.authority import (
    ApprovedImplementationBinding,
    RegulatoryAuthorityCatalog,
    RegulatoryAuthorityError,
    implementation_fingerprint,
    regulatory_claim_fingerprint,
    validate_rule_authority,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    AREA_GUARD_INSUFFICIENT,
    AREA_GUARD_SATISFIED,
    CANDIDATE_ADEQUACY_IMPLEMENTATION_MODULES,
    CandidatePmmAdequacyProbe,
    FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC,
    FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID,
    FND_COL_4_ETABS_AREA_TOLERANCE_MM2,
    FND_COL_4_PMM_UTILIZATION_LIMIT,
    ValidatedCandidateAdequacyPolicy,
    authorize_candidate_adequacy_policy,
    evaluate_candidate_pmm_adequacy,
    evaluate_required_area_guard,
)
from tbdy_engine.regulatory.contracts import Grain
from tbdy_engine.regulatory.kernel import (
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import (
    APPROVED_IMPLEMENTATION_FINGERPRINT,
    CLAIM_DATA,
    CLAIMS_FOR_RULE,
    FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
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


def _policy():
    return authorize_candidate_adequacy_policy(
        authority_catalog=(
            FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
        )
    )


def test_exact_claim_fingerprints_match_reviewed_literals():
    catalog = (
        FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
    )

    assert set(CLAIMS_FOR_RULE) == set(CLAIM_DATA)
    assert len(CLAIMS_FOR_RULE) == 4

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
            (
                "FND_COL_4_CANDIDATE_ADEQUACY_REVIEW:"
                f"{claim_id}:r1"
            )
        )

        assert (
            review.reviewed_claim_fingerprint
            == expected
        )


def test_exact_implementation_fingerprint_is_sealed():
    assert (
        IMPLEMENTATION_MODULES
        == CANDIDATE_ADEQUACY_IMPLEMENTATION_MODULES
    )

    actual = implementation_fingerprint(
        rule_id=(
            FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC.rule_id
        ),
        rule_version=(
            FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC.rule_version
        ),
        evaluator_binding_id=(
            FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC
            .evaluator
            .binding_id
        ),
        implementation_modules=IMPLEMENTATION_MODULES,
    )

    assert (
        actual
        == APPROVED_IMPLEMENTATION_FINGERPRINT
    )

    assert (
        APPROVED_IMPLEMENTATION_FINGERPRINT
        .startswith("sha256:")
    )

    assert (
        "__FND_COL_4_C1A_IMPL_FP__"
        not in APPROVED_IMPLEMENTATION_FINGERPRINT
    )


def test_strict_compiler_accepts_candidate_adequacy_authority():
    registry = RegulatoryRegistry(
        checks=(
            FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC,
        )
    )

    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=(
                        FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID
                    ),
                    grain=Grain.COMPONENT,
                    scope_ref="C1",
                    applicability_input=(
                        CandidatePmmAdequacyProbe(
                            component_id="C1",
                            numerically_resolved=True,
                            utilization=1.0,
                        )
                    ),
                ),
            ),
            regulatory_authority_catalog=(
                FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
            ),
        ),
    )

    assert (
        "F0.9_SOURCE_AUTHORITY_OK"
        in program.plan.compile_diagnostics
    )


def test_policy_is_factory_only_and_exactly_bounded():
    with pytest.raises(
        TypeError,
        match="authority-created only",
    ):
        ValidatedCandidateAdequacyPolicy()

    policy = _policy()

    assert (
        policy.authority
        == "VALIDATED_COLUMN_CANDIDATE_ADEQUACY_POLICY"
    )

    assert (
        policy.pmm_utilization_limit
        == FND_COL_4_PMM_UTILIZATION_LIMIT
        == 1.0
    )

    assert policy.require_every_pmm_row

    assert (
        policy.require_every_etabs_required_rebar_row
    )

    assert (
        policy.etabs_area_tolerance_mm2
        == FND_COL_4_ETABS_AREA_TOLERANCE_MM2
        == Decimal("0")
    )


def test_pmm_adequacy_boundary_is_exact_rd_greater_equal_fd():
    policy = _policy()

    below = evaluate_candidate_pmm_adequacy(
        policy=policy,
        component_id="C1",
        numerically_resolved=True,
        utilization=0.999999,
    )

    boundary = evaluate_candidate_pmm_adequacy(
        policy=policy,
        component_id="C1",
        numerically_resolved=True,
        utilization=1.0,
    )

    above = evaluate_candidate_pmm_adequacy(
        policy=policy,
        component_id="C1",
        numerically_resolved=True,
        utilization=1.000001,
    )

    unresolved = evaluate_candidate_pmm_adequacy(
        policy=policy,
        component_id="C1",
        numerically_resolved=False,
        utilization=None,
    )

    assert below.status == CheckStatus.OK
    assert boundary.status == CheckStatus.OK
    assert above.status == CheckStatus.FAIL
    assert unresolved.status == CheckStatus.NO_DATA

    assert boundary.ratio == pytest.approx(1.0)
    assert boundary.limit == pytest.approx(1.0)
    assert boundary.pass_rule == "ratio <= limit"


def test_p8a_required_area_guard_has_no_hidden_tolerance():
    policy = _policy()

    exact = evaluate_required_area_guard(
        policy=policy,
        candidate_as_mm2=Decimal("4200"),
        required_as_mm2=Decimal("4200"),
    )

    enough = evaluate_required_area_guard(
        policy=policy,
        candidate_as_mm2=Decimal("4200.0001"),
        required_as_mm2=Decimal("4200"),
    )

    short = evaluate_required_area_guard(
        policy=policy,
        candidate_as_mm2=Decimal("4199.9999"),
        required_as_mm2=Decimal("4200"),
    )

    assert exact.status == AREA_GUARD_SATISFIED
    assert enough.status == AREA_GUARD_SATISFIED
    assert short.status == AREA_GUARD_INSUFFICIENT

    assert exact.margin_mm2 == Decimal("0")
    assert short.margin_mm2 == Decimal("-0.0001")


def test_stale_implementation_binding_fails_closed():
    catalog = (
        FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
    )

    binding = catalog.implementation_bindings[0]

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
        catalog,
        bindings=(stale_binding,),
    )

    with pytest.raises(
        RegulatoryAuthorityError,
        match="STALE_REGULATORY_IMPLEMENTATION_BINDING",
    ):
        validate_rule_authority(
            FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC,
            stale,
        )


def test_stale_claim_review_fails_closed():
    catalog = (
        FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
    )

    claims = list(catalog.claims)

    target = claims[0]

    claims[0] = replace(
        target,
        normalized_statement=(
            target.normalized_statement
            + " Unreviewed drift."
        ),
    )

    stale = _copy_catalog(
        catalog,
        claims=tuple(claims),
    )

    with pytest.raises(
        RegulatoryAuthorityError,
        match="STALE_REGULATORY_CLAIM_REVIEW",
    ):
        validate_rule_authority(
            FND_COL_4_CANDIDATE_ADEQUACY_CHECK_SPEC,
            stale,
        )


def test_c1a_contains_no_legacy_selection_or_etabs_access():
    path = Path(subject.__file__).resolve()

    source = path.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(source)

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)

        elif isinstance(node, ast.Import):
            imports.update(
                alias.name
                for alias in node.names
            )

    forbidden = {
        "tbdy_engine.design.columns.rebar_selection",
        (
            "tbdy_engine.design.columns."
            "rebar_selection_authority"
        ),
        (
            "tbdy_engine.design.columns."
            "column_rebar_design_engine"
        ),
        "tbdy_engine.features.etabs_com_attach",
    }

    assert imports.isdisjoint(forbidden)

    assert "RunAnalysis" not in source
    assert "StartDesign" not in source


def test_candidate_aggregate_requires_every_row_and_is_exact():
    policy = _policy()

    adequate = subject.aggregate_candidate_adequacy(
        policy=policy,
        pmm_statuses=(
            CheckStatus.OK,
            CheckStatus.OK,
        ),
        area_guard_statuses=(
            subject.AREA_GUARD_SATISFIED,
            subject.AREA_GUARD_SATISFIED,
        ),
    )

    assert (
        adequate.status
        == subject.CANDIDATE_ADEQUATE
    )

    unresolved = subject.aggregate_candidate_adequacy(
        policy=policy,
        pmm_statuses=(
            CheckStatus.OK,
            CheckStatus.NO_DATA,
        ),
        area_guard_statuses=(
            subject.AREA_GUARD_SATISFIED,
        ),
    )

    assert (
        unresolved.status
        == subject.CANDIDATE_UNRESOLVED
    )

    with pytest.raises(
        subject.ColumnCandidateAdequacyAuthorityError,
        match="PMM decision population is empty",
    ):
        subject.aggregate_candidate_adequacy(
            policy=policy,
            pmm_statuses=(),
            area_guard_statuses=(
                subject.AREA_GUARD_SATISFIED,
            ),
        )


def test_proven_inadequacy_governs_even_if_other_row_unresolved():
    policy = _policy()

    pmm_fail = subject.aggregate_candidate_adequacy(
        policy=policy,
        pmm_statuses=(
            CheckStatus.FAIL,
            CheckStatus.NO_DATA,
        ),
        area_guard_statuses=(
            subject.AREA_GUARD_SATISFIED,
        ),
    )

    assert (
        pmm_fail.status
        == subject.CANDIDATE_INADEQUATE
    )

    area_fail = subject.aggregate_candidate_adequacy(
        policy=policy,
        pmm_statuses=(
            CheckStatus.NO_DATA,
        ),
        area_guard_statuses=(
            subject.AREA_GUARD_INSUFFICIENT,
        ),
    )

    assert (
        area_fail.status
        == subject.CANDIDATE_INADEQUATE
    )
