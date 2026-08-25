"""Integrated production engine for the current VS6 column design slice.

The engine composes source-bound combination classification/design-demand
promotion, TS500 minimum-eccentricity closure, and the longitudinal-reinforcement
design engine.  Combination scope and minimum eccentricity are derived by the
engine; callers cannot authorize them by merely setting demand-basis flags.

ETABS acquisition remains outside this pure orchestration layer.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from tbdy_engine.design.columns.column_design_demand_engine import (
    ColumnComboDefinition,
    ColumnDesignDemandEngineResult,
    evaluate_column_design_demands,
)
from tbdy_engine.design.columns.column_rebar_design_engine import (
    ColumnRebarDesignInputs,
    ColumnRebarDesignResult,
    design_column_longitudinal_rebar,
)
from tbdy_engine.design.columns.minimum_eccentricity import (
    ColumnMinimumEccentricityResult,
    apply_ts500_minimum_eccentricity,
)
from tbdy_engine.design.columns.rebar_catalog import RebarCatalog
from tbdy_engine.design.columns.rebar_selection import ColumnDemandBasis, ColumnDemandState


@dataclass(frozen=True, slots=True)
class ColumnDesignEngineResult:
    component_id: str
    status: str
    design_demands: ColumnDesignDemandEngineResult
    minimum_eccentricity: ColumnMinimumEccentricityResult
    rebar_design: ColumnRebarDesignResult


class ColumnDesignEngineError(ValueError):
    """Raised when the integrated engine inputs are inconsistent."""


def _basis_with_engine_closures(
    basis: ColumnDemandBasis,
    *,
    combination_scope_resolved: bool,
    minimum_eccentricity_resolved: bool,
) -> ColumnDemandBasis:
    refs = list(basis.review_refs)
    closure_refs = (
        (
            "VS6_COLUMN_DESIGN_DEMAND_ENGINE:COMBINATION_SCOPE_RESOLVED"
            if combination_scope_resolved
            else "VS6_COLUMN_DESIGN_DEMAND_ENGINE:COMBINATION_SCOPE_BLOCKED"
        ),
        (
            "TS500_6.3.10_MINIMUM_ECCENTRICITY:RESOLVED"
            if minimum_eccentricity_resolved
            else "TS500_6.3.10_MINIMUM_ECCENTRICITY:BLOCKED"
        ),
    )
    for ref in closure_refs:
        if ref not in refs:
            refs.append(ref)
    return ColumnDemandBasis(
        analysis_order_status=basis.analysis_order_status,
        minimum_eccentricity_status="RESOLVED" if minimum_eccentricity_resolved else "BLOCKED",
        slenderness_status=basis.slenderness_status,
        combination_scope_status="RESOLVED" if combination_scope_resolved else "BLOCKED",
        review_refs=tuple(refs),
    )


def evaluate_column_design(
    *,
    component_id: str,
    combo_definitions: Sequence[ColumnComboDefinition],
    constituent_case_demands: Sequence[ColumnDemandState],
    rebar_catalog: RebarCatalog,
    rebar_inputs: ColumnRebarDesignInputs,
    observed_combo_demands: Sequence[ColumnDemandState] = (),
    verify_observed_rows: bool = False,
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ColumnDesignEngineResult:
    """Evaluate current VS6 demand + minimum eccentricity + rebar authority."""
    if rebar_inputs.component_id != component_id:
        raise ColumnDesignEngineError("rebar_inputs.component_id differs from component_id")

    demand_result = evaluate_column_design_demands(
        component_id=component_id,
        definitions=combo_definitions,
        case_demands=constituent_case_demands,
        observed_combo_demands=observed_combo_demands,
        verify_observed_rows=verify_observed_rows,
        force_tolerance_n=force_tolerance_n,
        moment_tolerance_nmm=moment_tolerance_nmm,
    )

    minimum_eccentricity = apply_ts500_minimum_eccentricity(
        component_id=component_id,
        width_mm=rebar_inputs.width_mm,
        depth_mm=rebar_inputs.depth_mm,
        demands=demand_result.promoted_states,
        source_refs=("TS500 6.3.10 Eq. 6.16",),
    )

    authoritative_basis = _basis_with_engine_closures(
        rebar_inputs.demand_basis,
        combination_scope_resolved=demand_result.combination_scope_resolved,
        minimum_eccentricity_resolved=minimum_eccentricity.resolved,
    )
    bound_rebar_inputs = replace(rebar_inputs, demand_basis=authoritative_basis)
    rebar_result = design_column_longitudinal_rebar(
        inputs=bound_rebar_inputs,
        rebar_catalog=rebar_catalog,
        promoted_demands=minimum_eccentricity.states,
    )

    if not demand_result.combination_scope_resolved:
        status = "BLOCKED_COMBINATION_SCOPE"
    elif not minimum_eccentricity.resolved:
        status = "BLOCKED_MINIMUM_ECCENTRICITY"
    elif rebar_result.authority == "ENGINE_SELECTED_REBAR":
        status = "SELECTED_ENGINE_REBAR"
    elif rebar_result.status.startswith("BLOCKED"):
        status = rebar_result.status
    else:
        status = rebar_result.status

    return ColumnDesignEngineResult(
        component_id=component_id,
        status=status,
        design_demands=demand_result,
        minimum_eccentricity=minimum_eccentricity,
        rebar_design=rebar_result,
    )


__all__ = [
    "ColumnDesignEngineError",
    "ColumnDesignEngineResult",
    "evaluate_column_design",
]
