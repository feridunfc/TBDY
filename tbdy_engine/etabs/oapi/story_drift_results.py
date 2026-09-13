"""Exact factual CSI ``Results.StoryDrifts`` boundary.

This module owns only the documented CSI invocation/tuple decoding and the
reversible Results.Setup selection needed to read one exact case or combo.  It
does not decide TS500 sway, choose a governing drift, or assign engineering
meaning to result names.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession,
    ResultsSetupReadTransaction,
    _execute_verified_read,
)

from .contracts import EtabsOAPIError


@dataclass(frozen=True, slots=True)
class StoryDriftResultRow:
    story: str
    load_case: str
    step_type: str
    step_number: float
    direction: str
    drift: float
    point_label: str
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class StoryDriftResultFact:
    output_name: str
    output_kind: str
    rows: tuple[StoryDriftResultRow, ...]
    return_code: int
    source_api: str = "Results.StoryDrifts"

    @property
    def evidence_ref(self) -> str:
        return (
            f"ETABS:Results.StoryDrifts:{self.output_kind}:"
            f"{self.output_name}:rows={len(self.rows)}"
        )


def _text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise EtabsOAPIError(f"{label} must be a string")
    result = value.strip()
    if not result and not allow_empty:
        raise EtabsOAPIError(f"{label} must be nonblank")
    return result


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite")
    return result


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EtabsOAPIError("StoryDrifts.NumberResults must be a nonnegative integer")
    return int(value)


def _array(value: object, label: str, count: int) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)) or len(value) < count:
        raise EtabsOAPIError(f"{label} must contain at least {count} values")
    return tuple(value[:count])


def decode_story_drifts_response(
    raw: object,
    *,
    output_name: str,
    output_kind: str,
) -> StoryDriftResultFact:
    """Decode the documented StoryDrifts ABI without regulatory inference."""
    name = _text(output_name, "output_name")
    kind = _text(output_kind, "output_kind")
    if kind not in {"case", "combo"}:
        raise EtabsOAPIError("output_kind must be case or combo")
    if not isinstance(raw, (tuple, list)) or len(raw) != 12:
        raise EtabsOAPIError(f"Results.StoryDrifts returned unexpected ABI shape: {raw!r}")
    values = tuple(raw)
    count = _count(values[0])
    arrays = tuple(
        _array(values[index], f"StoryDrifts[{index}]", count)
        for index in range(1, 11)
    )
    ret = values[11]
    if not isinstance(ret, int) or isinstance(ret, bool) or ret != 0:
        raise EtabsOAPIError(f"Results.StoryDrifts returned nonzero code {ret!r}")

    rows: list[StoryDriftResultRow] = []
    for index in range(count):
        load_case = _text(arrays[1][index], f"StoryDrifts.LoadCase[{index}]")
        if load_case != name:
            raise EtabsOAPIError(
                f"StoryDrifts binding mismatch at row {index}: "
                f"LoadCase={load_case!r}, expected={name!r}"
            )
        direction = _text(arrays[4][index], f"StoryDrifts.Direction[{index}]")
        if direction not in {"X", "Y"}:
            raise EtabsOAPIError(
                f"StoryDrifts.Direction[{index}] must be X or Y; got {direction!r}"
            )
        rows.append(
            StoryDriftResultRow(
                story=_text(arrays[0][index], f"StoryDrifts.Story[{index}]"),
                load_case=load_case,
                step_type=_text(
                    str(arrays[2][index] or ""),
                    f"StoryDrifts.StepType[{index}]",
                    allow_empty=True,
                ),
                step_number=_finite(arrays[3][index], f"StoryDrifts.StepNum[{index}]"),
                direction=direction,
                drift=_finite(arrays[5][index], f"StoryDrifts.Drift[{index}]"),
                point_label=_text(arrays[6][index], f"StoryDrifts.Label[{index}]"),
                x=_finite(arrays[7][index], f"StoryDrifts.X[{index}]"),
                y=_finite(arrays[8][index], f"StoryDrifts.Y[{index}]"),
                z=_finite(arrays[9][index], f"StoryDrifts.Z[{index}]"),
            )
        )
    if not rows:
        raise EtabsOAPIError(f"Results.StoryDrifts returned no rows for {kind} {name!r}")
    return StoryDriftResultFact(
        output_name=name,
        output_kind=kind,
        rows=tuple(rows),
        return_code=0,
    )


def read_story_drifts_from_session(
    session: EtabsVerifiedSession,
    *,
    output_name: str,
    output_kind: str,
    timeout_seconds: float = 30.0,
) -> StoryDriftResultFact:
    """Read one exactly selected case/combo StoryDrifts population."""
    name = _text(output_name, "output_name")
    kind = _text(output_kind, "output_kind")
    if kind not in {"case", "combo"}:
        raise EtabsOAPIError("output_kind must be case or combo")

    def acquire(_etabs_object: object, sap_model: Any) -> StoryDriftResultFact:
        results = getattr(sap_model, "Results", None)
        method = getattr(results, "StoryDrifts", None)
        if not callable(method):
            raise EtabsOAPIError("Results.StoryDrifts is unavailable")
        with ResultsSetupReadTransaction(sap_model) as transaction:
            if kind == "combo":
                transaction.select_combo(name)
            else:
                transaction.select_case(name)
            raw = method()
        return decode_story_drifts_response(raw, output_name=name, output_kind=kind)

    return _execute_verified_read(
        session,
        acquire,
        operation=f"story_drifts:{kind}:{name}",
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "StoryDriftResultFact",
    "StoryDriftResultRow",
    "decode_story_drifts_response",
    "read_story_drifts_from_session",
]
