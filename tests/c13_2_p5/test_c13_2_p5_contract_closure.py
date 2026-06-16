from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = ROOT / "tbdy_engine" / "catalogs"
SCHEMAS = ROOT / "tbdy_engine" / "schemas"
MATRIX_PATH = CATALOGS / "source_feature_readiness_matrix.yaml"
SCHEMA_PATH = SCHEMAS / "source_feature_readiness_matrix.schema.json"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix():
    return load_yaml(MATRIX_PATH)


def rows(matrix):
    return {row["row_id"]: row for row in matrix["matrix"]}


def test_readiness_schema_validates_the_matrix(matrix):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(matrix))
    assert errors == []


def test_readiness_status_taxonomy_rejects_unknown_statuses():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    bad = load_yaml(MATRIX_PATH)
    bad["matrix"][0]["readiness_status"] = "READY_BUT_FAKE"
    errors = list(Draft202012Validator(schema).iter_errors(bad))
    assert errors


def test_material_properties_direct_readiness_requires_verified_live_source(matrix):
    r = rows(matrix)["material_mechanical_constants_source_capability"]
    assert r["readiness_status"] == "READY_DIRECT_SOURCE"
    assert r["source_families"] == ["material_properties"]
    assert set(r["required_source_fields"]) >= {"Material", "E1", "G12", "U12"}


def test_story_derived_elevation_readiness_requires_bselev_derivation_policy(matrix):
    r = rows(matrix)["story_derived_elevation_policy"]
    assert r["readiness_status"] == "READY_DERIVED_SOURCE"
    policy = r["derivation_policy"]
    assert policy["derived_elevation_supported"] is True
    assert policy["base_elevation_column"] == "BSElev"
    assert set(policy["input_fields"]) >= {"Story", "Height", "BSElev"}


def test_story_derived_elevation_must_not_claim_direct_elevation_column(matrix):
    policy = rows(matrix)["story_derived_elevation_policy"]["derivation_policy"]
    assert policy["elevation_is_direct_column"] is False


def test_pier_section_properties_direct_readiness_allows_missing_literal_section_column(matrix):
    r = rows(matrix)["pier_geometry_thickness_direct"]
    assert r["readiness_status"] == "READY_DIRECT_SOURCE"
    assert "pier_section_properties" in r["source_families"]
    assert "Section" not in set(r["required_source_fields"])


def test_pier_section_properties_requires_direct_geometry_present(matrix):
    r = rows(matrix)["pier_geometry_width_direct"]
    assert set(r["required_source_fields"]) >= {"Story", "Pier", "Width"}
    assert r["readiness_status"] == "READY_DIRECT_SOURCE"


def test_semantic_review_families_cannot_be_ready_direct_source(matrix):
    semantic_sources = {"pier_forces", "beam_forces", "concrete_beam_design_summary", "concrete_column_design_summary", "pier_design_summary"}
    for row in matrix["matrix"]:
        if semantic_sources.intersection(row["source_families"]):
            assert row["readiness_status"] != "READY_DIRECT_SOURCE", row["row_id"]
            assert row["readiness_status"] != "READY_DERIVED_SOURCE", row["row_id"]


def test_check_unlock_allowed_is_false_for_all_rows(matrix):
    assert matrix["metadata"]["check_unlock_allowed"] is False
    assert all(row["check_unlock_allowed"] is False for row in matrix["matrix"])


def test_safe_to_implement_checks_now_is_false_globally(matrix):
    assert matrix["metadata"]["safe_to_implement_checks_now"] is False
    assert all(row["safe_to_implement_checks_now"] is False for row in matrix["matrix"])


def test_excel_inventory_is_evidence_only_and_not_production_source(matrix):
    assert matrix["metadata"]["excel_production_input"] is False
    assert all(row["excel_production_input"] is False for row in matrix["matrix"])
    text = MATRIX_PATH.read_text(encoding="utf-8").lower()
    assert "excel_production_input: true" not in text


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_no_feature_resolver_import_introduced():
    imports = _imports_for(ROOT / "tools" / "validate_c13_2_p5_contract_closure.py")
    assert "tbdy_engine.features.resolver.live_smoke" not in imports


def test_no_check_engine_import_introduced():
    imports = _imports_for(ROOT / "tools" / "validate_c13_2_p5_contract_closure.py")
    assert "tbdy_engine.checks.engine" not in imports


def test_validator_json_summary_has_zero_cross_reference_errors():
    result = subprocess.run(
        [sys.executable, "tools/validate_c13_2_p5_contract_closure.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["cross_reference_errors"] == 0
    assert payload["safe_to_implement_checks_now"] is False
    assert payload["check_unlock_allowed"] is False


def test_existing_p2_p4_tests_remain_compatible():
    assert (ROOT / "tests/c13_2_p2/test_verified_source_contract_schema_expansion.py").exists()
    assert (ROOT / "tests/c13_2_p4/test_c13_2_p4_promoted_blocked_sources.py").exists()


def test_unit_taxonomy_accepts_required_display_units(matrix):
    allowed = set(matrix["metadata"]["unit_policy"]["allowed_units"])
    assert {"kN", "m", "mm", "MPa", "ratio", "percent"}.issubset(allowed)


def test_default_report_units_are_declared(matrix):
    units = matrix["metadata"]["unit_policy"]["default_report_units"]
    assert units["force"] == "kN"
    assert units["moment"] == "kN.m"
    assert units["global_length_elevation"] == "m"
    assert units["section_dimensions"] == "mm"
    assert units["deformation_displacement"] == "mm"
    assert units["stress_material_strength"] == "MPa"
    assert "ratio" in units["drift"] or "percent" in units["drift"]


def test_unit_sensitive_source_rows_declare_quantity_kind(matrix):
    for row in matrix["matrix"]:
        assert row.get("quantity_kind"), row["row_id"]
        assert row.get("source_unit_policy"), row["row_id"]
        assert row.get("normalized_unit_policy"), row["row_id"]
        assert row.get("default_report_unit"), row["row_id"]


def test_raw_source_unit_policy_is_separate_from_report_display_unit_policy(matrix):
    policy = matrix["metadata"]["unit_policy"]
    assert policy["source_contract_silent_conversion_allowed"] is False
    assert policy["raw_source_value_policy"] != policy["default_report_units"]["force"]
    for row in matrix["matrix"]:
        assert row["source_unit_policy"] != row["default_report_unit"], row["row_id"]


def test_no_check_engine_unlock_is_introduced_by_unit_normalization_metadata(matrix):
    policy = matrix["metadata"]["unit_policy"]
    assert policy["check_engine_behavior_changed"] is False
    assert policy["checks_implemented"] is False
    assert policy["safe_to_implement_checks_now"] is False
    assert matrix["metadata"]["check_unlock_allowed"] is False
    assert all(row["check_unlock_allowed"] is False for row in matrix["matrix"])


def test_validator_summary_reports_unit_policy_closed():
    result = subprocess.run(
        [sys.executable, "tools/validate_c13_2_p5_contract_closure.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["unit_policy_closed"] is True
    assert {"kN", "m", "mm", "MPa", "ratio", "percent"}.issubset(set(payload["allowed_units"]))
