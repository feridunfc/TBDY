from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.engine import _ALLOWED_CHECKS

ROOT = Path(__file__).resolve().parents[2]


def _catalog_ids() -> set[str]:
    catalog = yaml.safe_load((ROOT / "tbdy_engine/catalogs/check_catalog.yaml").read_text(encoding="utf-8"))
    return set(catalog["checks"])


def test_allowed_checks_exist_in_check_catalog():
    assert _ALLOWED_CHECKS == {
        "column_geometry_min_dimension",
        "beam_geometry_min_width",
        "beam_geometry_min_depth",
        "beam_depth_width_ratio",
    }
    assert _ALLOWED_CHECKS.issubset(_catalog_ids())


def test_engine_does_not_use_engine_only_or_legacy_column_id():
    engine_text = (ROOT / "tbdy_engine/checks/engine.py").read_text(encoding="utf-8")
    assert "column_geometry_min_dimension" in engine_text
    assert "column_min_dimension" not in engine_text
    assert not (_ALLOWED_CHECKS - _catalog_ids())
