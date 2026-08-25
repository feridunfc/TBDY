"""Projection-only reporting for VS6 column design-demand reconstruction."""
from __future__ import annotations

from tbdy_engine.design.columns.design_demand_states import (
    ComboDesignDemandBuild,
    ComboObservedSubsetVerification,
)
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_design_demand_report(
    build: ComboDesignDemandBuild,
    *,
    verification: ComboObservedSubsetVerification | None = None,
) -> SliceReportContribution:
    state_rows = tuple(
        {
            "state_id": item.state_id,
            "combo": item.output_case,
            "case_type": item.case_type,
            "end_tag": item.end_tag,
            "step_type": item.step_type,
            "station_m": item.station_m,
            "nd_compression_kn": item.nd_compression_n / 1000.0,
            "m2_knm": item.m2_nmm / 1_000_000.0,
            "m3_knm": item.m3_nmm / 1_000_000.0,
            "source_identity": item.source_identity,
        }
        for item in build.states
    )
    end_rows = tuple(
        {
            "end_tag": item.end_tag,
            "station_m": item.station_m,
            "static_nd_compression_kn": item.static_nd_compression_n / 1000.0,
            "static_m2_knm": item.static_m2_nmm / 1_000_000.0,
            "static_m3_knm": item.static_m3_nmm / 1_000_000.0,
            "spectrum_nd_magnitude_kn": item.spectrum_nd_magnitude_n / 1000.0,
            "spectrum_m2_magnitude_knm": item.spectrum_m2_magnitude_nmm / 1_000_000.0,
            "spectrum_m3_magnitude_knm": item.spectrum_m3_magnitude_nmm / 1_000_000.0,
            "static_cases": ",".join(item.static_case_names),
            "response_spectrum_cases": ",".join(item.response_spectrum_case_names),
        }
        for item in build.end_summaries
    )

    summary = [
        ReportField("build_status", "Design demand build status", build.status, role="STATUS"),
        ReportField("authority", "Design demand authority", build.authority, role="AUTHORITY"),
        ReportField("combo_name", "Combination", build.combo_name, role="SOURCE"),
        ReportField("state_count", "Generated design states", len(build.states), role="RESULT"),
    ]
    warnings = [
        "Raw ETABS response-spectrum combination Max/Min rows are not promoted directly to concurrent P-M2-M3 states.",
        "Response-spectrum P, M2 and M3 sign correspondence is treated through explicit design sign permutations.",
    ]
    if verification is not None:
        summary.extend(
            (
                ReportField("observed_subset_status", "Observed ETABS combo-row subset proof", verification.status, role="STATUS"),
                ReportField("observed_state_count", "Observed combo rows", verification.observed_state_count, role="EVIDENCE"),
                ReportField("matched_state_count", "Matched generated states", verification.matched_state_count, role="EVIDENCE"),
            )
        )
        if verification.unmatched_observed_state_ids:
            warnings.append("One or more observed ETABS combo rows were not reproduced by the generated design-state set.")

    return SliceReportContribution(
        slice_id="VS6-P6-COLUMN-DESIGN-DEMAND-STATES",
        title="VS6 Column P-M2-M3 Design Demand States",
        contribution_kind="DESIGN",
        status="PROVEN" if build.status == "PROVEN_DESIGN_DEMAND_STATES" else "BLOCKED",
        component_type="COLUMN",
        component_id=build.component_id,
        summary_fields=tuple(summary),
        tables=(
            ReportTable(
                table_id="vs6_design_demand_end_summary",
                title="Static base and response-spectrum component magnitudes",
                columns=(
                    "end_tag",
                    "station_m",
                    "static_nd_compression_kn",
                    "static_m2_knm",
                    "static_m3_knm",
                    "spectrum_nd_magnitude_kn",
                    "spectrum_m2_magnitude_knm",
                    "spectrum_m3_magnitude_knm",
                    "static_cases",
                    "response_spectrum_cases",
                ),
                rows=end_rows,
                purpose="ENGINEERING_CALCULATION_DETAIL",
            ),
            ReportTable(
                table_id="vs6_design_demand_states",
                title="Generated P-M2-M3 design states",
                columns=(
                    "state_id",
                    "combo",
                    "case_type",
                    "end_tag",
                    "step_type",
                    "station_m",
                    "nd_compression_kn",
                    "m2_knm",
                    "m3_knm",
                    "source_identity",
                ),
                rows=state_rows,
                purpose="DESIGN_DEMAND_TRACE",
            ),
        ),
        authority_refs=tuple(build.behavior_refs),
        warnings=tuple(warnings),
    )


__all__ = ["build_vs6_design_demand_report"]
