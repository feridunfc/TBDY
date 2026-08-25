"""Projection-only report adapter for VS6-P5 column capacity envelopes."""
from __future__ import annotations

from tbdy_engine.design.columns.section_capacity import ColumnInteractionEnvelope
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_section_capacity_report(
    *,
    component_id: str,
    candidate_id: str,
    envelope: ColumnInteractionEnvelope,
) -> SliceReportContribution:
    rows = tuple(
        {
            "neutral_axis_angle_deg": state.neutral_axis_angle_deg,
            "neutral_axis_depth_c_mm": state.neutral_axis_depth_c_mm,
            "block_depth_a_mm": state.block_depth_a_mm,
            "n_compression_n": state.n_compression_n,
            "m2_nmm": state.m2_nmm,
            "m3_nmm": state.m3_nmm,
            "concrete_force_n": state.concrete_force_n,
            "steel_force_n": state.steel_force_n,
        }
        for state in envelope.states
    )
    status = "PROVEN" if envelope.status == "PROVEN" else "BLOCKED"
    return SliceReportContribution(
        slice_id="VS6-P5-COLUMN-SECTION-CAPACITY",
        title="VS6 Column N-M2-M3 Capacity Envelope",
        contribution_kind="DESIGN",
        status=status,
        component_type="COLUMN",
        component_id=component_id,
        summary_fields=(
            ReportField("candidate_id", "Rebar candidate", candidate_id, role="IDENTITY"),
            ReportField("target_n", "Target compression force", envelope.target_n_compression_n, unit="N", role="INPUT"),
            ReportField("sample_count", "Capacity sample count", len(envelope.states), role="RESULT"),
            ReportField("angle_step_deg", "Neutral-axis angle step", envelope.angle_step_deg, unit="deg", role="INPUT"),
            ReportField("authority", "Authority", envelope.authority, role="AUTHORITY"),
        ),
        tables=(
            ReportTable(
                table_id="vs6_column_capacity_envelope",
                title="Resolved N-M2-M3 capacity states",
                columns=(
                    "neutral_axis_angle_deg",
                    "neutral_axis_depth_c_mm",
                    "block_depth_a_mm",
                    "n_compression_n",
                    "m2_nmm",
                    "m3_nmm",
                    "concrete_force_n",
                    "steel_force_n",
                ),
                rows=rows,
                purpose="CAPACITY_ENVELOPE",
            ),
        ),
        authority_refs=("TS500 7.1", "TS500 7.5", "TS500 Table 7.1"),
        warnings=(
            "This slice resolves section capacity only; it does not select design demand or emit compliance.",
            "Live/project acceptance of the numerical kernel remains a separate gate.",
        ),
    )


__all__ = ["build_vs6_section_capacity_report"]
