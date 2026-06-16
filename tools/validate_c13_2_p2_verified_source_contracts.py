#!/usr/bin/env python
"""Validate C13.2-P2 verified live source contract expansion.

This validator is intentionally contract-only. It must not import FeatureResolver,
CheckEngine, ETABS runtime providers, report renderers, or product check code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover - PyYAML is expected in repo tests
    raise SystemExit(f"PyYAML is required for contract validation: {exc}")

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"
SCHEMA_DIR = ROOT / "tbdy_engine" / "schemas"

STATUS_VALUES = {
    "VERIFIED_LIVE",
    "NEEDS_LIVE_PROBE",
    "SEMANTIC_REVIEW",
    "EXCEL_INVENTORY_ONLY",
    "PLANNED",
}
ALLOWED_VERIFIED_LIVE = {
    "frame_assignments_summary",
    "concrete_rectangular_frame_sections",
    "modal_participating_mass",
    "story_drifts",
    "story_max_over_avg_drifts",
    "base_reactions",
    "material_list_by_story",
    "concrete_material_properties",
    "rebar_material_properties",
    "frame_section_assignments",
    "frame_section_material_assignments",
    "area_assignments_summary",
    "wall_section_properties",
    "pier_assignments",
    # C13.2-P4 promoted blocked sources and live-proved supporting context.
    "material_properties",
    "story_definitions",
    "pier_section_properties",
    "wall_bays",
    "wall_object_connectivity",
}
FORBIDDEN_FEATURE_TERMS = ("pass", "fail", "ok", "verdict", "check_result")

LEGACY_COMPATIBILITY_VERIFIED_ALIASES = {
    "frame_assignments": "frame_assignments_summary",
    "frame_section_properties": "concrete_rectangular_frame_sections",
    "modal_results": "modal_participating_mass",
    "material_concrete_data": "concrete_material_properties",
    "material_rebar_data": "rebar_material_properties",
    "wall_section_data": "wall_section_properties",
}

ETABS_TABLE_NAME_FRAGMENTS = (
    "Frame Assignments - Summary",
    "Frame Section Property Definitions",
    "Modal Participating Mass Ratios",
    "Story Drifts",
    "Story Max Over Avg Drifts",
    "Base Reactions",
    "Material List by Story",
    "Frame Assignments - Section Properties",
    "Area Assignments - Summary",
)


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing required contract file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing required schema file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON schema root must be an object: {path}")
    return data


def validate_with_jsonschema(instance: Dict[str, Any], schema: Dict[str, Any], label: str) -> List[str]:
    try:
        import jsonschema  # type: ignore
    except Exception:
        # Fallback keeps this tool dependency-light; semantic validation below is the real gate.
        return []
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{label}: {err.message}" for err in sorted(validator.iter_errors(instance), key=lambda e: e.path)]


def require(condition: bool, message: str, errors: List[str]) -> None:
    if not condition:
        errors.append(message)


def validate_table_registry(data: Dict[str, Any], errors: List[str]) -> Dict[str, Any]:
    tables = data.get("tables") or {}
    require(isinstance(tables, dict), "table_registry.tables must be a mapping", errors)
    if not isinstance(tables, dict):
        return {}
    for key, entry in tables.items():
        require(entry.get("provider") == "etabs", f"{key}: provider must be etabs", errors)
        status = entry.get("evidence_status")
        require(status in STATUS_VALUES, f"{key}: invalid evidence_status {status!r}", errors)
        require(entry.get("check_unlock_allowed") is False, f"{key}: check_unlock_allowed must be false", errors)
        require(isinstance(entry.get("required_columns"), dict), f"{key}: required_columns must be a mapping", errors)
        require(isinstance(entry.get("optional_columns"), dict), f"{key}: optional_columns must be a mapping", errors)
        if status == "VERIFIED_LIVE":
            is_allowed_verified = key in ALLOWED_VERIFIED_LIVE
            alias_target = LEGACY_COMPATIBILITY_VERIFIED_ALIASES.get(key)
            is_legacy_alias = alias_target is not None and entry.get("compatibility_alias_for") == alias_target
            require(
                is_allowed_verified or is_legacy_alias,
                f"{key}: VERIFIED_LIVE is not in the C13.2-P1 allowed promotion list or legacy compatibility alias list",
                errors,
            )
            verified_by = entry.get("verified_by") or {}
            require(verified_by.get("live_probe") is True, f"{key}: VERIFIED_LIVE requires verified_by.live_probe true", errors)
            if is_legacy_alias:
                require(
                    entry.get("check_unlock_allowed") is False,
                    f"{key}: legacy compatibility alias must keep check_unlock_allowed false",
                    errors,
                )
    return tables


def validate_semantic_guardrails(tables: Dict[str, Any], errors: List[str]) -> None:
    material_properties = tables.get("material_properties") or {}
    # C13.2-P4 may promote material_properties after targeted live proof.
    material_live_name = str(material_properties.get("live_table_name", ""))
    forbidden_material_tables = ("Material List by Story", "Material List by Object Type", "Material List by Section Prop")
    for forbidden in forbidden_material_tables:
        require(forbidden not in material_live_name, f"material_properties must not use {forbidden}", errors)
    must_not_use = set(material_properties.get("must_not_use") or [])
    require(set(forbidden_material_tables).issubset(must_not_use), "material_properties must explicitly forbid Material List tables", errors)

    frame_material = tables.get("frame_section_material_assignments") or {}
    require(
        frame_material.get("live_table_name") == "Frame Section Property Definitions - Summary",
        "frame_section_material_assignments must use Frame Section Property Definitions - Summary",
        errors,
    )
    require(
        frame_material.get("live_table_name") != "Frame Assignments - Section Properties",
        "frame_section_material_assignments must not use Frame Assignments - Section Properties",
        errors,
    )
    require(
        "Material" in (frame_material.get("required_columns") or {}),
        "frame_section_material_assignments requires Material column",
        errors,
    )

    frame_assignment = tables.get("frame_section_assignments") or {}
    require(
        frame_assignment.get("live_table_name") == "Frame Assignments - Section Properties",
        "frame_section_assignments must use Frame Assignments - Section Properties",
        errors,
    )
    require(
        frame_assignment.get("source_role") == "section_assignment_context_only",
        "frame_section_assignments must be section_assignment_context_only",
        errors,
    )
    require(
        "Material" not in (frame_assignment.get("required_columns") or {}),
        "frame_section_assignments must not claim material mapping",
        errors,
    )

    # C13.2-P4 may promote story_definitions and pier_section_properties after targeted live proof.
    require((tables.get("pier_forces") or {}).get("evidence_status") == "SEMANTIC_REVIEW", "pier_forces must remain SEMANTIC_REVIEW", errors)


def validate_feature_sources(data: Dict[str, Any], tables: Dict[str, Any], errors: List[str], known_feature_ids: set[str] | None = None) -> int:
    sources = data.get("sources") or []
    require(isinstance(sources, list), "etabs_feature_source_contract.sources must be a list", errors)
    if not isinstance(sources, list):
        return 0
    for source in sources:
        feature_id = str(source.get("feature_id", ""))
        if known_feature_ids is not None:
            require(feature_id in known_feature_ids, f"feature source {feature_id}: missing from feature_catalog", errors)
        lower_id = feature_id.lower()
        for term in FORBIDDEN_FEATURE_TERMS:
            require(term not in lower_id, f"feature_id {feature_id!r} contains forbidden result/check term {term!r}", errors)
        table_key = source.get("table_registry_key")
        require(table_key in tables, f"feature source {feature_id}: table_registry_key {table_key!r} not found", errors)
        require(source.get("check_unlock_allowed") is False, f"feature source {feature_id}: check_unlock_allowed must be false", errors)
        for required_field in ("source_type", "source_owner", "row_selection_rule", "evidence_required", "display_selection_required"):
            require(required_field in source, f"feature source {feature_id}: missing legacy field {required_field}", errors)
        require(source.get("source_type") in {"display_table", "direct_api"}, f"feature source {feature_id}: source_type must be display_table or direct_api", errors)
        require(source.get("source_owner") == "ETABS", f"feature source {feature_id}: source_owner must be ETABS", errors)
        require(source.get("evidence_required") is True, f"feature source {feature_id}: evidence_required must be true", errors)
    return len(sources)


def validate_family_map(data: Dict[str, Any], tables: Dict[str, Any], errors: List[str]) -> None:
    families = data.get("feature_families") or {}
    require(isinstance(families, dict), "feature_family_map.feature_families must be a mapping", errors)
    if not isinstance(families, dict):
        return
    for family_id, family in families.items():
        require(family.get("check_unlock_allowed") is False, f"feature family {family_id}: check_unlock_allowed must be false", errors)
        for table_key in family.get("source_tables") or []:
            require(table_key in tables, f"feature family {family_id}: source table {table_key!r} missing from registry", errors)


def validate_report_contract(data: Dict[str, Any], tables: Dict[str, Any], errors: List[str]) -> None:
    report_tables = data.get("report_tables") or {}
    require(isinstance(report_tables, dict), "product_report_table_contract.report_tables must be a mapping", errors)
    if not isinstance(report_tables, dict):
        return
    for report_id, report in report_tables.items():
        require(report.get("check_unlock_allowed") is False, f"report table {report_id}: check_unlock_allowed must be false", errors)
        for field in ("verified_sources", "blocked_sources", "semantic_review_sources"):
            for table_key in report.get(field) or []:
                require(table_key in tables, f"report table {report_id}: {field} source {table_key!r} missing from registry", errors)


def validate_readiness_policy(data: Dict[str, Any], errors: List[str]) -> None:
    statuses = data.get("statuses") or {}
    for required in ["VERIFIED_LIVE", "NEEDS_LIVE_PROBE", "SEMANTIC_REVIEW", "EXCEL_INVENTORY_ONLY", "PLANNED", "OUT_OF_SCOPE", "UNSUPPORTED_SECTION_TYPE"]:
        require(required in statuses, f"readiness_status_policy missing status {required}", errors)
    verified = statuses.get("VERIFIED_LIVE") or {}
    require(verified.get("may_unlock_engineering_check") is False, "VERIFIED_LIVE must not unlock engineering checks in C13.2-P2", errors)


def validate_check_catalog_no_table_names(errors: List[str]) -> None:
    check_catalog = CATALOG_DIR / "check_catalog.yaml"
    if not check_catalog.exists():
        return
    text = check_catalog.read_text(encoding="utf-8")
    for fragment in ETABS_TABLE_NAME_FRAGMENTS:
        require(fragment not in text, f"check_catalog must not reference ETABS table name {fragment!r}", errors)



def validate_legacy_constitution_specific_source_contract_rules(source_contract: dict[str, Any], errors: list[str]) -> None:
    by_id = {row.get("feature_id"): row for row in source_contract.get("sources", [])}
    for feature_id in ["story_drift_value", "story_drift_max_mm", "story_drift_output_case", "story_drift_direction"]:
        row = by_id.get(feature_id) or {}
        require(row.get("canonical_table_key") == "story_drifts", f"{feature_id}: must use story_drifts", errors)
        require(row.get("display_selection_required") is True, f"{feature_id}: display selection required", errors)
        require(row.get("preferred_output_case_default") == "Crack_SeisY_UpSoil", f"{feature_id}: preferred output case default missing", errors)
    for feature_id in ["base_reaction_fx", "base_reaction_fy", "base_reaction_x_kN", "base_reaction_y_kN"]:
        row = by_id.get(feature_id) or {}
        require(row.get("canonical_table_key") == "base_reactions", f"{feature_id}: must use base_reactions", errors)
        identity = row.get("identity_requirements") or {}
        require(identity.get("requires_story") is False, f"{feature_id}: must not require story identity", errors)
        require(identity.get("requires_component_id") is False, f"{feature_id}: must not require component identity", errors)
    for feature_id in ["modal_sum_ux", "modal_sum_uy"]:
        row = by_id.get(feature_id) or {}
        require(row.get("aggregation") == "max_cumulative", f"{feature_id}: must use max_cumulative", errors)
        require("fixed_mode_10_only" in set(row.get("forbidden_source") or []), f"{feature_id}: must forbid fixed_mode_10_only", errors)
    for feature_id in ["beam_width_mm", "beam_depth_mm", "beam_length_mm"]:
        row = by_id.get(feature_id) or {}
        require(row.get("source_type") == "direct_api", f"{feature_id}: must preserve direct_api legacy source contract", errors)
        require("section_name_inference" in set(row.get("forbidden_source") or []), f"{feature_id}: must forbid section_name_inference", errors)

def main() -> int:
    errors: List[str] = []
    schema_errors: List[str] = []

    table_registry = load_yaml(CATALOG_DIR / "table_registry.yaml")
    feature_sources = load_yaml(CATALOG_DIR / "etabs_feature_source_contract.yaml")
    family_map = load_yaml(CATALOG_DIR / "feature_family_map.yaml")
    readiness = load_yaml(CATALOG_DIR / "readiness_status_policy.yaml")
    report_contract = load_yaml(CATALOG_DIR / "product_report_table_contract.yaml")

    schema_pairs = [
        ("table_registry", table_registry, "table_registry.schema.json"),
        ("etabs_feature_source_contract", feature_sources, "etabs_feature_source_contract.schema.json"),
        ("feature_family_map", family_map, "feature_family_map.schema.json"),
        ("readiness_status_policy", readiness, "readiness_status_policy.schema.json"),
        ("product_report_table_contract", report_contract, "product_report_table_contract.schema.json"),
    ]
    for label, instance, schema_name in schema_pairs:
        schema_errors.extend(validate_with_jsonschema(instance, load_json(SCHEMA_DIR / schema_name), label))

    tables = validate_table_registry(table_registry, errors)
    validate_semantic_guardrails(tables, errors)
    feature_catalog_path = CATALOG_DIR / 'feature_catalog.yaml'
    known_feature_ids = None
    if feature_catalog_path.exists():
        feature_catalog = load_yaml(feature_catalog_path)
        features = feature_catalog.get('features') or {}
        if isinstance(features, dict):
            known_feature_ids = set(features.keys())
    feature_source_count = validate_feature_sources(feature_sources, tables, errors, known_feature_ids)
    validate_family_map(family_map, tables, errors)
    validate_readiness_policy(readiness, errors)
    validate_report_contract(report_contract, tables, errors)
    validate_check_catalog_no_table_names(errors)

    all_errors = schema_errors + errors
    verified_live_count = sum(1 for entry in tables.values() if entry.get("evidence_status") == "VERIFIED_LIVE")
    compatibility_alias_count = sum(1 for entry in tables.values() if entry.get("compatibility_alias_for"))
    promoted_verified_live_count = sum(
        1
        for key, entry in tables.items()
        if entry.get("evidence_status") == "VERIFIED_LIVE" and not entry.get("compatibility_alias_for")
    )
    needs_live_probe_count = sum(1 for entry in tables.values() if entry.get("evidence_status") == "NEEDS_LIVE_PROBE")
    semantic_review_count = sum(1 for entry in tables.values() if entry.get("evidence_status") == "SEMANTIC_REVIEW")
    summary = {
        "table_registry_entries": len(tables),
        "verified_live_entries": verified_live_count,
        "promoted_verified_live_entries": promoted_verified_live_count,
        "legacy_compatibility_alias_entries": compatibility_alias_count,
        "needs_live_probe_entries": needs_live_probe_count,
        "semantic_review_entries": semantic_review_count,
        "feature_source_entries": feature_source_count,
        "cross_reference_errors": sum(1 for e in all_errors if "missing" in e or "not found" in e),
        "semantic_guardrail_errors": sum(1 for e in all_errors if "material" in e or "frame_section" in e or "pier" in e or "story_definitions" in e),
        "safe_to_implement_checks_now": False,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if all_errors:
        print("\nValidation errors:", file=sys.stderr)
        for err in all_errors:
            print(f"- {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
