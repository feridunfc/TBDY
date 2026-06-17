"""C13.4-P0 live semantic source review utilities.

Diagnostic-only classification for already-known ETABS display-table candidates.
No checks, formulas, CheckEngine calls, or source promotion are performed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from typing import Any, Iterable, Mapping, Sequence

SPRINT = "C13.4-P0"
SEMANTIC_REVIEW_CONTRACT_VERSION = "c13.4-p0.semantic_source_review.v1"

FORBIDDEN_ENGINEERING_VERDICT_TERMS = (
    "PASS",
    "FAIL",
    "CHECK_OK",
    "CHECK_FAIL",
    "adequate",
    "inadequate",
    "complies",
    "non-compliant",
    "TBDY compliant",
    "TS500 compliant",
    "utilization ratio",
    "capacity ratio",
)

SELF_SCAN_REPORT_KEYS = {
    "forbidden_verdict_scan_report.json",
    "semantic_source_review_summary.json",
}
SELF_SCAN_PAYLOAD_KEYS = {
    "forbidden_terms_found",
    "raw_source_forbidden_like_terms",
    "raw_source_terms_are_not_generated_verdicts",
}
STATIC_FORBIDDEN_DEFINITION_KEYS = {
    "FORBIDDEN_ENGINEERING_VERDICT_TERMS",
    "forbidden_engineering_verdict_terms",
    "forbidden_verdict_terms",
    "forbidden_terms",
}
RAW_SOURCE_PAYLOAD_KEYS = {
    "sample_rows_limited",
    "sample_rows",
    "source_rows",
    "raw_rows",
    "raw_value",
    "columns",
}
INTERNAL_DIAGNOSTIC_PAYLOAD_KEYS = {
    "fetch_diagnostics",
    "parser_debug",
    "parser_diagnostics",
    "selected_signature",
    "selected_signature_reason",
    "signature_attempts",
    "fetch_debug",
    "internal_diagnostics",
}

TARGET_FAMILIES = (
    "base_reactions",
    "story_drifts",
    "story_max_over_avg_drifts",
    "pier_forces",
    "frame_forces",
    "design_outputs",
    "rebar_outputs",
    "combo_semantics",
)

CANDIDATE_TABLES: dict[str, tuple[str, ...]] = {
    "base_reactions": ("Base Reactions",),
    "story_drifts": ("Story Drifts",),
    "story_max_over_avg_drifts": ("Story Max Over Avg Drifts",),
    "pier_forces": ("Pier Forces",),
    "frame_forces": ("Element Forces - Beams",),
    "design_outputs": (
        "Concrete Beam Design Summary",
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Column Design Summary",
        "Concrete Column Design Summary - TS 500-2000(R2018)",
        "Shear Wall/Pier Design Summary",
        "Shear Wall Pier Design Summary",
        "Shear Wall Pier Design Summary - TS 500-2000(R2018)",
    ),
    "rebar_outputs": (
        "Concrete Beam Design Summary",
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Column Design Summary",
        "Concrete Column Design Summary - TS 500-2000(R2018)",
    ),
    "combo_semantics": (
        "Base Reactions",
        "Story Drifts",
        "Story Max Over Avg Drifts",
        "Element Forces - Beams",
        "Pier Forces",
        "Concrete Beam Design Summary",
        "Concrete Column Design Summary",
    ),
}

COLUMN_GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    "combo_columns_detected": ("Combo", "LoadCombo", "Load Combo", "DesignCombo", "Design Combo"),
    "case_combo_columns_detected": ("OutputCase", "Output Case", "Case", "LoadCase", "Load Case"),
    "station_or_location_columns_detected": ("Station", "Location", "StepNum", "Step Number", "StepNumber"),
    "direction_columns_detected": ("Direction", "Dir", "UX", "UY", "X", "Y"),
    "object_identity_columns_detected": ("Story", "Pier", "Frame", "UniqueName", "Unique Name", "Element", "Label", "Beam", "Column"),
    "force_component_columns_detected": ("P", "FX", "FY", "FZ", "V2", "V3", "T", "M2", "M3", "MX", "MY", "MZ"),
    "design_component_columns_detected": ("PMMRatio", "AsTop", "AsBot", "AsShear", "VRebar", "Rebar", "Required", "Provided"),
    "rebar_role_columns_detected": ("Rebar", "Longitudinal", "Transverse", "Top", "Bottom", "Left", "Right", "Major", "Minor", "AsTop", "AsBot", "VRebar", "Area"),
    "unit_columns_detected": ("Unit", "Units", "LengthUnit", "ForceUnit"),
}

EXPECTED_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "base_reactions": ("OutputCase", "FX", "FY"),
    "story_drifts": ("Story", "OutputCase", "Direction", "Drift"),
    "story_max_over_avg_drifts": ("Story", "OutputCase", "Direction", "MaxDrift", "AvgDrift", "Ratio"),
    "pier_forces": ("Story", "Pier", "OutputCase", "P", "V2", "V3", "M2", "M3"),
    "frame_forces": ("Story", "Frame", "UniqueName", "Station", "OutputCase", "P", "V2", "V3", "M2", "M3"),
    "design_outputs": ("Story", "Frame", "Label", "Station", "Combo", "AsTop", "AsBot", "PMMRatio"),
    "rebar_outputs": ("Rebar", "AsTop", "AsBot", "AsShear", "VRebar", "Required", "Provided", "Area"),
    "combo_semantics": ("OutputCase", "Case", "Combo", "StepType", "StepNum", "Station", "Story"),
}


def _norm(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _detected(columns: Sequence[str], aliases: Iterable[str]) -> list[str]:
    by_norm = {_norm(column): column for column in columns}
    found: list[str] = []
    for alias in aliases:
        column = by_norm.get(_norm(alias))
        if column and column not in found:
            found.append(column)
    return sorted(found)


def _root_guardrails() -> dict[str, Any]:
    return {
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "diagnostic_only": True,
        "check_engine_invoked": False,
        "engineering_verdicts_emitted": False,
        "check_results_emitted": False,
        "excel_production_input_used": False,
        "feature_values_faked": False,
    }


def _is_static_forbidden_definition(value: Any) -> bool:
    if not isinstance(value, (list, tuple, set)):
        return False
    return set(str(item) for item in value) == set(FORBIDDEN_ENGINEERING_VERDICT_TERMS)


def _path_text(path: Sequence[Any]) -> str:
    return ".".join(str(item) for item in path)


def _hit_records(text: str, path: Sequence[Any]) -> list[dict[str, Any]]:
    lowered = text.casefold()
    hits: list[dict[str, Any]] = []
    for term in FORBIDDEN_ENGINEERING_VERDICT_TERMS:
        count = lowered.count(term.casefold())
        if count:
            preview = text if len(text) <= 120 else text[:117] + "..."
            hits.append({"term": term, "count": count, "path": _path_text(path), "preview": preview})
    return hits


def _scan_generated_and_raw(value: Any, *, path: tuple[Any, ...] = (), raw_source_context: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(value, Mapping):
        generated_hits: list[dict[str, Any]] = []
        raw_hits: list[dict[str, Any]] = []
        for key, item in value.items():
            key_text = str(key)
            if (
                key_text in SELF_SCAN_REPORT_KEYS
                or key_text in SELF_SCAN_PAYLOAD_KEYS
                or key_text in STATIC_FORBIDDEN_DEFINITION_KEYS
                or key_text in INTERNAL_DIAGNOSTIC_PAYLOAD_KEYS
            ):
                continue
            item_raw_context = raw_source_context or key_text in RAW_SOURCE_PAYLOAD_KEYS
            child_generated, child_raw = _scan_generated_and_raw(item, path=(*path, key_text), raw_source_context=item_raw_context)
            generated_hits.extend(child_generated)
            raw_hits.extend(child_raw)
        return generated_hits, raw_hits
    if isinstance(value, (list, tuple, set)):
        if _is_static_forbidden_definition(value):
            return [], []
        generated_hits = []
        raw_hits = []
        for index, item in enumerate(value):
            child_generated, child_raw = _scan_generated_and_raw(item, path=(*path, index), raw_source_context=raw_source_context)
            generated_hits.extend(child_generated)
            raw_hits.extend(child_raw)
        return generated_hits, raw_hits
    if isinstance(value, str):
        hits = _hit_records(value, path)
        return ([], hits) if raw_source_context else (hits, [])
    return [], []


def scan_semantic_outputs_for_forbidden_verdicts(obj_or_text: Any) -> dict[str, Any]:
    """Scan generated semantic-review output without self-scanning scanner artifacts.

    ``forbidden_terms_found`` means generated engineering-verdict-like text emitted
    by semantic review code. Raw ETABS sample rows/column values are reported
    separately because they are source evidence, not generated verdicts.
    """
    if isinstance(obj_or_text, str):
        generated_hits, raw_hits = _hit_records(obj_or_text, ("<text>",)), []
    else:
        generated_hits, raw_hits = _scan_generated_and_raw(obj_or_text)
    return {
        "sprint": SPRINT,
        "forbidden_terms_found": generated_hits,
        "raw_source_forbidden_like_terms": raw_hits,
        "raw_source_terms_are_not_generated_verdicts": True,
        **_root_guardrails(),
        "engineering_verdicts_emitted": bool(generated_hits),
    }


def classify_semantic_source_table(
    *,
    source_family: str,
    table_name: str,
    fetch_status: str,
    rows: Sequence[Mapping[str, Any]] | None = None,
    columns: Sequence[str] | None = None,
    notes: Sequence[str] | None = None,
) -> dict[str, Any]:
    rows = list(rows or [])
    columns = list(columns or (list(rows[0].keys()) if rows else []))
    expected = EXPECTED_SEMANTIC_ALIASES.get(source_family, ())
    semantic_columns = _detected(columns, expected)
    missing = sorted({alias for alias in expected if _norm(alias) not in {_norm(column) for column in semantic_columns}})
    groups = {name: _detected(columns, aliases) for name, aliases in COLUMN_GROUP_ALIASES.items()}
    blockers: list[str] = []
    status = "SEMANTIC_REVIEW_INCONCLUSIVE"
    if fetch_status != "FETCHED":
        status = "SOURCE_TABLE_UNAVAILABLE"
        blockers.append("candidate table was not fetched by the live display-table reader")
    elif not rows:
        status = "SOURCE_ROWS_EMPTY"
        blockers.append("candidate table returned no bounded sample rows")
    elif source_family == "design_outputs" and groups["design_component_columns_detected"]:
        status = "BLOCKED_DESIGN_OUTPUT_ROLE_POLICY"
        blockers.append("design output role policy is required before any future check use")
    elif source_family == "rebar_outputs" and groups["rebar_role_columns_detected"]:
        status = "BLOCKED_REBAR_ROLE_POLICY"
        blockers.append("rebar role policy is required before any future check use")
    elif groups["combo_columns_detected"] or groups["case_combo_columns_detected"]:
        status = "BLOCKED_COMBO_GOVERNING_POLICY"
        blockers.append("combo and future row-governing policies are required before check use")
    elif semantic_columns:
        status = "SEMANTICALLY_REVIEWED_SOURCE_CANDIDATE"
    else:
        blockers.append("required semantic columns were not detected in bounded sample")
    return {
        "source_family": source_family,
        "table_name": table_name,
        "fetch_status": fetch_status,
        "row_count": len(rows),
        "columns": sorted(columns),
        "sample_rows_limited": [dict(row) for row in rows],
        "semantic_columns_detected": semantic_columns,
        "missing_semantic_columns": missing,
        **groups,
        "semantic_review_status": status,
        "blockers": blockers,
        "notes": list(notes or []),
        "safe_to_use_for_check": False,
        "check_unlock_allowed": False,
        "diagnostic_only": True,
    }


def build_combo_semantic_review(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for item in classifications:
        statuses: list[str] = []
        if item.get("combo_columns_detected"):
            statuses.extend(["COMBO_COLUMNS_PRESENT", "LOAD_COMBO_PRESENT", "GOVERNING_POLICY_REQUIRED"])
        if item.get("case_combo_columns_detected") and not item.get("combo_columns_detected"):
            statuses.append("LOAD_CASE_ONLY")
        if item.get("station_or_location_columns_detected") or item.get("semantic_review_status") == "BLOCKED_COMBO_GOVERNING_POLICY":
            statuses.append("ENVELOPE_POLICY_REQUIRED")
        if not statuses:
            statuses.append("INCONCLUSIVE")
        entries.append({
            "source_family": item.get("source_family"),
            "table_name": item.get("table_name"),
            "combo_review_statuses": sorted(set(statuses)),
            "load_case_columns": item.get("case_combo_columns_detected", []),
            "load_combo_columns": item.get("combo_columns_detected", []),
            "station_or_location_columns": item.get("station_or_location_columns_detected", []),
            "story_columns": [c for c in item.get("object_identity_columns_detected", []) if _norm(c) == "story"],
            "object_identity_columns": item.get("object_identity_columns_detected", []),
            "direction_columns": item.get("direction_columns_detected", []),
            "future_governing_row_policy_needed": any(s in statuses for s in ("GOVERNING_POLICY_REQUIRED", "ENVELOPE_POLICY_REQUIRED")),
        })
    return {"sprint": SPRINT, "entries": entries, **_root_guardrails()}


def _filtered(classifications: Sequence[Mapping[str, Any]], families: set[str]) -> list[Mapping[str, Any]]:
    return [item for item in classifications if str(item.get("source_family")) in families]


def build_force_result_semantic_review(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = _filtered(classifications, {"base_reactions", "pier_forces", "frame_forces"})
    return {"sprint": SPRINT, "reviewed_tables": items, "table_count": len(items), **_root_guardrails()}


def build_design_output_semantic_review(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = _filtered(classifications, {"design_outputs"})
    return {"sprint": SPRINT, "reviewed_tables": items, "table_count": len(items), **_root_guardrails()}


def build_rebar_role_semantic_review(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = _filtered(classifications, {"rebar_outputs"})
    return {"sprint": SPRINT, "reviewed_tables": items, "table_count": len(items), **_root_guardrails()}


def build_drift_story_semantic_review(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = _filtered(classifications, {"story_drifts", "story_max_over_avg_drifts"})
    return {"sprint": SPRINT, "reviewed_tables": items, "table_count": len(items), **_root_guardrails()}


def build_semantic_source_review_report(
    *,
    classifications: Sequence[Mapping[str, Any]],
    generated_at: str | None = None,
    live_etabs_requested: bool = False,
    live_etabs_connected: bool = False,
    etabs_version: str | None = None,
    model_path: str | None = None,
    target_family: str = "all",
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    classifications = list(classifications)
    status_counts = Counter(str(item.get("semantic_review_status")) for item in classifications)
    scan = scan_semantic_outputs_for_forbidden_verdicts(classifications)
    summary = {
        "sprint": SPRINT,
        "generated_at": generated_at,
        "live_etabs_requested": live_etabs_requested,
        "live_etabs_connected": live_etabs_connected,
        "etabs_version": etabs_version,
        "model_path": model_path,
        "target_family": target_family,
        "reviewed_source_families": sorted({str(item.get("source_family")) for item in classifications}),
        "reviewed_table_count": len(classifications),
        "fetched_table_count": sum(1 for item in classifications if item.get("fetch_status") == "FETCHED"),
        "table_with_rows_count": sum(1 for item in classifications if int(item.get("row_count", 0) or 0) > 0),
        "semantic_review_status_counts": dict(sorted(status_counts.items())),
        "combo_governing_policy_required_count": sum(1 for item in classifications if item.get("semantic_review_status") == "BLOCKED_COMBO_GOVERNING_POLICY"),
        "design_role_policy_required_count": sum(1 for item in classifications if item.get("semantic_review_status") == "BLOCKED_DESIGN_OUTPUT_ROLE_POLICY"),
        "rebar_role_policy_required_count": sum(1 for item in classifications if item.get("semantic_review_status") == "BLOCKED_REBAR_ROLE_POLICY"),
        "source_tables_unavailable_count": sum(1 for item in classifications if item.get("semantic_review_status") == "SOURCE_TABLE_UNAVAILABLE"),
        "forbidden_terms_found": scan["forbidden_terms_found"],
        "raw_source_forbidden_like_terms": scan["raw_source_forbidden_like_terms"],
        "raw_source_terms_are_not_generated_verdicts": True,
        **_root_guardrails(),
        "engineering_verdicts_emitted": bool(scan["forbidden_terms_found"]),
    }
    return summary


def build_semantic_source_inventory_report(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"sprint": SPRINT, "source_tables": list(classifications), **_root_guardrails()}


def build_semantic_source_sample_rows(classifications: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "sprint": SPRINT,
        "tables": [
            {
                "source_family": item.get("source_family"),
                "table_name": item.get("table_name"),
                "row_count": item.get("row_count", 0),
                "sample_rows_limited": item.get("sample_rows_limited", []),
            }
            for item in classifications
        ],
        **_root_guardrails(),
    }


def candidate_tables_for_target(target_family: str) -> list[tuple[str, str]]:
    families = tuple(k for k in TARGET_FAMILIES if k != "combo_semantics") if target_family == "all" else (target_family,)
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for family in families:
        for table in CANDIDATE_TABLES.get(family, ()):
            pair = (family, table)
            if pair not in seen:
                pairs.append(pair)
                seen.add(pair)
    return pairs


__all__ = [
    "CANDIDATE_TABLES",
    "FORBIDDEN_ENGINEERING_VERDICT_TERMS",
    "SPRINT",
    "TARGET_FAMILIES",
    "build_combo_semantic_review",
    "build_design_output_semantic_review",
    "build_drift_story_semantic_review",
    "build_force_result_semantic_review",
    "build_rebar_role_semantic_review",
    "build_semantic_source_inventory_report",
    "build_semantic_source_review_report",
    "build_semantic_source_sample_rows",
    "candidate_tables_for_target",
    "classify_semantic_source_table",
    "scan_semantic_outputs_for_forbidden_verdicts",
]
