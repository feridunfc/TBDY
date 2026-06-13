from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    direct_api_geometry_from_payload,
    parser_strategy_report_for_response,
    table_extraction_debug_from_payload,
    tables_from_probe_report,
    unit_context_from_payload,
    to_jsonable,
)
from tbdy_engine.features.value import FeatureValueStatus

FIXTURE = Path("tests/fixtures/c8_3_direct_api_geometry_fixture.json")


def _payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _resolver():
    payload = _payload()
    bundle = load_contracts()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        direct_api_geometry=direct_api_geometry_from_payload(payload),
        table_extraction_debug=table_extraction_debug_from_payload(payload),
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
    )


def test_c8_3_direct_api_fallback_used_when_table_rows_empty():
    outputs = _resolver().build_all()
    assert outputs.geometry_source_table_debug_report["frame_assignments"]["row_count"] == 0
    assert outputs.geometry_source_table_debug_report["frame_section_properties"]["row_count"] == 0
    assert outputs.geometry_direct_api_report["used"] is True


def test_c8_3_width_depth_from_propframe_rectangle():
    beam = _resolver().build_beam_snapshot()
    assert beam.features["beam_width_mm"].value == 400
    assert beam.features["beam_depth_mm"].value == 700
    assert "PropFrame.GetRectangle" in beam.features["beam_width_mm"].evidence[0].source_column


def test_c8_3_length_from_frame_points_coordinates():
    beam = _resolver().build_beam_snapshot()
    length = beam.features["beam_length_mm"]
    assert length.value == 6200
    assert length.evidence[0].source_table == "direct_etabs_api"
    assert "PointObj.GetCoordCartesian" in json.dumps(to_jsonable(length.evidence[0].source_row))


def test_c8_3_geometry_uses_unit_context_m_to_mm():
    beam = _resolver().build_beam_snapshot()
    for name, value in (("beam_width_mm", 400), ("beam_depth_mm", 700), ("beam_length_mm", 6200)):
        feature = beam.features[name]
        assert feature.value == value
        assert feature.evidence[0].raw_value in {0.4, 0.7, 6.2}
        assert feature.evidence[0].unit == "mm"


def test_c8_3_geometry_full_evidence_from_direct_api():
    beam = _resolver().build_beam_snapshot()
    for name in ("beam_width_mm", "beam_depth_mm", "beam_length_mm"):
        feature = beam.features[name]
        assert feature.status == FeatureValueStatus.RESOLVED
        assert feature.evidence[0].evidence_status.value == "FULL"
        assert feature.evidence[0].source_table == "direct_etabs_api"
        assert feature.evidence[0].actual_table_name == "direct_etabs_api"


def test_c8_3_no_section_name_parse_as_feature_value():
    outputs = _resolver().build_all()
    suggestion = outputs.geometry_resolution_report["section_name_parse_suggestion"]
    assert suggestion["used_as_feature_value"] is False
    assert outputs.snapshots[0].features["beam_width_mm"].evidence[0].source_table != "section_name_parse"


def test_c8_3_section_parse_remains_diagnostic_only():
    beam = _resolver().build_beam_snapshot()
    assert any(d.code.value == "SECTION_NAME_PARSE_SUGGESTION" for d in beam.diagnostics)


def test_c8_3_direct_api_unavailable_keeps_geometry_partial():
    payload = _payload()
    payload.pop("direct_api_geometry", None)
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))
    beam = resolver.build_beam_snapshot()
    assert beam.features["beam_width_mm"].status == FeatureValueStatus.PARTIAL
    assert beam.features["beam_depth_mm"].status == FeatureValueStatus.PARTIAL
    assert beam.features["beam_length_mm"].status == FeatureValueStatus.PARTIAL


def test_c8_3_unit_context_unknown_keeps_geometry_partial():
    payload = _payload()
    payload.pop("unit_context", None)
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload), direct_api_geometry=direct_api_geometry_from_payload(payload))
    beam = resolver.build_beam_snapshot()
    assert beam.features["beam_width_mm"].status == FeatureValueStatus.PARTIAL
    assert beam.features["beam_length_mm"].status == FeatureValueStatus.PARTIAL


def test_c8_3_geometry_direct_api_report_created(tmp_path):
    out = tmp_path / "c8_3"
    result = subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out), "--target-component", "297", "--target-label", "B1", "--target-story", "+14.5", "--target-section", "B40x70"], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads((out / "geometry_direct_api_report.json").read_text(encoding="utf-8"))
    assert report["used"] is True
    assert report["normalized_length_mm"] == 6200


def test_c8_3_table_extraction_debug_reports_created(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    debug_dir = tmp_path / "c8_3_etabs_table_extraction_debug"
    assert (debug_dir / "raw_com_tuple_dump.json").exists()
    assert (debug_dir / "parser_strategy_report.json").exists()
    assert (debug_dir / "display_selection_diagnostics.json").exists()
    assert (debug_dir / "working_vs_failing_table_comparison.json").exists()


def test_c8_3_parser_strategy_can_reconstruct_flat_table_rows():
    raw = {
        "return_code": 0,
        "field_keys": ["Story", "Label", "UniqueName"],
        "number_fields": 3,
        "number_records": 1,
        "table_data": ["+14.5", "B1", "297"],
    }
    report = parser_strategy_report_for_response(raw, table_name="Frame Assignments - Summary")
    current = report["strategies"][0]
    assert current["parser_status"] == "FETCHED"
    assert current["sample_rows"][0]["UniqueName"] == "297"


def test_c8_3_empty_tabledata_despite_records_is_reported():
    outputs = _resolver().build_all()
    raw = outputs.geometry_source_table_debug_report["frame_assignments"]["raw_table_diagnostics"]
    assert raw["number_records"] == 998
    assert raw["table_data_length"] == 0
    assert raw["parser_status"] == "EMPTY"


def test_c8_3_no_checkengine_execution(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    boundary = json.loads((out / "c8_3_boundary_report.json").read_text(encoding="utf-8"))
    assert boundary["metadata"]["check_engine_executed"] is False


def test_c8_3_no_checkresult_output(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    text = "\n".join(p.read_text(encoding="utf-8") for p in out.glob("*.json"))
    assert "CheckResult" not in text


def test_c8_3_no_ok_fail_verdicts(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    text = "\n".join(p.read_text(encoding="utf-8") for p in out.glob("*.json"))
    assert '"OK"' not in text
    assert '"FAIL"' not in text


def test_c8_3_no_rebar_flexure_shear_unlock():
    boundary = _resolver().build_all().boundary_report
    assert boundary["rebar_flexure_shear_unlocked"] is False


def test_c8_3_import_safe_without_etabs():
    import tools.smoke_live_feature_resolver as smoke
    assert callable(smoke.main)


def test_c8_3_no_legacy_imports():
    paths = [Path("tools/smoke_live_feature_resolver.py"), Path("tbdy_engine/features/resolver/live_smoke.py")]
    forbidden = {"runner_v2", "tbdy_engine.runtime", "tbdy_engine.archx", "source.excel_adapter", "tbdy_engine.checks.engine", "tbdy_engine.checks.result"}
    imported = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert imported.isdisjoint(forbidden)


def test_c8_3_output_json_serializable(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    for path in out.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
