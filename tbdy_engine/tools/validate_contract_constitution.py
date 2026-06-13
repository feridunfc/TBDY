"""Validate TBDY Engine Contract Constitution v1.0 / C5.6 foundation.

Contract-only tool: no engine checks, no ETABS integration, no runtime/DAG import.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"

CATALOG_FILES = [
    "table_registry.yaml",
    "feature_catalog.yaml",
    "check_catalog.yaml",
    "load_combo_policy.yaml",
    "design_combo_matrix.yaml",
    "design_basis.yaml",
    "section_state_policy.yaml",
    "high_ductility_check_scope.yaml",
    "check_scope_alignment.yaml",
    "workspace_contract.yaml",
    "element_registry.yaml",
    "coverage_policy.yaml",
    "etabs_feature_source_contract.yaml",
]
EXAMPLE_SCHEMA_MAP = {
    "evidence.full.example.json": "evidence.schema.json",
    "evidence.partial.example.json": "evidence.schema.json",
    "coverage_matrix.example.json": "coverage_matrix.schema.json",
    "coverage_matrix.full.example.json": "coverage_matrix.schema.json",
    "coverage_matrix.blocked.example.json": "coverage_matrix.schema.json",
    "coverage_matrix.partial.example.json": "coverage_matrix.schema.json",
    "check_result.example.json": "check_result.schema.json",
    "feature_snapshot.example.json": "feature_snapshot.schema.json",
    "workspace_state.example.json": "workspace_state.schema.json",
    "element_registry.example.json": "element_registry.schema.json",
    "etabs_feature_source_contract.example.json": "etabs_feature_source_contract.schema.json",
}
REQUIRED_SCHEMA_FILES = [n.replace(".yaml", ".schema.json") for n in CATALOG_FILES] + [
    "evidence.schema.json",
    "coverage_matrix.schema.json",
    "check_result.schema.json",
    "feature_snapshot.schema.json",
    "workspace_state.schema.json",
]
FORBIDDEN_FEATURE_NAME_TERMS = ("ratio", "status", "pass", "fail", "ok")
FORBIDDEN_REBAR_TERMS = {"VERIFIED_PROVIDED_REBAR", "AS_BUILT_REBAR"}
REQUIRED_REBAR_ROLES = {
    "ETABS_REQUIRED_REBAR",
    "TBDY_MIN_REQUIRED_REBAR",
    "GOVERNING_REQUIRED_REBAR",
    "ENGINE_SELECTED_REBAR",
    "USER_PROVIDED_REBAR",
    "FINAL_DETAILING_REQUIRED",
}
EXPECTED_COMBO_FAMILIES = {
    "GRAV_SERVICE", "GRAV_STRENGTH", "DUCTILE_X", "DUCTILE_Y", "CAPACITY_X", "CAPACITY_Y",
    "DISP_X", "DISP_Y", "MODAL", "SOIL", "TEMP_POS", "TEMP_NEG", "NONE",
}
REINFORCEMENT_PURPOSE_HINTS = ("flexure", "shear", "capacity_design_shear", "pmm", "pier_design", "rebar", "reinforcement")


class ContractValidationError(AssertionError):
    """Raised when the contract constitution is malformed."""


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ContractValidationError(f"{path} must contain a YAML object")
    return data


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ContractValidationError(f"{path} must contain a JSON object")
    return data


def validate_jsonschema(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise ContractValidationError(f"Schema validation failed for {label}: {detail}")


def _schema_dir(catalog_dir: Path) -> Path:
    return catalog_dir / "schemas"


def _example_dir(catalog_dir: Path) -> Path:
    return catalog_dir / "examples"


def validate_files_exist(catalog_dir: Path) -> None:
    schema_dir = _schema_dir(catalog_dir)
    example_dir = _example_dir(catalog_dir)
    missing = [name for name in CATALOG_FILES if not (catalog_dir / name).exists()]
    missing += [name for name in REQUIRED_SCHEMA_FILES if not (schema_dir / name).exists()]
    missing += [name for name in EXAMPLE_SCHEMA_MAP if not (example_dir / name).exists()]
    if missing:
        raise FileNotFoundError("Missing contract files: " + ", ".join(sorted(set(missing))))


def validate_catalog_schemas(catalog_dir: Path, catalogs: dict[str, dict[str, Any]]) -> None:
    schema_dir = _schema_dir(catalog_dir)
    for catalog_name, data in catalogs.items():
        schema_name = catalog_name.replace(".yaml", ".schema.json")
        validate_jsonschema(data, load_json(schema_dir / schema_name), catalog_name)
        metadata = data.get("metadata", {})
        if metadata.get("version") != "1.0":
            raise ContractValidationError(f"{catalog_name} metadata.version must be 1.0")


def validate_examples(catalog_dir: Path, catalogs: dict[str, dict[str, Any]] | None = None) -> None:
    schema_dir = _schema_dir(catalog_dir)
    example_dir = _example_dir(catalog_dir)
    for example_name, schema_name in EXAMPLE_SCHEMA_MAP.items():
        example = load_json(example_dir / example_name)
        schema = load_json(schema_dir / schema_name)
        validate_jsonschema(example, schema, example_name)
        if schema_name == "evidence.schema.json":
            validate_evidence_semantics(example, example_name)
        if schema_name == "coverage_matrix.schema.json":
            validate_coverage_semantics(example, example_name)
        if schema_name == "check_result.schema.json":
            validate_check_result_semantics(example, example_name)
        if schema_name == "feature_snapshot.schema.json":
            validate_feature_snapshot_semantics(example, example_name)
        if schema_name == "workspace_state.schema.json" and catalogs is not None:
            validate_workspace_state_semantics(example, example_name, catalogs)


def combo_families_and_aliases(load_policy: dict[str, Any]) -> tuple[set[str], dict[str, list[str]]]:
    families = set((load_policy.get("combo_families") or {}).keys())
    aliases = {
        key: list(value.get("expands_to", []))
        for key, value in (load_policy.get("combo_family_aliases") or {}).items()
    }
    return families, aliases


def expand_combo_family(name: str, families: set[str], aliases: dict[str, list[str]]) -> list[str]:
    if name in families:
        return [name]
    if name in aliases:
        return aliases[name]
    return []


def validate_combo_policy(load_policy: dict[str, Any]) -> None:
    families, aliases = combo_families_and_aliases(load_policy)
    missing_expected = sorted(EXPECTED_COMBO_FAMILIES - families)
    if missing_expected:
        raise ContractValidationError("load_combo_policy missing canonical combo families: " + ", ".join(missing_expected))
    if load_policy.get("policy", {}).get("unknown_combo_behavior") != "diagnostic":
        raise ContractValidationError("unknown_combo_behavior must be diagnostic")
    for alias, expansion in aliases.items():
        unknown = [fam for fam in expansion if fam not in families]
        if unknown:
            raise ContractValidationError(f"combo alias {alias} expands to unknown family/families: {unknown}")
    for fam in ["DISP_X", "DISP_Y", "MODAL"]:
        row = load_policy.get("combo_families", {}).get(fam, {})
        if row.get("read_only") is not True or row.get("reinforcement_design_allowed") is not False:
            raise ContractValidationError(f"{fam} must be read_only and disallow reinforcement design")
    for alias in ["DISP_X_OR_Y"]:
        expansion = aliases.get(alias, [])
        if not expansion or any(load_policy["combo_families"][fam].get("reinforcement_design_allowed") for fam in expansion):
            raise ContractValidationError(f"{alias} must expand only to non-reinforcement displacement families")


def validate_feature_catalog(catalogs: dict[str, dict[str, Any]]) -> None:
    tables = set(catalogs["table_registry.yaml"].get("tables", {}))
    load_policy = catalogs["load_combo_policy.yaml"]
    families, aliases = combo_families_and_aliases(load_policy)
    features = catalogs["feature_catalog.yaml"].get("features", {})

    for feature_name, feature in features.items():
        lowered = feature_name.lower()
        for term in FORBIDDEN_FEATURE_NAME_TERMS:
            if term in lowered:
                raise ContractValidationError(f"feature_catalog contains forbidden pseudo-check term in feature name: {feature_name}")
        source = feature.get("source") or {}
        table_key = source.get("table_key")
        if table_key is not None and table_key not in tables:
            raise ContractValidationError(f"Feature {feature_name} references unknown table_key {table_key}")
        combo = source.get("combo_family")
        if combo and not expand_combo_family(combo, families, aliases):
            raise ContractValidationError(f"Feature {feature_name} references unknown combo family {combo}")
        for dep in feature.get("derived_from", []) or []:
            if dep not in features:
                raise ContractValidationError(f"Feature {feature_name} derived_from unknown feature {dep}")
        for filt in source.get("filters", []) or []:
            val = str(filt.get("value", ""))
            for ref in re.findall(r"\$\{([^}]+)\}", val):
                if ref not in features:
                    raise ContractValidationError(f"Feature {feature_name} filter references unknown feature {ref}")

    text = yaml.safe_dump(catalogs["feature_catalog.yaml"], sort_keys=True)
    rebar = catalogs["feature_catalog.yaml"].get("rebar_semantics", {})
    flow = set(rebar.get("canonical_flow", []))
    missing = sorted(REQUIRED_REBAR_ROLES - flow)
    if missing:
        raise ContractValidationError("Missing canonical rebar roles: " + ", ".join(missing))
    roles = {feature.get("semantic_role") for feature in features.values()}
    missing_role_features = sorted(REQUIRED_REBAR_ROLES - roles)
    if missing_role_features:
        raise ContractValidationError("No feature carries canonical rebar role(s): " + ", ".join(missing_role_features))
    forbidden_found = sorted(term for term in FORBIDDEN_REBAR_TERMS if term in text and term not in rebar.get("forbidden_central_terms", []))
    if forbidden_found:
        raise ContractValidationError("Forbidden rebar terms used outside explicit forbidden list: " + ", ".join(forbidden_found))


def validate_design_combo_matrix(catalogs: dict[str, dict[str, Any]]) -> None:
    load_policy = catalogs["load_combo_policy.yaml"]
    families, aliases = combo_families_and_aliases(load_policy)
    tables = set(catalogs["table_registry.yaml"].get("tables", {}))
    for row in catalogs["design_combo_matrix.yaml"].get("design_mappings", []):
        combo = row.get("combo_family")
        expanded = expand_combo_family(combo, families, aliases)
        if not expanded:
            raise ContractValidationError(f"design_combo_matrix uses unknown combo family: {combo}")
        table_key = row.get("design_result_table_key")
        if table_key is not None and table_key not in tables:
            raise ContractValidationError(f"design_combo_matrix references unknown table_key: {table_key}")
        if row.get("reinforcement_design"):
            blocked = [fam for fam in expanded if load_policy["combo_families"][fam].get("reinforcement_design_allowed") is False]
            if blocked:
                raise ContractValidationError(f"DISP/non-design combo used for reinforcement design in {row.get('id')}: {blocked}")



def validate_etabs_feature_source_contract(catalogs: dict[str, dict[str, Any]]) -> None:
    """Validate allowed source provenance for current accepted FeatureSnapshot features."""
    contract = catalogs["etabs_feature_source_contract.yaml"]
    feature_catalog = catalogs["feature_catalog.yaml"].get("features", {})
    entries = contract.get("sources", [])
    if not isinstance(entries, list) or not entries:
        raise ContractValidationError("etabs_feature_source_contract must contain a non-empty sources list")
    feature_ids = [row.get("feature_id") for row in entries]
    duplicates = sorted({fid for fid in feature_ids if feature_ids.count(fid) > 1})
    if duplicates:
        raise ContractValidationError("etabs_feature_source_contract has duplicate feature_id entries: " + ", ".join(duplicates))
    unknown = sorted(fid for fid in feature_ids if fid not in feature_catalog)
    if unknown:
        raise ContractValidationError("etabs_feature_source_contract references unknown feature_id(s): " + ", ".join(unknown))

    forbidden_sources = {"excel_production", "check_result", "engineering_verdict"}
    locked_unlock_scopes = {
        "future_rebar_unlock", "future_flexure_unlock", "future_shear_unlock", "future_capacity_unlock", "capacity_design",
    }
    future_feature_roles = {
        "TBDY_MIN_REQUIRED_REBAR", "GOVERNING_REQUIRED_REBAR", "ENGINE_SELECTED_REBAR", "USER_PROVIDED_REBAR", "FINAL_DETAILING_REQUIRED",
    }
    for row in entries:
        fid = row.get("feature_id")
        if row.get("source_type") == "excel_production":
            raise ContractValidationError(f"{fid} uses forbidden excel_production source_type")
        if row.get("source_status") in {"OK", "FAIL", "WARNING", "NO_DATA"}:
            raise ContractValidationError(f"{fid} contains CheckResult source status token")
        if set(row.get("forbidden_source", []) or []) & {"OK", "FAIL", "WARNING", "NO_DATA"}:
            raise ContractValidationError(f"{fid} contains CheckResult status token in forbidden_source")
        if not forbidden_sources.intersection(set(row.get("forbidden_source", []) or [])):
            raise ContractValidationError(f"{fid} must explicitly forbid at least one check/verdict/excel source")
        if row.get("source_scope") in locked_unlock_scopes:
            raise ContractValidationError(f"{fid} unlocks a future source scope: {row.get('source_scope')}")
        if row.get("semantic_role") in future_feature_roles:
            raise ContractValidationError(f"{fid} contracts future locked rebar/detailing role: {row.get('semantic_role')}")
        text = yaml.safe_dump(row, sort_keys=True)
        for token in ["CheckResult", "engineering_verdict", "live_verdict", "status_from_counts"]:
            if token in text and token not in (row.get("forbidden_source") or []):
                raise ContractValidationError(f"{fid} leaks forbidden result/verdict token: {token}")

    by_id = {row.get("feature_id"): row for row in entries}
    for fid in ["story_drift_value", "story_drift_max_mm", "story_drift_output_case", "story_drift_direction"]:
        row = by_id.get(fid)
        if not row or row.get("canonical_table_key") != "story_drifts" or row.get("display_selection_required") is not True:
            raise ContractValidationError(f"{fid} must require Story Drifts display selection")
        if row.get("preferred_output_case_default") != "Crack_SeisY_UpSoil":
            raise ContractValidationError(f"{fid} must default preferred output case to Crack_SeisY_UpSoil")
    torsion = by_id.get("story_torsion_a1_coefficient")
    if not torsion or torsion.get("canonical_table_key") != "story_max_over_avg_drifts" or torsion.get("display_selection_required") is not True:
        raise ContractValidationError("story_torsion_a1_coefficient must require Story Max Over Avg Drifts display selection")
    for fid in ["base_reaction_fx", "base_reaction_fy", "base_reaction_x_kN", "base_reaction_y_kN"]:
        row = by_id.get(fid)
        if not row or row.get("canonical_table_key") != "base_reactions" or row.get("display_selection_required") is not True:
            raise ContractValidationError(f"{fid} must require Base Reactions display selection")
        ident = row.get("identity_requirements") or {}
        if ident.get("requires_story") is not False or ident.get("requires_component_id") is not False:
            raise ContractValidationError(f"{fid} must not require story or component identity")
    for fid in ["modal_sum_ux", "modal_sum_uy"]:
        row = by_id.get(fid)
        if not row or row.get("aggregation") != "max_cumulative":
            raise ContractValidationError(f"{fid} must use max_cumulative aggregation")
        if "fixed_mode_10_only" not in set(row.get("forbidden_source", []) or []):
            raise ContractValidationError(f"{fid} must forbid fixed_mode_10_only")
    for fid in ["beam_width_mm", "beam_depth_mm", "beam_length_mm"]:
        row = by_id.get(fid)
        if not row or row.get("source_type") != "direct_api":
            raise ContractValidationError(f"{fid} must be contracted as direct_api geometry")
        if "section_name_inference" not in set(row.get("forbidden_source", []) or []):
            raise ContractValidationError(f"{fid} must forbid section_name_inference")


def validate_section_state_policy(catalogs: dict[str, dict[str, Any]]) -> None:
    families, _ = combo_families_and_aliases(catalogs["load_combo_policy.yaml"])
    mapping = catalogs["section_state_policy.yaml"].get("combo_family_to_section_state", {})
    missing = sorted(families - set(mapping))
    if missing:
        raise ContractValidationError("section_state_policy missing mapping for combo family/families: " + ", ".join(missing))
    allowed = set(catalogs["section_state_policy.yaml"].get("allowed_states", []))
    for fam, row in mapping.items():
        if fam not in families:
            raise ContractValidationError(f"section_state_policy references unknown combo family: {fam}")
        if row.get("default_state") not in allowed:
            raise ContractValidationError(f"section_state_policy uses unknown section state for {fam}: {row.get('default_state')}")
    if catalogs["section_state_policy.yaml"].get("missing_section_state_behavior") != "diagnostic_and_block":
        raise ContractValidationError("missing_section_state_behavior must be diagnostic_and_block")


def validate_check_catalog(catalogs: dict[str, dict[str, Any]]) -> None:
    check_catalog = catalogs["check_catalog.yaml"]
    feature_names = set(catalogs["feature_catalog.yaml"].get("features", {}))
    checks = check_catalog.get("checks", {})
    for check_id, check in checks.items():
        for feature_name in check.get("required_features", []) or []:
            if feature_name not in feature_names:
                raise ContractValidationError(f"Check {check_id} references missing feature {feature_name}")
        for feature_name in check.get("optional_features", []) or []:
            if feature_name not in feature_names:
                raise ContractValidationError(f"Check {check_id} references missing optional feature {feature_name}")
        ratio_type = (check.get("pass_rule") or {}).get("ratio_type")
        if ratio_type not in check_catalog.get("ratio_semantics", {}):
            raise ContractValidationError(f"Check {check_id} uses unknown ratio_type {ratio_type}")

    text = yaml.safe_dump(check_catalog, sort_keys=True)
    forbidden_tokens: set[str] = set()
    for table in catalogs["table_registry.yaml"].get("tables", {}).values():
        if table.get("logical_name"):
            forbidden_tokens.add(table["logical_name"])
        for provider_names in (table.get("provider_sources") or {}).values():
            forbidden_tokens.update(provider_names or [])
    forbidden_tokens.update({"ETABS_TABLE:", "include_patterns", "exclude_patterns", "combo_regex", "^", ".*"})
    leaks = sorted(token for token in forbidden_tokens if token and token in text)
    if leaks:
        raise ContractValidationError("check_catalog contains ETABS table name or combo regex: " + ", ".join(leaks[:8]))


def validate_scope_alignment(catalogs: dict[str, dict[str, Any]]) -> None:
    checks = set(catalogs["check_catalog.yaml"].get("checks", {}))
    scope_items = catalogs["high_ductility_check_scope.yaml"].get("scope_items", [])
    reverse = catalogs["check_scope_alignment.yaml"].get("reverse_mappings", [])
    aligned_checks = {row.get("check_catalog_key") for row in reverse if row.get("check_catalog_key")}
    for item in scope_items:
        status = item.get("status")
        keys = item.get("related_check_catalog_keys") or []
        reason = item.get("missing_alignment_reason")
        if status == "CONTRACTED" and not keys and not reason:
            raise ContractValidationError(f"CONTRACTED high ductility scope item has no check mapping and no pending reason: {item.get('check_scope_id')}")
        if status in {"BACKLOG", "PENDING_ALIGNMENT"} and not reason:
            raise ContractValidationError(f"{status} scope item lacks missing_alignment_reason: {item.get('check_scope_id')}")
        for key in keys:
            if key not in checks:
                raise ContractValidationError(f"Scope item {item.get('check_scope_id')} references unknown check_catalog key {key}")
    for check_id in checks:
        if check_id not in aligned_checks:
            check = catalogs["check_catalog.yaml"]["checks"].get(check_id, {})
            if not check.get("out_of_scope_reason"):
                raise ContractValidationError(f"check_catalog key has no scope alignment and no out_of_scope reason: {check_id}")


def validate_evidence_semantics(example: dict[str, Any], label: str) -> None:
    if example.get("evidence_status") == "FULL":
        required = ["source_table", "source_column", "source_row", "output_case", "combo_family"]
        missing = [field for field in required if example.get(field) in (None, "", {})]
        if missing:
            raise ContractValidationError(f"FULL evidence missing {missing} in {label}")
    if example.get("evidence_status") in {"PARTIAL", "MISSING"} and not example.get("messages"):
        raise ContractValidationError(f"{example.get('evidence_status')} evidence must include messages/reason in {label}")


def validate_coverage_semantics(example: dict[str, Any], label: str) -> None:
    forbidden_keys = {"ratio", "ratio_type", "pass_rule", "check_result", "check_results", "CheckResult", "emitted_status"}
    for row in example.get("checks", []):
        row_keys = set(row)
        forbidden_present = sorted(row_keys & forbidden_keys)
        if forbidden_present:
            raise ContractValidationError(f"coverage row contains forbidden CheckResult/decision/ratio field(s) in {label}: {forbidden_present}")
        text = repr(row)
        if "'OK'" in text or '"OK"' in text or "'FAIL'" in text or '"FAIL"' in text or "CheckResult" in text:
            raise ContractValidationError(f"coverage emits forbidden OK/FAIL/CheckResult token in {label}: {row.get('check_id')}")
        if row.get("coverage_status") == "BLOCKED" and not row.get("reason"):
            raise ContractValidationError(f"coverage BLOCKED item missing reason in {label}: {row.get('check_id')}")
        if row.get("coverage_status") == "BLOCKED" and not row.get("missing_features"):
            raise ContractValidationError(f"coverage BLOCKED item missing missing_features in {label}: {row.get('check_id')}")
        if row.get("coverage_status") == "BLOCKED" and not row.get("missing_feature_sources"):
            raise ContractValidationError(f"coverage BLOCKED item missing expected source diagnostics in {label}: {row.get('check_id')}")
        if row.get("coverage_status") == "PARTIAL" and not row.get("reason"):
            raise ContractValidationError(f"coverage PARTIAL item missing reason in {label}: {row.get('check_id')}")
        if row.get("coverage_status") == "PARTIAL" and not (row.get("missing_design_context_sources") or row.get("expected_evidence_requirements") or row.get("source_diagnostics")):
            raise ContractValidationError(f"coverage PARTIAL item missing expected source diagnostics in {label}: {row.get('check_id')}")


def validate_check_result_semantics(example: dict[str, Any], label: str) -> None:
    if "id" in example or "check_type" in example:
        raise ContractValidationError(f"CheckResult uses legacy id/check_type instead of check_id/component_type in {label}")
    if "check_id" not in example or "component_type" not in example:
        raise ContractValidationError(f"CheckResult must require check_id and component_type in {label}")




def validate_feature_snapshot_semantics(example: dict[str, Any], label: str) -> None:
    forbidden_feature_keys = {
        "check_id", "check_result", "check_results", "CheckResult", "pass", "fail",
        "OK", "FAIL", "verdict", "live_verdict", "engineering_verdict",
        "check_engine_status", "structural_status", "status_from_counts",
    }
    allowed_statuses = {"RESOLVED", "PARTIAL", "MISSING", "BLOCKED", "UNKNOWN"}
    for snapshot in example.get("snapshots", []):
        for feature_name, feature in (snapshot.get("features") or {}).items():
            present = forbidden_feature_keys & set(feature)
            if present:
                raise ContractValidationError(f"FeatureSnapshot feature {feature_name} contains forbidden check/result/verdict field(s) in {label}: {sorted(present)}")
            status = feature.get("status")
            if status not in allowed_statuses:
                raise ContractValidationError(f"FeatureSnapshot feature {feature_name} has non-feature status {status!r} in {label}")
            if status in {"OK", "FAIL", "WARNING", "NO_DATA"}:
                raise ContractValidationError(f"FeatureSnapshot feature {feature_name} contains CheckResult status token in {label}: {status}")

def validate_architecture_import_quarantine(project_root: Path) -> None:
    init_path = project_root / "tbdy_engine" / "__init__.py"
    text = init_path.read_text(encoding="utf-8") if init_path.exists() else ""
    if "runner_v2" in text:
        raise ContractValidationError("importing tbdy_engine imports runner_v2 or exposes runner_v2")


def validate_excel_sheet_policy() -> None:
    physical_sheet_names = ["00_Summary", "01_Checks", "02_Features", "03_No_Data", "04_Evidence", "05_ETABS_Tables", "06_Beam_Design", "07_Review", "99_Manifest"]
    too_long = [name for name in physical_sheet_names if len(name) > 31]
    if too_long:
        raise ContractValidationError("Excel physical sheet names exceed 31 characters: " + ", ".join(too_long))




def _walk_contract_text(obj: Any, *, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    rows: list[tuple[tuple[str, ...], str]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            rows.extend(_walk_contract_text(value, path=path + (str(key),)))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            rows.extend(_walk_contract_text(value, path=path + (str(idx),)))
    elif isinstance(obj, str):
        rows.append((path, obj))
    return rows


def _contains_forbidden_logic(obj: Any) -> bool:
    # The policy may name forbidden concepts under a dedicated forbidden_content section.
    # That declaration is allowed; formulas/check logic anywhere else are not.
    tokens = ("formula", "expression", "equation", "compute", "ratio =", "check_logic")
    for path, value in _walk_contract_text(obj):
        if "forbidden_content" in path:
            continue
        lowered = value.lower()
        if any(token in lowered for token in tokens):
            return True
    return False



def validate_coverage_policy(catalogs: dict[str, dict[str, Any]]) -> None:
    policy = catalogs["coverage_policy.yaml"]
    statuses = policy.get("coverage_statuses", {})
    for status in ["RUNNABLE", "BLOCKED", "PARTIAL"]:
        row = statuses.get(status, {})
        if row.get("decision_status_allowed") is not False:
            raise ContractValidationError(f"coverage_policy must forbid decision status emission for {status}")
    outputs = policy.get("forbidden_outputs", {})
    if outputs.get("ratio_fields_forbidden") is not True:
        raise ContractValidationError("coverage_policy must forbid ratio fields")
    if outputs.get("check_result_objects_forbidden") is not True:
        raise ContractValidationError("coverage_policy must forbid CheckResult objects")
    if sorted(outputs.get("decision_status_tokens", [])) != ["FAIL", "OK"]:
        raise ContractValidationError("coverage_policy must explicitly forbid OK/FAIL output tokens")
    rules = policy.get("runnability_rules", {})
    if rules.get("missing_required_feature") != "BLOCKED":
        raise ContractValidationError("coverage_policy malformed: missing required feature must be BLOCKED")
    if rules.get("partial_evidence") != "PARTIAL":
        raise ContractValidationError("coverage_policy malformed: partial evidence must be PARTIAL")
    expected = policy.get("expected_source_diagnostics", {})
    for key in [
        "required_for_blocked",
        "required_for_partial",
        "missing_feature_sources_required",
        "missing_design_context_sources_required",
        "expected_evidence_requirements_required_for_partial_evidence",
        "source_diagnostics_required",
    ]:
        if expected.get(key) is not True:
            raise ContractValidationError(f"coverage_policy must require expected source diagnostics: {key}")
    if not set(["etabs_table", "computed", "design_context"]).issubset(set(expected.get("source_kinds", []))):
        raise ContractValidationError("coverage_policy expected source diagnostics must support etabs_table, computed, and design_context")
    text = yaml.safe_dump(policy, sort_keys=True)
    # Policy can name forbidden words only inside forbidden_outputs.decision_status_tokens.
    scrubbed = re.sub(r"decision_status_tokens:.*?(?=\n[a-zA-Z_]+:|\Z)", "decision_status_tokens: <declared>", text, flags=re.S)
    if "CheckResult" in scrubbed and "check_result_objects_forbidden" not in scrubbed:
        raise ContractValidationError("coverage_policy must not define CheckResult payloads")

def validate_workspace_contract(catalogs: dict[str, dict[str, Any]]) -> None:
    workspace = catalogs["workspace_contract.yaml"]
    sources = workspace.get("allowed_source_types", {})
    if sources.get("ETABS_LIVE", {}).get("production_allowed") is not True:
        raise ContractValidationError("ETABS_LIVE is the only production source")
    for source_type in ["EXCEL_FIXTURE", "JSON_FIXTURE", "FAKE_PROVIDER"]:
        if sources.get(source_type, {}).get("production_allowed") is True:
            raise ContractValidationError(f"{source_type} cannot be production source")
    rules = workspace.get("source_rules", {})
    if rules.get("production_source") != "ETABS_LIVE":
        raise ContractValidationError("workspace production_source must be ETABS_LIVE")
    if rules.get("excel_never_production_input") is not True:
        raise ContractValidationError("Excel must never become production input")
    if _contains_forbidden_logic(workspace):
        raise ContractValidationError("workspace_contract must not define formulas or check logic")


def validate_element_registry(catalogs: dict[str, dict[str, Any]]) -> None:
    registry = catalogs["element_registry.yaml"]
    if _contains_forbidden_logic(registry):
        raise ContractValidationError("element_registry must not define formulas or check logic")
    required = {"beam", "column", "wall", "slab", "raft", "story", "global"}
    registered = set((registry.get("element_types") or {}).keys())
    missing_required = sorted(required - registered)
    if missing_required:
        raise ContractValidationError("element_registry missing required element types: " + ", ".join(missing_required))

    for feature_name, feature in catalogs["feature_catalog.yaml"].get("features", {}).items():
        et = feature.get("element_type")
        if et not in registered:
            raise ContractValidationError(f"element_type used in feature_catalog missing from element_registry: {et} ({feature_name})")
    for check_id, check in catalogs["check_catalog.yaml"].get("checks", {}).items():
        et = check.get("element_type")
        if et not in registered:
            raise ContractValidationError(f"element_type used in check_catalog missing from element_registry: {et} ({check_id})")
    for row in catalogs["design_combo_matrix.yaml"].get("design_mappings", []):
        et = row.get("element_type")
        if et not in registered:
            raise ContractValidationError(f"element_type used in design_combo_matrix missing from element_registry: {et}")
    for item in catalogs["high_ductility_check_scope.yaml"].get("scope_items", []):
        et = item.get("element_type")
        if et not in registered:
            raise ContractValidationError(f"element_type used in high_ductility_check_scope missing from element_registry: {et}")

    allowed_component_types = {row.get("component_type") for row in registry.get("element_types", {}).values()}
    allowed_component_types |= set(registry.get("explicit_allowed_component_types", []) or [])
    schema = load_json(_schema_dir(DEFAULT_CATALOG_DIR) / "check_result.schema.json") if DEFAULT_CATALOG_DIR.exists() else {}
    # When validating a copied tree, caller patches via schema_dir in validate_check_result_component_types.


def validate_check_result_component_types(catalog_dir: Path, catalogs: dict[str, dict[str, Any]]) -> None:
    registry = catalogs["element_registry.yaml"]
    registered_components = {row.get("component_type") for row in registry.get("element_types", {}).values()}
    explicit = set(registry.get("explicit_allowed_component_types", []) or [])
    allowed = registered_components | explicit
    schema = load_json(_schema_dir(catalog_dir) / "check_result.schema.json")
    enum_values = set((schema.get("properties", {}).get("component_type", {}).get("enum") or []))
    unknown = sorted(v for v in enum_values if v not in allowed)
    if unknown:
        raise ContractValidationError("component_type in check_result.schema missing from element_registry: " + ", ".join(unknown))


def validate_workspace_state_semantics(example: dict[str, Any], label: str, catalogs: dict[str, dict[str, Any]]) -> None:
    registry_types = set(catalogs["element_registry.yaml"].get("element_types", {}))
    for element in example.get("elements", []):
        if element.get("element_type") not in registry_types:
            raise ContractValidationError(f"workspace_state has unknown element type in {label}: {element.get('element_type')}")
    source = example.get("source", {})
    if source.get("environment") == "production" and source.get("source_type") in {"EXCEL_FIXTURE", "JSON_FIXTURE", "FAKE_PROVIDER"}:
        raise ContractValidationError(f"{source.get('source_type')} cannot be production source")
    coverage_status = (example.get("coverage_state") or {}).get("status")
    check_status = (example.get("check_state") or {}).get("status")
    report_status = (example.get("report_state") or {}).get("status")
    if coverage_status == "BLOCKED" and check_status == "EXECUTED":
        raise ContractValidationError("check_status cannot be EXECUTED when coverage_status is BLOCKED")
    if report_status == "COMPLETE" and check_status == "NOT_STARTED":
        raise ContractValidationError("report_status cannot be COMPLETE when check_status is NOT_STARTED")
    if report_status == "COMPLETE" and not example.get("check_results_json"):
        raise ContractValidationError("report_status cannot be COMPLETE when check_results_json is missing")
    if any(key in example for key in ["check_results", "CheckResult", "check_result_objects"]):
        raise ContractValidationError("workspace_state must not contain CheckResult objects")


def validate_engine_boundary_docs(project_root: Path) -> None:
    spec = project_root / "docs" / "ENGINE_BOUNDARY_SPEC_v1.md"
    text = spec.read_text(encoding="utf-8") if spec.exists() else ""
    required_phrases = [
        "CheckEngine must not read table registry",
        "combo policy",
        "design basis",
        "section-state policy",
        "design combo matrix",
        "ETABS table names",
        "combo regex",
        "actual combo names",
        "Excel sheet names",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in text]
    if missing:
        raise ContractValidationError("ENGINE_BOUNDARY_SPEC_v1.md missing boundary phrase(s): " + ", ".join(missing))

def validate_contract_tree(catalog_dir: Path = DEFAULT_CATALOG_DIR, *, validate_architecture: bool = True) -> None:
    catalog_dir = Path(catalog_dir)
    project_root = catalog_dir.parents[1]
    validate_files_exist(catalog_dir)
    catalogs = {name: load_yaml(catalog_dir / name) for name in CATALOG_FILES}
    validate_catalog_schemas(catalog_dir, catalogs)
    validate_combo_policy(catalogs["load_combo_policy.yaml"])
    validate_feature_catalog(catalogs)
    validate_etabs_feature_source_contract(catalogs)
    validate_design_combo_matrix(catalogs)
    validate_section_state_policy(catalogs)
    validate_check_catalog(catalogs)
    validate_scope_alignment(catalogs)
    validate_workspace_contract(catalogs)
    validate_coverage_policy(catalogs)
    validate_element_registry(catalogs)
    validate_check_result_component_types(catalog_dir, catalogs)
    validate_examples(catalog_dir, catalogs)
    validate_excel_sheet_policy()
    validate_engine_boundary_docs(project_root)
    if validate_architecture:
        validate_architecture_import_quarantine(project_root)


def validate_contract_constitution(catalog_dir: Path = DEFAULT_CATALOG_DIR, *, validate_architecture: bool = True) -> None:
    """Callable validator used by CLI, contract loader, and tests.

    This preserves the same validation semantics as the CLI entrypoint.
    """
    validate_contract_tree(catalog_dir, validate_architecture=validate_architecture)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Contract Constitution catalog tree")
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_CATALOG_DIR)
    args = parser.parse_args([] if argv is None else argv)
    validate_contract_constitution(args.catalog_dir)
    schema_count = len(list((_schema_dir(args.catalog_dir)).glob("*.schema.json")))
    print("Contract Constitution v1.0 C5.6 validation: OK")
    print(f"Catalogs: {len(CATALOG_FILES)} | Schemas: {schema_count} | Examples: {len(EXAMPLE_SCHEMA_MAP)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
