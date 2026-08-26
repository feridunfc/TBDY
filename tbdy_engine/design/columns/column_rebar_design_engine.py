"""Canonical VS6 longitudinal-reinforcement design orchestration.

The engine consumes already-promoted column design demand states plus factual
project bar-catalog evidence and explicit reviewed detailing/material inputs.
It delegates candidate generation and section capacity to the pure kernels and
is the only production path in this slice allowed to emit ENGINE_SELECTED_REBAR.

VS6-P8A adds a role-preserving optional required-area gate. ETABS_REQUIRED_REBAR
is factual design evidence only; it is combined with the already accepted TBDY
minimum as GOVERNING_REQUIRED_REBAR before candidate search. Selection and
N-M2-M3 capacity authority remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.design.columns.rebar_catalog import RebarCatalog
from tbdy_engine.design.columns.rebar_layout import (
    TBDY_COLUMN_RHO_MIN,
    ColumnRebarCandidatePopulation,
    ColumnRebarLayoutInputs,
    generate_rectangular_column_rebar_candidates,
)
from tbdy_engine.design.columns.rebar_requirement import (
    GoverningRequiredRebar,
    build_governing_required_rebar,
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
from tbdy_engine.features.column_design_rebar_evidence import EtabsRequiredRebar


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
    section_identity: str | None = None
    preferred_bar_diameter_mm: float | None = None
    candidate_preference_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateAreaGateTrial:
    candidate_id: str
    as_total_mm2: float
    required_as_mm2: float
    status: str


@dataclass(frozen=True, slots=True)
class ColumnRebarDesignResult:
    component_id: str
    status: str
    catalog_status: str
    candidate_population: ColumnRebarCandidatePopulation | None
    selection: ColumnRebarSelectionResult | None
    excluded_catalog_bar_names: tuple[str, ...]
    governing_required_rebar: GoverningRequiredRebar | None = None
    area_gate_trials: tuple[CandidateAreaGateTrial, ...] = ()
    candidate_preference_refs: tuple[str, ...] = ()

    @property
    def authority(self) -> str:
        if self.selection is None:
            return "NOT_SELECTED"
        return self.selection.authority


class ColumnRebarDesignEngineError(ValueError):
    pass


def _blocked_result(*, inputs: ColumnRebarDesignInputs, catalog_status: str, status: str, excluded: tuple[str, ...] = (), population: ColumnRebarCandidatePopulation | None = None, requirement: GoverningRequiredRebar | None = None, area_trials: tuple[CandidateAreaGateTrial, ...] = ()) -> ColumnRebarDesignResult:
    return ColumnRebarDesignResult(inputs.component_id, status, catalog_status, population, None, excluded, requirement, area_trials, tuple(inputs.candidate_preference_refs))


def _preference_refs(inputs: ColumnRebarDesignInputs) -> tuple[str, ...] | None:
    refs = tuple(inputs.candidate_preference_refs)
    if any(not isinstance(ref, str) or not ref.strip() or ref != ref.strip() for ref in refs) or len(refs) != len(set(refs)):
        return None
    if inputs.preferred_bar_diameter_mm is not None:
        if not refs:
            return None
        try:
            preferred = float(inputs.preferred_bar_diameter_mm)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(preferred) or preferred <= 0.0:
            return None
    return refs


def _candidate_search_population(population: ColumnRebarCandidatePopulation, *, requirement: GoverningRequiredRebar | None, preferred_bar_diameter_mm: float | None) -> tuple[ColumnRebarCandidatePopulation, tuple[CandidateAreaGateTrial, ...]]:
    candidates = tuple(population.candidates)
    if requirement is None:
        eligible = candidates
        trials: tuple[CandidateAreaGateTrial, ...] = ()
    else:
        required = requirement.governing_required_as_mm2
        trials = tuple(CandidateAreaGateTrial(item.candidate_id, item.as_total_mm2, required, "AREA_ELIGIBLE" if item.as_total_mm2 + 1e-9 >= required else "REJECTED_INSUFFICIENT_AS") for item in candidates)
        eligible = tuple(item for item in candidates if item.as_total_mm2 + 1e-9 >= required)
    if preferred_bar_diameter_mm is not None:
        preferred = float(preferred_bar_diameter_mm)
        eligible = tuple(sorted(eligible, key=lambda item: (round(item.as_total_mm2, 9), 0 if math.isclose(item.bar_diameter_mm, preferred, abs_tol=1e-9) else 1, item.bar_diameter_mm, item.bar_count, item.n_bars_dir2, item.n_bars_dir3, item.candidate_id)))
    return ColumnRebarCandidatePopulation(population.inputs, eligible, "PROVEN" if eligible else "NO_FEASIBLE_LAYOUT"), trials


def design_column_longitudinal_rebar(*, inputs: ColumnRebarDesignInputs, rebar_catalog: RebarCatalog, promoted_demands: Sequence[ColumnDemandState], governing_required_rebar: GoverningRequiredRebar | None = None) -> ColumnRebarDesignResult:
    """Select the smallest feasible physical candidate satisfying all active gates."""
    preference_refs = _preference_refs(inputs)
    if preference_refs is None:
        return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status="BLOCKED_CANDIDATE_PREFERENCE_PROVENANCE", requirement=governing_required_rebar)
    if governing_required_rebar is not None:
        if governing_required_rebar.component_id != inputs.component_id or inputs.section_identity is None or governing_required_rebar.section_identity != inputs.section_identity:
            return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status="BLOCKED_REQUIRED_REBAR_IDENTITY", requirement=governing_required_rebar)
    if rebar_catalog.status != "PROVEN_FACTUAL_REBAR_CATALOG":
        return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status="BLOCKED_REBAR_CATALOG", requirement=governing_required_rebar)
    allowed = rebar_catalog.column_longitudinal_diameters_mm
    excluded = tuple(item.name for item in rebar_catalog.excluded_below_column_minimum)
    if not allowed:
        return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status="NO_ELIGIBLE_COLUMN_BAR_SIZES", excluded=excluded, requirement=governing_required_rebar)
    population = generate_rectangular_column_rebar_candidates(ColumnRebarLayoutInputs(width_mm=inputs.width_mm, depth_mm=inputs.depth_mm, clear_cover_mm=inputs.clear_cover_mm, tie_diameter_mm=inputs.tie_diameter_mm, aggregate_max_mm=inputs.aggregate_max_mm, allowed_bar_diameters_mm=allowed))
    search_population, area_trials = _candidate_search_population(population, requirement=governing_required_rebar, preferred_bar_diameter_mm=inputs.preferred_bar_diameter_mm)
    if search_population.status != "PROVEN":
        return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status="NO_FEASIBLE_LAYOUT_REQUIRED_AS", excluded=excluded, population=population, requirement=governing_required_rebar, area_trials=area_trials)
    selection = select_engine_rebar_from_authorized_demands(component_id=inputs.component_id, width_mm=inputs.width_mm, depth_mm=inputs.depth_mm, population=search_population, material=inputs.material, demands=tuple(promoted_demands), basis=inputs.demand_basis, policy=inputs.selection_policy)
    status = "SELECTED_ENGINE_REBAR" if selection.authority == "ENGINE_SELECTED_REBAR" else selection.status
    return ColumnRebarDesignResult(inputs.component_id, status, rebar_catalog.status, population, selection, excluded, governing_required_rebar, area_trials, preference_refs)


def design_column_longitudinal_rebar_from_etabs_requirement(*, inputs: ColumnRebarDesignInputs, rebar_catalog: RebarCatalog, promoted_demands: Sequence[ColumnDemandState], etabs_required_rebar: EtabsRequiredRebar | None) -> ColumnRebarDesignResult:
    """P8A entry: require source-bound ETABS_REQUIRED_REBAR before engine selection."""
    if etabs_required_rebar is None or not etabs_required_rebar.resolved:
        status = "NO_DATA_ETABS_REQUIRED_REBAR" if etabs_required_rebar is None or etabs_required_rebar.status.startswith("NO_DATA") else "BLOCKED_ETABS_REQUIRED_REBAR"
        return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status=status)
    if inputs.section_identity is None:
        return _blocked_result(inputs=inputs, catalog_status=rebar_catalog.status, status="BLOCKED_REQUIRED_REBAR_IDENTITY")
    ledger = build_governing_required_rebar(etabs_required=etabs_required_rebar, width_mm=inputs.width_mm, depth_mm=inputs.depth_mm, tdby_rho_min=TBDY_COLUMN_RHO_MIN, tdby_source_refs=("TBDY_COLUMN_RHO_MIN:accepted-VS6-#145",))
    return design_column_longitudinal_rebar(inputs=inputs, rebar_catalog=rebar_catalog, promoted_demands=promoted_demands, governing_required_rebar=ledger)


__all__ = ["CandidateAreaGateTrial", "ColumnRebarDesignEngineError", "ColumnRebarDesignInputs", "ColumnRebarDesignResult", "design_column_longitudinal_rebar", "design_column_longitudinal_rebar_from_etabs_requirement"]
