"""Report-facing FeatureSnapshot artifact contract for C13.3-P2.

The functions in this module convert a resolver FeatureSnapshot dictionary into
check-safe JSON/Markdown/HTML artifacts.  They do not invoke CheckEngine, do not
produce CheckResult payloads, and do not emit engineering verdicts.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from html import escape
from typing import Any, Mapping, Sequence

from tbdy_engine.features.readiness import assert_no_engineering_verdict_text

SPRINT = "C13.3-P2"
ARTIFACT_CONTRACT_VERSION = "c13.3-p2.feature_snapshot_artifact.v1"
LOCKED_GUARDRAIL_IDS = (
    "material_compliance_locked",
    "story_drift_torsion_force_locked",
    "pier_wall_force_capacity_detailing_locked",
)


def _generated_at(value: str | None = None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _records(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(snapshot.get("feature_records") or snapshot.get("features") or [])


def _numeric_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [record for record in records if isinstance(record.get("raw_value"), (int, float))]


def _counter(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record.get(key)) for record in records if record.get(key)).items()))


def _source_tables(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(table) for record in records for table in record.get("source_tables", [])})


def _representative_feature(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": record.get("feature_id"),
        "feature_name": record.get("feature_name"),
        "component_type": record.get("component_type"),
        "component_id": record.get("component_id"),
        "source_family": record.get("source_family"),
        "source_tables": list(record.get("source_tables", [])),
        "source_columns": list(record.get("source_columns", [])),
        "readiness_status": record.get("readiness_status"),
        "feature_status": record.get("feature_status"),
        "raw_value": record.get("raw_value"),
        "raw_unit": record.get("raw_unit"),
        "normalized_value": record.get("normalized_value"),
        "normalized_unit": record.get("normalized_unit"),
        "quantity_kind": record.get("quantity_kind"),
        "derived": bool(record.get("derived")),
        "safe_to_use_for_check": False,
        "check_unlock_allowed": False,
    }


def _representatives(records: Sequence[Mapping[str, Any]], limit: int = 18) -> list[dict[str, Any]]:
    ordered = sorted(
        records,
        key=lambda record: (
            str(record.get("source_family", "")),
            str(record.get("component_type", "")),
            str(record.get("feature_id", "")),
        ),
    )
    preferred = [record for record in ordered if record.get("feature_status") in {"RESOLVED", "PARTIAL"}]
    selected = (preferred or ordered)[:limit]
    return [_representative_feature(record) for record in selected]


def _source_family_entries(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    families = sorted({str(record.get("source_family")) for record in records if record.get("source_family")})
    entries: list[dict[str, Any]] = []
    for family in families:
        family_records = [record for record in records if record.get("source_family") == family]
        status_counts = _counter(family_records, "feature_status")
        readiness_counts = _counter(family_records, "readiness_status")
        blocked_count = sum(
            status_counts.get(status, 0)
            for status in (
                "BLOCKED_SEMANTIC_REVIEW",
                "BLOCKED_NEEDS_LIVE_PROBE",
                "LOCKED_CHECK_NOT_ALLOWED",
                "OUT_OF_SCOPE_UNSUPPORTED",
            )
        )
        entries.append({
            "source_family": family,
            "feature_record_count": len(family_records),
            "numeric_feature_count": len(_numeric_records(family_records)),
            "feature_status_counts": status_counts,
            "readiness_status_counts": readiness_counts,
            "source_tables": _source_tables(family_records),
            "representative_feature_ids": [str(record.get("feature_id")) for record in _representatives(family_records, limit=6)],
            "has_resolved_records": status_counts.get("RESOLVED", 0) > 0,
            "has_partial_records": status_counts.get("PARTIAL", 0) > 0,
            "has_blocked_records": blocked_count > 0,
        })
    return entries


def _blocked_guardrails(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(record.get("feature_id")): record for record in records}
    guardrails: list[dict[str, Any]] = []
    for feature_id in LOCKED_GUARDRAIL_IDS:
        record = by_id.get(feature_id)
        if not record:
            continue
        guardrails.append({
            "feature_id": record.get("feature_id"),
            "feature_name": record.get("feature_name"),
            "source_family": record.get("source_family"),
            "readiness_status": record.get("readiness_status"),
            "feature_status": record.get("feature_status"),
            "lock_reason": record.get("semantic_guardrails", {}).get("lock_reason"),
            "safe_to_use_for_check": False,
            "check_unlock_allowed": False,
        })
    return guardrails


def build_feature_snapshot_report_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build the deterministic, report-facing FeatureSnapshot payload."""
    records = _records(snapshot)
    numeric_records = _numeric_records(records)
    source_families = _source_family_entries(records)
    payload = {
        "sprint": SPRINT,
        "generated_at": snapshot.get("generated_at"),
        "source_contract_baseline": snapshot.get("source_contract_baseline"),
        "live_etabs_connected": bool(snapshot.get("live_etabs_connected")),
        "model_path": snapshot.get("model_path"),
        "etabs_version": snapshot.get("etabs_version"),
        "target_family": snapshot.get("target_family", "all"),
        "feature_record_count": len(records),
        "feature_status_counts": dict(snapshot.get("feature_status_counts") or _counter(records, "feature_status")),
        "readiness_status_counts": dict(snapshot.get("readiness_status_counts") or _counter(records, "readiness_status")),
        "source_family_counts": dict(snapshot.get("source_family_counts") or {entry["source_family"]: entry["feature_record_count"] for entry in source_families}),
        "numeric_feature_count": int(snapshot.get("numeric_feature_count") or len(numeric_records)),
        "raw_values_preserved": bool(snapshot.get("raw_values_preserved", all(record.get("evidence", {}).get("raw_value") == record.get("raw_value") for record in records))),
        "all_numeric_have_units": bool(snapshot.get("all_numeric_have_units", all(record.get("raw_unit") and record.get("normalized_unit") for record in numeric_records))),
        "all_numeric_have_quantity_kind": bool(snapshot.get("all_numeric_have_quantity_kind", all(record.get("quantity_kind") for record in numeric_records))),
        "all_numeric_have_conversion_provenance": bool(snapshot.get("all_numeric_have_conversion_provenance", all(record.get("conversion_provenance") for record in numeric_records))),
        "unit_policy_closed": True,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "source_families": source_families,
        "blocked_guardrails": _blocked_guardrails(records),
        "representative_features": _representatives(records),
        "report_disclaimer": {
            "source_evidence_only": True,
            "engineering_compliance_report": False,
            "check_engine_invoked": False,
            "check_results_emitted": False,
            "engineering_verdicts_emitted": False,
        },
    }
    assert_no_engineering_verdict_text(payload)
    return payload


