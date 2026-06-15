from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/table_registry.yaml").read_text(encoding="utf-8"))["tables"]


def test_table_registry_entries_have_required_contract_fields():
    required = {
        "provider",
        "evidence_status",
        "live_table_name",
        "excel_inventory_aliases",
        "fetch_policy",
        "verified_by",
        "required_columns",
        "optional_columns",
        "source_role",
        "check_unlock_allowed",
    }
    for key, entry in TABLES.items():
        assert required.issubset(entry.keys()), key
        assert entry["provider"] == "etabs"
        assert entry["check_unlock_allowed"] is False


def test_verified_live_entries_have_live_probe_proof():
    for key, entry in TABLES.items():
        if entry["evidence_status"] == "VERIFIED_LIVE":
            assert entry["verified_by"]["live_probe"] is True, key
