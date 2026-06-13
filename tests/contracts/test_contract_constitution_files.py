from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"
SCHEMA_DIR = CATALOG_DIR / "schemas"
EXAMPLE_DIR = CATALOG_DIR / "examples"

CATALOGS = [
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

EXAMPLES = [
    "evidence.full.example.json",
    "evidence.partial.example.json",
    "coverage_matrix.example.json",
    "check_result.example.json",
    "feature_snapshot.example.json",
    "workspace_state.example.json",
    "element_registry.example.json",
    "etabs_feature_source_contract.example.json",
]


def test_canonical_catalog_tree_exists():
    assert CATALOG_DIR.is_dir()
    assert SCHEMA_DIR.is_dir()
    assert EXAMPLE_DIR.is_dir()
    for name in CATALOGS:
        assert (CATALOG_DIR / name).is_file(), name
        assert (SCHEMA_DIR / name.replace(".yaml", ".schema.json")).is_file(), name
    for name in ["evidence.schema.json", "coverage_matrix.schema.json", "check_result.schema.json", "feature_snapshot.schema.json", "workspace_state.schema.json", "etabs_feature_source_contract.schema.json"]:
        assert (SCHEMA_DIR / name).is_file(), name
    for name in EXAMPLES:
        assert (EXAMPLE_DIR / name).is_file(), name
