from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke, tables_from_probe_report
from tbdy_engine.features.value import FeatureValueStatus

FIXTURE = Path("tests/fixtures/c8_table_headers_fixture.json")
FORBIDDEN_IMPORT_TEXT = (
    "runner_v2",
    "runtime",
    "archx",
    "old beam",
    "BeamCheckResult",
    "source.excel_adapter",
    "source.live_adapter",
)


def _resolver():
    bundle = load_contracts()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tables = tables_from_probe_report(payload, bundle)
    return C8LiveFeatureResolverSmoke(bundle, tables)


def _outputs():
    return _resolver().build_all()


def _feature(snapshot, name):
    return snapshot.features[name]


def _tables_payload(payload):
    return payload.get("tables", payload) if isinstance(payload, dict) else payload


def test_fake_live_table_fixture_resolves_beam_identity_with_design_section():
    beam = _resolver().build_beam_snapshot()
    assert beam.component_type == "beam"
    assert beam.identity["component"] == "297"
    assert beam.identity["label"] == "B1"
    assert beam.identity["story"] == "+14.5"
    assert beam.identity["section"] == "B40x70"
    assert _feature(beam, "beam_unique_name").value == "297"
    assert _feature(beam, "beam_section_name").status == FeatureValueStatus.RESOLVED
    assert any(d.code.value == "IDENTITY_SEEDED_FROM_DESIGN_SUMMARY" for d in beam.diagnostics)


def test_analysis_section_fallback_emits_diagnostic():
    bundle = load_contracts()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for table in _tables_payload(payload):
        if table["canonical_table_key"] == "frame_assignments":
            row = table["sample_rows_limited"][0]
            row.pop("DesignSect")
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle))
    beam = resolver.build_beam_snapshot()
    assert beam.identity["section"] == "B40x70_ANA"
    assert any(d.code.value == "ANALYSIS_SECTION_FALLBACK" for d in beam.diagnostics)
    assert any(d.code.value == "ANALYSIS_SECTION_FALLBACK" for d in beam.features["beam_section_name"].diagnostics)


def test_t2_t3_resolve_width_depth():
    beam = _resolver().build_beam_snapshot()
    assert _feature(beam, "beam_width_mm").value == 400
    assert _feature(beam, "beam_width_mm").evidence[0].source_column == "t2"
    assert _feature(beam, "beam_depth_mm").value == 700
    assert _feature(beam, "beam_depth_mm").evidence[0].source_column == "t3"


def test_beam_design_summary_observed_rebar_and_combo_fields_resolve():
    beam = _resolver().build_beam_snapshot()
    assert _feature(beam, "beam_As_top_etabs_required_mm2").value == 1250
    assert _feature(beam, "beam_As_top_etabs_required_mm2").evidence[0].source_column == "AsTop"
    assert _feature(beam, "beam_As_bottom_etabs_required_mm2").value == 1180
    assert _feature(beam, "beam_As_bottom_etabs_required_mm2").evidence[0].source_column == "AsBot"
    assert _feature(beam, "beam_shear_rebar_etabs_required_mm2").value == 420
    assert _feature(beam, "beam_shear_rebar_etabs_required_mm2").evidence[0].source_column == "VRebar"
    assert _feature(beam, "beam_As_top_combo").value == "Crack_SeisY_UpSoil"
    assert _feature(beam, "beam_As_bottom_combo").value == "Crack_SeisX"
    assert _feature(beam, "beam_V_combo").value == "Crack_SeisY"


def test_warnmsg_errmsg_are_evidence_diagnostics_not_checkresult_status():
    beam = _resolver().build_beam_snapshot()
    warn = _feature(beam, "beam_design_warn_msg")
    err = _feature(beam, "beam_design_err_msg")
    assert warn.value == "Shear design warning text"
    assert err.value == "No Message"
    assert any(d.code.value == "ETABS_WARNING_MESSAGE" for d in warn.diagnostics)
    serialized = json.dumps(beam.as_dict())
    assert "CheckResult" not in serialized
    assert '"OK"' not in serialized
    assert '"FAIL"' not in serialized


def test_story_drifts_drift_and_story_max_over_avg_ratio_are_separated():
    story = _resolver().build_story_snapshot()
    drift = _feature(story, "story_drift_value")
    torsion = _feature(story, "story_torsion_a1_coefficient")
    assert drift.value == 9.5
    assert drift.evidence[0].source_table == "story_drifts"
    assert drift.evidence[0].source_column == "Drift"
    assert torsion.value == 1.33
    assert torsion.evidence[0].source_table == "story_max_over_avg_drifts"
    assert torsion.evidence[0].source_column == "Ratio"


