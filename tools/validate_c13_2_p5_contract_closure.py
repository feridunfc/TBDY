#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "tbdy_engine" / "catalogs" / "source_feature_readiness_matrix.yaml"
SCHEMA_PATH = ROOT / "tbdy_engine" / "schemas" / "source_feature_readiness_matrix.schema.json"
FEATURE_CATALOG_PATH = ROOT / "tbdy_engine" / "catalogs" / "feature_catalog.yaml"
TABLE_REGISTRY_PATH = ROOT / "tbdy_engine" / "catalogs" / "table_registry.yaml"
FEATURE_FAMILY_MAP_PATH = ROOT / "tbdy_engine" / "catalogs" / "feature_family_map.yaml"

APPROVED_STATUSES = {
    "READY_DIRECT_SOURCE",
    "READY_DERIVED_SOURCE",
    "READY_SUPPORTING_CONTEXT_ONLY",
    "BLOCKED_NEEDS_LIVE_PROBE",
    "BLOCKED_SEMANTIC_REVIEW",
    "BLOCKED_FEATURE_CONTRACT_MISSING",
    "OUT_OF_SCOPE_UNSUPPORTED",
    "LOCKED_CHECK_NOT_ALLOWED",
}
SPECIAL_SOURCE_FAMILIES = {"NONE", "OUT_OF_SCOPE"}

APPROVED_UNITS = {"kN", "kN.m", "m", "mm", "mm2", "MPa", "ratio", "percent", "unitless"}
UNIT_REQUIRED_ROW_FIELDS = {"quantity_kind", "source_unit_policy", "normalized_unit_policy", "default_report_unit"}
FORBIDDEN_PATHS = [
    "tbdy_engine/features/resolver/live_smoke.py",
    "tbdy_engine/checks/engine.py",
    "tools/render_product_report.py",
    "apps/",
    "runtime/",
    "archx/",
    "runner_v2/",
]


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def feature_ids() -> set[str]:
    catalog = load_yaml(FEATURE_CATALOG_PATH)
    features = catalog.get("features") or {}
    return set(features)


def source_family_statuses() -> dict[str, str]:
    tables = load_yaml(TABLE_REGISTRY_PATH).get("tables") or {}
    families = load_yaml(FEATURE_FAMILY_MAP_PATH).get("feature_families") or {}
    statuses: dict[str, str] = {key: str(value.get("evidence_status", "")) for key, value in tables.items()}
    for key, value in families.items():
        statuses.setdefault(key, str(value.get("evidence_status", "")))
    return statuses


def fail(errors: list[str]) -> None:
    print(json.dumps({"ok": False, "errors": errors}, indent=2))
    raise SystemExit(1)


