from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


M2_TO_CM2 = 10_000.0

LOCATION_END_I = "End-I"
LOCATION_MIDDLE = "Middle"
LOCATION_END_J = "End-J"

KNOWN_LOCATIONS = {
    "end-i": LOCATION_END_I,
    "endi": LOCATION_END_I,
    "i": LOCATION_END_I,
    "left": LOCATION_END_I,
    "middle": LOCATION_MIDDLE,
    "mid": LOCATION_MIDDLE,
    "center": LOCATION_MIDDLE,
    "centre": LOCATION_MIDDLE,
    "end-j": LOCATION_END_J,
    "endj": LOCATION_END_J,
    "j": LOCATION_END_J,
    "right": LOCATION_END_J,
}


@dataclass(frozen=True)
class ETABSBeamDesignOutputRow:
    story: str
    label: str
    unique_name: str
    section: str
    location: str
    negative_moment_combo: str | None
    negative_moment_kNm: float | None
    as_top_m2: float | None
    as_top_cm2: float | None
    positive_moment_combo: str | None
    positive_moment_kNm: float | None
    as_bot_m2: float | None
    as_bot_cm2: float | None
    status: str | None
    location_is_known: bool


def normalize_etabs_beam_design_output_row(row: Mapping[str, object]) -> ETABSBeamDesignOutputRow:
    """Normalize one ETABS concrete beam design output table row.

    Input row may use ETABS exported headers such as:
    Story, Beam/Label, UniqueName/Unique Name, Section, Location,
    -ve Moment Combo, -ve Moment, As Top, +ve Moment Combo, +ve Moment, As Bot, Status.

    Units:
    - moments are assumed to be kN-m / kNm
    - As Top / As Bot are assumed to be m² and converted to cm²
    """
    story = _text(_first(row, ("Story", "story")))
    label = _text(_first(row, ("Label", "Beam", "label", "beam")))
    unique_name = _text(_first(row, ("UniqueName", "Unique Name", "Object", "object_name", "unique_name")))
    section = _text(_first(row, ("Section", "section")))
    raw_location = _text(_first(row, ("Location", "location")))

    location, location_is_known = normalize_location(raw_location)

    negative_moment_combo = _optional_text(_first(row, ("-ve Moment Combo", "Negative Moment Combo", "negative_moment_combo")))
    negative_moment_kNm = _optional_float(_first(row, ("-ve Moment", "Negative Moment", "negative_moment_kNm")))

    as_top_m2 = _optional_float(_first(row, ("As Top", "AsTop", "as_top_m2")))
    as_top_cm2 = None if as_top_m2 is None else as_top_m2 * M2_TO_CM2

    positive_moment_combo = _optional_text(_first(row, ("+ve Moment Combo", "Positive Moment Combo", "positive_moment_combo")))
    positive_moment_kNm = _optional_float(_first(row, ("+ve Moment", "Positive Moment", "positive_moment_kNm")))

    as_bot_m2 = _optional_float(_first(row, ("As Bot", "AsBot", "as_bot_m2")))
    as_bot_cm2 = None if as_bot_m2 is None else as_bot_m2 * M2_TO_CM2

    status = _optional_text(_first(row, ("Status", "status")))

    return ETABSBeamDesignOutputRow(
        story=story,
        label=label,
        unique_name=unique_name,
        section=section,
        location=location,
        negative_moment_combo=negative_moment_combo,
        negative_moment_kNm=negative_moment_kNm,
        as_top_m2=as_top_m2,
        as_top_cm2=as_top_cm2,
        positive_moment_combo=positive_moment_combo,
        positive_moment_kNm=positive_moment_kNm,
        as_bot_m2=as_bot_m2,
        as_bot_cm2=as_bot_cm2,
        status=status,
        location_is_known=location_is_known,
    )


def normalize_etabs_beam_design_output_rows(rows: list[Mapping[str, object]]) -> list[ETABSBeamDesignOutputRow]:
    return [normalize_etabs_beam_design_output_row(row) for row in rows]


def normalize_location(value: object) -> tuple[str, bool]:
    raw = _text(value)
    if not raw:
        return ("", False)

    key = raw.strip().lower().replace(" ", "").replace("_", "-")
    normalized = KNOWN_LOCATIONS.get(key)
    if normalized is not None:
        return (normalized, True)

    return (raw, False)


def row_to_report_dict(row: ETABSBeamDesignOutputRow) -> dict[str, object]:
    return {
        "story": row.story,
        "label": row.label,
        "unique_name": row.unique_name,
        "section": row.section,
        "location": row.location,
        "location_is_known": row.location_is_known,
        "negative_moment_combo": row.negative_moment_combo,
        "negative_moment_kNm": row.negative_moment_kNm,
        "as_top_m2": row.as_top_m2,
        "as_top_cm2": row.as_top_cm2,
        "positive_moment_combo": row.positive_moment_combo,
        "positive_moment_kNm": row.positive_moment_kNm,
        "as_bot_m2": row.as_bot_m2,
        "as_bot_cm2": row.as_bot_cm2,
        "status": row.status,
    }


def rows_to_report_dicts(rows: list[ETABSBeamDesignOutputRow]) -> list[dict[str, object]]:
    return [row_to_report_dict(row) for row in rows]


def _first(row: Mapping[str, object], names: tuple[str, ...]) -> object:
    for name in names:
        if name in row:
            return row[name]
    return None


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text if text else None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ETABSBeamDesignOutputRow",
    "M2_TO_CM2",
    "normalize_etabs_beam_design_output_row",
    "normalize_etabs_beam_design_output_rows",
    "normalize_location",
    "row_to_report_dict",
    "rows_to_report_dicts",
]
