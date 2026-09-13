"""Source-bound qualification of signed concurrent TS500 stability outputs.

The ETABS ``JointDispl`` boundary is factual only.  This module binds one exact
stability-combo candidate to an independently proven global direction and to the
qualified B5 result generation.  Only existing LINEAR_ADD stability combos are
promoted to the supported signed/concurrent algebraic output semantics.

This module does not read ETABS results and does not compute TS500 Delta-i.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from tbdy_engine.design.columns.stability_combo_basis import (
    STABILITY_COMBO_AUTHORITY,
    StabilityComboCandidate,
)


SIGNED_LINEAR_ADD_STATE = "SIGNED_CONCURRENT_LINEAR_ADD_OUTPUT_STATE"
STABILITY_OUTPUT_STATE_AUTHORITY = "B5_TS500_STABILITY_SIGNED_OUTPUT_STATE"


class StabilityOutputStateError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StabilityOutputStateError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    refs = tuple(_text(value, label) for value in values)
    if not refs or len(refs) != len(set(refs)):
        raise StabilityOutputStateError(f"{label} must be nonempty and unique")
    return refs


def _stable_ref(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "stability-output-state:sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class StabilityActionDirectionBinding:
    case_name: str
    global_direction: str
    source_refs: tuple[str, ...]
    authority: str = "FACTUAL_HORIZONTAL_ACTION_DIRECTION_BINDING"

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_name", _text(self.case_name, "case_name"))
        direction = _text(self.global_direction, "global_direction")
        if direction not in {"X", "Y"}:
            raise StabilityOutputStateError("global_direction must be X or Y")
        object.__setattr__(self, "global_direction", direction)
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "direction.source_ref"))


@dataclass(frozen=True, slots=True)
class StabilityConcurrentOutputStateBinding:
    output_name: str
    output_kind: str
    load_basis: str
    horizontal_case_name: str
    global_direction: str
    combination_method: str
    state_semantics: str
    required_step_type: str
    required_step_number: float
    analysis_result_ref: str
    execution_proof_ref: str
    source_refs: tuple[str, ...]
    binding_ref: str
    authority: str = STABILITY_OUTPUT_STATE_AUTHORITY


def qualify_signed_linear_add_stability_output(
    candidate: StabilityComboCandidate,
    *,
    direction_binding: StabilityActionDirectionBinding,
    analysis_result_ref: str,
    execution_proof_ref: str,
) -> StabilityConcurrentOutputStateBinding:
    """Qualify the bounded exact signed/concurrent stability-output representation.

    ``StabilityComboCandidate`` is created only by the existing exact
    ``FlattenedLinearCombo`` role-matching authority.  For this supported slice,
    a CSI linear-add combination is consumed only when ``JointDispl`` returns
    the single algebraic state (blank StepType / zero StepNum).  Envelope or
    permutation states are therefore never admitted by this binding.
    """
    if not isinstance(candidate, StabilityComboCandidate):
        raise TypeError("candidate must be StabilityComboCandidate")
    if candidate.authority != STABILITY_COMBO_AUTHORITY:
        raise StabilityOutputStateError("candidate does not carry canonical stability-combo authority")
    if not isinstance(direction_binding, StabilityActionDirectionBinding):
        raise TypeError("direction_binding must be StabilityActionDirectionBinding")
    if direction_binding.case_name != candidate.horizontal_case_name:
        raise StabilityOutputStateError(
            "direction binding case does not match stability candidate horizontal case"
        )
    analysis_ref = _text(analysis_result_ref, "analysis_result_ref")
    proof_ref = _text(execution_proof_ref, "execution_proof_ref")
    refs = tuple(
        dict.fromkeys(
            (
                analysis_ref,
                proof_ref,
                *candidate.source_refs,
                *direction_binding.source_refs,
                f"stability-combo:{candidate.combo_name}:LINEAR_ADD",
                f"stability-direction:{candidate.horizontal_case_name}:{direction_binding.global_direction}",
            )
        )
    )
    payload = {
        "output_name": candidate.combo_name,
        "output_kind": "combo",
        "load_basis": candidate.load_basis,
        "horizontal_case_name": candidate.horizontal_case_name,
        "global_direction": direction_binding.global_direction,
        "combination_method": "LINEAR_ADD",
        "state_semantics": SIGNED_LINEAR_ADD_STATE,
        "required_step_type": "",
        "required_step_number": 0.0,
        "analysis_result_ref": analysis_ref,
        "execution_proof_ref": proof_ref,
        "source_refs": list(refs),
    }
    return StabilityConcurrentOutputStateBinding(
        output_name=candidate.combo_name,
        output_kind="combo",
        load_basis=candidate.load_basis,
        horizontal_case_name=candidate.horizontal_case_name,
        global_direction=direction_binding.global_direction,
        combination_method="LINEAR_ADD",
        state_semantics=SIGNED_LINEAR_ADD_STATE,
        required_step_type="",
        required_step_number=0.0,
        analysis_result_ref=analysis_ref,
        execution_proof_ref=proof_ref,
        source_refs=refs,
        binding_ref=_stable_ref(payload),
    )


__all__ = [
    "SIGNED_LINEAR_ADD_STATE",
    "STABILITY_OUTPUT_STATE_AUTHORITY",
    "StabilityActionDirectionBinding",
    "StabilityConcurrentOutputStateBinding",
    "StabilityOutputStateError",
    "qualify_signed_linear_add_stability_output",
]
