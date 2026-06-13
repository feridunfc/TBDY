from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke, tables_from_probe_report, unit_context_from_payload
from tbdy_engine.features.value import FeatureValueStatus

FIXTURE = Path("tests/fixtures/c8_1_live_units_fixture.json")
BASE_FIXTURE = Path("tests/fixtures/c8_table_headers_fixture.json")
OUT_FILES = {
    "feature_snapshot.json",
    "feature_resolution_report.json",
    "evidence_report.json",
    "missing_features_report.json",
    "identity_resolution_report.json",
    "geometry_resolution_report.json",
    "unit_context_report.json",
    "unit_basis_report.json",
    "unit_normalization_report.json",
    "geometry_source_table_debug_report.json",
    "live_failure_delta_report.json",
    "coverage_preview.json",
    "c8_1_boundary_report.json",
    "legacy_alias_crosswalk_report.json",
}


def _payload(path: Path = FIXTURE):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolver(path: Path = FIXTURE):
    bundle = load_contracts()
    payload = _payload(path)
    return C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))


def _beam(path: Path = FIXTURE):
    return _resolver(path).build_beam_snapshot()


def _feature(snapshot, name: str):
    return snapshot.features[name]


def test_c8_1_seed_identity_from_beam_design_summary():
    beam = _beam()
    report = _resolver().build_all().identity_resolution_report
    assert report["identity_seeded"] is True
    assert report["identity_source"] == "concrete_beam_design_summary"
    assert beam.component_id == "297"
    assert any(d.code.value == "IDENTITY_SEEDED_FROM_DESIGN_SUMMARY" for d in beam.diagnostics)


def test_c8_1_component_id_becomes_real_unique_name_when_seeded():
    beam = _beam()
    assert beam.component_id == "297"
    assert beam.component_id != "BEAM_SMOKE"
    assert _feature(beam, "beam_unique_name").value == "297"


def test_c8_1_frame_assignment_exact_match_by_unique_name_label_story_designsect():
    outputs = _resolver().build_all()
    report = outputs.identity_resolution_report
    attempts = report["frame_assignment_matching_attempts"]
    assert attempts[0]["matched"] is True
    assert attempts[0]["reason"] == "matched_by_unique_label_story_designsect"
    assert report["identity_confirmed_by_frame_assignments"] is True


def test_c8_1_analysissect_fallback_emits_diagnostic():
    payload = _payload()
    for table in payload["tables"]:
        if table["canonical_table_key"] == "frame_assignments":
            table["sample_rows_limited"][0].pop("DesignSect")
            table["sample_rows_limited"][0]["AnalysisSect"] = "B40x70"
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))
    beam = resolver.build_beam_snapshot()
    assert any(d.code.value == "ANALYSIS_SECTION_FALLBACK" for d in beam.diagnostics)
    assert any(d.code.value == "ANALYSIS_SECTION_FALLBACK" for d in beam.features["beam_section_name"].diagnostics)


def test_c8_1_no_fake_geometry_from_section_name():
    payload = _payload()
    for table in payload["tables"]:
        if table["canonical_table_key"] == "frame_section_properties":
            table["sample_rows_limited"] = []
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))
    beam = resolver.build_beam_snapshot()
    assert beam.features["beam_width_mm"].status != FeatureValueStatus.RESOLVED
    assert beam.features["beam_depth_mm"].status != FeatureValueStatus.RESOLVED
    suggestion = resolver.build_all().geometry_resolution_report["section_name_parse_suggestion"]
    assert suggestion["section_name"] == "B40x70"
    assert suggestion["used_as_feature_value"] is False


def test_c8_1_section_geometry_resolves_t2_t3_from_section_table():
    beam = _beam()
    assert _feature(beam, "beam_width_mm").value == 400
    assert _feature(beam, "beam_width_mm").evidence[0].source_column == "t2"
    assert _feature(beam, "beam_depth_mm").value == 700
    assert _feature(beam, "beam_depth_mm").evidence[0].source_column == "t3"


def test_c8_1_beam_width_depth_full_evidence():
    beam = _beam()
    for name in ("beam_width_mm", "beam_depth_mm"):
        feature = beam.features[name]
        assert feature.status == FeatureValueStatus.RESOLVED
        assert feature.evidence[0].evidence_status.value == "FULL"
        assert feature.evidence[0].source_table == "frame_section_properties"
        assert feature.evidence[0].source_row


def test_c8_1_beam_length_from_frame_assignment_length():
    beam = _beam()
    length = _feature(beam, "beam_length_mm")
    assert length.value == 6200
    assert length.evidence[0].source_table == "frame_assignments"
    assert length.evidence[0].source_column == "Length"


def test_c8_1_unmatched_frame_assignment_reports_attempted_keys():
    payload = _payload()
    for table in payload["tables"]:
        if table["canonical_table_key"] == "frame_assignments":
            table["sample_rows_limited"] = []
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))
    report = resolver.build_all().identity_resolution_report
    assert report["identity_seeded"] is True
    assert report["identity_confirmed_by_frame_assignments"] is False
    assert report["frame_assignment_matching_attempts"]
    assert any(d["code"] == "IDENTITY_SEEDED_NOT_FRAME_CONFIRMED" for d in report["diagnostics"])


