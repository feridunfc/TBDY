"""Projection-only report adapter for TS500 7.6.2.1 stability-index sway proof."""
from __future__ import annotations

from tbdy_engine.design.columns.sway_stability import StorySwayStabilityResolution
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    ReportTable,
    SliceReportContribution,
)


_COLUMNS = (
    "load_basis",
    "phi",
    "limit",
    "status",
    "source_refs",
)


def build_vs6_sway_stability_report(
    result: StorySwayStabilityResolution,
) -> SliceReportContribution:
    status = "PROVEN" if result.proves_sway_prevented else "BLOCKED"
    rows = tuple(
        {
            "load_basis": item.load_basis,
            "phi": item.phi,
            "limit": item.limit,
            "status": item.status,
            "source_refs": " | ".join(item.source_refs),
        }
        for item in result.load_results
    )
    warnings: list[str] = []
    if result.missing_load_bases:
        warnings.append(
            "TS500 7.6.2.1 stability-index proof is incomplete because one or more prescribed load bases are missing."
        )
    elif not result.proves_sway_prevented:
        warnings.append(
            "The stability-index route did not prove sway-prevented behavior; this is not a proof of sway-permitted behavior and another TS500 proof route may still govern."
        )

    return SliceReportContribution(
        slice_id="VS6-P6-TS500-STORY-SWAY-STABILITY",
        title="TS500 Storey Sway Stability-Index Proof",
        contribution_kind="CHECK",
        status=status,
        component_type="STORY",
        component_id=f"{result.story}:{result.direction}",
        summary_fields=(
            ReportField("story", "Story", result.story, role="IDENTITY"),
            ReportField("direction", "Direction", result.direction, role="IDENTITY"),
            ReportField("sway_stability_status", "Sway proof status", result.status, role="STATUS"),
            ReportField("governing_phi", "Governing stability index phi", result.governing_phi, role="RESULT"),
            ReportField("governing_load_basis", "Governing load basis", result.governing_load_basis, role="RESULT"),
            ReportField("authority", "Authority", result.authority, role="AUTHORITY"),
        ),
        tables=(
            ReportTable(
                table_id="sway_stability_load_bases",
                title="TS500 7.6.2.1 Eq.7.13 load-basis evaluations",
                columns=_COLUMNS,
                rows=rows,
            ),
        ),
        authority_refs=("TS500 7.6.2.1", "TS500 Eq.7.13"),
        evidence_refs=result.source_refs,
        warnings=tuple(warnings),
    )


__all__ = ["build_vs6_sway_stability_report"]
