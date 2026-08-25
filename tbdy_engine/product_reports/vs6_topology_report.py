"""Report projection for the VS6 strict factual topology slice.

This adapter performs presentation-only projection from StrictColumnTopologyBundle.
It does not promote the factual clear-length candidate to regulatory l_n and does
not calculate reinforcement, moment capacity, shear capacity, or compliance.
"""
from __future__ import annotations

from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


def build_vs6_topology_report_contribution(
    topology: StrictColumnTopologyBundle,
) -> SliceReportContribution:
    summary = topology.summary()

    column_rows: list[dict[str, object]] = []
    attachment_rows: list[dict[str, object]] = []
    for column in topology.columns:
        column_rows.append(
            {
                "component_id": column.component_id,
                "story": column.story,
                "column": column.column_label,
                "unique_name": column.unique_name,
                "section": column.section,
                "object_length_m": column.object_length_m,
                "coordinate_length_m": column.coordinate_length_m,
                "offset_bottom_m": column.offset_bottom_m,
                "offset_top_m": column.offset_top_m,
                "analysis_clear_length_candidate_m": column.analysis_clear_length_candidate_m,
                "regulatory_ln_status": "NOT_PROMOTED_FROM_FACTUAL_CANDIDATE",
                "top_attachment_count": len(column.beams_at_top),
                "bottom_attachment_count": len(column.beams_at_bottom),
                "unsupported_attachment_count": (
                    len(column.unsupported_beams_at_top) + len(column.unsupported_beams_at_bottom)
                ),
            }
        )
        for end_name, attachments in (
            ("BOTTOM", column.beams_at_bottom),
            ("TOP", column.beams_at_top),
        ):
            for beam in attachments:
                attachment_rows.append(
                    {
                        "component_id": column.component_id,
                        "column_end": end_name,
                        "joint_unique_name": beam.joint_unique_name,
                        "beam_unique_name": beam.beam_unique_name,
                        "beam_label": beam.beam_label,
                        "connected_end": beam.connected_end,
                        "shape": beam.shape,
                        "section": beam.section,
                        "supported_rc_beam": beam.is_supported_rc_beam,
                        "horizontal_azimuth_deg": beam.horizontal_azimuth_deg,
                    }
                )

    warnings: tuple[str, ...] = ()
    if int(summary["columns_with_unsupported_beam_attachments"]) > 0:
        warnings = (
            "Some RC-column joints contain non-RC beam attachments; later RC beam-capacity logic requires explicit scope classification.",
        )

    return SliceReportContribution(
        slice_id="VS6_STRICT_COLUMN_TOPOLOGY",
        title="VS6 Strict RC Column Topology Evidence",
        contribution_kind="FACTUAL",
        status="PROVEN",
        component_type="RC_COLUMN_POPULATION",
        summary_fields=(
            ReportField("source_status", "Topology source status", str(summary["status"]), role="STATUS"),
            ReportField("column_count", "RC column count", int(summary["column_count"]), role="RESULT"),
            ReportField("beam_count", "Beam object count", int(summary["beam_count"]), role="RESULT"),
            ReportField(
                "supported_rc_beam_count",
                "Supported RC beam count",
                int(summary["supported_rc_beam_count"]),
                role="RESULT",
            ),
            ReportField(
                "unsupported_beam_count",
                "Unsupported beam count",
                int(summary["unsupported_beam_count"]),
                role="RESULT",
            ),
            ReportField(
                "columns_with_unsupported_beam_attachments",
                "Columns with unsupported beam attachments",
                int(summary["columns_with_unsupported_beam_attachments"]),
                role="STATUS",
            ),
            ReportField(
                "analysis_clear_length_candidate_min_m",
                "Minimum factual clear-length candidate",
                float(summary["analysis_clear_length_candidate_min_m"]),
                unit="m",
                role="RESULT",
                note="Factual ETABS geometry candidate only; not regulatory l_n.",
            ),
            ReportField(
                "analysis_clear_length_candidate_max_m",
                "Maximum factual clear-length candidate",
                float(summary["analysis_clear_length_candidate_max_m"]),
                unit="m",
                role="RESULT",
                note="Factual ETABS geometry candidate only; not regulatory l_n.",
            ),
            ReportField(
                "regulatory_ln_status",
                "Regulatory l_n status",
                str(summary["regulatory_ln_status"]),
                role="STATUS",
            ),
            ReportField("heuristics_used", "Heuristics used", bool(summary["heuristics_used"]), role="STATUS"),
        ),
        tables=(
            ReportTable(
                table_id="vs6_column_topology_population",
                title="RC Column Topology Population",
                columns=(
                    "component_id",
                    "story",
                    "column",
                    "unique_name",
                    "section",
                    "object_length_m",
                    "coordinate_length_m",
                    "offset_bottom_m",
                    "offset_top_m",
                    "analysis_clear_length_candidate_m",
                    "regulatory_ln_status",
                    "top_attachment_count",
                    "bottom_attachment_count",
                    "unsupported_attachment_count",
                ),
                rows=tuple(column_rows),
                purpose="ENGINEERING_DETAIL",
            ),
            ReportTable(
                table_id="vs6_column_joint_beam_attachments",
                title="Column-Joint-Beam Attachments",
                columns=(
                    "component_id",
                    "column_end",
                    "joint_unique_name",
                    "beam_unique_name",
                    "beam_label",
                    "connected_end",
                    "shape",
                    "section",
                    "supported_rc_beam",
                    "horizontal_azimuth_deg",
                ),
                rows=tuple(attachment_rows),
                purpose="ENGINEERING_DETAIL",
            ),
        ),
        warnings=warnings,
        render_views=("EXECUTIVE", "ENGINEERING", "AUDIT"),
    )


__all__ = ["build_vs6_topology_report_contribution"]
