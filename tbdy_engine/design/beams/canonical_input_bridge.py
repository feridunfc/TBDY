from __future__ import annotations

from typing import Mapping


_REQUIRED_TEXT_FIELD_MAP = (
    ("beam_id", ("id",)),
    ("story", ("story",)),
    ("section_name", ("section",)),
)

_REQUIRED_NESTED_FIELD_MAP = (
    ("bw_mm", ("geometry", "bw_mm")),
    ("h_mm", ("geometry", "h_mm")),
    ("d_mm", ("geometry", "d_mm")),
    ("cover_mm", ("geometry", "cover_mm")),
    ("Ln_mm", ("geometry", "Ln_mm")),
    ("fck_mpa", ("materials", "fck_mpa")),
    ("fcd_mpa", ("materials", "fcd_mpa")),
    ("fctd_mpa", ("materials", "fctd_mpa")),
    ("fyk_mpa", ("materials", "fyk_mpa")),
    ("fyd_mpa", ("materials", "fyd_mpa")),
    ("fywd_mpa", ("materials", "fywd_mpa")),
    ("Vd_left_kN", ("actions", "Vd_left_kN")),
    ("Ve_left_kN", ("actions", "Ve_left_kN")),
    ("Md_left_neg_kNm", ("actions", "Md_left_neg_kNm")),
    ("axial_kN", ("actions", "axial_kN")),
    ("stirrup_legs", ("reinforcement", "stirrup_legs")),
    ("stirrup_diameter_mm", ("reinforcement", "stirrup_diameter_mm")),
    ("stirrup_spacing_mm", ("reinforcement", "stirrup_spacing_mm")),
)

_OPTIONAL_NESTED_FIELD_MAP = (
    ("Md_mid_pos_kNm", ("actions", "Md_mid_pos_kNm")),
    ("Md_right_neg_kNm", ("actions", "Md_right_neg_kNm")),
    ("longitudinal_bar_diameter_mm", ("reinforcement", "longitudinal_bar_diameter_mm")),
    ("top_required_area_cm2", ("reinforcement", "top_required_area_cm2")),
    ("top_selected_area_cm2", ("reinforcement", "top_selected_area_cm2")),
    ("bottom_required_area_cm2", ("reinforcement", "bottom_required_area_cm2")),
    ("bottom_selected_area_cm2", ("reinforcement", "bottom_selected_area_cm2")),
)


def build_canonical_beam_input_from_normalized(data: Mapping[str, object]) -> dict[str, object]:
    """Map normalized beam data to the deterministic BeamCore canonical input shape.

    This bridge is intentionally data-shaping only:
    - no external analysis application access
    - no table reads
    - no engineering formulas
    - no missing numeric value fabrication
    """

    missing_inputs: list[str] = []

    canonical: dict[str, object] = {}

    for canonical_name, path in _REQUIRED_TEXT_FIELD_MAP:
        canonical[canonical_name] = _required_value(data, path, canonical_name, missing_inputs)

    for canonical_name, path in _REQUIRED_NESTED_FIELD_MAP:
        canonical[canonical_name] = _required_value(data, path, canonical_name, missing_inputs)

    for canonical_name, path in _OPTIONAL_NESTED_FIELD_MAP:
        canonical[canonical_name] = _optional_value(data, path)

    canonical["missing_inputs"] = tuple(dict.fromkeys(missing_inputs))
    canonical["source"] = _source_metadata(data)

    return canonical


def _required_value(
    data: Mapping[str, object],
    path: tuple[str, ...],
    canonical_name: str,
    missing_inputs: list[str],
) -> object:
    value = _get_path(data, path)

    if value in (None, ""):
        missing_inputs.append(canonical_name)
        return None

    return value


def _optional_value(data: Mapping[str, object], path: tuple[str, ...]) -> object:
    value = _get_path(data, path)
    if value == "":
        return None
    return value


def _get_path(data: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = data

    for key in path:
        if not isinstance(current, Mapping):
            return None
        if key not in current:
            return None
        current = current[key]

    return current


def _source_metadata(data: Mapping[str, object]) -> dict[str, object]:
    metadata = data.get("metadata")
    raw_source = None

    if isinstance(metadata, Mapping):
        raw_source = metadata.get("source")

    return {
        "origin": "normalized_bridge",
        "raw_source": raw_source,
    }