"""FND-COL-4C1A reviewed candidate-adequacy source authority catalog."""
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
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    CANDIDATE_ADEQUACY_IMPLEMENTATION_MODULES,
    FND_COL_4_CANDIDATE_ADEQUACY_EVALUATOR_BINDING_ID,
    FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID,
    FND_COL_4_CANDIDATE_ADEQUACY_RULE_VERSION,
)
from tbdy_engine.regulatory.sources.fnd_col_4_pmm import (
    ANCHOR_DATA as PMM_ANCHOR_DATA,
    CLAIM_DATA as PMM_CLAIM_DATA,
    SOURCE_DATA,
    TBDY_SOURCE_ID,
    TS500_SOURCE_ID,
)


BASE_CLAIM_IDS = (
    "TBDY2018_COLUMN_PMM_TS500_DESIGN_BASIS",
    "TS500_COLUMN_PMM_DESIGN_ACTION_AND_STRENGTH",
    "TS500_COLUMN_PMM_AXIAL_BENDING_METHOD_SCOPE",
)

ANCHOR_DATA = {
    "TBDY2018_7_2_2": PMM_ANCHOR_DATA[
        "TBDY2018_7_2_2"
    ],
    "TBDY2018_7_2_4": PMM_ANCHOR_DATA[
        "TBDY2018_7_2_4"
    ],
    "TS500_7_2": PMM_ANCHOR_DATA["TS500_7_2"],
    "TS500_7_5": PMM_ANCHOR_DATA["TS500_7_5"],
    "TS500_6_2_3": (
        TS500_SOURCE_ID,
        "6.2.3",
    ),
}

CLAIM_DATA = {
    claim_id: PMM_CLAIM_DATA[claim_id]
    for claim_id in BASE_CLAIM_IDS
}

CLAIM_DATA[
    (
        "TS500_ULTIMATE_LIMIT_STATE_RESISTANCE_"
        "NOT_LESS_THAN_DESIGN_ACTION"
    )
] = (
    ("TS500_6_2_3",),
    "v1",
    (
        "At the ultimate limit state, design resistance Rd "
        "calculated using design material strengths must not "
        "be less than the internal-force effect Fd calculated "
        "from factored design loads; TS500 Eq. 6.1 states "
        "Rd >= Fd."
    ),
    (
        "sha256:"
        "67a8cb667bf75a46fd9f79f0f70753d1862a56c1"
        "afd7212655c49ac9f65e98c7"
    ),
)

CLAIMS_FOR_RULE = tuple(sorted(CLAIM_DATA))

IMPLEMENTATION_MODULES = (
    CANDIDATE_ADEQUACY_IMPLEMENTATION_MODULES
)

APPROVED_IMPLEMENTATION_FINGERPRINT = (
    "sha256:159daf252557fef8d7062f2f85dd68a93aeb92a6c03a940840c0f354ed785316"
)

REVIEW_BASIS_REF = (
    "FND_COL_4_SUPERVISOR_CANDIDATE_ADEQUACY_"
    "SOURCE_INTERPRETATION_2026_08_29"
)

BINDING_ID = (
    "FND_COL_4_BIND:COLUMN_CANDIDATE_PMM_ADEQUACY"
)


def build_fnd_col_4_candidate_adequacy_authority_catalog(
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
                "FND_COL_4_CANDIDATE_ADEQUACY_REVIEW:"
                f"{claim_id}:r1"
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
        rule_id=(
            FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID
        ),
        claim_refs=CLAIMS_FOR_RULE,
        review_refs=tuple(
            (
                "FND_COL_4_CANDIDATE_ADEQUACY_REVIEW:"
                f"{claim_id}:r1"
            )
            for claim_id in CLAIMS_FOR_RULE
        ),
        evaluator_binding_id=(
            FND_COL_4_CANDIDATE_ADEQUACY_EVALUATOR_BINDING_ID
        ),
        rule_version=(
            FND_COL_4_CANDIDATE_ADEQUACY_RULE_VERSION
        ),
        implementation_modules=IMPLEMENTATION_MODULES,
        approved_implementation_fingerprint=(
            APPROVED_IMPLEMENTATION_FINGERPRINT
        ),
        binding_version=(
            "fnd-col-4-candidate-adequacy-v1"
        ),
    )

    return RegulatoryAuthorityCatalog(
        source_documents=sources,
        anchors=anchors,
        claims=claims,
        review_records=reviews,
        implementation_bindings=(binding,),
    )


FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG = (
    build_fnd_col_4_candidate_adequacy_authority_catalog()
)


__all__ = [
    "ANCHOR_DATA",
    "APPROVED_IMPLEMENTATION_FINGERPRINT",
    "BASE_CLAIM_IDS",
    "BINDING_ID",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG",
    "IMPLEMENTATION_MODULES",
    "REVIEW_BASIS_REF",
    "SOURCE_DATA",
    "TBDY_SOURCE_ID",
    "TS500_SOURCE_ID",
    "build_fnd_col_4_candidate_adequacy_authority_catalog",
]
