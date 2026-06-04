from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from tbdy_engine.verification.beams.etabs_design_output import ETABSBeamDesignOutputRow


LOCATION_TO_REGION = {
    "End-I": "left",
    "Middle": "middle",
    "End-J": "right",
}


@dataclass(frozen=True)
class BeamDesignCrosscheckRow:
    story: str
    label: str
    unique_name: str
    section: str
    location: str
    region: str
    status: str
    etabs_negative_moment_kNm: float | None
    beamcore_negative_moment_kNm: float | None
    negative_moment_delta_kNm: float | None
    etabs_positive_moment_kNm: float | None
    beamcore_positive_moment_kNm: float | None
    positive_moment_delta_kNm: float | None
    etabs_as_top_cm2: float | None
    beamcore_top_required_cm2: float | None
    top_as_delta_cm2: float | None
    etabs_as_bot_cm2: float | None
    beamcore_bottom_required_cm2: float | None
    bottom_as_delta_cm2: float | None
    message: str


def crosscheck_etabs_design_output_row(
    etabs_row: ETABSBeamDesignOutputRow,
    beamcore_actions: Mapping[str, object],
    beamcore_flexure: Mapping[str, object],
) -> BeamDesignCrosscheckRow:
    region = LOCATION_TO_REGION.get(etabs_row.location, "")

    if not region:
        return BeamDesignCrosscheckRow(
            story=etabs_row.story,
            label=etabs_row.label,
            unique_name=etabs_row.unique_name,
            section=etabs_row.section,
            location=etabs_row.location,
            region="",
            status="DIAGNOSTIC",
            etabs_negative_moment_kNm=etabs_row.negative_moment_kNm,
            beamcore_negative_moment_kNm=None,
            negative_moment_delta_kNm=None,
            etabs_positive_moment_kNm=etabs_row.positive_moment_kNm,
            beamcore_positive_moment_kNm=None,
            positive_moment_delta_kNm=None,
            etabs_as_top_cm2=etabs_row.as_top_cm2,
            beamcore_top_required_cm2=None,
            top_as_delta_cm2=None,
            etabs_as_bot_cm2=etabs_row.as_bot_cm2,
            beamcore_bottom_required_cm2=None,
            bottom_as_delta_cm2=None,
            message=f"Unknown ETABS design output location: {etabs_row.location}",
        )

    beamcore_neg = _beamcore_negative_moment(region, beamcore_actions)
    beamcore_pos = _beamcore_positive_moment(region, beamcore_actions)

    top_required = _optional_float(_first(beamcore_flexure, ("top_required_area_cm2", "top_required_cm2", "As_top_required_cm2")))
    bottom_required = _optional_float(_first(beamcore_flexure, ("bottom_required_area_cm2", "bottom_required_cm2", "As_bottom_required_cm2")))

    return BeamDesignCrosscheckRow(
        story=etabs_row.story,
        label=etabs_row.label,
        unique_name=etabs_row.unique_name,
        section=etabs_row.section,
        location=etabs_row.location,
        region=region,
        status="DIAGNOSTIC",
        etabs_negative_moment_kNm=etabs_row.negative_moment_kNm,
        beamcore_negative_moment_kNm=beamcore_neg,
        negative_moment_delta_kNm=_delta_abs(etabs_row.negative_moment_kNm, beamcore_neg),
        etabs_positive_moment_kNm=etabs_row.positive_moment_kNm,
        beamcore_positive_moment_kNm=beamcore_pos,
        positive_moment_delta_kNm=_delta_abs(etabs_row.positive_moment_kNm, beamcore_pos),
        etabs_as_top_cm2=etabs_row.as_top_cm2,
        beamcore_top_required_cm2=top_required,
        top_as_delta_cm2=_delta_abs(etabs_row.as_top_cm2, top_required),
        etabs_as_bot_cm2=etabs_row.as_bot_cm2,
        beamcore_bottom_required_cm2=bottom_required,
        bottom_as_delta_cm2=_delta_abs(etabs_row.as_bot_cm2, bottom_required),
        message="Diagnostic comparison only; ETABS design output does not validate BeamCore.",
    )


def crosscheck_etabs_design_output_rows(
    etabs_rows: list[ETABSBeamDesignOutputRow],
    beamcore_actions: Mapping[str, object],
    beamcore_flexure: Mapping[str, object],
) -> list[BeamDesignCrosscheckRow]:
    return [
        crosscheck_etabs_design_output_row(row, beamcore_actions, beamcore_flexure)
        for row in etabs_rows
    ]


def crosscheck_row_to_report_dict(row: BeamDesignCrosscheckRow) -> dict[str, object]:
    return {
        "story": row.story,
        "label": row.label,
        "unique_name": row.unique_name,
        "section": row.section,
        "location": row.location,
        "region": row.region,
        "status": row.status,
        "etabs_negative_moment_kNm": row.etabs_negative_moment_kNm,
        "beamcore_negative_moment_kNm": row.beamcore_negative_moment_kNm,
        "negative_moment_delta_kNm": row.negative_moment_delta_kNm,
        "etabs_positive_moment_kNm": row.etabs_positive_moment_kNm,
        "beamcore_positive_moment_kNm": row.beamcore_positive_moment_kNm,
        "positive_moment_delta_kNm": row.positive_moment_delta_kNm,
        "etabs_as_top_cm2": row.etabs_as_top_cm2,
        "beamcore_top_required_cm2": row.beamcore_top_required_cm2,
        "top_as_delta_cm2": row.top_as_delta_cm2,
        "etabs_as_bot_cm2": row.etabs_as_bot_cm2,
        "beamcore_bottom_required_cm2": row.beamcore_bottom_required_cm2,
        "bottom_as_delta_cm2": row.bottom_as_delta_cm2,
        "message": row.message,
    }


def crosscheck_rows_to_report_dicts(rows: list[BeamDesignCrosscheckRow]) -> list[dict[str, object]]:
    return [crosscheck_row_to_report_dict(row) for row in rows]


def _beamcore_negative_moment(region: str, beamcore_actions: Mapping[str, object]) -> float | None:
    if region == "left":
        return _optional_float(beamcore_actions.get("Md_left_neg_kNm"))
    if region == "right":
        return _optional_float(beamcore_actions.get("Md_right_neg_kNm"))
    if region == "middle":
        return None
    return None


def _beamcore_positive_moment(region: str, beamcore_actions: Mapping[str, object]) -> float | None:
    if region == "middle":
        return _optional_float(beamcore_actions.get("Md_mid_pos_kNm"))
    return None


def _delta_abs(etabs_value: object, beamcore_value: object) -> float | None:
    etabs = _optional_float(etabs_value)
    beamcore = _optional_float(beamcore_value)
    if etabs is None or beamcore is None:
        return None
    return abs(abs(etabs) - abs(beamcore))


def _first(mapping: Mapping[str, object], names: tuple[str, ...]) -> object:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


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
    "BeamDesignCrosscheckRow",
    "LOCATION_TO_REGION",
    "crosscheck_etabs_design_output_row",
    "crosscheck_etabs_design_output_rows",
    "crosscheck_row_to_report_dict",
    "crosscheck_rows_to_report_dicts",
]
