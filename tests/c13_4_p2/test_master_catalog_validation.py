from __future__ import annotations

from pathlib import Path

from tbdy_engine.catalogs.loader import GEOMETRY_CHECK_IDS, load_modular_catalog, summarize_master_catalog, validate_master_catalog

ROOT = Path(__file__).resolve().parents[2]
MODULAR_ROOT = ROOT / "tbdy_engine" / "catalogs" / "modular"


def test_merged_master_catalog_contains_required_geometry_checks_and_features():
    master = load_modular_catalog(MODULAR_ROOT)
    validate_master_catalog(master)
    assert GEOMETRY_CHECK_IDS.issubset(set(master["checks"]))
    for check_id in GEOMETRY_CHECK_IDS:
        for feature_id in master["checks"][check_id]["required_features"]:
            assert feature_id in master["features"]


def test_summary_reports_counts_without_silent_failures():
    master = load_modular_catalog(MODULAR_ROOT)
    summary = summarize_master_catalog(master)
    assert summary["checks"] == 4
    assert summary["features"] == 4
    assert summary["duplicate_ids"] == 0
    assert summary["missing_feature_references"] == 0
