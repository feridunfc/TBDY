"""Projection-only report for TS500 7.6.2.1 stiffness-basis assessment.

This module performs no engineering calculation. It projects the canonical
``StabilityStiffnessBasisResolution`` already produced by the design layer.
"""
from __future__ import annotations

from tbdy_engine.design.columns.stability_stiffness_basis import (
    StabilityStiffnessBasisResolution,
)
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_stability_stiffness_basis_report(
    resolution: StabilityStiffnessBasisResolution,
    *,
    component_id: str | None = None,
) -> SliceReportContribution:
    """Project the canonical stiffness-basis resolution without recalculation."""
    report_status = "REANALYSIS_REQUIRED" if resolution.reanalysis_required else "BLOCKED"
    rows = tuple(
        {
            "member_kind": item.member_kind,
            "section_name": item.section_name,
            "i2_modifier": item.i2_modifier,
            "i3_modifier": item.i3_modifier,
            "authority": item.authority,
        }
        for item in resolution.nonunit_sections
    )
    tables = ()
    if rows:
        tables = (
            ReportTable(
                table_id="nonunit_assigned_rc_sections",
                title="Assigned RC frame sections incompatible with unit gross bending stiffness",
                columns=(
                    "member_kind",
                    "section_name",
                    "i2_modifier",
                    "i3_modifier",
                    "authority",
                ),
                rows=rows,
                purpose="AUDIT_EVIDENCE",
            ),
        )

    warnings = [
        "This contribution projects an already-resolved analysis-basis decision; it does not recalculate stiffness or sway.",
        "A positive global UNCRACKED basis cannot be inferred from RC-frame modifiers alone.",
    ]
    if resolution.reanalysis_required:
        warnings.append(
            "The current ETABS assigned RC-frame bending modifiers are incompatible with the TS500 Eq.7.13 uncracked-section route; a compatible reanalysis basis is required before that sway-proof route can be authorized."
        )

    return SliceReportContribution(
        slice_id="VS6-P6-TS500-STABILITY-STIFFNESS-BASIS",
        title="TS500 7.6.2.1 Stability Stiffness Basis",
        contribution_kind="REGULATORY",
        status=report_status,
        component_type="COLUMN" if component_id is not None else "MODEL",
        component_id=component_id,
        summary_fields=(
            ReportField("source_status", "Stiffness-basis resolution", resolution.status, role="STATUS"),
            ReportField("reanalysis_required", "Reanalysis required", resolution.reanalysis_required, role="STATUS"),
            ReportField("inspected_section_count", "Inspected assigned RC sections", resolution.inspected_section_count, role="RESULT"),
            ReportField("inspected_member_kinds", "Inspected member kinds", ",".join(resolution.inspected_member_kinds), role="RESULT"),
            ReportField("nonunit_section_count", "Non-unit assigned RC sections", len(resolution.nonunit_sections), role="RESULT"),
            ReportField("authority", "Decision authority", resolution.authority, role="AUTHORITY"),
        ),
        tables=tables,
        authority_refs=("TS500 7.6.2.1 Eq.7.13",),
        evidence_refs=resolution.source_refs,
        warnings=tuple(warnings),
    )


__all__ = ["build_vs6_stability_stiffness_basis_report"]
