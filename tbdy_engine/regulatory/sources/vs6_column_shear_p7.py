"""F0.9 reviewed source-authority catalog for VS6-P7 column shear."""
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
from tbdy_engine.regulatory.column_shear_p7 import VS6_COLUMN_SHEAR_P7_REGISTRY

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
    "TBDY2018_7_3_7_1_EQ7_5": (TBDY_SOURCE_ID, "7.3.7.1 / Eq. (7.5)"),
    "TBDY2018_7_3_7_3": (TBDY_SOURCE_ID, "7.3.7.3"),
    "TBDY2018_7_3_7_4": (TBDY_SOURCE_ID, "7.3.7.4"),
    "TBDY2018_7_3_7_5_EQ7_7": (TBDY_SOURCE_ID, "7.3.7.5 / Eq. (7.7)"),
    "TS500_8_1_5_B_EQ8_7": (TS500_SOURCE_ID, "8.1.5(b) / Eq. (8.7)"),
}

CLAIM_DATA = {
    "TBDY2018_7_3_7_COLUMN_SHEAR_VE": (
        (
            "TBDY2018_7_3_7_1_EQ7_5",
            "TBDY2018_7_3_7_3",
            "TBDY2018_7_3_7_4",
            "TBDY2018_7_3_7_5_EQ7_7",
        ),
        "v1",
        "For high-ductility reinforced-concrete columns in the bounded VS6-P7 slice, column design shear is derived from the end plastic moment capacities as Ve=(Ma+Mü)/ln, the reviewed safe-side 7.3.7.3 relation may govern when smaller, and the final Ve shall not be less than the analysis shear Vd; exact end capacities and the reviewed D-amplified demand basis are required rather than inferred defaults.",
        "sha256:4e0b9ec6edc76ef865015bbef01f4bcfd78c1b342c3f1e3f93f3f6b0eb8793dd",
    ),
    "TBDY2018_7_3_7_5_COLUMN_SHEAR_BRITTLE_BOUND": (
        ("TBDY2018_7_3_7_5_EQ7_7",),
        "v1",
        "For high-ductility reinforced-concrete columns, the bounded brittle upper condition is Ve <= 0.85 Aw sqrt(fck); in the strict plain-rectangular VS6-P7 geometry Aw is the effective column web area with no perpendicular projections to exclude, and violation requires section enlargement followed by earthquake reanalysis.",
        "sha256:fbf3301c5c8dd9c557fe517df9c5040ea6750ecee953e1125e48d547404e2300",
    ),
    "TS500_8_1_5_B_COLUMN_SHEAR_WEB_COMPRESSION": (
        ("TS500_8_1_5_B_EQ8_7",),
        "v1",
        "For reinforced-concrete column shear in the bounded VS6-P7 slice, the TS 500 web-compression upper condition is Vd <= 0.22 fcd bw d, with bw and d resolved from the reviewed local-axis section geometry and selected longitudinal-bar coordinates.",
        "sha256:ea532be93c57ca8094d312d1f1c6204dc5cf7aaef734f7209ed5e01b446391b5",
    ),
}

CLAIMS_FOR_RULE = {
    "TBDY_7_3_7_COLUMN_SHEAR_VE": ("TBDY2018_7_3_7_COLUMN_SHEAR_VE",),
    "TBDY_7_3_7_5_COLUMN_SHEAR_BRITTLE_BOUND": (
        "TBDY2018_7_3_7_5_COLUMN_SHEAR_BRITTLE_BOUND",
    ),
    "TS500_8_1_5_B_COLUMN_SHEAR_WEB_COMPRESSION": (
        "TS500_8_1_5_B_COLUMN_SHEAR_WEB_COMPRESSION",
    ),
}

IMPLEMENTATION_MODULES = ("tbdy_engine.regulatory.column_shear_p7",)

APPROVED_IMPLEMENTATION_FINGERPRINTS = {
    "TBDY_7_3_7_COLUMN_SHEAR_VE": "sha256:7303a1863a9923e7b588e8d7edbc6ebe2217ecfcc454e0db07d1db4aa17d5b3b",
    "TBDY_7_3_7_5_COLUMN_SHEAR_BRITTLE_BOUND": "sha256:e21ae4dc3aa88095e6fc27bf3efff3de14d6e49f99a1033782ad8b5b6d110b38",
    "TS500_8_1_5_B_COLUMN_SHEAR_WEB_COMPRESSION": "sha256:59ecf3720ea9ac8acc6e59acd050268220508505ab6d6c61218f5900dd227dcc",
}


def build_vs6_column_shear_p7_authority_catalog() -> RegulatoryAuthorityCatalog:
    sources = tuple(
        RegulatorySourceDocument(
            source_id=source_id,
            title=title,
            edition=edition,
            issuer=issuer,
            jurisdiction=jurisdiction,
            source_fingerprint=fingerprint,
        )
        for source_id, (title, edition, issuer, jurisdiction, fingerprint)
        in sorted(SOURCE_DATA.items())
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
        for claim_id, (anchor_refs, version, statement, _fingerprint)
        in sorted(CLAIM_DATA.items())
    )
    reviews = tuple(
        AuthorityReviewRecord(
            review_id=f"VS6_P7_COLUMN_SHEAR_REVIEW:{claim_id}:r1",
            claim_id=claim_id,
            status=AuthorityReviewStatus.APPROVED,
            review_version="r1",
            reviewed_claim_fingerprint=fingerprint,
            review_basis_refs=(
                "VS6_P7_COLUMN_SHEAR_SUPERVISOR_REVIEWED_SOURCE_PACKAGE_2026_08_26",
            ),
        )
        for claim_id, (_anchors, _version, _statement, fingerprint)
        in sorted(CLAIM_DATA.items())
    )

    bindings = []
    for spec in (*VS6_COLUMN_SHEAR_P7_REGISTRY.derivations, *VS6_COLUMN_SHEAR_P7_REGISTRY.checks):
        rule_name = spec.rule_id.value
        claim_refs = CLAIMS_FOR_RULE[rule_name]
        bindings.append(
            ApprovedImplementationBinding(
                binding_id=f"VS6_P7_COLUMN_SHEAR_BIND:{rule_name}",
                rule_id=spec.rule_id,
                claim_refs=claim_refs,
                review_refs=tuple(
                    f"VS6_P7_COLUMN_SHEAR_REVIEW:{claim_id}:r1"
                    for claim_id in claim_refs
                ),
                evaluator_binding_id=spec.evaluator.binding_id,
                rule_version=spec.rule_version,
                implementation_modules=IMPLEMENTATION_MODULES,
                approved_implementation_fingerprint=APPROVED_IMPLEMENTATION_FINGERPRINTS[rule_name],
                binding_version="vs6-p7-column-shear-v1",
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
    "TBDY_SOURCE_ID",
    "TS500_SOURCE_ID",
    "SOURCE_DATA",
    "ANCHOR_DATA",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "IMPLEMENTATION_MODULES",
    "APPROVED_IMPLEMENTATION_FINGERPRINTS",
    "build_vs6_column_shear_p7_authority_catalog",
]
