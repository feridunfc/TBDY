"""
Beam Region Flexure Mapping.
Maps BeamDemandSet moments to beam regions and runs pure flexure design kernels.
No external model adapters or postprocessing dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .context import BeamModelContext
from .demand import BeamDemandSet
from .calculators.flexure_design import (
    FlexureMdToAsInput,
    flexure_md_to_as,
    STATUS_OK as FLEXURE_OK,
    STATUS_NO_TENSION_REINFORCEMENT,
    STATUS_INVALID_INPUT as FLEXURE_INVALID,
)
from .calculators.flexure_limits import (
    FlexureLimitsInput,
    flexure_limits,
    STATUS_OK as LIMITS_OK,
    STATUS_MIN_REINFORCEMENT_GOVERNS,
    STATUS_OVER_REINFORCED,
    STATUS_INVALID_INPUT as LIMITS_INVALID,
)


# =============================================================================
# Status Constants
# =============================================================================

STATUS_OK = "OK"
STATUS_MIN_REINFORCEMENT_GOVERNS = "MIN_REINFORCEMENT_GOVERNS"
STATUS_OVER_REINFORCED = "OVER_REINFORCED"
STATUS_MISSING_DEMAND = "MISSING_DEMAND"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUS_PARTIAL = "PARTIAL"


# =============================================================================
# Region Result
# =============================================================================

@dataclass(frozen=True)
class BeamRegionFlexureResult:
    """Tek bölge eğilme tasarım sonucu"""
    region: str = ""
    demand_name: str = ""
    Md_kNm: float | None = None
    status: str = "NOT_EVALUATED"
    As_required_cm2: float = 0.0
    As_min_cm2: float = 0.0
    As_max_cm2: float = 0.0
    As_design_required_cm2: float = 0.0
    rho_required: float = 0.0
    rho_min: float = 0.0
    rho_max: float = 0.0
    governing: str = ""
    demand_evidence: Mapping[str, object] = field(default_factory=dict)
    flexure_evidence: Mapping[str, object] = field(default_factory=dict)
    limit_evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamFlexureRegionDesignResult:
    """Tüm bölgelerin eğilme tasarım sonucu"""
    beam_id: str
    label: str
    status: str = "NOT_EVALUATED"
    regions: dict[str, BeamRegionFlexureResult] = field(default_factory=dict)
    evidence: Mapping[str, object] = field(default_factory=dict)


# =============================================================================
# Region Mapping
# =============================================================================

REGION_MAP: dict[str, tuple[str, str]] = {
    "top_left":   ("left",   "Md_left_neg_kNm"),
    "bottom_mid": ("mid",    "Md_mid_pos_kNm"),
    "top_right":  ("right",  "Md_right_neg_kNm"),
}


def _get_demand_value(demand: BeamDemandSet, demand_name: str) -> float | None:
    """BeamDemandSet'ten demand değerini oku."""
    mapping = {
        "Md_left_neg_kNm":  demand.Md_left_neg_kNm,
        "Md_mid_pos_kNm":   demand.Md_mid_pos_kNm,
        "Md_right_neg_kNm": demand.Md_right_neg_kNm,
    }
    return mapping.get(demand_name)


def _get_demand_evidence(demand: BeamDemandSet, demand_name: str) -> Mapping[str, object]:
    """BeamDemandSet'ten demand evidence'ını oku."""
    gov = demand.governing.get(demand_name)
    if gov is None:
        return {}
    return {
        "combo": gov.combo,
        "station": gov.station,
        "raw_value": gov.raw_value,
        "rule": gov.rule,
        "combo_family": gov.combo_family,
    }


# =============================================================================
# Single Region Design
# =============================================================================

def _design_region(
    region: str,
    demand_name: str,
    Md_kNm: float | None,
    context: BeamModelContext,
    rho_max: float,
) -> BeamRegionFlexureResult:
    """Tek bölge için flexure design + limits."""

    demand_evidence = {}

    # Missing demand
    if Md_kNm is None:
        return BeamRegionFlexureResult(
            region=region,
            demand_name=demand_name,
            Md_kNm=None,
            status=STATUS_MISSING_DEMAND,
            demand_evidence={"rule": "missing_demand", "demand_name": demand_name},
        )

    # Zero or positive moment: run flexure kernel
    flex_input = FlexureMdToAsInput(
        Md_kNm=Md_kNm,
        bw_mm=context.geometry.bw_mm,
        d_mm=context.geometry.d_mm,
        fcd_mpa=context.material.fcd_mpa,
        fyd_mpa=context.material.fyd_mpa,
    )
    flex_result = flexure_md_to_as(flex_input)

    if flex_result.status == FLEXURE_INVALID:
        return BeamRegionFlexureResult(
            region=region,
            demand_name=demand_name,
            Md_kNm=Md_kNm,
            status=STATUS_INVALID_INPUT,
            demand_evidence=demand_evidence,
            flexure_evidence=dict(flex_result.evidence),
        )

    # Run limits
    limits_input = FlexureLimitsInput(
        As_required_cm2=flex_result.As_required_cm2,
        bw_mm=context.geometry.bw_mm,
        d_mm=context.geometry.d_mm,
        fctd_mpa=context.material.fctd_mpa,
        fyd_mpa=context.material.fyd_mpa,
        rho_max=rho_max,
    )
    limits_result = flexure_limits(limits_input)

    # Determine region status
    if limits_result.status == STATUS_OVER_REINFORCED:
        region_status = STATUS_OVER_REINFORCED
    elif limits_result.status == STATUS_MIN_REINFORCEMENT_GOVERNS:
        region_status = STATUS_MIN_REINFORCEMENT_GOVERNS
    elif flex_result.status == STATUS_NO_TENSION_REINFORCEMENT:
        region_status = STATUS_MIN_REINFORCEMENT_GOVERNS
    else:
        region_status = STATUS_OK

    return BeamRegionFlexureResult(
        region=region,
        demand_name=demand_name,
        Md_kNm=Md_kNm,
        status=region_status,
        As_required_cm2=flex_result.As_required_cm2,
        As_min_cm2=limits_result.As_min_cm2,
        As_max_cm2=limits_result.As_max_cm2,
        As_design_required_cm2=limits_result.As_design_required_cm2,
        rho_required=limits_result.rho_required,
        rho_min=limits_result.rho_min,
        rho_max=limits_result.rho_max,
        governing=limits_result.governing,
        demand_evidence=demand_evidence,
        flexure_evidence=dict(flex_result.evidence),
        limit_evidence=dict(limits_result.evidence),
    )


