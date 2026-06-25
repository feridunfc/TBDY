#!/usr/bin/env python3
"""Run the deterministic ETABS gateway offline acceptance gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify ETABS gateway fixture replay, source boundaries, "
            "phase provenance, and vendor checksums without ETABS."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(
            "packages/etabs_gateway/tests/fixtures/"
            "gateway_context_v1.json"
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.resolve()
    package_source = repo_root / "packages" / "etabs_gateway" / "src"
    sys.path.insert(0, str(package_source))

    from etabs_gateway.acceptance import (
        canonical_offline_acceptance_report_json,
        run_offline_acceptance,
    )

    report = run_offline_acceptance(
        repo_root=repo_root,
        fixture_path=args.fixture,
    )
    rendered = canonical_offline_acceptance_report_json(report)

    if args.json_out is not None:
        destination = args.json_out
        if not destination.is_absolute():
            destination = repo_root / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            rendered + "\n",
            encoding="utf-8",
            newline="\n",
        )

    print(f"ETABS gateway offline acceptance: {report.status.value}")
    for check in report.checks:
        print(
            f"[{check.status.value}] {check.check_id}: "
            f"{check.message}"
        )

    if report.fixture_sha256 is not None:
        print(f"Fixture SHA-256: {report.fixture_sha256}")
    if report.manifest_phase is not None:
        print(f"Manifest phase: {report.manifest_phase}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
