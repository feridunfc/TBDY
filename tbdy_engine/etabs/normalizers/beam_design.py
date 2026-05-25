from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any


BEAM_TABLE_KEYS = {
    "design_summary": "beam_design_summary",
    "flexure_envelope": "beam_flexure_envelope",
    "shear_envelope": "beam_shear_envelope",
}


def normalize_beam_design_summary(df: Any, *, source_table: str) -> list[dict[str, object]]:
    rows = []
    for source_row, row in _iter_rows(df):
        label = _string(_row_get(row, "label", "beam", "frame", "element", "objlabel", "unique name", "name"))
        if not label:
            continue
        source_columns = _source_columns(df)
        rows.append(
            {
                "label": label,
                "beam_label": label,
                "story": _string(_row_get(row, "story", "level")),
                "section": _string(_row_get(row, "designsect", "section", "section_name", "sectionname", "frame section")),
                "status": _string(_row_get(row, "status", "designstatus", "result")),
                "ratio": _number_or_none(_row_get(row, "ratio", "dcratio", "pm ratio", "interaction ratio")),
                "as_top": _number_or_none(_row_get(row, "tottoprebar", "astop", "asmintop", "top_area", "as_top")),
                "as_bottom": _number_or_none(_row_get(row, "totbotrebar", "asbot", "asminbot", "bottom_area", "as_bottom")),
                "asw_per_m": _number_or_none(_row_get(row, "tottrnrebar", "vrebar", "asw_per_m", "avs", "av/s")),
                "source_table": source_table,
                "source_row": source_row,
                "source_columns": source_columns,
            }
        )
    return rows


def normalize_beam_flexure_envelope(df: Any, *, source_table: str) -> list[dict[str, object]]:
    rows = []
    for source_row, row in _iter_rows(df):
        label = _string(_row_get(row, "label", "beam", "frame", "element", "objlabel", "unique name", "name"))
        if not label:
            continue
        rows.append(
            {
                "label": label,
                "beam_label": label,
                "story": _string(_row_get(row, "story", "level")),
                "location": _string(_row_get(row, "location", "station", "loc", "position")),
                "combo": _string(_row_get(row, "combo", "case", "outputcase", "loadcase", "mcombo", "designcombo")),
                "moment": _number_or_none(_row_get(row, "moment", "m3", "m3_knm", "moment3", "m", "mu", "mmax")),
                "m_pos": _number_or_none(_row_get(row, "m_pos", "m3_pos", "positive moment", "posmoment")),
                "m_neg": _number_or_none(_row_get(row, "m_neg", "m3_neg", "negative moment", "negmoment")),
                "status": _string(_row_get(row, "status", "designstatus", "result")),
                "ratio": _number_or_none(_row_get(row, "ratio", "dcratio", "d/c", "demandcapacityratio")),
                "source_table": source_table,
                "source_row": source_row,
                "source_columns": _source_columns(df),
            }
        )
    return rows


def normalize_beam_shear_envelope(df: Any, *, source_table: str) -> list[dict[str, object]]:
    rows = []
    for source_row, row in _iter_rows(df):
        label = _string(_row_get(row, "label", "beam", "frame", "element", "objlabel", "unique name", "name"))
        if not label:
            continue
        rows.append(
            {
                "label": label,
                "beam_label": label,
                "story": _string(_row_get(row, "story", "level")),
                "location": _string(_row_get(row, "location", "station", "loc", "position")),
                "combo": _string(_row_get(row, "combo", "case", "outputcase", "loadcase", "vcombo", "designcombo")),
                "shear": _number_or_none(_row_get(row, "shear", "v2", "v2_kn", "shear2", "v", "vu", "vmax")),
                "v_support": _number_or_none(_row_get(row, "v_support", "support shear", "vsupport", "v_at_support")),
                "status": _string(_row_get(row, "status", "designstatus", "result")),
                "ratio": _number_or_none(_row_get(row, "ratio", "dcratio", "d/c", "demandcapacityratio")),
                "source_table": source_table,
                "source_row": source_row,
                "source_columns": _source_columns(df),
            }
        )
    return rows


