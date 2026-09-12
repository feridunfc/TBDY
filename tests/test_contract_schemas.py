from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.contracts.export_schema import CANONICAL_SCHEMA_DIR, export_all_schemas
from tbdy_engine.contracts.loader import ContractConstitutionLoader
from tbdy_engine.contracts.validation import validate_contracts
from tbdy_engine.tools.validate_contract_constitution import CATALOG_FILES, REQUIRED_SCHEMA_FILES


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def _bundle():
    return ContractConstitutionLoader(CATALOG_DIR).load()


def test_contract_constitution_loads_current_catalogs_schemas_and_examples():
    bundle = _bundle()
    assert set(CATALOG_FILES) <= set(bundle.catalogs)
    assert set(REQUIRED_SCHEMA_FILES) <= set(bundle.schemas)
    assert bundle.examples


def test_contract_bundle_is_current_constitution_not_retired_runtime_catalog():
    bundle = _bundle()
    assert "check_catalog.yaml" in bundle.catalogs
    assert "feature_catalog.yaml" in bundle.catalogs
    assert not hasattr(bundle, "legacy_raw")
    assert not hasattr(bundle, "runtime_catalog")


def test_current_check_catalog_contains_column_and_beam_contracts():
    checks = _bundle().catalogs["check_catalog.yaml"]["checks"]
    assert "column_geometry_min_dimension" in checks
    assert "column_pmm_contract" in checks
    assert "column_shear_contract" in checks
    assert "beam_geometry_min_width" in checks
    assert "beam_shear_ve_le_vr" in checks


def test_contract_validator_accepts_exact_repository_catalog():
    validate_contracts(CATALOG_DIR)


def test_every_check_references_existing_required_features():
    bundle = _bundle()
    checks = bundle.catalogs["check_catalog.yaml"]["checks"]
    features = bundle.catalogs["feature_catalog.yaml"]["features"]
    missing = {
        (check_id, feature_id)
        for check_id, row in checks.items()
        for feature_id in row.get("required_features", ())
        if feature_id not in features
    }
    assert missing == set()


def test_every_check_has_a_ratio_or_boolean_pass_rule():
    checks = _bundle().catalogs["check_catalog.yaml"]["checks"]
    assert checks
    for check_id, row in checks.items():
        pass_rule = row.get("pass_rule") or {}
        assert pass_rule.get("ratio_type"), check_id
        assert pass_rule.get("ok_if") is not None, check_id


def test_schema_export_uses_current_canonical_schema_authority(tmp_path):
    names = {path.name for path in export_all_schemas(tmp_path)}
    assert names == {path.name for path in CANONICAL_SCHEMA_DIR.glob("*.schema.json")}
    assert "check_catalog.schema.json" in names
    assert "check_result.schema.json" in names


def test_exported_schema_json_is_semantically_identical_to_canonical_source(tmp_path):
    for exported in export_all_schemas(tmp_path):
        canonical = CANONICAL_SCHEMA_DIR / exported.name
        assert json.loads(exported.read_text(encoding="utf-8")) == json.loads(canonical.read_text(encoding="utf-8"))


def test_required_schema_files_exist_in_canonical_directory():
    missing = [name for name in REQUIRED_SCHEMA_FILES if not (CANONICAL_SCHEMA_DIR / name).exists()]
    assert missing == []


def test_wall_contract_rows_are_explicit_and_not_inferred_from_old_runtime_models():
    checks = _bundle().catalogs["check_catalog.yaml"]["checks"]
    wall_rows = [row for row in checks.values() if row.get("element_type") == "wall"]
    assert wall_rows
    assert all("readiness" in row for row in wall_rows)
    assert all("required_features" in row for row in wall_rows)
