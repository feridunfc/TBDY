"""Report projection for VS6 longitudinal rebar candidate populations."""
from __future__ import annotations

from tbdy_engine.design.columns.rebar_layout import ColumnRebarCandidatePopulation
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_rebar_layout_report(
    *,
    component_id: str,
    section_name: str,
    population: ColumnRebarCandidatePopulation,
) -> SliceReportContribution:
    inputs = population.inputs
    rows = tuple(
        {
            "candidate_id": item.candidate_id,
            "bar_count": item.bar_count,
            "bar_diameter_mm": item.bar_diameter_mm,
            "as_total_mm2": item.as_total_mm2,
            "rho_pct": item.rho_pct,
            "n_bars_dir2": item.n_bars_dir2,
            "n_bars_dir3": item.n_bars_dir3,
            "min_clear_spacing_mm": item.min_clear_spacing_mm,
            "required_min_clear_spacing_mm": item.required_min_clear_spacing_mm,
            "authority": item.authority,
        }
        for item in population.candidates
    )
    return SliceReportContribution(
        slice_id="VS6-P4-COLUMN-REBAR-CANDIDATES",
        title="VS6 Column Longitudinal Rebar Candidate Population",
        contribution_kind="DESIGN",
        status="PROVEN" if population.status == "PROVEN" else "BLOCKED",
        component_type="COLUMN",
        component_id=component_id,
        summary_fields=(
            ReportField("section", "Section", section_name, role="IDENTITY"),
            ReportField("width_mm", "Width", inputs.width_mm, unit="mm", role="INPUT"),
            ReportField("depth_mm", "Depth", inputs.depth_mm, unit="mm", role="INPUT"),
            ReportField("clear_cover_mm", "Reviewed clear cover", inputs.clear_cover_mm, unit="mm", role="INPUT"),
            ReportField("tie_diameter_mm", "Reviewed tie diameter", inputs.tie_diameter_mm, unit="mm", role="INPUT"),
            ReportField("aggregate_max_mm", "Reviewed maximum aggregate", inputs.aggregate_max_mm, unit="mm", role="INPUT"),
            ReportField("candidate_count", "Candidate count", len(population.candidates), role="RESULT"),
            ReportField("authority", "Authority", population.authority, role="AUTHORITY"),
        ),
        tables=(
            ReportTable(
                table_id="vs6_column_rebar_candidates",
                title="Eligible rectangular perimeter layouts",
                columns=(
                    "candidate_id",
                    "bar_count",
                    "bar_diameter_mm",
                    "as_total_mm2",
                    "rho_pct",
                    "n_bars_dir2",
                    "n_bars_dir3",
                    "min_clear_spacing_mm",
                    "required_min_clear_spacing_mm",
                    "authority",
                ),
                rows=rows,
                purpose="DESIGN_CANDIDATE_POPULATION",
            ),
        ),
        authority_refs=("TBDY 2018 7.3.2.1", "TS500 7.4.1", "TS500 9.5.2"),
        warnings=(
            "Candidate layouts are not ENGINE_SELECTED_REBAR.",
            "Tie-leg/crosstie support adequacy is not inferred in this slice.",
        ),
    )


__all__ = ["build_vs6_rebar_layout_report"]
