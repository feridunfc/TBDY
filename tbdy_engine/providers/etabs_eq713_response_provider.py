"""Factual Eq.7.13 member-response population bound to one qualified B5 generation.

The provider aggregates typed CSI local generalized-force result facts.  It does
not decide TS500 applicability or whether a stiffness mode participates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from tbdy_engine.etabs.oapi.eq713_response_results import (
    AreaForceShellResponseFact,
    FrameForceResponseFact,
    probe_eq713_response_results_capability_from_session,
    read_area_force_shell_response_from_session,
    read_frame_force_response_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession


@dataclass(frozen=True, slots=True)
class Eq713ResponsePopulationFact:
    model_fingerprint: str
    evidence_epoch_id: str
    analysis_result_ref: str
    execution_proof_ref: str
    case_names: tuple[str, ...]
    frame_names: tuple[str, ...]
    area_names: tuple[str, ...]
    frame_results: tuple[FrameForceResponseFact, ...]
    area_results: tuple[AreaForceShellResponseFact, ...]
    source_refs: tuple[str, ...]
    evidence_ref: str


def _names(values: Sequence[str], label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    result = tuple(values)
    if (not allow_empty and not result) or any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in result
    ):
        raise ValueError(f"{label} must be {'a ' if not allow_empty else 'an optional '}canonical string sequence")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _refs(values: Sequence[str], label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(values))
    if not allow_empty and not result:
        raise ValueError(f"{label} must not be empty")
    if any(not isinstance(value, str) or not value.strip() or value != value.strip() for value in result):
        raise ValueError(f"{label} must contain canonical strings")
    return result


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return "eq713-response-population:sha256:" + hashlib.sha256(encoded).hexdigest()


def probe_eq713_response_population_capability(
    session: EtabsVerifiedSession,
    *,
    require_frame: bool,
    require_area: bool,
) -> tuple[str, ...]:
    return probe_eq713_response_results_capability_from_session(
        session,
        require_frame=require_frame,
        require_area=require_area,
    )


def capture_eq713_response_population_from_session(
    session: EtabsVerifiedSession,
    *,
    model_fingerprint: str,
    evidence_epoch_id: str,
    analysis_result_ref: str,
    execution_proof_ref: str,
    case_names: Sequence[str],
    frame_names: Sequence[str] = (),
    area_names: Sequence[str] = (),
    case_scope_refs: Sequence[str] = (),
) -> Eq713ResponsePopulationFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    model = _text(model_fingerprint, "model_fingerprint")
    epoch = _text(evidence_epoch_id, "evidence_epoch_id")
    result_ref = _text(analysis_result_ref, "analysis_result_ref")
    execution_ref = _text(execution_proof_ref, "execution_proof_ref")
    cases = _names(case_names, "case_names")
    frames = _names(frame_names, "frame_names", allow_empty=True)
    areas = _names(area_names, "area_names", allow_empty=True)
    scope_refs = _refs(case_scope_refs, "case_scope_refs", allow_empty=True)
    if not frames and not areas:
        raise ValueError("at least one Frame or Area response target is required")

    frame_results = tuple(
        read_frame_force_response_from_session(session, frame_name=frame, case_name=case)
        for frame in frames
        for case in cases
    )
    area_results = tuple(
        read_area_force_shell_response_from_session(session, area_name=area, case_name=case)
        for area in areas
        for case in cases
    )

    if {(row.frame_name, row.case_name) for row in frame_results} != {
        (frame, case) for frame in frames for case in cases
    }:
        raise ValueError("Frame Eq713 response population is incomplete")
    if {(row.area_name, row.case_name) for row in area_results} != {
        (area, case) for area in areas for case in cases
    }:
        raise ValueError("Area Eq713 response population is incomplete")

    refs = tuple(
        dict.fromkeys(
            (
                result_ref,
                execution_ref,
                *scope_refs,
                *(row.evidence_ref for row in frame_results),
                *(row.evidence_ref for row in area_results),
            )
        )
    )
    evidence_ref = _digest(
        {
            "model_fingerprint": model,
            "evidence_epoch_id": epoch,
            "analysis_result_ref": result_ref,
            "execution_proof_ref": execution_ref,
            "case_names": cases,
            "case_scope_refs": scope_refs,
            "frame_names": frames,
            "area_names": areas,
            "frame_result_refs": [row.evidence_ref for row in frame_results],
            "area_result_refs": [row.evidence_ref for row in area_results],
        }
    )
    return Eq713ResponsePopulationFact(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        analysis_result_ref=result_ref,
        execution_proof_ref=execution_ref,
        case_names=cases,
        frame_names=frames,
        area_names=areas,
        frame_results=frame_results,
        area_results=area_results,
        source_refs=refs,
        evidence_ref=evidence_ref,
    )


__all__ = [
    "Eq713ResponsePopulationFact",
    "capture_eq713_response_population_from_session",
    "probe_eq713_response_population_capability",
]
