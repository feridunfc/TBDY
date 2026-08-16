from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.engine import _ALLOWED_CHECKS
from tbdy_engine.checks.wall_contract import PACK_B_NEW_CHECK_IDS, PACK_C_CHECK_IDS
from tbdy_engine.checks.wall_pack_a_contract import PACK_A_CHECK_IDS

ROOT = Path(__file__).resolve().parents[2]
BASE_CHECK_CATALOG = ROOT / "tbdy_engine/catalogs/check_catalog.yaml"
C13_5_CHECK_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_c13_5_p1_column_geometry.yaml"
P2_10_WALL_PACK_A_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_p2_10_wall_pack_a.yaml"
P2_10_WALL_PACK_B_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_p2_10_wall_pack_b.yaml"
P2_10_WALL_PACK_C_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_p2_10_wall_pack_c.yaml"


def _catalog_ids() -> set[str]:
    catalog_ids: set[str] = set()
    for catalog_path in (
        BASE_CHECK_CATALOG,
        C13_5_CHECK_OVERLAY,
        P2_10_WALL_PACK_A_OVERLAY,
        P2_10_WALL_PACK_B_OVERLAY,
        P2_10_WALL_PACK_C_OVERLAY,
    ):
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        catalog_ids.update(catalog["checks"])
    return catalog_ids


def test_allowed_checks_exist_in_check_catalog():
    expected = {
        "column_geometry_min_dimension", "column_geometry_min_width", "column_geometry_min_depth",
        "beam_geometry_min_width", "beam_geometry_min_depth", "beam_depth_width_ratio",
    } | set(PACK_A_CHECK_IDS) | set(PACK_B_NEW_CHECK_IDS) | set(PACK_C_CHECK_IDS)
    assert _ALLOWED_CHECKS == expected
    assert _ALLOWED_CHECKS.issubset(_catalog_ids())


def test_engine_does_not_use_engine_only_or_legacy_column_or_ge7_id():
    engine_text = (ROOT / "tbdy_engine/checks/engine.py").read_text(encoding="utf-8")
    assert "column_geometry_min_dimension" in engine_text
    assert "column_min_dimension" not in engine_text
    assert "WALL11_LENGTH_TO_THICKNESS_GE7" not in _ALLOWED_CHECKS
    assert not (_ALLOWED_CHECKS - _catalog_ids())
