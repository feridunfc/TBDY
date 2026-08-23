from __future__ import annotations

from tbdy_engine.regulatory.authority import (
    implementation_fingerprint,
    regulatory_claim_fingerprint,
    validate_registry_authority,
)
from tbdy_engine.regulatory.rc_a15_wall_share import VS4B_A15_REGISTRY
from tbdy_engine.regulatory.sources.tbdy2018_vs4b import (
    APPROVED_IMPLEMENTATION_FINGERPRINTS,
    CLAIMS_FOR_RULE,
    IMPLEMENTATION_MODULE,
    build_vs4b_a15_authority_catalog,
)


def test_every_vs4b_a15_rule_has_current_strict_f0_9_authority():
    catalog = build_vs4b_a15_authority_catalog()
    validated = validate_registry_authority(VS4B_A15_REGISTRY, catalog)
    assert len(validated) == VS4B_A15_REGISTRY.rule_count == 2
    assert all(item.claim_refs and item.review_refs for item in validated)


def test_implementation_fingerprint_boundary_is_only_final_regulatory_module():
    catalog = build_vs4b_a15_authority_catalog()
    for spec in VS4B_A15_REGISTRY.derivations:
        binding = catalog.bindings_for_rule(spec.rule_id)[0]
        assert binding.implementation_modules == (IMPLEMENTATION_MODULE,)
        assert IMPLEMENTATION_MODULE == "tbdy_engine.regulatory.rc_a15_wall_share"
        actual = implementation_fingerprint(
            rule_id=spec.rule_id,
            rule_version=spec.rule_version,
            evaluator_binding_id=spec.evaluator.binding_id,
            implementation_modules=binding.implementation_modules,
        )
        assert actual == APPROVED_IMPLEMENTATION_FINGERPRINTS[spec.rule_id.value]
        assert actual == binding.approved_implementation_fingerprint


def test_every_approved_claim_review_matches_current_atomic_source_chain():
    catalog = build_vs4b_a15_authority_catalog()
    for review in catalog.review_records:
        claim = catalog.claim(review.claim_id)
        anchors = tuple(catalog.anchor(ref) for ref in claim.anchor_refs)
        sources_by_id = {catalog.source(anchor.source_id).source_id: catalog.source(anchor.source_id) for anchor in anchors}
        actual = regulatory_claim_fingerprint(
            claim=claim,
            anchors=anchors,
            source_documents=tuple(sources_by_id[key] for key in sorted(sources_by_id)),
        )
        assert review.reviewed_claim_fingerprint == actual


def test_modal_mo_claim_is_explicitly_modal_and_has_no_equivalent_static_anchor():
    catalog = build_vs4b_a15_authority_catalog()
    claim = catalog.claim("TBDY2018_4_3_4_8_TOTAL_MO_MODAL")
    assert claim.anchor_refs == (
        "TBDY2018_4B_2_5",
        "TBDY2018_4_3_4_8",
        "TBDY2018_4_8_2_1",
    )
    locators = {catalog.anchor(ref).locator for ref in claim.anchor_refs}
    assert locators == {"4B.2.5", "4.3.4.8", "4.8.2.1"}
    assert not any(locator.startswith("4.7") for locator in locators)
    assert "modal-combination" in claim.normalized_statement


def test_effective_policy_binds_exact_a15_branch_mdev_and_modal_mo_claims():
    refs = CLAIMS_FOR_RULE["RC_A15_4345_EFFECTIVE_POLICY"]
    assert refs == (
        "TBDY2018_4_3_4_5_A15_BRANCHES",
        "TBDY2018_4_3_4_8_SOLID_WALL_MDEV",
        "TBDY2018_4_3_4_8_TOTAL_MO_MODAL",
        "TBDY2018_VS4B_A15_EFFECTIVE_POLICY_LIFECYCLE",
    )
