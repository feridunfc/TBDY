from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/table_registry.yaml").read_text(encoding="utf-8"))["tables"]
FAMILIES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/feature_family_map.yaml").read_text(encoding="utf-8"))["feature_families"]


def test_feature_family_source_tables_exist_and_do_not_unlock_checks():
    for family_id, family in FAMILIES.items():
        assert family["check_unlock_allowed"] is False, family_id
        for table_key in family["source_tables"]:
            assert table_key in TABLES, (family_id, table_key)
