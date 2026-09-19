"""F0.9 reviewed source-authority catalog for TBDY §7.7.5 limited column shear."""
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
from tbdy_engine.regulatory.column_shear_limited import (
    COLUMN_SHEAR_LIMITED_775_REGISTRY,
)

TBDY_SOURCE_ID = "TBDY2018_AFAD"

SOURCE_DATA = {
    TBDY_SOURCE_ID: (
        "Türkiye Bina Deprem Yönetmeliği 2018",
        "2018",
        "AFAD",
        "Türkiye",
        "sha256:8d3a9a463d4a534ec2c6834c557b5f706e2ad976c2d6837f6c9b6242e38a6bb2",
    ),
}

ANCHOR_DATA = {
    "TBDY2018_7_7_5_1": (
        TBDY_SOURCE_ID,
        "7.7.5.1",
    ),
    "TBDY2018_7_7_5_2_EQ7_7": (
        TBDY_SOURCE_ID,
        "7.7.5.2 / Eq. (7.7)",
    ),
}

CLAIM_DATA = {
    "TBDY2018_7_7_5_LIMITED_COLUMN_SHEAR_DEMAND_AND_BRITTLE_BOUND": (
        (
            "TBDY2018_7_7_5_1",
            "TBDY2018_7_7_5_2_EQ7_7",
        ),
        "v1",
        "For limited-ductility reinforced-concrete columns, the transverse-reinforcement design shear Vd is the exact reviewed effect of vertical loads acting together with earthquake effects amplified by the overstrength factor D, and the Eq.(7.7) brittle upper bound is applied using that D-amplified Vd in place of high-ductility Ve.",
        "sha256:6ca33931759294c45623dfa18811c8ad48d8bf643dc2f838352dd4f951f27ef3",
    ),
}

CLAIMS_FOR_RULE = {
    "TBDY_7_7_5_2_COLUMN_SHEAR_BRITTLE_BOUND": (
        "TBDY2018_7_7_5_LIMITED_COLUMN_SHEAR_DEMAND_AND_BRITTLE_BOUND",
    ),
}

IMPLEMENTATION_MODULES = (
    "tbdy_engine.regulatory.column_shear_limited",
)

APPROVED_IMPLEMENTATION_FINGERPRINTS = {
    "TBDY_7_7_5_2_COLUMN_SHEAR_BRITTLE_BOUND":
        "sha256:a6f5d19ff508da43de943b30af047e7e5e8043aad581333f47cb39473d3ddd30",
}


def build_column_shear_limited_775_authority_catalog(
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
        )
        in sorted(SOURCE_DATA.items())
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
        )
        in sorted(ANCHOR_DATA.items())
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
        )
        in sorted(CLAIM_DATA.items())
    )
    reviews = tuple(
        AuthorityReviewRecord(
            review_id=(
                "COLUMN_R1_A37_LIMITED_SHEAR_REVIEW:"
                f"{claim_id}:r1"
            ),
            claim_id=claim_id,
            status=AuthorityReviewStatus.APPROVED,
            review_version="r1",
            reviewed_claim_fingerprint=fingerprint,
            review_basis_refs=(
                "COLUMN_R1_A37_LIMITED_SHEAR_SUPERVISOR_"
                "REVIEWED_SOURCE_PACKAGE_2026_09_18",
            ),
        )
        for claim_id, (
            _anchors,
            _version,
            _statement,
            fingerprint,
        )
        in sorted(CLAIM_DATA.items())
    )

    bindings = []
    for spec in (
        *COLUMN_SHEAR_LIMITED_775_REGISTRY.derivations,
        *COLUMN_SHEAR_LIMITED_775_REGISTRY.checks,
    ):
        rule_name = spec.rule_id.value
        claim_refs = CLAIMS_FOR_RULE[rule_name]
        bindings.append(
            ApprovedImplementationBinding(
                binding_id=(
                    "COLUMN_R1_A37_LIMITED_SHEAR_BIND:"
                    f"{rule_name}"
                ),
                rule_id=spec.rule_id,
                claim_refs=claim_refs,
                review_refs=tuple(
                    (
                        "COLUMN_R1_A37_LIMITED_SHEAR_REVIEW:"
                        f"{claim_id}:r1"
                    )
                    for claim_id in claim_refs
                ),
                evaluator_binding_id=(
                    spec.evaluator.binding_id
                ),
                rule_version=spec.rule_version,
                implementation_modules=(
                    IMPLEMENTATION_MODULES
                ),
                approved_implementation_fingerprint=(
                    APPROVED_IMPLEMENTATION_FINGERPRINTS[
                        rule_name
                    ]
                ),
                binding_version=(
                    "column-r1-a37-limited-shear-v1"
                ),
            )
        )

    return RegulatoryAuthorityCatalog(
        source_documents=sources,
        anchors=anchors,
        claims=claims,
        review_records=reviews,
        implementation_bindings=tuple(bindings),
    )


__all__ = [
    "ANCHOR_DATA",
    "APPROVED_IMPLEMENTATION_FINGERPRINTS",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "IMPLEMENTATION_MODULES",
    "SOURCE_DATA",
    "TBDY_SOURCE_ID",
    "build_column_shear_limited_775_authority_catalog",
]
