"""Projection-only report for TS500 6.3.10 column minimum eccentricity."""
from __future__ import annotations

from tbdy_engine.design.columns.minimum_eccentricity import ColumnMinimumEccentricityResult
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_minimum_eccentricity_report(
    result: ColumnMinimumEccentricityResult,
) -> SliceReportContribution:
    rows = tuple(
        {
            "source_state_id": item.source_state_id,
            "nd_compression_kn": item.nd_compression_n / 1000.0,
            "emin_for_m2_mm": item.emin_for_m2_mm,
            "emin_for_m3_mm": item.emin_for_m3_mm,
            "required_abs_m2_knm": item.required_abs_m2_nmm / 1_000_000.0,
            "required_abs_m3_knm": item.required_abs_m3_nmm / 1_000_000.0,
            "original_m2_knm": item.original_m2_nmm / 1_000_000.0,
            "original_m3_knm": item.original_m3_nmm / 1_000_000.0,
            "m2_adjusted": item.m2_adjusted,
            "m3_adjusted": item.m3_adjusted,
            "generated_state_count": len(item.generated_state_ids),
            "application_status": item.application_status,
        }
        for item in result.adjustments
    )
    return SliceReportContribution(
        slice_id="VS6-P6-TS500-MINIMUM-ECCENTRICITY",
        title="TS500 Column Minimum Eccentricity Closure",
        contribution_kind="DESIGN",
        status="PROVEN" if result.resolved else "BLOCKED",
        component_type="COLUMN",
        component_id=result.component_id,
        summary_fields=(
            ReportField("status", "Minimum eccentricity status", result.status, role="STATUS"),
            ReportField("authority", "Authority", result.authority, role="AUTHORITY"),
            ReportField("input_state_count", "Input design states", result.input_state_count, role="INPUT"),
            ReportField("output_state_count", "Post-eccentricity design states", result.output_state_count, role="RESULT"),
            ReportField(
                "adjusted_source_state_count",
                "Source states requiring moment floor",
                result.adjusted_source_state_count,
                role="RESULT",
            ),
            ReportField(
                "sign_branch_source_state_count",
                "Source states requiring zero-moment sign branching",
                result.sign_branch_source_state_count,
                role="RESULT",
            ),
        ),
        tables=(
            ReportTable(
                table_id="vs6_ts500_minimum_eccentricity",
                title="TS500 6.3.10 directional minimum eccentricity trace",
                columns=(
                    "source_state_id",
                    "nd_compression_kn",
                    "emin_for_m2_mm",
                    "emin_for_m3_mm",
                    "required_abs_m2_knm",
                    "required_abs_m3_knm",
                    "original_m2_knm",
                    "original_m3_knm",
                    "m2_adjusted",
                    "m3_adjusted",
                    "generated_state_count",
                    "application_status",
                ),
                rows=rows,
                purpose="ENGINEERING_CALCULATION_DETAIL",
            ),
        ),
        authority_refs=("TS500 6.3.10 Eq. 6.16",),
        evidence_refs=result.source_refs,
        warnings=(
            "For zero moment in a required compression direction, both minimum-eccentricity signs are retained; no imperfection sign is invented.",
            "M2 uses the local-3/depth bending-plane dimension and M3 uses the local-2/width bending-plane dimension.",
        ),
    )


__all__ = ["build_vs6_minimum_eccentricity_report"]
