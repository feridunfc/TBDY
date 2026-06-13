from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def load(name):
    return yaml.safe_load((CATALOG_DIR / name).read_text(encoding="utf-8"))


def test_check_catalog_uses_only_feature_names():
    features = set(load("feature_catalog.yaml")["features"])
    checks = load("check_catalog.yaml")["checks"]
    for check_id, check in checks.items():
        for feature_name in check.get("required_features", []):
            assert feature_name in features, f"{check_id} -> {feature_name}"


def test_feature_sources_reference_known_table_keys():
    tables = set(load("table_registry.yaml")["tables"])
    features = load("feature_catalog.yaml")["features"]
    for feature_name, feature in features.items():
        source = feature.get("source") or {}
        table_key = source.get("table_key")
        assert table_key is None or table_key in tables, f"{feature_name} -> {table_key}"
