"""Authority gate for VS6 ENGINE_SELECTED_REBAR.

The lower-level selection kernel is intentionally generic.  This wrapper is the
production authority boundary: raw ETABS Combination/LinRespSpec rows are not
accepted as design states.  Only demand states explicitly promoted by the VS6
design-demand reconstruction layer may reach ENGINE_SELECTED_REBAR.
"""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.design.columns.rebar_layout import ColumnRebarCandidatePopulation
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
    ColumnRebarSelectionResult,
    select_engine_rebar_for_demands,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial


AUTHORIZED_DESIGN_DEMAND_CASE_TYPES = frozenset(
    {
        "DesignStaticLinearExact",
        "DesignResponseSpectrumPermutation",
    }
)


def select_engine_rebar_from_authorized_demands(
    *,
    component_id: str,
    width_mm: float,
    depth_mm: float,
    population: ColumnRebarCandidatePopulation,
    material: ColumnSectionMaterial,
    demands: Sequence[ColumnDemandState],
    basis: ColumnDemandBasis,
    policy: ColumnRebarSelectionPolicy,
) -> ColumnRebarSelectionResult:
    demand_tuple = tuple(demands)
    if demand_tuple and any(
        item.case_type not in AUTHORIZED_DESIGN_DEMAND_CASE_TYPES for item in demand_tuple
    ):
        return ColumnRebarSelectionResult(
            component_id=component_id,
            status="BLOCKED_UNPROMOTED_DEMAND_STATES",
            authority="NOT_SELECTED",
            selected_candidate=None,
            required_as_in_candidate_family_mm2=None,
            governing_state_id=None,
            governing_utilization=None,
            trials=(),
            selected_evaluations=(),
            basis=basis,
        )
    return select_engine_rebar_for_demands(
        component_id=component_id,
        width_mm=width_mm,
        depth_mm=depth_mm,
        population=population,
        material=material,
        demands=demand_tuple,
        basis=basis,
        policy=policy,
    )


__all__ = [
    "AUTHORIZED_DESIGN_DEMAND_CASE_TYPES",
    "select_engine_rebar_from_authorized_demands",
]
