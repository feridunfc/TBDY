from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def load_yaml(name):
    return yaml.safe_load((CATALOG_DIR / name).read_text(encoding="utf-8"))


def test_element_registry_defines_required_structural_workspace_types():
    data = load_yaml("element_registry.yaml")
    assert {"beam", "column", "wall", "slab", "raft", "story", "global"} <= set(data["element_types"])
    for element_type, row in data["element_types"].items():
        for field in ["component_type", "identity_fields", "context_model", "demand_set", "design_result", "verification_result", "allowed_feature_groups", "allowed_check_categories"]:
            assert field in row, f"{element_type}: {field}"


def test_catalog_element_types_are_registered():
    registry = set(load_yaml("element_registry.yaml")["element_types"])
    feature_types = {f["element_type"] for f in load_yaml("feature_catalog.yaml")["features"].values()}
    check_types = {c["element_type"] for c in load_yaml("check_catalog.yaml")["checks"].values()}
    matrix_types = {r["element_type"] for r in load_yaml("design_combo_matrix.yaml")["design_mappings"]}
    scope_types = {s["element_type"] for s in load_yaml("high_ductility_check_scope.yaml")["scope_items"]}
    assert feature_types <= registry
    assert check_types <= registry
    assert matrix_types <= registry
    assert scope_types <= registry


def test_check_result_component_types_are_registered_or_explicitly_allowed():
    registry_data = load_yaml("element_registry.yaml")
    allowed = {r["component_type"] for r in registry_data["element_types"].values()} | set(registry_data.get("explicit_allowed_component_types", []))
    schema = json.loads((CATALOG_DIR / "schemas" / "check_result.schema.json").read_text(encoding="utf-8"))
    assert set(schema["properties"]["component_type"]["enum"]) <= allowed
