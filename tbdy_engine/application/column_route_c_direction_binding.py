"""Source-bound Route-C horizontal action direction composition for COLUMN-R1.

This module deliberately owns no direction inference.  ETABS static-linear
cases are first promoted to TS500 action roles from factual load-pattern type.
Seismic E directions are then bound only through the existing live-proven
TSC2018 auto-seismic direction table.  The repository currently has no
source-bound wind-direction owner; W therefore remains explicit unresolved
rather than being inferred from case/pattern naming.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.stability_action_basis import TS500_ACTION_E, TS500_ACTION_W
from tbdy_engine.design.columns.stability_output_state import StabilityActionDirectionBinding
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.providers.etabs_auto_seismic_direction_provider import (
    bind_etabs_seismic_action_directions,
    capture_etabs_auto_seismic_direction_evidence_from_session,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    capture_etabs_static_linear_cases_from_session,
)
from tbdy_engine.providers.etabs_ts500_stability_action_provider import (
    promote_etabs_static_cases_to_ts500_stability_actions,
)

ROUTE_C_DIRECTION_READY = "READY"
ROUTE_C_DIRECTION_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
ROUTE_C_DIRECTION_AUTHORITY = "COLUMN_R1_ROUTE_C_SOURCE_BOUND_DIRECTION_BINDING"
WIND_DIRECTION_BLOCKER = "ROUTE_C_W_DIRECTION_SOURCE_BOUND_EVIDENCE_NOT_AVAILABLE"


@dataclass(frozen=True, slots=True)
class RouteCDirectionBindingResolution:
    status: str
    bindings: tuple[StabilityActionDirectionBinding, ...]
    blockers: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = ROUTE_C_DIRECTION_AUTHORITY

    @property
    def ready(self) -> bool:
        return self.status == ROUTE_C_DIRECTION_READY


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def resolve_route_c_source_bound_directions(
    *,
    session: EtabsVerifiedSession,
    static_case_names: Sequence[str],
) -> RouteCDirectionBindingResolution:
    """Resolve only directions that are proven by existing factual authorities.

    No case/load/pattern name is parsed for X/Y meaning.  Until a source-bound
    wind-direction factual owner exists, any promoted W action is retained as
    an explicit unresolved Route-C edge.
    """
    names = tuple(static_case_names)
    if not names or len(names) != len(set(names)):
        raise ValueError("static_case_names must be a nonempty unique sequence")

    cases = capture_etabs_static_linear_cases_from_session(session, names)
    promotion = promote_etabs_static_cases_to_ts500_stability_actions(cases)
    sources = promotion.promoted_sources
    e_sources = tuple(item for item in sources if item.action_role == TS500_ACTION_E)
    w_sources = tuple(item for item in sources if item.action_role == TS500_ACTION_W)

    bindings: list[StabilityActionDirectionBinding] = []
    blockers: list[str] = []
    refs: list[str] = [ROUTE_C_DIRECTION_AUTHORITY, promotion.authority]

    if e_sources:
        seismic_table = capture_etabs_auto_seismic_direction_evidence_from_session(session)
        seismic = bind_etabs_seismic_action_directions(tuple(sources), seismic_table)
        refs.extend(seismic.source_refs)
        if not seismic.complete:
            blockers.append(f"ROUTE_C_E_DIRECTION:{seismic.status}")
        for item in seismic.bindings:
            bindings.append(
                StabilityActionDirectionBinding(
                    case_name=item.case_name,
                    global_direction=item.direction,
                    source_refs=item.source_refs,
                    authority=item.authority,
                )
            )
    else:
        blockers.append("ROUTE_C_E_ACTION_SOURCE_NOT_PROVEN")

    if w_sources:
        for source in w_sources:
            blockers.append(f"{WIND_DIRECTION_BLOCKER}:{source.case_name}")
            refs.extend(source.source_refs)
    else:
        blockers.append("ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN")

    unique_bindings = {(item.case_name, item.global_direction) for item in bindings}
    if len(unique_bindings) != len(bindings):
        blockers.append("ROUTE_C_DIRECTION_BINDING_NOT_UNIQUE")

    status = (
        ROUTE_C_DIRECTION_READY
        if not blockers and {item.global_direction for item in bindings} == {"X", "Y"}
        else ROUTE_C_DIRECTION_EXPLICIT_UNRESOLVED
    )
    return RouteCDirectionBindingResolution(
        status=status,
        bindings=tuple(bindings),
        blockers=tuple(dict.fromkeys(blockers)),
        source_refs=_refs((*refs, *(ref for item in bindings for ref in item.source_refs))),
    )


__all__ = [
    "ROUTE_C_DIRECTION_AUTHORITY",
    "ROUTE_C_DIRECTION_EXPLICIT_UNRESOLVED",
    "ROUTE_C_DIRECTION_READY",
    "RouteCDirectionBindingResolution",
    "WIND_DIRECTION_BLOCKER",
    "resolve_route_c_source_bound_directions",
]
