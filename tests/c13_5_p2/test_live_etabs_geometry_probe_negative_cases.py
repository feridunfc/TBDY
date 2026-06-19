from __future__ import annotations

import json
from pathlib import Path

from tbdy_engine.features.live_etabs_geometry_probe import (
    MappingGeometryRowProvider,
    load_mapping_provider_from_json,
    probe_geometry_feature_snapshots,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "c13_5_p2" / "fake_live_etabs_geometry_tables.json"
MODULE_PATH = ROOT / "tbdy_engine" / "features" / "live_etabs_geometry_probe.py"
FORBIDDEN_IMPORT_PATHS = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.archx",
    "tbdy_engine.product.geometry_product_smoke",
    "tbdy_engine.product.bundle_validator",
    "tbdy_engine.product.golden_regression",
)
FORBIDDEN_TERMS = (
    "beam_flexure",
    "beam_shear",
    "rebar_adequacy",
    "capacity_design",
    "governing_combo_selection",
    "force_envelope_selection",
    "drift_compliance",
    "final_building_compliance",
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_missing_width_produces_diagnostic_and_no_guessed_value(tmp_path: Path):
    result = probe_geometry_feature_snapshots(
        provider=load_mapping_provider_from_json(FIXTURE),
        output_dir=tmp_path,
        target_component="B_MISSING_WIDTH",
    )
    snapshot = _read_json(result.feature_snapshot_path)["snapshots"][0]
    diagnostics = _read_json(result.diagnostics_path)

    assert result.status == "PARTIAL"
    assert snapshot["features"]["beam_width_mm"]["status"] == "MISSING"
    assert snapshot["features"]["beam_width_mm"]["value"] is None
    assert snapshot["features"]["beam_width_mm"]["evidence"] == []
    assert any(item["code"] == "GEOMETRY_FEATURE_MISSING" and item["feature_id"] == "beam_width_mm" for item in diagnostics)
    assert {item["status"] for item in diagnostics}.isdisjoint({"OK", "FAIL"})


def test_missing_depth_produces_diagnostic_and_no_guessed_value(tmp_path: Path):
    provider = MappingGeometryRowProvider(
        [
            {
                "actual_table_name": "Fake ETABS Frame Geometry",
                "beam_width_mm": 300.0,
                "component_id": "B_MISSING_DEPTH",
                "component_type": "beam",
                "label": "B_MISSING_DEPTH",
                "section": "B40x70",
                "source_table": "fake_frame_geometry_table",
                "story": "+14.5",
                "unit": "mm",
            }
        ]
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    snapshot = _read_json(result.feature_snapshot_path)["snapshots"][0]
    diagnostics = _read_json(result.diagnostics_path)

    assert result.status == "PARTIAL"
    assert snapshot["features"]["beam_depth_mm"]["status"] == "MISSING"
    assert snapshot["features"]["beam_depth_mm"]["value"] is None
    assert snapshot["features"]["beam_depth_mm"]["evidence"] == []
    assert any(item["code"] == "GEOMETRY_FEATURE_MISSING" and item["feature_id"] == "beam_depth_mm" for item in diagnostics)


def test_wrong_unit_produces_blocked_diagnostic_and_no_conversion(tmp_path: Path):
    result = probe_geometry_feature_snapshots(
        provider=load_mapping_provider_from_json(FIXTURE),
        output_dir=tmp_path,
        target_component="C_WRONG_UNIT",
    )
    snapshot = _read_json(result.feature_snapshot_path)["snapshots"][0]
    diagnostics = _read_json(result.diagnostics_path)

    assert result.status == "PARTIAL"
    assert snapshot["features"]["column_width_mm"]["status"] == "PARTIAL"
    assert snapshot["features"]["column_width_mm"]["unit"] == "cm"
    assert snapshot["features"]["column_width_mm"]["value"] is None
    assert snapshot["features"]["column_depth_mm"]["status"] == "PARTIAL"
    assert snapshot["features"]["column_depth_mm"]["unit"] == "cm"
    assert snapshot["features"]["column_depth_mm"]["value"] is None
    assert sum(1 for item in diagnostics if item["status"] == "BLOCKED" and item["code"] == "GEOMETRY_UNIT_NOT_MM") == 2


def test_section_label_parsing_is_not_used_for_missing_dimensions(tmp_path: Path):
    provider = MappingGeometryRowProvider(
        [
            {
                "actual_table_name": "Fake ETABS Frame Geometry",
                "component_id": "B_LABEL_ONLY",
                "component_type": "beam",
                "label": "B_LABEL_ONLY",
                "section": "B40x70",
                "source_table": "fake_frame_geometry_table",
                "story": "+14.5",
                "unit": "mm",
            }
        ]
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    snapshot = _read_json(result.feature_snapshot_path)["snapshots"][0]

    assert result.status == "PARTIAL"
    assert snapshot["identity"]["section"] == "B40x70"
    assert snapshot["features"]["beam_width_mm"]["value"] is None
    assert snapshot["features"]["beam_depth_mm"]["value"] is None
    assert snapshot["features"]["beam_width_mm"]["status"] == "MISSING"
    assert snapshot["features"]["beam_depth_mm"]["status"] == "MISSING"


def test_unknown_component_type_is_warning_not_snapshot(tmp_path: Path):
    provider = MappingGeometryRowProvider(
        [
            {
                "component_id": "W1",
                "component_type": "wall",
                "label": "W1",
                "source_table": "fake_frame_geometry_table",
                "unit": "mm",
                "width_mm": 300.0,
                "depth_mm": 500.0,
            }
        ]
    )

    result = probe_geometry_feature_snapshots(provider=provider, output_dir=tmp_path)
    payload = _read_json(result.feature_snapshot_path)
    diagnostics = _read_json(result.diagnostics_path)

    assert result.status == "FAIL"
    assert payload["snapshots"] == []
    assert diagnostics[0]["status"] == "WARNING"
    assert diagnostics[0]["code"] == "COMPONENT_TYPE_OUT_OF_SCOPE"


def test_row_limit_truncation_is_recorded_as_warning(tmp_path: Path):
    rows = [
        {
            "actual_table_name": "Fake ETABS Frame Geometry",
            "component_id": f"B{index}",
            "component_type": "beam",
            "label": f"B{index}",
            "source_table": "fake_frame_geometry_table",
            "story": "+14.5",
            "unit": "mm",
            "width_mm": 300.0,
            "depth_mm": 600.0,
        }
        for index in range(3)
    ]

    result = probe_geometry_feature_snapshots(provider=MappingGeometryRowProvider(rows), output_dir=tmp_path, max_rows=2)
    summary = _read_json(result.summary_path)
    diagnostics = _read_json(result.diagnostics_path)

    assert result.status == "PARTIAL"
    assert summary["candidate_row_count"] == 3
    assert summary["selected_row_count"] == 2
    assert summary["truncation_applied"] is True
    assert any(item["code"] == "ROW_LIMIT_TRUNCATED" for item in diagnostics)


def test_probe_module_does_not_import_forbidden_paths_or_product_pipeline():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden_import in FORBIDDEN_IMPORT_PATHS:
        assert forbidden_import not in module_text


def test_probe_module_does_not_contain_forbidden_engineering_terms():
    module_text = MODULE_PATH.read_text(encoding="utf-8")

    for forbidden_term in FORBIDDEN_TERMS:
        assert forbidden_term not in module_text
