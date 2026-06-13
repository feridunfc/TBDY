from pathlib import Path
import shutil

import pytest

from tbdy_engine.contracts.loader import ContractConstitutionLoader, load_contracts
from tbdy_engine.tools.validate_contract_constitution import ContractValidationError

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def test_contract_loader_loads_all_c5_catalogs_schemas_and_examples():
    bundle = load_contracts(CATALOG_DIR)
    assert bundle.catalog_count == 13
    assert bundle.schema_count == 18
    assert bundle.example_count == 11
    assert "workspace_contract.yaml" in bundle.catalogs
    assert "element_registry.yaml" in bundle.catalogs
    assert "coverage_policy.yaml" in bundle.catalogs
    assert "etabs_feature_source_contract.yaml" in bundle.catalogs


def test_contract_loader_exposes_read_only_data():
    bundle = ContractConstitutionLoader(CATALOG_DIR).load()
    with pytest.raises(TypeError):
        bundle.catalogs["new.yaml"] = {}
    with pytest.raises(TypeError):
        bundle.catalog("load_combo_policy.yaml")["policy"] = {}
    with pytest.raises(TypeError):
        bundle.catalog("load_combo_policy.yaml")["combo_families"]["DISP_X"]["read_only"] = False


def test_contract_loader_fails_fast_on_malformed_copy(tmp_path):
    bad_root = tmp_path / "catalogs"
    shutil.copytree(CATALOG_DIR, bad_root)
    (bad_root / "feature_catalog.yaml").write_text("features: [", encoding="utf-8")
    with pytest.raises(Exception):
        ContractConstitutionLoader(bad_root).load()


def test_contract_loader_reuses_callable_validator():
    from tbdy_engine.tools.validate_contract_constitution import validate_contract_constitution

    validate_contract_constitution(CATALOG_DIR)
