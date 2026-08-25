"""Projection-only report adapter for VS6-P6 ENGINE_SELECTED_REBAR."""
from __future__ import annotations

from tbdy_engine.design.columns.rebar_selection import ColumnRebarSelectionResult
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_rebar_selection_report(result: ColumnRebarSelectionResult) -> SliceReportContribution:
    selected = result.selected_candidate
    report_status = "PROVEN" if result.status == "SELECTED" else ("BLOCKED" if result.status.startswith("BLOCKED") else "NO_DATA")
    trial_rows = tuple(
        {
            "candidate_id": item.candidate_id,
            "as_total_mm2": item.as_total_mm2,
            "status": item.status,
            "max_utilization": item.max_utilization,
            "governing_state_id": item.governing_state_id,
            "evaluated_state_count": item.evaluated_state_count,
        }
        for item in result.trials
    )
    evaluation_rows = tuple(
        {
            "state_id": item.state.state_id,
            "output_case": item.state.output_case,
            "end_tag": item.state.end_tag,
            "step_type": item.state.step_type,
            "station_m": item.state.station_m,
            "nd_compression_n": item.state.nd_compression_n,
            "m2_nmm": item.state.m2_nmm,
            "m3_nmm": item.state.m3_nmm,
            "radial_capacity_nmm": item.radial_capacity_nmm,
            "utilization": item.utilization,
            "status": item.status,
        }
        for item in result.selected_evaluations
    )
    summary = [
        ReportField("selection_status", "Selection status", result.status, role="STATUS"),
        ReportField("authority", "Rebar authority", result.authority, role="AUTHORITY"),
        ReportField("governing_state_id", "Governing demand state", result.governing_state_id, role="RESULT"),
        ReportField("governing_utilization", "Governing utilization", result.governing_utilization, role="RESULT"),
    ]
    if selected is not None:
        summary.extend(
            (
                ReportField("candidate_id", "Selected candidate", selected.candidate_id, role="RESULT"),
                ReportField("bar_count", "Longitudinal bar count", selected.bar_count, role="RESULT"),
                ReportField("bar_diameter_mm", "Longitudinal bar diameter", selected.bar_diameter_mm, unit="mm", role="RESULT"),
                ReportField("as_total_mm2", "Selected As", selected.as_total_mm2, unit="mm2", role="RESULT"),
                ReportField("rho_pct", "Selected reinforcement ratio", selected.rho_pct, unit="%", role="RESULT"),
                ReportField(
                    "required_as_candidate_family_mm2",
                    "Required As within reviewed candidate family",
                    result.required_as_in_candidate_family_mm2,
                    unit="mm2",
                    role="RESULT",
                ),
            )
        )
    return SliceReportContribution(
        slice_id="VS6-P6-COLUMN-REBAR-SELECTION",
        title="VS6 Column Longitudinal Reinforcement Selection",
        contribution_kind="DESIGN",
        status=report_status,
        component_type="COLUMN",
        component_id=result.component_id,
        summary_fields=tuple(summary),
        tables=(
            ReportTable(
                table_id="vs6_column_rebar_candidate_trials",
                title="Candidate selection trials",
                columns=(
                    "candidate_id",
                    "as_total_mm2",
                    "status",
                    "max_utilization",
                    "governing_state_id",
                    "evaluated_state_count",
                ),
                rows=trial_rows,
                purpose="SELECTION_TRACE",
            ),
            ReportTable(
                table_id="vs6_column_rebar_selected_demand_checks",
                title="Selected candidate demand-capacity evaluations",
                columns=(
                    "state_id",
                    "output_case",
                    "end_tag",
                    "step_type",
                    "station_m",
                    "nd_compression_n",
                    "m2_nmm",
                    "m3_nmm",
                    "radial_capacity_nmm",
                    "utilization",
                    "status",
                ),
                rows=evaluation_rows,
                purpose="ENGINEERING_CALCULATION_DETAIL",
            ),
        ),
        authority_refs=("TBDY 2018 7.3.2.1", "TS500 7.1", "TS500 7.5"),
        warnings=(
            "ENGINE_SELECTED_REBAR is a design-selection authority; it is not USER_PROVIDED_REBAR or as-built reinforcement.",
            "Transverse reinforcement and final VS6 shear compliance are outside this slice.",
        ),
    )


__all__ = ["build_vs6_rebar_selection_report"]
