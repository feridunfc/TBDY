from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BeamCheckEvaluation:
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    unit: str | None = None
    code_ref: str | None = None
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class BeamEvaluationPackage:
    component: str
    checks: tuple[BeamCheckEvaluation, ...]
    evidence: Mapping[str, object]
    messages: tuple[str, ...] = ()
    story: str | None = None
    section: str | None = None


class BeamDesignModule:
    def __init__(self, context: Mapping[str, object]) -> None:
        self.context = context

    def run(self) -> tuple[BeamEvaluationPackage, ...]:
        return build_beam_evaluation_packages(self.context)


def build_beam_evaluation_packages(context: Mapping[str, object]) -> tuple[BeamEvaluationPackage, ...]:
    metadata = _mapping(context.get("design_metadata"))
    design_rows = [row for row in _sequence(metadata.get("beam_design_summary_rows")) if _mapping(row).get("label")]
    flexure_grouped = _mapping(metadata.get("beam_flexure_grouped"))
    shear_grouped = _mapping(metadata.get("beam_shear_grouped"))
    packages: list[BeamEvaluationPackage] = []
    for raw_row in design_rows:
        row = _mapping(raw_row)
        component = _text(row.get("label"))
        story = _optional_text(row.get("story"))
        section = _optional_text(row.get("section"))
        key = _text(row.get("key")) or _beam_key(story, component)
        flexure_row = _flexure_row(_mapping(flexure_grouped.get(key)))
        shear_row = _shear_row(_mapping(shear_grouped.get(key)))
        evidence = _package_evidence(row, key, flexure_row=flexure_row, shear_row=shear_row)
        packages.append(BeamEvaluationPackage(component=component, checks=(_geometry_check(row), _flexure_check(flexure_row), _shear_check(shear_row)), evidence=evidence, messages=(), story=story, section=section))
    return tuple(packages)


def _geometry_check(row: Mapping[str, object]) -> BeamCheckEvaluation:
    return BeamCheckEvaluation(check_type="beam_geometry", status="OK", demand=None, capacity=None, ratio=None, unit="mm", code_ref="TBDY 2018 §7.4.1", messages=("geometry package emitted",))


def _flexure_row(grouped: Mapping[str, object]) -> Mapping[str, object]:
    return _first_mapping(grouped.get("governing_area"), grouped.get("governing_ratio"), grouped.get("governing_positive"), grouped.get("governing_negative"))


def _flexure_check(row: Mapping[str, object]) -> BeamCheckEvaluation:
    if not row:
        return BeamCheckEvaluation(check_type="beam_flexure", status="NO_DATA", demand=None, capacity=None, ratio=None, unit="cm²", code_ref="TBDY 2018 §7.4.2", messages=("TABLE_FIELD_MISSING: flexure governing row",))
    selected_area = _selected_area(row)
    required_area = _flexure_required_area(row)
    messages = _row_messages(row)
    selected_label = _optional_text(_first_value(row, "selected_rebar", "rebar", "rebar_label"))
    if selected_label:
        messages = messages + (f"selected rebar: {selected_label}",)
    elif selected_area is None:
        messages = messages + ("selected rebar not available",)
    return BeamCheckEvaluation(check_type="beam_flexure", status=_status(row), demand=required_area, capacity=selected_area, ratio=_ratio_or_required_over_selected(row, required_area, selected_area), unit="cm²" if required_area is not None or selected_area is not None else None, code_ref="TBDY 2018 §7.4.2", messages=messages)


def _shear_row(grouped: Mapping[str, object]) -> Mapping[str, object]:
    return _first_mapping(grouped.get("governing_ratio"), grouped.get("governing_shear"))


def _shear_check(row: Mapping[str, object]) -> BeamCheckEvaluation:
    if not row:
        return BeamCheckEvaluation(check_type="beam_shear", status="NO_DATA", demand=None, capacity=None, ratio=None, unit="kN", code_ref="TBDY 2018 §7.4.5", messages=("TABLE_FIELD_MISSING: shear governing row",))
    demand = _first_number(row.get("Vd"), row.get("demand"), row.get("shear"), row.get("v_support"))
    capacity = _first_number(row.get("Vr"), row.get("capacity"))
    return BeamCheckEvaluation(check_type="beam_shear", status=_status(row), demand=demand, capacity=capacity, ratio=_ratio_or_demand_over_capacity(row, demand, capacity), unit="kN" if demand is not None or capacity is not None else None, code_ref="TBDY 2018 §7.4.5", messages=_row_messages(row) + _stirrup_messages(row))


