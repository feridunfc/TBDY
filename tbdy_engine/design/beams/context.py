from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


CanonicalBeamInput = Mapping[str, object]

_REQUIRED_TEXT_FIELDS = ("beam_id", "story", "section_name")
_REQUIRED_FLOAT_FIELDS = (
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
    "Vd_left_kN",
    "Ve_left_kN",
    "Md_left_neg_kNm",
    "axial_kN",
    "stirrup_diameter_mm",
    "stirrup_spacing_mm",
)
_OPTIONAL_FLOAT_FIELDS = (
    "top_required_area_cm2",
    "bottom_required_area_cm2",
    "top_selected_area_cm2",
    "bottom_selected_area_cm2",
    "left_top_as_cm2",
    "left_bottom_as_cm2",
    "right_top_as_cm2",
    "right_bottom_as_cm2",
    "Md_mid_pos_kNm",
    "Md_right_neg_kNm",
)
_ALLOWED_SOURCE_KEYS = frozenset({"source_table", "source_row", "source_columns", "origin"})


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
    left_top_as_cm2: float | None = None
    left_bottom_as_cm2: float | None = None
    right_top_as_cm2: float | None = None
    right_bottom_as_cm2: float | None = None
    Md_mid_pos_kNm: float | None = None
    Md_right_neg_kNm: float | None = None
    missing_inputs: tuple[str, ...] = ()
    source: Mapping[str, object] = field(default_factory=dict)


def build_beam_model_context(data: CanonicalBeamInput) -> BeamModelContext:
    missing_inputs = list(_missing_inputs(data.get("missing_inputs")))
    text_values = {name: _text_value(data.get(name), name, missing_inputs) for name in _REQUIRED_TEXT_FIELDS}
    float_values = {name: _float_value(data.get(name), name, missing_inputs, required=True) for name in _REQUIRED_FLOAT_FIELDS}
    optional_values = {name: _float_value(data.get(name), name, missing_inputs, required=False) for name in _OPTIONAL_FLOAT_FIELDS}
    stirrup_legs = _int_value(data.get("stirrup_legs"), "stirrup_legs", missing_inputs)
    return BeamModelContext(
        beam_id=text_values["beam_id"],
        story=text_values["story"],
        section_name=text_values["section_name"],
        bw_mm=float_values["bw_mm"],
        h_mm=float_values["h_mm"],
        d_mm=float_values["d_mm"],
        cover_mm=float_values["cover_mm"],
        Ln_mm=float_values["Ln_mm"],
        fck_mpa=float_values["fck_mpa"],
        fcd_mpa=float_values["fcd_mpa"],
        fctd_mpa=float_values["fctd_mpa"],
        fyk_mpa=float_values["fyk_mpa"],
        fyd_mpa=float_values["fyd_mpa"],
        fywd_mpa=float_values["fywd_mpa"],
        Vd_left_kN=float_values["Vd_left_kN"],
        Ve_left_kN=float_values["Ve_left_kN"],
        Md_left_neg_kNm=float_values["Md_left_neg_kNm"],
        axial_kN=float_values["axial_kN"],
        stirrup_legs=stirrup_legs,
        stirrup_diameter_mm=float_values["stirrup_diameter_mm"],
        stirrup_spacing_mm=float_values["stirrup_spacing_mm"],
        top_required_area_cm2=optional_values["top_required_area_cm2"],
        bottom_required_area_cm2=optional_values["bottom_required_area_cm2"],
        top_selected_area_cm2=optional_values["top_selected_area_cm2"],
        bottom_selected_area_cm2=optional_values["bottom_selected_area_cm2"],
        left_top_as_cm2=optional_values["left_top_as_cm2"],
        left_bottom_as_cm2=optional_values["left_bottom_as_cm2"],
        right_top_as_cm2=optional_values["right_top_as_cm2"],
        right_bottom_as_cm2=optional_values["right_bottom_as_cm2"],
        Md_mid_pos_kNm=optional_values["Md_mid_pos_kNm"],
        Md_right_neg_kNm=optional_values["Md_right_neg_kNm"],
        missing_inputs=tuple(dict.fromkeys(missing_inputs)),
        source=_sanitize_source(data.get("source")),
    )


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


def _sanitize_source(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): value[key] for key in value if str(key) in _ALLOWED_SOURCE_KEYS}


def _text_value(value: object, name: str, missing_inputs: list[str]) -> str:
    if value in (None, ""):
        _append_missing(missing_inputs, name)
        return ""
    return str(value)


def _float_value(value: object, name: str, missing_inputs: list[str], *, required: bool) -> float | None:
    number = _number_or_none(value)
    if number is None and required:
        _append_missing(missing_inputs, name)
        return 0.0
    return number


def _int_value(value: object, name: str, missing_inputs: list[str]) -> int:
    number = _number_or_none(value)
    if number is None:
        _append_missing(missing_inputs, name)
        return 0
    return int(number)


def _missing_inputs(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, tuple):
        return tuple(str(item) for item in value if str(item))
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item))
    return ()


def _append_missing(missing_inputs: list[str], name: str) -> None:
    if name not in missing_inputs:
        missing_inputs.append(name)


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
