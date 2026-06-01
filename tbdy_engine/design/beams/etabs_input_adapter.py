from __future__ import annotations

from typing import Mapping


_REQUIRED_FIELD_MAP = (
    ("id", ("beam", "name"), "id"),
    ("story", ("beam", "story"), "story"),
    ("section", ("beam", "section"), "section"),
    ("geometry.bw_mm", ("section_properties", "width_mm"), "geometry.bw_mm"),
    ("geometry.h_mm", ("section_properties", "height_mm"), "geometry.h_mm"),
    ("geometry.d_mm", ("section_properties", "effective_depth_mm"), "geometry.d_mm"),
    ("geometry.cover_mm", ("section_properties", "cover_mm"), "geometry.cover_mm"),
    ("geometry.Ln_mm", ("section_properties", "clear_span_mm"), "geometry.Ln_mm"),
    ("materials.fck_mpa", ("materials", "concrete", "fck_mpa"), "materials.fck_mpa"),
    ("materials.fcd_mpa", ("materials", "concrete", "fcd_mpa"), "materials.fcd_mpa"),
    ("materials.fctd_mpa", ("materials", "concrete", "fctd_mpa"), "materials.fctd_mpa"),
    ("materials.fyk_mpa", ("materials", "steel", "fyk_mpa"), "materials.fyk_mpa"),
    ("materials.fyd_mpa", ("materials", "steel", "fyd_mpa"), "materials.fyd_mpa"),
    ("materials.fywd_mpa", ("materials", "steel", "fywd_mpa"), "materials.fywd_mpa"),
    ("actions.Vd_left_kN", ("actions", "Vd_left_kN"), "actions.Vd_left_kN"),
    ("actions.Ve_left_kN", ("actions", "Ve_left_kN"), "actions.Ve_left_kN"),
    ("actions.Md_left_neg_kNm", ("actions", "Md_left_neg_kNm"), "actions.Md_left_neg_kNm"),
    ("actions.Md_mid_pos_kNm", ("actions", "Md_mid_pos_kNm"), "actions.Md_mid_pos_kNm"),
    ("actions.Md_right_neg_kNm", ("actions", "Md_right_neg_kNm"), "actions.Md_right_neg_kNm"),
    ("actions.axial_kN", ("actions", "axial_kN"), "actions.axial_kN"),
    ("reinforcement.stirrup_legs", ("reinforcement", "stirrups", "legs"), "reinforcement.stirrup_legs"),
    ("reinforcement.stirrup_diameter_mm", ("reinforcement", "stirrups", "diameter_mm"), "reinforcement.stirrup_diameter_mm"),
    ("reinforcement.stirrup_spacing_mm", ("reinforcement", "stirrups", "spacing_mm"), "reinforcement.stirrup_spacing_mm"),
    ("reinforcement.longitudinal_bar_diameter_mm", ("reinforcement", "longitudinal", "diameter_mm"), "reinforcement.longitudinal_bar_diameter_mm"),
    ("reinforcement.top_selected_area_cm2", ("reinforcement", "longitudinal", "top_selected_area_cm2"), "reinforcement.top_selected_area_cm2"),
    ("reinforcement.bottom_selected_area_cm2", ("reinforcement", "longitudinal", "bottom_selected_area_cm2"), "reinforcement.bottom_selected_area_cm2"),
)

_OPTIONAL_FIELD_MAP = (
    ("reinforcement.top_required_area_cm2", ("reinforcement", "longitudinal", "top_required_area_cm2")),
    ("reinforcement.bottom_required_area_cm2", ("reinforcement", "longitudinal", "bottom_required_area_cm2")),
)


def build_normalized_beam_input_from_etabs_payload(data: Mapping[str, object]) -> dict[str, object]:
    """Build P2 normalized beam input from a static ETABS-adjacent payload mapping."""

    missing_inputs: list[str] = []

    normalized: dict[str, object] = {
        "geometry": {},
        "materials": {},
        "actions": {},
        "reinforcement": {},
        "metadata": _metadata(data),
    }

    for normalized_path, raw_path, missing_name in _REQUIRED_FIELD_MAP:
        value = _get_path(data, raw_path)
        if value in (None, ""):
            missing_inputs.append(missing_name)
            value = None
        _set_dotted_path(normalized, normalized_path, value)

    for normalized_path, raw_path in _OPTIONAL_FIELD_MAP:
        value = _get_path(data, raw_path)
        if value == "":
            value = None
        _set_dotted_path(normalized, normalized_path, value)

    normalized["missing_inputs"] = tuple(dict.fromkeys(missing_inputs))

    return normalized


def _metadata(data: Mapping[str, object]) -> dict[str, object]:
    source = data.get("source")
    source_kind = None
    model_name = None

    if isinstance(source, Mapping):
        source_kind = source.get("kind")
        model_name = source.get("model_name")

    return {
        "source": {
            "origin": "etabs_payload_adapter",
            "raw_source_kind": source_kind,
            "raw_model_name": model_name,
        }
    }


def _get_path(data: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = data

    for key in path:
        if not isinstance(current, Mapping):
            return None
        if key not in current:
            return None
        current = current[key]

    return current


def _set_dotted_path(target: dict[str, object], dotted_path: str, value: object) -> None:
    parts = dotted_path.split(".")
    current = target

    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value

    current[parts[-1]] = value