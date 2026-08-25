"""Projection-only report adapter for the TS500 VS6 slenderness result."""
from __future__ import annotations

from tbdy_engine.design.columns.slenderness import ColumnSlendernessResult
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_slenderness_report(result: ColumnSlendernessResult) -> SliceReportContribution:
    if result.resolved:
        status = "PROVEN"
    elif result.status.startswith("BLOCKED"):
        status = "BLOCKED"
    else:
        # REQUIRES_MOMENT_MAGNIFICATION / GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED
        # are truthful engineering routing states, not compliance FAIL verdicts.
        status = "BLOCKED"

    rows = []
    for axis in (result.m2, result.m3):
        rows.append(
            {
                "axis": axis.axis,
                "status": axis.status,
                "sway_classification": axis.sway_classification,
                "section_dimension_mm": axis.section_dimension_mm,
                "free_length_ln_mm": axis.free_length_ln_mm,
                "effective_length_factor_k": axis.effective_length_factor_k,
                "effective_length_lk_mm": axis.effective_length_lk_mm,
                "radius_of_gyration_i_mm": axis.radius_of_gyration_i_mm,
                "slenderness_ratio_lk_over_i": axis.slenderness_ratio_lk_over_i,
                "moment_ratio_m1_over_m2": axis.moment_ratio_m1_over_m2,
                "neglect_limit": axis.neglect_limit,
                "source_refs": list(axis.source_refs),
            }
        )

    warnings = []
    if result.status == "BLOCKED_SLENDERNESS_BASIS":
        warnings.append(
            "TS500 regulatory free length / sway / effective-length basis is not yet promoted; factual ETABS clear-length candidates are not regulatory ln."
        )
    elif result.requires_moment_magnification:
        warnings.append(
            "TS500 7.6.2.3 neglect limit is exceeded in at least one direction; moment magnification must be applied before reinforcement authority."
        )
    elif result.status == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED":
        warnings.append(
            "TS500 approximate method scope is exceeded in at least one direction; general second-order analysis is required."
        )

    return SliceReportContribution(
        slice_id="VS6-P6-TS500-COLUMN-SLENDERNESS",
        title="TS500 Column Slenderness / Second-Order Basis",
        contribution_kind="CHECK_DETAIL",
        status=status,
        component_type="COLUMN",
        component_id=result.component_id,
        summary_fields=(
            ReportField("slenderness_status", "Slenderness closure status", result.status, role="STATUS"),
            ReportField("slenderness_authority", "Authority", result.authority, role="AUTHORITY"),
            ReportField("slenderness_resolved", "Current design moments complete for slenderness", result.resolved, role="STATUS"),
        ),
        detail_tables=(
            ReportTable(
                table_id="slenderness_axes",
                title="TS500 7.6 directional slenderness assessment",
                rows=tuple(rows),
            ),
        ),
        authority_refs=("TS500 7.6.1", "TS500 7.6.2.2", "TS500 7.6.2.3"),
        evidence_refs=result.source_refs,
        warnings=tuple(warnings),
    )


__all__ = ["build_vs6_slenderness_report"]
