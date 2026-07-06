"""Small deterministic report-package helper for P2.2 deliverables.

This module packages already-rendered product report files. It does not call
ETABS, does not execute checks, and does not mutate source report payloads.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

SPRINT_ID = "P2.3_SCOPE_MATERIAL_COMBINED_VERDICT"
SPRINT_NAME = "P2.3 - Live Object Scope Ledger + Material Evidence + Combined Product Scope Verdict"
DETERMINISTIC_GENERATED_AT = "DETERMINISTIC_NO_WALL_CLOCK"

PACKAGE_INPUT_FILES: tuple[str, ...] = (
    "product_report.json",
    "product_report.md",
    "product_summary.json",
    "product_evidence.json",
    "product_report_source_tables.json",
    "product_slice_manifest.json",
    "product_report.html",
    "object_scope_ledger.json",
    "object_scope_summary.json",
    "material_evidence.json",
    "material_summary.json",
    "README.md",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _report_file_entries(report_dir: Path, file_names: Sequence[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name in file_names:
        path = report_dir / name
        if not path.is_file():
            continue
        entries.append({
            "path": name,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    return entries


def _truth_status_from_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "checked_scope_status",
        "model_scope_status",
        "full_tbdy_compliance_status",
        "unsupported_object_count_total",
        "excluded_frame_object_count_total",
        "frame_assignment_type_counts",
        "source_frame_assignment_row_count",
        "frame_assignment_type_counts_reconciled",
        "object_scope_ledger_row_count",
        "object_scope_reconciled",
        "checked_concrete_beam_object_count",
        "checked_concrete_column_object_count",
        "excluded_brace_object_count",
        "excluded_null_object_count",
        "excluded_other_object_count",
        "material_evidence_status",
        "combined_product_scope_status",
    )
    return {key: summary.get(key) for key in keys if key in summary}


def _guardrail_metadata(report: Mapping[str, Any]) -> dict[str, bool]:
    metadata = report.get("metadata") if isinstance(report.get("metadata"), Mapping) else {}
    guardrails = report.get("guardrails") if isinstance(report.get("guardrails"), Mapping) else {}
    return {
        "no_etabs_mutation": not bool(metadata.get("etabs_model_mutated", False)),
        "no_analysis_run": not bool(metadata.get("analysis_run", False)),
        "no_design_run": not bool(metadata.get("design_run", False)),
        "no_excel_production_input": not bool(guardrails.get("excel_production_path_used", False)),
        "no_check_engine_execution": not bool(metadata.get("check_engine_executed", False)),
    }


def build_package_readme(report: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    truth = _truth_status_from_summary(summary)
    lines = [
        "# TBDY Minimal Live Product Report Package - C13.1",
        "",
        "## Scope warning",
        "",
        "This package is NOT full TBDY compliance.",
        "",
        f"full_tbdy_compliance_status: {truth.get('full_tbdy_compliance_status', 'NOT_EVALUATED')}",
        f"checked_scope_status: {truth.get('checked_scope_status')}",
        f"model_scope_status: {truth.get('model_scope_status')}",
        "",
        "The checked product scope is limited to the implemented live ETABS product slice: concrete rectangular beam/column geometry screening, modal mass participation reporting, object-scope accounting, and material/fck evidence reporting.",
        "Concrete material/fck evidence is evidence only; no fck adequacy or TBDY material sufficiency verdict is emitted.",
        "Unsupported or excluded frame objects are visible in the report and are not silently treated as checked TBDY compliance.",
        "Full object_scope_ledger.json is JSON-only and is not rendered into Markdown/HTML.",
        "Legacy booleans such as product_slice_passed and report_product_passed are product-slice compatibility signals only, not full-model or full-code compliance certificates.",
        "",
        "## Packaged deliverables",
        "",
    ]
    for name in PACKAGE_INPUT_FILES:
        lines.append(f"- {name}")
    lines.extend([
        "- package_manifest.json",
        "",
        "## Guardrails",
        "",
        "- No ETABS mutation",
        "- No analysis run",
        "- No design run",
        "- No Excel production input",
        "- No CheckEngine execution",
        "",
    ])
    return "\n".join(lines)


def write_report_package(report_dir: Path, report: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Write README, package manifest, and deterministic zip package."""
    report_dir = Path(report_dir)
    readme_path = report_dir / "README.md"
    readme_path.write_text(build_package_readme(report, summary), encoding="utf-8")

    packaged_report_files = _report_file_entries(report_dir, PACKAGE_INPUT_FILES)
    manifest = {
        "sprint_id": SPRINT_ID,
        "sprint_name": SPRINT_NAME,
        "generated_at": DETERMINISTIC_GENERATED_AT,
        "timestamp_policy": "No wall-clock timestamp is embedded so fixture/offline package output remains deterministic.",
        "source_report_directory": str(report_dir),
        "files": packaged_report_files,
        "truth_status_summary": _truth_status_from_summary(summary),
        "guardrail_metadata": _guardrail_metadata(report),
        "package_notes": {
            "full_tbdy_compliance_status_is_authoritative": "NOT_EVALUATED",
            "report_product_passed_is_legacy_product_slice_boolean": True,
            "full_object_ledger_is_json_only": True,
            "fck_adequacy_verdict_emitted": False,
        },
    }
    manifest_path = report_dir / "package_manifest.json"
    _write_json(manifest_path, manifest)

    zip_path = report_dir / "product_report_package.zip"
    if zip_path.exists():
        zip_path.unlink()
    zip_names = [entry["path"] for entry in packaged_report_files] + ["package_manifest.json"]
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for name in zip_names:
            path = report_dir / name
            info = ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return manifest