def test_c8_1_reads_or_records_etabs_present_units():
    report = _resolver().build_all().unit_context_report["unit_context"]
    assert report["source"] == "fixture_declared_units"
    assert report["force_unit"] == "kN"
    assert report["length_unit"] == "m"
    assert report["unit_query_status"] == "RESOLVED"


def test_c8_1_fixture_declared_units_used_when_no_live_etabs():
    ctx = unit_context_from_payload(_payload(BASE_FIXTURE))
    assert ctx.source == "fixture_declared_units"
    assert ctx.unit_query_status == "RESOLVED"


def test_c8_1_unit_context_missing_blocks_silent_normalization():
    payload = {"tables": _payload()["tables"]}
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))
    beam = resolver.build_beam_snapshot()
    assert beam.features["beam_width_mm"].status == FeatureValueStatus.PARTIAL
    assert any(d.code.value == "UNIT_CONTEXT_MISSING" for d in beam.features["beam_width_mm"].diagnostics)


def test_c8_1_concrete_fc_30000_kn_per_m2_normalizes_to_30_mpa():
    material = _resolver().build_material_snapshot()
    fck = material.features["concrete_fck_mpa"]
    assert fck.value == 30
    assert fck.evidence[0].raw_value == 30000
    assert fck.evidence[0].normalized_value == 30


def test_c8_1_rebar_fy_500000_kn_per_m2_normalizes_to_500_mpa():
    material = _resolver().build_material_snapshot()
    fyk = material.features["rebar_fyk_mpa"]
    assert fyk.value == 500
    assert fyk.evidence[0].raw_value == 500000


def test_c8_1_area_0_000572_m2_normalizes_to_572_mm2():
    beam = _beam()
    astop = beam.features["beam_As_top_etabs_required_mm2"]
    assert astop.value == 572
    assert astop.evidence[0].raw_value == 0.000572
    assert astop.evidence[0].normalized_value == 572


def test_c8_1_geometry_m_to_mm_conversion_uses_length_unit():
    beam = _beam()
    assert beam.features["beam_width_mm"].value == 400
    assert beam.features["beam_depth_mm"].value == 700
    assert beam.features["beam_length_mm"].value == 6200


def test_c8_1_no_silent_mpa_label_without_unit_context():
    payload = {"tables": _payload()["tables"]}
    bundle = load_contracts()
    material = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload)).build_material_snapshot()
    assert material.features["concrete_fck_mpa"].status == FeatureValueStatus.PARTIAL
    assert any(d.code.value == "UNIT_NORMALIZATION_UNVERIFIED" for d in material.features["concrete_fck_mpa"].diagnostics)


def test_c8_1_vrebar_gets_shear_rebar_unit_semantics_review():
    beam = _beam()
    vrebar = beam.features["beam_shear_rebar_etabs_required_mm2"]
    assert any(d.code.value == "SHEAR_REBAR_UNIT_SEMANTICS_REVIEW" for d in vrebar.diagnostics)


def test_c8_1_unit_context_report_created(tmp_path):
    out = tmp_path / "c8_1"
    result = subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert OUT_FILES <= {p.name for p in out.glob("*.json")}
    report = json.loads((out / "unit_context_report.json").read_text(encoding="utf-8"))
    assert report["unit_context"]["unit_query_status"] == "RESOLVED"


def test_c8_1_unit_evidence_written_for_normalized_features(tmp_path):
    out = tmp_path / "c8_1"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], text=True, capture_output=True, check=True)
    evidence = json.loads((out / "evidence_report.json").read_text(encoding="utf-8"))
    astop = next(item for item in evidence if item["feature_name"] == "beam_As_top_etabs_required_mm2")
    assert astop["unit_evidence"]["raw_unit"] == "m2"
    assert astop["unit_evidence"]["normalized_unit"] == "mm2"
    assert astop["unit_evidence"]["unit_normalization_status"] == "NORMALIZED"


def test_c8_1_combo_review_diagnostic_preserved():
    beam = _beam()
    astop = beam.features["beam_As_top_etabs_required_mm2"]
    assert any(d.code.value == "COMBO_ENGINEERING_REVIEW" for d in astop.diagnostics)


def test_c8_1_drift_torsion_semantic_lock_preserved():
    story = _resolver().build_story_snapshot()
    assert story.features["story_drift_value"].evidence[0].source_column == "Drift"
    assert story.features["story_torsion_a1_coefficient"].evidence[0].source_column == "Ratio"
    assert story.features["story_torsion_a1_coefficient"].feature_name != "story_drift_value"


def test_c8_1_warnmsg_errmsg_evidence_only():
    beam = _beam()
    assert any(d.code.value == "ETABS_WARNING_MESSAGE" for d in beam.features["beam_design_warn_msg"].diagnostics)
    text = json.dumps(beam.as_dict())
    assert "CheckResult" not in text
    assert '"OK"' not in text
    assert '"FAIL"' not in text


