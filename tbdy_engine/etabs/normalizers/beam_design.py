from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any


BEAM_TABLE_KEYS = {
    "design_summary": "beam_design_summary",
    "flexure_envelope": "beam_flexure_envelope",
    "shear_envelope": "beam_shear_envelope",
}

COLUMN_ALIASES = {
    "beam_label": ["label", "beam", "frame", "element", "objlabel", "unique name", "name"],
    "story": ["story", "level"],
    "section": ["designsect", "section", "section_name", "sectionname", "frame section"],
    "location": ["location", "station", "loc", "position"],
    "combo": ["combo", "case", "outputcase", "loadcase", "mcombo", "vcombo", "designcombo"],
    "status": ["status", "designstatus", "result"],
    "ratio": ["ratio", "dcratio", "d/c", "demandcapacityratio", "pm ratio", "interaction ratio"],
    "moment": ["moment", "m3", "m3_knm", "moment3", "m", "mu", "mmax"],
    "moment_pos": ["m_pos", "m3_pos", "positive moment", "posmoment"],
    "moment_neg": ["m_neg", "m3_neg", "negative moment", "negmoment"],
    "shear": ["shear", "v2", "v2_kn", "shear2", "v", "vu", "vmax"],
    "shear_support": ["v_support", "support shear", "vsupport", "v_at_support"],
    "as_top": ["tottoprebar", "astop", "asmintop", "top_area", "as_top"],
    "as_bottom": ["totbotrebar", "asbot", "asminbot", "bottom_area", "as_bottom"],
    "asw_per_m": ["tottrnrebar", "vrebar", "asw_per_m", "avs", "av/s"],
}

DIAGNOSTIC_STATUS = "NO_DATA"
DIAGNOSTIC_REASON_MISSING_LABEL = "TABLE_FIELD_MISSING: beam_label"
DIAGNOSTIC_REASON_NO_GOVERNING_VALUE = "TABLE_FIELD_MISSING: numeric governing value"
DIAGNOSTIC_REASON_DUCTILITY_FIELDS_MISSING = "TABLE_FIELD_MISSING: beam design summary rebar/status fields"

ALLOWED_EVIDENCE_TYPES = {"live_etabs_table", "diagnostic_helper"}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
ALLOWED_UNIT_CONVERSION_STATUS = {
    "not_required",
    "not_required_ratio",
    "not_normalized",
    "blocked_until_unit_contract",
    "unknown",
}
ALLOWED_COMBO_FAMILY_STATUS = {
    "not_applicable",
    "not_classified",
    "combo_name_present_family_unclassified",
    "heuristic_deferred",
}