def build_beam_context_from_tables(tables: Mapping[str, object]) -> dict[str, object]:
    design_summary = _coerce_records(
        tables.get("beam_design_summary"),
        normalizer=normalize_beam_design_summary,
        source_table=str(tables.get("beam_design_summary_source_table") or "beam_design_summary"),
    )
    flexure = _coerce_records(
        tables.get("beam_flexure_envelope"),
        normalizer=normalize_beam_flexure_envelope,
        source_table=str(tables.get("beam_flexure_envelope_source_table") or "beam_flexure_envelope"),
    )
    shear = _coerce_records(
        tables.get("beam_shear_envelope"),
        normalizer=normalize_beam_shear_envelope,
        source_table=str(tables.get("beam_shear_envelope_source_table") or "beam_shear_envelope"),
    )

    return {
        "tables": {
            "beam_design_summary": _records_to_dataframe(design_summary),
            "beam_flexure_envelope": _records_to_dataframe(flexure),
            "beam_shear_envelope": _records_to_dataframe(shear),
        },
        "design_metadata": {
            "beam_design_summary": _records_to_dataframe(design_summary),
            "beam_design_summary_rows": design_summary,
            "beam_flexure_envelope_rows": flexure,
            "beam_shear_envelope_rows": shear,
        },
        "envelopes": {
            "beam_forces_map": _build_beam_forces_map(flexure, shear),
        },
        "geometry": {
            "beam_sections": _build_beam_sections(design_summary),
            "section_dims": _build_section_dims(design_summary),
        },
        "topology": {},
        "design_basis": _default_design_basis(),
        "flags": {
            "has_beam_design_summary": bool(design_summary),
            "has_beam_flexure_envelope": bool(flexure),
            "has_beam_shear_envelope": bool(shear),
            "materials_verified": False,
        },
        "diagnostics": {
            "beam_design_summary_row_count": len(design_summary),
            "beam_flexure_row_count": len(flexure),
            "beam_shear_row_count": len(shear),
        },
    }