def test_c8_1_no_checkengine_execution(tmp_path):
    out = tmp_path / "c8_1"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    boundary = json.loads((out / "c8_1_boundary_report.json").read_text(encoding="utf-8"))
    assert boundary["metadata"]["check_engine_executed"] is False


def test_c8_1_no_checkresult_output(tmp_path):
    out = tmp_path / "c8_1"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    assert "CheckResult" not in json.dumps({p.name: p.read_text(encoding="utf-8") for p in out.glob("*.json")})


def test_c8_1_no_ok_fail_verdicts(tmp_path):
    out = tmp_path / "c8_1"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)], check=True)
    text = "\n".join(p.read_text(encoding="utf-8") for p in out.glob("*.json"))
    assert '"OK"' not in text
    assert '"FAIL"' not in text


def test_c8_1_no_legacy_imports():
    paths = [Path("tools/smoke_live_feature_resolver.py"), Path("tbdy_engine/features/resolver/live_smoke.py")]
    forbidden = {
        "runner_v2", "tbdy_engine.runtime", "tbdy_engine.archx", "source.excel_adapter",
        "source.live_adapter", "tbdy_engine.checks.engine", "tbdy_engine.checks.result",
    }
    imported = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert imported.isdisjoint(forbidden)


def test_c8_1_import_safe_without_etabs():
    import tools.smoke_live_feature_resolver as smoke
    assert callable(smoke.main)


def test_c8_1_output_deterministic(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    cmd = [sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE)]
    first = subprocess.run(cmd + ["--out", str(out_a)], text=True, capture_output=True, check=False)
    second = subprocess.run(cmd + ["--out", str(out_b)], text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    for filename in sorted(OUT_FILES):
        assert (out_a / filename).read_text(encoding="utf-8") == (out_b / filename).read_text(encoding="utf-8")


def test_c8_2_decode_get_present_units_2_tuple_to_named_units():
    from tbdy_engine.features.resolver.live_smoke import decode_etabs_present_units

    decoded = decode_etabs_present_units([4, 6, 2, 0])
    assert decoded["force_unit"] == "kN"
    assert decoded["length_unit"] == "m"
    assert decoded["temperature_unit"] == "C"
    assert decoded["etabs_present_units_return_code"] == 0
    assert decoded["unit_query_status"] == "RESOLVED"


def test_c8_2_unit_context_status_resolved_only_after_enum_names_decoded():
    from tbdy_engine.features.resolver.live_smoke import unit_context_from_payload

    ctx = unit_context_from_payload({"unit_context": {"source": "live_etabs_present_units", "etabs_present_units_raw": [4, 6, 2, 0]}})
    assert ctx.unit_query_status == "RESOLVED"
    assert ctx.force_unit == "kN"
    assert ctx.length_unit == "m"
    assert ctx.temperature_unit == "C"

    unknown = unit_context_from_payload({"unit_context": {"source": "live_etabs_present_units", "etabs_present_units_raw": [99, 99, 99, 0]}})
    assert unknown.unit_query_status != "RESOLVED"
    assert unknown.force_unit is None


def test_c8_2_geometry_debug_report_includes_raw_table_diagnostics():
    report = _resolver().build_all().geometry_source_table_debug_report
    for table_key in ("frame_assignments", "frame_section_properties"):
        raw = report[table_key]["raw_table_diagnostics"]
        assert set(raw) >= {
            "table_name",
            "return_code",
            "number_fields",
            "number_records",
            "fields",
            "table_data_length",
            "expected_flat_length",
            "parser_status",
        }
        assert report[table_key]["row_count_investigation"]["headers_present"] is True


def test_c8_2_headers_without_rows_remain_partial_with_debug():
    payload = _payload()
    for table in payload["tables"]:
        if table["canonical_table_key"] in {"frame_assignments", "frame_section_properties"}:
            table["sample_rows_limited"] = []
            table["raw_table_diagnostics"] = {
                "table_name": table["actual_table_name"],
                "return_code": 0,
                "number_fields": len(table["headers"]),
                "number_records": 2,
                "fields": table["headers"],
                "table_data_length": 0,
                "expected_flat_length": 2 * len(table["headers"]),
                "parser_status": "EMPTY",
            }
    bundle = load_contracts()
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle), unit_context=unit_context_from_payload(payload))
    outputs = resolver.build_all()
    beam = outputs.snapshots[0]
    assert beam.features["beam_width_mm"].status != FeatureValueStatus.RESOLVED
    assert beam.features["beam_depth_mm"].status != FeatureValueStatus.RESOLVED
    assert beam.features["beam_length_mm"].status != FeatureValueStatus.RESOLVED
    debug = outputs.geometry_source_table_debug_report
    assert debug["frame_assignments"]["row_count"] == 0
    assert debug["frame_assignments"]["raw_table_diagnostics"]["number_records"] == 2
    assert debug["frame_section_properties"]["row_count_investigation"]["parser_status"] == "EMPTY"
