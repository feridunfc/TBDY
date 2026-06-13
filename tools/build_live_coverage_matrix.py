#!/usr/bin/env python
"""C9 coverage readiness builder for C8 FeatureSnapshot JSON.

Manual/fixture safe. This script never executes CheckEngine, never emits
CheckResult payloads, never emits engineering verdicts, and does not require
ETABS in CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tbdy_engine.coverage.live_matrix import build_and_write_c9_outputs, build_c9_outputs, write_c9_outputs
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke, tables_from_probe_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build C9 coverage readiness outputs from a C8 FeatureSnapshot JSON file.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--feature-snapshot", help="Path to C8 feature_snapshot.json")
    source.add_argument("--c8-probe-input", help="Path to C8 table header probe fixture/input; resolves a transient FeatureSnapshot in memory")
    parser.add_argument("--out", default="local_out/c9_live_coverage_matrix", help="Output directory")
    args = parser.parse_args(argv)
    try:
        if args.feature_snapshot:
            build_and_write_c9_outputs(Path(args.feature_snapshot), Path(args.out))
        else:
            bundle = load_contracts()
            payload = json.loads(Path(args.c8_probe_input).read_text(encoding="utf-8"))
            tables = tables_from_probe_report(payload, bundle)
            c8_outputs = C8LiveFeatureResolverSmoke(bundle, tables).build_all()
            transient_snapshot = {
                "metadata": {
                    "sprint": "C8_TRANSIENT_FIXTURE_FOR_C9",
                    "check_engine_executed": False,
                    "check_result_emitted": False,
                    "live_verdict_emitted": False,
                },
                "snapshots": [snapshot.as_dict() for snapshot in c8_outputs.snapshots],
            }
            tmp = Path(args.out) / "_transient_c8_feature_snapshot.json"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(transient_snapshot, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            outputs = build_c9_outputs(tmp, contract_bundle=bundle)
            tmp.unlink(missing_ok=True)
            write_c9_outputs(Path(args.out), outputs)
        print(f"Wrote C9 coverage readiness outputs to {args.out}")
        return 0
    except Exception as exc:
        print(f"C9 coverage readiness build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
