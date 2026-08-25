#!/usr/bin/env python
"""Print current VS5 source-claim and implementation fingerprints for review/freeze."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.regulatory.authority import implementation_fingerprint, regulatory_claim_fingerprint
from tbdy_engine.regulatory.sources.vs5_column_axial import (
    APPROVED_IMPLEMENTATION_FINGERPRINTS,
    CLAIM_DATA,
    build_vs5_column_axial_authority_catalog,
)
from tbdy_engine.regulatory.column_axial_dual_code import VS5_COLUMN_AXIAL_REGISTRY


def main() -> int:
    catalog = build_vs5_column_axial_authority_catalog()
    print("=== CLAIM FINGERPRINTS ===")
    for claim_id in sorted(CLAIM_DATA):
        claim = catalog.claim(claim_id)
        anchors = tuple(catalog.anchor(ref) for ref in claim.anchor_refs)
        source_ids = sorted({anchor.source_id for anchor in anchors})
        sources = tuple(catalog.source(source_id) for source_id in source_ids)
        actual = regulatory_claim_fingerprint(
            claim=claim,
            anchors=anchors,
            source_documents=sources,
        )
        approved = catalog.review(f"VS5_COLUMN_AXIAL_REVIEW:{claim_id}:r1").reviewed_claim_fingerprint
        print(claim_id)
        print("  approved =", approved)
        print("  actual   =", actual)
        print("  match    =", approved == actual)

    print("=== IMPLEMENTATION FINGERPRINTS ===")
    for spec in VS5_COLUMN_AXIAL_REGISTRY.checks:
        rule_id = spec.rule_id.value
        binding = catalog.bindings_for_rule(spec.rule_id)[0]
        actual = implementation_fingerprint(
            rule_id=spec.rule_id,
            rule_version=spec.rule_version,
            evaluator_binding_id=spec.evaluator.binding_id,
            implementation_modules=binding.implementation_modules,
        )
        approved = APPROVED_IMPLEMENTATION_FINGERPRINTS[rule_id]
        print(rule_id)
        print("  approved =", approved)
        print("  actual   =", actual)
        print("  match    =", approved == actual)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
