"""Reviewed F0.9 source-authority package for FND-COL-2.

This module contains immutable review metadata only.  It stores no copyrighted
standard text and executes no engineering formulas.  The actual FND-COL-2 rule
runs through the existing F0 RegulatoryCompiler / RegulatoryEngine.

The source fingerprint identifies the reviewed TS 500:2000 PDF including the
T1:2001 and T2:2002 amendment pages supplied for this implementation review.
Claim-review fingerprints and the implementation fingerprint are deliberately
hard-coded approval snapshots: a later source, claim, or reviewed implementation
change must fail closed until explicitly re-reviewed.
"""
from __future__ import annotations

from tbdy_engine.regulatory.authority import (
    ApprovedImplementationBinding,
    AuthorityReviewRecord,
    AuthorityReviewStatus,
    RegulatoryAuthorityCatalog,
    RegulatoryClaim,
    RegulatorySourceDocument,
    SourceAnchor,
)
from tbdy_engine.regulatory.fnd_col_2 import RULE_ID, RULE_VERSION, SPEC

SOURCE_ID = "TS500_2000_T1_T2"
SOURCE_FINGERPRINT = "sha256:d925114d01a1de2baee63738bc0da0112b547b58526c3394843c36ee66722d44"

SOURCE_DOCUMENT = RegulatorySourceDocument(
    source_id=SOURCE_ID,
    title="Betonarme Yapıların Tasarım ve Yapım Kuralları",
    edition="TS 500:2000 + T1:2001 + T2:2002",
    issuer="Türk Standardları Enstitüsü",
    jurisdiction="TR",
    source_fingerprint=SOURCE_FINGERPRINT,
)

ANCHOR_MIN_ECC = SourceAnchor("A_MIN_ECC", SOURCE_ID, "6.3.10 Eq.6.16")
ANCHOR_GENERAL_SECOND_ORDER = SourceAnchor(
    "A_GENERAL_SECOND_ORDER", SOURCE_ID, "7.6.1"
)
ANCHOR_SWAY_STABILITY = SourceAnchor(
    "A_SWAY_STABILITY", SOURCE_ID, "7.6.2.1 Eq.7.13"
)
ANCHOR_EFFECTIVE_LENGTH = SourceAnchor(
    "A_EFFECTIVE_LENGTH", SOURCE_ID, "7.6.2.2 Eq.7.14-7.16"
)
ANCHOR_SLENDERNESS_NEGLECT = SourceAnchor(
    "A_SLENDERNESS_NEGLECT", SOURCE_ID, "7.6.2.3 Eq.7.17-7.18"
)
ANCHOR_MAGNIFICATION = SourceAnchor(
    "A_MAGNIFICATION", SOURCE_ID, "7.6.2.4-7.6.2.6 Eq.7.19-7.29"
)

ANCHORS = (
    ANCHOR_MIN_ECC,
    ANCHOR_GENERAL_SECOND_ORDER,
    ANCHOR_SWAY_STABILITY,
    ANCHOR_EFFECTIVE_LENGTH,
    ANCHOR_SLENDERNESS_NEGLECT,
    ANCHOR_MAGNIFICATION,
)

CLAIM_MIN_ECC = RegulatoryClaim(
    claim_id="FND_COL_2_MIN_ECC",
    claim_version="1",
    anchor_refs=(ANCHOR_MIN_ECC.anchor_id,),
    normalized_statement=(
        "For a column end design moment obtained from structural analysis, the design eccentricity "
        "shall not be less than emin = 15 mm + 0.03 h, where h is the section dimension in the "
        "bending plane."
    ),
)
CLAIM_GENERAL_SECOND_ORDER = RegulatoryClaim(
    claim_id="FND_COL_2_GENERAL_SECOND_ORDER",
    claim_version="1",
    anchor_refs=(ANCHOR_GENERAL_SECOND_ORDER.anchor_id,),
    normalized_statement=(
        "Reinforced-concrete members under axial compression and bending are generally designed "
        "from second-order structural analysis; the TS500 approximate method may be used only when "
        "lk/i does not exceed 100 and its stated applicability conditions are met."
    ),
)
CLAIM_SWAY_STABILITY = RegulatoryClaim(
    claim_id="FND_COL_2_SWAY_STABILITY",
    claim_version="1",
    anchor_refs=(ANCHOR_SWAY_STABILITY.anchor_id,),
    normalized_statement=(
        "When the second-order comparison route is not used, TS500 Eq.7.13 may prove a storey "
        "sway-prevented only with phi <= 0.05 using the uncracked-section assumption and the "
        "unfavorable of Fd=1.0G+1.0Q+1.0E and Fd=1.0G+1.3Q+1.3W."
    ),
)
CLAIM_EFFECTIVE_LENGTH = RegulatoryClaim(
    claim_id="FND_COL_2_EFFECTIVE_LENGTH",
    claim_version="1",
    anchor_refs=(ANCHOR_EFFECTIVE_LENGTH.anchor_id,),
    normalized_statement=(
        "Column free length is measured between members providing lateral support; effective length "
        "is lk=k ln, with separate k rules for sway-prevented and sway-permitted columns and k=1.0 "
        "permitted for sway-prevented columns when k is not otherwise calculated."
    ),
)
CLAIM_SLENDERNESS_NEGLECT = RegulatoryClaim(
    claim_id="FND_COL_2_SLENDERNESS_NEGLECT",
    claim_version="1",
    anchor_refs=(ANCHOR_SLENDERNESS_NEGLECT.anchor_id,),
    normalized_statement=(
        "For rectangular columns i may be taken as 0.30h; slenderness effects may be neglected only "
        "within Eq.7.17 for sway-prevented columns or Eq.7.18 for sway-permitted columns, with the "
        "signed per-combination M1/M2 convention required by TS500."
    ),
)
CLAIM_MAGNIFICATION = RegulatoryClaim(
    claim_id="FND_COL_2_MAGNIFICATION",
    claim_version="1",
    anchor_refs=(ANCHOR_MAGNIFICATION.anchor_id,),
    normalized_statement=(
        "When slenderness effects cannot be neglected within the approximate method, TS500 requires "
        "the applicable Eq.7.19-7.29 moment-magnification treatment; biaxial moments are magnified "
        "separately, while conditions outside the approximate-method boundary require the general "
        "second-order route."
    ),
)

