"""Role-preserving longitudinal-reinforcement requirement ledger for VS6-P8A."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.features.column_design_rebar_evidence import EtabsRequiredRebar


class RebarRequirementError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RebarRequirementError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RebarRequirementError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise RebarRequirementError(f"{label} must be finite and > 0")
    return result


@dataclass(frozen=True, slots=True)
class RebarRequirementState:
    role: str
    required_as_mm2: float
    component_id: str
    section_identity: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        role = _text(self.role, "role")
        if role not in {"ETABS_REQUIRED_REBAR", "TBDY_MIN_REQUIRED_REBAR"}:
            raise RebarRequirementError("unsupported requirement role")
        object.__setattr__(self, "required_as_mm2", _positive(self.required_as_mm2, "required_as_mm2"))
        _text(self.component_id, "component_id")
        _text(self.section_identity, "section_identity")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise RebarRequirementError("source_refs must be nonempty and unique")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class GoverningRequiredRebar:
    component_id: str
    section_identity: str
    states: tuple[RebarRequirementState, ...]
    governing_required_as_mm2: float
    governing_roles: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = "GOVERNING_REQUIRED_REBAR"

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        _text(self.section_identity, "section_identity")
        states = tuple(self.states)
        if len(states) < 2:
            raise RebarRequirementError("governing ledger requires source-distinct ETABS and TBDY states")
        if any(item.component_id != self.component_id or item.section_identity != self.section_identity for item in states):
            raise RebarRequirementError("requirement state identity mismatch")
        if {item.role for item in states} != {"ETABS_REQUIRED_REBAR", "TBDY_MIN_REQUIRED_REBAR"}:
            raise RebarRequirementError("governing ledger must preserve ETABS and TBDY minimum roles")
        expected = max(item.required_as_mm2 for item in states)
        value = _positive(self.governing_required_as_mm2, "governing_required_as_mm2")
        if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-9):
            raise RebarRequirementError("governing_required_as_mm2 is not the exact requirement maximum")
        expected_roles = tuple(sorted(item.role for item in states if math.isclose(item.required_as_mm2, expected, rel_tol=0.0, abs_tol=1e-9)))
        if tuple(self.governing_roles) != expected_roles:
            raise RebarRequirementError("governing_roles do not match governing source state(s)")
        refs = tuple(_text(ref, "source_ref") for ref in self.source_refs)
        if not refs or len(refs) != len(set(refs)):
            raise RebarRequirementError("source_refs must be nonempty and unique")
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "source_refs", refs)

    def as_dict(self) -> dict[str, object]:
        return {"authority": self.authority, "component_id": self.component_id, "section_identity": self.section_identity, "governing_required_as_mm2": self.governing_required_as_mm2, "unit": "mm2", "governing_roles": list(self.governing_roles), "states": [{"role": item.role, "required_as_mm2": item.required_as_mm2, "unit": "mm2", "source_refs": list(item.source_refs)} for item in self.states], "source_refs": list(self.source_refs)}


def build_governing_required_rebar(*, etabs_required: EtabsRequiredRebar, width_mm: float, depth_mm: float, tdby_rho_min: float, tdby_source_refs: Sequence[str]) -> GoverningRequiredRebar:
    if not etabs_required.resolved or etabs_required.required_as_mm2 is None:
        raise RebarRequirementError("resolved ETABS_REQUIRED_REBAR is required")
    width = _positive(width_mm, "width_mm")
    depth = _positive(depth_mm, "depth_mm")
    rho = float(tdby_rho_min)
    if not math.isfinite(rho) or rho <= 0.0:
        raise RebarRequirementError("tdby_rho_min must be finite and > 0")
    tdby_refs = tuple(_text(ref, "tdby_source_ref") for ref in tdby_source_refs)
    if not tdby_refs:
        raise RebarRequirementError("tdby_source_refs must be nonempty")
    etabs_state = RebarRequirementState("ETABS_REQUIRED_REBAR", etabs_required.required_as_mm2, etabs_required.component_id, etabs_required.section_identity, etabs_required.source_refs)
    tdby_state = RebarRequirementState("TBDY_MIN_REQUIRED_REBAR", width * depth * rho, etabs_required.component_id, etabs_required.section_identity, tdby_refs)
    states = (etabs_state, tdby_state)
    maximum = max(item.required_as_mm2 for item in states)
    governing_roles = tuple(sorted(item.role for item in states if math.isclose(item.required_as_mm2, maximum, rel_tol=0.0, abs_tol=1e-9)))
    refs = tuple(dict.fromkeys(ref for state in states for ref in state.source_refs))
    return GoverningRequiredRebar(etabs_required.component_id, etabs_required.section_identity, states, maximum, governing_roles, refs)


__all__ = ["RebarRequirementError", "RebarRequirementState", "GoverningRequiredRebar", "build_governing_required_rebar"]
