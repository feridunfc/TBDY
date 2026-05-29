from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..models import Beam, CanonicalSnapshot, Column, DesignBasis, Section, Story


_TABLE_CANDIDATES = {
    "stories": ["Story Definitions", "Stories", "Story Data"],
    "sections": [
        "Frame Section Property Definitions - Concrete Rectangular",
        "Frame Section Properties - Concrete Rectangular",
        "Concrete Rectangular Frame Sections",
        "Frame Section Property Definitions - Summary",
        "Frame Sec Rect",
        "Frame Sec Def - Conc Rect",
    ],
    "assignments": [
        "Frame Assignments - Section Properties",
        "Frame Assignments - Section Property",
        "Frame Section Assignments",
        "Assignments - Frame Sections",
        "Frame Assign Sections",
        "Frame Assigns - Sect Prop",
    ],
    "beam_connectivity": [
        "Beam Object Connectivity",
        "Connectivity - Beam",
        "Object Connectivity - Beams",
        "Connectivity - Frame",
        "Beam Connectivity",
    ],
    "column_connectivity": [
        "Column Object Connectivity",
        "Connectivity - Column",
        "Object Connectivity - Columns",
        "Connectivity - Frame",
        "Column Connectivity",
    ],
    "story_drifts": ["Story Drifts", "Story Drift", "Story Max Over Avg Drifts"],
}

_FIELD_ALIASES = {
    "story_id": ["Story", "StoryName", "Name"],
    "height_mm": ["Height", "StoryHeight", "Height_mm"],
    "section_id": ["Name", "Section", "SectProp", "Property", "SectionName", "AnalysisSect", "DesignSect", "Section Property"],
    "width_mm": ["Width", "t2", "B", "Width_mm"],
    "depth_mm": ["Depth", "t3", "H", "Depth_mm"],
    "design_type": ["Design Type"],
    "element_id": ["UniqueName", "Unique Name", "ObjectUniqueName", "Element", "Frame", "Label"],
    "label": ["Label", "ObjectLabel", "Frame", "Element", "BeamBay", "ColumnBay"],
    "assignment_section_id": ["Section Property", "AnalysisSect", "DesignSect", "Section", "SectProp", "Property"],
    "assignment_story_id": ["Story", "StoryName"],
    "object_type": ["ObjectType", "Type", "FrameType"],
    "drift_story_id": ["Story", "StoryName"],
    "drift_ratio": ["Drift", "DriftRatio", "Max Drift", "MaxDrift"],
    "drift_direction": ["Direction"],
    "drift_output_case": ["Output Case"],
}

_LAST_DIAGNOSTICS: list[str] = []


@dataclass(frozen=True)
class _ProviderResult:
    snapshot: CanonicalSnapshot
    diagnostics: list[str]


def build_snapshot_from_etabs_workbook(
    workbook_path: str | Path,
    manifest_path: str | Path | None = None,
    drift_limit: float | None = None,
) -> CanonicalSnapshot:
    result = _build_snapshot_with_diagnostics(workbook_path, manifest_path, drift_limit)
    return result.snapshot


def inspect_etabs_workbook_tables(workbook_path: str | Path) -> dict[str, Any]:
    path = Path(workbook_path)
    sheets = pd.ExcelFile(path).sheet_names
    return {"workbook_path": str(path), "sheet_names": sorted(sheets)}


def get_last_provider_diagnostics() -> list[str]:
    return list(_LAST_DIAGNOSTICS)


