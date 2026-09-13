"""Bounded global-X/Y to column-local M2/M3 sway binding.

This module contains only coordinate-system composition needed by FND-COL-2.
It does not acquire ETABS data and does not evaluate TS500 Eq.7.13.  Global X/Y
sway proof is supplied by the existing ``sway_stability`` owner; the exact
column local-axis angle/provenance is supplied by factual topology.

CSI's Frame-element convention for a vertical member defines ``ang`` as the
angle from global +X to local +2.  Bending M3 corresponds to transverse action
along local 2; bending M2 corresponds to transverse action along local 3.
Therefore X=M2/Y=M3 is intentionally never assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


PROVEN_SWAY_PREVENTED = "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
NOT_PROVEN_SWAY_PREVENTED = "NOT_PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
BLOCKED_SWAY = "BLOCKED_TS500_SWAY_STABILITY_INDEX_EVIDENCE"

LOCAL_SWAY_PREVENTED = "SWAY_PREVENTED"
LOCAL_SWAY_NOT_PROVEN = "NOT_PROVEN_SWAY_PREVENTED"
LOCAL_AXIS_SWAY_AUTHORITY = "CSI_FRAME_LOCAL_AXIS_TO_TS500_SWAY_BINDING"


class LocalAxisSwayBindingError(ValueError):
    pass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise LocalAxisSwayBindingError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    refs = tuple(_text(item, label) for item in values)
    if not refs or len(refs) != len(set(refs)):
        raise LocalAxisSwayBindingError(f"{label} must be nonempty and unique")
    return refs


@dataclass(frozen=True, slots=True)
class GlobalSwayDirectionEvidence:
    direction: str
    status: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        direction = _text(self.direction, "direction")
        if direction not in {"X", "Y"}:
            raise LocalAxisSwayBindingError("direction must be X or Y")
        if self.status not in {
            PROVEN_SWAY_PREVENTED,
            NOT_PROVEN_SWAY_PREVENTED,
            BLOCKED_SWAY,
        }:
            raise LocalAxisSwayBindingError(f"unsupported global sway status={self.status}")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "global_sway.source_ref"))


@dataclass(frozen=True, slots=True)
class LocalAxisSwayResult:
    axis: str
    status: str
    sway_classification: str | None
    contributing_global_directions: tuple[str, ...]
    local_transverse_unit_xy: tuple[float, float]
    source_refs: tuple[str, ...]
    authority: str = LOCAL_AXIS_SWAY_AUTHORITY


@dataclass(frozen=True, slots=True)
class ColumnLocalAxisSwayBinding:
    component_id: str
    local_axis_angle_deg: float
    m2: LocalAxisSwayResult
    m3: LocalAxisSwayResult
    source_refs: tuple[str, ...]
    authority: str = LOCAL_AXIS_SWAY_AUTHORITY


def _axis_result(
    *,
    axis: str,
    vector_xy: tuple[float, float],
    global_by_direction: dict[str, GlobalSwayDirectionEvidence],
    axis_refs: tuple[str, ...],
    projection_tolerance: float,
) -> LocalAxisSwayResult:
    contributing = tuple(
        direction
        for direction, projection in (("X", vector_xy[0]), ("Y", vector_xy[1]))
        if abs(projection) > projection_tolerance
    )
    if not contributing:
        raise LocalAxisSwayBindingError(f"{axis} transverse axis has no horizontal global projection")
    selected = tuple(global_by_direction[item] for item in contributing)
    proven = all(item.status == PROVEN_SWAY_PREVENTED for item in selected)
    status = LOCAL_SWAY_PREVENTED if proven else LOCAL_SWAY_NOT_PROVEN
    refs = tuple(
        dict.fromkeys(
            (
                *axis_refs,
                *(ref for item in selected for ref in item.source_refs),
                *(f"GLOBAL_{item}:PROJECTS_TO_{axis}" for item in contributing),
            )
        )
    )
    return LocalAxisSwayResult(
        axis=axis,
        status=status,
        sway_classification=(LOCAL_SWAY_PREVENTED if proven else None),
        contributing_global_directions=contributing,
        local_transverse_unit_xy=vector_xy,
        source_refs=refs,
    )


def bind_global_sway_to_column_local_axes(
    *,
    component_id: str,
    local_axis_angle_deg: float,
    local_axis_source_refs: tuple[str, ...],
    global_x: GlobalSwayDirectionEvidence,
    global_y: GlobalSwayDirectionEvidence,
    projection_tolerance: float = 1.0e-10,
) -> ColumnLocalAxisSwayBinding:
    """Bind two global sway proofs to M2/M3 using the exact frame coordinate angle.

    For a vertical CSI Frame, local +2 is ``(cos ang, sin ang)`` in the global
    horizontal plane. Local +3 is the perpendicular horizontal axis. The sign of
    +3 is irrelevant to sway-proof applicability; only whether X/Y projects onto
    that transverse direction is used here.
    """
    component = _text(component_id, "component_id")
    angle = float(local_axis_angle_deg)
    if not math.isfinite(angle):
        raise LocalAxisSwayBindingError("local_axis_angle_deg must be finite")
    tolerance = float(projection_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0.0 or tolerance >= 1.0:
        raise LocalAxisSwayBindingError("projection_tolerance must be finite within [0,1)")
    refs = _refs(local_axis_source_refs, "local_axis.source_ref")
    if global_x.direction != "X" or global_y.direction != "Y":
        raise LocalAxisSwayBindingError("global_x/global_y direction identity mismatch")

    theta = math.radians(angle)
    local_2_xy = (math.cos(theta), math.sin(theta))
    local_3_xy = (-math.sin(theta), math.cos(theta))
    common = tuple(dict.fromkeys((*refs, f"CSI_FRAME_VERTICAL_LOCAL_AXIS_ANGLE:{angle:.12g}deg")))

    # M3 bends about local 3, hence its transverse displacement/action direction
    # is local 2. M2 correspondingly uses transverse local 3.
    m3 = _axis_result(
        axis="M3",
        vector_xy=local_2_xy,
        global_by_direction={"X": global_x, "Y": global_y},
        axis_refs=common,
        projection_tolerance=tolerance,
    )
    m2 = _axis_result(
        axis="M2",
        vector_xy=local_3_xy,
        global_by_direction={"X": global_x, "Y": global_y},
        axis_refs=common,
        projection_tolerance=tolerance,
    )
    all_refs = tuple(dict.fromkeys((*common, *m2.source_refs, *m3.source_refs)))
    return ColumnLocalAxisSwayBinding(
        component_id=component,
        local_axis_angle_deg=angle,
        m2=m2,
        m3=m3,
        source_refs=all_refs,
    )


__all__ = [
    "BLOCKED_SWAY",
    "ColumnLocalAxisSwayBinding",
    "GlobalSwayDirectionEvidence",
    "LOCAL_AXIS_SWAY_AUTHORITY",
    "LOCAL_SWAY_NOT_PROVEN",
    "LOCAL_SWAY_PREVENTED",
    "LocalAxisSwayBindingError",
    "LocalAxisSwayResult",
    "NOT_PROVEN_SWAY_PREVENTED",
    "PROVEN_SWAY_PREVENTED",
    "bind_global_sway_to_column_local_axes",
]
