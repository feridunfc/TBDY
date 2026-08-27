"""Canonical VS6 longitudinal-reinforcement design orchestration.

The engine consumes already-promoted column design demand states plus factual
project bar-catalog evidence and explicit reviewed detailing/material inputs.
It delegates candidate generation and section capacity to the pure kernels and
is the only production path in this slice allowed to emit ENGINE_SELECTED_REBAR.

VS6-P8A may additionally consume a role-preserving GOVERNING_REQUIRED_REBAR
requirement set.  Every ETABS/TBDY requirement state is checked independently;
there is no first/last/max design-result reduction.
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
from tbdy_engine.design.columns.rebar_requirement import (
    CandidateRequirementTrial,
    GoverningRequiredRebar,
    build_governing_required_rebar,
    evaluate_candidate_requirement_states,
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
from tbdy_engine.features.column_design_rebar_evidence import EtabsRequiredRebarComponent


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
    model_fingerprint: str | None = None
    evidence_epoch_id: str | None = None


@dataclass(frozen=True, slots=True)
class ColumnRebarDesignResult:
    component_id: str
    status: str
    catalog_status: str
    candidate_population: ColumnRebarCandidatePopulation | None
    selection: ColumnRebarSelectionResult | None
    excluded_catalog_bar_names: tuple[str, ...]
    governing_required_rebar: GoverningRequiredRebar | None = None
    requirement_trials: tuple[CandidateRequirementTrial, ...] = ()

    @property
    def authority(self) -> str:
        if self.selection is None:
            return "NOT_SELECTED"
        return self.selection.authority


class ColumnRebarDesignEngineError(ValueError):
    """Raised when factual/reviewed inputs cannot support a deterministic design."""


def _result(
    *,
    inputs: ColumnRebarDesignInputs,
    status: str,
    catalog_status: str,
    population: ColumnRebarCandidatePopulation | None,
    selection: ColumnRebarSelectionResult | None,
    excluded: tuple[str, ...],
    requirements: GoverningRequiredRebar | None,
    trials: tuple[CandidateRequirementTrial, ...] = (),
) -> ColumnRebarDesignResult:
    return ColumnRebarDesignResult(
        component_id=inputs.component_id,
        status=status,
        catalog_status=catalog_status,
        candidate_population=population,
        selection=selection,
        excluded_catalog_bar_names=excluded,
        governing_required_rebar=requirements,
        requirement_trials=trials,
    )


def _filter_population_by_requirements(
    population: ColumnRebarCandidatePopulation,
    *,
    requirements: GoverningRequiredRebar,
) -> tuple[ColumnRebarCandidatePopulation, tuple[CandidateRequirementTrial, ...]]:
    """Keep only candidates satisfying every source-distinct area requirement."""
    eligible = []
    trials: list[CandidateRequirementTrial] = []
    for candidate in population.candidates:
        candidate_trials = evaluate_candidate_requirement_states(
            candidate_id=candidate.candidate_id,
            candidate_as_mm2=candidate.as_total_mm2,
            requirements=requirements,
        )
        trials.extend(candidate_trials)
        if all(item.status == "SATISFIED" for item in candidate_trials):
            eligible.append(candidate)
    return (
        ColumnRebarCandidatePopulation(
            inputs=population.inputs,
            candidates=tuple(eligible),
            status="PROVEN" if eligible else "NO_FEASIBLE_LAYOUT",
        ),
        tuple(trials),
    )


def design_column_longitudinal_rebar(
    *,
    inputs: ColumnRebarDesignInputs,
    rebar_catalog: RebarCatalog,
    promoted_demands: Sequence[ColumnDemandState],
    governing_required_rebar: GoverningRequiredRebar | None = None,
) -> ColumnRebarDesignResult:
    """Select the smallest feasible candidate satisfying every active gate.

    The legacy accepted path remains valid when ``governing_required_rebar`` is
    absent.  P8A passes a source-distinct requirement set, which only narrows
    the candidate population; ENGINE_SELECTED_REBAR continues to be emitted by
    the accepted demand/capacity authority gate.
    """
    if governing_required_rebar is not None:
        if governing_required_rebar.component_id != inputs.component_id:
            return _result(
                inputs=inputs,
                status="BLOCKED_REQUIRED_REBAR_IDENTITY",
                catalog_status=rebar_catalog.status,
                population=None,
                selection=None,
                excluded=(),
                requirements=governing_required_rebar,
            )
        if inputs.section_identity is None or inputs.section_identity != governing_required_rebar.section_identity:
            return _result(
                inputs=inputs,
                status="BLOCKED_REQUIRED_REBAR_SECTION",
                catalog_status=rebar_catalog.status,
                population=None,
                selection=None,
                excluded=(),
                requirements=governing_required_rebar,
            )
        if (
            inputs.model_fingerprint is None
            or inputs.evidence_epoch_id is None
            or inputs.model_fingerprint != governing_required_rebar.model_fingerprint
            or inputs.evidence_epoch_id != governing_required_rebar.evidence_epoch_id
        ):
            return _result(
                inputs=inputs,
                status="BLOCKED_REQUIRED_REBAR_EVIDENCE_EPOCH",
                catalog_status=rebar_catalog.status,
                population=None,
                selection=None,
                excluded=(),
                requirements=governing_required_rebar,
            )

    if rebar_catalog.status != "PROVEN_FACTUAL_REBAR_CATALOG":
        return _result(
            inputs=inputs,
            status="BLOCKED_REBAR_CATALOG",
            catalog_status=rebar_catalog.status,
            population=None,
            selection=None,
            excluded=(),
            requirements=governing_required_rebar,
        )

    allowed = rebar_catalog.column_longitudinal_diameters_mm
    excluded = tuple(item.name for item in rebar_catalog.excluded_below_column_minimum)
    if not allowed:
        return _result(
            inputs=inputs,
            status="NO_ELIGIBLE_COLUMN_BAR_SIZES",
            catalog_status=rebar_catalog.status,
            population=None,
            selection=None,
            excluded=excluded,
            requirements=governing_required_rebar,
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
    search_population = population
    requirement_trials: tuple[CandidateRequirementTrial, ...] = ()
    if governing_required_rebar is not None:
        search_population, requirement_trials = _filter_population_by_requirements(
            population,
            requirements=governing_required_rebar,
        )
        if search_population.status != "PROVEN":
            return _result(
                inputs=inputs,
                status="NO_FEASIBLE_LAYOUT_REQUIRED_AS",
                catalog_status=rebar_catalog.status,
                population=population,
                selection=None,
                excluded=excluded,
                requirements=governing_required_rebar,
                trials=requirement_trials,
            )

    selection = select_engine_rebar_from_authorized_demands(
        component_id=inputs.component_id,
        width_mm=inputs.width_mm,
        depth_mm=inputs.depth_mm,
        population=search_population,
        material=inputs.material,
        demands=tuple(promoted_demands),
        basis=inputs.demand_basis,
        policy=inputs.selection_policy,
    )
    status = "SELECTED_ENGINE_REBAR" if selection.authority == "ENGINE_SELECTED_REBAR" else selection.status
    return _result(
        inputs=inputs,
        status=status,
        catalog_status=rebar_catalog.status,
        population=population,
        selection=selection,
        excluded=excluded,
        requirements=governing_required_rebar,
        trials=requirement_trials,
    )


def design_column_longitudinal_rebar_from_etabs_requirement(
    *,
    inputs: ColumnRebarDesignInputs,
    rebar_catalog: RebarCatalog,
    promoted_demands: Sequence[ColumnDemandState],
    etabs_required_rebar: EtabsRequiredRebarComponent,
    tdby_min_required_as_mm2: object,
    tdby_min_source_refs: Sequence[str],
) -> ColumnRebarDesignResult:
    """P8A entry point preserving ETABS/TBDY/GOVERNING/ENGINE roles."""
    requirements = build_governing_required_rebar(
        etabs_required=etabs_required_rebar,
        tdby_min_required_as_mm2=tdby_min_required_as_mm2,
        tdby_min_source_refs=tdby_min_source_refs,
    )
    return design_column_longitudinal_rebar(
        inputs=inputs,
        rebar_catalog=rebar_catalog,
        promoted_demands=promoted_demands,
        governing_required_rebar=requirements,
    )


__all__ = [
    "ColumnRebarDesignEngineError",
    "ColumnRebarDesignInputs",
    "ColumnRebarDesignResult",
    "design_column_longitudinal_rebar",
    "design_column_longitudinal_rebar_from_etabs_requirement",
]
