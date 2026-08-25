"""Strict TS500 7.6.2.1 stability action-role and load-basis inventory.

This module owns regulatory promotion rules only.  It consumes already factual,
source-bound atomic load-case action records and determines whether the action
inventory needed by TS500 Eq. 7.13 is available.

It deliberately does NOT infer roles from case names, does not assign seismic or
wind direction, does not read ETABS results, and does not calculate the story
stability index.  Directional E/W binding and the uncracked result basis remain
separate evidence closures.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


TS500_ACTION_G = "G"
TS500_ACTION_Q = "Q"
TS500_ACTION_E = "E"
TS500_ACTION_W = "W"
TS500_STABILITY_ACTION_ROLES = frozenset(
    {TS500_ACTION_G, TS500_ACTION_Q, TS500_ACTION_E, TS500_ACTION_W}
)

TS500_LOAD_BASIS_GQE = "TS500_FD_1.0G_1.0Q_1.0E"
TS500_LOAD_BASIS_GQW = "TS500_FD_1.0G_1.3Q_1.3W"

TS500_STABILITY_ACTION_AUTHORITY = "TS500_7.6.2.1_STABILITY_ACTION_ROLE"
TS500_STABILITY_LOAD_INVENTORY_AUTHORITY = "TS500_7.6.2.1_STABILITY_LOAD_INVENTORY"


class StabilityActionBasisError(ValueError):
    """Raised when promoted action evidence is malformed or inconsistent."""


@dataclass(frozen=True, slots=True)
class StabilityActionSource:
    case_name: str
    pattern_name: str
    source_pattern_type: str
    action_role: str
    case_scale_factor: float
    source_refs: tuple[str, ...]
    authority: str = TS500_STABILITY_ACTION_AUTHORITY


@dataclass(frozen=True, slots=True)
class StabilityLoadBasisTemplate:
    load_basis: str
    coefficients: Mapping[str, float]
    candidate_case_names_by_role: Mapping[str, tuple[str, ...]]
    missing_roles: tuple[str, ...]
    direction_binding_required_roles: tuple[str, ...]
    status: str
    source_refs: tuple[str, ...]
    authority: str = TS500_STABILITY_LOAD_INVENTORY_AUTHORITY

    @property
    def action_inventory_complete(self) -> bool:
        return not self.missing_roles

    @property
    def direction_binding_complete(self) -> bool:
        return not self.direction_binding_required_roles


@dataclass(frozen=True, slots=True)
class StabilityLoadInventoryResolution:
    status: str
    gqe: StabilityLoadBasisTemplate
    gqw: StabilityLoadBasisTemplate
    promoted_sources: tuple[StabilityActionSource, ...]
    source_refs: tuple[str, ...]
    authority: str = TS500_STABILITY_LOAD_INVENTORY_AUTHORITY

    @property
    def both_action_inventories_complete(self) -> bool:
        return self.gqe.action_inventory_complete and self.gqw.action_inventory_complete


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StabilityActionBasisError(f"{label} must be a nonblank canonical string")
    return value


def _source_map(sources: tuple[StabilityActionSource, ...]) -> dict[str, tuple[StabilityActionSource, ...]]:
    by_role: dict[str, list[StabilityActionSource]] = {
        role: [] for role in sorted(TS500_STABILITY_ACTION_ROLES)
    }
    seen_cases: set[str] = set()
    for source in sources:
        case_name = _text(source.case_name, "case_name")
        _text(source.pattern_name, f"{case_name}.pattern_name")
        _text(source.source_pattern_type, f"{case_name}.source_pattern_type")
        if case_name in seen_cases:
            raise StabilityActionBasisError(f"duplicate promoted action case: {case_name}")
        seen_cases.add(case_name)
        if source.action_role not in TS500_STABILITY_ACTION_ROLES:
            raise StabilityActionBasisError(
                f"{case_name}.action_role must be one of {sorted(TS500_STABILITY_ACTION_ROLES)}"
            )
        if abs(float(source.case_scale_factor) - 1.0) > 1e-12:
            raise StabilityActionBasisError(
                f"{case_name} is not an atomic unit-scale action case"
            )
        if source.authority != TS500_STABILITY_ACTION_AUTHORITY:
            raise StabilityActionBasisError(f"{case_name} has unsupported action-role authority")
        if not source.source_refs or len(set(source.source_refs)) != len(source.source_refs):
            raise StabilityActionBasisError(f"{case_name}.source_refs must be nonempty and unique")
        for ref in source.source_refs:
            _text(ref, f"{case_name}.source_ref")
        by_role[source.action_role].append(source)
    return {role: tuple(values) for role, values in by_role.items()}


def _template(
    *,
    load_basis: str,
    coefficients: Mapping[str, float],
    by_role: Mapping[str, tuple[StabilityActionSource, ...]],
) -> StabilityLoadBasisTemplate:
    required = tuple(coefficients.keys())
    missing = tuple(role for role in required if not by_role.get(role))
    # Direction is a separate factual closure.  Merely knowing that a source is
    # QUAKE or WIND does not prove whether it belongs to X or Y.
    directional = tuple(
        role for role in required
        if role in {TS500_ACTION_E, TS500_ACTION_W} and by_role.get(role)
    )
    candidates = MappingProxyType(
        {
            role: tuple(item.case_name for item in by_role.get(role, ()))
            for role in required
        }
    )
    refs = tuple(
        dict.fromkeys(
            ref
            for role in required
            for item in by_role.get(role, ())
            for ref in item.source_refs
        )
    )
    if missing:
        status = "BLOCKED_TS500_STABILITY_ACTION_INVENTORY"
    elif directional:
        status = "BLOCKED_TS500_STABILITY_DIRECTION_BINDING"
    else:
        status = "PROVEN_TS500_STABILITY_LOAD_BASIS_TEMPLATE"
    return StabilityLoadBasisTemplate(
        load_basis=load_basis,
        coefficients=MappingProxyType(dict(coefficients)),
        candidate_case_names_by_role=candidates,
        missing_roles=missing,
        direction_binding_required_roles=directional,
        status=status,
        source_refs=refs,
    )


def resolve_ts500_stability_load_inventory(
    sources: tuple[StabilityActionSource, ...],
) -> StabilityLoadInventoryResolution:
    """Resolve the action inventory for the two TS500 Eq. 7.13 load bases.

    This produces symbolic basis templates only.  E/W directional binding,
    result-row reconstruction and the required uncracked stiffness basis are
    deliberately outside this function.
    """
    if not sources:
        raise StabilityActionBasisError("at least one promoted stability action source is required")
    by_role = _source_map(sources)
    gqe = _template(
        load_basis=TS500_LOAD_BASIS_GQE,
        coefficients={TS500_ACTION_G: 1.0, TS500_ACTION_Q: 1.0, TS500_ACTION_E: 1.0},
        by_role=by_role,
    )
    gqw = _template(
        load_basis=TS500_LOAD_BASIS_GQW,
        coefficients={TS500_ACTION_G: 1.0, TS500_ACTION_Q: 1.3, TS500_ACTION_W: 1.3},
        by_role=by_role,
    )
    if gqe.action_inventory_complete and gqw.action_inventory_complete:
        status = "PROVEN_TS500_STABILITY_ACTION_INVENTORY"
    else:
        status = "BLOCKED_TS500_STABILITY_ACTION_INVENTORY"
    refs = tuple(dict.fromkeys(ref for item in sources for ref in item.source_refs))
    return StabilityLoadInventoryResolution(
        status=status,
        gqe=gqe,
        gqw=gqw,
        promoted_sources=sources,
        source_refs=refs,
    )


__all__ = [
    "StabilityActionBasisError",
    "StabilityActionSource",
    "StabilityLoadBasisTemplate",
    "StabilityLoadInventoryResolution",
    "TS500_ACTION_E",
    "TS500_ACTION_G",
    "TS500_ACTION_Q",
    "TS500_ACTION_W",
    "TS500_LOAD_BASIS_GQE",
    "TS500_LOAD_BASIS_GQW",
    "TS500_STABILITY_ACTION_AUTHORITY",
    "TS500_STABILITY_LOAD_INVENTORY_AUTHORITY",
    "resolve_ts500_stability_load_inventory",
]
