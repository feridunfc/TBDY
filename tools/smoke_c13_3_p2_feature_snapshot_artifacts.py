#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.feature_snapshot_artifacts import (  # noqa: E402
    build_feature_snapshot_artifact_manifest,
    build_feature_snapshot_report_payload,
    render_feature_snapshot_html_report,
    render_feature_snapshot_markdown_report,
)
from tbdy_engine.features.resolver_feature_snapshot import (  # noqa: E402
    SOURCE_FAMILIES,
    blocked_check_guardrail_report,
    build_feature_snapshot_from_source_rows,
    readiness_projection_report,
    source_family_projection_report,
    summarize_snapshot,
    unit_normalization_report,
)
from tools import smoke_c13_3_p1_feature_snapshot_resolver as p1_smoke  # noqa: E402

SPRINT = "C13.3-P2"
OUTPUT_FILES = [
    "connection_report.json",
    "feature_snapshot.json",
    "feature_snapshot_summary.json",
    "unit_normalization_report.json",
    "readiness_projection_report.json",
    "blocked_check_guardrail_report.json",
    "source_family_projection_report.json",
    "source_table_projection_debug_report.json",
    "feature_snapshot_report_payload.json",
    "feature_snapshot_artifact_manifest.json",
    "feature_snapshot_evidence_report.md",
    "feature_snapshot_evidence_report.html",
]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _empty_projection_debug(generated_at: str) -> dict[str, Any]:
    report = p1_smoke._empty_projection_debug(generated_at)
    report["sprint"] = SPRINT
    return report


def source_table_projection_debug_report(
    *,
    generated_at: str,
    debug_tables: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    report = p1_smoke.source_table_projection_debug_report(
        generated_at=generated_at,
        debug_tables=debug_tables,
        snapshot=snapshot,
    )
    report["sprint"] = SPRINT
    report["check_unlock_allowed"] = False
    report["safe_to_implement_checks_now"] = False
    return report


def _write_all_artifacts(
    out: Path,
    *,
    connection_report: dict[str, Any],
    snapshot: dict[str, Any],
    source_debug_report: dict[str, Any],
    generated_at: str,
) -> None:
    payload = build_feature_snapshot_report_payload(snapshot)
    markdown = render_feature_snapshot_markdown_report(payload)
    html = render_feature_snapshot_html_report(payload)
    manifest = build_feature_snapshot_artifact_manifest(
        snapshot=snapshot,
        output_files=OUTPUT_FILES,
        generated_at=generated_at,
    )

    _write_json(out / "connection_report.json", connection_report)
    _write_json(out / "feature_snapshot.json", snapshot)
    _write_json(out / "feature_snapshot_summary.json", summarize_snapshot(snapshot))
    _write_json(out / "unit_normalization_report.json", unit_normalization_report(snapshot))
    _write_json(out / "readiness_projection_report.json", readiness_projection_report(snapshot))
    _write_json(out / "blocked_check_guardrail_report.json", blocked_check_guardrail_report(snapshot))
    _write_json(out / "source_family_projection_report.json", source_family_projection_report(snapshot))
    _write_json(out / "source_table_projection_debug_report.json", source_debug_report)
    _write_json(out / "feature_snapshot_report_payload.json", payload)
    _write_json(out / "feature_snapshot_artifact_manifest.json", manifest)
    _write_text(out / "feature_snapshot_evidence_report.md", markdown)
    _write_text(out / "feature_snapshot_evidence_report.html", html)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C13.3-P2 FeatureSnapshot artifact contract smoke")
    parser.add_argument("--out", required=True)
    parser.add_argument("--live-etabs", action="store_true")
    parser.add_argument("--max-rows-per-table", type=int, default=25)
    parser.add_argument(
        "--target-family",
        choices=["all", "material_properties", "story_definitions", "pier_section_properties"],
        default="all",
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    generated_at = datetime.now(timezone.utc).isoformat()

    if not args.live_etabs:
        connection_report = {
            "sprint": SPRINT,
            "generated_at": generated_at,
            "live_etabs_requested": False,
            "live_etabs_connected": False,
            "connection_status": "NO_LIVE_REQUESTED",
            "feature_values_faked": False,
            "check_unlock_allowed": False,
            "safe_to_implement_checks_now": False,
            "target_family": args.target_family,
            "max_rows_per_table": args.max_rows_per_table,
        }
        snapshot = build_feature_snapshot_from_source_rows(
            {family: [] for family in SOURCE_FAMILIES},
            live_etabs_connected=False,
            target_family=args.target_family,
            generated_at=generated_at,
        )
        _write_all_artifacts(
            out,
            connection_report=connection_report,
            snapshot=snapshot,
            source_debug_report=_empty_projection_debug(generated_at),
            generated_at=generated_at,
        )
        return 2

    rows, connection_report, debug_tables = p1_smoke._collect_live_rows(args.target_family, args.max_rows_per_table)
    connection_report.update({
        "sprint": SPRINT,
        "generated_at": generated_at,
        "live_etabs_requested": True,
        "feature_values_faked": False,
        "check_unlock_allowed": False,
        "safe_to_implement_checks_now": False,
        "target_family": args.target_family,
        "max_rows_per_table": args.max_rows_per_table,
    })
    snapshot = build_feature_snapshot_from_source_rows(
        rows,
        live_etabs_connected=bool(connection_report.get("live_etabs_connected")),
        model_path=connection_report.get("model_path"),
        etabs_version=connection_report.get("etabs_version"),
        target_family=args.target_family,
        generated_at=generated_at,
    )
    source_debug_report = source_table_projection_debug_report(
        generated_at=generated_at,
        debug_tables=debug_tables,
        snapshot=snapshot,
    )
    _write_all_artifacts(
        out,
        connection_report=connection_report,
        snapshot=snapshot,
        source_debug_report=source_debug_report,
        generated_at=generated_at,
    )
    return 0 if connection_report.get("live_etabs_connected") else 3


if __name__ == "__main__":
    raise SystemExit(main())
