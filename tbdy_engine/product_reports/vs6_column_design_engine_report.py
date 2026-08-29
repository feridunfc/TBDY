"""Projection-only reporting for the integrated VS6 column design engine.

This module performs no engineering calculation. It projects the already
resolved demand-engine, minimum-eccentricity, stiffness-basis,
slenderness-basis/slenderness and longitudinal-rebar-engine results into the
common ``SliceReportContribution`` contract.
"""
from __future__ import annotations

from tbdy_engine.design.columns.column_design_engine import ColumnDesignEngineResult
from tbdy_engine.product_reports.slice_report_contribution import (
    ReportField,
    SliceReportContribution,
)
from tbdy_engine.product_reports.vs6_design_demand_report import build_vs6_design_demand_report
from tbdy_engine.product_reports.vs6_minimum_eccentricity_report import (
    build_vs6_minimum_eccentricity_report,
)
from tbdy_engine.product_reports.vs6_rebar_layout_report import build_vs6_rebar_layout_report
from tbdy_engine.product_reports.vs6_rebar_selection_report import build_vs6_rebar_selection_report
from tbdy_engine.product_reports.vs6_slenderness_basis_report import build_vs6_slenderness_basis_report
from tbdy_engine.product_reports.vs6_slenderness_report import build_vs6_slenderness_report
from tbdy_engine.product_reports.vs6_stability_stiffness_basis_report import (
    build_vs6_stability_stiffness_basis_report,
)


def build_vs6_column_design_engine_reports(
    result: ColumnDesignEngineResult,
    *,
    section_name: str,
) -> tuple[SliceReportContribution, ...]:
    """Project one canonical engine result to composite + detailed contributions."""
    demand = result.design_demands
    minimum_eccentricity = result.minimum_eccentricity
    stability_stiffness_basis = result.stability_stiffness_basis
    slenderness_basis = result.slenderness_basis
    slenderness = result.slenderness
    rebar = result.rebar_design
    selected = rebar.selection.selected_candidate if rebar.selection is not None else None

    if result.status == "SELECTED_DESIGN_CANDIDATE_ONLY":
        composite_status = "PARTIAL"
    elif result.status == "REANALYSIS_REQUIRED":
        composite_status = "REANALYSIS_REQUIRED"
    elif result.status.startswith("BLOCKED") or result.status in {
        "REQUIRES_MOMENT_MAGNIFICATION",
        "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED",
    }:
        composite_status = "BLOCKED"
    else:
        composite_status = "NO_DATA"

    warnings: list[str] = [
        "Legacy DESIGN_CANDIDATE_ONLY reinforcement is not ENGINE_SELECTED_REBAR, USER_PROVIDED_REBAR, or final/as-built reinforcement.",
        "Transverse reinforcement and final VS6 column shear compliance are outside this report slice.",
    ]
    if demand.blocked_combo_names:
        warnings.append(
            "One or more requested ETABS combination patterns are unsupported; full combination scope is blocked."
        )
    if not minimum_eccentricity.resolved:
        warnings.append("TS500 minimum-eccentricity closure is not resolved.")
    if result.status == "REANALYSIS_REQUIRED":
        warnings.append(
            "Current source-bound ETABS stiffness evidence requires a TS500 Eq.7.13-compatible uncracked reanalysis before that sway-proof route can authorize slenderness closure."
        )
    if not slenderness_basis.resolved:
        warnings.append(
            "TS500 regulatory ln/sway/effective-length basis is not fully promoted; factual clear-length candidates remain evidence only."
        )
    elif not slenderness.resolved:
        warnings.append(
            "TS500 slenderness closure is not complete for current design moments; reinforcement authority remains blocked."
        )

    summary = [
        ReportField("engine_status", "Integrated column design status", result.status, role="STATUS"),
        ReportField("section", "Section", section_name, role="IDENTITY"),
        ReportField("design_demand_status", "Design demand scope status", demand.status, role="STATUS"),
        ReportField("promoted_state_count", "Promoted P-M2-M3 states", len(demand.promoted_states), role="RESULT"),
        ReportField("blocked_combo_count", "Blocked combinations", len(demand.blocked_combo_names), role="STATUS"),
        ReportField(
            "minimum_eccentricity_status",
            "TS500 minimum eccentricity status",
            minimum_eccentricity.status,
            role="STATUS",
        ),
        ReportField(
            "post_eccentricity_state_count",
            "Post-eccentricity P-M2-M3 states",
            minimum_eccentricity.output_state_count,
            role="RESULT",
        ),
        ReportField(
            "stability_stiffness_basis_status",
            "TS500 Eq.7.13 stiffness-basis status",
            "NOT_EVALUATED" if stability_stiffness_basis is None else stability_stiffness_basis.status,
            role="STATUS",
        ),
        ReportField(
            "slenderness_basis_status",
            "TS500 slenderness basis promotion",
            slenderness_basis.status,
            role="STATUS",
        ),
        ReportField(
            "slenderness_status",
            "TS500 slenderness status",
            slenderness.status,
            role="STATUS",
        ),
        ReportField("rebar_design_status", "Longitudinal rebar design status", rebar.status, role="STATUS"),
        ReportField("rebar_authority", "Longitudinal rebar authority", rebar.authority, role="AUTHORITY"),
    ]
    if selected is not None:
        summary.extend(
            (
                ReportField("selected_candidate_id", "Selected reinforcement candidate", selected.candidate_id, role="RESULT"),
                ReportField("selected_bar_count", "Selected longitudinal bar count", selected.bar_count, role="RESULT"),
                ReportField("selected_bar_diameter_mm", "Selected longitudinal bar diameter", selected.bar_diameter_mm, unit="mm", role="RESULT"),
                ReportField("selected_as_total_mm2", "Selected total longitudinal As", selected.as_total_mm2, unit="mm2", role="RESULT"),
                ReportField("selected_rho_pct", "Selected longitudinal reinforcement ratio", selected.rho_pct, unit="%", role="RESULT"),
            )
        )

    contributions: list[SliceReportContribution] = [
        SliceReportContribution(
            slice_id="VS6-P4-P6-COLUMN-DESIGN-ENGINE",
            title="VS6 Integrated Column Demand and Legacy Rebar Candidate Trial",
            contribution_kind="COMPOSITE",
            status=composite_status,
            component_type="COLUMN",
            component_id=result.component_id,
            summary_fields=tuple(summary),
            authority_refs=(
                "TBDY 2018 7.3.2.1",
                "TS500 6.3.10",
                "TS500 7.1",
                "TS500 7.5",
                "TS500 7.6",
            ),
            warnings=tuple(warnings),
        )
    ]

    for combo in demand.combo_results:
        if combo.build is not None:
            contributions.append(
                build_vs6_design_demand_report(
                    combo.build,
                    verification=combo.verification,
                )
            )

    contributions.append(build_vs6_minimum_eccentricity_report(minimum_eccentricity))
    if stability_stiffness_basis is not None:
        contributions.append(
            build_vs6_stability_stiffness_basis_report(
                stability_stiffness_basis,
                component_id=result.component_id,
            )
        )
    contributions.append(build_vs6_slenderness_basis_report(slenderness_basis))
    contributions.append(build_vs6_slenderness_report(slenderness))

    if rebar.candidate_population is not None:
        contributions.append(
            build_vs6_rebar_layout_report(
                component_id=result.component_id,
                section_name=section_name,
                population=rebar.candidate_population,
            )
        )
    if rebar.selection is not None:
        contributions.append(build_vs6_rebar_selection_report(rebar.selection))

    return tuple(contributions)


__all__ = ["build_vs6_column_design_engine_reports"]
