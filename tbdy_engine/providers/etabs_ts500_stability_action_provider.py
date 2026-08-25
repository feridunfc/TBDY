"""ETABS-to-TS500 stability action-role promotion boundary.

The factual provider has already decoded StaticLinear.GetLoads and
LoadPatterns.GetLoadType.  This module promotes only a deliberately narrow,
reviewed mapping of ETABS load-pattern types to TS500 stability action roles.

Case names are never inspected.  Only atomic, unit-scale linear-static cases
are eligible as reusable response sources for later TS500 load-basis
reconstruction.  Composite/scaled cases remain visible as excluded evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.design.columns.stability_action_basis import (
    StabilityActionSource,
    TS500_ACTION_E,
    TS500_ACTION_G,
    TS500_ACTION_Q,
    TS500_ACTION_W,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsStaticLinearCaseEvidence,
)


ETABS_PATTERN_TYPE_TO_TS500_ACTION: dict[str, str] = {
    "DEAD": TS500_ACTION_G,
    "SUPER_DEAD": TS500_ACTION_G,
    "LIVE": TS500_ACTION_Q,
    "QUAKE": TS500_ACTION_E,
    "WIND": TS500_ACTION_W,
}

ETABS_TS500_ACTION_PROMOTION_AUTHORITY = "ETABS_PATTERN_TYPE_TO_TS500_STABILITY_ACTION"


@dataclass(frozen=True, slots=True)
class ExcludedStaticCaseActionEvidence:
    case_name: str
    reason: str
    factual_loads: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "reason": self.reason,
            "factual_loads": [dict(item) for item in self.factual_loads],
        }


@dataclass(frozen=True, slots=True)
class EtabsTS500StabilityActionPromotion:
    status: str
    promoted_sources: tuple[StabilityActionSource, ...]
    excluded_cases: tuple[ExcludedStaticCaseActionEvidence, ...]
    authority: str = ETABS_TS500_ACTION_PROMOTION_AUTHORITY

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "authority": self.authority,
            "promoted_sources": [
                {
                    "case_name": item.case_name,
                    "pattern_name": item.pattern_name,
                    "source_pattern_type": item.source_pattern_type,
                    "action_role": item.action_role,
                    "case_scale_factor": item.case_scale_factor,
                    "source_refs": list(item.source_refs),
                    "authority": item.authority,
                }
                for item in self.promoted_sources
            ],
            "excluded_cases": [item.as_dict() for item in self.excluded_cases],
        }


def _load_projection(case: EtabsStaticLinearCaseEvidence) -> tuple[dict[str, Any], ...]:
    return tuple(item.as_dict() for item in case.loads)


def promote_etabs_static_cases_to_ts500_stability_actions(
    cases: tuple[EtabsStaticLinearCaseEvidence, ...],
) -> EtabsTS500StabilityActionPromotion:
    """Promote eligible atomic ETABS cases using factual pattern type only."""
    if not cases:
        raise ValueError("at least one factual ETABS static-linear case is required")
    if len({item.name for item in cases}) != len(cases):
        raise ValueError("factual static-linear case names must be unique")

    promoted: list[StabilityActionSource] = []
    excluded: list[ExcludedStaticCaseActionEvidence] = []
    for case in cases:
        loads = case.loads
        if len(loads) != 1:
            excluded.append(
                ExcludedStaticCaseActionEvidence(
                    case_name=case.name,
                    reason="NOT_ATOMIC_SINGLE_LOAD_TERM",
                    factual_loads=_load_projection(case),
                )
            )
            continue
        term = loads[0]
        if term.load_type != "Load" or term.load_pattern is None:
            excluded.append(
                ExcludedStaticCaseActionEvidence(
                    case_name=case.name,
                    reason="NOT_FACTUAL_LOAD_PATTERN_TERM",
                    factual_loads=_load_projection(case),
                )
            )
            continue
        if abs(term.scale_factor - 1.0) > 1e-12:
            excluded.append(
                ExcludedStaticCaseActionEvidence(
                    case_name=case.name,
                    reason="NOT_UNIT_SCALE_ATOMIC_CASE",
                    factual_loads=_load_projection(case),
                )
            )
            continue
        role = ETABS_PATTERN_TYPE_TO_TS500_ACTION.get(term.load_pattern.type_name)
        if role is None:
            excluded.append(
                ExcludedStaticCaseActionEvidence(
                    case_name=case.name,
                    reason=f"PATTERN_TYPE_NOT_PROMOTED:{term.load_pattern.type_name}",
                    factual_loads=_load_projection(case),
                )
            )
            continue
        promoted.append(
            StabilityActionSource(
                case_name=case.name,
                pattern_name=term.load_name,
                source_pattern_type=term.load_pattern.type_name,
                action_role=role,
                case_scale_factor=term.scale_factor,
                source_refs=(
                    f"ETABS:StaticLinear.GetLoads:{case.name}",
                    f"ETABS:LoadPatterns.GetLoadType:{term.load_name}:{term.load_pattern.type_name}",
                    ETABS_TS500_ACTION_PROMOTION_AUTHORITY,
                ),
            )
        )

    status = (
        "PROVEN_TS500_STABILITY_ACTION_PROMOTION"
        if promoted
        else "BLOCKED_TS500_STABILITY_ACTION_PROMOTION"
    )
    return EtabsTS500StabilityActionPromotion(
        status=status,
        promoted_sources=tuple(promoted),
        excluded_cases=tuple(excluded),
    )


__all__ = [
    "ETABS_PATTERN_TYPE_TO_TS500_ACTION",
    "ETABS_TS500_ACTION_PROMOTION_AUTHORITY",
    "EtabsTS500StabilityActionPromotion",
    "ExcludedStaticCaseActionEvidence",
    "promote_etabs_static_cases_to_ts500_stability_actions",
]