CLAIMS = (
    CLAIM_MIN_ECC,
    CLAIM_GENERAL_SECOND_ORDER,
    CLAIM_SWAY_STABILITY,
    CLAIM_EFFECTIVE_LENGTH,
    CLAIM_SLENDERNESS_NEGLECT,
    CLAIM_MAGNIFICATION,
)

REVIEWED_CLAIM_FINGERPRINTS = {
    CLAIM_MIN_ECC.claim_id: "sha256:defb574d8d6d94f24262b8deda427f42e8673544d219b2a734211d7aa680255e",
    CLAIM_GENERAL_SECOND_ORDER.claim_id: "sha256:642b66f3e113baa0d0f73da13966e84db67d195b333d1213f95e28aa20721376",
    CLAIM_SWAY_STABILITY.claim_id: "sha256:a7e6352699700edd2e6d1189e5ad77bf0d5502df771184eefd71eec95d8cd944",
    CLAIM_EFFECTIVE_LENGTH.claim_id: "sha256:f57cd0e302885ee8873483fa23a96ac901ad2a9cb66dd27af5a035e9205b945b",
    CLAIM_SLENDERNESS_NEGLECT.claim_id: "sha256:e74707b7130a73345e4a679aff67b432ecda65cce8086a409a4390c542979798",
    CLAIM_MAGNIFICATION.claim_id: "sha256:bc741660b89731c70ed7b112e5f01aa145d94916cb89a48742bf16d5a847b8ce",
}


def _review(claim: RegulatoryClaim) -> AuthorityReviewRecord:
    return AuthorityReviewRecord(
        review_id=f"REVIEW:{claim.claim_id}",
        claim_id=claim.claim_id,
        status=AuthorityReviewStatus.APPROVED,
        review_version="1",
        reviewed_claim_fingerprint=REVIEWED_CLAIM_FINGERPRINTS[claim.claim_id],
        review_basis_refs=(
            "FND-COL-2:TS500(4).pdf:source-review",
            "FND-COL-2:TS500-T1-T2-amendment-review",
        ),
    )


REVIEWS = tuple(_review(claim) for claim in CLAIMS)

APPROVED_IMPLEMENTATION_MODULES = (
    "tbdy_engine.regulatory.fnd_col_2",
    "tbdy_engine.design.columns.column_design_readiness",
    "tbdy_engine.design.columns.column_design_demand_engine",
    "tbdy_engine.design.columns.combo_pattern_engine",
    "tbdy_engine.design.columns.design_demand_states",
    "tbdy_engine.design.columns.minimum_eccentricity",
    "tbdy_engine.design.columns.slenderness_basis",
    "tbdy_engine.design.columns.slenderness",
    "tbdy_engine.design.columns.stability_stiffness_basis",
)
APPROVED_IMPLEMENTATION_FINGERPRINT = (
    "sha256:66a343d4bd0b726f6bc4048ab83a0cc3a48eb7fc033e269b19cecfd1470574ff"
)
BINDING_ID = "FND_COL_2_TS500_BINDING"

IMPLEMENTATION_BINDING = ApprovedImplementationBinding(
    binding_id=BINDING_ID,
    rule_id=RULE_ID,
    claim_refs=tuple(claim.claim_id for claim in CLAIMS),
    review_refs=tuple(review.review_id for review in REVIEWS),
    evaluator_binding_id=SPEC.evaluator.binding_id,
    rule_version=RULE_VERSION,
    implementation_modules=APPROVED_IMPLEMENTATION_MODULES,
    approved_implementation_fingerprint=APPROVED_IMPLEMENTATION_FINGERPRINT,
    binding_version="1",
)

FND_COL_2_AUTHORITY_CATALOG = RegulatoryAuthorityCatalog(
    source_documents=(SOURCE_DOCUMENT,),
    anchors=ANCHORS,
    claims=CLAIMS,
    review_records=REVIEWS,
    implementation_bindings=(IMPLEMENTATION_BINDING,),
)

__all__ = [
    "ANCHORS",
    "APPROVED_IMPLEMENTATION_FINGERPRINT",
    "APPROVED_IMPLEMENTATION_MODULES",
    "BINDING_ID",
    "CLAIMS",
    "FND_COL_2_AUTHORITY_CATALOG",
    "IMPLEMENTATION_BINDING",
    "REVIEWS",
    "REVIEWED_CLAIM_FINGERPRINTS",
    "SOURCE_DOCUMENT",
    "SOURCE_FINGERPRINT",
    "SOURCE_ID",
]