def to_context_namespace(context: Mapping[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        tables=context.get("tables", {}),
        design_metadata=context.get("design_metadata", {}),
        envelopes=context.get("envelopes", {}),
        geometry=context.get("geometry", {}),
        topology=context.get("topology", {}),
        design_basis=context.get("design_basis", _default_design_basis()),
        flags=context.get("flags", {}),
    )


def _build_beam_forces_map(flexure: list[dict[str, object]], shear: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in flexure:
        label = str(row.get("label") or "")
        if not label:
            continue
        force = out.setdefault(label, _empty_force_row())
        moment = _number_or_none(row.get("moment"))
        if moment is None:
            moment = _first_number(row.get("m_pos"), row.get("m_neg"))
        if moment is None:
            continue
        if moment >= 0:
            if abs(moment) >= abs(float(force.get("M_pos") or 0.0)):
                force["M_pos"] = abs(moment)
                force["M_pos_case"] = row.get("combo") or ""
        else:
            if abs(moment) >= abs(float(force.get("M_neg_left") or 0.0)):
                force["M_neg_left"] = abs(moment)
                force["M_neg_right"] = abs(moment)
                force["M_neg_left_case"] = row.get("combo") or ""
                force["M_neg_right_case"] = row.get("combo") or ""
        force["combo"] = force.get("combo") or row.get("combo") or ""
        force.setdefault("evidence", {})
        force["evidence"]["flexure"] = _source_evidence(row)

    for row in shear:
        label = str(row.get("label") or "")
        if not label:
            continue
        force = out.setdefault(label, _empty_force_row())
        shear_value = _first_number(row.get("shear"), row.get("v_support"))
        if shear_value is None:
            continue
        if abs(shear_value) >= abs(float(force.get("V_max") or 0.0)):
            force["V_max"] = abs(shear_value)
            force["V2_max"] = abs(shear_value)
            force["V_support"] = abs(shear_value)
            force["V2_support"] = abs(shear_value)
            force["V_max_case"] = row.get("combo") or ""
            force["V_support_case"] = row.get("combo") or ""
        force["combo"] = force.get("combo") or row.get("combo") or ""
        force.setdefault("evidence", {})
        force["evidence"]["shear"] = _source_evidence(row)

    return out


def _empty_force_row() -> dict[str, object]:
    return {
        "M_pos": 0.0,
        "M_neg_left": 0.0,
        "M_neg_right": 0.0,
        "V_max": 0.0,
        "V_support": 0.0,
        "T_max": 0.0,
        "combo": "",
    }


def _build_beam_sections(design_summary: list[dict[str, object]]) -> dict[str, str]:
    out = {}
    for row in design_summary:
        label = str(row.get("label") or "")
        story = str(row.get("story") or "")
        section = str(row.get("section") or "")
        if label and section:
            out[label] = section
            if story:
                out[f"{story}|{label}"] = section
    return out


def _build_section_dims(design_summary: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    out = {}
    for row in design_summary:
        section = str(row.get("section") or "")
        if section and section not in out:
            width, depth = _parse_rect_section_dims(section)
            out[section] = {"width_mm": width, "depth_mm": depth, "source": "section_name_parse"}
    return out


def _parse_rect_section_dims(section: str) -> tuple[float, float]:
    import re

    match = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", str(section or ""))
    if not match:
        return 300.0, 500.0
    b = float(match.group(1))
    h = float(match.group(2))
    if b < 100.0:
        b *= 10.0
    if h < 100.0:
        h *= 10.0
    return b, h


def _source_evidence(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "source_table": row.get("source_table"),
        "source_row": row.get("source_row"),
        "source_columns": row.get("source_columns"),
        "evidence_type": "live_etabs_table",
        "unit_conversion_status": "not_normalized",
        "combo_family_status": "not_inferred",
    }


def _default_design_basis() -> dict[str, object]:
    return {
        "fck_mpa": 30.0,
        "fyk_mpa": 420.0,
        "gamma_c": 1.5,
        "gamma_s": 1.15,
        "materials_verified": False,
    }


def _coerce_records(value: object, *, normalizer, source_table: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return normalizer(value, source_table=source_table)


def _records_to_dataframe(records: list[dict[str, object]]):
    try:
        import pandas as pd
    except Exception:
        return records
    return pd.DataFrame(records)


def _iter_rows(df: Any):
    if df is None:
        return
    if isinstance(df, list):
        for index, item in enumerate(df):
            if isinstance(item, Mapping):
                yield index, item
        return
    if isinstance(df, Mapping):
        yield 0, df
        return
    if not hasattr(df, "iterrows"):
        return
    for index, row in df.iterrows():
        yield index, row


def _source_columns(df: Any) -> list[str]:
    columns = getattr(df, "columns", None)
    if columns is None:
        if isinstance(df, Mapping):
            return [str(key) for key in df]
        return []
    return [str(column) for column in columns]


def _row_get(row: Any, *names: str) -> Any:
    normalized = {_normalize_name(name): name for name in names}
    keys = list(row.keys()) if hasattr(row, "keys") else []
    for key in keys:
        if _normalize_name(key) in normalized:
            try:
                value = row.get(key)
            except Exception:
                value = None
            if _is_present(value):
                return value
    for key in keys:
        key_norm = _normalize_name(key)
        if any(name_norm in key_norm or key_norm in name_norm for name_norm in normalized):
            try:
                value = row.get(key)
            except Exception:
                value = None
            if _is_present(value):
                return value
    return None


def _normalize_name(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "").replace("/", "")


def _is_present(value: object) -> bool:
    if value in (None, ""):
        return False
    try:
        return not bool(value != value)
    except Exception:
        return True


def _string(value: object) -> str:
    return str(value).strip() if _is_present(value) else ""


def _number_or_none(value: object) -> float | None:
    if not _is_present(value):
        return None
    try:
        text = str(value).replace(",", ".")
        number = float(text)
        if number != number:
            return None
        return number
    except Exception:
        return None


def _first_number(*values: object) -> float | None:
    for value in values:
        number = _number_or_none(value)
        if number is not None:
            return number
    return None
