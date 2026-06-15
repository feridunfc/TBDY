from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/table_registry.yaml").read_text(encoding="utf-8"))["tables"]
SOURCES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/etabs_feature_source_contract.yaml").read_text(encoding="utf-8"))["sources"]


def test_feature_source_table_registry_keys_exist():
    for source in SOURCES:
        assert source["table_registry_key"] in TABLES, source["feature_id"]


def test_feature_sources_are_observed_data_not_results():
    forbidden = ("pass", "fail", "ok", "verdict", "check_result")
    for source in SOURCES:
        feature_id = source["feature_id"].lower()
        assert all(term not in feature_id for term in forbidden), source["feature_id"]
        assert source["check_unlock_allowed"] is False

def test_story_drift_sources_preserve_legacy_display_selection_invariant():
    by_id = {source["feature_id"]: source for source in SOURCES}
    for feature_id in [
        "story_drift_value",
        "story_drift_max_mm",
        "story_drift_output_case",
        "story_drift_direction",
    ]:
        row = by_id[feature_id]
        assert row["canonical_table_key"] == "story_drifts"
        assert row["display_selection_required"] is True
        assert row["preferred_output_case_default"] == "Crack_SeisY_UpSoil"
        assert row["check_unlock_allowed"] is False

