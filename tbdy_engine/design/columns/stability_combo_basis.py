"""TS500 7.6.2.1 stability-combination identity resolution.

This module never infers engineering meaning from ETABS case/combo names.  It
consumes already promoted atomic action roles and flattened LINEAR_ADD combo
constituents, then identifies only exact existing combinations matching the two
TS500 Eq.7.13 load bases.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

from tbdy_engine.design.columns.stability_action_basis import (
    StabilityActionSource,
    TS500_ACTION_E,
    TS500_ACTION_G,
    TS500_ACTION_Q,
    TS500_ACTION_W,
    TS500_LOAD_BASIS_GQE,
    TS500_LOAD_BASIS_GQW,
)


class StabilityComboBasisError(ValueError):
    """Raised when stability-combo identity inputs are malformed."""


STABILITY_COMBO_AUTHORITY = "TS500_7.6.2.1_EXISTING_COMBO_ROLE_MATCH"


@dataclass(frozen=True, slots=True)
class FlattenedLinearCombo:
    name: str
    constituents: tuple[tuple[str, float], ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StabilityComboCandidate:
    combo_name: str
    load_basis: str
    horizontal_action_role: str
    horizontal_case_name: str
    horizontal_scale_factor: float
    role_coefficients: tuple[tuple[str, float], ...]
    constituent_case_names: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = STABILITY_COMBO_AUTHORITY


@dataclass(frozen=True, slots=True)
class StabilityComboResolution:
    status: str
    gqe_candidates: tuple[StabilityComboCandidate, ...]
    gqw_candidates: tuple[StabilityComboCandidate, ...]
    excluded_combo_names: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = STABILITY_COMBO_AUTHORITY

    @property
    def both_bases_present(self) -> bool:
        return bool(self.gqe_candidates) and bool(self.gqw_candidates)


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StabilityComboBasisError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise StabilityComboBasisError(f"{label} must be finite")
    return result


def _close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=1e-10)


def _candidate(
    combo: FlattenedLinearCombo,
    *,
    source_by_case: Mapping[str, StabilityActionSource],
    load_basis: str,
) -> StabilityComboCandidate | None:
    if not combo.constituents:
        return None

    terms: list[tuple[StabilityActionSource, float]] = []
    for case_name_raw, scale_raw in combo.constituents:
        case_name = _text(case_name_raw, "constituent.case_name")
        source = source_by_case.get(case_name)
        if source is None:
            return None
        scale = _finite(scale_raw, f"{combo.name}:{case_name}.scale_factor")
        terms.append((source, scale))

    by_role: dict[str, float] = {}
    cases_by_role: dict[str, list[tuple[str, float]]] = {}
    for source, scale in terms:
        by_role[source.action_role] = by_role.get(source.action_role, 0.0) + scale
        cases_by_role.setdefault(source.action_role, []).append((source.case_name, scale))

    if load_basis == TS500_LOAD_BASIS_GQE:
        expected = {TS500_ACTION_G: 1.0, TS500_ACTION_Q: 1.0}
        horizontal_role = TS500_ACTION_E
        horizontal_magnitude = 1.0
        forbidden = TS500_ACTION_W
    elif load_basis == TS500_LOAD_BASIS_GQW:
        expected = {TS500_ACTION_G: 1.0, TS500_ACTION_Q: 1.3}
        horizontal_role = TS500_ACTION_W
        horizontal_magnitude = 1.3
        forbidden = TS500_ACTION_E
    else:
        raise StabilityComboBasisError(f"unsupported stability load basis {load_basis!r}")

    if forbidden in by_role and not _close(by_role[forbidden], 0.0):
        return None
    if set(by_role) - {TS500_ACTION_G, TS500_ACTION_Q, horizontal_role}:
        return None
    for role, coefficient in expected.items():
        if not _close(by_role.get(role, 0.0), coefficient):
            return None

    horizontal_terms = tuple(cases_by_role.get(horizontal_role, ()))
    if len(horizontal_terms) != 1:
        # Exact directional identity requires one atomic horizontal action case.
        # Orthogonal/accidental combinations such as EX+0.3EY are deliberately
        # not promoted to the Eq.7.13 single-direction basis.
        return None
    horizontal_case, horizontal_scale = horizontal_terms[0]
    if not _close(abs(horizontal_scale), horizontal_magnitude):
        return None
    if not _close(by_role.get(horizontal_role, 0.0), horizontal_scale):
        return None

    refs = tuple(
        dict.fromkeys(
            (
                *combo.source_refs,
                *(ref for source, _scale in terms for ref in source.source_refs),
                f"TS500 7.6.2.1:{load_basis}",
            )
        )
    )
    return StabilityComboCandidate(
        combo_name=combo.name,
        load_basis=load_basis,
        horizontal_action_role=horizontal_role,
        horizontal_case_name=horizontal_case,
        horizontal_scale_factor=horizontal_scale,
        role_coefficients=tuple(sorted((role, value) for role, value in by_role.items())),
        constituent_case_names=tuple(case for case, _scale in combo.constituents),
        source_refs=refs,
    )


def resolve_existing_ts500_stability_combos(
    combos: Sequence[FlattenedLinearCombo],
    promoted_sources: Sequence[StabilityActionSource],
) -> StabilityComboResolution:
    """Find existing exact G+Q+E and G+1.3Q+1.3W LINEAR_ADD combinations."""
    combo_rows = tuple(combos)
    sources = tuple(promoted_sources)
    if not combo_rows:
        raise StabilityComboBasisError("at least one flattened combo is required")
    if len({item.name for item in combo_rows}) != len(combo_rows):
        raise StabilityComboBasisError("flattened combo names must be unique")
    if not sources:
        return StabilityComboResolution(
            status="BLOCKED_TS500_STABILITY_ACTION_PROMOTION",
            gqe_candidates=(),
            gqw_candidates=(),
            excluded_combo_names=tuple(sorted(item.name for item in combo_rows)),
            source_refs=("TS500 stability action promotion produced no atomic sources",),
        )
    if len({item.case_name for item in sources}) != len(sources):
        raise StabilityComboBasisError("promoted stability case names must be unique")
    source_by_case = {item.case_name: item for item in sources}

    gqe: list[StabilityComboCandidate] = []
    gqw: list[StabilityComboCandidate] = []
    excluded: list[str] = []
    for combo in combo_rows:
        _text(combo.name, "combo.name")
        if not combo.source_refs:
            raise StabilityComboBasisError(f"{combo.name}.source_refs must be nonempty")
        gqe_candidate = _candidate(combo, source_by_case=source_by_case, load_basis=TS500_LOAD_BASIS_GQE)
        gqw_candidate = _candidate(combo, source_by_case=source_by_case, load_basis=TS500_LOAD_BASIS_GQW)
        if gqe_candidate is not None:
            gqe.append(gqe_candidate)
        if gqw_candidate is not None:
            gqw.append(gqw_candidate)
        if gqe_candidate is None and gqw_candidate is None:
            excluded.append(combo.name)

    refs = tuple(
        dict.fromkeys(
            ref
            for item in (*gqe, *gqw)
            for ref in item.source_refs
        )
    )
    status = (
        "PROVEN_TS500_STABILITY_COMBO_SCOPE"
        if gqe and gqw
        else "BLOCKED_TS500_STABILITY_COMBO_SCOPE"
    )
    return StabilityComboResolution(
        status=status,
        gqe_candidates=tuple(sorted(gqe, key=lambda item: item.combo_name)),
        gqw_candidates=tuple(sorted(gqw, key=lambda item: item.combo_name)),
        excluded_combo_names=tuple(sorted(excluded)),
        source_refs=refs,
    )


__all__ = [
    "FlattenedLinearCombo",
    "STABILITY_COMBO_AUTHORITY",
    "StabilityComboBasisError",
    "StabilityComboCandidate",
    "StabilityComboResolution",
    "resolve_existing_ts500_stability_combos",
]