def normalize_beam_design_summary(
    df: Any,
    *,
    source_table: str,
    logical_table: str = "beam_design_summary",
    attempted_candidates: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    attempts = _attempted_candidates(attempted_candidates, source_table)
    for source_row, row in _iter_rows(df):
        source_columns = _source_columns(df)
        label = _string(_row_get(row, *COLUMN_ALIASES["beam_label"]))
        story = _string(_row_get(row, *COLUMN_ALIASES["story"]))
        if not label:
            rows.append(
                _diagnostic_row(
                    source_table,
                    source_row,
                    source_columns,
                    DIAGNOSTIC_REASON_MISSING_LABEL,
                    story=story,
                    logical_table=logical_table,
                    attempted_candidates=attempts,
                )
            )
            continue
        section = _string(_row_get(row, *COLUMN_ALIASES["section"]))
        as_top = _number_or_none(_row_get(row, *COLUMN_ALIASES["as_top"]))
        as_bottom = _number_or_none(_row_get(row, *COLUMN_ALIASES["as_bottom"]))
        asw_per_m = _number_or_none(_row_get(row, *COLUMN_ALIASES["asw_per_m"]))
        status = _string(_row_get(row, *COLUMN_ALIASES["status"]))
        combo = _string(_row_get(row, *COLUMN_ALIASES["combo"]))
        evidence = make_beam_evidence(
            source_table=source_table,
            source_row=source_row,
            source_columns=source_columns,
            logical_table=logical_table,
            attempted_candidates=attempts,
            combo=combo,
        )
        rows.append(
            {
                "key": _beam_key(story, label),
                "label": label,
                "beam_label": label,
                "frame": label,
                "story": story,
                "section": section,
                "designsect": section,
                "status": status,
                "combo": combo,
                "ratio": _number_or_none(_row_get(row, *COLUMN_ALIASES["ratio"])),
                "as_top": as_top,
                "astop": as_top,
                "as_bottom": as_bottom,
                "asbot": as_bottom,
                "asw_per_m": asw_per_m,
                "vrebar": asw_per_m,
                "ductility_status": _ductility_status(status, as_top, as_bottom, asw_per_m),
                "diagnostic": _ductility_diagnostic(status, as_top, as_bottom, asw_per_m),
                "source_table": source_table,
                "source_row": source_row,
                "source_columns": source_columns,
                "logical_table": logical_table,
                "attempted_candidates": attempts,
                "evidence": evidence,
            }
        )
    return rows


def normalize_beam_flexure_envelope(
    df: Any,
    *,
    source_table: str,
    logical_table: str = "beam_flexure_envelope",
    attempted_candidates: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    attempts = _attempted_candidates(attempted_candidates, source_table)
    for source_row, row in _iter_rows(df):
        source_columns = _source_columns(df)
        label = _string(_row_get(row, *COLUMN_ALIASES["beam_label"]))
        story = _string(_row_get(row, *COLUMN_ALIASES["story"]))
        if not label:
            rows.append(
                _diagnostic_row(
                    source_table,
                    source_row,
                    source_columns,
                    DIAGNOSTIC_REASON_MISSING_LABEL,
                    story=story,
                    logical_table=logical_table,
                    attempted_candidates=attempts,
                )
            )
            continue
        moment = _number_or_none(_row_get(row, *COLUMN_ALIASES["moment"]))
        m_pos = _number_or_none(_row_get(row, *COLUMN_ALIASES["moment_pos"]))
        m_neg = _number_or_none(_row_get(row, *COLUMN_ALIASES["moment_neg"]))
        ratio = _number_or_none(_row_get(row, *COLUMN_ALIASES["ratio"]))
        combo = _string(_row_get(row, *COLUMN_ALIASES["combo"]))
        evidence = make_beam_evidence(
            source_table=source_table,
            source_row=source_row,
            source_columns=source_columns,
            logical_table=logical_table,
            attempted_candidates=attempts,
            combo=combo,
        )
        rows.append(
            {
                "key": _beam_key(story, label),
                "label": label,
                "beam_label": label,
                "story": story,
                "location": _string(_row_get(row, *COLUMN_ALIASES["location"])),
                "combo": combo,
                "moment": moment,
                "m_pos": m_pos,
                "m_neg": m_neg,
                "status": _string(_row_get(row, *COLUMN_ALIASES["status"])),
                "ratio": ratio,
                "diagnostic": None if _first_number(moment, m_pos, m_neg, ratio) is not None else DIAGNOSTIC_REASON_NO_GOVERNING_VALUE,
                "source_table": source_table,
                "source_row": source_row,
                "source_columns": source_columns,
                "logical_table": logical_table,
                "attempted_candidates": attempts,
                "evidence": evidence,
            }
        )
    return rows


def normalize_beam_shear_envelope(
    df: Any,
    *,
    source_table: str,
    logical_table: str = "beam_shear_envelope",
    attempted_candidates: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    attempts = _attempted_candidates(attempted_candidates, source_table)
    for source_row, row in _iter_rows(df):
        source_columns = _source_columns(df)
        label = _string(_row_get(row, *COLUMN_ALIASES["beam_label"]))
        story = _string(_row_get(row, *COLUMN_ALIASES["story"]))
        if not label:
            rows.append(
                _diagnostic_row(
                    source_table,
                    source_row,
                    source_columns,
                    DIAGNOSTIC_REASON_MISSING_LABEL,
                    story=story,
                    logical_table=logical_table,
                    attempted_candidates=attempts,
                )
            )
            continue
        shear = _number_or_none(_row_get(row, *COLUMN_ALIASES["shear"]))
        v_support = _number_or_none(_row_get(row, *COLUMN_ALIASES["shear_support"]))
        ratio = _number_or_none(_row_get(row, *COLUMN_ALIASES["ratio"]))
        combo = _string(_row_get(row, *COLUMN_ALIASES["combo"]))
        evidence = make_beam_evidence(
            source_table=source_table,
            source_row=source_row,
            source_columns=source_columns,
            logical_table=logical_table,
            attempted_candidates=attempts,
            combo=combo,
        )
        rows.append(
            {
                "key": _beam_key(story, label),
                "label": label,
                "beam_label": label,
                "story": story,
                "location": _string(_row_get(row, *COLUMN_ALIASES["location"])),
                "combo": combo,
                "shear": shear,
                "v_support": v_support,
                "status": _string(_row_get(row, *COLUMN_ALIASES["status"])),
                "ratio": ratio,
                "diagnostic": None if _first_number(shear, v_support, ratio) is not None else DIAGNOSTIC_REASON_NO_GOVERNING_VALUE,
                "source_table": source_table,
                "source_row": source_row,
                "source_columns": source_columns,
                "logical_table": logical_table,
                "attempted_candidates": attempts,
                "evidence": evidence,
            }
        )
    return rows


def build_beam_context_from_tables(tables: Mapping[str, object]) -> dict[str, object]:
    design_summary_source = str(tables.get("beam_design_summary_source_table") or "beam_design_summary")
    flexure_source = str(tables.get("beam_flexure_envelope_source_table") or "beam_flexure_envelope")
    shear_source = str(tables.get("beam_shear_envelope_source_table") or "beam_shear_envelope")
    design_summary = _coerce_records(
        tables.get("beam_design_summary"),
        normalizer=normalize_beam_design_summary,
        source_table=design_summary_source,
        logical_table="beam_design_summary",
        attempted_candidates=_attempted_candidates(tables.get("beam_design_summary_attempted_candidates"), design_summary_source),
    )
    flexure = _coerce_records(
        tables.get("beam_flexure_envelope"),
        normalizer=normalize_beam_flexure_envelope,
        source_table=flexure_source,
        logical_table="beam_flexure_envelope",
        attempted_candidates=_attempted_candidates(tables.get("beam_flexure_envelope_attempted_candidates"), flexure_source),
    )
    shear = _coerce_records(
        tables.get("beam_shear_envelope"),
        normalizer=normalize_beam_shear_envelope,
        source_table=shear_source,
        logical_table="beam_shear_envelope",
        attempted_candidates=_attempted_candidates(tables.get("beam_shear_envelope_attempted_candidates"), shear_source),
    )
    flexure_grouped = group_beam_flexure_rows(flexure)
    shear_grouped = group_beam_shear_rows(shear)

    beam_design_summary_df = _records_to_dataframe([row for row in design_summary if row.get("label")])
    diagnostics = _diagnostics(design_summary, flexure, shear)
    return {
        "tables": {
            "beam_design_summary": beam_design_summary_df,
            "beam_flexure_envelope": _records_to_dataframe(flexure),
            "beam_shear_envelope": _records_to_dataframe(shear),
        },
        "design_metadata": {
            "beam_design_summary": beam_design_summary_df,
            "beam_design_summary_rows": design_summary,
            "beam_flexure_envelope_rows": flexure,
            "beam_shear_envelope_rows": shear,
            "beam_flexure_grouped": flexure_grouped,
            "beam_shear_grouped": shear_grouped,
            "beam_diagnostics": diagnostics,
        },
        "envelopes": {
            "beam_forces_map": _build_beam_forces_map(flexure_grouped, shear_grouped),
        },
        "geometry": {
            "beam_sections": _build_beam_sections(design_summary),
            "section_dims": _build_section_dims(design_summary),
        },
        "topology": {},
        "design_basis": _default_design_basis(),
        "flags": {
            "has_beam_design_summary": bool([row for row in design_summary if row.get("label")]),
            "has_beam_flexure_envelope": bool([row for row in flexure if row.get("label")]),
            "has_beam_shear_envelope": bool([row for row in shear if row.get("label")]),
            "materials_verified": False,
        },
        "diagnostics": {
            "beam_design_summary_row_count": len([row for row in design_summary if row.get("label")]),
            "beam_flexure_row_count": len([row for row in flexure if row.get("label")]),
            "beam_shear_row_count": len([row for row in shear if row.get("label")]),
            "diagnostic_row_count": len(diagnostics),
        },
    }


def group_beam_flexure_rows(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        key = str(row.get("key") or "")
        if not key:
            continue
        item = grouped.setdefault(key, {"key": key, "rows": [], "governing_positive": None, "governing_negative": None, "governing_ratio": None})
        item["rows"].append(row)
        moment = _first_number(row.get("moment"), row.get("m_pos"), row.get("m_neg"))
        ratio = _number_or_none(row.get("ratio"))
        if ratio is not None and _is_better_abs(row, item.get("governing_ratio"), "ratio"):
            item["governing_ratio"] = row
        if moment is None:
            continue
        if moment >= 0 and _is_better_abs(row, item.get("governing_positive"), "moment"):
            item["governing_positive"] = row
        if moment < 0 and _is_better_abs(row, item.get("governing_negative"), "moment"):
            item["governing_negative"] = row
    return grouped


def group_beam_shear_rows(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        key = str(row.get("key") or "")
        if not key:
            continue
        item = grouped.setdefault(key, {"key": key, "rows": [], "governing_shear": None, "governing_ratio": None})
        item["rows"].append(row)
        ratio = _number_or_none(row.get("ratio"))
        shear = _first_number(row.get("shear"), row.get("v_support"))
        if ratio is not None and _is_better_abs(row, item.get("governing_ratio"), "ratio"):
            item["governing_ratio"] = row
        if shear is not None and _is_better_abs(row, item.get("governing_shear"), "shear"):
            item["governing_shear"] = row
    return grouped


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


def make_beam_evidence(
    *,
    source_table: object,
    source_row: object | None = None,
    source_rows: Sequence[object] | None = None,
    source_columns: Sequence[object] | None = None,
    evidence_type: str = "live_etabs_table",
    confidence: str = "HIGH",
    unit_conversion_status: str = "not_normalized",
    combo_family_status: str | None = None,
    logical_table: str,
    attempted_candidates: Sequence[str] | None = None,
    combo: object | None = None,
    notes: Sequence[object] | None = None,
) -> dict[str, object]:
    rows = list(source_rows) if source_rows is not None else ([source_row] if source_row is not None else [])
    combo_status = combo_family_status or (
        "combo_name_present_family_unclassified" if _string(combo) else "not_applicable"
    )
    evidence = {
        "source_table": source_table,
        "source_row": source_row,
        "source_rows": rows,
        "source_columns": [str(column) for column in (source_columns or [])],
        "evidence_type": evidence_type,
        "confidence": confidence,
        "unit_conversion_status": unit_conversion_status,
        "combo_family_status": combo_status,
        "logical_table": logical_table,
        "attempted_candidates": _attempted_candidates(attempted_candidates, str(source_table or logical_table)),
        "notes": [str(note) for note in (notes or [])],
    }
    _validate_evidence(evidence)
    return evidence


def make_beam_diagnostic_evidence(
    *,
    logical_table: str,
    reason: object,
    attempted_candidates: Sequence[str] | None = None,
    source_table: object | None = None,
    source_row: object | None = None,
    source_columns: Sequence[object] | None = None,
    confidence: str = "LOW",
) -> dict[str, object]:
    return make_beam_evidence(
        source_table=source_table,
        source_row=source_row,
        source_columns=source_columns,
        evidence_type="diagnostic_helper",
        confidence=confidence,
        unit_conversion_status="unknown",
        combo_family_status="not_applicable",
        logical_table=logical_table,
        attempted_candidates=attempted_candidates or ([str(source_table)] if source_table else []),
        notes=[reason],
    )


def _build_beam_forces_map(flexure_grouped: dict[str, dict[str, object]], shear_grouped: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for key, grouped in flexure_grouped.items():
        label = _label_from_key(key)
        if not label:
            continue
        force = out.setdefault(label, _empty_force_row())
        pos = grouped.get("governing_positive")
        neg = grouped.get("governing_negative")
        if isinstance(pos, Mapping):
            moment = _first_number(pos.get("moment"), pos.get("m_pos"))
            if moment is not None:
                force["M_pos"] = abs(moment)
                force["M_pos_case"] = pos.get("combo") or ""
                force.setdefault("evidence", {})["flexure"] = _source_evidence(pos, grouped.get("rows"))
        if isinstance(neg, Mapping):
            moment = _first_number(neg.get("moment"), neg.get("m_neg"))
            if moment is not None:
                force["M_neg_left"] = abs(moment)
                force["M_neg_right"] = abs(moment)
                force["M_neg_left_case"] = neg.get("combo") or ""
                force["M_neg_right_case"] = neg.get("combo") or ""
                force.setdefault("evidence", {})["flexure"] = _source_evidence(neg, grouped.get("rows"))
        chosen = pos if isinstance(pos, Mapping) else neg if isinstance(neg, Mapping) else grouped.get("governing_ratio")
        if isinstance(chosen, Mapping):
            force["combo"] = force.get("combo") or chosen.get("combo") or ""

    for key, grouped in shear_grouped.items():
        label = _label_from_key(key)
        if not label:
            continue
        force = out.setdefault(label, _empty_force_row())
        chosen = grouped.get("governing_ratio") if isinstance(grouped.get("governing_ratio"), Mapping) else grouped.get("governing_shear")
        if not isinstance(chosen, Mapping):
            continue
        shear_value = _first_number(chosen.get("shear"), chosen.get("v_support"))
        if shear_value is None:
            continue
        force["V_max"] = abs(shear_value)
        force["V2_max"] = abs(shear_value)
        force["V_support"] = abs(shear_value)
        force["V2_support"] = abs(shear_value)
        force["V_max_case"] = chosen.get("combo") or ""
        force["V_support_case"] = chosen.get("combo") or ""
        force["combo"] = force.get("combo") or chosen.get("combo") or ""
        force.setdefault("evidence", {})["shear"] = _source_evidence(chosen, grouped.get("rows"))

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
                out[_beam_key(story, label)] = section
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


def _source_evidence(row: Mapping[str, object], rows: object | None = None) -> dict[str, object]:
    source_rows = [item.get("source_row") for item in rows if isinstance(item, Mapping)] if isinstance(rows, list) else [row.get("source_row")]
    return make_beam_evidence(
        source_table=row.get("source_table"),
        source_row=row.get("source_row"),
        source_rows=source_rows,
        source_columns=row.get("source_columns") if isinstance(row.get("source_columns"), list) else [],
        logical_table=str(row.get("logical_table") or "unknown"),
        attempted_candidates=row.get("attempted_candidates") if isinstance(row.get("attempted_candidates"), list) else None,
        combo=row.get("combo"),
        notes=[],
    )


def _diagnostics(*row_groups: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for rows in row_groups:
        for row in rows:
            diagnostic = row.get("diagnostic")
            if diagnostic:
                out.append(
                    {
                        "key": row.get("key") or "",
                        "label": row.get("label") or "",
                        "story": row.get("story") or "",
                        "status": DIAGNOSTIC_STATUS,
                        "reason": diagnostic,
                        "source_table": row.get("source_table"),
                        "source_row": row.get("source_row"),
                        "source_columns": row.get("source_columns"),
                        "evidence": make_beam_diagnostic_evidence(
                            logical_table=str(row.get("logical_table") or "unknown"),
                            reason=diagnostic,
                            attempted_candidates=row.get("attempted_candidates") if isinstance(row.get("attempted_candidates"), list) else None,
                            source_table=row.get("source_table"),
                            source_row=row.get("source_row"),
                            source_columns=row.get("source_columns") if isinstance(row.get("source_columns"), list) else [],
                        ),
                    }
                )
    return out


def _diagnostic_row(
    source_table: str,
    source_row: object,
    source_columns: list[str],
    reason: str,
    *,
    story: str = "",
    logical_table: str,
    attempted_candidates: Sequence[str] | None,
) -> dict[str, object]:
    return {
        "key": _beam_key(story, ""),
        "label": "",
        "beam_label": "",
        "story": story,
        "status": DIAGNOSTIC_STATUS,
        "diagnostic": reason,
        "source_table": source_table,
        "source_row": source_row,
        "source_columns": source_columns,
        "logical_table": logical_table,
        "attempted_candidates": _attempted_candidates(attempted_candidates, source_table),
        "evidence": make_beam_diagnostic_evidence(
            logical_table=logical_table,
            reason=reason,
            attempted_candidates=attempted_candidates,
            source_table=source_table,
            source_row=source_row,
            source_columns=source_columns,
        ),
    }


def _ductility_status(status: str, as_top: float | None, as_bottom: float | None, asw_per_m: float | None) -> str:
    if status or as_top is not None or as_bottom is not None or asw_per_m is not None:
        return "ETABS_DERIVED"
    return DIAGNOSTIC_STATUS


def _ductility_diagnostic(status: str, as_top: float | None, as_bottom: float | None, asw_per_m: float | None) -> str | None:
    if _ductility_status(status, as_top, as_bottom, asw_per_m) == DIAGNOSTIC_STATUS:
        return DIAGNOSTIC_REASON_DUCTILITY_FIELDS_MISSING
    return None


def _beam_key(story: object, label: object) -> str:
    return f"{str(story or '').strip()}|{str(label or '').strip()}"


def _label_from_key(key: str) -> str:
    return key.split("|", 1)[1] if "|" in key else key


def _is_better_abs(row: Mapping[str, object], current: object, field: str) -> bool:
    value = _number_or_none(row.get(field))
    if value is None and field == "moment":
        value = _first_number(row.get("m_pos"), row.get("m_neg"))
    if value is None and field == "shear":
        value = _first_number(row.get("v_support"))
    if value is None:
        return False
    if not isinstance(current, Mapping):
        return True
    current_value = _number_or_none(current.get(field))
    if current_value is None and field == "moment":
        current_value = _first_number(current.get("m_pos"), current.get("m_neg"))
    if current_value is None and field == "shear":
        current_value = _first_number(current.get("v_support"))
    return abs(value) > abs(current_value or 0.0)


def _default_design_basis() -> dict[str, object]:
    return {
        "fck_mpa": 30.0,
        "fyk_mpa": 420.0,
        "gamma_c": 1.5,
        "gamma_s": 1.15,
        "materials_verified": False,
    }


def _coerce_records(value: object, *, normalizer, source_table: str, logical_table: str, attempted_candidates: Sequence[str]) -> list[dict[str, object]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return normalizer(value, source_table=source_table, logical_table=logical_table, attempted_candidates=attempted_candidates)


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


def _attempted_candidates(value: object, source_table: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        candidates = [str(item) for item in value if str(item)]
        return candidates or [source_table]
    return [source_table]


def _validate_evidence(evidence: Mapping[str, object]) -> None:
    if evidence.get("evidence_type") not in ALLOWED_EVIDENCE_TYPES:
        raise ValueError(f"Invalid evidence_type: {evidence.get('evidence_type')}")
    if evidence.get("confidence") not in ALLOWED_CONFIDENCE:
        raise ValueError(f"Invalid confidence: {evidence.get('confidence')}")
    if evidence.get("unit_conversion_status") not in ALLOWED_UNIT_CONVERSION_STATUS:
        raise ValueError(f"Invalid unit_conversion_status: {evidence.get('unit_conversion_status')}")
    if evidence.get("combo_family_status") not in ALLOWED_COMBO_FAMILY_STATUS:
        raise ValueError(f"Invalid combo_family_status: {evidence.get('combo_family_status')}")
