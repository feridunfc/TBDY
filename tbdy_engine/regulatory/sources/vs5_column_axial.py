"""Source-bound authority catalog for VS5 RC column axial dual-code checks.

No regulation text is stored here. The catalog binds reviewed normalized claims
to exact TBDY 2018, TS 500 and TS 498 source identities and to the implementation
bytes that execute the bounded VS5 rules.
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
from tbdy_engine.regulatory.column_axial_dual_code import VS5_COLUMN_AXIAL_REGISTRY

TBDY_SOURCE_ID = "TBDY2018_AFAD"
TS500_SOURCE_ID = "TS500_2000_TSE"
TS498_SOURCE_ID = "TS498_1997_TSE"

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
    TS498_SOURCE_ID: (
        "TS 498 Yapı Elemanlarının Boyutlandırılmasında Alınacak Yüklerin Hesap Değerleri",
        "Kasım 1997",
        "TSE",
        "Türkiye",
        "sha256:853e864c8c0a9691bd39a7fb49dff31463d89b1881f836fd03290146ed727f9d",
    ),
}

ANCHOR_DATA = {
    "TBDY2018_7_3_1_2": (TBDY_SOURCE_ID, "7.3.1.2"),
    "TBDY2018_4_4_4_1": (TBDY_SOURCE_ID, "4.4.4.1 / Eq. (4.11)"),
    "TS498_13": (TS498_SOURCE_ID, "13 / Table 8"),
    "TS500_6_2_5": (TS500_SOURCE_ID, "6.2.5"),
    "TS500_6_2_6": (TS500_SOURCE_ID, "6.2.6"),
    "TS500_7_4_1": (TS500_SOURCE_ID, "7.4.1 / Eq. (7.7)"),
}

CLAIM_DATA = {
    "TBDY2018_7_3_1_2_COLUMN_AXIAL": (
        ("TBDY2018_4_4_4_1", "TBDY2018_7_3_1_2", "TS498_13"),
        "v1",
        "For reinforced-concrete columns in the bounded VS5 slice, Ndm is the greatest axial compression from the reviewed common G, Q and earthquake-effect population with TS 498 live-load reduction explicitly reviewed and the Eq. (4.11) snow coefficient equal to 0.2; the gross concrete section shall satisfy Ndm <= 0.40 Ac fck.",
        "sha256:936bc4a4da59866e560cb6fd83d166fd4fa6f5eca9fb12a169a203d363199a48",
    ),
    "TS500_7_4_1_COLUMN_AXIAL": (
        ("TS500_6_2_5", "TS500_6_2_6", "TS500_7_4_1"),
        "v1",
        "For reinforced-concrete columns, all applicable design load combinations are considered for Nd, concrete design compressive strength is fcd=fck/gamma_mc with the reviewed material factor, and every column shall satisfy Nd <= 0.90 fcd Ac.",
        "sha256:9672426b38cf3687065eea50c5ca4fbd97aadbe55d5f20abfd56659f91c209b0",
    ),
}

CLAIMS_FOR_RULE = {
    "TBDY_7_3_1_2_COLUMN_AXIAL": ("TBDY2018_7_3_1_2_COLUMN_AXIAL",),
    "TS500_7_4_1_COLUMN_AXIAL": ("TS500_7_4_1_COLUMN_AXIAL",),
}

IMPLEMENTATION_MODULES = (
    "tbdy_engine.checks.column_axial_selection",
    "tbdy_engine.regulatory.column_axial_dual_code",
)

APPROVED_IMPLEMENTATION_FINGERPRINTS = {
    "TBDY_7_3_1_2_COLUMN_AXIAL": "sha256:6847965478f7ed4e58a09d93b64d3cdbe2ea5bda868c1c447f3fdd307039fcfa",
    "TS500_7_4_1_COLUMN_AXIAL": "sha256:c8aaa8ac874576bc8513a133e3dad56f104a23a78882c5a807f3c60405818106",
}


def build_vs5_column_axial_authority_catalog() -> RegulatoryAuthorityCatalog:
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
            review_id=f"VS5_COLUMN_AXIAL_REVIEW:{claim_id}:r1",
            claim_id=claim_id,
            status=AuthorityReviewStatus.APPROVED,
            review_version="r1",
            reviewed_claim_fingerprint=fingerprint,
            review_basis_refs=("VS5_COLUMN_AXIAL_SUPERVISOR_REVIEWED_SOURCE_PACKAGE_2026_08_24",),
        )
        for claim_id, (_anchors, _version, _statement, fingerprint) in sorted(CLAIM_DATA.items())
    )
    bindings = []
    for spec in VS5_COLUMN_AXIAL_REGISTRY.checks:
        rule_name = spec.rule_id.value
        claim_refs = CLAIMS_FOR_RULE[rule_name]
        bindings.append(
            ApprovedImplementationBinding(
                binding_id=f"VS5_COLUMN_AXIAL_BIND:{rule_name}",
                rule_id=spec.rule_id,
                claim_refs=claim_refs,
                review_refs=tuple(
                    f"VS5_COLUMN_AXIAL_REVIEW:{claim_id}:r1" for claim_id in claim_refs
                ),
                evaluator_binding_id=spec.evaluator.binding_id,
                rule_version=spec.rule_version,
                implementation_modules=IMPLEMENTATION_MODULES,
                approved_implementation_fingerprint=APPROVED_IMPLEMENTATION_FINGERPRINTS[rule_name],
                binding_version="vs5-column-axial-v1",
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
    "TS498_SOURCE_ID",
    "SOURCE_DATA",
    "ANCHOR_DATA",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "IMPLEMENTATION_MODULES",
    "APPROVED_IMPLEMENTATION_FINGERPRINTS",
    "build_vs5_column_axial_authority_catalog",
]
