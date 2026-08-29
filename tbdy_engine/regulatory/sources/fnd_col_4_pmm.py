"""FND-COL-4 reviewed F0.9 PMM source authority catalog."""
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
from tbdy_engine.regulatory.column_pmm_authority import (
    FND_COL_4_PMM_EVALUATOR_BINDING_ID,
    FND_COL_4_PMM_RULE_ID,
    FND_COL_4_PMM_RULE_VERSION,
    PMM_IMPLEMENTATION_MODULES,
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
    "TBDY2018_7_2_2": (
        TBDY_SOURCE_ID,
        "7.2.2",
    ),
    "TBDY2018_7_2_4": (
        TBDY_SOURCE_ID,
        "7.2.4",
    ),
    "TS500_7_1": (
        TS500_SOURCE_ID,
        "7.1",
    ),
    "TS500_7_2": (
        TS500_SOURCE_ID,
        "7.2",
    ),
    "TS500_7_5": (
        TS500_SOURCE_ID,
        "7.5",
    ),
    "TS500_TABLE_7_1": (
        TS500_SOURCE_ID,
        "Table 7.1",
    ),
}

CLAIM_DATA = {
    "TBDY2018_COLUMN_PMM_TS500_DESIGN_BASIS": (
        (
            "TBDY2018_7_2_2",
            "TBDY2018_7_2_4",
        ),
        "v1",
        (
            "Reinforced-concrete member section design follows "
            "TS 500 within the referenced concrete-strength domain; "
            "for concrete strengths above C50, the separate "
            "TS EN 1992-1 route applies."
        ),
        "sha256:9a02859ab6db6c385156d27e405dfb77b4bbe6f930002801ce35da13c5b60b74",
    ),
    "TS500_COLUMN_PMM_STRAIN_COMPATIBILITY": (
        ("TS500_7_1",),
        "v1",
        (
            "Section capacity is evaluated by strain compatibility "
            "with plane sections, concrete tension neglected, ultimate "
            "concrete compression strain 0.003, and reinforcing-steel "
            "stress limited by an elastic-perfectly-plastic law using "
            "Es = 200000 MPa and design steel strength fyd."
        ),
        "sha256:122851af0de0f4662fa7726db2237674433d49f7e4c2bc1289aecb8547584d61",
    ),
    "TS500_COLUMN_PMM_EQUIVALENT_RECTANGULAR_BLOCK": (
        (
            "TS500_7_1",
            "TS500_TABLE_7_1",
        ),
        "v1",
        (
            "Concrete compression is represented by an equivalent "
            "rectangular stress block with stress 0.85 fcd and block "
            "depth a = k1 c, using the Table 7.1 k1 values for "
            "concrete classes C16 through C50."
        ),
        "sha256:855d767452c513d146e5bfa671a103f3d98e6ce4d79d5ac96835c4740271ad6e",
    ),
    "TS500_COLUMN_PMM_DESIGN_ACTION_AND_STRENGTH": (
        ("TS500_7_2",),
        "v1",
        (
            "Section-capacity checks use unfavorable design action "
            "effects together with design material strengths fcd and "
            "fyd rather than characteristic strengths."
        ),
        "sha256:8200a01a5ff2fa0e73f8ccaac218fd49fff430127b50a0426a746b643f740376",
    ),
    "TS500_COLUMN_PMM_AXIAL_BENDING_METHOD_SCOPE": (
        ("TS500_7_5",),
        "v1",
        (
            "The column section-capacity method covers reinforced-"
            "concrete members subjected to combined axial force "
            "and bending."
        ),
        "sha256:e3266332847feb7b4ae8583684654ff2a19021b100d8d43f19b050ae719c3a52",
    ),
}

CLAIMS_FOR_RULE = tuple(sorted(CLAIM_DATA))
IMPLEMENTATION_MODULES = PMM_IMPLEMENTATION_MODULES

# Sealed below only after the exact implementation source exists.
APPROVED_IMPLEMENTATION_FINGERPRINT = (
    "sha256:5c7953f6b09eebc09fe880c62fa627bab1d96ced2258b881859aa7c48faeb4f6"
)

REVIEW_BASIS_REF = (
    "FND_COL_4_SUPERVISOR_SOURCE_INTERPRETATION_2026_08_29"
)

BINDING_ID = (
    "FND_COL_4_BIND:COLUMN_PMM_CAPACITY_AUTHORITY"
)


def build_fnd_col_4_pmm_authority_catalog(
) -> RegulatoryAuthorityCatalog:
    sources = tuple(
        RegulatorySourceDocument(
            source_id=source_id,
            title=title,
            edition=edition,
            issuer=issuer,
            jurisdiction=jurisdiction,
            source_fingerprint=fingerprint,
        )
        for source_id, (
            title,
            edition,
            issuer,
            jurisdiction,
            fingerprint,
        ) in sorted(SOURCE_DATA.items())
    )

    anchors = tuple(
        SourceAnchor(
            anchor_id=anchor_id,
            source_id=source_id,
            locator=locator,
        )
        for anchor_id, (
            source_id,
            locator,
        ) in sorted(ANCHOR_DATA.items())
    )

    claims = tuple(
        RegulatoryClaim(
            claim_id=claim_id,
            claim_version=version,
            anchor_refs=anchor_refs,
            normalized_statement=statement,
        )
        for claim_id, (
            anchor_refs,
            version,
            statement,
            _fingerprint,
        ) in sorted(CLAIM_DATA.items())
    )

    reviews = tuple(
        AuthorityReviewRecord(
            review_id=(
                f"FND_COL_4_PMM_REVIEW:{claim_id}:r1"
            ),
            claim_id=claim_id,
            status=AuthorityReviewStatus.APPROVED,
            review_version="r1",
            reviewed_claim_fingerprint=fingerprint,
            review_basis_refs=(REVIEW_BASIS_REF,),
        )
        for claim_id, (
            _anchors,
            _version,
            _statement,
            fingerprint,
        ) in sorted(CLAIM_DATA.items())
    )

    binding = ApprovedImplementationBinding(
        binding_id=BINDING_ID,
        rule_id=FND_COL_4_PMM_RULE_ID,
        claim_refs=CLAIMS_FOR_RULE,
        review_refs=tuple(
            f"FND_COL_4_PMM_REVIEW:{claim_id}:r1"
            for claim_id in CLAIMS_FOR_RULE
        ),
        evaluator_binding_id=(
            FND_COL_4_PMM_EVALUATOR_BINDING_ID
        ),
        rule_version=FND_COL_4_PMM_RULE_VERSION,
        implementation_modules=IMPLEMENTATION_MODULES,
        approved_implementation_fingerprint=(
            APPROVED_IMPLEMENTATION_FINGERPRINT
        ),
        binding_version="fnd-col-4-pmm-v1",
    )

    return RegulatoryAuthorityCatalog(
        source_documents=sources,
        anchors=anchors,
        claims=claims,
        review_records=reviews,
        implementation_bindings=(binding,),
    )


FND_COL_4_PMM_AUTHORITY_CATALOG = (
    build_fnd_col_4_pmm_authority_catalog()
)

__all__ = [
    "ANCHOR_DATA",
    "APPROVED_IMPLEMENTATION_FINGERPRINT",
    "BINDING_ID",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "FND_COL_4_PMM_AUTHORITY_CATALOG",
    "IMPLEMENTATION_MODULES",
    "REVIEW_BASIS_REF",
    "SOURCE_DATA",
    "TBDY_SOURCE_ID",
    "TS500_SOURCE_ID",
    "build_fnd_col_4_pmm_authority_catalog",
]