def test_historical_sample_only_modal_source_fails_closed():
    global_snapshot = _resolver().build_global_snapshot()
    for feature_name in ("modal_sum_ux", "modal_sum_uy"):
        feature = _feature(global_snapshot, feature_name)
        assert feature.status == FeatureValueStatus.PARTIAL
        assert feature.value is None
        assert any(diagnostic.code.value == "MODAL_SOURCE_INCOMPLETE" for diagnostic in feature.diagnostics)


def test_base_reactions_fx_fy_resolve():
    global_snapshot = _resolver().build_global_snapshot()
    assert _feature(global_snapshot, "base_reaction_fx").value == 1.0205
    assert _feature(global_snapshot, "base_reaction_fy").value == pytest.approx(2.4401)
    assert _feature(global_snapshot, "base_reaction_fx").evidence[0].source_column == "FX"
    assert _feature(global_snapshot, "base_reaction_fy").evidence[0].source_column == "FY"


def test_missing_section_row_produces_partial_or_missing():
    bundle = load_contracts()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for table in _tables_payload(payload):
        if table["canonical_table_key"] == "frame_section_properties":
            table["sample_rows_limited"] = [{"Name": "OTHER", "t3": 500, "t2": 300}]
    resolver = C8LiveFeatureResolverSmoke(bundle, tables_from_probe_report(payload, bundle))
    beam = resolver.build_beam_snapshot()
    assert beam.features["beam_width_mm"].status in {FeatureValueStatus.PARTIAL, FeatureValueStatus.MISSING}
    assert beam.features["beam_depth_mm"].status in {FeatureValueStatus.PARTIAL, FeatureValueStatus.MISSING}


def test_unknown_or_project_specific_combo_produces_diagnostic_not_verdict():
    beam = _resolver().build_beam_snapshot()
    top = beam.features["beam_As_top_etabs_required_mm2"]
    assert top.evidence[0].output_case == "Crack_SeisY_UpSoil"
    assert any(d.code.value == "COMBO_ENGINEERING_REVIEW" for d in top.diagnostics)
    serialized = json.dumps(top.as_dict())
    assert '"OK"' not in serialized
    assert '"FAIL"' not in serialized


def test_coverage_preview_does_not_execute_checkengine():
    outputs = _outputs()
    assert outputs.coverage_preview
    serialized = json.dumps(outputs.coverage_preview)
    assert "CheckResult" not in serialized
    assert '"OK"' not in serialized
    assert '"FAIL"' not in serialized
    statuses = {row.get("coverage_status") for row in outputs.coverage_preview if "coverage_status" in row}
    assert statuses & {"RUNNABLE", "PARTIAL", "BLOCKED"}


def test_c8_outputs_contain_no_checkresult_and_no_live_verdicts(tmp_path):
    from tbdy_engine.features.resolver.live_smoke import write_smoke_outputs
    outputs = _outputs()
    write_smoke_outputs(tmp_path, outputs)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "CheckResult" not in text
        assert '"OK"' not in text
        assert '"FAIL"' not in text
    meta = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))["metadata"]
    assert meta["check_engine_executed"] is False
    assert meta["check_result_emitted"] is False
    assert meta["live_verdict_emitted"] is False


def test_smoke_tool_fixture_mode_writes_required_outputs(tmp_path):
    out = tmp_path / "smoke"
    result = subprocess.run(
        [sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = {
        "feature_snapshot.json",
        "feature_resolution_report.json",
        "evidence_report.json",
        "missing_features_report.json",
        "coverage_preview.json",
        "legacy_alias_crosswalk_report.json",
    }
    assert expected <= {p.name for p in out.glob("*.json")}
    snapshot = json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["feature_status_counts"]["RESOLVED"] >= 10


def test_smoke_tool_import_safe_without_etabs():
    import tools.smoke_live_feature_resolver as smoke
    assert callable(smoke.main)


def test_no_legacy_or_forbidden_imports_in_c8_smoke_sources():
    import ast
    paths = [Path("tools/smoke_live_feature_resolver.py"), Path("tbdy_engine/features/resolver/live_smoke.py")]
    imported = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    forbidden_modules = {
        "runner_v2",
        "tbdy_engine.runner_v2",
        "tbdy_engine.runtime",
        "tbdy_engine.archx",
        "source.excel_adapter",
        "source.live_adapter",
        "tbdy_engine.checks.engine",
    }
    assert imported.isdisjoint(forbidden_modules)