def read_etabs_export_sheet(excel: Any, sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(excel, sheet_name=sheet_name, header=None)
    if raw.empty:
        df = pd.DataFrame()
        df.attrs["sheet_name"] = sheet_name
        df.attrs["units"] = {}
        return df

    first_cell = raw.iat[0, 0]
    first_text = "" if pd.isna(first_cell) else str(first_cell).strip()
    if first_text.startswith("TABLE:") and len(raw.index) >= 2:
        headers = [_clean_header(value) for value in raw.iloc[1].tolist()]
        units_row = raw.iloc[2].tolist() if len(raw.index) >= 3 else [None] * len(headers)
        data = raw.iloc[3:].copy() if len(raw.index) >= 3 else raw.iloc[2:].copy()
        data.columns = headers
        df = data.reset_index(drop=True)
        units = {
            header: _clean_unit(unit)
            for header, unit in zip(headers, units_row)
            if header and _clean_unit(unit)
        }
    else:
        df = pd.read_excel(excel, sheet_name=sheet_name)
        df.columns = [_clean_header(col) for col in df.columns]
        units = {}

    df = _drop_empty_or_unnamed_columns(df)
    df = df.dropna(how="all").reset_index(drop=True)
    df.attrs["sheet_name"] = sheet_name
    df.attrs["units"] = units
    return df


def _build_snapshot_with_diagnostics(
    workbook_path: str | Path,
    manifest_path: str | Path | None = None,
    drift_limit: float | None = None,
) -> _ProviderResult:
    global _LAST_DIAGNOSTICS
    path = Path(workbook_path)
    if not path.exists():
        raise FileNotFoundError(f"ETABS workbook not found: {path}")
    diagnostics = [f"ETABS workbook path: {path}"]
    tables = _load_tables(path, manifest_path, diagnostics)
    stories = _build_stories(tables, diagnostics)
    sections = _build_sections(tables, diagnostics)
    assignments = _build_assignments(tables, diagnostics)
    beams = _build_elements(tables, assignments, "beam_connectivity", "Beam", diagnostics)
    columns = _build_elements(tables, assignments, "column_connectivity", "Column", diagnostics)
    _apply_story_drifts(stories, tables, diagnostics)
    snapshot = CanonicalSnapshot(
        sections=sections,
        beams=beams,
        columns=columns,
        stories=stories,
        design_basis=DesignBasis(code="TBDY-2018", drift_limit=drift_limit),
    )
    diagnostics.append(f"Built stories={len(stories)} sections={len(sections)} beams={len(beams)} columns={len(columns)}")
    _LAST_DIAGNOSTICS = diagnostics
    return _ProviderResult(snapshot=snapshot, diagnostics=diagnostics)


def _load_tables(path: Path, manifest_path: str | Path | None, diagnostics: list[str]) -> dict[str, pd.DataFrame]:
    excel = pd.ExcelFile(path)
    sheet_names = list(excel.sheet_names)
    available_sheets = set(sheet_names)
    diagnostics.append(f"Workbook sheets found: {', '.join(sheet_names)}")
    manifest = _load_manifest(manifest_path) if manifest_path else {}
    tables: dict[str, pd.DataFrame] = {}
    for canonical_name, candidates in _TABLE_CANDIDATES.items():
        sheet_name = _resolve_sheet(candidates, sheet_names, manifest)
        if sheet_name is None:
            diagnostics.append(f"Missing table for {canonical_name}: candidates={candidates}")
            continue
        if sheet_name not in available_sheets:
            diagnostics.append(f"Mapped sheet not found for {canonical_name}: {sheet_name}")
            continue
        tables[canonical_name] = read_etabs_export_sheet(excel, sheet_name)
        diagnostics.append(
            f"Matched {canonical_name}: {sheet_name} rows={len(tables[canonical_name])} "
            f"columns={list(tables[canonical_name].columns)}"
        )
    return tables


def _load_manifest(manifest_path: str | Path) -> dict[str, str]:
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    if isinstance(data, dict):
        items = data.get("tables", data)
        if isinstance(items, list):
            for item in items:
                mapping[str(item.get("table_name"))] = str(item.get("sheet_name"))
        elif isinstance(items, dict):
            for key, value in items.items():
                mapping[str(key)] = str(value)
    return mapping


def _resolve_sheet(candidates: list[str], sheet_names: list[str], manifest: dict[str, str]) -> str | None:
    for candidate in candidates:
        if candidate in manifest:
            return manifest[candidate]
    normalized = {_norm(name): name for name in sheet_names}
    for candidate in candidates:
        if _norm(candidate) in normalized:
            return normalized[_norm(candidate)]
    return None


def _build_stories(tables: dict[str, pd.DataFrame], diagnostics: list[str]) -> dict[str, Story]:
    df = tables.get("stories")
    stories: dict[str, Story] = {}
    if df is None:
        diagnostics.append("Stories table missing; story IDs may be inferred from connectivity.")
        return stories
    story_col = _find_col(df, _FIELD_ALIASES["story_id"])
    height_col = _find_col(df, _FIELD_ALIASES["height_mm"])
    _diagnose_missing_columns("stories", df, {"story_id": _FIELD_ALIASES["story_id"], "height_mm": _FIELD_ALIASES["height_mm"]}, diagnostics)
    for _, row in df.iterrows():
        story_id = _str_value(row, story_col)
        if not story_id:
            continue
        height = _length_mm_value(row, height_col, df)
        stories[story_id] = Story(story_id=story_id, height_mm=height, drift_max_mm=None)
    return stories


def _build_sections(tables: dict[str, pd.DataFrame], diagnostics: list[str]) -> dict[str, Section]:
    df = tables.get("sections")
    sections: dict[str, Section] = {}
    if df is None:
        diagnostics.append("Rectangular section table missing; geometry checks may return NO_DATA.")
        return sections
    id_col = _find_col(df, _FIELD_ALIASES["section_id"])
    width_col = _find_col(df, _FIELD_ALIASES["width_mm"])
    depth_col = _find_col(df, _FIELD_ALIASES["depth_mm"])
    _diagnose_missing_columns(
        "sections",
        df,
        {"section_id": _FIELD_ALIASES["section_id"], "width_mm": _FIELD_ALIASES["width_mm"], "depth_mm": _FIELD_ALIASES["depth_mm"]},
        diagnostics,
    )
    for _, row in df.iterrows():
        section_id = _str_value(row, id_col)
        if not section_id:
            continue
        sections[section_id] = Section(
            section_id=section_id,
            width_mm=_length_mm_value(row, width_col, df),
            depth_mm=_length_mm_value(row, depth_col, df),
        )
    return sections


def _build_assignments(tables: dict[str, pd.DataFrame], diagnostics: list[str]) -> dict[str, dict[str, str]]:
    df = tables.get("assignments")
    assignments: dict[str, dict[str, str]] = {}
    if df is None:
        diagnostics.append("Frame section assignment table missing; beams/columns may be incomplete.")
        return assignments
    id_col = _find_col(df, _FIELD_ALIASES["element_id"])
    section_col = _find_col(df, _FIELD_ALIASES["assignment_section_id"])
    story_col = _find_col(df, _FIELD_ALIASES["assignment_story_id"])
    type_col = _find_col(df, _FIELD_ALIASES["object_type"])
    _diagnose_missing_columns(
        "assignments",
        df,
        {"element_id": _FIELD_ALIASES["element_id"], "section_id": _FIELD_ALIASES["assignment_section_id"], "story_id": _FIELD_ALIASES["assignment_story_id"]},
        diagnostics,
    )
    for _, row in df.iterrows():
        element_id = _str_value(row, id_col)
        if not element_id:
            continue
        assignments[element_id] = {
            "section_id": _str_value(row, section_col),
            "story_id": _str_value(row, story_col),
            "object_type": _str_value(row, type_col),
        }
    return assignments


def _build_elements(
    tables: dict[str, pd.DataFrame],
    assignments: dict[str, dict[str, str]],
    table_key: str,
    object_kind: str,
    diagnostics: list[str],
) -> dict[str, Beam] | dict[str, Column]:
    df = tables.get(table_key)
    elements: dict[str, Any] = {}
    if df is None:
        diagnostics.append(f"{object_kind} connectivity table missing; trying assignment object_type inference.")
        for element_id, assignment in assignments.items():
            if object_kind.lower() in assignment.get("object_type", "").lower():
                story_id = assignment.get("story_id", "")
                section_id = assignment.get("section_id", "")
                elements[element_id] = _make_element(object_kind, element_id, element_id, story_id, section_id)
        return elements
    id_col = _find_col(df, _FIELD_ALIASES["element_id"])
    label_col = _find_col(df, _FIELD_ALIASES["label"])
    story_col = _find_col(df, _FIELD_ALIASES["assignment_story_id"])
    _diagnose_missing_columns(
        table_key,
        df,
        {"element_id": _FIELD_ALIASES["element_id"], "label": _FIELD_ALIASES["label"], "story_id": _FIELD_ALIASES["assignment_story_id"]},
        diagnostics,
    )
    for _, row in df.iterrows():
        element_id = _str_value(row, id_col)
        if not element_id:
            continue
        assignment = assignments.get(element_id, {})
        label = _str_value(row, label_col) or element_id
        story_id = _str_value(row, story_col) or assignment.get("story_id", "")
        section_id = assignment.get("section_id", "")
        elements[element_id] = _make_element(object_kind, element_id, label, story_id, section_id)
    return elements


def _make_element(object_kind: str, element_id: str, label: str, story_id: str, section_id: str) -> Beam | Column:
    if object_kind == "Beam":
        return Beam(element_id=element_id, label=label, story_id=story_id, section_id=section_id)
    return Column(element_id=element_id, label=label, story_id=story_id, section_id=section_id)


def _apply_story_drifts(stories: dict[str, Story], tables: dict[str, pd.DataFrame], diagnostics: list[str]) -> None:
    df = tables.get("story_drifts")
    if df is None:
        diagnostics.append("Story drift table missing; story_drift may return NO_DATA.")
        return
    story_col = _find_col(df, _FIELD_ALIASES["drift_story_id"])
    drift_col = _find_col(df, _FIELD_ALIASES["drift_ratio"])
    _diagnose_missing_columns("story_drifts", df, {"story_id": _FIELD_ALIASES["drift_story_id"], "drift": _FIELD_ALIASES["drift_ratio"]}, diagnostics)
    if story_col is None or drift_col is None:
        diagnostics.append("Story drift table missing required story/drift columns.")
        return
    for _, row in df.iterrows():
        story_id = _str_value(row, story_col)
        drift_ratio = _float_value(row, drift_col)
        story = stories.get(story_id)
        if story is None:
            stories[story_id] = Story(story_id=story_id, height_mm=None, drift_max_mm=None)
            diagnostics.append(f"Story drift found for {story_id}, but story height is unavailable.")
        elif story.height_mm is not None and drift_ratio is not None:
            stories[story_id] = Story(story_id=story.story_id, height_mm=story.height_mm, drift_max_mm=drift_ratio * story.height_mm)
        elif drift_ratio is not None:
            diagnostics.append(f"Story drift ratio found for {story_id}, but height is unavailable.")


def _diagnose_missing_columns(canonical_name: str, df: pd.DataFrame, required_aliases: dict[str, list[str]], diagnostics: list[str]) -> None:
    missing: dict[str, list[str]] = {}
    for field_name, aliases in required_aliases.items():
        if _find_col(df, aliases) is None:
            missing[field_name] = aliases
    if not missing:
        return
    diagnostics.append(
        f"Required columns missing for {canonical_name} sheet={df.attrs.get('sheet_name', '-')}: "
        f"columns={list(df.columns)} required_aliases={missing}"
    )


def _find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    normalized = {_norm(str(col)): str(col) for col in df.columns}
    for alias in aliases:
        if _norm(alias) in normalized:
            return normalized[_norm(alias)]
    return None


def _str_value(row: Any, col: str | None) -> str:
    if col is None:
        return ""
    value = row.get(col)
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _float_value(row: Any, col: str | None) -> float | None:
    if col is None:
        return None
    value = row.get(col)
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _length_mm_value(row: Any, col: str | None, df: pd.DataFrame) -> float | None:
    value = _float_value(row, col)
    if value is None or col is None:
        return value
    unit = str(df.attrs.get("units", {}).get(col, "")).strip().lower()
    if unit == "m":
        return value * 1000.0
    if unit == "mm":
        return value
    if col in {"Height", "Depth", "Width", "Length"} and 0 < abs(value) < 100:
        return value * 1000.0
    return value


def _clean_header(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.startswith("Unnamed:"):
        return ""
    return text


def _clean_unit(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _drop_empty_or_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    keep = [col for col in df.columns if str(col).strip() and not str(col).startswith("Unnamed")]
    return df.loc[:, keep]


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
