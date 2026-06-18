from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tbdy_engine.catalogs.loader import CatalogLoadError, load_modular_catalog


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


def _feature() -> dict:
    return {
        "element_type": "beam",
        "type": "float",
        "unit": "mm",
        "semantic_role": "GEOMETRY",
        "availability": {"status": "available", "confidence": "high"},
        "source": {"table_key": "frame_section_properties", "field_aliases": ["Width"], "filters": [], "combo_family": "NONE", "aggregation": "none"},
        "unit_policy": {"source_unit": "mm", "target_unit": "mm", "conversion": "none"},
        "fallback": {"allowed": False, "method": "none", "warning": ""},
        "semantics": {"source_level": "ETABS_RAW", "provided_rebar_verified": "not_applicable", "notes": ""},
        "evidence_fields": ["source_table", "source_row", "source_column", "raw_value", "normalized_value", "unit", "output_case", "combo_family"],
    }


def _check(required_features=None) -> dict:
    return {
        "title": "Beam Geometry Min Width",
        "element_type": "beam",
        "category": "GEOMETRY",
        "readiness": {"status": "ready", "reason": "fixture"},
        "required_features": ["beam_width_mm"] if required_features is None else required_features,
        "optional_features": [],
        "pass_rule": {"ratio_type": "boolean", "ok_if": "true"},
        "output": {"value": "contract_defined", "limit": "contract_defined", "ratio": "contract_defined", "unit": "mm"},
        "evidence_policy": {"include_features": ["beam_width_mm"], "include_formula": False, "include_source_refs": True},
        "code_ref": "contract",
    }


def test_duplicate_check_id_fails(tmp_path):
    _write(tmp_path / "a.yaml", {"checks": {"beam_geometry_min_width": _check()}, "features": {"beam_width_mm": _feature()}})
    _write(tmp_path / "b.yaml", {"checks": {"beam_geometry_min_width": _check()}})
    with pytest.raises(CatalogLoadError) as exc:
        load_modular_catalog(tmp_path)
    assert "duplicate id" in str(exc.value)


def test_duplicate_feature_id_fails(tmp_path):
    _write(tmp_path / "a.yaml", {"features": {"beam_width_mm": _feature()}})
    _write(tmp_path / "b.yaml", {"features": {"beam_width_mm": _feature()}})
    with pytest.raises(CatalogLoadError) as exc:
        load_modular_catalog(tmp_path)
    assert "duplicate id" in str(exc.value)


def test_missing_required_feature_reference_fails(tmp_path):
    _write(tmp_path / "a.yaml", {"checks": {"beam_geometry_min_width": _check(required_features=["missing_width_mm"])}, "features": {"beam_width_mm": _feature()}})
    with pytest.raises(CatalogLoadError) as exc:
        load_modular_catalog(tmp_path)
    assert "required feature not found" in str(exc.value)


def test_nested_required_features_list_fails(tmp_path):
    _write(tmp_path / "a.yaml", {"checks": {"beam_geometry_min_width": _check(required_features=[["beam_width_mm"]])}, "features": {"beam_width_mm": _feature()}})
    with pytest.raises(CatalogLoadError) as exc:
        load_modular_catalog(tmp_path)
    assert "nested list" in str(exc.value)


def test_missing_engineering_sensitive_field_fails(tmp_path):
    bad_check = _check()
    bad_check.pop("code_ref")
    _write(tmp_path / "a.yaml", {"checks": {"beam_geometry_min_width": bad_check}, "features": {"beam_width_mm": _feature()}})
    with pytest.raises(CatalogLoadError) as exc:
        load_modular_catalog(tmp_path)
    assert "missing required field" in str(exc.value)


def test_invalid_yaml_shape_fails(tmp_path):
    (tmp_path / "a.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(CatalogLoadError) as exc:
        load_modular_catalog(tmp_path)
    assert "YAML object" in str(exc.value)


def test_forbidden_legacy_import_in_new_loader_path_would_be_caught():
    loader_text = Path("tbdy_engine/catalogs/loader.py").read_text(encoding="utf-8")
    assert "tbdy_engine.design" not in loader_text
    assert "tbdy_engine.adapters.check_adapter" not in loader_text
    assert "runner_v2" not in loader_text