def build_feature_snapshot_artifact_manifest(
    *,
    snapshot: Mapping[str, Any],
    output_files: Sequence[str],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic machine-readable artifact manifest."""
    files = list(output_files)
    artifact_roles = {
        "connection_report.json": "live connection metadata",
        "feature_snapshot.json": "resolver feature snapshot source payload",
        "feature_snapshot_summary.json": "snapshot summary counts",
        "unit_normalization_report.json": "unit metadata completeness report",
        "readiness_projection_report.json": "source readiness projection report",
        "blocked_check_guardrail_report.json": "locked check guardrail report",
        "source_family_projection_report.json": "source-family projection report",
        "source_table_projection_debug_report.json": "ETABS source table fetch/projection diagnostics",
        "feature_snapshot_report_payload.json": "report-facing JSON payload",
        "feature_snapshot_artifact_manifest.json": "artifact manifest",
        "feature_snapshot_evidence_report.md": "human-readable Markdown source evidence report",
        "feature_snapshot_evidence_report.html": "human-readable HTML source evidence report",
    }
    manifest = {
        "sprint": SPRINT,
        "artifact_contract_version": ARTIFACT_CONTRACT_VERSION,
        "generated_at": _generated_at(generated_at),
        "source_snapshot_file": "feature_snapshot.json",
        "output_files": files,
        "artifact_roles": {file_name: artifact_roles[file_name] for file_name in files if file_name in artifact_roles},
        "live_etabs_connected": bool(snapshot.get("live_etabs_connected")),
        "feature_values_faked": False,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": False,
        "check_results_emitted": False,
        "excel_production_input_used": False,
    }
    assert_no_engineering_verdict_text(manifest)
    return manifest


def _format_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def render_feature_snapshot_markdown_report(payload: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown source evidence report."""
    lines: list[str] = [
        "# C13.3-P2 FeatureSnapshot Evidence Report",
        "",
        "## Connection summary",
        f"- live_etabs_connected: {_format_bool(payload.get('live_etabs_connected'))}",
        f"- model_path: {payload.get('model_path') or 'None'}",
        f"- etabs_version: {payload.get('etabs_version') or 'None'}",
        f"- target_family: {payload.get('target_family')}",
        "",
        "## Snapshot summary",
    ]
    lines.extend(_markdown_table(
        ["metric", "value"],
        [
            ["feature_record_count", payload.get("feature_record_count", 0)],
            ["numeric_feature_count", payload.get("numeric_feature_count", 0)],
            ["raw_values_preserved", _format_bool(payload.get("raw_values_preserved"))],
            ["unit_policy_closed", _format_bool(payload.get("unit_policy_closed"))],
            ["safe_to_implement_checks_now", _format_bool(payload.get("safe_to_implement_checks_now"))],
            ["check_unlock_allowed", _format_bool(payload.get("check_unlock_allowed"))],
        ],
    ))
    lines.extend(["", "## Source family summary"])
    lines.extend(_markdown_table(
        ["source_family", "records", "numeric", "resolved", "partial", "blocked"],
        [
            [
                item["source_family"],
                item["feature_record_count"],
                item["numeric_feature_count"],
                _format_bool(item["has_resolved_records"]),
                _format_bool(item["has_partial_records"]),
                _format_bool(item["has_blocked_records"]),
            ]
            for item in payload.get("source_families", [])
        ],
    ))
    lines.extend([
        "",
        "## Unit metadata summary",
        f"- all_numeric_have_units: {_format_bool(payload.get('all_numeric_have_units'))}",
        f"- all_numeric_have_quantity_kind: {_format_bool(payload.get('all_numeric_have_quantity_kind'))}",
        f"- all_numeric_have_conversion_provenance: {_format_bool(payload.get('all_numeric_have_conversion_provenance'))}",
        "",
        "## Representative features",
    ])
    lines.extend(_markdown_table(
        ["feature_id", "family", "status", "readiness", "raw_unit", "normalized_unit", "not check-usable"],
        [
            [
                item.get("feature_id"),
                item.get("source_family"),
                item.get("feature_status"),
                item.get("readiness_status"),
                item.get("raw_unit"),
                item.get("normalized_unit"),
                _format_bool(not item.get("safe_to_use_for_check", True)),
            ]
            for item in payload.get("representative_features", [])
        ],
    ))
    lines.extend(["", "## Locked check guardrails"])
    lines.extend(_markdown_table(
        ["feature_id", "family", "status", "reason", "checks locked"],
        [
            [
                item.get("feature_id"),
                item.get("source_family"),
                item.get("feature_status"),
                item.get("lock_reason"),
                _format_bool(not item.get("check_unlock_allowed", True)),
            ]
            for item in payload.get("blocked_guardrails", [])
        ],
    ))
    lines.extend([
        "",
        "## Explicit non-check disclaimer",
        "- This report is source evidence only.",
        "- This report is not an engineering compliance report.",
        "- No TBDY/TS500 check verdicts are emitted.",
        "- CheckEngine is not invoked.",
        "- safe_to_implement_checks_now is false.",
        "- check_unlock_allowed is false.",
        "",
    ])
    text = "\n".join(lines)
    assert_no_engineering_verdict_text(text)
    return text


def render_feature_snapshot_html_report(payload: Mapping[str, Any]) -> str:
    """Render a deterministic static HTML source evidence report."""
    md_payload = render_feature_snapshot_markdown_report(payload)
    rows = "".join(f"<pre>{escape(line)}</pre>\n" for line in md_payload.splitlines())
    html = (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head><meta charset=\"utf-8\"><title>C13.3-P2 FeatureSnapshot Evidence Report</title></head>\n"
        "<body>\n"
        "<h1>C13.3-P2 FeatureSnapshot Evidence Report</h1>\n"
        "<section><h2>Static source evidence artifact</h2>\n"
        "<p>This report is source evidence only. It is not an engineering compliance report.</p>\n"
        "<p>No TBDY/TS500 check verdicts are emitted. CheckEngine is not invoked.</p>\n"
        "<p>safe_to_implement_checks_now is false. check_unlock_allowed is false.</p></section>\n"
        "<section><h2>Rendered Markdown Content</h2>\n"
        f"{rows}"
        "</section>\n"
        "</body>\n"
        "</html>\n"
    )
    assert_no_engineering_verdict_text(html)
    return html


__all__ = [
    "ARTIFACT_CONTRACT_VERSION",
    "SPRINT",
    "build_feature_snapshot_artifact_manifest",
    "build_feature_snapshot_report_payload",
    "render_feature_snapshot_html_report",
    "render_feature_snapshot_markdown_report",
]
