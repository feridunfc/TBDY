"""Exact factual CSI object/property reads used by current semantic providers."""
from __future__ import annotations

import math
from typing import Any, Sequence

from .contracts import (
    AreaPropertyAssignmentFact,
    EtabsOAPIError,
    PointRestraintFact,
    RebarColumnFact,
    WallPropertyFact,
)


def _sequence(raw: Any, *, method: str, expected: int) -> tuple[Any, ...]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(f"{method} returned unexpected scalar: {raw!r}")
    values = tuple(raw)
    if len(values) != expected:
        raise EtabsOAPIError(
            f"{method} returned {len(values)} values; expected {expected}: {raw!r}"
        )
    return values


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(f"{label} must be finite numeric") from exc
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite")
    return result


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise EtabsOAPIError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(f"{label} must be an integer") from exc
    if result < 0:
        raise EtabsOAPIError(f"{label} must be >= 0")
    return result


def read_point_restraint(point_obj: Any, point_name: str) -> PointRestraintFact:
    name = _text(str(point_name), "point_name")
    try:
        raw = point_obj.GetRestraint(name)
    except Exception as exc:
        raise EtabsOAPIError(
            f"PointObj.GetRestraint({name!r}) failed: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise EtabsOAPIError(
            f"PointObj.GetRestraint({name!r}) returned unsupported shape {type(raw).__name__}"
        )
    ret = raw[-1]
    if not isinstance(ret, int) or ret != 0:
        raise EtabsOAPIError(f"PointObj.GetRestraint({name!r}) returned code {ret!r}")
    candidates: list[Sequence[Any]] = [
        item for item in raw[:-1]
        if isinstance(item, (list, tuple)) and len(item) == 6
    ]
    if len(candidates) != 1 or not all(isinstance(item, bool) for item in candidates[0]):
        raise EtabsOAPIError(
            f"PointObj.GetRestraint({name!r}) requires one six-boolean DOF array"
        )
    dofs = tuple(bool(item) for item in candidates[0])
    return PointRestraintFact(point_name=name, dofs=dofs, raw_response=raw)  # type: ignore[arg-type]


def read_rebar_column(prop_frame: Any, section_name: str) -> RebarColumnFact:
    section = _text(section_name, "section_name")
    raw = prop_frame.GetRebarColumn(section)
    values = _sequence(raw, method=f"PropFrame.GetRebarColumn({section!r})", expected=15)
    (
        mat_long, mat_confine, pattern, confine_type, cover,
        number_c, number_r3, number_r2, rebar_size, tie_size,
        tie_spacing, number_2_tie, number_3_tie, to_be_designed, ret,
    ) = values
    if not isinstance(ret, int) or ret != 0:
        raise EtabsOAPIError(f"GetRebarColumn({section!r}) failed/raw={raw!r}")
    if not isinstance(to_be_designed, bool):
        raise EtabsOAPIError(
            f"GetRebarColumn({section!r}) returned non-boolean ToBeDesigned={to_be_designed!r}"
        )
    cover_value = _finite(cover, "Cover")
    tie_spacing_value = _finite(tie_spacing, "TieSpacingLongit")
    if cover_value <= 0.0 or tie_spacing_value <= 0.0:
        raise EtabsOAPIError("Cover and TieSpacingLongit must be > 0")
    return RebarColumnFact(
        section_name=section,
        mat_prop_long=_text(mat_long, "MatPropLong"),
        mat_prop_confine=_text(mat_confine, "MatPropConfine"),
        pattern=_nonnegative_int(pattern, "Pattern"),
        confine_type=_nonnegative_int(confine_type, "ConfineType"),
        cover=cover_value,
        number_c_bars=_nonnegative_int(number_c, "NumberCBars"),
        number_r3_bars=_nonnegative_int(number_r3, "NumberR3Bars"),
        number_r2_bars=_nonnegative_int(number_r2, "NumberR2Bars"),
        rebar_size_name=_text(rebar_size, "RebarSize"),
        tie_size_name=_text(tie_size, "TieSize"),
        tie_spacing_longit=tie_spacing_value,
        number_2_dir_tie_bars=_nonnegative_int(number_2_tie, "Number2DirTieBars"),
        number_3_dir_tie_bars=_nonnegative_int(number_3_tie, "Number3DirTieBars"),
        to_be_designed=to_be_designed,
        raw_response=raw,
    )


def _decode_optional_ret(raw: Any, outputs: int, method: str) -> tuple[tuple[Any, ...], int | None]:
    values = list(raw) if isinstance(raw, (tuple, list)) else []
    if not values:
        if isinstance(raw, int) and not isinstance(raw, bool):
            return (), int(raw)
        raise EtabsOAPIError(f"{method} returned unsupported scalar: {raw!r}")
    ret: int | None = None
    if len(values) > outputs and isinstance(values[-1], int) and not isinstance(values[-1], bool):
        ret = int(values.pop())
    return tuple(values[:outputs]), ret


def read_area_property_assignment(area_obj: Any, area_name: str) -> AreaPropertyAssignmentFact:
    name = _text(area_name, "area_name")
    raw = area_obj.GetProperty(name)
    values, ret = _decode_optional_ret(raw, 1, f"AreaObj.GetProperty({name!r})")
    if ret not in (None, 0) or not values:
        raise EtabsOAPIError(f"AreaObj.GetProperty({name!r}) failed/raw={raw!r}")
    prop = _text(values[0], "assigned_area_property")
    return AreaPropertyAssignmentFact(area_name=name, property_name=prop, raw_response=raw)


def read_wall_property(prop_area: Any, property_name: str) -> WallPropertyFact:
    name = _text(property_name, "property_name")
    raw = prop_area.GetWall(name)
    values, ret = _decode_optional_ret(raw, 7, f"PropArea.GetWall({name!r})")
    if ret not in (None, 0) or len(values) < 4:
        raise EtabsOAPIError(f"PropArea.GetWall({name!r}) failed/raw={raw!r}")
    padded = list(values) + [None] * (7 - len(values))
    try:
        wall_type = int(padded[0])
        shell_type = int(padded[1])
        thickness = float(padded[3])
    except (TypeError, ValueError) as exc:
        raise EtabsOAPIError(f"PropArea.GetWall({name!r}) returned invalid numeric fields") from exc
    if not math.isfinite(thickness):
        raise EtabsOAPIError(f"PropArea.GetWall({name!r}) returned nonfinite thickness")
    material = "" if padded[2] is None else str(padded[2]).strip()
    return WallPropertyFact(
        property_name=name,
        wall_type=wall_type,
        shell_type=shell_type,
        material_name=material,
        thickness=thickness,
        color=int(padded[4]) if padded[4] is not None else 0,
        notes="" if padded[5] is None else str(padded[5]),
        guid="" if padded[6] is None else str(padded[6]),
        raw_response=raw,
    )


__all__ = [
    "read_area_property_assignment",
    "read_point_restraint",
    "read_rebar_column",
    "read_wall_property",
]
