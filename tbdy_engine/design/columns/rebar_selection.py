"""VS6-P6 column demand normalization and ENGINE_SELECTED_REBAR selection.

This module is intentionally pure.  ETABS acquisition is external; factual
rows are normalized here only after explicit unit/sign contracts are supplied.
Final selection is blocked unless the reviewed design-demand basis is complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarCandidate,
    ColumnRebarCandidatePopulation,
)
from tbdy_engine.design.columns.section_capacity import (
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    radial_moment_capacity,
)


class ColumnRebarSelectionError(ValueError):
    """Raised when demand evidence or reviewed selection inputs are invalid."""


ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION = "ETABS_P_NEGATIVE_COMPRESSION"
_ALLOWED_BASIS_STATUS = frozenset({"RESOLVED", "BLOCKED"})


def _float(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnRebarSelectionError(f"{label} must be a finite numeric scalar")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        try:
            result = float(Decimal(str(value)))
        except (InvalidOperation, ValueError) as exc:
            raise ColumnRebarSelectionError(f"{label} must be a finite numeric scalar") from exc
    if not math.isfinite(result):
        raise ColumnRebarSelectionError(f"{label} must be finite")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnRebarSelectionError(f"{label} must be a nonblank canonical string")
    return value


@dataclass(frozen=True, slots=True)
class ColumnDemandBasis:
    analysis_order_status: str
    minimum_eccentricity_status: str
    slenderness_status: str
    combination_scope_status: str
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "analysis_order_status",
            "minimum_eccentricity_status",
            "slenderness_status",
            "combination_scope_status",
        ):
            value = _text(getattr(self, name), name)
            if value not in _ALLOWED_BASIS_STATUS:
                raise ColumnRebarSelectionError(f"{name} must be RESOLVED or BLOCKED")
        refs = tuple(_text(value, "review_ref") for value in self.review_refs)
        if not refs or len(refs) != len(set(refs)):
            raise ColumnRebarSelectionError("review_refs must be a nonempty unique sequence")
        object.__setattr__(self, "review_refs", refs)

    @property
    def is_resolved(self) -> bool:
        return all(
            value == "RESOLVED"
            for value in (
                self.analysis_order_status,
                self.minimum_eccentricity_status,
                self.slenderness_status,
                self.combination_scope_status,
            )
        )

    @property
    def blocked_items(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in (
                "analysis_order_status",
                "minimum_eccentricity_status",
                "slenderness_status",
                "combination_scope_status",
            )
            if getattr(self, name) != "RESOLVED"
        )


@dataclass(frozen=True, slots=True)
class ColumnDemandState:
    state_id: str
    component_id: str
    output_case: str
    case_type: str
    step_type: str
    step_number: str | None
    station_m: float
    end_tag: str
    nd_compression_n: float
    m2_nmm: float
    m3_nmm: float
    source_identity: str

    @property
    def moment_magnitude_nmm(self) -> float:
        return math.hypot(self.m2_nmm, self.m3_nmm)


@dataclass(frozen=True, slots=True)
class DemandCapacityEvaluation:
    state: ColumnDemandState
    radial_capacity_nmm: float | None
    utilization: float
    status: str


@dataclass(frozen=True, slots=True)
class CandidateSelectionTrial:
    candidate_id: str
    as_total_mm2: float
    status: str
    max_utilization: float | None
    governing_state_id: str | None
    evaluated_state_count: int


@dataclass(frozen=True, slots=True)
class ColumnRebarSelectionResult:
    component_id: str
    status: str
    authority: str
    selected_candidate: ColumnRebarCandidate | None
    required_as_in_candidate_family_mm2: float | None
    governing_state_id: str | None
    governing_utilization: float | None
    trials: tuple[CandidateSelectionTrial, ...]
    selected_evaluations: tuple[DemandCapacityEvaluation, ...]
    basis: ColumnDemandBasis


@dataclass(frozen=True, slots=True)
class ColumnRebarSelectionPolicy:
    angle_count: int
    axial_tolerance_n: float
    utilization_limit: float = 1.0

    def __post_init__(self) -> None:
        if self.angle_count < 8 or self.angle_count % 4 != 0:
            raise ColumnRebarSelectionError("angle_count must be >= 8 and divisible by 4")
        if not math.isfinite(float(self.axial_tolerance_n)) or self.axial_tolerance_n <= 0.0:
            raise ColumnRebarSelectionError("axial_tolerance_n must be finite and > 0")
        if not math.isfinite(float(self.utilization_limit)) or not (0.0 < self.utilization_limit <= 1.0):
            raise ColumnRebarSelectionError("utilization_limit must be in (0, 1]")


def normalize_etabs_column_end_demands(
    rows: Sequence[Mapping[str, Any]],
    *,
    unique_name: str,
    component_id: str,
    reviewed_force_unit: str,
    reviewed_moment_unit: str,
    axial_sign_policy: str,
) -> tuple[ColumnDemandState, ...]:
    """Normalize exact ETABS I/J-end P-M2-M3 rows without governing selection."""
    uid = _text(unique_name, "unique_name")
    component = _text(component_id, "component_id")
    if reviewed_force_unit != "kN" or reviewed_moment_unit != "kN-m":
        raise ColumnRebarSelectionError("initial VS6 demand normalizer requires reviewed kN / kN-m source units")
    if axial_sign_policy != ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION:
        raise ColumnRebarSelectionError("ETABS axial sign convention must be explicitly reviewed as negative compression")

    exact = [row for row in rows if str(row.get("UniqueName")) == uid]
    if not exact:
        raise ColumnRebarSelectionError(f"no exact force rows for UniqueName={uid}")
    stations = sorted({_float(row.get("Station"), "Station") for row in exact})
    if len(stations) < 2:
        raise ColumnRebarSelectionError("column end normalization requires at least two exact Station values")
    station_i = stations[0]
    station_j = stations[-1]

    out: list[ColumnDemandState] = []
    seen: set[str] = set()
    for row in exact:
        station = _float(row.get("Station"), "Station")
        if abs(station - station_i) <= 1e-9:
            end_tag = "I_END"
        elif abs(station - station_j) <= 1e-9:
            end_tag = "J_END"
        else:
            continue
        output_case = _text(row.get("OutputCase"), "OutputCase")
        case_type = _text(row.get("CaseType"), "CaseType")
        step_type = _text(row.get("StepType"), "StepType")
        step_number_raw = row.get("StepNumber")
        step_number = None if step_number_raw in (None, "") else str(step_number_raw)
        source_identity = "|".join(
            str(row.get(field) if row.get(field) is not None else "")
            for field in (
                "Story",
                "Column",
                "UniqueName",
                "OutputCase",
                "CaseType",
                "StepType",
                "StepNumber",
                "Station",
                "Element",
                "ElemStation",
            )
        )
        state_id = f"{component}|{end_tag}|{source_identity}"
        if state_id in seen:
            raise ColumnRebarSelectionError("duplicate exact design demand identity")
        seen.add(state_id)
        p_kn = _float(row.get("P"), "P")
        m2_knm = _float(row.get("M2"), "M2")
        m3_knm = _float(row.get("M3"), "M3")
        out.append(
            ColumnDemandState(
                state_id=state_id,
                component_id=component,
                output_case=output_case,
                case_type=case_type,
                step_type=step_type,
                step_number=step_number,
                station_m=station,
                end_tag=end_tag,
                nd_compression_n=-p_kn * 1000.0,
                m2_nmm=m2_knm * 1_000_000.0,
                m3_nmm=m3_knm * 1_000_000.0,
                source_identity=source_identity,
            )
        )
    if not out:
        raise ColumnRebarSelectionError("no I/J end rows remained after exact station filtering")
    out.sort(key=lambda item: item.state_id)
    return tuple(out)


def _evaluate_candidate(
    *,
    width_mm: float,
    depth_mm: float,
    candidate: ColumnRebarCandidate,
    material: ColumnSectionMaterial,
    demands: Sequence[ColumnDemandState],
    policy: ColumnRebarSelectionPolicy,
) -> tuple[CandidateSelectionTrial, tuple[DemandCapacityEvaluation, ...]]:
    evaluations: list[DemandCapacityEvaluation] = []
    max_utilization = -1.0
    governing_state_id: str | None = None

    for demand in demands:
        envelope = build_interaction_envelope_at_axial_force(
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=candidate.bars,
            material=material,
            target_n_compression_n=demand.nd_compression_n,
            angle_count=policy.angle_count,
            axial_tolerance_n=policy.axial_tolerance_n,
        )
        if envelope.status != "PROVEN":
            evaluations.append(DemandCapacityEvaluation(demand, None, math.inf, "OUTSIDE_AXIAL_CAPACITY"))
            return (
                CandidateSelectionTrial(
                    candidate_id=candidate.candidate_id,
                    as_total_mm2=candidate.as_total_mm2,
                    status="REJECTED_CAPACITY",
                    max_utilization=None,
                    governing_state_id=demand.state_id,
                    evaluated_state_count=len(evaluations),
                ),
                tuple(evaluations),
            )

        if demand.moment_magnitude_nmm <= 1e-12:
            evaluation = DemandCapacityEvaluation(demand, None, 0.0, "PROVEN")
        else:
            radial = radial_moment_capacity(
                envelope,
                demand_m2_nmm=demand.m2_nmm,
                demand_m3_nmm=demand.m3_nmm,
            )
            if radial.status != "PROVEN" or radial.capacity_nmm <= 0.0:
                evaluations.append(DemandCapacityEvaluation(demand, None, math.inf, radial.status))
                return (
                    CandidateSelectionTrial(
                        candidate_id=candidate.candidate_id,
                        as_total_mm2=candidate.as_total_mm2,
                        status="REJECTED_CAPACITY",
                        max_utilization=None,
                        governing_state_id=demand.state_id,
                        evaluated_state_count=len(evaluations),
                    ),
                    tuple(evaluations),
                )
            utilization = demand.moment_magnitude_nmm / radial.capacity_nmm
            evaluation = DemandCapacityEvaluation(demand, radial.capacity_nmm, utilization, "PROVEN")
        evaluations.append(evaluation)
        if evaluation.utilization > max_utilization:
            max_utilization = evaluation.utilization
            governing_state_id = demand.state_id
        if evaluation.utilization > policy.utilization_limit + 1e-12:
            return (
                CandidateSelectionTrial(
                    candidate_id=candidate.candidate_id,
                    as_total_mm2=candidate.as_total_mm2,
                    status="REJECTED_UTILIZATION",
                    max_utilization=evaluation.utilization,
                    governing_state_id=demand.state_id,
                    evaluated_state_count=len(evaluations),
                ),
                tuple(evaluations),
            )

    return (
        CandidateSelectionTrial(
            candidate_id=candidate.candidate_id,
            as_total_mm2=candidate.as_total_mm2,
            status="ELIGIBLE",
            max_utilization=max_utilization if max_utilization >= 0.0 else 0.0,
            governing_state_id=governing_state_id,
            evaluated_state_count=len(evaluations),
        ),
        tuple(evaluations),
    )


def select_engine_rebar_for_demands(
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
    component = _text(component_id, "component_id")
    if not basis.is_resolved:
        return ColumnRebarSelectionResult(
            component_id=component,
            status="BLOCKED_DEMAND_BASIS",
            authority="NOT_SELECTED",
            selected_candidate=None,
            required_as_in_candidate_family_mm2=None,
            governing_state_id=None,
            governing_utilization=None,
            trials=(),
            selected_evaluations=(),
            basis=basis,
        )
    demand_tuple = tuple(demands)
    if not demand_tuple:
        return ColumnRebarSelectionResult(
            component_id=component,
            status="NO_DATA",
            authority="NOT_SELECTED",
            selected_candidate=None,
            required_as_in_candidate_family_mm2=None,
            governing_state_id=None,
            governing_utilization=None,
            trials=(),
            selected_evaluations=(),
            basis=basis,
        )
    if population.status != "PROVEN" or not population.candidates:
        return ColumnRebarSelectionResult(
            component_id=component,
            status="NO_FEASIBLE_LAYOUT",
            authority="NOT_SELECTED",
            selected_candidate=None,
            required_as_in_candidate_family_mm2=None,
            governing_state_id=None,
            governing_utilization=None,
            trials=(),
            selected_evaluations=(),
            basis=basis,
        )

    trials: list[CandidateSelectionTrial] = []
    for candidate in population.candidates:
        trial, evaluations = _evaluate_candidate(
            width_mm=width_mm,
            depth_mm=depth_mm,
            candidate=candidate,
            material=material,
            demands=demand_tuple,
            policy=policy,
        )
        trials.append(trial)
        if trial.status == "ELIGIBLE":
            return ColumnRebarSelectionResult(
                component_id=component,
                status="SELECTED",
                authority="ENGINE_SELECTED_REBAR",
                selected_candidate=candidate,
                required_as_in_candidate_family_mm2=candidate.as_total_mm2,
                governing_state_id=trial.governing_state_id,
                governing_utilization=trial.max_utilization,
                trials=tuple(trials),
                selected_evaluations=evaluations,
                basis=basis,
            )

    return ColumnRebarSelectionResult(
        component_id=component,
        status="NO_FEASIBLE_LAYOUT",
        authority="NOT_SELECTED",
        selected_candidate=None,
        required_as_in_candidate_family_mm2=None,
        governing_state_id=trials[-1].governing_state_id if trials else None,
        governing_utilization=trials[-1].max_utilization if trials else None,
        trials=tuple(trials),
        selected_evaluations=(),
        basis=basis,
    )


__all__ = [
    "CandidateSelectionTrial",
    "ColumnDemandBasis",
    "ColumnDemandState",
    "ColumnRebarSelectionError",
    "ColumnRebarSelectionPolicy",
    "ColumnRebarSelectionResult",
    "DemandCapacityEvaluation",
    "ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION",
    "normalize_etabs_column_end_demands",
    "select_engine_rebar_for_demands",
]
