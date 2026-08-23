"""Reviewed TBDY 2018 source metadata for the bounded VS-4A policy pack.

No copyrighted regulation text is stored here. Review and implementation
fingerprints are literal approval snapshots: catalog construction never
self-approves changed claims or changed evaluator code.
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
from tbdy_engine.regulatory.structural_system import VS4A_REGISTRY

SOURCE_ID = "TBDY2018_AFAD"
SOURCE_SHA256 = "8d3a9a463d4a534ec2c6834c557b5f706e2ad976c2d6837f6c9b6242e38a6bb2"
IMPLEMENTATION_MODULE = "tbdy_engine.regulatory.structural_system"

ANCHOR_DATA = {
    "TBDY2018_4_3_1_2": (SOURCE_ID, "4.3.1.2"),
    "TBDY2018_4_3_2_1": (SOURCE_ID, "4.3.2.1"),
    "TBDY2018_4_3_2_4": (SOURCE_ID, "4.3.2.4"),
    "TBDY2018_4_3_3_1": (SOURCE_ID, "4.3.3.1"),
    "TBDY2018_4_3_4_1": (SOURCE_ID, "4.3.4.1"),
    "TBDY2018_4_3_4_2": (SOURCE_ID, "4.3.4.2"),
    "TBDY2018_4_3_4_3": (SOURCE_ID, "4.3.4.3"),
    "TBDY2018_4_3_4_5": (SOURCE_ID, "4.3.4.5"),
    "TBDY2018_4_3_4_6": (SOURCE_ID, "4.3.4.6"),
    "TBDY2018_4_3_4_7": (SOURCE_ID, "4.3.4.7"),
    "TBDY2018_4_3_4_8": (SOURCE_ID, "4.3.4.8"),
    **{f"TBDY2018_TABLE4_1_{row}": (SOURCE_ID, f"Table 4.1 / {row}") for row in ("A11", "A12", "A13", "A14", "A15", "A16", "A21", "A22", "A23", "A24", "A31", "A32", "A33")},
}

CLAIM_DATA = {
    "TBDY2018_TABLE4_1_A11": (("TBDY2018_TABLE4_1_A11",), "v1", "A11 cast-in-place RC Table 4.1 baseline policy is ductility=HIGH, R=8, D=3, permitted BYS classes satisfy BYS>=3.", "sha256:990c4d15fff7d89c63671e87451561850371888f7e4ef7616e4f828fd994ace6"),
    "TBDY2018_TABLE4_1_A12": (("TBDY2018_TABLE4_1_A12",), "v1", "A12 cast-in-place RC Table 4.1 baseline policy is ductility=HIGH, R=7, D=2.5, permitted BYS classes satisfy BYS>=2.", "sha256:fc833735ce1df90578e945938683c9f2328346a0e49165eb5aa76ea838783251"),
    "TBDY2018_TABLE4_1_A13": (("TBDY2018_TABLE4_1_A13",), "v1", "A13 cast-in-place RC Table 4.1 baseline policy is ductility=HIGH, R=6, D=2.5, permitted BYS classes satisfy BYS>=2.", "sha256:bb6a5545c4af3666c733869f28f293a171a15c7f65cec1b99fbdad65d8842263"),
    "TBDY2018_TABLE4_1_A14": (("TBDY2018_TABLE4_1_A14",), "v1", "A14 cast-in-place RC Table 4.1 baseline policy is ductility=HIGH, R=8, D=2.5, permitted BYS classes satisfy BYS>=2.", "sha256:e04fcc74d5a5d034bb4d5f2490e4d2a342e4d103d90e42ce7239a01ddf571e50"),
    "TBDY2018_TABLE4_1_A15": (("TBDY2018_TABLE4_1_A15",), "v1", "A15 cast-in-place RC Table 4.1 baseline policy is ductility=HIGH, R=7, D=2.5, permitted BYS classes satisfy BYS>=2.", "sha256:eb78f1abc7070d3ee074e485f99b0de5271326a7c9b931cd305a06d207315341"),
    "TBDY2018_TABLE4_1_A16": (("TBDY2018_TABLE4_1_A16",), "v1", "A16 is the high-ductility one-storey cast-in-place RC column system with R=3, D=2, building height not exceeding 12 m, and pinned roof-level connections; the ordinary Table 4.1 BYS lookup is not used.", "sha256:f48affae8cbe55b1273bbfb168e621a254dcacf14f4e6310a106c7c3f800e699"),
    "TBDY2018_TABLE4_1_A21": (("TBDY2018_TABLE4_1_A21",), "v1", "A21 cast-in-place RC Table 4.1 baseline policy is ductility=MIXED, R=6, D=2.5, permitted BYS classes satisfy BYS>=4.", "sha256:439cf5bdde2f64ac9c840f41ec815e89e23d8841e6a4080492dc6e4fd3834de7"),
    "TBDY2018_TABLE4_1_A22": (("TBDY2018_TABLE4_1_A22",), "v1", "A22 cast-in-place RC Table 4.1 baseline policy is ductility=MIXED, R=5, D=2.5, permitted BYS classes satisfy BYS>=4.", "sha256:3fd21b66368db4f3b4477e3f0f51792ecc092e77972ffbe135862fea47fac416"),
    "TBDY2018_TABLE4_1_A23": (("TBDY2018_TABLE4_1_A23",), "v1", "A23 cast-in-place RC Table 4.1 baseline policy is ductility=MIXED, R=6, D=2.5, permitted BYS classes satisfy BYS>=6.", "sha256:11e6e0d48d10e70e493233e32d554d0b58e46cc0b5b80e6de1998272b90066c2"),
    "TBDY2018_TABLE4_1_A24": (("TBDY2018_TABLE4_1_A24",), "v1", "A24 cast-in-place RC Table 4.1 baseline policy is ductility=MIXED, R=5, D=2.5, permitted BYS classes satisfy BYS>=6.", "sha256:6dc3ef7202bbd133d134306bf47bee9f7714a1dd09b66eeaf5f22e2991dd5194"),
    "TBDY2018_TABLE4_1_A31": (("TBDY2018_TABLE4_1_A31",), "v1", "A31 cast-in-place RC Table 4.1 baseline policy is ductility=LIMITED, R=4, D=2.5, permitted BYS classes satisfy BYS>=7.", "sha256:ce172bccebb566544011410ce07d163062c8ef3825c93609d7004c56dcd931e2"),
    "TBDY2018_TABLE4_1_A32": (("TBDY2018_TABLE4_1_A32",), "v1", "A32 cast-in-place RC Table 4.1 baseline policy is ductility=LIMITED, R=4, D=2, permitted BYS classes satisfy BYS>=6.", "sha256:c3db7396f000b7dd66583fd62ed0a1ce00ef2a9e1637679eaee32c271da2335a"),
    "TBDY2018_TABLE4_1_A33": (("TBDY2018_TABLE4_1_A33",), "v1", "A33 cast-in-place RC Table 4.1 baseline policy is ductility=LIMITED, R=4, D=2, permitted BYS classes satisfy BYS>=6.", "sha256:d6eb87deabec48167e74f9b7f55d55319dc265c67b21ef44926ee566ad0e361c"),
    "TBDY2018_4_3_1_2_A21_A22_DTS4_BYS": (("TBDY2018_4_3_1_2",), "v1", "For A21 and A22, only when DTS=4, the permitted building height class may be relaxed to BYS>=2.", "sha256:91c360212669f1d2b9601fe14021963a52fdf94a8ef46f20d1701f6903ab6c27"),
    "TBDY2018_4_3_2_1_TABLE4_1_RD": (("TBDY2018_4_3_2_1",), "v1", "Structural system behavior coefficient R and overstrength coefficient D are taken from Table 4.1 for the applicable structural system and ductility level.", "sha256:39069c8824df076e100e2758a0be51017a0415cf25070ed09cdccebd41b2dd11"),
    "TBDY2018_4_3_2_4_WALL_DISTRIBUTION_R_POLICY": (("TBDY2018_4_3_2_4",), "v1", "For DTS 1,1a,2,2a RC-wall and/or steel-braced buildings, failure of either specified distribution condition requires (4/5)R in that direction while D is unchanged; VS-4A therefore treats the final R as pending post-analysis qualification where this clause applies.", "sha256:ceff776f6e1323838efb1928000b02e5baa8ce7be054fe469b290403174dd5c4"),
    "TBDY2018_4_3_3_1_DUCTILITY_CLASSES": (("TBDY2018_4_3_3_1",), "v1", "Structural systems are classified by Table 4.1 into high, limited, or mixed ductility levels.", "sha256:edb53571a81ca02ecabc9bd473b589b1492591cc2c34631a67db6c444e54d7ad"),
    "TBDY2018_4_3_4_1_LIMITED_DTS": (("TBDY2018_4_3_4_1",), "v1", "Limited-ductility structural systems are prohibited for DTS=1a,2a,3a,4a.", "sha256:7cc2ec957cab05ed8d96d5bb8b2dd973b48993e8d7be8f72dc12ed2218d5c080"),
    "TBDY2018_4_3_4_1_MIXED_DTS_BYS": (("TBDY2018_4_3_4_1",), "v1", "Mixed-ductility structural systems are prohibited for DTS=1a or 2a when BYS<=6.", "sha256:7a19f18a6603026940b0532b3f8f6b846a59539ef529b44f3f0cfaaf50399061"),
    "TBDY2018_4_3_4_2_ORTHOGONAL_DUCTILITY": (("TBDY2018_4_3_4_2",), "v1", "Orthogonal structural systems must have the same ductility level; different R values and their corresponding D values may be used by direction.", "sha256:bf0b93e06bd2fac88a9024a779db1143bb45be4401db4c42ef93ac471213c717"),
    "TBDY2018_4_3_4_3_A31_DTS": (("TBDY2018_4_3_4_3",), "v1", "A31 limited-ductility RC moment-frame-only systems may be used only for DTS=3 or DTS=4.", "sha256:ef2a0aba405d354482701ef518dbac397d169a47522fd38b55084976b0dedec7"),
    "TBDY2018_4_3_4_5_HIGH_COMBINED_QUALIFICATION": (("TBDY2018_4_3_4_5",), "v1", "High-ductility frame plus high wall/braced systems require the post-analysis overturning-moment distribution qualification of 4.3.4.5; VS-4A does not resolve that calculation.", "sha256:0d6d38f772f8215196001ed3c27521e13d448ee344ef1c8b64f80c18c6bf269f"),
    "TBDY2018_4_3_4_6_MIXED_QUALIFICATION": (("TBDY2018_4_3_4_6",), "v1", "Mixed-ductility systems require the post-analysis overturning-moment distribution qualification of 4.3.4.6; VS-4A does not resolve that calculation.", "sha256:5b8c5f8cf1911963367f2c727454951e18bf0c0e8050fa2d0f91636284ffc41c"),
    "TBDY2018_4_3_4_7_LIMITED_WALL_FRAME_QUALIFICATION": (("TBDY2018_4_3_4_7",), "v1", "Limited wall plus limited moment-frame systems require the 4.3.4.7 post-analysis qualification; VS-4A does not resolve that calculation.", "sha256:da3944c74229475733340123f535cf1e0ac8ddc44b1c535ef3c8087fbc985b28"),
    "TBDY2018_4_3_4_8_MDEV_MO_DEFERRED": (("TBDY2018_4_3_4_8",), "v1", "MDEV and Mo used by 4.3.2.4, 4.3.4.5 and 4.3.4.6 are obtained by the methods referenced in 4.3.4.8; formal derivation is deferred to VS-4B.", "sha256:8cc9203c2a196278d3fd099b7c1441d7db57ecda11786f7ceb4f0df83aa4847d"),
    "TBDY2018_VS4A_ANALYSIS_BASIS_COMPATIBILITY": (("TBDY2018_4_3_2_1", "TBDY2018_4_3_2_4", "TBDY2018_4_3_4_5", "TBDY2018_4_3_4_6", "TBDY2018_4_3_4_7"), "v1", "Analysis-basis compatibility is MATCH only when the final applicable directional system/R/D policy is resolved and equals the reviewed analysis assumption; a resolved mismatch requires reanalysis, while pending post-analysis qualification remains UNRESOLVED.", "sha256:73d1bf5b5a69614c05b4ab71b2831de1f053fd753e590ed2338453befd5f40e8"),
}

_ROW_CLAIMS = tuple(f"TBDY2018_TABLE4_1_{row}" for row in ("A11", "A12", "A13", "A14", "A15", "A16", "A21", "A22", "A23", "A24", "A31", "A32", "A33"))
CLAIMS_FOR_RULE = {
    "RC_SYSTEM_DUCTILITY_CLASS": ("TBDY2018_4_3_3_1_DUCTILITY_CLASSES", *_ROW_CLAIMS),
    "RC_TABLE_4_1_BASE_R": ("TBDY2018_4_3_2_1_TABLE4_1_RD", *_ROW_CLAIMS),
    "RC_TABLE_4_1_BASE_D": ("TBDY2018_4_3_2_1_TABLE4_1_RD", *_ROW_CLAIMS),
    "RC_TABLE_4_1_BASE_BYS_POLICY": _ROW_CLAIMS,
    "RC_EFFECTIVE_PREANALYSIS_BYS_POLICY": ("TBDY2018_4_3_1_2_A21_A22_DTS4_BYS", *_ROW_CLAIMS),
    "RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT": ("TBDY2018_4_3_2_4_WALL_DISTRIBUTION_R_POLICY", "TBDY2018_4_3_4_5_HIGH_COMBINED_QUALIFICATION", "TBDY2018_4_3_4_6_MIXED_QUALIFICATION", "TBDY2018_4_3_4_7_LIMITED_WALL_FRAME_QUALIFICATION", *_ROW_CLAIMS),
    "RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY": ("TBDY2018_4_3_1_2_A21_A22_DTS4_BYS", "TBDY2018_4_3_2_1_TABLE4_1_RD", "TBDY2018_4_3_2_4_WALL_DISTRIBUTION_R_POLICY", "TBDY2018_4_3_3_1_DUCTILITY_CLASSES", "TBDY2018_4_3_4_5_HIGH_COMBINED_QUALIFICATION", "TBDY2018_4_3_4_6_MIXED_QUALIFICATION", "TBDY2018_4_3_4_7_LIMITED_WALL_FRAME_QUALIFICATION", *_ROW_CLAIMS),
    "RC_ANALYSIS_BASIS_COMPATIBILITY": ("TBDY2018_VS4A_ANALYSIS_BASIS_COMPATIBILITY",),
    "RC_TABLE_4_1_BYS_ELIGIBILITY": ("TBDY2018_4_3_1_2_A21_A22_DTS4_BYS", *_ROW_CLAIMS),
    "RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY": ("TBDY2018_4_3_4_1_LIMITED_DTS", "TBDY2018_4_3_4_1_MIXED_DTS_BYS"),
    "RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY": ("TBDY2018_4_3_4_2_ORTHOGONAL_DUCTILITY", *_ROW_CLAIMS),
    "RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY": ("TBDY2018_4_3_4_3_A31_DTS", "TBDY2018_TABLE4_1_A31"),
    "RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY": ("TBDY2018_TABLE4_1_A16",),
}

APPROVED_IMPLEMENTATION_FINGERPRINTS = {
    "RC_ANALYSIS_BASIS_COMPATIBILITY": "sha256:53d30b83716b831ef658ca58d348b24eeb0a5e08bc7b77fbb666d222049c7756",
    "RC_DIRECTIONAL_BASELINE_SYSTEM_POLICY": "sha256:44d4375d7756669cdccacc16b06b951aa1d8c23d2a0ec5d7d3b7e223350f9bf9",
    "RC_EFFECTIVE_PREANALYSIS_BYS_POLICY": "sha256:2efb1692b830eb939694e61be11787e131dcfb0518d059e2acf3fa1c07909a2b",
    "RC_POST_ANALYSIS_SYSTEM_QUALIFICATION_REQUIREMENT": "sha256:95da0c7aca94751b6d01781cd0ce3143b29ebb74207754bc2728f024d6f4ffe0",
    "RC_SYSTEM_DUCTILITY_CLASS": "sha256:0c811d0e5b3a4d99ff8d41f345bc291b3ccc798c8ae234f66a290b958f17e4ca",
    "RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY": "sha256:2f08b57ab5ddb3427dea0cf6e297aec5a9c86800a33023163aa325be63c3c6d7",
    "RC_TABLE_4_1_BASE_BYS_POLICY": "sha256:054b39c5e587cf912338da6ab928bce208c7b13174202e7391a846f194c93637",
    "RC_TABLE_4_1_BASE_D": "sha256:1b66ea51bec57142318aea12636160a0c423feb2392caba5df454ad90d3d6456",
    "RC_TABLE_4_1_BASE_R": "sha256:3d1ee369088d07a077816113f6122584cdc3530e1d6986149d38dffb36e2eacb",
    "RC_TABLE_4_1_BYS_ELIGIBILITY": "sha256:27827ff52c23b1bcca45280e106638ac813c8c93aa4d9e222d8869a8af0054f3",
    "RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY": "sha256:c57d3df53cf6414834795f3bc90a5c2f0be1422c1005f776eed6fba3ea31995d",
    "RC_TBDY_4_3_4_2_ORTHOGONAL_DUCTILITY_CONSISTENCY": "sha256:b4705d26b9b9fe297a6bd89c3a6952d18d665734b110ac4ba985d76243315e6f",
    "RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY": "sha256:0c1aacdca9593b6afa5fe715c6fa51407da68c8476d60b732e4c75ab43b851da",
}


def build_vs4a_authority_catalog() -> RegulatoryAuthorityCatalog:
    source = RegulatorySourceDocument(source_id=SOURCE_ID, title="Türkiye Bina Deprem Yönetmeliği 2018", edition="2018", issuer="AFAD", jurisdiction="Türkiye", source_fingerprint="sha256:" + SOURCE_SHA256)
    anchors = tuple(SourceAnchor(anchor_id=anchor_id, source_id=source_id, locator=locator) for anchor_id, (source_id, locator) in sorted(ANCHOR_DATA.items()))
    claims = tuple(RegulatoryClaim(claim_id=claim_id, claim_version=claim_version, anchor_refs=anchor_refs, normalized_statement=statement) for claim_id, (anchor_refs, claim_version, statement, _review_fp) in sorted(CLAIM_DATA.items()))
    reviews = tuple(AuthorityReviewRecord(review_id=f"VS4A_REVIEW:{claim_id}:r1", claim_id=claim_id, status=AuthorityReviewStatus.APPROVED, review_version="r1", reviewed_claim_fingerprint=review_fp, review_basis_refs=("VS4A_SUPERVISOR_REVIEWED_TBDY2018_SOURCE_PACKAGE",)) for claim_id, (_anchor_refs, _claim_version, _statement, review_fp) in sorted(CLAIM_DATA.items()))
    bindings = []
    for spec in (*VS4A_REGISTRY.derivations, *VS4A_REGISTRY.checks):
        rule_name = spec.rule_id.value
        claim_refs = CLAIMS_FOR_RULE[rule_name]
        bindings.append(ApprovedImplementationBinding(binding_id=f"VS4A_BIND:{rule_name}", rule_id=spec.rule_id, claim_refs=claim_refs, review_refs=tuple(f"VS4A_REVIEW:{claim_id}:r1" for claim_id in claim_refs), evaluator_binding_id=spec.evaluator.binding_id, rule_version=spec.rule_version, implementation_modules=(IMPLEMENTATION_MODULE,), approved_implementation_fingerprint=APPROVED_IMPLEMENTATION_FINGERPRINTS[rule_name], binding_version="vs4a-b1"))
    return RegulatoryAuthorityCatalog(source_documents=(source,), anchors=anchors, claims=claims, review_records=reviews, implementation_bindings=tuple(bindings))


__all__ = ["SOURCE_ID", "SOURCE_SHA256", "ANCHOR_DATA", "CLAIM_DATA", "CLAIMS_FOR_RULE", "APPROVED_IMPLEMENTATION_FINGERPRINTS", "build_vs4a_authority_catalog"]
