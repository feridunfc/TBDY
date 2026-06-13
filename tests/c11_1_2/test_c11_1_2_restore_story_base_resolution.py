from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.features.evidence import FeatureEvidence

FIXTURE = Path("tests/fixtures/c8_3_direct_api_geometry_fixture.json")


def _payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _resolver(payload=None):
    payload = payload or _payload()
    bundle = load_contracts()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        direct_api_geometry=direct_api_geometry_from_payload(payload),
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
    )


def _feature(snapshot, name):
    return snapshot.features[name]


def _assert_full_resolved(feature):
    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.evidence[0].evidence_status.value == "FULL"


def test_c11_1_2_restores_story_drift_resolution():
    story = _resolver().build_story_snapshot()
    for name, column in {
        "story_drift_value": "Drift",
        "story_drift_max_mm": "Drift",
        "story_drift_output_case": "OutputCase",
        "story_drift_direction": "Direction",
    }.items():
        feature = _feature(story, name)
        _assert_full_resolved(feature)
        assert feature.evidence[0].source_table == "story_drifts"
        assert feature.evidence[0].source_column == column
    assert _feature(story, "story_drift_value").unit == "mm"


def test_c11_1_2_restores_story_torsion_resolution():
    story = _resolver().build_story_snapshot()
    torsion = _feature(story, "story_torsion_a1_coefficient")
    _assert_full_resolved(torsion)
    assert torsion.evidence[0].source_table == "story_max_over_avg_drifts"
    assert torsion.evidence[0].source_column == "Ratio"
    assert torsion.unit == "ratio"


def test_c11_1_2_restores_base_reaction_resolution():
    global_snapshot = _resolver().build_global_snapshot()
    for name, column in {
        "base_reaction_fx": "FX",
        "base_reaction_fy": "FY",
        "base_reaction_x_kN": "FX",
        "base_reaction_y_kN": "FY",
    }.items():
        feature = _feature(global_snapshot, name)
        _assert_full_resolved(feature)
        assert feature.evidence[0].source_table == "base_reactions"
        assert feature.evidence[0].source_column == column
        assert feature.unit == "kN"


def test_c11_1_2_feature_snapshot_counts_28_resolved():
    outputs = _resolver().build_all()
    counts = {}
    for row in outputs.feature_resolution_report:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    assert counts == {"RESOLVED": 28}
    assert outputs.missing_features_report == ()


def test_modal_mass_max_cumulative_still_passes():
    global_snapshot = _resolver().build_global_snapshot()
    ux = _feature(global_snapshot, "modal_sum_ux")
    uy = _feature(global_snapshot, "modal_sum_uy")
    assert ux.evidence[0].source_row["aggregation_method"] == "max_cumulative"
    assert uy.evidence[0].source_row["aggregation_method"] == "max_cumulative"
    row = CoverageRow(
        check_id="modal_mass_participation",
        component_type="global",
        component_id="GLOBAL",
        required_features=("modal_sum_ux", "modal_sum_uy"),
        resolved_features=("modal_sum_ux", "modal_sum_uy"),
        coverage_status="RUNNABLE",
        evidence_status="FULL",
        reason="C11.1.2 regression fixture",
    )
    result = MinimalCheckEngine(C11_CHECK_DEFINITIONS).run_check("modal_mass_participation", global_snapshot, row)
    assert result.status.value == "OK"


@pytest.mark.parametrize("safe_value", ["STORY_SMOKE", "STORY_SAMPLE", "OKUL", "B40x70"])
def test_feature_snapshot_identity_guard_accepts_safe_values(safe_value):
    FeatureSnapshot(component_type="story", component_id=safe_value, identity={"component": safe_value}, features={})


@pytest.mark.parametrize("bad_key", ["check_id", "check_result", "check_results", "status_counts", "pass_rule", "result_panel", "formula_panel"])
def test_feature_snapshot_identity_guard_rejects_forbidden_keys(bad_key):
    with pytest.raises(ValueError) as exc:
        FeatureSnapshot(component_type="story", component_id="S1", identity={bad_key: "x"}, features={})
    assert bad_key in str(exc.value)
    assert "path=" in str(exc.value)


def test_feature_snapshot_still_rejects_checkresult_object_in_features():
    class LegacyCheckResult:
        pass

    with pytest.raises((TypeError, ValueError)):
        FeatureSnapshot(component_type="beam", component_id="B1", identity={"component": "B1"}, features={"beam_width_mm": LegacyCheckResult()})


def test_no_checkresult_before_c11(tmp_path):
    out = tmp_path / "c8_3"
    subprocess.run([sys.executable, "tools/smoke_live_feature_resolver.py", "--input", str(FIXTURE), "--out", str(out), "--target-component", "297", "--target-label", "B1", "--target-story", "+14.5", "--target-section", "B40x70"], check=True)
    text = "\n".join(path.read_text(encoding="utf-8") for path in out.glob("*.json"))
    assert "CheckResult" not in text
    assert '"OK"' not in text
    assert '"FAIL"' not in text


def test_checkengine_boundary_unchanged():
    # C11 dry-run remains explicit and isolated; resolver output contains no CheckResult.
    output = _resolver().build_all()
    assert all("CheckResult" not in json.dumps(to_jsonable(snapshot.as_dict())) for snapshot in output.snapshots)

    # The check engine is only used here explicitly on a runnable modal row.
    row = CoverageRow(
        check_id="modal_mass_participation",
        component_type="global",
        component_id="GLOBAL",
        required_features=("modal_sum_ux", "modal_sum_uy"),
        resolved_features=("modal_sum_ux", "modal_sum_uy"),
        coverage_status="RUNNABLE",
        evidence_status="FULL",
        reason="C11.1.2 explicit dry-run boundary test",
    )
    result = MinimalCheckEngine(C11_CHECK_DEFINITIONS).run_check("modal_mass_participation", _resolver().build_global_snapshot(), row)
    assert result.check_id == "modal_mass_participation"
