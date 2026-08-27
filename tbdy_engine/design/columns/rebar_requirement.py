"""Role-preserving longitudinal reinforcement requirement set for VS6-P8A.

The P8A layer does not collapse ETABS factual requirements into one scalar and
does not derive the TBDY minimum.  It consumes an already-established
``TBDY_MIN_REQUIRED_REBAR`` quantity plus every exact ``ETABS_REQUIRED_REBAR``
row, then exposes a conjunction of requirements under the distinct
``GOVERNING_REQUIRED_REBAR`` role.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Sequence

from tbdy_engine.features.column_design_rebar_evidence import EtabsRequiredRebarComponent


ETABS_REQUIRED_REBAR = "ETABS_REQUIRED_REBAR"
TBDY_MIN_REQUIRED_REBAR = "TBDY_MIN_REQUIRED_REBAR"
GOVERNING_REQUIRED_REBAR = "GOVERNING_REQUIRED_REBAR"


class RebarRequirementError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RebarRequirementError(f"{label} must be a nonblank canonical string")
    return value


def _nonnegative_decimal(value: object, label: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise RebarRequirementError(f"{label} must be finite and >= 0")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RebarRequirementError(f"{label} must be finite and >= 0") from exc
    if not result.is_finite() or result < 0:
        raise RebarRequirementError(f"{label} must be finite and >= 0")
    return Decimal(0) if result == 0 else result.normalize()


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(ref, label) for ref in values)
    if not refs or len(refs) != len(set(refs)):
        raise RebarRequirementError(f"{label} must be nonempty and unique")
    return refs


@dataclass(frozen=True, slots=True)
class RebarRequirementState:
    requirement_id: str
    role: str
    required_as_mm2: Decimal
    component_id: str
    section_identity: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _text(self.requirement_id, "requirement_id"))
        role = _text(self.role, "role")
        if role not in {ETABS_REQUIRED_REBAR, TBDY_MIN_REQUIRED_REBAR}:
            raise RebarRequirementError("unsupported longitudinal requirement role")
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "required_as_mm2", _nonnegative_decimal(self.required_as_mm2, "required_as_mm2"))
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "section_identity", _text(self.section_identity, "section_identity"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))


@dataclass(frozen=True, slots=True)
class GoverningRequiredRebar:
    """Conjunctive requirement set; deliberately no max/envelope reduction."""

    component_id: str
    section_identity: str
    states: tuple[RebarRequirementState, ...]
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]
    authority: str = GOVERNING_REQUIRED_REBAR

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "section_identity", _text(self.section_identity, "section_identity"))
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        states = tuple(self.states)
        if len(states) < 2 or any(not isinstance(item, RebarRequirementState) for item in states):
            raise RebarRequirementError("governing requirement requires typed ETABS and TBDY states")
        if any(
            item.component_id != self.component_id
            or item.section_identity != self.section_identity
            for item in states
        ):
            raise RebarRequirementError("requirement state component/section identity mismatch")
        roles = {item.role for item in states}
        if roles != {ETABS_REQUIRED_REBAR, TBDY_MIN_REQUIRED_REBAR}:
            raise RebarRequirementError("governing requirement must preserve ETABS and TBDY roles")
        ids = tuple(item.requirement_id for item in states)
        if len(ids) != len(set(ids)):
            raise RebarRequirementError("requirement identities must be unique")
        object.__setattr__(self, "states", tuple(sorted(states, key=lambda item: item.requirement_id)))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != GOVERNING_REQUIRED_REBAR:
            raise RebarRequirementError("governing requirement authority label mismatch")


@dataclass(frozen=True, slots=True)
class CandidateRequirementTrial:
    candidate_id: str
    requirement_id: str
    role: str
    candidate_as_mm2: Decimal
    required_as_mm2: Decimal
    status: str


def build_governing_required_rebar(
    *,
    etabs_required: EtabsRequiredRebarComponent,
    tdby_min_required_as_mm2: object,
    tdby_min_source_refs: Sequence[str],
) -> GoverningRequiredRebar:
    """Join source-distinct requirements without recomputing either authority."""
    if not isinstance(etabs_required, EtabsRequiredRebarComponent):
        raise TypeError("etabs_required must be EtabsRequiredRebarComponent")
    tdby_required = _nonnegative_decimal(tdby_min_required_as_mm2, "tdby_min_required_as_mm2")
    tdby_refs = _refs(tdby_min_source_refs, "tdby_min_source_ref")

    states: list[RebarRequirementState] = [
        RebarRequirementState(
            requirement_id=item.requirement_id,
            role=ETABS_REQUIRED_REBAR,
            required_as_mm2=item.required_as_mm2,
            component_id=etabs_required.component_id,
            section_identity=etabs_required.design_section,
            source_refs=item.source_refs,
        )
        for item in etabs_required.requirements
    ]
    states.append(
        RebarRequirementState(
            requirement_id=f"tdby-min-required-rebar:{etabs_required.component_id}",
            role=TBDY_MIN_REQUIRED_REBAR,
            required_as_mm2=tdby_required,
            component_id=etabs_required.component_id,
            section_identity=etabs_required.design_section,
            source_refs=tdby_refs,
        )
    )
    refs = tuple(
        dict.fromkeys(
            (
                *etabs_required.source_refs,
                *tdby_refs,
                *(ref for state in states for ref in state.source_refs),
            )
        )
    )
    return GoverningRequiredRebar(
        component_id=etabs_required.component_id,
        section_identity=etabs_required.design_section,
        states=tuple(states),
        model_fingerprint=etabs_required.model_fingerprint,
        evidence_epoch_id=etabs_required.evidence_epoch_id,
        source_refs=refs,
    )


def evaluate_candidate_requirement_states(
    *,
    candidate_id: str,
    candidate_as_mm2: object,
    requirements: GoverningRequiredRebar,
) -> tuple[CandidateRequirementTrial, ...]:
    """Evaluate every requirement independently; no scalar governing reduction."""
    candidate = _nonnegative_decimal(candidate_as_mm2, "candidate_as_mm2")
    cid = _text(candidate_id, "candidate_id")
    return tuple(
        CandidateRequirementTrial(
            candidate_id=cid,
            requirement_id=state.requirement_id,
            role=state.role,
            candidate_as_mm2=candidate,
            required_as_mm2=state.required_as_mm2,
            status=("SATISFIED" if candidate >= state.required_as_mm2 else "NOT_SATISFIED"),
        )
        for state in requirements.states
    )


__all__ = [
    "ETABS_REQUIRED_REBAR",
    "TBDY_MIN_REQUIRED_REBAR",
    "GOVERNING_REQUIRED_REBAR",
    "CandidateRequirementTrial",
    "GoverningRequiredRebar",
    "RebarRequirementError",
    "RebarRequirementState",
    "build_governing_required_rebar",
    "evaluate_candidate_requirement_states",
]
