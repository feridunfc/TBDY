from __future__ import annotations

from tbdy_engine.regulatory.authority import (
    implementation_fingerprint,
    regulatory_claim_fingerprint,
    validate_registry_authority,
)
from tbdy_engine.regulatory import structural_system as ss
from tbdy_engine.regulatory.sources.tbdy2018 import (
    APPROVED_IMPLEMENTATION_FINGERPRINTS,
    CLAIMS_FOR_RULE,
    SOURCE_ID,
    build_vs4a_authority_catalog,
)


def test_every_vs4a_rule_has_current_strict_f0_9_authority():
    catalog = build_vs4a_authority_catalog()
    validated = validate_registry_authority(ss.VS4A_REGISTRY, catalog)
    assert len(validated) == ss.VS4A_REGISTRY.rule_count
    assert {item.rule_id for item in validated} == set(ss.ALL_VS4A_RULE_IDS)
    assert all(item.claim_refs and item.review_refs for item in validated)


def test_approved_implementation_fingerprints_match_exact_current_evaluators():
    for spec in (*ss.VS4A_REGISTRY.derivations, *ss.VS4A_REGISTRY.checks):
        actual = implementation_fingerprint(
            rule_id=spec.rule_id,
            rule_version=spec.rule_version,
            evaluator_binding_id=spec.evaluator.binding_id,
            implementation_modules=("tbdy_engine.regulatory.structural_system",),
        )
        assert APPROVED_IMPLEMENTATION_FINGERPRINTS[spec.rule_id.value] == actual


def test_every_approved_claim_review_matches_current_source_chain():
    catalog = build_vs4a_authority_catalog()
    for review in catalog.review_records:
        claim = catalog.claim(review.claim_id)
        actual = regulatory_claim_fingerprint(
            claim=claim,
            anchors=tuple(catalog.anchor(ref) for ref in claim.anchor_refs),
            source_documents=tuple(
                catalog.source(catalog.anchor(ref).source_id) for ref in claim.anchor_refs
            ),
        )
        assert review.reviewed_claim_fingerprint == actual


def test_table_4_1_rows_are_bound_as_distinct_claims_and_anchors():
    catalog = build_vs4a_authority_catalog()
    row_claim_ids = ss.TABLE_4_1_ROW_CLAIM_IDS
    assert len(row_claim_ids) == len(set(row_claim_ids)) == len(ss.TABLE_4_1_ROWS)
    for row, claim_id in zip(ss.TABLE_4_1_ROWS, row_claim_ids):
        claim = catalog.claim(claim_id)
        assert claim.anchor_refs == (f"TBDY2018_TABLE4_1_{row}",)
        anchor = catalog.anchor(claim.anchor_refs[0])
        assert anchor.source_id == SOURCE_ID
        assert anchor.locator == f"Table 4.1 / {row}"
    assert not any("ALL" in claim_id for claim_id in row_claim_ids)


def test_shared_eligibility_and_lifecycle_rules_have_explicit_claim_bindings():
    expected = {
        ss.RC_TABLE_4_1_BYS_ELIGIBILITY_STATE,
        ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY_STATE,
        ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY_STATE,
        ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY_STATE,
        ss.RC_PREANALYSIS_SYSTEM_ELIGIBILITY,
        ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY,
        ss.RC_ANALYSIS_BASIS_COMPATIBILITY,
    }
    for rule_id in expected:
        refs = CLAIMS_FOR_RULE[rule_id.value]
        assert refs
    assert CLAIMS_FOR_RULE[ss.RC_PREANALYSIS_SYSTEM_ELIGIBILITY.value] == (
        "TBDY2018_VS4A_PREANALYSIS_ELIGIBILITY_COMPOSITION",
    )
    assert "TBDY2018_VS4A_BASELINE_POLICY_LIFECYCLE" in CLAIMS_FOR_RULE[
        ss.RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY.value
    ]
    assert CLAIMS_FOR_RULE[ss.RC_ANALYSIS_BASIS_COMPATIBILITY.value] == (
        "TBDY2018_VS4A_ANALYSIS_BASIS_COMPATIBILITY",
    )
