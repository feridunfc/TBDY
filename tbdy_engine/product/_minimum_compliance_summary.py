"""C14.1-P1 summary, manifest, failure-bundle, and selector helpers."""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
import yaml
from tbdy_engine.reports.minimum_compliance_tabular_report import write_minimum_compliance_tabular_report
from tbdy_engine.product._minimum_compliance_util import _text, _write_json
_SCOPE = "C14_1_P1_LIVE_BEAM_COLUMN_MINIMUM_COMPLIANCE"
_COMPONENT_TABLE = "Frame Assignments - Summary"
_ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
_SECTION_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
_MATERIAL_TABLE = "Material Properties - Concrete Data"
_CONNECTIVITY_TABLE = "Beam Object Connectivity"
_OFFSET_TABLE = "Frame Assignments - End Length Offsets"
_CATALOG = Path(__file__).resolve().parents[1] / "catalogs" / "check_catalog_c14_1_p1_minimum_compliance.yaml"
_REPORT_FILES = ("minimum_compliance_report.md", "executive_summary.csv", "beam_section_checks.csv", "unsupported_beam_sections.csv", "column_section_checks.csv", "unsupported_column_sections.csv", "check_detail.csv", "diagnostic_summary.csv", "guardrails.csv", "boundary_notes.csv")
_ARTIFACT_FILES = ("enriched_feature_snapshots.json", "check_results.json", "adapter_diagnostics.json", "product_summary.json", "product_manifest.json")
def _summary(tables: Mapping[str, list[dict[str, object]]], inventory: Sequence[Mapping[str, object]], classifications: Sequence[Mapping[str, object]], check_records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    fail_records = [row for row in check_records if row.get("status") == "FAIL"]
    executable_records = [row for row in check_records if row.get("status") in {"OK", "FAIL"}]
    blocked_count = sum(row.get("status") == "BLOCKED" for row in check_records)
    no_data_count = sum(row.get("status") == "NO_DATA" for row in check_records)
    out_scope_count = sum(item.get("status") == "OUT_OF_SCOPE" for item in classifications)
    required_count = sum(row.get("result_status") == "REQUIRED" for row in check_records)
    not_required_count = sum(row.get("result_status") == "NOT_REQUIRED" for row in check_records)
    coverage_partial = bool(blocked_count or no_data_count or out_scope_count or not executable_records or any(item.get("status") != "SUPPORTED" for item in classifications))
    engineering_status = "FAIL" if fail_records else "OK" if executable_records else "NO_DATA"
    coverage_status = "PARTIAL" if coverage_partial else "COMPLETE"
    product_status = "FAIL" if fail_records else "PARTIAL" if coverage_partial else "OK"
    supported = [item for item in classifications if item.get("status") == "SUPPORTED"]
    metrics = {
        "engineering_status": engineering_status, "engineering_fail": bool(fail_records),
        "coverage_status": coverage_status, "product_status": product_status,
        "beam_assignment_count": sum(item.get("raw_type") == "Beam" for item in inventory),
        "supported_concrete_beam_count": sum(item.get("element_type") == "beam" for item in supported),
        "unsupported_beam_count": sum(item.get("element_type") == "beam" and item.get("status") != "SUPPORTED" for item in classifications),
        "concrete_beam_section_type_count": len({item.get("section") for item in supported if item.get("element_type") == "beam"}),
        "column_assignment_count": sum(item.get("raw_type") == "Column" for item in inventory),
        "supported_concrete_column_count": sum(item.get("element_type") == "column" for item in supported),
        "unsupported_column_count": sum(item.get("element_type") == "column" and item.get("status") != "SUPPORTED" for item in classifications),
        "concrete_column_section_type_count": len({item.get("section") for item in supported if item.get("element_type") == "column"}),
        "beam_check_result_count": sum(row.get("component_type") == "beam" and row.get("check_id") != "minimum_compliance_scope" for row in check_records),
        "column_check_result_count": sum(row.get("component_type") == "column" and row.get("check_id") != "minimum_compliance_scope" for row in check_records),
        "geometry_fail_count": sum(row.get("status") == "FAIL" and "material" not in str(row.get("check_id")) for row in check_records),
        "material_fail_count": sum(row.get("status") == "FAIL" and "material" in str(row.get("check_id")) for row in check_records),
        "blocked_check_count": blocked_count, "no_data_check_count": no_data_count,
        "detailing_required_count": required_count, "detailing_not_required_count": not_required_count,
        "out_of_scope_object_count": out_scope_count, "total_fail_count": len(fail_records),
    }
    tables["executive_summary"] = [{"metric": key, "value": value} for key, value in metrics.items()]
    return metrics
def _manifest(root: Path, selectors: Mapping[str, object], summary: Mapping[str, object]) -> dict[str, object]:
    return {"scope": _SCOPE, "runner": "C14.1-P1 Live Beam and Column Minimum Compliance", "selectors": dict(selectors), "production_source_tables": [_COMPONENT_TABLE, _ASSIGNMENT_TABLE, _SECTION_TABLE, _MATERIAL_TABLE, _CONNECTIVITY_TABLE, _OFFSET_TABLE], "output_files": sorted([f"report/{name}" for name in _REPORT_FILES] + [f"artifacts/{name}" for name in _ARTIFACT_FILES]), "guardrails": {"live_etabs_source_used": True, "excel_production_input_used": False, "legacy_runtime_used": False, "section_name_parsing_used": False, "material_name_strength_inference_used": False, "direct_api_primary_source_used": False, "default_row_truncation_used": False, "checks_executed": True}, "summary": dict(summary), "output_root": "."}
def _write_failure_bundle(root: Path, report_dir: Path, artifact_dir: Path, selectors: Mapping[str, object], error: Exception) -> Mapping[str, object]:
    diagnostic = {"status": "BLOCKED", "code": "ETABS_ATTACH_OR_SOURCE_FAILURE", "message": str(error), "affected_element_type": None, "sample_component_ids": [], "sample_sections": []}
    summary = {"engineering_status": "NO_DATA", "engineering_fail": False, "coverage_status": "PARTIAL", "product_status": "FAIL", "beam_assignment_count": 0, "column_assignment_count": 0, "blocked_check_count": 0, "no_data_check_count": 0, "detailing_required_count": 0, "detailing_not_required_count": 0, "out_of_scope_object_count": 0, "total_fail_count": 0, "failure_stage": "COM_ATTACH_OR_SOURCE", "error_type": type(error).__name__, "error_message": str(error)}
    tables = {"executive_summary": [{"metric": key, "value": value} for key, value in summary.items()], "beam_section_checks": [], "unsupported_beam_sections": [], "column_section_checks": [], "unsupported_column_sections": [], "check_detail": [], "diagnostic_summary": [diagnostic], "guardrails": [], "boundary_notes": []}
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_dir / "enriched_feature_snapshots.json", {"snapshots": []})
    _write_json(artifact_dir / "check_results.json", [])
    _write_json(artifact_dir / "adapter_diagnostics.json", [diagnostic])
    _write_json(artifact_dir / "product_summary.json", summary)
    _write_json(artifact_dir / "product_manifest.json", _manifest(root, selectors, summary))
    write_minimum_compliance_tabular_report(output_dir=report_dir, tables=tables)
    return summary
