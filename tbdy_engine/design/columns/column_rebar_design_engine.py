"""Canonical VS6 longitudinal-reinforcement design orchestration.

The engine consumes already-promoted column design demand states plus factual
project bar-catalog evidence and explicit reviewed detailing/material inputs.
It delegates candidate generation and section capacity to the pure kernels and
is the only production path in this slice allowed to emit ENGINE_SELECTED_REBAR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.rebar_catalog import RebarCatalog
from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarCandidatePopulation,
    ColumnRebarLayoutInputs,
    generate_rectangular_column_rebar_candidates,
)
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
    ColumnRebarSelectionResult,
)
from tbdy_engine.design.columns.rebar_selection_authority import (
    select_engine_rebar_from_authorized_demands,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial


@dataclass(frozen=True, slots=True)
class ColumnRebarDesignInputs:
    component_id: str
    width_mm: float
    depth_mm: float
    clear_cover_mm: float
    tie_diameter_mm: float
    aggregate_max_mm: float
    material: ColumnSectionMaterial
    demand_basis: ColumnDemandBasis
    selection_policy: ColumnRebarSelectionPolicy


@dataclass(frozen=True, slots=True)
class ColumnRebarDesignResult:
    component_id: str
    status: str
    catalog_status: str
    candidate_population: ColumnRebarCandidatePopulation | None
    selection: ColumnRebarSelectionResult | None
    excluded_catalog_bar_names: tuple[str, ...]

    @property
    def authority(self) -> str:
        if self.selection is None:
            return "NOT_SELECTED"
        return self.selection.authority


class ColumnRebarDesignEngineError(ValueError):
    """Raised when factual/reviewed inputs cannot support a deterministic design."""


def design_column_longitudinal_rebar(
    *,
    inputs: ColumnRebarDesignInputs,
    rebar_catalog: RebarCatalog,
    promoted_demands: Sequence[ColumnDemandState],
) -> ColumnRebarDesignResult:
    """Select the smallest feasible candidate satisfying every promoted demand.

    No hard-coded bar library is used.  Bars below the TBDY column longitudinal
    minimum remain visible as factual catalog exclusions and are never passed to
    the candidate kernel.
    """
    if rebar_catalog.status != "PROVEN_FACTUAL_REBAR_CATALOG":
        return ColumnRebarDesignResult(
            component_id=inputs.component_id,
            status="BLOCKED_REBAR_CATALOG",
            catalog_status=rebar_catalog.status,
            candidate_population=None,
            selection=None,
            excluded_catalog_bar_names=(),
        )

    allowed = rebar_catalog.column_longitudinal_diameters_mm
    excluded = tuple(item.name for item in rebar_catalog.excluded_below_column_minimum)
    if not allowed:
        return ColumnRebarDesignResult(
            component_id=inputs.component_id,
            status="NO_ELIGIBLE_COLUMN_BAR_SIZES",
            catalog_status=rebar_catalog.status,
            candidate_population=None,
            selection=None,
            excluded_catalog_bar_names=excluded,
        )

    population = generate_rectangular_column_rebar_candidates(
        ColumnRebarLayoutInputs(
            width_mm=inputs.width_mm,
            depth_mm=inputs.depth_mm,
            clear_cover_mm=inputs.clear_cover_mm,
            tie_diameter_mm=inputs.tie_diameter_mm,
            aggregate_max_mm=inputs.aggregate_max_mm,
            allowed_bar_diameters_mm=allowed,
        )
    )
    selection = select_engine_rebar_from_authorized_demands(
        component_id=inputs.component_id,
        width_mm=inputs.width_mm,
        depth_mm=inputs.depth_mm,
        population=population,
        material=inputs.material,
        demands=tuple(promoted_demands),
        basis=inputs.demand_basis,
        policy=inputs.selection_policy,
    )
    if selection.authority == "ENGINE_SELECTED_REBAR":
        status = "SELECTED_ENGINE_REBAR"
    elif selection.status.startswith("BLOCKED"):
        status = selection.status
    else:
        status = selection.status
    return ColumnRebarDesignResult(
        component_id=inputs.component_id,
        status=status,
        catalog_status=rebar_catalog.status,
        candidate_population=population,
        selection=selection,
        excluded_catalog_bar_names=excluded,
    )


__all__ = [
    "ColumnRebarDesignEngineError",
    "ColumnRebarDesignInputs",
    "ColumnRebarDesignResult",
    "design_column_longitudinal_rebar",
]