# =============================================================================
# Main Orchestration
# =============================================================================

def design_beam_region_flexure(
    context: BeamModelContext,
    demand: BeamDemandSet,
    *,
    rho_max: float = 0.02,
) -> BeamFlexureRegionDesignResult:
    """
    Map BeamDemandSet moments to beam regions and run flexure design kernels.

    Args:
        context: BeamModelContext (geometry + material).
        demand: BeamDemandSet (Md_left_neg, Md_mid_pos, Md_right_neg).
        rho_max: Maximum reinforcement ratio (default 0.02).

    Returns:
        BeamFlexureRegionDesignResult with per-region flexure design.
    """
    # -----------------------------------------------------------------
    # 1. Validate identity match
    # -----------------------------------------------------------------
    invalid: list[str] = []

    if context.beam_id != demand.beam_id:
        invalid.append(f"beam_id mismatch: context={context.beam_id}, demand={demand.beam_id}")
    if context.label != demand.label:
        invalid.append(f"label mismatch: context={context.label}, demand={demand.label}")

    if invalid:
        return BeamFlexureRegionDesignResult(
            beam_id=context.beam_id,
            label=context.label,
            status=STATUS_INVALID_INPUT,
            evidence={"invalid_inputs": tuple(invalid)},
        )

    # -----------------------------------------------------------------
    # 2. Validate geometry/material
    # -----------------------------------------------------------------
    if context.geometry.bw_mm <= 0 or context.geometry.d_mm <= 0:
        return BeamFlexureRegionDesignResult(
            beam_id=context.beam_id,
            label=context.label,
            status=STATUS_INVALID_INPUT,
            evidence={"invalid_inputs": ("geometry dimensions <= 0",)},
        )

    if context.material.fcd_mpa <= 0 or context.material.fyd_mpa <= 0:
        return BeamFlexureRegionDesignResult(
            beam_id=context.beam_id,
            label=context.label,
            status=STATUS_INVALID_INPUT,
            evidence={"invalid_inputs": ("material strengths <= 0",)},
        )

    # -----------------------------------------------------------------
    # 3. Design each region
    # -----------------------------------------------------------------
    regions: dict[str, BeamRegionFlexureResult] = {}

    for region_key, (position, demand_name) in REGION_MAP.items():
        Md_val = _get_demand_value(demand, demand_name)
        demand_evidence = _get_demand_evidence(demand, demand_name)

        region_result = _design_region(
            region=region_key,
            demand_name=demand_name,
            Md_kNm=Md_val,
            context=context,
            rho_max=rho_max,
        )

        # Merge demand evidence into region result
        if demand_evidence:
            region_result = BeamRegionFlexureResult(
                region=region_result.region,
                demand_name=region_result.demand_name,
                Md_kNm=region_result.Md_kNm,
                status=region_result.status,
                As_required_cm2=region_result.As_required_cm2,
                As_min_cm2=region_result.As_min_cm2,
                As_max_cm2=region_result.As_max_cm2,
                As_design_required_cm2=region_result.As_design_required_cm2,
                rho_required=region_result.rho_required,
                rho_min=region_result.rho_min,
                rho_max=region_result.rho_max,
                governing=region_result.governing,
                demand_evidence=demand_evidence,
                flexure_evidence=region_result.flexure_evidence,
                limit_evidence=region_result.limit_evidence,
            )

        regions[region_key] = region_result

    # -----------------------------------------------------------------
    # 4. Determine overall status
    # -----------------------------------------------------------------
    region_statuses = [r.status for r in regions.values()]

    if STATUS_OVER_REINFORCED in region_statuses:
        overall = STATUS_OVER_REINFORCED
    elif STATUS_INVALID_INPUT in region_statuses:
        overall = STATUS_INVALID_INPUT
    elif STATUS_MISSING_DEMAND in region_statuses:
        overall = STATUS_PARTIAL
    elif STATUS_MIN_REINFORCEMENT_GOVERNS in region_statuses:
        overall = STATUS_MIN_REINFORCEMENT_GOVERNS
    else:
        overall = STATUS_OK

    # -----------------------------------------------------------------
    # 5. Return
    # -----------------------------------------------------------------
    return BeamFlexureRegionDesignResult(
        beam_id=context.beam_id,
        label=context.label,
        status=overall,
        regions=regions,
        evidence={
            "method": "beam_region_flexure_mapping",
            "region_map": dict(REGION_MAP),
            "demand_source": demand.source,
            "envelope_mode": demand.combination_metadata.envelope_mode,
            "rho_max": rho_max,
        },
    )
