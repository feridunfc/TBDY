from pathlib import Path
import json
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"
SCHEMA_DIR = CATALOG_DIR / "schemas"
EXAMPLE_DIR = CATALOG_DIR / "examples"

EXAMPLE_SCHEMA_MAP = {
    "evidence.full.example.json": "evidence.schema.json",
    "evidence.partial.example.json": "evidence.schema.json",
    "coverage_matrix.example.json": "coverage_matrix.schema.json",
    "check_result.example.json": "check_result.schema.json",
    "feature_snapshot.example.json": "feature_snapshot.schema.json",
    "workspace_state.example.json": "workspace_state.schema.json",
    "element_registry.example.json": "element_registry.schema.json",
    "etabs_feature_source_contract.example.json": "etabs_feature_source_contract.schema.json",
}


def test_examples_validate_against_schemas():
    for example_name, schema_name in EXAMPLE_SCHEMA_MAP.items():
        instance = json.loads((EXAMPLE_DIR / example_name).read_text(encoding="utf-8"))
        schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema).iter_errors(instance))
        assert not errors, f"{example_name}: {[e.message for e in errors]}"
