"""Truth-preserving combined product-scope verdict for P2.3."""
from __future__ import annotations

from typing import Any, Mapping

FULL_TBDY_COMPLIANCE_STATUS = "NOT_EVALUATED"


def geometry_product_status(executive_summary: Mapping[str, Any]) -> str:
    checked = executive_summary.get("checked_scope_status")
    if checked == "FAIL":
        return "FAIL"
    if checked == "NO_DATA":
        return "NO_DATA"
    if checked == "PASS":
        return "PASS"
    return "NO_DATA"


def guardrail_failed(report: Mapping[str, Any]) -> bool:
    metadata = report.get("metadata") if isinstance(report.get("metadata"), Mapping) else {}
    guardrails = report.get("guardrails") if isinstance(report.get("guardrails"), Mapping) else {}
    hard_flags = (
        metadata.get("etabs_model_mutated", False),
        metadata.get("analysis_run", False),
        metadata.get("design_run", False),
        metadata.get("check_engine_executed", False),
        guardrails.get("excel_production_path_used", False),
        guardrails.get("streamlit_ui_used", False),
        guardrails.get("legacy_runtime_used", False),
        guardrails.get("rebar_flexure_shear_capacity_unlocked", False),
    )
    return any(bool(flag) for flag in hard_flags)


def build_combined_product_scope_verdict(
    *,
    report: Mapping[str, Any],
    executive_summary: Mapping[str, Any],
    material_summary: Mapping[str, Any],
    object_scope_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply P2.3 status precedence without claiming full TBDY compliance."""
    geometry_status = geometry_product_status(executive_summary)
    material_status = str(material_summary.get("material_evidence_status") or "MISSING")
    unsupported_total = int(object_scope_summary.get("unsupported_object_count_total") or executive_summary.get("unsupported_object_count_total") or 0)
    excluded_total = int(object_scope_summary.get("excluded_frame_object_count_total") or executive_summary.get("excluded_frame_object_count_total") or 0)
    if guardrail_failed(report):
        combined = "FAIL"
        reason = "A product/report guardrail flag indicates forbidden execution or unsafe report generation."
    elif geometry_status == "FAIL":
        combined = "FAIL"
        reason = "Implemented geometry/modal checked scope has one or more failures."
    elif geometry_status == "NO_DATA":
        combined = "PARTIAL_EVIDENCE"
        reason = "Implemented checked scope could not be evaluated because required geometry/modal evidence is missing."
    elif material_status in {"PARTIAL", "MISSING"}:
        combined = "PARTIAL_EVIDENCE"
        reason = "Geometry scope passed, but checked concrete section material/fck evidence is partial or missing."
    elif unsupported_total > 0 or excluded_total > 0:
        combined = "PASS_WITH_EXCLUSIONS"
        reason = "Implemented checked scope passed and material evidence resolved, but unsupported/excluded model content exists."
    else:
        combined = "PASS"
        reason = "Implemented checked scope passed, material evidence resolved, and no unsupported/excluded frame content was reported."
    return {
        "geometry_product_status": geometry_status,
        "material_evidence_status": material_status,
        "combined_product_scope_status": combined,
        "full_tbdy_compliance_status": FULL_TBDY_COMPLIANCE_STATUS,
        "unsupported_object_count_total": unsupported_total,
        "excluded_frame_object_count_total": excluded_total,
        "combined_product_scope_reason": reason,
    }
