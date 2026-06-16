#!/usr/bin/env python
"""C13.2-P3 targeted live proof for blocked foundational ETABS sources.

Probe-only utility. It targets only material_properties, story_definitions,
and pier_section_properties. It writes evidence reports for human review and
must not promote stable contracts, resolve features, execute checks, emit
CheckResult, or mutate the ETABS model.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SPRINT = "C13.2-P3"
TARGET_FAMILY_CHOICES = ("material_properties", "story_definitions", "pier_section_properties", "all")
SOURCE_STATUSES = {
    "VERIFIED_LIVE_CANDIDATE",
    "PARTIAL_CONTEXT_ONLY",
    "NEEDS_LIVE_PROBE",
    "NOT_FOUND",
    "FETCH_FAILED",
}

WEAK_ONE_WORD_KEYWORDS = {
    "summary",
    "material",
    "area",
    "wall",
    "story",
    "properties",
    "property",
    "section",
    "assignment",
    "assignments",
    "data",
}

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "Material": ("Material", "Mat", "Material Name", "Name"),
    "Name": ("Name", "Material", "Story", "SectionName", "Section Name"),
    "Type": ("Type", "Material Type", "Design Type"),
    "E1": ("E1", "Elastic Modulus", "Modulus of Elasticity", "E"),
    "G12": ("G12", "Shear Modulus", "G"),
    "U12": ("U12", "Poisson", "Poisson Ratio", "Nu"),
    "Weight": ("Weight", "UnitWeight", "Unit Weight", "Weight/UnitVolume"),
    "Fc": ("Fc", "Fcs", "fck", "Concrete Strength"),
    "Fy": ("Fy", "Yield Strength"),
    "Fu": ("Fu", "Ultimate Strength"),
    "Story": ("Story", "Story Name", "Name"),
    "Height": ("Height", "Story Height", "H"),
    "Elevation": ("Elevation", "Elev"),
    "BSElev": ("BSElev", "Base Elevation", "BaseElev", "Base Elev"),
    "MasterStory": ("MasterStory", "Master Story"),
    "SimilarTo": ("SimilarTo", "Similar To"),
    "SpliceAbove": ("SpliceAbove", "Splice Above"),
    "SpliceHeight": ("SpliceHeight", "Splice Height"),
    "Pier": ("Pier", "Pier Label", "PierName", "Pier Name", "Wall", "Label"),
    "Section": ("Section", "SectProp", "PropName", "WallProp", "Property", "Section Property"),
    "PropName": ("PropName", "Property", "Section", "SectProp"),
    "WallProp": ("WallProp", "Wall Property", "Section", "PropName"),
    "WidthBottom": ("Width Bottom", "WidthBottom", "Bottom Width", "Width Bot", "Bot Width"),
    "WidthTop": ("Width Top", "WidthTop", "Top Width", "Width T", "TopWidth"),
    "ThicknessBottom": ("Thickness Bottom", "ThicknessBottom", "Bottom Thickness", "Thick Bottom", "Thick Bot"),
    "ThicknessTop": ("Thickness Top", "ThicknessTop", "Top Thickness", "Thick Top", "TopThickness"),
}

INVENTORY_ONLY_MATERIAL_TABLES = {
    "materiallistbystory",
    "materiallistbyobjecttype",
    "materiallistbysectionprop",
}


@dataclass(frozen=True, slots=True)
class TargetFamily:
    family_id: str
    semantic_role: str
    expected_table_names: tuple[str, ...]
    fallback_keywords: tuple[str, ...]
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...] = ()
    forbidden_direct_table_names: tuple[str, ...] = ()


TARGET_FAMILIES: dict[str, TargetFamily] = {
    "material_properties": TargetFamily(
        family_id="material_properties",
        semantic_role="material mechanical properties proof only; no design interpretation",
        expected_table_names=(
            "Material Properties - Basic Mechanical Properties",
            "Material Properties - Concrete Data",
            "Material Properties - Rebar Data",
        ),
        fallback_keywords=("Material Properties", "Basic Mechanical", "Concrete Data", "Rebar Data"),
        required_columns=("Material", "E1", "G12", "U12"),
        optional_columns=("Type", "Weight", "Fc", "Fy", "Fu"),
        forbidden_direct_table_names=("Material List by Story", "Material List by Object Type", "Material List by Section Prop"),
    ),
    "story_definitions": TargetFamily(
        family_id="story_definitions",
        semantic_role="story metadata / elevation / height context proof only",
        expected_table_names=("Story Definitions", "Story Data", "Story Definitions - Summary", "Tower and Base Story Definition"),
        fallback_keywords=("Story Definitions", "Story Data", "Story Information", "Tower Base Story"),
        required_columns=("Story", "Height", "Elevation"),
        optional_columns=("BSElev", "MasterStory", "SimilarTo", "SpliceAbove", "SpliceHeight"),
    ),
    "pier_section_properties": TargetFamily(
        family_id="pier_section_properties",
        semantic_role="pier/wall section-property context proof only; no force/capacity interpretation",
        expected_table_names=(
            "Pier Section Properties",
            "Pier Assignments",
            "Wall Section Properties",
            "Area Assignments - Summary",
            "Wall Bays",
            "Wall Object Connectivity",
            "Area Assigns - Pier Labels",
            "Area Assigns - Sect Prop",
            "Wall Property Def - Specified",
            "Area Section Props - Summary",
        ),
        fallback_keywords=(
            "Pier Section",
            "Pier Assignment",
            "Wall Section",
            "Area Assignments",
            "Wall Object Connectivity",
            "Area Assigns Pier Labels",
            "Area Assigns Sect Prop",
            "Wall Property Def Specified",
            "Area Section Props Summary",
        ),
        required_columns=("Story", "Pier", "Section"),
        optional_columns=("Material", "PropName", "WallProp", "WidthBottom", "WidthTop", "ThicknessBottom", "ThicknessTop"),
    ),
}


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _normalize_words(value: Any) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^a-z0-9]+", str(value or "").lower()) if part)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _selected_family_ids(target_family: str) -> tuple[str, ...]:
    if target_family == "all":
        return tuple(TARGET_FAMILIES)
    if target_family not in TARGET_FAMILIES:
        raise ValueError(f"Unknown target family: {target_family}")
    return (target_family,)


def _headers_for_table(headers_by_table: Mapping[str, Sequence[str]], table_name: str) -> tuple[str, ...]:
    return tuple(str(item) for item in headers_by_table.get(table_name, ()) or ())


def _rows_for_table(rows_by_table: Mapping[str, Sequence[Mapping[str, Any]]], table_name: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(dict(row) for row in rows_by_table.get(table_name, ()) or ())


def _has_column(columns: Sequence[str], logical_column: str) -> bool:
    normalized_columns = {_normalize_token(col) for col in columns}
    aliases = HEADER_ALIASES.get(logical_column, (logical_column,))
    return any(_normalize_token(alias) in normalized_columns for alias in aliases)


def _columns_found_missing(columns: Sequence[str], required: Sequence[str]) -> tuple[list[str], list[str]]:
    found = [col for col in required if _has_column(columns, col)]
    missing = [col for col in required if col not in found]
    return found, missing


def _table_name_in(table_name: str, names: Sequence[str]) -> bool:
    norm = _normalize_token(table_name)
    return norm in {_normalize_token(name) for name in names}


def _is_inventory_material_table(table_name: str) -> bool:
    return _normalize_token(table_name) in INVENTORY_ONLY_MATERIAL_TABLES


def _keyword_score(table_name: str, keywords: Sequence[str]) -> int:
    table_words = set(_normalize_words(table_name))
    table_norm = _normalize_token(table_name)
    score = 0
    for keyword in keywords:
        key_words = set(_normalize_words(keyword))
        key_norm = _normalize_token(keyword)
        if not key_words:
            continue
        if len(key_words) == 1 and next(iter(key_words)) in WEAK_ONE_WORD_KEYWORDS:
            continue
        if key_norm and key_norm in table_norm:
            score += 4 + len(key_words)
        elif key_words and key_words.issubset(table_words):
            score += 2 + len(key_words)
    return score


def match_target_tables(
    available_tables: Sequence[str],
    family: TargetFamily,
    *,
    max_candidate_tables_per_family: int,
) -> dict[str, Any]:
    """Match exact expected table names first, then capped keyword fallback."""
    available_by_norm: dict[str, list[str]] = {}
    for name in available_tables:
        available_by_norm.setdefault(_normalize_token(name), []).append(name)
    exact_matches: list[str] = []
    for expected in family.expected_table_names:
        exact_matches.extend(available_by_norm.get(_normalize_token(expected), []))

    if exact_matches:
        selected_tables = exact_matches[:max_candidate_tables_per_family]
        before = len(exact_matches)
        return {
            "expected_table_names": list(family.expected_table_names),
            "exact_matches": exact_matches,
            "fallback_candidates": [],
            "selected_tables": selected_tables,
            "candidate_count_before_cap": before,
            "candidate_count_after_cap": len(selected_tables),
            "candidate_truncation_applied": before > len(selected_tables),
            "match_strategy": "exact",
            "notes": ["Exact expected table names were preferred over fallback candidates."],
        }

    scored: list[tuple[int, str]] = []
    for table_name in available_tables:
        score = _keyword_score(table_name, family.fallback_keywords)
        if score > 0:
            scored.append((score, table_name))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    fallback_candidates = [name for _score, name in scored]
    selected_tables = fallback_candidates[:max_candidate_tables_per_family]
    return {
        "expected_table_names": list(family.expected_table_names),
        "exact_matches": [],
        "fallback_candidates": fallback_candidates,
        "selected_tables": selected_tables,
        "candidate_count_before_cap": len(fallback_candidates),
        "candidate_count_after_cap": len(selected_tables),
        "candidate_truncation_applied": len(fallback_candidates) > len(selected_tables),
        "match_strategy": "fallback_capped_keyword" if fallback_candidates else "not_found",
        "notes": ["Fallback candidates are capped before any fetch."] if fallback_candidates else ["No exact or fallback candidates found."],
    }


def _aggregate_columns(selected_tables: Sequence[str], headers_by_table: Mapping[str, Sequence[str]]) -> list[str]:
    columns: list[str] = []
    for table in selected_tables:
        for column in _headers_for_table(headers_by_table, table):
            if column not in columns:
                columns.append(column)
    return columns


def _find_selected_table(selected_tables: Sequence[str], expected_name: str) -> str | None:
    expected = _normalize_token(expected_name)
    for table in selected_tables:
        if _normalize_token(table) == expected:
            return table
    return None


def _story_definitions_proof(
    selected_tables: Sequence[str],
    headers_by_table: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    story_table = _find_selected_table(selected_tables, "Story Definitions")
    tower_table = _find_selected_table(selected_tables, "Tower and Base Story Definition")
    story_columns = _headers_for_table(headers_by_table, story_table) if story_table else ()
    tower_columns = _headers_for_table(headers_by_table, tower_table) if tower_table else ()

    story_name_found = bool(story_table) and (_has_column(story_columns, "Story") or _has_column(story_columns, "Name"))
    height_found = bool(story_table) and _has_column(story_columns, "Height")
    direct_elevation_found = bool(story_table) and _has_column(story_columns, "Elevation")
    base_elevation_found = bool(tower_table) and _has_column(tower_columns, "BSElev")

    combined_elevation_supported = story_name_found and height_found and base_elevation_found
    verified = story_name_found and height_found and (direct_elevation_found or combined_elevation_supported)
    found: list[str] = []
    if story_name_found:
        found.append("Story")
    if height_found:
        found.append("Height")
    if direct_elevation_found or combined_elevation_supported:
        found.append("Elevation")
    missing = [col for col in ("Story", "Height", "Elevation") if col not in found]
    return {
        "verified": verified,
        "required_columns_found": found,
        "required_columns_missing": missing,
        "story_definitions_table": story_table,
        "tower_and_base_story_definition_table": tower_table,
        "derived_elevation_supported": bool(combined_elevation_supported and not direct_elevation_found),
        "elevation_is_direct_column": bool(direct_elevation_found),
        "base_elevation_column": "BSElev" if base_elevation_found else None,
    }


def _pier_section_properties_proof(
    selected_tables: Sequence[str],
    headers_by_table: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    direct_table = _find_selected_table(selected_tables, "Pier Section Properties")
    direct_columns = _headers_for_table(headers_by_table, direct_table) if direct_table else ()
    story_present = bool(direct_table) and _has_column(direct_columns, "Story")
    pier_present = bool(direct_table) and _has_column(direct_columns, "Pier")
    width_present = bool(direct_table) and (
        _has_column(direct_columns, "WidthBottom") or _has_column(direct_columns, "WidthTop")
    )
    thickness_present = bool(direct_table) and (
        _has_column(direct_columns, "ThicknessBottom") or _has_column(direct_columns, "ThicknessTop")
    )
    section_name_column_present = bool(direct_table) and any(
        _has_column(direct_columns, key) for key in ("Section", "PropName", "WallProp")
    )
    material_present = bool(direct_table) and _has_column(direct_columns, "Material")
    verified = story_present and pier_present and width_present and thickness_present
    found: list[str] = []
    if story_present:
        found.append("Story")
    if pier_present:
        found.append("Pier")
    if section_name_column_present:
        found.append("Section")
    if width_present:
        found.append("Width")
    if thickness_present:
        found.append("Thickness")
    if material_present:
        found.append("Material")
    missing: list[str] = []
    if not story_present:
        missing.append("Story")
    if not pier_present:
        missing.append("Pier")
    if not width_present:
        missing.append("Width Bottom or Width Top")
    if not thickness_present:
        missing.append("Thickness Bottom or Thickness Top")
    return {
        "verified": verified,
        "direct_table": direct_table,
        "direct_section_geometry_present": bool(verified),
        "section_name_column_present": bool(section_name_column_present),
        "material_present": bool(material_present),
        "required_columns_found": found,
        "required_columns_missing": missing,
    }


def evaluate_family_status(
    family: TargetFamily,
    selected_tables: Sequence[str],
    headers_by_table: Mapping[str, Sequence[str]],
    fetch_status_by_table: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    fetch_status_by_table = dict(fetch_status_by_table or {})
    if not selected_tables:
        return {
            "source_status": "NOT_FOUND",
            "required_columns_found": [],
            "required_columns_missing": list(family.required_columns),
            "promotion_recommendation": "Keep blocked; no live candidate table was found.",
            "semantic_risks": ["No live evidence."],
        }

    failed = [table for table in selected_tables if str(fetch_status_by_table.get(table, "")).upper() == "FAILED"]
    if failed and len(failed) == len(selected_tables):
        return {
            "source_status": "FETCH_FAILED",
            "required_columns_found": [],
            "required_columns_missing": list(family.required_columns),
            "promotion_recommendation": "Keep blocked; all selected live table fetches failed.",
            "semantic_risks": ["Fetch failed for every selected table."],
        }

    columns = _aggregate_columns(selected_tables, headers_by_table)
    found, missing = _columns_found_missing(columns, family.required_columns)
    selected_norms = {_normalize_token(table) for table in selected_tables}

    if family.family_id == "material_properties":
        inventory_context = any(_is_inventory_material_table(table) for table in selected_tables)
        mechanical_proof = all(column in found for column in ("Material", "E1", "G12", "U12"))
        if mechanical_proof and not inventory_context:
            return {
                "source_status": "VERIFIED_LIVE_CANDIDATE",
                "required_columns_found": found,
                "required_columns_missing": missing,
                "promotion_recommendation": "Eligible for future human-reviewed promotion as material mechanical-property source.",
                "semantic_risks": ["Raw material constants only; no material compliance check is unlocked."],
            }
        if inventory_context:
            return {
                "source_status": "PARTIAL_CONTEXT_ONLY",
                "required_columns_found": found,
                "required_columns_missing": missing,
                "promotion_recommendation": "Do not promote as material_properties; Material List tables are inventory context only.",
                "semantic_risks": ["Material List by Story/Object/Section does not prove E1/G12/U12."],
            }
        return {
            "source_status": "NEEDS_LIVE_PROBE",
            "required_columns_found": found,
            "required_columns_missing": missing,
            "promotion_recommendation": "Keep blocked until live table proves Material/E1/G12/U12 semantics.",
            "semantic_risks": ["Material table headers do not yet prove required mechanical properties."],
        }

    if family.family_id == "story_definitions":
        proof = _story_definitions_proof(selected_tables, headers_by_table)
        if proof["verified"]:
            return {
                "source_status": "VERIFIED_LIVE_CANDIDATE",
                "required_columns_found": proof["required_columns_found"],
                "required_columns_missing": proof["required_columns_missing"],
                "promotion_recommendation": "Eligible for future human-reviewed promotion as story metadata source.",
                "semantic_risks": ["Story metadata only; no drift or check verdict is unlocked."],
                "derived_elevation_supported": proof["derived_elevation_supported"],
                "elevation_is_direct_column": proof["elevation_is_direct_column"],
                "story_definitions_table": proof["story_definitions_table"],
                "tower_and_base_story_definition_table": proof["tower_and_base_story_definition_table"],
                "base_elevation_column": proof["base_elevation_column"],
            }
        return {
            "source_status": "NEEDS_LIVE_PROBE",
            "required_columns_found": proof["required_columns_found"],
            "required_columns_missing": proof["required_columns_missing"],
            "promotion_recommendation": "Keep blocked until Story/Name + Height and direct Elevation or Tower/Base BSElev are proven live.",
            "semantic_risks": ["Story definition table missing required metadata columns or Tower/Base BSElev support."],
            "derived_elevation_supported": proof["derived_elevation_supported"],
            "elevation_is_direct_column": proof["elevation_is_direct_column"],
            "story_definitions_table": proof["story_definitions_table"],
            "tower_and_base_story_definition_table": proof["tower_and_base_story_definition_table"],
            "base_elevation_column": proof["base_elevation_column"],
        }

    if family.family_id == "pier_section_properties":
        proof = _pier_section_properties_proof(selected_tables, headers_by_table)
        supporting_context_names = (
            "Pier Assignments",
            "Wall Section Properties",
            "Area Assignments - Summary",
            "Wall Bays",
            "Wall Object Connectivity",
            "Area Assigns - Pier Labels",
            "Area Assigns - Sect Prop",
            "Wall Property Def - Specified",
            "Area Section Props - Summary",
        )
        has_supporting_context = any(_normalize_token(name) in selected_norms for name in supporting_context_names)
        if proof["verified"]:
            return {
                "source_status": "VERIFIED_LIVE_CANDIDATE",
                "required_columns_found": proof["required_columns_found"],
                "required_columns_missing": proof["required_columns_missing"],
                "promotion_recommendation": "Eligible for future human-reviewed promotion as direct pier section geometry/material evidence.",
                "semantic_risks": ["Direct pier section geometry evidence only; no wall/pier force, capacity, or detailing check is unlocked."],
                "direct_section_geometry_present": proof["direct_section_geometry_present"],
                "section_name_column_present": proof["section_name_column_present"],
                "material_present": proof["material_present"],
                "direct_pier_section_table": proof["direct_table"],
            }
        if has_supporting_context:
            return {
                "source_status": "PARTIAL_CONTEXT_ONLY",
                "required_columns_found": proof["required_columns_found"] or found,
                "required_columns_missing": proof["required_columns_missing"] or missing,
                "promotion_recommendation": "Do not promote as direct pier_section_properties without direct Pier Section Properties geometry evidence.",
                "semantic_risks": ["Pier assignment, wall connectivity, wall property, and area section tables are supporting/context evidence only unless combined with direct Pier Section Properties geometry."],
                "direct_section_geometry_present": proof["direct_section_geometry_present"],
                "section_name_column_present": proof["section_name_column_present"],
                "material_present": proof["material_present"],
                "direct_pier_section_table": proof["direct_table"],
            }
        return {
            "source_status": "NEEDS_LIVE_PROBE",
            "required_columns_found": proof["required_columns_found"] or found,
            "required_columns_missing": proof["required_columns_missing"] or missing,
            "promotion_recommendation": "Keep blocked until direct pier section geometry semantics are proven live.",
            "semantic_risks": ["No direct pier section geometry proof."],
            "direct_section_geometry_present": proof["direct_section_geometry_present"],
            "section_name_column_present": proof["section_name_column_present"],
            "material_present": proof["material_present"],
            "direct_pier_section_table": proof["direct_table"],
        }

    raise ValueError(f"Unsupported family: {family.family_id}")


def build_summary(
    *,
    live_etabs_connected: bool,
    probe_passed: bool,
    family_ids: Sequence[str],
    matches: Mapping[str, Mapping[str, Any]],
    headers_by_table: Mapping[str, Sequence[str]],
    fetch_status_by_table: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    families: dict[str, Any] = {}
    for family_id in family_ids:
        family = TARGET_FAMILIES[family_id]
        selected = list(matches.get(family_id, {}).get("selected_tables", []))
        evaluation = evaluate_family_status(family, selected, headers_by_table, fetch_status_by_table)
        row = {
            "source_status": evaluation["source_status"],
            "selected_tables": selected,
            "required_columns_found": evaluation["required_columns_found"],
            "required_columns_missing": evaluation["required_columns_missing"],
            "semantic_role": family.semantic_role,
            "promotion_recommendation": evaluation["promotion_recommendation"],
            "semantic_risks": evaluation["semantic_risks"],
            "check_unlock_allowed": False,
        }
        for optional_key in (
            "derived_elevation_supported",
            "elevation_is_direct_column",
            "story_definitions_table",
            "tower_and_base_story_definition_table",
            "base_elevation_column",
            "direct_section_geometry_present",
            "section_name_column_present",
            "material_present",
            "direct_pier_section_table",
        ):
            if optional_key in evaluation:
                row[optional_key] = evaluation[optional_key]
        families[family_id] = row
    return {
        "sprint": SPRINT,
        "live_etabs_connected": bool(live_etabs_connected),
        "probe_passed": bool(probe_passed),
        "safe_to_implement_checks_now": False,
        "families": families,
    }


def build_promotion_recommendations(summary: Mapping[str, Any]) -> dict[str, Any]:
    families = dict(summary.get("families") or {})
    eligible = {
        family_id: row.get("source_status") == "VERIFIED_LIVE_CANDIDATE"
        for family_id, row in families.items()
    }
    return {
        "sprint": SPRINT,
        "promote_now": False,
        "eligible_for_future_promotion": eligible,
        "required_follow_up": {
            family_id: "human review and later stable contract promotion sprint" if is_eligible else "additional bounded live proof required"
            for family_id, is_eligible in eligible.items()
        },
        "semantic_risks": {
            family_id: row.get("semantic_risks", [])
            for family_id, row in families.items()
        },
        "reason": "C13.2-P3 is evidence-only. Stable contracts and checks remain unchanged.",
        "safe_to_implement_checks_now": False,
    }


def _empty_required_artifacts(out: Path, family_ids: Sequence[str]) -> None:
    empty_matches = {
        family_id: {
            "expected_table_names": list(TARGET_FAMILIES[family_id].expected_table_names),
            "exact_matches": [],
            "fallback_candidates": [],
            "selected_tables": [],
            "candidate_count_before_cap": 0,
            "candidate_count_after_cap": 0,
            "candidate_truncation_applied": False,
            "match_strategy": "not_attempted_no_live",
            "notes": ["No --live-etabs supplied; COM/ETABS access was not attempted."],
        }
        for family_id in family_ids
    }
    summary = build_summary(
        live_etabs_connected=False,
        probe_passed=False,
        family_ids=family_ids,
        matches=empty_matches,
        headers_by_table={},
        fetch_status_by_table={},
    )
    _write_json(out / "available_tables_summary.json", {"available_table_count": 0, "available_tables": []})
    _write_json(out / "target_table_matches.json", empty_matches)
    _write_json(out / "fetched_table_headers.json", {})
    _write_json(out / "fetched_table_samples.json", {})
    _write_json(out / "c13_2_p3_blocked_source_probe_summary.json", summary)
    _write_json(out / "c13_2_p3_promotion_recommendations.json", build_promotion_recommendations(summary))


def run_no_live(out: Path, family_ids: Sequence[str]) -> int:
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "connection_report.json", {
        "sprint": SPRINT,
        "live_etabs_requested": False,
        "live_etabs_connected": False,
        "probe_passed": False,
        "message": "No --live-etabs supplied; diagnostic no-live mode only.",
        "safe_to_implement_checks_now": False,
    })
    _empty_required_artifacts(out, family_ids)
    return 2


def _fetch_live_table(database_tables: Any, table_name: str, *, max_rows: int) -> tuple[dict[str, Any], dict[str, Any], Sequence[str], str]:
    try:
        from tbdy_engine.providers.etabs_display_table_fetcher import fetch_display_table

        result = fetch_display_table(database_tables, table_name, max_rows=max_rows)
        parsed = result.parsed
        columns = [str(col) for col in parsed.field_keys]
        rows = [dict(row) for row in parsed.rows[:max_rows]]
        fetch_status = "OK" if columns or rows else str(parsed.fetch_status or "EMPTY")
        header_payload = {
            "table_name": table_name,
            "columns": columns,
            "normalized_columns": [_normalize_token(col) for col in columns],
            "row_count_if_available": parsed.row_count_reported if parsed.row_count_reported is not None else len(rows),
            "fetch_status": fetch_status,
            "error": None,
        }
        sample_payload = {
            "table_name": table_name,
            "sample_rows": rows,
            "max_rows": max_rows,
            "sample_row_count": len(rows),
            "fetch_status": fetch_status,
        }
        return header_payload, sample_payload, columns, fetch_status
    except Exception as exc:  # pragma: no cover - requires ETABS failure shapes
        return (
            {
                "table_name": table_name,
                "columns": [],
                "normalized_columns": [],
                "row_count_if_available": None,
                "fetch_status": "FAILED",
                "error": str(exc),
            },
            {
                "table_name": table_name,
                "sample_rows": [],
                "max_rows": max_rows,
                "sample_row_count": 0,
                "fetch_status": "FAILED",
                "error": str(exc),
            },
            [],
            "FAILED",
        )


def run_live(out: Path, family_ids: Sequence[str], *, max_candidate_tables_per_family: int, max_rows_per_table: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    try:
        from tbdy_engine.etabs.connection import ETABSConnection, get_available_tables
    except Exception as exc:  # pragma: no cover - local no-live normally avoids imports
        _write_json(out / "connection_report.json", {
            "sprint": SPRINT,
            "live_etabs_requested": True,
            "live_etabs_connected": False,
            "probe_passed": False,
            "message": f"ETABS helper import failed: {exc}",
            "safe_to_implement_checks_now": False,
        })
        _empty_required_artifacts(out, family_ids)
        return 2

    connection = ETABSConnection()
    ok, message = connection.connect()
    if not ok:
        _write_json(out / "connection_report.json", {
            "sprint": SPRINT,
            "live_etabs_requested": True,
            "live_etabs_connected": False,
            "probe_passed": False,
            "message": message,
            "safe_to_implement_checks_now": False,
        })
        _empty_required_artifacts(out, family_ids)
        return 2

    sap = connection.get_sap()
    available_tables = list(get_available_tables(sap))
    database_tables = sap.DatabaseTables
    _write_json(out / "connection_report.json", {
        "sprint": SPRINT,
        "live_etabs_requested": True,
        "live_etabs_connected": True,
        "probe_passed": True,
        "message": message,
        "safe_to_implement_checks_now": False,
    })
    _write_json(out / "available_tables_summary.json", {
        "available_table_count": len(available_tables),
        "available_tables": available_tables,
    })

    matches = {
        family_id: match_target_tables(
            available_tables,
            TARGET_FAMILIES[family_id],
            max_candidate_tables_per_family=max_candidate_tables_per_family,
        )
        for family_id in family_ids
    }
    _write_json(out / "target_table_matches.json", matches)

    fetched_headers: dict[str, dict[str, Any]] = {}
    fetched_samples: dict[str, dict[str, Any]] = {}
    headers_by_table: dict[str, Sequence[str]] = {}
    fetch_status_by_table: dict[str, str] = {}
    for family_match in matches.values():
        for table_name in family_match.get("selected_tables", []):
            if table_name in fetched_headers:
                continue
            header_payload, sample_payload, columns, fetch_status = _fetch_live_table(
                database_tables,
                table_name,
                max_rows=max_rows_per_table,
            )
            fetched_headers[table_name] = header_payload
            fetched_samples[table_name] = sample_payload
            headers_by_table[table_name] = columns
            fetch_status_by_table[table_name] = fetch_status

    _write_json(out / "fetched_table_headers.json", fetched_headers)
    _write_json(out / "fetched_table_samples.json", fetched_samples)
    summary = build_summary(
        live_etabs_connected=True,
        probe_passed=True,
        family_ids=family_ids,
        matches=matches,
        headers_by_table=headers_by_table,
        fetch_status_by_table=fetch_status_by_table,
    )
    _write_json(out / "c13_2_p3_blocked_source_probe_summary.json", summary)
    _write_json(out / "c13_2_p3_promotion_recommendations.json", build_promotion_recommendations(summary))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C13.2-P3 targeted blocked-source live proof probe.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--live-etabs", action="store_true")
    parser.add_argument("--max-candidate-tables-per-family", type=int, default=5)
    parser.add_argument("--max-rows-per-table", type=int, default=25)
    parser.add_argument("--target-family", choices=TARGET_FAMILY_CHOICES, default="all")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    family_ids = _selected_family_ids(args.target_family)
    if args.max_candidate_tables_per_family < 1:
        parser.error("--max-candidate-tables-per-family must be >= 1")
    if args.max_rows_per_table < 1:
        parser.error("--max-rows-per-table must be >= 1")
    if not args.live_etabs:
        return run_no_live(args.out, family_ids)
    return run_live(
        args.out,
        family_ids,
        max_candidate_tables_per_family=args.max_candidate_tables_per_family,
        max_rows_per_table=args.max_rows_per_table,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
