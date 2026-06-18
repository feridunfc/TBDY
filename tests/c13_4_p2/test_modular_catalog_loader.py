from __future__ import annotations

from pathlib import Path

from tbdy_engine.catalogs.loader import GEOMETRY_CHECK_IDS, load_modular_catalog, load_single_file_master

ROOT = Path(__file__).resolve().parents[2]
MODULAR_ROOT = ROOT / "tbdy_engine" / "catalogs" / "modular"
CATALOG_ROOT = ROOT / "tbdy_engine" / "catalogs"


def test_loader_reads_modular_check_fragments():
    master = load_modular_catalog(MODULAR_ROOT)
    assert GEOMETRY_CHECK_IDS.issubset(set(master["checks"]))


def test_loader_reads_modular_feature_fragments():
    master = load_modular_catalog(MODULAR_ROOT)
    assert {"beam_width_mm", "beam_depth_mm", "column_width_mm", "column_depth_mm"}.issubset(set(master["features"]))


def test_loader_merges_fragments_deterministically():
    first = load_modular_catalog(MODULAR_ROOT)
    second = load_modular_catalog(MODULAR_ROOT)
    assert list(first["checks"]) == list(second["checks"])
    assert list(first["features"]) == list(second["features"])
    assert first == second


def test_single_file_catalog_loading_path_still_works():
    master = load_single_file_master(CATALOG_ROOT)
    assert GEOMETRY_CHECK_IDS.issubset(set(master["checks"]))
    assert {"beam_width_mm", "beam_depth_mm"}.issubset(set(master["features"]))