def _load_catalog() -> dict[str, Mapping[str, Any]]:
    payload = yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))
    checks = payload.get("checks", {}) if isinstance(payload, Mapping) else {}
    return {str(key): {**dict(value), "code_ref": value.get("tbdy_ref")} for key, value in checks.items() if isinstance(value, Mapping)}
def _filter_snapshots(rows: Sequence[Mapping[str, object]], element_type: str | None, story: str | None, section: str | None) -> list[dict[str, object]]:
    output = []
    for row in rows:
        identity = row.get("identity") if isinstance(row.get("identity"), Mapping) else {}
        if element_type and str(row.get("component_type", "")).casefold() != element_type: continue
        if story is not None and _text(identity.get("story")) != story: continue
        if section is not None and _text(identity.get("section")) != section: continue
        output.append(dict(row))
    return output
def _unsupported_rows(classifications: Sequence[Mapping[str, object]], element_type: str) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for item in classifications:
        if item.get("element_type") == element_type and item.get("status") != "SUPPORTED":
            key = (_text(item.get("section")) or "<missing>", _text(item.get("section_family")) or "<unknown>", _text(item.get("reason")))
            grouped[key].append(item)
    rows = []
    count_key = "assigned_beam_count" if element_type == "beam" else "assigned_column_count"
    for (section, family, reason), items in sorted(grouped.items()):
        rows.append({"section": section, "section_family": family, count_key: len(items), "stories": sorted({_text(item.get("story")) for item in items if _text(item.get("story"))}), "sample_labels": sorted({_text(item.get("label")) for item in items if _text(item.get("label"))})[:5], "sample_unique_names": sorted({_text(item.get("unique_name")) for item in items})[:5], "reason": reason, "coverage_impact": "PARTIAL"})
    return rows
__all__ = ["_summary", "_manifest", "_write_failure_bundle", "_load_catalog", "_filter_snapshots", "_unsupported_rows"]
