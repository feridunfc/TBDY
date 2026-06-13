#!/usr/bin/env python
"""Bootstrap clean-zip validation fixtures from committed, non-live inputs.

This script never calls live ETABS. It materializes the local_out artifacts that
C9/C10/C11 validation tests historically expect, using only committed fixtures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.checks.dry_run import build_and_write_c11_outputs
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.coverage.live_matrix import build_and_write_c9_outputs
from tbdy_engine.coverage.live_readiness import build_and_write_c10_outputs
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke, tables_from_probe_report, write_smoke_outputs

C8_FIXTURE = ROOT / "tests" / "fixtures" / "c8_table_headers_fixture.json"
C10_CONTEXT = ROOT / "tests" / "fixtures" / "c10_design_context_fixture.json"
C8_OUT = ROOT / "local_out" / "c8_feature_resolver_smoke"
C9_OUT = ROOT / "local_out" / "c9_live_coverage_matrix"
C10_OUT = ROOT / "local_out" / "c10_minimal_live_readiness"
C11_OUT = ROOT / "local_out" / "c11_minimal_check_dry_run"


def bootstrap_validation_fixtures() -> dict[str, str]:
    bundle = load_contracts()
    payload = json.loads(C8_FIXTURE.read_text(encoding="utf-8"))
    tables = tables_from_probe_report(payload, bundle)
    c8_outputs = C8LiveFeatureResolverSmoke(bundle, tables).build_all()
    write_smoke_outputs(C8_OUT, c8_outputs)

    build_and_write_c9_outputs(C8_OUT / "feature_snapshot.json", C9_OUT, contract_bundle=bundle)
    build_and_write_c10_outputs(
        C8_OUT / "feature_snapshot.json",
        C10_CONTEXT,
        C10_OUT,
        coverage_input_path=C9_OUT / "coverage_matrix.json",
    )
    build_and_write_c11_outputs(C10_OUT / "feature_snapshot_with_context.json", C10_OUT / "coverage_matrix.json", C11_OUT)
    return {
        "c8_feature_snapshot": str(C8_OUT / "feature_snapshot.json"),
        "c9_coverage_matrix": str(C9_OUT / "coverage_matrix.json"),
        "c10_feature_snapshot_with_context": str(C10_OUT / "feature_snapshot_with_context.json"),
        "c10_coverage_matrix": str(C10_OUT / "coverage_matrix.json"),
        "c11_boundary_report": str(C11_OUT / "c11_boundary_report.json"),
    }


def main() -> int:
    outputs = bootstrap_validation_fixtures()
    print("Bootstrapped validation fixtures:")
    for key, value in outputs.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
