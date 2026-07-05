from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    direct_api_geometry_from_payload,
    tables_from_probe_report,
    unit_context_from_payload,
)
from tbdy_engine.features.value import FeatureValueStatus
from tools.probe_live_story_base_tables import build_table_debug

FIXTURE = Path("tests/fixtures/c8_3_direct_api_geometry_fixture.json")
P1_14_COMPLETE_FIXTURE = Path("tests/fixtures/p1_14_story_base_complete_population.json")


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _complete_payload() -> dict:
    return json.loads(P1_14_COMPLETE_FIXTURE.read_text(encoding="utf-8"))


def _table(payload: dict, canonical_key: str) -> dict:
    for item in payload["tables"]:
        if item.get("canonical_table_key") == canonical_key:
            return item
    raise AssertionError(f"fixture table {canonical_key} not found")


def _resolver(payload=None, *, target_story="+14.5"):
    payload = payload or _payload()
    bundle = load_contracts()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        direct_api_geometry=direct_api_geometry_from_payload(payload),
        target_component="297",
        target_label="B1",
        target_story=target_story,
        target_section="B40x70",
    )


def _feature(snapshot, name):
    return snapshot.features[name]


def _assert_full_resolved(feature):
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.evidence[0].evidence_status.value == "FULL"
    assert feature.evidence[0].source_row
    assert feature.evidence[0].source_column


def test_probe_story_drifts_debug_reports_headers_rows_and_lengths():
    raw = {
        "return_code": 0,
        "field_keys": ["Story", "OutputCase", "Direction", "Drift"],
        "number_records": 1,
        "number_fields": 4,
        "table_data": ["+14.5", "Crack_SeisY_UpSoil", "Y", 9.5],
    }
    report = build_table_debug("story_drifts", "Story Drifts", raw, target_story="+14.5")
    assert report["headers"] == ["Story", "OutputCase", "Direction", "Drift"]
    assert report["row_count"] == 1
    assert report["table_data_length"] == 4
    assert report["expected_flat_length"] == 4
    assert report["parser_status"] == "PARSED_ROWS"


def test_probe_reports_tabledata_empty_despite_records():
    raw = {
        "return_code": 0,
        "field_keys": ["Story", "OutputCase", "Direction", "Drift"],
        "number_records": 7,
        "number_fields": 4,
        "table_data": [],
    }
    report = build_table_debug("story_drifts", "Story Drifts", raw, target_story="+14.5")
    assert report["parser_status"] == "TABLEDATA_EMPTY_DESPITE_RECORDS"
    assert any(d["code"] == "ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS" for d in report["diagnostics"])


def test_story_selector_accepts_normalized_lowercase_live_rows():
    payload = deepcopy(_payload())
    story = _table(payload, "story_drifts")
    story["headers"] = story["field_keys"] = ["story", "output_case", "direction", "drift"]
    story["rows"] = [{"story": "14.5000", "output_case": "Crack_SeisY_UpSoil", "direction": "Y", "drift": 9.5}]
    story["row_count_reported"] = 1
    snapshot = _resolver(payload).build_story_snapshot()
    for name in ("story_drift_value", "story_drift_max_mm", "story_drift_output_case", "story_drift_direction"):
        _assert_full_resolved(_feature(snapshot, name))


def test_story_selector_accepts_raw_etabs_header_rows():
    snapshot = _resolver(_complete_payload()).build_story_snapshot()
    for name in ("story_drift_value", "story_drift_max_mm", "story_drift_output_case", "story_drift_direction"):
        _assert_full_resolved(_feature(snapshot, name))
    assert _feature(snapshot, "story_drift_value").evidence[0].source_column == "Drift"


def test_story_torsion_selector_accepts_lowercase_rows():
    payload = deepcopy(_payload())
    torsion = _table(payload, "story_max_over_avg_drifts")
    torsion["headers"] = torsion["field_keys"] = ["story", "output_case", "ratio"]
    torsion["rows"] = [{"story": "14.5", "output_case": "Crack_SeisY_UpSoil", "ratio": 1.33}]
    torsion["row_count_reported"] = 1
    snapshot = _resolver(payload).build_story_snapshot()
    _assert_full_resolved(_feature(snapshot, "story_torsion_a1_coefficient"))


def test_story_torsion_selector_accepts_raw_rows():
    snapshot = _resolver(_complete_payload()).build_story_snapshot()
    torsion = _feature(snapshot, "story_torsion_a1_coefficient")
    _assert_full_resolved(torsion)
    assert torsion.evidence[0].source_column == "Ratio"


