"""Reviewed TBDY 2018 source authority for bounded VS-4B-A A15 qualification.

No regulation text is stored here.  Claims are normalized reviewed statements
bound to exact atomic source anchors.  The 4.8.2/4B.2.5 Mo claim is explicitly
modal and must never authorize an unreviewed LinStatic result population; that
population-identity gate is enforced before the F0 regulatory program compiles.
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
from tbdy_engine.regulatory.rc_a15_wall_share import VS4B_A15_REGISTRY

SOURCE_ID = "TBDY2018_AFAD"
SOURCE_SHA256 = "8d3a9a463d4a534ec2c6834c557b5f706e2ad976c2d6837f6c9b6242e38a6bb2"
IMPLEMENTATION_MODULE = "tbdy_engine.regulatory.rc_a15_wall_share"

ANCHOR_DATA = {
    "TBDY2018_4B_2_5": (SOURCE_ID, "4B.2.5"),
    "TBDY2018_4_3_4_5": (SOURCE_ID, "4.3.4.5"),
    "TBDY2018_4_3_4_8": (SOURCE_ID, "4.3.4.8"),
    "TBDY2018_4_5_3_7_D": (SOURCE_ID, "4.5.3.7(d)"),
    "TBDY2018_4_5_3_8_C": (SOURCE_ID, "4.5.3.8(c)"),
    "TBDY2018_4_8_2_1": (SOURCE_ID, "4.8.2.1"),
    "TBDY2018_TABLE4_1_A13": (SOURCE_ID, "Table 4.1 / A13"),
    "TBDY2018_TABLE4_1_A15": (SOURCE_ID, "Table 4.1 / A15"),
}

CLAIM_DATA = {
    "TBDY2018_4_3_4_5_A15_BRANCHES": (
        ("TBDY2018_4_3_4_5", "TBDY2018_TABLE4_1_A13", "TBDY2018_TABLE4_1_A15"),
        "v1",
        "For A15, Eq. (4.2) requires the solid-wall base overturning-moment sum to be strictly greater than 0.40 Mo and strictly less than 0.75 Mo. Failure of the lower strict bound keeps A15 R=7 and D=2.5 but uses BYS>=3; failure of the upper strict bound uses the solid-wall-only A13 basis R=6, D=2.5, BYS>=2 while the declared system remains A15.",
        "sha256:6567aef012910fbf3d348e9a664ddebaf0b090782a0b12526810f70335dc5fdf",
    ),
    "TBDY2018_4_3_4_8_SOLID_WALL_MDEV": (
        ("TBDY2018_4_3_4_8", "TBDY2018_4_5_3_7_D", "TBDY2018_4_5_3_8_C"),
        "v1",
        "For the 4.3.4.5 wall-share calculation, a solid reinforced-concrete wall base overturning moment MDEV is the wall-base bending moment obtained from the equivalent section effects at the section centroid according to 4.5.3.7(d) or 4.5.3.8(c).",
        "sha256:7097b811dc239995329e6ee02b4c3a918ba78eafc4f9c8bd10c082e015bbaa33",
    ),
    "TBDY2018_4_3_4_8_TOTAL_MO_MODAL": (
        ("TBDY2018_4B_2_5", "TBDY2018_4_3_4_8", "TBDY2018_4_8_2_1"),
        "v1",
        "For a modal-combination analysis used by this slice, total building base overturning moment Mo is a modal response quantity obtained under 4.8.2, with modal base overturning moment defined by 4B.2.5 and modal contributions combined by the referenced modal-combination rule.",
        "sha256:e73191859e3f21bb402622fb96e39552e881be979a581c13d92c11415eaa6e26",
    ),
    "TBDY2018_VS4B_A15_ANALYSIS_BASIS_COMPATIBILITY": (
        ("TBDY2018_4_3_4_5", "TBDY2018_TABLE4_1_A13", "TBDY2018_TABLE4_1_A15"),
        "v1",
        "For this bounded A15 lifecycle, a resolved effective parameter basis is analysis-compatible only when the reviewed analysis assumption uses that effective Table 4.1 row with the same R and D and satisfies the effective BYS policy; a resolved parameter-basis change requires reanalysis rather than reinterpretation of the old reduced seismic effects.",
        "sha256:05207c1642f0dfae8f24f31126733f5fef83b59cbbb99968aed0b8b4abf425dd",
    ),
    "TBDY2018_VS4B_A15_EFFECTIVE_POLICY_LIFECYCLE": (
        ("TBDY2018_4_3_4_5", "TBDY2018_TABLE4_1_A13", "TBDY2018_TABLE4_1_A15"),
        "v1",
        "The bounded A15 post-analysis qualification resolves to LOWER when alphaM<=0.40, NOMINAL when 0.40<alphaM<0.75, and UPPER when alphaM>=0.75. LOWER and NOMINAL retain the A15 R/D basis, with LOWER requiring BYS>=3; UPPER uses the A13 R/D/BYS parameter basis without rewriting the reviewed A15 declaration.",
        "sha256:5b0e36aa3e20e3a852dffe49a7b5b9c01ee26dc5f69a317a9a961811cb1463f7",
    ),
}

CLAIMS_FOR_RULE = {
    "RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY": (
        "TBDY2018_VS4B_A15_ANALYSIS_BASIS_COMPATIBILITY",
    ),
    "RC_A15_4345_EFFECTIVE_POLICY": (
        "TBDY2018_4_3_4_5_A15_BRANCHES",
        "TBDY2018_4_3_4_8_SOLID_WALL_MDEV",
        "TBDY2018_4_3_4_8_TOTAL_MO_MODAL",
        "TBDY2018_VS4B_A15_EFFECTIVE_POLICY_LIFECYCLE",
    ),
}

# Fresh against the FINAL bytes of tbdy_engine.regulatory.rc_a15_wall_share.
APPROVED_IMPLEMENTATION_FINGERPRINTS = {
    "RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY": "sha256:6e805373adf33177b05da7154d0506c2b6d74ceb02ffd8adf43c25b0fe2e3d39",
    "RC_A15_4345_EFFECTIVE_POLICY": "sha256:479591712bff113a2e27b03aa5adb775cc754dd3aadf67c9908715e4dfcfdb16",
}


def build_vs4b_a15_authority_catalog() -> RegulatoryAuthorityCatalog:
    source = RegulatorySourceDocument(
        source_id=SOURCE_ID,
        title="Türkiye Bina Deprem Yönetmeliği 2018",
        edition="2018",
        issuer="AFAD",
        jurisdiction="Türkiye",
        source_fingerprint="sha256:" + SOURCE_SHA256,
    )
    anchors = tuple(
        SourceAnchor(anchor_id=anchor_id, source_id=source_id, locator=locator)
        for anchor_id, (source_id, locator) in sorted(ANCHOR_DATA.items())
    )
    claims = tuple(
        RegulatoryClaim(
            claim_id=claim_id,
            claim_version=claim_version,
            anchor_refs=anchor_refs,
            normalized_statement=statement,
        )
        for claim_id, (anchor_refs, claim_version, statement, _review_fp) in sorted(CLAIM_DATA.items())
    )
    reviews = tuple(
        AuthorityReviewRecord(
            review_id=f"VS4B_A15_REVIEW:{claim_id}:r1",
            claim_id=claim_id,
            status=AuthorityReviewStatus.APPROVED,
            review_version="r1",
            reviewed_claim_fingerprint=review_fp,
            review_basis_refs=("VS4B_A15_SUPERVISOR_REVIEWED_TBDY2018_SOURCE_PACKAGE",),
        )
        for claim_id, (_anchor_refs, _claim_version, _statement, review_fp) in sorted(CLAIM_DATA.items())
    )
    bindings = []
    for spec in VS4B_A15_REGISTRY.derivations:
        rule_name = spec.rule_id.value
        claim_refs = CLAIMS_FOR_RULE[rule_name]
        bindings.append(
            ApprovedImplementationBinding(
                binding_id=f"VS4B_A15_BIND:{rule_name}",
                rule_id=spec.rule_id,
                claim_refs=claim_refs,
                review_refs=tuple(f"VS4B_A15_REVIEW:{claim_id}:r1" for claim_id in claim_refs),
                evaluator_binding_id=spec.evaluator.binding_id,
                rule_version=spec.rule_version,
                implementation_modules=(IMPLEMENTATION_MODULE,),
                approved_implementation_fingerprint=APPROVED_IMPLEMENTATION_FINGERPRINTS[rule_name],
                binding_version="vs4b-a-b2",
            )
        )
    return RegulatoryAuthorityCatalog(
        source_documents=(source,),
        anchors=anchors,
        claims=claims,
        review_records=reviews,
        implementation_bindings=tuple(bindings),
    )


__all__ = [
    "SOURCE_ID",
    "SOURCE_SHA256",
    "IMPLEMENTATION_MODULE",
    "ANCHOR_DATA",
    "CLAIM_DATA",
    "CLAIMS_FOR_RULE",
    "APPROVED_IMPLEMENTATION_FINGERPRINTS",
    "build_vs4b_a15_authority_catalog",
]
