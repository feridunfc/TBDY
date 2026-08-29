"""Integrated production engine for the current VS6 column design slice.

The engine composes source-bound combination classification/design-demand
promotion, TS500 minimum-eccentricity closure, strict TS500 slenderness-basis
promotion, TS500 slenderness closure, and the longitudinal-reinforcement design
engine. Combination scope, minimum eccentricity and slenderness are derived by
the engine; callers cannot authorize them by merely setting demand-basis flags.

The current slenderness path is intentionally conservative: factual ETABS clear-
length candidates are never promoted to regulatory ``ln`` automatically. If a
valid TS500 basis is promoted but the 7.6.2.3 neglect limit is exceeded, rebar
authority remains blocked until the required moment-magnification/second-order
path is available.

When the active sway-proof route still lacks a promoted sway classification and
source-bound stiffness evidence proves that the current ETABS model is
incompatible with the TS500 7.6.2.1 Eq.7.13 uncracked-section requirement, the
canonical engine emits ``REANALYSIS_REQUIRED`` instead of hiding that action
behind a generic slenderness-basis blocker. A separately promoted complete
slenderness basis remains authoritative and is not overridden by an Eq.7.13-
specific stiffness assessment.

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
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessBasis,
    ColumnSlendernessResult,
    evaluate_ts500_column_slenderness,
)
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessBasisResolution,
    ColumnSlendernessEvidence,
    resolve_ts500_column_slenderness_basis,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    StabilityStiffnessBasisResolution,
)


@dataclass(frozen=True, slots=True)
class ColumnDesignEngineResult:
    component_id: str
    status: str
    design_demands: ColumnDesignDemandEngineResult
    minimum_eccentricity: ColumnMinimumEccentricityResult
    slenderness_basis: ColumnSlendernessBasisResolution
    slenderness: ColumnSlendernessResult
    rebar_design: ColumnRebarDesignResult
    stability_stiffness_basis: StabilityStiffnessBasisResolution | None = None


class ColumnDesignEngineError(ValueError):
    """Raised when the integrated engine inputs are inconsistent."""


def _basis_with_engine_closures(
    basis: ColumnDemandBasis,
    *,
    combination_scope_resolved: bool,
    minimum_eccentricity_resolved: bool,
    slenderness_resolved: bool,
    reanalysis_required: bool,
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
        (
            "TS500_7.6_SLENDERNESS:RESOLVED"
            if slenderness_resolved
            else "TS500_7.6_SLENDERNESS:BLOCKED"
        ),
    )
    for ref in closure_refs:
        if ref not in refs:
            refs.append(ref)
    if reanalysis_required:
        ref = "TS500_7.6.2.1_STIFFNESS_BASIS:REANALYSIS_REQUIRED"
        if ref not in refs:
            refs.append(ref)
    return ColumnDemandBasis(
        analysis_order_status=basis.analysis_order_status,
        minimum_eccentricity_status="RESOLVED" if minimum_eccentricity_resolved else "BLOCKED",
        slenderness_status="RESOLVED" if slenderness_resolved else "BLOCKED",
        combination_scope_status="RESOLVED" if combination_scope_resolved else "BLOCKED",
        review_refs=tuple(refs),
    )


def _prepromoted_resolution(
    component_id: str,
    basis: ColumnSlendernessBasis,
) -> ColumnSlendernessBasisResolution:
    if basis.component_id != component_id:
        raise ColumnDesignEngineError("slenderness_basis.component_id differs from component_id")
    refs = tuple(dict.fromkeys((*basis.source_refs, *basis.m2.source_refs, *basis.m3.source_refs)))
    return ColumnSlendernessBasisResolution(
        component_id=component_id,
        status="PROVEN_TS500_SLENDERNESS_BASIS",
        basis=basis,
        blocked_items=(),
        derivation_notes=("Canonical pre-promoted TS500 slenderness basis supplied to pure engine",),
        source_refs=refs,
    )


def evaluate_column_design(
    *,
    component_id: str,
    combo_definitions: Sequence[ColumnComboDefinition],
    constituent_case_demands: Sequence[ColumnDemandState],
    rebar_catalog: RebarCatalog,
    rebar_inputs: ColumnRebarDesignInputs,
    slenderness_evidence: ColumnSlendernessEvidence | None = None,
    slenderness_basis: ColumnSlendernessBasis | None = None,
    stability_stiffness_basis: StabilityStiffnessBasisResolution | None = None,
    observed_combo_demands: Sequence[ColumnDemandState] = (),
    verify_observed_rows: bool = False,
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ColumnDesignEngineResult:
    """Evaluate current VS6 demand + TS500 closures + rebar authority.

    Production adapters should prefer ``slenderness_evidence`` so the strict
    promotion boundary is visible in the canonical result. ``slenderness_basis``
    remains accepted for already-promoted internal/replay fixtures; supplying
    both is rejected.

    ``stability_stiffness_basis`` is a source-bound assessment of the current
    model for the TS500 Eq.7.13 sway-proof route. It can require reanalysis only
    while sway classification is still unpromoted; it cannot invalidate a
    separately completed canonical slenderness basis.
    """
    if rebar_inputs.component_id != component_id:
        raise ColumnDesignEngineError("rebar_inputs.component_id differs from component_id")
    if slenderness_evidence is not None and slenderness_basis is not None:
        raise ColumnDesignEngineError("supply slenderness_evidence or slenderness_basis, not both")

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

    if slenderness_basis is not None:
        slenderness_basis_resolution = _prepromoted_resolution(component_id, slenderness_basis)
    else:
        slenderness_basis_resolution = resolve_ts500_column_slenderness_basis(
            slenderness_evidence,
            component_id=component_id,
        )
    slenderness = evaluate_ts500_column_slenderness(
        component_id=component_id,
        basis=slenderness_basis_resolution.basis,
    )

    sway_not_promoted = any(
        item.endswith(":SWAY_CLASSIFICATION_NOT_PROMOTED")
        for item in slenderness_basis_resolution.blocked_items
    )
    reanalysis_required = bool(
        stability_stiffness_basis is not None
        and stability_stiffness_basis.reanalysis_required
        and sway_not_promoted
    )
    authoritative_basis = _basis_with_engine_closures(
        rebar_inputs.demand_basis,
        combination_scope_resolved=demand_result.combination_scope_resolved,
        minimum_eccentricity_resolved=minimum_eccentricity.resolved,
        slenderness_resolved=slenderness.resolved and not reanalysis_required,
        reanalysis_required=reanalysis_required,
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
    elif reanalysis_required:
        status = "REANALYSIS_REQUIRED"
    elif not slenderness_basis_resolution.resolved:
        status = "BLOCKED_SLENDERNESS_BASIS"
    elif slenderness.requires_moment_magnification:
        status = "REQUIRES_MOMENT_MAGNIFICATION"
    elif slenderness.status == "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED":
        status = "GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED"
    elif not slenderness.resolved:
        status = "BLOCKED_SLENDERNESS_BASIS"
    elif rebar_result.status.startswith("BLOCKED"):
        status = rebar_result.status
    else:
        status = rebar_result.status

    return ColumnDesignEngineResult(
        component_id=component_id,
        status=status,
        design_demands=demand_result,
        minimum_eccentricity=minimum_eccentricity,
        slenderness_basis=slenderness_basis_resolution,
        slenderness=slenderness,
        rebar_design=rebar_result,
        stability_stiffness_basis=stability_stiffness_basis,
    )


__all__ = [
    "ColumnDesignEngineError",
    "ColumnDesignEngineResult",
    "evaluate_column_design",
]