def _package_evidence(row: Mapping[str, object], key: str, *, flexure_row: Mapping[str, object], shear_row: Mapping[str, object]) -> Mapping[str, object]:
    evidence: dict[str, object] = {"key": key, "source_table": row.get("source_table"), "source_row": row.get("source_row"), "source_columns": tuple(_sequence(row.get("source_columns")))}
    dimensions = _section_dimensions(row)
    evidence.update(dimensions)
    evidence.update(_flexure_evidence(flexure_row, dimensions))
    evidence.update(_shear_evidence(shear_row, dimensions))
    return evidence


def _flexure_evidence(row: Mapping[str, object], dimensions: Mapping[str, object]) -> dict[str, object]:
    if not row:
        return {}
    out: dict[str, object] = _prefixed_source(row, "flexure")
    _put_if_number(out, "i_top_required_area", row.get("top_required_area"))
    _put_if_number(out, "j_top_required_area", row.get("top_required_area"))
    _put_if_number(out, "bottom_required_area", row.get("bottom_required_area"))
    _put_if_number(out, "i_top_selected_area", row.get("top_selected_area"))
    _put_if_number(out, "j_top_selected_area", row.get("top_selected_area"))
    _put_if_number(out, "bottom_selected_area", row.get("bottom_selected_area"))
    required = _flexure_required_area(row)
    selected = _selected_area(row)
    if required is not None:
        target = _flexure_required_key(_optional_text(row.get("location")) or "")
        out.setdefault(target, required)
        out["total_required_area"] = required
    if selected is not None:
        out["total_selected_area"] = selected
    selected_label = _first_value(row, "selected_rebar", "rebar", "rebar_label")
    if selected_label not in (None, ""):
        out["span_top_selected_rebar"] = selected_label
    ratio = _number_or_none(row.get("ratio"))
    if ratio is not None:
        out["excess_ratio"] = ratio
    if row.get("area_unit"):
        out["area_unit"] = row.get("area_unit")
    for key in ("B", "H"):
        if key in dimensions:
            out[key] = dimensions[key]
    return out


def _shear_evidence(row: Mapping[str, object], dimensions: Mapping[str, object]) -> dict[str, object]:
    if not row:
        return {}
    out: dict[str, object] = _prefixed_source(row, "shear")
    for source_key, target_key in (("Vd", "Vd"), ("demand", "Vd"), ("shear", "Vd"), ("v_support", "Vd"), ("Vr", "Vr"), ("capacity", "Vr"), ("P", "P"), ("axial_force", "P"), ("Asmin", "Asmin"), ("Asmin_cm2", "Asmin"), ("Asw", "Asw"), ("Asw_cm2", "Asw"), ("Vmax", "Vmax"), ("vmax", "Vmax"), ("Vc", "Vc"), ("Vw", "Vw"), ("section_control_ratio", "section_control_ratio"), ("section_control", "section_control_ratio"), ("min_leg_count", "min_leg_count"), ("selected_leg_count", "selected_leg_count"), ("stirrup_diameter", "stirrup_diameter"), ("stirrup_spacing_m", "stirrup_spacing_m"), ("leg_diameter_label", "leg_diameter_label"), ("concrete_class", "concrete_class"), ("rebar_class", "rebar_class"), ("cover_m", "cover_m"), ("earthquake_contribution_considered", "earthquake_contribution_considered")):
        value = _first_value(row, source_key)
        if value not in (None, "") and target_key not in out:
            out[target_key] = value
    for key in ("B", "H"):
        if key in dimensions:
            out[key] = dimensions[key]
    if "d" not in out and "H" in dimensions:
        cover = _number_or_none(out.get("cover_m"))
        if cover is not None:
            out["d"] = round(float(dimensions["H"]) - cover, 6)
    return out


