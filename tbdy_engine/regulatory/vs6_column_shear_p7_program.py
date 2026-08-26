"""Bounded source-bound VS6-P7 column shear orchestration.

This is the production composition seam for P7.  It composes already promoted
facts/derived inputs with the pure demand and upper-bound kernels.  It does not
acquire ETABS data, select transverse reinforcement, compute Vr, mutate the
model, or perform reporting calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.design.columns.column_shear_demand import (
    ColumnEndMomentCapacityBasis,
    ColumnShearDesignDemandInput,
    ColumnShearDesignDemandResult,
    evaluate_tbdy_737_column_shear_demand,
)
from tbdy_engine.design.columns.column_shear_upper_bounds import (
    ColumnEffectiveDepthResolution,
    evaluate_tbdy_7375_brittle_upper_bound,
    evaluate_ts500_815_web_compression_upper_bound,
)
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


class VS6P7ProgramError(ValueError):
    """Raised when composed P7 identities/authorities are inconsistent."""


class ColumnShearVrClosureStatus(StrEnum):
    BLOCKED_BY_TRANSVERSE_REBAR_SLICE = "BLOCKED_BY_TRANSVERSE_REBAR_SLICE"


@dataclass(frozen=True, slots=True)
class SourceBoundShearDemand:
    demand_n: float
    source_identity: str
    output_case: str
    case_type: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        value = float(self.demand_n)
        if not math.isfinite(value) or value < 0.0:
            raise VS6P7ProgramError("demand_n must be finite and >= 0")
        object.__setattr__(self, "demand_n", value)
        for name in ("source_identity", "output_case", "case_type", "evidence_epoch_id"):
            text = getattr(self, name)
            if not isinstance(text, str) or not text.strip() or text != text.strip():
                raise VS6P7ProgramError(f"{name} must be a nonblank canonical string")
        refs = tuple(self.source_refs)
        if not refs or len(refs) != len(set(refs)) or any(
            not isinstance(item, str) or not item.strip() for item in refs
        ):
            raise VS6P7ProgramError("source_refs must be nonempty unique strings")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class VS6P7DirectionRun:
    component_id: str
    story: str
    section: str
    direction: str
    demand: ColumnShearDesignDemandResult
    tbdy_vd: SourceBoundShearDemand
    ts500_vd: SourceBoundShearDemand
    bottom_capacity: ColumnEndMomentCapacityBasis
    top_capacity: ColumnEndMomentCapacityBasis
    effective_depth: ColumnEffectiveDepthResolution
    tbdy_brittle_result: CheckResult | None
    ts500_web_result: CheckResult | None
    full_vr_closure_status: ColumnShearVrClosureStatus
    analysis_basis_status: AnalysisBasisStatus
    applicability_status: str

    @property
    def ve_n(self) -> float | None:
        return self.demand.final_ve_n


@dataclass(frozen=True, slots=True)
class VS6P7ColumnShearRun:
    component_id: str
    directions: tuple[VS6P7DirectionRun, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise VS6P7ProgramError("component_id must be nonblank")
        directions = tuple(sorted(self.directions, key=lambda item: item.direction))
        if any(item.component_id != self.component_id for item in directions):
            raise VS6P7ProgramError("direction run component identity mismatch")
        if len({item.direction for item in directions}) != len(directions):
            raise VS6P7ProgramError("duplicate direction run")
        object.__setattr__(self, "directions", directions)


def _blocked_check(
    *,
    check_id: str,
    component_id: str,
    story: str,
    section: str,
    code_ref: str,
    message: str,
    evidence: Sequence[object],
    status: CheckStatus = CheckStatus.BLOCKED,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        component=component_id,
        component_type="column",
        story=story,
        section=section,
        status=status,
        evaluation_level=EvaluationLevel.NO_DATA,
        evidence=tuple(evidence),
        messages=(message,),
        code_ref=code_ref,
        diagnostics=(),
    )


def run_vs6_p7_direction(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    tbdy_high_ductility_applies: bool | None,
    ts500_rc_applies: bool | None,
    free_length_ln_mm: float | None,
    free_length_basis_ref: str | None,
    bottom_capacity: ColumnEndMomentCapacityBasis,
    top_capacity: ColumnEndMomentCapacityBasis,
    d_amplified_candidate_n: float | None,
    d_amplified_basis_ref: str | None,
    tbdy_vd: SourceBoundShearDemand,
    ts500_vd: SourceBoundShearDemand,
    response_spectrum_concurrency_required: bool,
    response_spectrum_concurrency_proven: bool,
    aw_mm2: float | None,
    aw_source_ref: str | None,
    fck_mpa: float,
    fcd_mpa: float,
    effective_depth: ColumnEffectiveDepthResolution,
) -> VS6P7DirectionRun:
    """Run one local shear direction with separate TBDY/TS500 applicability."""
    if tbdy_high_ductility_applies is not None and type(tbdy_high_ductility_applies) is not bool:
        raise VS6P7ProgramError("tbdy_high_ductility_applies must be bool or None")
    if ts500_rc_applies is not None and type(ts500_rc_applies) is not bool:
        raise VS6P7ProgramError("ts500_rc_applies must be bool or None")

    evidence = tuple(
        dict.fromkeys(
            (
                *tbdy_vd.source_refs,
                *ts500_vd.source_refs,
                *bottom_capacity.source_refs,
                *top_capacity.source_refs,
                *effective_depth.source_refs,
            )
        )
    )

    demand_input = ColumnShearDesignDemandInput(
        component_id=component_id,
        direction=direction,
        free_length_ln_mm=free_length_ln_mm,
        free_length_basis_ref=free_length_basis_ref,
        bottom_capacity=bottom_capacity,
        top_capacity=top_capacity,
        d_amplified_candidate_n=d_amplified_candidate_n,
        d_amplified_basis_ref=d_amplified_basis_ref,
        vd_floor_n=tbdy_vd.demand_n,
        vd_source_ref=tbdy_vd.source_identity,
        response_spectrum_concurrency_required=response_spectrum_concurrency_required,
        response_spectrum_concurrency_proven=response_spectrum_concurrency_proven,
    )

    if tbdy_high_ductility_applies is True:
        demand = evaluate_tbdy_737_column_shear_demand(demand_input)
        applicability = "TBDY_APPLIES"
    else:
        demand = ColumnShearDesignDemandResult(
            component_id=component_id,
            direction=direction,
            status=(
                "PROVEN_NOT_APPLICABLE"
                if tbdy_high_ductility_applies is False
                else "BLOCKED_TBDY_HIGH_DUCTILITY_APPLICABILITY"
            ),
            ve_capacity_eq75_n=None,
            d_amplified_candidate_n=d_amplified_candidate_n,
            vd_floor_n=tbdy_vd.demand_n,
            final_ve_n=None,
            governing_rule=None,
            bottom_capacity=bottom_capacity,
            top_capacity=top_capacity,
            source_refs=evidence,
        )
        applicability = demand.status

    if tbdy_high_ductility_applies is False:
        tbdy_result = _blocked_check(
            check_id="TBDY_7_3_7_5_EQ7_7_BRITTLE_UPPER",
            component_id=component_id,
            story=story,
            section=section,
            code_ref="TBDY 2018 7.3.7.5 Eq. (7.7)",
            message="TBDY_7_3_7_PROVEN_NOT_APPLICABLE",
            evidence=evidence,
            status=CheckStatus.OUT_OF_SCOPE,
        )
    elif tbdy_high_ductility_applies is None or demand.final_ve_n is None:
        tbdy_result = _blocked_check(
            check_id="TBDY_7_3_7_5_EQ7_7_BRITTLE_UPPER",
            component_id=component_id,
            story=story,
            section=section,
            code_ref="TBDY 2018 7.3.7.5 Eq. (7.7)",
            message=demand.status,
            evidence=evidence,
        )
    elif aw_mm2 is None or aw_source_ref is None:
        tbdy_result = _blocked_check(
            check_id="TBDY_7_3_7_5_EQ7_7_BRITTLE_UPPER",
            component_id=component_id,
            story=story,
            section=section,
            code_ref="TBDY 2018 7.3.7.5 Eq. (7.7)",
            message="BLOCKED_AW_BASIS",
            evidence=evidence,
        )
    else:
        tbdy_result = evaluate_tbdy_7375_brittle_upper_bound(
            component_id=component_id,
            story=story,
            section=section,
            direction=direction,
            ve_n=demand.final_ve_n,
            aw_mm2=aw_mm2,
            fck_mpa=fck_mpa,
            evidence=(*evidence, aw_source_ref),
        )

    if ts500_rc_applies is False:
        ts500_result = _blocked_check(
            check_id="TS500_8_1_5_WEB_COMPRESSION_UPPER",
            component_id=component_id,
            story=story,
            section=section,
            code_ref="TS 500 8.1.5",
            message="TS500_RC_SHEAR_PROVEN_NOT_APPLICABLE",
            evidence=evidence,
            status=CheckStatus.OUT_OF_SCOPE,
        )
    elif ts500_rc_applies is None:
        ts500_result = _blocked_check(
            check_id="TS500_8_1_5_WEB_COMPRESSION_UPPER",
            component_id=component_id,
            story=story,
            section=section,
            code_ref="TS 500 8.1.5",
            message="BLOCKED_TS500_RC_APPLICABILITY",
            evidence=evidence,
        )
    else:
        ts500_result = evaluate_ts500_815_web_compression_upper_bound(
            component_id=component_id,
            story=story,
            section=section,
            direction=direction,
            vd_n=ts500_vd.demand_n,
            fcd_mpa=fcd_mpa,
            effective_depth=effective_depth,
            evidence=evidence,
        )

    analysis_basis = (
        AnalysisBasisStatus.REANALYSIS_REQUIRED
        if tbdy_result.status is CheckStatus.FAIL
        else (
            AnalysisBasisStatus.UNRESOLVED
            if tbdy_result.status in {CheckStatus.BLOCKED, CheckStatus.NO_DATA}
            else AnalysisBasisStatus.MATCH
        )
    )

    return VS6P7DirectionRun(
        component_id=component_id,
        story=story,
        section=section,
        direction=direction,
        demand=demand,
        tbdy_vd=tbdy_vd,
        ts500_vd=ts500_vd,
        bottom_capacity=bottom_capacity,
        top_capacity=top_capacity,
        effective_depth=effective_depth,
        tbdy_brittle_result=tbdy_result,
        ts500_web_result=ts500_result,
        full_vr_closure_status=ColumnShearVrClosureStatus.BLOCKED_BY_TRANSVERSE_REBAR_SLICE,
        analysis_basis_status=analysis_basis,
        applicability_status=applicability,
    )


def build_vs6_p7_column_shear_run(
    *,
    component_id: str,
    directions: Sequence[VS6P7DirectionRun],
) -> VS6P7ColumnShearRun:
    return VS6P7ColumnShearRun(component_id=component_id, directions=tuple(directions))


__all__ = [
    "ColumnShearVrClosureStatus",
    "SourceBoundShearDemand",
    "VS6P7DirectionRun",
    "VS6P7ColumnShearRun",
    "VS6P7ProgramError",
    "build_vs6_p7_column_shear_run",
    "run_vs6_p7_direction",
]
