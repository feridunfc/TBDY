"""FND-COL-1 reviewed F0.9 source authority catalog."""
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
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    FND_COL_1_EVALUATOR_BINDING_ID,
    FND_COL_1_RULE_ID,
    FND_COL_1_RULE_VERSION,
)

TBDY_SOURCE_ID = "TBDY2018_AFAD"
TS500_SOURCE_ID = "TS500_2000_TSE"
SOURCE_DATA = {
    TBDY_SOURCE_ID: (
        "Türkiye Bina Deprem Yönetmeliği 2018",
        "2018",
        "AFAD",
        "Türkiye",
        "sha256:8d3a9a463d4a534ec2c6834c557b5f706e2ad976c2d6837f6c9b6242e38a6bb2",
    ),
    TS500_SOURCE_ID: (
        "TS 500 Betonarme Yapıların Tasarım ve Yapım Kuralları",
        "Şubat 2000",
        "TSE",
        "Türkiye",
        "sha256:d925114d01a1de2baee63738bc0da0112b547b58526c3394843c36ee66722d44",
    ),
}
ANCHOR_DATA = {
    "TBDY2018_7_3_2_1": (TBDY_SOURCE_ID, "7.3.2.1"),
    "TBDY2018_7_3_2_2": (TBDY_SOURCE_ID, "7.3.2.2"),
    "TS500_9_5_2": (TS500_SOURCE_ID, "9.5.2"),
}
CLAIM_DATA = {
    "TBDY2018_COLUMN_LONGITUDINAL_RATIO_1_4": (
        ("TBDY2018_7_3_2_1",),
        "v1",
        "Column longitudinal reinforcement ratio is not less than 0.01 and not greater than 0.04 of the gross section area.",
        "sha256:1f3ccd2ab8a8a0613a78714c3fb3ad0fd72eee738569168c2f383ba094aedf96",
    ),
    "TBDY2018_COLUMN_MIN_LONGITUDINAL_BAR_DIAMETER_14_MM": (
        ("TBDY2018_7_3_2_1",),
        "v1",
        "Column longitudinal reinforcement bars are not smaller than 14 mm diameter.",
        "sha256:92cb0eea7b8051a5b0f870f799159daed03e05049d3a78a0b9ad45fdd678b564",
    ),
    "TBDY2018_CIRCULAR_COLUMN_MIN_LONGITUDINAL_BAR_COUNT_6": (
        ("TBDY2018_7_3_2_1",),
        "v1",
        "The minimum longitudinal bar count of six applies to circular columns.",
        "sha256:257c550fc6df4702672a4164960b132de2cd20aee4f8052e2b291fcb6d0d23aa",
    ),
    "TBDY2018_COLUMN_LAP_SPLICE_TOTAL_RHO_MAX_6": (
        ("TBDY2018_7_3_2_2",),
        "v1",
        "At sections containing lap splices, total column longitudinal reinforcement ratio does not exceed 0.06.",
        "sha256:0e0b8e637492c6515e652c14d8d5de5e0a4059257e44aa8f4c9415655c60736a",
    ),
    "TS500_COLUMN_LONGITUDINAL_CLEAR_SPACING": (
        ("TS500_9_5_2",),
        "v1",
        "For columns, clear distance between longitudinal bars is not less than max(1.5 times bar diameter, 4/3 maximum aggregate diameter, 40 mm).",
        "sha256:9edda524c5b79ed87ebf67589ce845c47981e65874dd1a8555a6a616bc1d8da5",
    ),
}
CLAIMS_FOR_RULE = tuple(sorted(CLAIM_DATA))
IMPLEMENTATION_MODULES = (
    "tbdy_engine.design.columns.rebar_layout",
    "tbdy_engine.regulatory.column_longitudinal_rebar",
)
APPROVED_IMPLEMENTATION_FINGERPRINT = "sha256:6bdd0d88546fb5e678c977326c09098893f59ca80cc2b5a1a09843300b2619f1"
REVIEW_BASIS_REF = "FND_COL_1_SUPERVISOR_SOURCE_INTERPRETATION_2026_08_27"
BINDING_ID = "FND_COL_1_BIND:COLUMN_LONGITUDINAL_LAYOUT_AUTHORITY"


def build_fnd_col_1_authority_catalog() -> RegulatoryAuthorityCatalog:
    sources = tuple(
        RegulatorySourceDocument(
            source_id=source_id,
            title=title,
            edition=edition,
            issuer=issuer,
            jurisdiction=jurisdiction,
            source_fingerprint=fingerprint,
        )
        for source_id, (title, edition, issuer, jurisdiction, fingerprint) in sorted(SOURCE_DATA.items())
    )
    anchors = tuple(
        SourceAnchor(anchor_id=anchor_id, source_id=source_id, locator=locator)
        for anchor_id, (source_id, locator) in sorted(ANCHOR_DATA.items())
    )
    claims = tuple(
        RegulatoryClaim(
            claim_id=claim_id,
            claim_version=version,
            anchor_refs=anchor_refs,
            normalized_statement=statement,
        )
        for claim_id, (anchor_refs, version, statement, _fingerprint) in sorted(CLAIM_DATA.items())
    )
    reviews = tuple(
        AuthorityReviewRecord(
            review_id=f"FND_COL_1_REVIEW:{claim_id}:r1",
            claim_id=claim_id,
            status=AuthorityReviewStatus.APPROVED,
            review_version="r1",
            reviewed_claim_fingerprint=fingerprint,
            review_basis_refs=(REVIEW_BASIS_REF,),
        )
        for claim_id, (_anchors, _version, _statement, fingerprint) in sorted(CLAIM_DATA.items())
    )
    binding = ApprovedImplementationBinding(
        binding_id=BINDING_ID,
        rule_id=FND_COL_1_RULE_ID,
        claim_refs=CLAIMS_FOR_RULE,
        review_refs=tuple(f"FND_COL_1_REVIEW:{claim_id}:r1" for claim_id in CLAIMS_FOR_RULE),
        evaluator_binding_id=FND_COL_1_EVALUATOR_BINDING_ID,
        rule_version=FND_COL_1_RULE_VERSION,
        implementation_modules=IMPLEMENTATION_MODULES,
        approved_implementation_fingerprint=APPROVED_IMPLEMENTATION_FINGERPRINT,
        binding_version="fnd-col-1-v1",
    )
    return RegulatoryAuthorityCatalog(
        source_documents=sources,
        anchors=anchors,
        claims=claims,
        review_records=reviews,
        implementation_bindings=(binding,),
    )


FND_COL_1_AUTHORITY_CATALOG = build_fnd_col_1_authority_catalog()

__all__ = [
    "TBDY_SOURCE_ID",
    "TS500_SOURCE_ID",
    "SOURCE_DATA",
    "ANCHOR_DATA",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "IMPLEMENTATION_MODULES",
    "APPROVED_IMPLEMENTATION_FINGERPRINT",
    "REVIEW_BASIS_REF",
    "BINDING_ID",
    "FND_COL_1_AUTHORITY_CATALOG",
    "build_fnd_col_1_authority_catalog",
]
