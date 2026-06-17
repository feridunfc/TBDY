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

from tbdy_engine.features.check_preflight_diagnostics import build_check_preflight_diagnostic_report  # noqa: E402
from tbdy_engine.features.feature_snapshot_artifact_validator import validate_artifact_file_set  # noqa: E402
from tbdy_engine.features.feature_snapshot_artifacts import (  # noqa: E402
    build_feature_snapshot_artifact_manifest,
    build_feature_snapshot_report_payload,
    render_feature_snapshot_html_report,
    render_feature_snapshot_markdown_report,
)
from tbdy_engine.features.resolver_feature_snapshot import (  # noqa: E402
    blocked_check_guardrail_report,
    build_feature_snapshot_from_source_rows,
    readiness_projection_report,
    source_family_projection_report,
    summarize_snapshot,
    unit_normalization_report,
)
from tbdy_engine.features.source_feature_snapshot_builder import fixture_source_rows  # noqa: E402

SPRINT = "C13.3-P3"
OUTPUT_FILES = [
    "connection_report.json",
    "feature_snapshot.json",
    "feature_snapshot_summary.json",
    "unit_normalization_report.json",
    "readiness_projection_report.json",
    "blocked_check_guardrail_report.json",
    "source_family_projection_report.json",
    "feature_snapshot_report_payload.json",
    "feature_snapshot_artifact_manifest.json",
    "feature_snapshot_evidence_report.md",
    "feature_snapshot_evidence_report.html",
    "check_preflight_diagnostic_report.json",
    "artifact_contract_validation_report.json",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_fixture_rows() -> dict[str, list[dict[str, Any]]]:
    rows = fixture_source_rows()
    return {
        "material_properties": rows["material_properties"][:1],
        "story_definitions": rows["story_definitions"][:3],
        "pier_section_properties": rows["pier_section_properties"][:1],
    }


def _fixture_rows(kind: str) -> dict[str, list[dict[str, Any]]]:
    if kind == "minimal":
        return _minimal_fixture_rows()
    return fixture_source_rows()


def _manifest_with_p3_roles(snapshot: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    manifest = build_feature_snapshot_artifact_manifest(
        snapshot=snapshot,
        output_files=OUTPUT_FILES,
        generated_at=generated_at,
    )
    manifest["sprint"] = SPRINT
    manifest["artifact_roles"].update({
        "check_preflight_diagnostic_report.json": "diagnostic-only check preflight contract",
        "artifact_contract_validation_report.json": "no-live artifact contract validation report",
    })
    manifest["feature_values_faked"] = False
    manifest["safe_to_implement_checks_now"] = False
    manifest["check_unlock_allowed"] = False
    manifest["engineering_verdicts_emitted"] = False
    manifest["check_results_emitted"] = False
    manifest["excel_production_input_used"] = False
    return manifest


def build_no_live_artifacts(out: Path, *, fixture: str = "p2-compatible") -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = _fixture_rows(fixture)
    connection_report = {
        "sprint": SPRINT,
        "generated_at": generated_at,
        "live_etabs_requested": False,
        "live_etabs_connected": False,
        "connection_status": "NO_LIVE_REQUESTED",
        "feature_values_faked": False,
        "fixture_values_used": True,
        "fixture": fixture,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
    }
    snapshot = build_feature_snapshot_from_source_rows(
        rows,
        live_etabs_connected=False,
        model_path=None,
        etabs_version=None,
        target_family="all",
        generated_at=generated_at,
    )
    report_payload = build_feature_snapshot_report_payload(snapshot)
    artifact_manifest = _manifest_with_p3_roles(snapshot, generated_at=generated_at)
    markdown_report = render_feature_snapshot_markdown_report(report_payload)
    html_report = render_feature_snapshot_html_report(report_payload)
    preflight_report = build_check_preflight_diagnostic_report(report_payload)

    _write_json(out / "connection_report.json", connection_report)
    _write_json(out / "feature_snapshot.json", snapshot)
    _write_json(out / "feature_snapshot_summary.json", summarize_snapshot(snapshot))
    _write_json(out / "unit_normalization_report.json", unit_normalization_report(snapshot))
    _write_json(out / "readiness_projection_report.json", readiness_projection_report(snapshot))
    _write_json(out / "blocked_check_guardrail_report.json", blocked_check_guardrail_report(snapshot))
    _write_json(out / "source_family_projection_report.json", source_family_projection_report(snapshot))
    _write_json(out / "feature_snapshot_report_payload.json", report_payload)
    _write_json(out / "feature_snapshot_artifact_manifest.json", artifact_manifest)
    _write_text(out / "feature_snapshot_evidence_report.md", markdown_report)
    _write_text(out / "feature_snapshot_evidence_report.html", html_report)
    _write_json(out / "check_preflight_diagnostic_report.json", preflight_report)
    _write_json(
        out / "artifact_contract_validation_report.json",
        {
            "sprint": SPRINT,
            "validation_status": "PENDING",
            "safe_to_implement_checks_now": False,
            "check_unlock_allowed": False,
            "engineering_verdicts_emitted": False,
            "check_results_emitted": False,
            "excel_production_input_used": False,
        },
    )
    validation_report = validate_artifact_file_set(out)
    _write_json(out / "artifact_contract_validation_report.json", validation_report)
    return validation_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C13.3-P3 no-live FeatureSnapshot artifact contract smoke")
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixture", choices=["minimal", "p2-compatible"], default="p2-compatible")
    args = parser.parse_args(argv)

    validation_report = build_no_live_artifacts(Path(args.out), fixture=args.fixture)
    print(json.dumps(validation_report, indent=2, sort_keys=True))
    return 0 if validation_report["validation_status"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