def _prefixed_source(row: Mapping[str, object], prefix: str) -> dict[str, object]:
    out: dict[str, object] = {}
    if row.get("source_table") is not None:
        out[f"{prefix}_source_table"] = row.get("source_table")
    if row.get("source_row") is not None:
        out[f"{prefix}_source_row"] = row.get("source_row")
    if row.get("source_columns") is not None:
        out[f"{prefix}_source_columns"] = tuple(_sequence(row.get("source_columns")))
    return out


def _section_dimensions(row: Mapping[str, object]) -> dict[str, object]:
    b = _first_number(row.get("B"), row.get("b_m"), row.get("width_m"))
    h = _first_number(row.get("H"), row.get("h_m"), row.get("depth_m"))
    if b is not None and h is not None:
        return {"B": b, "H": h}
    section = _optional_text(row.get("section")) or _optional_text(row.get("DesignSect")) or _optional_text(row.get("designsect"))
    parsed = _parse_rect_section_m(section)
    return parsed or {}


def _parse_rect_section_m(section: str | None) -> dict[str, object] | None:
    if not section:
        return None
    match = re.fullmatch(r"(?:[Bb])?(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", section.strip())
    if not match:
        return None
    b = float(match.group(1))
    h = float(match.group(2))
    if b <= 0 or h <= 0:
        return None
    return {"B": b / 100.0, "H": h / 100.0}


def _flexure_required_area(row: Mapping[str, object]) -> float | None:
    return _first_number(row.get("required_area"), row.get("top_required_area"), row.get("bottom_required_area"), row.get("area"), row.get("as_required"), row.get("as_top"), row.get("as_bottom"), row.get("AsTop"), row.get("AsBot"), row.get("i_top_required_area"), row.get("j_top_required_area"), row.get("bottom_required_area"), row.get("total_required_area"))


def _selected_area(row: Mapping[str, object]) -> float | None:
    return _first_number(row.get("selected_area"), row.get("top_selected_area"), row.get("bottom_selected_area"), row.get("selected_rebar_area"), row.get("total_selected_area"))


def _put_if_number(out: dict[str, object], key: str, value: object) -> None:
    number = _number_or_none(value)
    if number is not None:
        out[key] = number


def _flexure_required_key(location: str) -> str:
    text = location.strip().lower()
    if text in {"end-i", "i", "left", "start"}:
        return "i_top_required_area"
    if text in {"end-j", "j", "right", "end"}:
        return "j_top_required_area"
    if "bottom" in text or "bot" in text:
        return "bottom_required_area"
    if "top" in text or "mid" in text or "middle" in text or "span" in text:
        return "span_top_required_area"
    return "total_required_area"


def _ratio_or_required_over_selected(row: Mapping[str, object], required: float | None, selected: float | None) -> float | None:
    if required is not None and selected not in (None, 0):
        return required / selected
    return _number_or_none(row.get("ratio"))


def _ratio_or_demand_over_capacity(row: Mapping[str, object], demand: float | None, capacity: float | None) -> float | None:
    if demand is not None and capacity not in (None, 0):
        return demand / capacity
    return _number_or_none(row.get("ratio"))


def _stirrup_messages(row: Mapping[str, object]) -> tuple[str, ...]:
    label = _optional_text(row.get("leg_diameter_label"))
    return (f"stirrup: {label}",) if label else ()


def _row_messages(row: Mapping[str, object]) -> tuple[str, ...]:
    diagnostic = _optional_text(row.get("diagnostic"))
    if diagnostic:
        return (diagnostic,)
    return ()


def _status(row: Mapping[str, object]) -> str:
    status = _optional_text(row.get("status"))
    return status or "OK"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _first_mapping(*values: object) -> Mapping[str, object]:
    for value in values:
        if isinstance(value, Mapping) and value:
            return value
    return {}


def _first_number(*values: object) -> float | None:
    for value in values:
        number = _number_or_none(value)
        if number is not None:
            return number
    return None


def _first_value(mapping: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _number_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _optional_text(value: object) -> str | None:
    text = _text(value).strip()
    return text or None


def _beam_key(story: str | None, component: str) -> str:
    return f"{story or ''}|{component}"
