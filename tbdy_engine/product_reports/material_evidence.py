"""Concrete material/fck evidence rows for checked product-slice sections.

This module resolves evidence only. It reports concrete material names and fck
values when source tables support them. It never evaluates material adequacy and
never claims TBDY material sufficiency.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CONCRETE_MATERIAL_TABLE = "Material Properties - Concrete Data"


def _first_present(row: Mapping[str, Any] | None, aliases: Sequence[str]) -> tuple[str | None, Any]:
    if not row:
        return None, None
    direct = {str(k): k for k in row.keys()}
    folded = {str(k).replace(" ", "").replace("_", "").casefold(): k for k in row.keys()}
    for alias in aliases:
        if alias in direct:
            key = direct[alias]
            value = row.get(key)
            if value not in (None, ""):
                return str(key), value
        key = folded.get(alias.replace(" ", "").replace("_", "").casefold())
        if key is not None:
            value = row.get(key)
            if value not in (None, ""):
                return str(key), value
    return None, None


def _table(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    item = tables.get(key) if isinstance(tables, Mapping) else None
    return item if isinstance(item, Mapping) else {}


def _rows(source: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    item = _table(source, key)
    rows = item.get("rows") or item.get("parsed_rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _actual_table_name(source: Mapping[str, Any], key: str, fallback: str) -> str:
    item = _table(source, key)
    return str(item.get("actual_table_name") or fallback)


def _section_name(row: Mapping[str, Any]) -> str | None:
    _, value = _first_present(row, ("Name", "Section", "SectionName", "PropName", "FrameSection"))
    return None if value in (None, "") else str(value).strip()


def _material_name(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    col, value = _first_present(row, ("Material", "MaterialName", "Material Name", "MatProp", "ConcreteMaterial", "ConcMaterial"))
    return col, None if value in (None, "") else str(value).strip()


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _fck_to_mpa(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    # ETABS fixture/live values may be given either directly in MPa or in kN/m2.
    if abs(number) > 1000.0:
        number = number / 1000.0
    return round(number, 6)


def _match_by_name(rows: Sequence[Mapping[str, Any]], name: str, aliases: Sequence[str]) -> tuple[int | None, Mapping[str, Any] | None]:
    wanted = str(name).strip()
    for index, row in enumerate(rows):
        _, value = _first_present(row, aliases)
        if value is not None and str(value).strip() == wanted:
            return index, row
    return None, None


def _checked_sections(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for element_type, report_key, count_key in (
        ("Beam", "concrete_beam_section_geometry_checks", "assigned_beam_count"),
        ("Column", "concrete_column_section_geometry_checks", "assigned_column_count"),
    ):
        for row in report.get(report_key, []) or []:
            if not isinstance(row, Mapping):
                continue
            section = row.get("section")
            if section in (None, ""):
                continue
            key = (element_type, str(section))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "section": str(section),
                "element_type": element_type,
                "assigned_object_count": int(row.get(count_key) or 0),
            })
    return out


def build_material_evidence(source: Mapping[str, Any], report: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one material/fck evidence row for each checked concrete section."""
    checked_sections = _checked_sections(report)
    section_rows = _rows(source, "frame_section_properties")
    section_material_rows = _rows(source, "frame_section_material_assignments")
    concrete_rows = _rows(source, "material_concrete_data")
    concrete_table_name = _actual_table_name(source, "material_concrete_data", CONCRETE_MATERIAL_TABLE)

    evidence_rows: list[dict[str, Any]] = []
    for checked in checked_sections:
        section = checked["section"]
        section_source_key = "frame_section_properties"
        section_row_index, section_row = _match_by_name(section_rows, section, ("Name", "Section", "SectionName", "PropName", "FrameSection"))
        material_col, material_name = _material_name(section_row or {})
        if material_name is None and section_material_rows:
            section_source_key = "frame_section_material_assignments"
            section_row_index, section_row = _match_by_name(section_material_rows, section, ("Name", "Section", "SectionName", "Property"))
            material_col, material_name = _material_name(section_row or {})

        material_row_index: int | None = None
        material_row: Mapping[str, Any] | None = None
        fck_col: str | None = None
        fck_raw: Any = None
        fck_mpa: float | None = None
        status = "MISSING"
        reason = "No section material evidence could be resolved for this checked concrete section"
        if material_name:
            material_row_index, material_row = _match_by_name(concrete_rows, material_name, ("Material", "Name", "MaterialName"))
            if material_row is None:
                status = "PARTIAL"
                reason = "Section material name was resolved, but no concrete material row matched it"
            else:
                fck_col, fck_raw = _first_present(material_row, ("Fc", "fck", "Fck", "Concrete Strength", "Strength"))
                fck_mpa = _fck_to_mpa(fck_raw)
                if fck_mpa is None:
                    status = "PARTIAL"
                    reason = "Concrete material row was resolved, but fck/Fc is missing or not numeric"
                else:
                    status = "RESOLVED"
                    reason = "Concrete material and numeric fck evidence resolved; no material adequacy verdict is emitted"

        evidence_rows.append({
            "section": section,
            "element_type": checked["element_type"],
            "assigned_object_count": checked["assigned_object_count"],
            "material_name": material_name,
            "fck_value_mpa": fck_mpa,
            "fck_source_unit": "MPa" if fck_mpa is not None else None,
            "material_status": status,
            "evidence_table": concrete_table_name if material_row is not None else None,
            "evidence_columns": [col for col in ("Material", fck_col or "Fc") if col],
            "source_row_index": material_row_index,
            "section_source_table": section_source_key if section_row is not None else None,
            "section_source_row_index": section_row_index,
            "section_material_column": material_col,
            "raw_fck_value": fck_raw,
            "material_evidence_note": reason,
            "fck_adequacy_status": "NOT_EVALUATED",
        })

    resolved = sum(1 for row in evidence_rows if row["material_status"] == "RESOLVED")
    partial = sum(1 for row in evidence_rows if row["material_status"] == "PARTIAL")
    missing = sum(1 for row in evidence_rows if row["material_status"] == "MISSING")
    out_of_scope = sum(1 for row in evidence_rows if row["material_status"] == "OUT_OF_SCOPE")
    if missing:
        status = "MISSING"
    elif partial:
        status = "PARTIAL"
    elif len(evidence_rows) == len(checked_sections):
        status = "RESOLVED"
    else:
        status = "MISSING"
    summary = {
        "checked_concrete_section_count": len(checked_sections),
        "material_evidence_row_count": len(evidence_rows),
        "material_resolved_section_count": resolved,
        "material_partial_section_count": partial,
        "material_missing_section_count": missing,
        "material_out_of_scope_section_count": out_of_scope,
        "material_evidence_reconciled": len(checked_sections) == len(evidence_rows),
        "material_evidence_status": status,
        "fck_adequacy_status": "NOT_EVALUATED",
        "material_evidence_scope": "Evidence only: section concrete material name and fck value are reported without TBDY material adequacy/sufficiency verdicts.",
    }
    return evidence_rows, summary
