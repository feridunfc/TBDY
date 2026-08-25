"""Projection-only report for TS500 slenderness-basis promotion."""
from __future__ import annotations

from tbdy_engine.design.columns.slenderness_basis import ColumnSlendernessBasisResolution
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    SliceReportContribution,
)


def build_vs6_slenderness_basis_report(
    result: ColumnSlendernessBasisResolution,
) -> SliceReportContribution:
    return SliceReportContribution(
        slice_id="VS6-P6-TS500-SLENDERNESS-BASIS",
        title="TS500 Column Slenderness Basis Promotion",
        contribution_kind="REGULATORY",
        status="PROVEN" if result.resolved else "BLOCKED",
        component_type="COLUMN",
        component_id=result.component_id,
        summary_fields=(
            ReportField("basis_status", "Slenderness basis status", result.status, role="STATUS"),
            ReportField("basis_authority", "Slenderness basis authority", result.authority, role="AUTHORITY"),
            ReportField("blocked_item_count", "Blocked basis items", len(result.blocked_items), role="STATUS"),
            ReportField(
                "derivation_note_count",
                "Source-bound conservative derivations",
                len(result.derivation_notes),
                role="NOTE",
            ),
        ),
        authority_refs=("TS500 7.6.2.1", "TS500 7.6.2.2", "TS500 7.6.2.3"),
        evidence_refs=result.source_refs,
        warnings=tuple((*result.blocked_items, *result.derivation_notes)),
    )


__all__ = ["build_vs6_slenderness_basis_report"]
