from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class BeamModelContext:
    beam_id: str
    story: str
    section_name: str
    bw_mm: float
    h_mm: float
    d_mm: float
    cover_mm: float
    Ln_mm: float
    fck_mpa: float
    fcd_mpa: float
    fctd_mpa: float
    fyk_mpa: float
    fyd_mpa: float
    fywd_mpa: float
    Vd_left_kN: float
    Ve_left_kN: float
    Md_left_neg_kNm: float
    axial_kN: float
    stirrup_legs: int
    stirrup_diameter_mm: float
    stirrup_spacing_mm: float
    top_required_area_cm2: float | None = None
    bottom_required_area_cm2: float | None = None
    top_selected_area_cm2: float | None = None
    bottom_selected_area_cm2: float | None = None
    missing_inputs: tuple[str, ...] = ()
    source: Mapping[str, object] = field(default_factory=dict)


def validate_beam_model_context(ctx: BeamModelContext) -> tuple[str, ...]:
    invalid: list[str] = []
    for name in (
        "bw_mm",
        "h_mm",
        "d_mm",
        "cover_mm",
        "Ln_mm",
        "fck_mpa",
        "fcd_mpa",
        "fctd_mpa",
        "fyk_mpa",
        "fyd_mpa",
        "fywd_mpa",
    ):
        if _not_positive(getattr(ctx, name)):
            invalid.append(name)
    for name in ("Vd_left_kN", "Ve_left_kN", "Md_left_neg_kNm", "axial_kN"):
        if _is_missing(getattr(ctx, name)):
            invalid.append(name)
    if ctx.stirrup_legs < 2:
        invalid.append("stirrup_legs")
    if _not_positive(ctx.stirrup_diameter_mm):
        invalid.append("stirrup_diameter_mm")
    if _not_positive(ctx.stirrup_spacing_mm):
        invalid.append("stirrup_spacing_mm")
    invalid.extend(str(name) for name in ctx.missing_inputs if str(name) not in invalid)
    return tuple(invalid)


def _not_positive(value: object) -> bool:
    number = _number_or_none(value)
    return number is None or number <= 0.0


def _is_missing(value: object) -> bool:
    return _number_or_none(value) is None


def _number_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    return number
