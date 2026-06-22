"""C14.1-P1 deterministic report-row aggregation."""
from __future__ import annotations
from collections import defaultdict
from tbdy_engine.product._minimum_compliance_checks import _clear_span_candidate
from tbdy_engine.product._minimum_compliance_summary import _unsupported_rows
from tbdy_engine.product._minimum_compliance_util import (
    _STATUS_PRIORITY, _feature_value, _identity, _section, _finite, _ratio,
    _worst_status, _evidence_tables, _detail_row, _diagnostic_summary,
    _section_overall,
)
def _build_report_tables(*, inventory, classifications, snapshots, check_records, diagnostics, connectivity, offsets, unit_evidence):
    results_by_component = defaultdict(list)
    for record in check_records:
        results_by_component[str(record.get("component", ""))].append(record)
    snapshots_by_section = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_section[(str(snapshot.get("component_type", "")), _section(snapshot) or "")].append(snapshot)
    beam_rows, column_rows, detail_rows = [], [], []
    for (element, section_name), grouped in sorted(snapshots_by_section.items()):
        component_ids = sorted(str(item.get("component_id")) for item in grouped)
        section_results = [row for component in component_ids for row in results_by_component.get(component, ())]
        first = grouped[0]
        material = _identity(first, "assigned_material_name")
        stories = sorted({_identity(item, "story") for item in grouped if _identity(item, "story") is not None})
        evidence_tables = sorted(_evidence_tables(section_results))
        check_ids = {str(row.get("check_id")) for row in section_results}
        statuses = {cid: _worst_status(str(row.get("result_status") or row.get("status")) for row in section_results if row.get("check_id") == cid) for cid in check_ids}
        trigger_rows = [row for row in section_results if row.get("pass_rule") == "detailing_trigger"]
        trigger_status = _worst_status(str(row.get("result_status") or row.get("status")) for row in trigger_rows) if trigger_rows else None
        trigger_reasons = sorted({str(row.get("messages", [""])[0]) for row in trigger_rows})
        if element == "beam":
            candidates = [_clear_span_candidate(component, connectivity, offsets, unit_evidence) for component in component_ids]
            candidates = [item for item in candidates if item and _finite(item.get("candidate_clear_span_mm"))]
            centerlines = [float(item["centerline_length_mm"]) for item in candidates]
            spans = [float(item["candidate_clear_span_mm"]) for item in candidates]
            beam_rows.append({
                "section": section_name, "material": material, "assigned_beam_count": len(grouped), "stories": stories,
                "width_mm": _feature_value(first, "beam_width_mm"), "width_limit_mm": 250.0, "width_status": statuses.get("beam_geometry_min_width"),
                "absolute_depth_value_mm": _feature_value(first, "beam_depth_mm"), "absolute_depth_limit_mm": 300.0, "absolute_depth_status": statuses.get("beam_geometry_min_depth_absolute"),
                "slab_thickness_mm": None, "three_times_slab_thickness_mm": None, "depth_vs_slab_status": statuses.get("beam_geometry_depth_ge_three_times_slab_thickness"),
                "depth_width_ratio": _ratio(_feature_value(first, "beam_depth_mm"), _feature_value(first, "beam_width_mm")), "depth_width_limit": 3.5, "depth_width_status": statuses.get("beam_depth_width_ratio"),
                "centerline_length_min_mm": min(centerlines) if centerlines else None, "centerline_length_max_mm": max(centerlines) if centerlines else None,
                "clear_span_mm": spans[0] if spans and len(set(spans)) == 1 else None,
                "clear_span_candidate_min_mm": min(spans) if spans else None, "clear_span_candidate_max_mm": max(spans) if spans else None,
                "web_detailing_trigger_status": trigger_status, "web_detailing_trigger_reason": "; ".join(trigger_reasons),
                "span_depth_status": statuses.get("beam_span_depth_ratio"),
                "fck_mpa": _feature_value(first, "concrete_fck_mpa"), "fck_limit_mpa": 25.0, "material_status": statuses.get("beam_material_min_concrete_strength"),
                "overall_status": _section_overall(section_results), "evidence_tables": evidence_tables,
            })
        elif element == "column":
            width, depth = _feature_value(first, "column_width_mm"), _feature_value(first, "column_depth_mm")
            resolved = _finite(width) and _finite(depth)
            column_rows.append({
                "section": section_name, "material": material, "assigned_column_count": len(grouped), "stories": stories,
                "width_mm": width, "depth_mm": depth,
                "minimum_dimension_mm": min(float(width), float(depth)) if resolved else None, "minimum_dimension_limit_mm": 300.0, "minimum_dimension_status": statuses.get("column_geometry_min_dimension"),
                "area_mm2": float(width) * float(depth) if resolved else None, "area_limit_mm2": 75000.0, "area_status": statuses.get("column_geometry_min_area"),
                "aspect_ratio": _ratio(min(float(width), float(depth)), max(float(width), float(depth))) if resolved else None, "aspect_ratio_limit": 0.40, "aspect_ratio_status": statuses.get("column_geometry_aspect_ratio"),
                "fck_mpa": _feature_value(first, "concrete_fck_mpa"), "fck_limit_mpa": 25.0, "material_status": statuses.get("column_material_min_concrete_strength"),
                "overall_status": _section_overall(section_results), "evidence_tables": evidence_tables,
            })
        for cid in sorted(check_ids):
            rows = [row for row in section_results if row.get("check_id") == cid]
            representative = max(rows, key=lambda row: _STATUS_PRIORITY.get(str(row.get("status")), 0))
            detail_rows.append(_detail_row(element, section_name, material, representative))
    guardrails = [{"metric": key, "value": value} for key, value in (
        ("live_etabs_source_used", True), ("excel_production_input_used", False),
        ("legacy_runtime_used", False), ("section_name_parsing_used", False),
        ("material_name_strength_inference_used", False), ("direct_api_primary_source_used", False),
        ("default_row_truncation_used", False), ("checks_executed", True),
    )]
    boundaries = [
        {"topic": "beam_depth_vs_slab", "note": "BLOCKED until explicit beam-slab adjacency and thickness evidence are implemented."},
        {"topic": "beam_web_detailing_trigger", "note": "BLOCKED when a Length/Offset candidate exists but clear-span semantics are not locked; NO_DATA only when candidate values are absent."},
        {"topic": "material_minimum_strength", "note": "25 MPa remains BLOCKED because an exact TBDY clause is not locked."},
        {"topic": "engineering_failure", "note": "BLOCKED, NO_DATA, OUT_OF_SCOPE, REQUIRED, and NOT_REQUIRED do not count as engineering FAIL."},
    ]
    return {
        "executive_summary": [], "beam_section_checks": beam_rows,
        "unsupported_beam_sections": _unsupported_rows(classifications, "beam"),
        "column_section_checks": column_rows,
        "unsupported_column_sections": _unsupported_rows(classifications, "column"),
        "check_detail": detail_rows, "diagnostic_summary": _diagnostic_summary(diagnostics),
        "guardrails": guardrails, "boundary_notes": boundaries,
    }
__all__ = ["_build_report_tables"]
