from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from tbdy_engine.tools.validate_contract_constitution import ContractValidationError, validate_contract_tree

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "tbdy_engine" / "catalogs"


def write_yaml(path: Path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def malformed_tree(tmp_path: Path) -> Path:
    target = tmp_path / "catalogs"
    shutil.copytree(BASE, target)
    return target


def expect_fail(catalog_dir: Path, needle: str):
    with pytest.raises((ContractValidationError, FileNotFoundError, AssertionError)) as exc:
        validate_contract_tree(catalog_dir, validate_architecture=False)
    assert needle in str(exc.value)


def y(catalog_dir: Path, name: str):
    return yaml.safe_load((catalog_dir / name).read_text(encoding="utf-8"))


def test_feature_catalog_bad_ratio_feature_fails(malformed_tree):
    data = y(malformed_tree, "feature_catalog.yaml")
    sample = copy.deepcopy(next(iter(data["features"].values())))
    data["features"]["beam_bad_ratio_feature"] = sample
    write_yaml(malformed_tree / "feature_catalog.yaml", data)
    expect_fail(malformed_tree, "forbidden pseudo-check")


def test_check_catalog_bad_etabs_table_name_or_combo_regex_fails(malformed_tree):
    data = y(malformed_tree, "check_catalog.yaml")
    data["checks"]["beam_geometry_min_width"]["notes"] = "Use Concrete Beam Design Summary and ^COMB.*"
    write_yaml(malformed_tree / "check_catalog.yaml", data)
    expect_fail(malformed_tree, "ETABS table name or combo regex")


def test_check_catalog_missing_required_feature_fails(malformed_tree):
    data = y(malformed_tree, "check_catalog.yaml")
    data["checks"]["beam_geometry_min_width"]["required_features"].append("missing_feature_x")
    write_yaml(malformed_tree / "check_catalog.yaml", data)
    expect_fail(malformed_tree, "references missing feature")


def test_design_combo_matrix_unknown_combo_family_fails(malformed_tree):
    data = y(malformed_tree, "design_combo_matrix.yaml")
    data["design_mappings"][0]["combo_family"] = "UNKNOWN_FAMILY"
    write_yaml(malformed_tree / "design_combo_matrix.yaml", data)
    expect_fail(malformed_tree, "unknown combo family")


def test_combo_alias_expands_to_unknown_family_fails(malformed_tree):
    data = y(malformed_tree, "load_combo_policy.yaml")
    data["combo_family_aliases"]["DUCTILE_X_OR_Y"]["expands_to"].append("BOGUS")
    write_yaml(malformed_tree / "load_combo_policy.yaml", data)
    expect_fail(malformed_tree, "expands to unknown")


def test_displacement_combo_used_for_reinforcement_design_fails(malformed_tree):
    data = y(malformed_tree, "design_combo_matrix.yaml")
    for row in data["design_mappings"]:
        if row["element_type"] == "beam" and row["purpose"] == "flexure":
            row["combo_family"] = "DISP_X_OR_Y"
            row["reinforcement_design"] = True
    write_yaml(malformed_tree / "design_combo_matrix.yaml", data)
    expect_fail(malformed_tree, "reinforcement design")


def test_section_state_missing_combo_family_fails(malformed_tree):
    data = y(malformed_tree, "section_state_policy.yaml")
    data["combo_family_to_section_state"].pop("CAPACITY_X")
    write_yaml(malformed_tree / "section_state_policy.yaml", data)
    expect_fail(malformed_tree, "section_state_policy")


def test_contracted_scope_without_alignment_or_reason_fails(malformed_tree):
    data = y(malformed_tree, "high_ductility_check_scope.yaml")
    data["scope_items"][0]["related_check_catalog_keys"] = []
    data["scope_items"][0]["missing_alignment_reason"] = None
    write_yaml(malformed_tree / "high_ductility_check_scope.yaml", data)
    expect_fail(malformed_tree, "CONTRACTED high ductility scope item")


def test_orphan_check_catalog_key_fails(malformed_tree):
    data = y(malformed_tree, "check_scope_alignment.yaml")
    data["reverse_mappings"] = [r for r in data["reverse_mappings"] if r["check_catalog_key"] != "beam_geometry_min_width"]
    write_yaml(malformed_tree / "check_scope_alignment.yaml", data)
    expect_fail(malformed_tree, "no scope alignment")


def test_full_evidence_missing_source_fields_fails(malformed_tree):
    path = malformed_tree / "examples" / "evidence.full.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("source_table")
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_check_result_legacy_id_check_type_shape_fails(malformed_tree):
    path = malformed_tree / "examples" / "check_result.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["id"] = data.pop("check_id")
    data["check_type"] = "legacy"
    data.pop("component_type")
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_blocked_item_attempts_ok_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][1]["emitted_status"] = "OK"
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_import_tbdy_engine_does_not_import_runner_v2():
    text = (ROOT / "tbdy_engine" / "__init__.py").read_text(encoding="utf-8")
    assert "runner_v2" not in text

# -----------------------
# C2 workspace/element registry negative cases
# -----------------------

def test_workspace_state_unknown_element_type_fails(malformed_tree):
    path = malformed_tree / "examples" / "workspace_state.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["elements"].append({"element_type": "mystery", "component": "X1"})
    write_json(path, data)
    expect_fail(malformed_tree, "workspace_state has unknown element type")