def main() -> int:
    errors: list[str] = []
    if not MATRIX_PATH.exists():
        fail([f"missing matrix: {MATRIX_PATH.relative_to(ROOT)}"])
    matrix = load_yaml(MATRIX_PATH)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_errors = sorted(Draft202012Validator(schema).iter_errors(matrix), key=lambda e: list(e.path))
    for err in schema_errors:
        errors.append(f"schema {list(err.path)}: {err.message}")

    known_features = feature_ids()
    source_status = source_family_statuses()
    known_sources = set(source_status) | SPECIAL_SOURCE_FAMILIES
    rows = matrix.get("matrix") or []

    unit_policy = matrix.get("metadata", {}).get("unit_policy") or {}
    allowed_units = set(unit_policy.get("allowed_units") or [])
    for required_unit in ["kN", "m", "mm", "MPa", "ratio", "percent"]:
        if required_unit not in allowed_units:
            errors.append(f"unit_policy.allowed_units missing {required_unit!r}")
    default_report_units = unit_policy.get("default_report_units") or {}
    for key, expected in {
        "force": "kN",
        "moment": "kN.m",
        "global_length_elevation": "m",
        "section_dimensions": "mm",
        "deformation_displacement": "mm",
        "stress_material_strength": "MPa",
    }.items():
        if default_report_units.get(key) != expected:
            errors.append(f"unit_policy.default_report_units.{key} must be {expected!r}")
    drift_unit = str(default_report_units.get("drift", ""))
    if "ratio" not in drift_unit and "percent" not in drift_unit:
        errors.append("unit_policy.default_report_units.drift must explicitly mention ratio or percent")
    if unit_policy.get("source_contract_silent_conversion_allowed") is not False:
        errors.append("unit_policy.source_contract_silent_conversion_allowed must be false")
    if unit_policy.get("feature_resolver_behavior_changed") is not False:
        errors.append("unit_policy.feature_resolver_behavior_changed must be false")
    if unit_policy.get("check_engine_behavior_changed") is not False:
        errors.append("unit_policy.check_engine_behavior_changed must be false")
    if unit_policy.get("checks_implemented") is not False:
        errors.append("unit_policy.checks_implemented must be false")
    if unit_policy.get("safe_to_implement_checks_now") is not False:
        errors.append("unit_policy.safe_to_implement_checks_now must be false")

    for row in rows:
        row_id = row.get("row_id", "<unknown>")
        status = row.get("readiness_status")
        if status not in APPROVED_STATUSES:
            errors.append(f"{row_id}: unknown readiness status {status!r}")
        feature_id = row.get("feature_id")
        if feature_id not in (None, "NONE", "OUT_OF_SCOPE") and feature_id not in known_features:
            errors.append(f"{row_id}: invented or unknown feature_id {feature_id!r}")
        for family in row.get("source_families") or []:
            if family not in known_sources:
                errors.append(f"{row_id}: unknown source_family {family!r}")
        if row.get("check_unlock_allowed") is not False:
            errors.append(f"{row_id}: check_unlock_allowed must be false")
        if row.get("safe_to_implement_checks_now") is not False:
            errors.append(f"{row_id}: safe_to_implement_checks_now must be false")
        if row.get("excel_production_input") is not False:
            errors.append(f"{row_id}: excel_production_input must be false")
        missing_unit_fields = [field for field in UNIT_REQUIRED_ROW_FIELDS if not row.get(field)]
        if missing_unit_fields:
            errors.append(f"{row_id}: missing unit metadata fields {missing_unit_fields}")
        if row.get("default_report_unit") not in APPROVED_UNITS:
            errors.append(f"{row_id}: default_report_unit must be one of {sorted(APPROVED_UNITS)}, got {row.get('default_report_unit')!r}")
        if row.get("source_unit_policy") == row.get("default_report_unit"):
            errors.append(f"{row_id}: raw source unit policy must be separate from report display unit")
        if status in {"READY_DIRECT_SOURCE", "READY_DERIVED_SOURCE"} and not row.get("quantity_kind"):
            errors.append(f"{row_id}: numeric readiness rows must declare quantity_kind")
        if "SILENT" in str(row.get("normalized_unit_policy", "")).upper() and "NO_SILENT" not in str(row.get("normalized_unit_policy", "")).upper():
            errors.append(f"{row_id}: normalized unit policy must not allow silent conversion")
        if status == "READY_DIRECT_SOURCE":
            for family in row.get("source_families") or []:
                if family in SPECIAL_SOURCE_FAMILIES:
                    errors.append(f"{row_id}: READY_DIRECT_SOURCE cannot use {family}")
                elif source_status.get(family) != "VERIFIED_LIVE":
                    errors.append(f"{row_id}: READY_DIRECT_SOURCE requires VERIFIED_LIVE source family {family!r}, got {source_status.get(family)!r}")
        if status == "READY_DERIVED_SOURCE":
            derivation = row.get("derivation_policy") or {}
            for key in ["source_families", "input_fields", "output_feature", "semantic_guardrail"]:
                if key not in derivation and key != "semantic_guardrail":
                    errors.append(f"{row_id}: READY_DERIVED_SOURCE missing derivation_policy.{key}")
            if not row.get("semantic_guardrail"):
                errors.append(f"{row_id}: READY_DERIVED_SOURCE missing semantic_guardrail")
            for family in derivation.get("source_families", []):
                if source_status.get(family) != "VERIFIED_LIVE":
                    errors.append(f"{row_id}: READY_DERIVED_SOURCE requires VERIFIED_LIVE source family {family!r}")
        if status == "BLOCKED_SEMANTIC_REVIEW":
            for family in row.get("source_families") or []:
                if family not in SPECIAL_SOURCE_FAMILIES and source_status.get(family) == "SEMANTIC_REVIEW":
                    continue
            # The key invariant is negative: semantic review rows must not be ready.
        if status in {"READY_DIRECT_SOURCE", "READY_DERIVED_SOURCE"}:
            for family in row.get("source_families") or []:
                if family not in SPECIAL_SOURCE_FAMILIES and source_status.get(family) == "SEMANTIC_REVIEW":
                    errors.append(f"{row_id}: semantic review source {family!r} cannot be marked ready")

    text = "\n".join(
        (ROOT / p).read_text(encoding="utf-8", errors="ignore")
        for p in ["c13_2_p5_changed_files.txt"]
        if (ROOT / p).exists()
    )
    for forbidden in FORBIDDEN_PATHS:
        if forbidden in text:
            errors.append(f"forbidden runtime path modified: {forbidden}")

    safe = matrix.get("metadata", {}).get("safe_to_implement_checks_now") is False
    unlock = matrix.get("metadata", {}).get("check_unlock_allowed") is False
    if not safe:
        errors.append("metadata.safe_to_implement_checks_now must be false")
    if not unlock:
        errors.append("metadata.check_unlock_allowed must be false")

    summary = {
        "total_matrix_rows": len(rows),
        "ready_direct_count": sum(1 for r in rows if r.get("readiness_status") == "READY_DIRECT_SOURCE"),
        "ready_derived_count": sum(1 for r in rows if r.get("readiness_status") == "READY_DERIVED_SOURCE"),
        "supporting_context_count": sum(1 for r in rows if r.get("readiness_status") == "READY_SUPPORTING_CONTEXT_ONLY"),
        "blocked_needs_live_probe_count": sum(1 for r in rows if r.get("readiness_status") == "BLOCKED_NEEDS_LIVE_PROBE"),
        "blocked_semantic_review_count": sum(1 for r in rows if r.get("readiness_status") == "BLOCKED_SEMANTIC_REVIEW"),
        "locked_check_not_allowed_count": sum(1 for r in rows if r.get("readiness_status") == "LOCKED_CHECK_NOT_ALLOWED"),
        "cross_reference_errors": len(errors),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "unit_policy_closed": True,
        "allowed_units": sorted(allowed_units),
    }
    if errors:
        summary["errors"] = errors
        print(json.dumps(summary, indent=2))
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