def test_base_selector_accepts_lowercase_rows_without_story():
    payload = deepcopy(_payload())
    base = _table(payload, "base_reactions")
    base["headers"] = base["field_keys"] = ["output_case", "fx", "fy"]
    base["rows"] = [{"output_case": "Crack_SeisY_UpSoil", "fx": 1020.5, "fy": 2440.1}]
    base["row_count_reported"] = 1
    snapshot = _resolver(payload).build_global_snapshot()
    for name in ("base_reaction_fx", "base_reaction_fy", "base_reaction_x_kN", "base_reaction_y_kN"):
        _assert_full_resolved(_feature(snapshot, name))


def test_base_selector_accepts_raw_etabs_rows_without_story():
    snapshot = _resolver(_complete_payload()).build_global_snapshot()
    for name, col in {
        "base_reaction_fx": "FX",
        "base_reaction_fy": "FY",
        "base_reaction_x_kN": "FX",
        "base_reaction_y_kN": "FY",
    }.items():
        feature = _feature(snapshot, name)
        _assert_full_resolved(feature)
        assert feature.evidence[0].source_column == col


def test_base_selector_reports_partial_when_tabledata_empty_despite_records():
    payload = deepcopy(_payload())
    base = _table(payload, "base_reactions")
    base["sample_rows_limited"] = []
    base["raw_table_diagnostics"] = {
        "table_name": "Base Reactions",
        "return_code": 0,
        "number_fields": 3,
        "number_records": 12,
        "fields": ["OutputCase", "FX", "FY"],
        "table_data_length": 0,
        "expected_flat_length": 36,
        "parser_status": "EMPTY",
    }
    snapshot = _resolver(payload).build_global_snapshot()
    feature = _feature(snapshot, "base_reaction_fx")
    assert feature.status == FeatureValueStatus.PARTIAL
    assert any(d.code.value == "ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS" for d in feature.diagnostics)
    assert feature.value is None


def test_c8_3_historical_sample_modal_rows_remain_partial():
    outputs = _resolver().build_all()
    counts = {}
    for row in outputs.feature_resolution_report:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert counts == {"RESOLVED": 17, "PARTIAL": 11}
    assert outputs.story_base_table_debug_report["story_drifts"]["parser_status"] == "PARSED_ROWS"
    assert outputs.story_base_table_debug_report["story_drifts"]["source_row_storage_field_used"] == "sample_rows_limited"


def test_historical_sample_modal_source_does_not_emit_cumulative_evidence():
    snapshot = _resolver().build_global_snapshot()
    for feature_name in ("modal_sum_ux", "modal_sum_uy"):
        feature = snapshot.features[feature_name]
        assert feature.status == FeatureValueStatus.PARTIAL
        assert feature.value is None
        assert len(feature.evidence) == 1
        assert feature.evidence[0].evidence_status.value == "PARTIAL"
        assert feature.evidence[0].normalized_value is None
        assert {diagnostic.code.value for diagnostic in feature.diagnostics} == {"MODAL_SOURCE_INCOMPLETE"}


def test_no_checkresult_before_c11(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([
        sys.executable,
        "tools/smoke_live_feature_resolver.py",
        "--input",
        str(FIXTURE),
        "--out",
        str(out),
        "--target-component",
        "297",
        "--target-label",
        "B1",
        "--target-story",
        "+14.5",
        "--target-section",
        "B40x70",
    ], check=True)
    text = "\n".join(path.read_text(encoding="utf-8") for path in out.glob("*.json"))
    assert "CheckResult" not in text
    assert '"OK"' not in text
    assert '"FAIL"' not in text


def test_boundary_rebar_flexure_shear_locked():
    outputs = _resolver().build_all()
    boundary = outputs.boundary_report
    assert boundary["metadata"]["check_engine_executed"] is False
    assert boundary["metadata"]["check_result_emitted"] is False
    assert boundary["metadata"]["live_verdict_emitted"] is False


def test_live_smoke_captures_full_rows_for_story_base_modal_tables():
    from tools.smoke_live_feature_resolver import _live_table_max_rows

    assert _live_table_max_rows("Modal Participating Mass Ratios", 10) == 100000
    assert _live_table_max_rows("Story Drifts", 10) == 100000
    assert _live_table_max_rows("Story Max Over Avg Drifts", 10) == 100000
    assert _live_table_max_rows("Base Reactions", 10) == 100000
    assert _live_table_max_rows("Concrete Beam Design Summary - TS 500-2000(R2018)", 10) == 10
