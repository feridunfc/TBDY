from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from tbdy_engine.checks.dry_run import C11_CHECK_DEFINITIONS
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    direct_api_geometry_from_payload,
    tables_from_probe_report,
    unit_context_from_payload,
    to_jsonable,
)
from tbdy_engine.features.value import FeatureValueStatus

FIXTURE = Path("tests/fixtures/c8_3_direct_api_geometry_fixture.json")


def _payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


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


def test_live_story_snapshot_uses_target_story_not_story_smoke_null():
    story = _resolver(target_story="+14.5").build_story_snapshot()
    assert story.component_id == "+14.5"
    assert story.identity["component"] == "+14.5"
    assert story.identity["story"] == "+14.5"
    assert story.identity["story"] is not None


def test_story_row_selection_normalizes_target_story():
    payload = deepcopy(_payload())
    _table(payload, "story_drifts")["sample_rows_limited"][0]["Story"] = "14.5000"
    _table(payload, "story_max_over_avg_drifts")["sample_rows_limited"][0]["Story"] = " 14.5 "
    story = _resolver(payload, target_story="+14.5").build_story_snapshot()
    _assert_full_resolved(_feature(story, "story_drift_value"))
    _assert_full_resolved(_feature(story, "story_torsion_a1_coefficient"))
    assert story.identity["story"] == "+14.5"


def test_story_drifts_resolve_with_full_evidence_when_target_story_exists():
    story = _resolver().build_story_snapshot()
    expected = {
        "story_drift_value": "Drift",
        "story_drift_max_mm": "Drift",
        "story_drift_output_case": "OutputCase",
        "story_drift_direction": "Direction",
    }
    for name, source_column in expected.items():
        feature = _feature(story, name)
        _assert_full_resolved(feature)
        assert feature.evidence[0].source_table == "story_drifts"
        assert feature.evidence[0].source_column == source_column
        assert feature.evidence[0].source_row.get("story") == "+14.5"


def test_story_torsion_resolves_with_full_evidence_when_target_story_exists():
    story = _resolver().build_story_snapshot()
    torsion = _feature(story, "story_torsion_a1_coefficient")
    _assert_full_resolved(torsion)
    assert torsion.evidence[0].source_table == "story_max_over_avg_drifts"
    assert torsion.evidence[0].source_column == "Ratio"
    assert torsion.evidence[0].unit == "ratio"


def test_base_reactions_do_not_require_story_identity():
    global_snapshot = _resolver().build_global_snapshot()
    for name, source_column in {
        "base_reaction_fx": "FX",
        "base_reaction_fy": "FY",
        "base_reaction_x_kN": "FX",
        "base_reaction_y_kN": "FY",
    }.items():
        feature = _feature(global_snapshot, name)
        _assert_full_resolved(feature)
        assert feature.evidence[0].source_table == "base_reactions"
        assert feature.evidence[0].source_column == source_column
        assert feature.evidence[0].output_case == "Crack_SeisY_UpSoil"


def test_base_reactions_prefer_valid_numeric_rows():
    payload = deepcopy(_payload())
    base = _table(payload, "base_reactions")
    valid = deepcopy(base["sample_rows_limited"][0])
    base["sample_rows_limited"] = [
        {"OutputCase": "BadCase", "FX": "not-a-number", "FY": 10.0},
        {"OutputCase": "OtherCase", "FX": 20.0, "FY": "bad"},
        valid,
    ]
    global_snapshot = _resolver(payload).build_global_snapshot()
    fx = _feature(global_snapshot, "base_reaction_fx")
    fy = _feature(global_snapshot, "base_reaction_fy")
    _assert_full_resolved(fx)
    _assert_full_resolved(fy)
    assert fx.evidence[0].output_case == "Crack_SeisY_UpSoil"
    assert fy.evidence[0].output_case == "Crack_SeisY_UpSoil"


def test_c8_3_live_style_counts_28_resolved_no_partials():
    outputs = _resolver().build_all()
    counts = {}
    for row in outputs.feature_resolution_report:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert counts == {"RESOLVED": 28}
    assert outputs.missing_features_report == ()


def test_modal_max_cumulative_preserved():
    global_snapshot = _resolver().build_global_snapshot()
    ux = _feature(global_snapshot, "modal_sum_ux")
    uy = _feature(global_snapshot, "modal_sum_uy")
    assert ux.evidence[0].source_row["aggregation_method"] == "max_cumulative"
    assert uy.evidence[0].source_row["aggregation_method"] == "max_cumulative"
    assert ux.value >= 0.90
    assert uy.value >= 0.90


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


def test_checkengine_boundary_unchanged():
    output = _resolver().build_all()
    assert all("CheckResult" not in json.dumps(to_jsonable(snapshot.as_dict())) for snapshot in output.snapshots)
    row = CoverageRow(
        check_id="modal_mass_participation",
        component_type="global",
        component_id="GLOBAL",
        required_features=("modal_sum_ux", "modal_sum_uy"),
        resolved_features=("modal_sum_ux", "modal_sum_uy"),
        coverage_status="RUNNABLE",
        evidence_status="FULL",
        reason="C11.1.3 explicit boundary test",
    )
    result = MinimalCheckEngine(C11_CHECK_DEFINITIONS).run_check("modal_mass_participation", _resolver().build_global_snapshot(), row)
    assert result.check_id == "modal_mass_participation"
