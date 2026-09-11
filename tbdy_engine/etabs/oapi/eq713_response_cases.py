"""Typed factual qualification of horizontal inertial load cases for Eq.7.13 response evidence.

Only CSI case/load metadata is interpreted here.  This module does not decide
TS500 participation or modifier targets.  It proves that every earthquake-type
candidate case used for member-response classification is a clean horizontal
inertial case, so gravity/member-load response cannot masquerade as Eq.7.13
horizontal participation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError

_LINEAR_STATIC = 1
_RESPONSE_SPECTRUM = 4
_QUAKE = 5
_AUTO_SEISMIC_DIRECTION_AUTHORITY = "ETABS_AUTO_SEISMIC_TSC2018_DIRECTION_FLAGS"
_AUTO_SEISMIC_TABLE = "Load Pattern Definitions - Auto Seismic - TSC 2018"


@dataclass(frozen=True, slots=True)
class Eq713HorizontalCaseFact:
    case_name: str
    case_type: str
    design_type_code: int
    direction_vectors_xy: tuple[tuple[float, float], ...]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Eq713HorizontalCaseScope:
    candidate_case_names: tuple[str, ...]
    case_names: tuple[str, ...]
    cases: tuple[Eq713HorizontalCaseFact, ...]
    direction_rank: int
    source_refs: tuple[str, ...]
    evidence_ref: str


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EtabsOAPIError(f"{label} must be an integer")
    return int(value)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite")
    return result


def _seq(value: object, label: str, count: int) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)) or len(value) < count:
        raise EtabsOAPIError(f"{label} must contain at least {count} values")
    return tuple(value[:count])


def _ret(value: object, method: str) -> int:
    ret = _int(value, f"{method}.ret")
    if ret != 0:
        raise EtabsOAPIError(f"{method} returned nonzero code {ret}")
    return ret


def _case_type(raw: object, case_name: str) -> tuple[int, int]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 6:
        raise EtabsOAPIError(f"LoadCases.GetTypeOAPI_1({case_name!r}) returned unexpected ABI shape: {raw!r}")
    case_type = _int(raw[0], "GetTypeOAPI_1.CaseType")
    design_type = _int(raw[2], "GetTypeOAPI_1.DesignType")
    _ret(raw[5], "LoadCases.GetTypeOAPI_1")
    return case_type, design_type


def _response_spectrum_vectors(raw: object, case_name: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 7:
        raise EtabsOAPIError(f"ResponseSpectrum.GetLoads({case_name!r}) returned unexpected ABI shape: {raw!r}")
    count = _int(raw[0], "ResponseSpectrum.NumberLoads")
    if count <= 0:
        raise EtabsOAPIError(f"response-spectrum case {case_name!r} has no loads")
    load_names = _seq(raw[1], "ResponseSpectrum.LoadName", count)
    scale_factors = _seq(raw[3], "ResponseSpectrum.SF", count)
    coordinate_systems = _seq(raw[4], "ResponseSpectrum.CSys", count)
    angles = _seq(raw[5], "ResponseSpectrum.Ang", count)
    _ret(raw[6], "LoadCases.ResponseSpectrum.GetLoads")

    vectors: list[tuple[float, float]] = []
    for index in range(count):
        name = _text(load_names[index], "ResponseSpectrum.LoadName")
        sf = _finite(scale_factors[index], "ResponseSpectrum.SF")
        csys_raw = coordinate_systems[index]
        if not isinstance(csys_raw, str):
            raise EtabsOAPIError("ResponseSpectrum.CSys must be a string")
        csys = csys_raw.strip()
        angle = _finite(angles[index], "ResponseSpectrum.Ang")
        if csys not in {"", "Global"}:
            raise EtabsOAPIError(
                f"earthquake response-spectrum case {case_name!r} uses non-Global coordinate system {csys!r}"
            )
        if name not in {"U1", "U2"}:
            raise EtabsOAPIError(
                f"earthquake response-spectrum case {case_name!r} is not clean horizontal-only; load={name!r}"
            )
        if sf == 0.0:
            continue
        theta = math.radians(angle)
        if name == "U1":
            vector = (math.cos(theta), math.sin(theta))
        else:
            vector = (-math.sin(theta), math.cos(theta))
        vectors.append(vector)
    if not vectors:
        raise EtabsOAPIError(f"response-spectrum case {case_name!r} has no nonzero horizontal inertial load")
    return tuple(vectors)


def _pattern_direction_map(
    value: Mapping[str, Sequence[bool]] | None,
) -> dict[str, tuple[bool, bool]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise EtabsOAPIError("tsc2018_pattern_directions must be a mapping")
    result: dict[str, tuple[bool, bool]] = {}
    for raw_name, raw_flags in value.items():
        name = _text(raw_name, "tsc2018_pattern_name")
        if isinstance(raw_flags, (str, bytes)) or not isinstance(raw_flags, Sequence):
            raise EtabsOAPIError("TSC-2018 direction flags must be a two-item bool sequence")
        flags = tuple(raw_flags)
        if len(flags) != 2 or any(type(flag) is not bool for flag in flags):
            raise EtabsOAPIError("TSC-2018 direction flags must be exactly (x_selected, y_selected)")
        result[name] = (flags[0], flags[1])
    return result


def _static_linear_vectors(
    raw: object,
    case_name: str,
    *,
    pattern_directions: Mapping[str, tuple[bool, bool]],
) -> tuple[tuple[tuple[float, float], ...], tuple[str, ...]]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 5:
        raise EtabsOAPIError(f"StaticLinear.GetLoads({case_name!r}) returned unexpected ABI shape: {raw!r}")
    count = _int(raw[0], "StaticLinear.NumberLoads")
    if count <= 0:
        raise EtabsOAPIError(f"static-linear earthquake case {case_name!r} has no loads")
    load_types = _seq(raw[1], "StaticLinear.LoadType", count)
    load_names = _seq(raw[2], "StaticLinear.LoadName", count)
    scale_factors = _seq(raw[3], "StaticLinear.SF", count)
    _ret(raw[4], "LoadCases.StaticLinear.GetLoads")

    nonzero: list[tuple[str, str, float]] = []
    for index in range(count):
        load_type = _text(load_types[index], "StaticLinear.LoadType")
        load_name = _text(load_names[index], "StaticLinear.LoadName")
        sf = _finite(scale_factors[index], "StaticLinear.SF")
        if sf != 0.0:
            nonzero.append((load_type, load_name, sf))
    if not nonzero:
        raise EtabsOAPIError(f"static-linear earthquake case {case_name!r} has no nonzero horizontal action")

    families = {row[0] for row in nonzero}
    if len(families) != 1:
        raise EtabsOAPIError(
            f"earthquake static-linear case {case_name!r} mixes unsupported load families"
        )
    load_type = next(iter(families))
    vectors: list[tuple[float, float]] = []
    refs: list[str] = []
    if load_type == "Accel":
        for _kind, load_name, _sf in nonzero:
            if load_name not in {"UX", "UY"}:
                raise EtabsOAPIError(
                    f"earthquake static-linear case {case_name!r} is not clean horizontal acceleration-only; "
                    f"load_type={load_type!r}, load_name={load_name!r}"
                )
            vectors.append((1.0, 0.0) if load_name == "UX" else (0.0, 1.0))
            refs.append(f"CSI:StaticLinear.LoadName={load_name}")
    elif load_type == "Load":
        for _kind, pattern_name, _sf in nonzero:
            flags = pattern_directions.get(pattern_name)
            if flags is None:
                raise EtabsOAPIError(
                    f"earthquake static-linear case {case_name!r} load pattern {pattern_name!r} has no exact TSC-2018 direction fact"
                )
            x_selected, y_selected = flags
            if x_selected == y_selected:
                raise EtabsOAPIError(
                    f"earthquake static-linear case {case_name!r} load pattern {pattern_name!r} has ambiguous/non-horizontal TSC-2018 direction flags"
                )
            vectors.append((1.0, 0.0) if x_selected else (0.0, 1.0))
            refs.append(f"ETABS:{_AUTO_SEISMIC_TABLE}:{pattern_name}")
        if _rank_xy(vectors) != 1:
            raise EtabsOAPIError(
                f"earthquake static-linear case {case_name!r} mixes X/Y load-pattern actions; clean single-axis action required"
            )
        refs.append(_AUTO_SEISMIC_DIRECTION_AUTHORITY)
    else:
        raise EtabsOAPIError(
            f"earthquake static-linear case {case_name!r} uses unsupported LoadType={load_type!r}"
        )
    return tuple(vectors), tuple(dict.fromkeys(refs))


def _rank_xy(vectors: Sequence[tuple[float, float]]) -> int:
    if not vectors:
        return 0
    for index, left in enumerate(vectors):
        for right in vectors[index + 1 :]:
            if abs(left[0] * right[1] - left[1] * right[0]) > 1.0e-10:
                return 2
    return 1


def qualify_eq713_horizontal_case_scope_from_session(
    session: EtabsVerifiedSession,
    *,
    candidate_case_names: Sequence[str],
    tsc2018_pattern_directions: Mapping[str, Sequence[bool]] | None = None,
    direction_source_refs: Sequence[str] = (),
    timeout_seconds: float = 30.0,
) -> Eq713HorizontalCaseScope:
    candidates = tuple(_text(value, "candidate_case_name") for value in candidate_case_names)
    if not candidates or len(candidates) != len(set(candidates)):
        raise EtabsOAPIError("candidate_case_names must be a nonempty duplicate-free sequence")
    pattern_directions = _pattern_direction_map(tsc2018_pattern_directions)
    supplied_direction_refs = tuple(
        dict.fromkeys(_text(value, "direction_source_ref") for value in direction_source_refs)
    )

    def acquire(_etabs_object: object, sap_model: Any) -> Eq713HorizontalCaseScope:
        load_cases = getattr(sap_model, "LoadCases", None)
        if load_cases is None or not callable(getattr(load_cases, "GetTypeOAPI_1", None)):
            raise EtabsOAPIError("SapModel.LoadCases.GetTypeOAPI_1 is unavailable")
        spectrum = getattr(load_cases, "ResponseSpectrum", None)
        static_linear = getattr(load_cases, "StaticLinear", None)
        facts: list[Eq713HorizontalCaseFact] = []
        all_vectors: list[tuple[float, float]] = []
        refs: list[str] = list(supplied_direction_refs)

        for case_name in candidates:
            case_type, design_type = _case_type(load_cases.GetTypeOAPI_1(case_name), case_name)
            type_ref = (
                f"ETABS:LoadCases.GetTypeOAPI_1:{case_name}:case_type={case_type}:design_type={design_type}"
            )
            refs.append(type_ref)
            if design_type != _QUAKE:
                continue
            if case_type == _RESPONSE_SPECTRUM:
                method = getattr(spectrum, "GetLoads", None)
                if not callable(method):
                    raise EtabsOAPIError("LoadCases.ResponseSpectrum.GetLoads is unavailable")
                vectors = _response_spectrum_vectors(method(case_name), case_name)
                case_type_name = "RESPONSE_SPECTRUM"
                method_refs = (
                    f"ETABS:LoadCases.ResponseSpectrum.GetLoads:{case_name}:HORIZONTAL_INERTIAL_ONLY",
                )
            elif case_type == _LINEAR_STATIC:
                method = getattr(static_linear, "GetLoads", None)
                if not callable(method):
                    raise EtabsOAPIError("LoadCases.StaticLinear.GetLoads is unavailable")
                vectors, load_refs = _static_linear_vectors(
                    method(case_name),
                    case_name,
                    pattern_directions=pattern_directions,
                )
                case_type_name = "LINEAR_STATIC"
                method_refs = (
                    f"ETABS:LoadCases.StaticLinear.GetLoads:{case_name}:HORIZONTAL_INERTIAL_ONLY",
                    *load_refs,
                )
            else:
                raise EtabsOAPIError(
                    f"earthquake-design candidate case {case_name!r} has unsupported case type {case_type}; "
                    "horizontal response provenance is not qualified"
                )
            source_refs = tuple(dict.fromkeys((type_ref, *method_refs)))
            facts.append(
                Eq713HorizontalCaseFact(
                    case_name=case_name,
                    case_type=case_type_name,
                    design_type_code=design_type,
                    direction_vectors_xy=vectors,
                    source_refs=source_refs,
                )
            )
            refs.extend(method_refs)
            all_vectors.extend(vectors)

        if not facts:
            raise EtabsOAPIError("no earthquake-design horizontal inertial case exists in candidate case scope")
        rank = _rank_xy(all_vectors)
        if rank != 2:
            raise EtabsOAPIError(
                "qualified horizontal inertial case scope does not span two independent global XY directions"
            )
        case_names = tuple(fact.case_name for fact in facts)
        payload = {
            "candidate_case_names": candidates,
            "case_names": case_names,
            "direction_rank": rank,
            "case_refs": [ref for fact in facts for ref in fact.source_refs],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        evidence_ref = "eq713-horizontal-case-scope:sha256:" + hashlib.sha256(encoded).hexdigest()
        return Eq713HorizontalCaseScope(
            candidate_case_names=candidates,
            case_names=case_names,
            cases=tuple(facts),
            direction_rank=rank,
            source_refs=tuple(dict.fromkeys((*refs, evidence_ref))),
            evidence_ref=evidence_ref,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="eq713_horizontal_response_case_scope",
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "Eq713HorizontalCaseFact",
    "Eq713HorizontalCaseScope",
    "qualify_eq713_horizontal_case_scope_from_session",
]
