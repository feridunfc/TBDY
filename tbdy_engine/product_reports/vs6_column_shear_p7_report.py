"""Projection-only VS6-P7 column shear report contributions."""
from __future__ import annotations

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.product_reports.slice_report_contribution import ReportField, SliceReportContribution
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from tbdy_engine.regulatory.vs6_column_shear_p7_program import VS6P7ColumnShearRun, VS6P7DirectionRun


def _status(run: VS6P7DirectionRun) -> str:
    if run.analysis_basis_status is AnalysisBasisStatus.REANALYSIS_REQUIRED:
        return "REANALYSIS_REQUIRED"
    results = (run.tbdy_brittle_result, run.ts500_web_result)
    if any(item is not None and item.status is CheckStatus.FAIL for item in results):
        return "FAIL"
    if any(item is not None and item.status is CheckStatus.NO_DATA for item in results):
        return "NO_DATA"
    if any(item is None or item.status is CheckStatus.BLOCKED for item in results):
        return "BLOCKED"
    # Even when both bounded upper checks are OK, Ve<=Vr is deliberately P8.
    return "PARTIAL"


def build_vs6_p7_column_shear_reports(run: VS6P7ColumnShearRun) -> tuple[SliceReportContribution, ...]:
    if not isinstance(run, VS6P7ColumnShearRun):
        raise TypeError("run must be VS6P7ColumnShearRun")
    out: list[SliceReportContribution] = []
    for direction in run.directions:
        tbdy = direction.tbdy_brittle_result
        ts500 = direction.ts500_web_result
        fields = [
            ReportField("direction", "Local shear direction", direction.direction, role="IDENTITY"),
            ReportField("Ve_n", "TBDY design shear Ve", direction.ve_n, unit="N", role="RESULT"),
            ReportField("tbdy_vd_n", "TBDY Vd floor demand", direction.tbdy_vd.demand_n, unit="N", role="INPUT"),
            ReportField("ts500_vd_n", "TS500 Vd demand", direction.ts500_vd.demand_n, unit="N", role="INPUT"),
            ReportField("bottom_capacity_status", "Bottom end moment-capacity basis", direction.bottom_capacity.status, role="STATUS"),
            ReportField("top_capacity_status", "Top end moment-capacity basis", direction.top_capacity.status, role="STATUS"),
            ReportField("effective_depth_status", "TS500 effective-depth basis", direction.effective_depth.status, role="STATUS"),
            ReportField("effective_depth_d_mm", "TS500 effective depth d", direction.effective_depth.effective_depth_d_mm, unit="mm", role="RESULT"),
            ReportField("vr_closure", "Full Ve <= Vr closure", direction.full_vr_closure_status.value, role="STATUS"),
            ReportField("analysis_basis_status", "Analysis-basis consequence", direction.analysis_basis_status.value, role="STATUS"),
        ]
        if tbdy is not None:
            fields.extend((
                ReportField("tbdy_upper_status", "TBDY Eq.7.7 brittle upper-bound", tbdy.status.value, role="STATUS"),
                ReportField("tbdy_upper_limit_n", "TBDY brittle upper-bound limit", tbdy.limit, unit=tbdy.unit, role="LIMIT"),
                ReportField("tbdy_upper_ratio", "TBDY demand/capacity ratio", tbdy.ratio, role="RESULT"),
            ))
        if ts500 is not None:
            fields.extend((
                ReportField("ts500_upper_status", "TS500 Eq.8.7 web-compression bound", ts500.status.value, role="STATUS"),
                ReportField("ts500_upper_limit_n", "TS500 web-compression limit", ts500.limit, unit=ts500.unit, role="LIMIT"),
                ReportField("ts500_upper_ratio", "TS500 demand/capacity ratio", ts500.ratio, role="RESULT"),
            ))
        out.append(
            SliceReportContribution(
                slice_id=f"VS6-P7-COLUMN-SHEAR-{direction.direction}",
                title=f"VS6-P7 Column Shear — {direction.direction}",
                contribution_kind="CHECK",
                status=_status(direction),
                component_type="COLUMN",
                component_id=direction.component_id,
                summary_fields=tuple(fields),
                authority_refs=("TBDY 2018 7.3.7", "TS 500 8.1.5(b)"),
                evidence_refs=(
                    f"ETABS:{direction.tbdy_vd.source_identity}",
                    f"ETABS:{direction.ts500_vd.source_identity}",
                ),
                warnings=(
                    "Full Ve <= Vr transverse-reinforcement resistance closure is deferred to VS6-P8.",
                ),
            )
        )
    return tuple(out)


__all__ = ["build_vs6_p7_column_shear_reports"]