def test_excel_fixture_as_production_source_fails(malformed_tree):
    path = malformed_tree / "examples" / "workspace_state.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["source"]["source_type"] = "EXCEL_FIXTURE"
    data["source"]["environment"] = "production"
    write_json(path, data)
    expect_fail(malformed_tree, "EXCEL_FIXTURE cannot be production source")


def test_check_status_executed_while_coverage_blocked_fails(malformed_tree):
    path = malformed_tree / "examples" / "workspace_state.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["coverage_state"]["status"] = "BLOCKED"
    data["check_state"]["status"] = "EXECUTED"
    write_json(path, data)
    expect_fail(malformed_tree, "check_status cannot be EXECUTED")


def test_report_complete_while_check_not_started_fails(malformed_tree):
    path = malformed_tree / "examples" / "workspace_state.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["check_state"]["status"] = "NOT_STARTED"
    data["report_state"]["status"] = "COMPLETE"
    write_json(path, data)
    expect_fail(malformed_tree, "report_status cannot be COMPLETE when check_status is NOT_STARTED")


def test_feature_catalog_element_type_missing_from_registry_fails(malformed_tree):
    data = y(malformed_tree, "feature_catalog.yaml")
    data["features"]["beam_width_mm"]["element_type"] = "mystery"
    write_yaml(malformed_tree / "feature_catalog.yaml", data)
    expect_fail(malformed_tree, "element_type used in feature_catalog missing from element_registry")


def test_check_catalog_element_type_missing_from_registry_fails(malformed_tree):
    data = y(malformed_tree, "check_catalog.yaml")
    data["checks"]["beam_geometry_min_width"]["element_type"] = "mystery"
    write_yaml(malformed_tree / "check_catalog.yaml", data)
    expect_fail(malformed_tree, "element_type used in check_catalog missing from element_registry")


def test_design_combo_matrix_element_type_missing_from_registry_fails(malformed_tree):
    data = y(malformed_tree, "design_combo_matrix.yaml")
    data["design_mappings"][0]["element_type"] = "mystery"
    write_yaml(malformed_tree / "design_combo_matrix.yaml", data)
    expect_fail(malformed_tree, "element_type used in design_combo_matrix missing from element_registry")


def test_check_result_schema_component_type_missing_from_registry_fails(malformed_tree):
    path = malformed_tree / "schemas" / "check_result.schema.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["properties"]["component_type"]["enum"].append("mystery")
    write_json(path, data)
    expect_fail(malformed_tree, "component_type in check_result.schema missing from element_registry")


def test_workspace_contract_contains_formula_logic_fails(malformed_tree):
    data = y(malformed_tree, "workspace_contract.yaml")
    data["illegal_formula"] = "formula = demand / capacity"
    write_yaml(malformed_tree / "workspace_contract.yaml", data)
    expect_fail(malformed_tree, "workspace_contract must not define formulas")


def test_element_registry_contains_formula_logic_fails(malformed_tree):
    data = y(malformed_tree, "element_registry.yaml")
    data["element_types"]["beam"]["notes"] = "formula = L / h"
    write_yaml(malformed_tree / "element_registry.yaml", data)
    expect_fail(malformed_tree, "element_registry must not define formulas")

# -----------------------
# C5 coverage policy/matrix negative cases
# -----------------------

def test_coverage_policy_allows_ratio_fields_fails(malformed_tree):
    data = y(malformed_tree, "coverage_policy.yaml")
    data["forbidden_outputs"]["ratio_fields_forbidden"] = False
    write_yaml(malformed_tree / "coverage_policy.yaml", data)
    expect_fail(malformed_tree, "Schema validation failed for coverage_policy.yaml")


def test_coverage_policy_allows_check_result_objects_fails(malformed_tree):
    data = y(malformed_tree, "coverage_policy.yaml")
    data["forbidden_outputs"]["check_result_objects_forbidden"] = False
    write_yaml(malformed_tree / "coverage_policy.yaml", data)
    expect_fail(malformed_tree, "Schema validation failed for coverage_policy.yaml")


def test_coverage_full_example_emits_ok_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.full.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["emitted_status"] = "OK"
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_full_example_contains_ratio_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.full.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["ratio"] = 0.5
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_full_example_contains_check_result_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.full.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["CheckResult"] = {"check_id": "beam_geometry_min_width"}
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_blocked_without_reason_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.blocked.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["reason"] = None
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_unknown_status_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.partial.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["coverage_status"] = "DONE"
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")

# -----------------------
# C5.1 expected source diagnostics negative cases
# -----------------------

def test_coverage_blocked_without_expected_feature_sources_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.blocked.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["missing_feature_sources"] = {}
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_partial_without_expected_sources_fails(malformed_tree):
    path = malformed_tree / "examples" / "coverage_matrix.partial.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"][0]["missing_design_context_sources"] = {}
    data["checks"][0]["expected_evidence_requirements"] = {}
    data["checks"][0]["source_diagnostics"] = []
    write_json(path, data)
    expect_fail(malformed_tree, "Schema validation failed")


def test_coverage_policy_disables_expected_source_diagnostics_fails(malformed_tree):
    data = y(malformed_tree, "coverage_policy.yaml")
    data["expected_source_diagnostics"]["required_for_blocked"] = False
    write_yaml(malformed_tree / "coverage_policy.yaml", data)
    expect_fail(malformed_tree, "Schema validation failed for coverage_policy.yaml")
