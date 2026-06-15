#!/usr/bin/env python
"""C13.2-P0 live ETABS contract-source probe.

Probe-only utility for future TBDY source-contract planning.

Safety rules:
- Default profile is ``current_product`` and fetches only three canonical exact
  ETABS tables: Frame Assignments - Summary, Frame Section Property Definitions
  - Concrete Rectangular, and Modal Participating Mass Ratios.
- Broad keyword matches are capped before any table fetch.
- Weak one-word keywords such as Summary, Material, Area, Wall, Drift, Forces,
  Properties, and Assignment cannot create fetch candidates alone.
- ``exact_only`` and ``exact_only_when_requested`` policies never fall back to
  keyword matching.
- SEMANTIC_REVIEW families are never classified as VERIFIED_LIVE.
- VERIFIED_LIVE requires both usable headers/sample rows and alias-aware
  expected-header validation when required columns are declared.

This script must not resolve features, execute checks, emit CheckResult, mutate
catalogs/schemas, or edit the ETABS model.
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

from tbdy_engine.etabs.connection import ETABSConnection, get_available_tables
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import (
    fetch_display_table,
    select_output_for_display,
)

READINESS_VALUES = {
    "VERIFIED_LIVE",
    "PROBED_PARTIAL",
    "NEEDS_LIVE_PROBE",
    "NOT_FOUND",
    "SEMANTIC_REVIEW",
}

FETCH_POLICIES = {
    "exact_only",
    "exact_first_capped_keyword",
    "capped_keyword",
    "exact_only_when_requested",
    "capped_keyword_when_requested",
}

WEAK_ONE_WORD_KEYWORDS = {
    "summary",
    "material",
    "area",
    "wall",
    "story",
    "drift",
    "forces",
    "force",
    "properties",
    "property",
    "assignment",
    "assignments",
    "section",
}

SEMANTIC_REVIEW_FAMILIES = {
    "concrete_beam_design_summary",
    "concrete_beam_flexure_envelope",
    "concrete_beam_shear_envelope",
    "concrete_column_design_summary",
    "concrete_column_pmm_envelope",
    "concrete_column_shear_envelope",
    "concrete_joint_design_summary",
    "concrete_joint_envelope",
    "concrete_wall_design_summary",
    "shear_wall_design_summary",
    "wall_forces_or_pier_forces",
}

OUTPUT_DEPENDENT_FAMILIES = {
    "story_drifts",
    "story_max_over_avg_drifts",
    "base_reactions",
    "concrete_beam_design_summary",
    "concrete_beam_flexure_envelope",
    "concrete_beam_shear_envelope",
    "concrete_column_design_summary",
    "concrete_column_pmm_envelope",
    "concrete_column_shear_envelope",
    "concrete_joint_design_summary",
    "concrete_joint_envelope",
    "concrete_wall_design_summary",
    "shear_wall_design_summary",
    "wall_forces_or_pier_forces",
}

GENERATED_ARTIFACTS = [
    "connection_report.json",
    "available_tables.json",
    "target_table_matches.json",
    "target_table_headers.json",
    "target_table_sample_rows.json",
    "raw_return_shape_report.json",
    "source_readiness_observations.json",
    "c13_2_scope_recommendation.md",
    "probe_summary.json",
]

# Required logical header -> accepted live/export aliases. This protects C13.2
# from treating an alias mismatch as VERIFIED_LIVE while still accepting real
# ETABS/export variations already seen in older workbook exports.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "UniqueName": ("UniqueName", "Unique Name", "GUID"),
    "Label": ("Label", "Frame", "Beam", "Column", "Object Label"),
    "Story": ("Story", "Story Name"),
    "Type": ("Type", "Design Type", "Object Type", "Frame Type"),
    "DesignSect": ("DesignSect", "Design Section", "DesignSec", "Design Sect"),
    "AnalysisSect": ("AnalysisSect", "Analysis Section", "AnalysisSec", "Analysis Sect", "Section"),
    "Length": ("Length", "Len"),
    "Name": ("Name", "SectionName", "Section Name", "Property", "PropName"),
    "t2": ("t2", "T2", "Width", "B", "b", "bw"),
    "t3": ("t3", "T3", "Depth", "H", "h", "d"),
    "Area": ("Area", "A"),
    "Material": ("Material", "Mat", "Material Name"),
    "Case": ("Case", "OutputCase", "Output Case", "Load Case/Combo"),
    "Mode": ("Mode", "Mode Number"),
    "Period": ("Period", "Period sec", "Period (sec)", "T"),
    "UX": ("UX", "U1"),
    "UY": ("UY", "U2"),
    "UZ": ("UZ", "U3"),
    "SumUX": ("SumUX", "Sum UX", "Cumulative UX", "Cumul UX"),
    "SumUY": ("SumUY", "Sum UY", "Cumulative UY", "Cumul UY"),
    "SumUZ": ("SumUZ", "Sum UZ", "Cumulative UZ", "Cumul UZ"),
    "OutputCase": ("OutputCase", "Output Case", "Load Case/Combo", "Case"),
    "Direction": ("Direction", "Dir"),
    "Drift": ("Drift", "Story Drift"),
    "MaxDrift": ("MaxDrift", "Max Drift", "Maximum Drift"),
    "AvgDrift": ("AvgDrift", "Avg Drift", "Average Drift"),
    "Ratio": ("Ratio", "Max/Avg", "Max Over Avg", "MaxOverAvg"),
    "Height": ("Height", "Story Height", "H"),
    "Elevation": ("Elevation", "Elev"),
    "FX": ("FX", "F1", "X Force"),
    "FY": ("FY", "F2", "Y Force"),
    "FZ": ("FZ", "F3", "Z Force"),
    "MX": ("MX", "M1", "X Moment"),
    "MY": ("MY", "M2", "Y Moment"),
    "MZ": ("MZ", "M3", "Z Moment"),
    "Frame": ("Frame", "Frame Label", "Label", "UniqueName", "Unique Name"),
    "Station": ("Station", "Location", "Loc"),
    "AsTop": ("AsTop", "As Top", "Top As", "Top Rebar"),
    "AsBottom": ("AsBottom", "AsBot", "As Bottom", "Bottom As", "Bottom Rebar"),
    "VRebar": ("VRebar", "V Rebar", "Asw", "Shear Rebar"),
    "Beam": ("Beam", "Frame", "Label"),
    "Location": ("Location", "Station", "Loc"),
    "MomentTop": ("MomentTop", "Moment Top", "MTop", "Top Moment"),
    "MomentBot": ("MomentBot", "Moment Bottom", "MBot", "Bottom Moment"),
    "Shear": ("Shear", "V", "V2", "V3"),
    "VCombo": ("VCombo", "V Combo", "Combo"),
    "Column": ("Column", "Frame", "Label"),
    "PMMRatio": ("PMMRatio", "PMM Ratio", "P-M-M Ratio", "Ratio"),
    "Pier": ("Pier", "Pier Label", "PierName", "Pier Name"),
    "Thickness": ("Thickness", "Thick", "t"),
    "AsVertical": ("AsVertical", "As Vertical", "Vertical Rebar"),
    "AsHorizontal": ("AsHorizontal", "As Horizontal", "Horizontal Rebar"),
    "RhoV": ("RhoV", "Rho V", "Vertical Ratio"),
    "RhoH": ("RhoH", "Rho H", "Horizontal Ratio"),
}


@dataclass(frozen=True, slots=True)
class SourceFamily:
    family_id: str
    tier: int
    purpose: str
    fetch_policy: str = "exact_only"
    candidate_exact_names: tuple[str, ...] = ()
    candidate_keywords: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()
    optional_columns: tuple[str, ...] = ()
    semantic_status: str = ""


TARGET_SOURCE_FAMILIES: tuple[SourceFamily, ...] = (
    # Tier 0 — accepted current product, exact-only canonical names.
    SourceFamily(
        "frame_assignments_summary",
        0,
        "frame object identity, Type, DesignSect/AnalysisSect, story/label",
        "exact_only",
        ("Frame Assignments - Summary",),
        ("Frame", "Assignment", "Summary"),
        ("UniqueName", "Label", "Story", "Type", "DesignSect"),
        ("AnalysisSect", "Length"),
    ),
    SourceFamily(
        "concrete_rectangular_frame_sections",
        0,
        "concrete rectangular frame section dimensions",
        "exact_only",
        ("Frame Section Property Definitions - Concrete Rectangular",),
        ("Frame Section", "Concrete Rectangular"),
        ("Name", "t2", "t3"),
        ("Area", "Material"),
    ),
    SourceFamily(
        "modal_participating_mass",
        0,
        "modal mass participation table",
        "exact_only",
        ("Modal Participating Mass Ratios",),
        ("Modal", "Participating", "Mass"),
        ("Mode", "Period", "UX", "UY", "SumUX", "SumUY"),
        ("Case", "UZ", "SumUZ"),
    ),
    # Tier 2 — story/global readiness, exact-first + capped keyword.
    SourceFamily(
        "story_definitions",
        2,
        "story names, elevations and heights",
        "exact_first_capped_keyword",
        ("Story Definitions", "Story Data", "Story Information"),
        ("Story Definition", "Story Data", "Stories"),
        ("Story", "Height", "Elevation"),
    ),
    SourceFamily(
        "story_drifts",
        2,
        "story drift rows by output case/direction/story",
        "exact_first_capped_keyword",
        ("Story Drifts",),
        ("Story Drift", "Diaphragm Drift"),
        ("Story", "OutputCase", "Direction", "Drift"),
        ("Label",),
    ),
    SourceFamily(
        "story_max_over_avg_drifts",
        2,
        "torsional irregularity/max over average drift evidence",
        "exact_first_capped_keyword",
        ("Story Max Over Avg Drifts", "Story Max/Avg Drifts"),
        ("Story Max Over Avg", "Max Over Avg Drift"),
        ("Story", "OutputCase", "Direction", "Ratio"),
        ("MaxDrift", "AvgDrift"),
    ),
    SourceFamily(
        "base_reactions",
        2,
        "base reaction summary for selected output case",
        "exact_first_capped_keyword",
        ("Base Reactions", "Base Reactions Summary"),
        ("Base Reaction",),
        ("OutputCase", "FX", "FY", "FZ"),
        ("MX", "MY", "MZ"),
    ),
    # Tier 3 — material context, never default.
    SourceFamily(
        "material_properties",
        3,
        "material names/types/basic mechanical properties",
        "capped_keyword",
        ("Material Properties", "Material Properties - Summary", "Material List"),
        ("Material Properties", "Material List"),
        (),
    ),
    SourceFamily(
        "concrete_material_properties",
        3,
        "concrete material properties such as fck-like values",
        "capped_keyword",
        ("Mat Prop - Concrete Data", "Material Properties - Concrete Data"),
        ("Concrete Material", "Mat Prop Concrete"),
        (),
    ),
    SourceFamily(
        "rebar_material_properties",
        3,
        "rebar material properties such as fyk-like values",
        "capped_keyword",
        ("Mat Prop - Rebar Data", "Material Properties - Rebar Data"),
        ("Rebar Material", "Mat Prop Rebar"),
        (),
    ),
    SourceFamily(
        "frame_section_material_assignments",
        3,
        "section to material mapping",
        "capped_keyword",
        ("Frame Prop - Summary", "Frame Property Summary"),
        ("Frame Section Material", "Frame Prop Summary"),
        (),
    ),
    # Tier 4 — design outputs, evidence only / semantic review.
    SourceFamily(
        "concrete_beam_design_summary",
        4,
        "ETABS concrete beam design summary; required rebar evidence only",
        "exact_only_when_requested",
        ("Concrete Beam Design Summary - TS 500-2000(R2018)", "Concrete Beam Design Summary"),
        ("Concrete Beam Design", "Beam Design Summary"),
        ("Frame", "Station", "AsTop", "AsBottom"),
        ("VRebar", "PMMRatio"),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_beam_flexure_envelope",
        4,
        "ETABS concrete beam flexure envelope; demand evidence only",
        "exact_only_when_requested",
        ("Concrete Beam Flexure Envelope - TS 500-2000(R2018)", "Concrete Beam Flexure Envelope"),
        ("Concrete Beam Flexure", "Beam Flexure Envelope"),
        ("Beam", "Location"),
        ("MomentTop", "MomentBot", "AsTop", "AsBottom"),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_beam_shear_envelope",
        4,
        "ETABS concrete beam shear envelope; demand evidence only",
        "exact_only_when_requested",
        ("Concrete Beam Shear Envelope - TS 500-2000(R2018)", "Concrete Beam Shear Envelope"),
        ("Concrete Beam Shear", "Beam Shear Envelope"),
        ("Beam", "Location"),
        ("Shear", "VCombo"),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_column_design_summary",
        4,
        "ETABS concrete column design summary; PMM/rebar evidence only",
        "exact_only_when_requested",
        ("Concrete Column Design Summary - TS 500-2000(R2018)", "Concrete Column Design Summary"),
        ("Concrete Column Design", "Column Design Summary"),
        ("Column",),
        ("PMMRatio",),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_column_pmm_envelope",
        4,
        "ETABS concrete column PMM envelope evidence only",
        "exact_only_when_requested",
        ("Concrete Column PMM Envelope - TS 500-2000(R2018)", "Concrete Column PMM Envelope"),
        ("Concrete Column PMM", "Column PMM Envelope"),
        ("Column",),
        ("PMMRatio",),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_column_shear_envelope",
        4,
        "ETABS concrete column shear envelope evidence only",
        "exact_only_when_requested",
        ("Concrete Column Shear Envelope - TS 500-2000(R2018)", "Concrete Column Shear Envelope"),
        ("Concrete Column Shear", "Column Shear Envelope"),
        ("Column",),
        ("Shear",),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_joint_design_summary",
        4,
        "ETABS concrete joint design summary evidence only",
        "exact_only_when_requested",
        ("Concrete Joint Design Summary - TS 500-2000(R2018)", "Concrete Joint Design Summary"),
        ("Concrete Joint Design", "Joint Design Summary"),
        (),
        (),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "concrete_joint_envelope",
        4,
        "ETABS concrete joint envelope evidence only",
        "exact_only_when_requested",
        ("Concrete Joint Envelope - TS 500-2000(R2018)", "Concrete Joint Envelope"),
        ("Concrete Joint Envelope",),
        (),
        (),
        "SEMANTIC_REVIEW",
    ),
    # Tier 5 — wall/area, never default.
    SourceFamily(
        "area_assignments_summary",
        5,
        "area/shell assignment identity",
        "capped_keyword_when_requested",
        ("Area Assigns - Summary", "Area Assignments - Summary"),
        ("Area Assign", "Area Assignment"),
    ),
    SourceFamily(
        "wall_section_properties",
        5,
        "wall/slab/area section thickness/material source readiness",
        "capped_keyword_when_requested",
        ("Wall Property Definitions - Specified", "Area Section Props - Summary", "Area Section Property Definitions"),
        ("Wall Property", "Area Section", "Shell Section"),
        (),
    ),
    SourceFamily(
        "pier_assignments",
        5,
        "pier/wall label grouping",
        "capped_keyword_when_requested",
        ("Area Assigns - Pier Labels", "Pier Assignments", "Pier Labels"),
        ("Pier Assignment", "Pier Label"),
    ),
    SourceFamily(
        "pier_section_properties",
        5,
        "pier/wall section dimensions",
        "capped_keyword_when_requested",
        ("Pier Section Properties",),
        ("Pier Section",),
        ("Pier", "Length", "Thickness"),
    ),
    SourceFamily(
        "shear_wall_design_summary",
        5,
        "ETABS shear wall design summary; wall rebar evidence only",
        "capped_keyword_when_requested",
        ("Shear Wall Design Summary - TS 500-2000(R2018)", "Shear Wall Design Summary"),
        ("Shear Wall Design", "Wall Design Summary"),
        ("Pier",),
        ("PMMRatio", "AsVertical", "AsHorizontal", "RhoV", "RhoH"),
        "SEMANTIC_REVIEW",
    ),
    SourceFamily(
        "wall_forces_or_pier_forces",
        5,
        "wall/pier force table evidence only",
        "capped_keyword_when_requested",
        ("Pier Forces", "Wall Forces"),
        ("Pier Forces", "Wall Forces"),
        (),
        (),
        "SEMANTIC_REVIEW",
    ),
)

PROBE_PROFILES: dict[str, dict[str, Any]] = {
    "current_product": {
        "families": [
            "frame_assignments_summary",
            "concrete_rectangular_frame_sections",
            "modal_participating_mass",
        ],
        "timeout_risk": "low",
    },
    "column_geometry": {
        "families": [
            "frame_assignments_summary",
            "concrete_rectangular_frame_sections",
        ],
        "timeout_risk": "low",
    },
    "story_global": {
        "families": [
            "story_definitions",
            "story_drifts",
            "story_max_over_avg_drifts",
            "base_reactions",
        ],
        "timeout_risk": "medium",
    },
    "material_context": {
        "families": [
            "material_properties",
            "concrete_material_properties",
            "rebar_material_properties",
            "frame_section_material_assignments",
        ],
        "timeout_risk": "high",
    },
    "beam_engineering": {
        "families": [
            "concrete_beam_design_summary",
            "concrete_beam_flexure_envelope",
            "concrete_beam_shear_envelope",
        ],
        "timeout_risk": "low",
    },
    "column_engineering": {
        "families": [
            "concrete_column_design_summary",
            "concrete_column_pmm_envelope",
            "concrete_column_shear_envelope",
        ],
        "timeout_risk": "low",
    },
    "joint_design": {
        "families": [
            "concrete_joint_design_summary",
            "concrete_joint_envelope",
        ],
        "timeout_risk": "low",
    },
    "wall_area": {
        "families": [
            "area_assignments_summary",
            "wall_section_properties",
            "pier_assignments",
            "pier_section_properties",
            "shear_wall_design_summary",
            "wall_forces_or_pier_forces",
        ],
        "timeout_risk": "high",
    },
    "full_inventory": {
        "families": "all",
        "timeout_risk": "high",
    },
}


def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").casefold())


def _short_repr(value: Any, limit: int = 240) -> str:
    try:
        text = repr(value)
    except Exception as exc:  # pragma: no cover - defensive for COM objects
        text = f"<repr failed: {type(exc).__name__}: {exc}>"
    if len(text) > limit:
        return text[: limit - 14] + "...<truncated>"
    return text


def _json_safe(value: Any) -> Any:
    try:
        return to_jsonable(value)
    except TypeError:
        if isinstance(value, Mapping):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_json_safe(v) for v in value]
        return _short_repr(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _keyword_parts(keyword: str) -> list[str]:
    return [p for p in re.split(r"[^a-z0-9]+", str(keyword or "").casefold()) if p]


def _is_phrase_keyword(keyword: str) -> bool:
    return len(_keyword_parts(keyword)) >= 2


def _keyword_evidence(table_name: str, keywords: Sequence[str]) -> dict[str, Any]:
    table_norm = _norm(table_name)
    phrase_matches: list[str] = []
    meaningful: list[str] = []
    weak: list[str] = []

    for keyword in keywords:
        keyword_text = str(keyword or "")
        keyword_norm = _norm(keyword_text)
        if not keyword_norm or keyword_norm not in table_norm:
            continue
        if _is_phrase_keyword(keyword_text):
            phrase_matches.append(keyword_text)
        elif keyword_text.casefold() in WEAK_ONE_WORD_KEYWORDS:
            weak.append(keyword_text)
        else:
            meaningful.append(keyword_text)

    is_fetch_candidate = bool(phrase_matches) or len(meaningful) >= 2 or (bool(meaningful) and bool(weak))
    score = sum(1000 for _ in phrase_matches) + sum(100 for _ in meaningful) + sum(5 for _ in weak)
    return {
        "phrase_matches": phrase_matches,
        "meaningful_keyword_matches": meaningful,
        "weak_keyword_matches": weak,
        "is_fetch_candidate": is_fetch_candidate,
        "score": score,
    }


def _family_by_id() -> dict[str, SourceFamily]:
    return {family.family_id: family for family in TARGET_SOURCE_FAMILIES}


def validate_probe_profile(probe_profile: str) -> tuple[bool, list[str], list[SourceFamily]]:
    profile = PROBE_PROFILES.get(probe_profile)
    if profile is None:
        return False, [f"Unknown probe profile: {probe_profile}"], []
    family_ids = profile.get("families")
    known = _family_by_id()
    if family_ids == "all":
        return True, [], list(TARGET_SOURCE_FAMILIES)
    missing = [family_id for family_id in list(family_ids or []) if family_id not in known]
    if missing:
        return False, [f"Probe profile '{probe_profile}' references unknown family IDs: {', '.join(missing)}"], []
    return True, [], [known[family_id] for family_id in family_ids]


def match_target_tables(
    available_table_names: Sequence[str],
    families: Sequence[SourceFamily],
    *,
    max_candidate_tables_per_family: int = 5,
) -> list[dict[str, Any]]:
    exact_lookup: dict[str, list[str]] = {}
    for name in available_table_names:
        exact_lookup.setdefault(_norm(name), []).append(name)

    results: list[dict[str, Any]] = []
    for family in families:
        exact_matches: list[str] = []
        for exact in family.candidate_exact_names:
            for matched in exact_lookup.get(_norm(exact), []):
                if matched not in exact_matches:
                    exact_matches.append(matched)

        keyword_evidence_by_table: dict[str, dict[str, Any]] = {}
        candidate_count_before_cap = 0
        candidate_count_after_cap = 0
        candidate_truncation_applied = False

        if exact_matches:
            matched_tables = exact_matches
            match_status = "EXACT_MATCH" if len(exact_matches) == 1 else "MULTIPLE_CANDIDATES"
            candidate_count_before_cap = len(exact_matches)
            candidate_count_after_cap = len(exact_matches)
        elif family.fetch_policy in {"exact_only", "exact_only_when_requested"}:
            matched_tables = []
            match_status = "NOT_FOUND"
        else:
            scored: list[tuple[str, int]] = []
            for name in available_table_names:
                evidence = _keyword_evidence(name, family.candidate_keywords)
                if evidence["is_fetch_candidate"]:
                    keyword_evidence_by_table[name] = evidence
                    scored.append((name, int(evidence["score"])))
            ranked = [name for name, _score in sorted(scored, key=lambda item: (-item[1], item[0]))]
            ranked = list(dict.fromkeys(ranked))
            candidate_count_before_cap = len(ranked)
            cap = max(0, int(max_candidate_tables_per_family))
            matched_tables = ranked[:cap]
            candidate_count_after_cap = len(matched_tables)
            candidate_truncation_applied = candidate_count_after_cap < candidate_count_before_cap
            if not matched_tables:
                match_status = "NOT_FOUND"
            elif len(matched_tables) == 1:
                match_status = "KEYWORD_MATCH"
            else:
                match_status = "MULTIPLE_CANDIDATES"

        results.append(
            {
                "family_id": family.family_id,
                "tier": family.tier,
                "purpose": family.purpose,
                "fetch_policy": family.fetch_policy,
                "fetch_mode_used": family.fetch_policy,
                "semantic_status": family.semantic_status or None,
                "candidate_exact_names": list(family.candidate_exact_names),
                "candidate_keywords": list(family.candidate_keywords),
                "required_columns": list(family.required_columns),
                "optional_columns": list(family.optional_columns),
                "matched_tables": matched_tables,
                "match_status": match_status,
                "candidate_count_before_cap": candidate_count_before_cap,
                "candidate_count_after_cap": candidate_count_after_cap,
                "candidate_truncation_applied": candidate_truncation_applied,
                "probe_profile": "",
                "keyword_match_evidence": {
                    table: {
                        "phrase_matches": evidence["phrase_matches"],
                        "meaningful_keyword_matches": evidence["meaningful_keyword_matches"],
                        "weak_keyword_matches": evidence["weak_keyword_matches"],
                        "score": evidence["score"],
                    }
                    for table, evidence in keyword_evidence_by_table.items()
                    if table in matched_tables
                },
            }
        )
    return results


def _candidate_header_aliases(logical_column: str) -> tuple[str, ...]:
    return HEADER_ALIASES.get(logical_column, (logical_column,))


def _has_any_header(headers: Sequence[Any], aliases: Sequence[str]) -> bool:
    header_norms = {_norm(header) for header in headers if _norm(header)}
    for alias in aliases:
        alias_norm = _norm(alias)
        if not alias_norm:
            continue
        for header_norm in header_norms:
            if alias_norm == header_norm:
                return True
            # This permissive containment handles exports like "Output Case" vs
            # "OutputCase" and "Max Drift X" vs "MaxDrift" while avoiding very
            # short accidental matches.
            if len(alias_norm) > 2 and (alias_norm in header_norm or header_norm in alias_norm):
                return True
    return False


def expected_header_validation(
    family_id: str,
    headers: Sequence[Any],
    required: Sequence[str],
    optional: Sequence[str],
) -> dict[str, Any]:
    matched_required: list[str] = []
    missing_required: list[str] = []
    matched_optional: list[str] = []
    proof: dict[str, list[str]] = {}

    for column in required:
        aliases = _candidate_header_aliases(column)
        if _has_any_header(headers, aliases):
            matched_required.append(column)
            proof[column] = list(aliases)
        else:
            missing_required.append(column)
    for column in optional:
        aliases = _candidate_header_aliases(column)
        if _has_any_header(headers, aliases):
            matched_optional.append(column)

    return {
        "family_id": family_id,
        "validation_applies": bool(required),
        "passed": not missing_required,
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_optional": matched_optional,
        "alias_policy_used": True,
        "alias_proof": proof,
    }


def _raw_slot_summary(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, (list, tuple)):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        row: dict[str, Any] = {"index": index, "type": type(item).__name__, "repr": _short_repr(item)}
        if isinstance(item, (list, tuple, str)):
            row["len"] = len(item)
            if isinstance(item, (list, tuple)):
                row["sample"] = [_json_safe(value) for value in item[:8]]
        rows.append(row)
    return rows


def raw_return_shape_record(family_id: str, table_name: str, fetch_result: Any) -> dict[str, Any]:
    raw = getattr(fetch_result, "raw_response", None)
    parsed = getattr(fetch_result, "parsed", None)
    debug = dict(getattr(parsed, "debug", {}) or {}) if parsed is not None else {}
    selected = dict(getattr(fetch_result, "selected_signature", {}) or {})
    return {
        "family_id": family_id,
        "attempted_table_name": table_name,
        "method_used": "GetTableForDisplayArray",
        "raw_type": type(raw).__name__,
        "raw_length": len(raw) if isinstance(raw, (list, tuple, str)) else None,
        "raw_slot_summary": _raw_slot_summary(raw),
        "compact_shape_detected": bool(debug.get("compact_six_item_shape_detected")),
        "headers_slot": (debug.get("compact_shape_slots") or {}).get("headers_index"),
        "records_slot": (debug.get("compact_shape_slots") or {}).get("number_records_index"),
        "data_slot": (debug.get("compact_shape_slots") or {}).get("table_data_index"),
        "return_code_slot": (debug.get("compact_shape_slots") or {}).get("return_code_index"),
        "parse_status": selected.get("parser_status") or debug.get("row_parse_status") or getattr(parsed, "fetch_status", None),
        "parser_warning": debug.get("mismatch_reason"),
    }


def headers_record(family_id: str, table_name: str, fetch_result: Any | None = None, *, error: str | None = None) -> dict[str, Any]:
    if fetch_result is None:
        return {
            "family_id": family_id,
            "attempted_table_name": table_name,
            "fetch_status": "ERROR" if error else "TABLE_UNAVAILABLE",
            "return_code": None,
            "headers": [],
            "header_count": 0,
            "number_records": None,
            "error": error,
            "warning": None,
        }
    parsed = fetch_result.parsed
    debug = dict(parsed.debug or {})
    if parsed.fetch_status in {"FETCHED", "PARSED_ROWS"} or parsed.rows:
        status = "FETCHED"
    elif parsed.field_keys and not parsed.rows:
        status = "EMPTY"
    elif parsed.return_code not in {None, 0}:
        status = "TABLE_UNAVAILABLE"
    else:
        status = "EMPTY" if parsed.field_keys else "TABLE_UNAVAILABLE"
    return {
        "family_id": family_id,
        "attempted_table_name": table_name,
        "fetch_status": status,
        "return_code": parsed.return_code,
        "headers": list(parsed.field_keys),
        "header_count": len(parsed.field_keys),
        "number_records": debug.get("number_records", parsed.row_count_reported),
        "error": None,
        "warning": debug.get("mismatch_reason"),
    }


def sample_rows_record(
    family_id: str,
    table_name: str,
    rows: Sequence[Mapping[str, Any]],
    row_limit: int,
) -> dict[str, Any]:
    limited = [dict(row) for row in rows[:row_limit]]
    return {
        "family_id": family_id,
        "attempted_table_name": table_name,
        "sample_row_count": len(limited),
        "rows": limited,
        "row_limit": row_limit,
        "truncation_applied": len(rows) > row_limit,
    }


def _available_table_rows(table_names: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "table_key": _norm(name),
            "table_name": name,
            "import_type": None,
            "is_empty_hint": None,
            "source": "ETABS.DatabaseTables.GetAvailableTables",
        }
        for name in table_names
    ]


def _fetch_attempted_tables(
    database_tables: Any,
    matches: Sequence[Mapping[str, Any]],
    *,
    max_sample_rows: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    headers: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    raw_shapes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for match in matches:
        family_id = str(match["family_id"])
        for table_name in list(match.get("matched_tables") or []):
            key = (family_id, str(table_name))
            if key in seen:
                continue
            seen.add(key)
            try:
                result = fetch_display_table(database_tables, table_name, max_rows=max_sample_rows)
                headers.append(headers_record(family_id, table_name, result))
                samples.append(sample_rows_record(family_id, table_name, result.parsed.rows, max_sample_rows))
                raw_shapes.append(raw_return_shape_record(family_id, table_name, result))
            except Exception as exc:  # pragma: no cover - live COM failure path
                headers.append(headers_record(family_id, table_name, None, error=str(exc)))
                samples.append(sample_rows_record(family_id, table_name, [], max_sample_rows))
                raw_shapes.append(
                    {
                        "family_id": family_id,
                        "attempted_table_name": table_name,
                        "method_used": "GetTableForDisplayArray",
                        "raw_type": None,
                        "raw_length": None,
                        "raw_slot_summary": [],
                        "compact_shape_detected": False,
                        "headers_slot": None,
                        "records_slot": None,
                        "data_slot": None,
                        "return_code_slot": None,
                        "parse_status": "ERROR",
                        "parser_warning": str(exc),
                    }
                )
    return headers, samples, raw_shapes


def classify_source_readiness(
    family: SourceFamily,
    match: Mapping[str, Any],
    header_records: Sequence[Mapping[str, Any]],
    sample_records: Sequence[Mapping[str, Any]],
    *,
    display_selection_failed: bool = False,
) -> dict[str, Any]:
    family_id = family.family_id
    matched_tables = list(match.get("matched_tables") or [])
    family_headers = [record for record in header_records if record.get("family_id") == family_id]
    family_samples = [record for record in sample_records if record.get("family_id") == family_id]
    verified_names = [
        str(record.get("attempted_table_name"))
        for record in family_headers
        if record.get("fetch_status") in {"FETCHED", "EMPTY"} and record.get("headers")
    ]
    sample_count = sum(int(record.get("sample_row_count") or 0) for record in family_samples)
    all_headers = [header for record in family_headers for header in (record.get("headers") or [])]
    header_validation = expected_header_validation(family_id, all_headers, family.required_columns, family.optional_columns)

    if family.semantic_status == "SEMANTIC_REVIEW" and verified_names:
        return {
            "family_id": family_id,
            "tier": family.tier,
            "readiness_status": "SEMANTIC_REVIEW",
            "verified_table_names": verified_names,
            "sample_row_count": sample_count,
            "evidence_quality": "headers_and_rows" if sample_count else "headers_only",
            "expected_header_validation": header_validation,
            "blockers": ["engineering semantics require human review before any feature/check contract"],
            "recommendation": "Record as source evidence only; do not unlock checks.",
        }

    if display_selection_failed and family_id in OUTPUT_DEPENDENT_FAMILIES:
        return {
            "family_id": family_id,
            "tier": family.tier,
            "readiness_status": "PROBED_PARTIAL" if verified_names else "NEEDS_LIVE_PROBE",
            "verified_table_names": verified_names,
            "sample_row_count": sample_count,
            "evidence_quality": "headers_and_rows" if sample_count else "matched_name_only",
            "expected_header_validation": header_validation,
            "blockers": ["display selection failed"],
            "recommendation": "Retry after successful display selection.",
        }

    if not matched_tables:
        return {
            "family_id": family_id,
            "tier": family.tier,
            "readiness_status": "NOT_FOUND",
            "verified_table_names": [],
            "sample_row_count": 0,
            "evidence_quality": "none",
            "expected_header_validation": header_validation,
            "blockers": ["no plausible table found"],
            "recommendation": "Check available ETABS table catalog or ETABS version.",
        }

    if family.required_columns and not header_validation["passed"]:
        return {
            "family_id": family_id,
            "tier": family.tier,
            "readiness_status": "PROBED_PARTIAL",
            "verified_table_names": verified_names,
            "sample_row_count": sample_count,
            "evidence_quality": "headers_only_semantics_weak" if verified_names else "matched_name_only",
            "expected_header_validation": header_validation,
            "blockers": ["expected header proof failed: " + ", ".join(header_validation["missing_required"])],
            "recommendation": "Do not classify VERIFIED_LIVE until headers prove semantics.",
        }

    if verified_names and sample_count > 0:
        return {
            "family_id": family_id,
            "tier": family.tier,
            "readiness_status": "VERIFIED_LIVE",
            "verified_table_names": verified_names,
            "sample_row_count": sample_count,
            "evidence_quality": "headers_and_rows",
            "expected_header_validation": header_validation,
            "blockers": [],
            "recommendation": "Safe for source-contract planning; still no engineering check implementation in this sprint.",
        }

    if verified_names:
        return {
            "family_id": family_id,
            "tier": family.tier,
            "readiness_status": "PROBED_PARTIAL",
            "verified_table_names": verified_names,
            "sample_row_count": sample_count,
            "evidence_quality": "headers_only",
            "expected_header_validation": header_validation,
            "blockers": ["rows unavailable or sample empty"],
            "recommendation": "Retry with live ETABS model/selection if rows are expected.",
        }

    return {
        "family_id": family_id,
        "tier": family.tier,
        "readiness_status": "NEEDS_LIVE_PROBE",
        "verified_table_names": [],
        "sample_row_count": 0,
        "evidence_quality": "matched_name_only",
        "expected_header_validation": header_validation,
        "blockers": ["matched table did not produce usable headers/rows"],
        "recommendation": "Retry live probe or narrow candidate aliases.",
    }


def _md_table(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "_(none)_\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines) + "\n"


def _recommended_next_sprint(readiness: Sequence[Mapping[str, Any]], probe_profile: str) -> str:
    verified = {str(row.get("family_id")) for row in readiness if row.get("readiness_status") == "VERIFIED_LIVE"}
    if probe_profile == "current_product" and {"frame_assignments_summary", "concrete_rectangular_frame_sections", "modal_participating_mass"}.issubset(verified):
        return "C13.2 contract infrastructure using verified current product sources"
    if probe_profile == "column_geometry" and {"frame_assignments_summary", "concrete_rectangular_frame_sections"}.issubset(verified):
        return "C13.1 concrete column geometry product report"
    if probe_profile == "story_global" and verified:
        return "C13.3 story/global report contract planning"
    if probe_profile in {"beam_engineering", "column_engineering", "joint_design", "wall_area"}:
        return "semantic source review before any engineering check implementation"
    return "C13.2 report/source contract planning only"


def build_scope_recommendation(readiness: Sequence[Mapping[str, Any]], probe_profile: str) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in readiness:
        groups.setdefault(str(row.get("readiness_status")), []).append(dict(row))

    def rows_for(status: str) -> list[dict[str, Any]]:
        return [
            {
                "family_id": row.get("family_id"),
                "tier": row.get("tier"),
                "tables": ", ".join(row.get("verified_table_names") or []),
                "samples": row.get("sample_row_count"),
                "recommendation": row.get("recommendation"),
            }
            for row in groups.get(status, [])
        ]

    next_sprint = _recommended_next_sprint(readiness, probe_profile)
    parts = [
        "# C13.2-P0 Live ETABS Contract Source Probe Recommendation",
        "",
        f"Profile: **{probe_profile}**",
        f"Recommended next sprint: **{next_sprint}**.",
        "",
        "This probe is evidence-only. It does not implement checks, emit CheckResult, edit catalogs/schemas, or unlock rebar/flexure/shear/capacity/axial/N-M/wall design scope.",
        "",
        "## VERIFIED_LIVE",
        _md_table(["family_id", "tier", "tables", "samples", "recommendation"], rows_for("VERIFIED_LIVE")),
        "## SEMANTIC_REVIEW",
        _md_table(["family_id", "tier", "tables", "samples", "recommendation"], rows_for("SEMANTIC_REVIEW")),
        "## PROBED_PARTIAL",
        _md_table(["family_id", "tier", "tables", "samples", "recommendation"], rows_for("PROBED_PARTIAL")),
        "## NEEDS_LIVE_PROBE",
        _md_table(["family_id", "tier", "tables", "samples", "recommendation"], rows_for("NEEDS_LIVE_PROBE")),
        "## NOT_FOUND",
        _md_table(["family_id", "tier", "tables", "samples", "recommendation"], rows_for("NOT_FOUND")),
        "## Explicit exclusions",
        "- No engineering checks.",
        "- No CheckResult emission.",
        "- No feature/check catalog edits.",
        "- No schema edits.",
        "- No Excel production input or Streamlit/runtime/archx/runner_v2 path.",
    ]
    return "\n".join(parts)


def build_probe_summary(
    *,
    probe_profile: str,
    live_etabs_connected: bool,
    available_table_count: int,
    readiness: Sequence[Mapping[str, Any]],
    recommendation_markdown: str,
) -> dict[str, Any]:
    counts = {status: 0 for status in READINESS_VALUES}
    for row in readiness:
        status = str(row.get("readiness_status"))
        if status in counts:
            counts[status] += 1
    next_sprint = _recommended_next_sprint(readiness, probe_profile)
    has_current_product_core = {
        str(row.get("family_id"))
        for row in readiness
        if row.get("readiness_status") == "VERIFIED_LIVE"
    }.issuperset({"frame_assignments_summary", "concrete_rectangular_frame_sections", "modal_participating_mass"})
    return {
        "probe_passed": bool(live_etabs_connected) and (counts["VERIFIED_LIVE"] > 0 or counts["SEMANTIC_REVIEW"] > 0),
        "live_etabs_connected": bool(live_etabs_connected),
        "available_table_count": int(available_table_count),
        "verified_live_count": counts["VERIFIED_LIVE"],
        "probed_partial_count": counts["PROBED_PARTIAL"],
        "needs_live_probe_count": counts["NEEDS_LIVE_PROBE"],
        "not_found_count": counts["NOT_FOUND"],
        "semantic_review_count": counts["SEMANTIC_REVIEW"],
        "recommended_next_sprint": next_sprint,
        "safe_to_expand_contract_now": bool(has_current_product_core or counts["VERIFIED_LIVE"] > 0),
        "safe_to_implement_checks_now": False,
        "generated_artifacts": GENERATED_ARTIFACTS,
        "recommendation_markdown_size": len(recommendation_markdown),
    }


def _base_connection_report(*, live_etabs: bool, preferred_output_case: str | None, probe_profile: str) -> dict[str, Any]:
    return {
        "live_etabs_requested": bool(live_etabs),
        "live_etabs_connected": False,
        "etabs_model_available": False,
        "preferred_output_case": preferred_output_case,
        "display_selection_attempted": False,
        "display_selection_status": "NOT_ATTEMPTED",
        "probe_profile": probe_profile,
        "errors": [],
        "warnings": [],
    }


def run_live_probe(
    *,
    out: Path,
    probe_profile: str = "current_product",
    live_etabs: bool = False,
    preferred_output_case: str | None = None,
    max_sample_rows: int = 20,
    max_candidate_tables_per_family: int = 5,
) -> int:
    out.mkdir(parents=True, exist_ok=True)
    connection = _base_connection_report(
        live_etabs=live_etabs,
        preferred_output_case=preferred_output_case,
        probe_profile=probe_profile,
    )

    # Validate profile before ETABS connection.
    profile_ok, profile_errors, families = validate_probe_profile(probe_profile)
    if not profile_ok:
        connection["errors"].extend(profile_errors)
        _write_json(out / "connection_report.json", connection)
        return 2

    if max_sample_rows < 0:
        connection["errors"].append("--max-sample-rows must be non-negative")
        _write_json(out / "connection_report.json", connection)
        return 2
    if max_candidate_tables_per_family < 0:
        connection["errors"].append("--max-candidate-tables-per-family must be non-negative")
        _write_json(out / "connection_report.json", connection)
        return 2

    if not live_etabs:
        connection["errors"].append("--live-etabs is required.")
        _write_json(out / "connection_report.json", connection)
        return 2

    conn = ETABSConnection()
    ok, message = conn.connect()
    connection["live_etabs_connected"] = bool(ok)
    connection["etabs_model_available"] = bool(ok)
    if not ok:
        connection["errors"].append(message)
        _write_json(out / "connection_report.json", connection)
        return 1

    sap = conn.get_sap()
    database_tables = sap.DatabaseTables

    display_selection_failed = False
    if preferred_output_case:
        connection["display_selection_attempted"] = True
        selection = select_output_for_display(database_tables, preferred_output_case)
        connection["display_selection_status"] = "SUCCESS" if selection.get("display_selection_success") else "FAILED"
        connection["display_selection_diagnostics"] = selection
        if not selection.get("display_selection_success"):
            display_selection_failed = True

    try:
        table_names = get_available_tables(sap)
    except Exception as exc:  # pragma: no cover - live COM failure path
        connection["errors"].append(f"GetAvailableTables failed: {exc}")
        _write_json(out / "connection_report.json", connection)
        return 1

    matches = match_target_tables(
        table_names,
        families,
        max_candidate_tables_per_family=max_candidate_tables_per_family,
    )
    for match in matches:
        match["probe_profile"] = probe_profile

    headers, samples, raw_shapes = _fetch_attempted_tables(database_tables, matches, max_sample_rows=max_sample_rows)
    readiness = [
        classify_source_readiness(
            family,
            match,
            headers,
            samples,
            display_selection_failed=display_selection_failed,
        )
        for family, match in zip(families, matches)
    ]
    recommendation = build_scope_recommendation(readiness, probe_profile)
    summary = build_probe_summary(
        probe_profile=probe_profile,
        live_etabs_connected=True,
        available_table_count=len(table_names),
        readiness=readiness,
        recommendation_markdown=recommendation,
    )

    _write_json(out / "connection_report.json", connection)
    _write_json(out / "available_tables.json", {"available_table_count": len(table_names), "tables": _available_table_rows(table_names)})
    _write_json(out / "target_table_matches.json", matches)
    _write_json(out / "target_table_headers.json", headers)
    _write_json(out / "target_table_sample_rows.json", samples)
    _write_json(out / "raw_return_shape_report.json", raw_shapes)
    _write_json(out / "source_readiness_observations.json", readiness)
    _write_text(out / "c13_2_scope_recommendation.md", recommendation)
    _write_json(out / "probe_summary.json", summary)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C13.2-P0 tier/profile-aware ETABS source probe")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--live-etabs", action="store_true")
    parser.add_argument("--probe-profile", default="current_product", choices=list(PROBE_PROFILES.keys()))
    parser.add_argument("--preferred-output-case", default=None)
    parser.add_argument("--max-sample-rows", type=int, default=20)
    parser.add_argument("--max-candidate-tables-per-family", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_live_probe(
        out=args.out,
        probe_profile=str(args.probe_profile),
        live_etabs=bool(args.live_etabs),
        preferred_output_case=args.preferred_output_case,
        max_sample_rows=int(args.max_sample_rows),
        max_candidate_tables_per_family=int(args.max_candidate_tables_per_family),
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
