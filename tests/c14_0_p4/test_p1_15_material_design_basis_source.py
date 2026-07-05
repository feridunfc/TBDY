from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import pytest

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke, tables_from_probe_report, unit_context_from_payload
from tbdy_engine.features.value import FeatureValueStatus
from tools import smoke_live_feature_resolver as smoke
from tools import verify_p1_15_material_design_basis_live_acceptance as verifier

FIXTURE = Path("tests/fixtures/p1_15_material_design_basis_complete_population.json")


def _payload(path: Path = FIXTURE):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolver(payload=None) -> C8LiveFeatureResolverSmoke:
    payload = payload or _payload()
    bundle = load_contracts()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
        preferred_output_case="Crack_SeisY_UpSoil",
    )


def _material(payload=None):
    return _resolver(payload).build_material_snapshot()


def test_fixture_replay_enforces_expected_material_values(tmp_path):
    out = tmp_path / "fixture_acceptance"
    rc = verifier.main(["--input", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    summary = json.loads((out / "p1_15_material_acceptance_summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "fixture_replay"
    assert summary["strict_expected_enforced"] is True
    assert summary["observed"]["component_section_name"] == "B40x70"
    assert summary["observed"]["component_section_type"] == "Beam"
    assert summary["observed"]["section_concrete_material_name"] == "C30/37"
    assert summary["observed"]["section_rebar_material_name"] == "B420C"
    assert summary["observed"]["concrete_fck_mpa"] == 30.0
    assert summary["observed"]["rebar_fyk_mpa"] == 500.0


def test_live_no_input_mode_does_not_enforce_stale_fixture_values(monkeypatch, tmp_path):
    source_out = tmp_path / "source"
    assert smoke.main([
        "--input", str(FIXTURE),
        "--out", str(source_out),
        "--target-component", "297",
        "--target-label", "B1",
        "--target-story", "+14.5",
        "--target-section", "B40x70",
    ]) == 0

    def fake_smoke_main(argv):
        out_dir = Path(argv[argv.index("--out") + 1])
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(source_out, out_dir)
        snapshot_path = out_dir / "feature_snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        material = next(item for item in snapshot["snapshots"] if item["component_type"] == "material")
        fck = material["features"]["concrete_fck_mpa"]
        fck["value"] = 42.0
        fck["evidence"][0]["normalized_value"] = 42.0
        material["evidence_by_feature"]["concrete_fck_mpa"][0]["normalized_value"] = 42.0
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        return 0

    monkeypatch.setattr(verifier.smoke, "main", fake_smoke_main)
    monkeypatch.setattr(verifier, "_etabs_model_state", lambda: {"available": True, "model_filename": "fixture.EDB", "model_locked": True})
    out = tmp_path / "live_smoke"
    rc = verifier.main(["--out", str(out)])
    assert rc == 0
    summary = json.loads((out / "p1_15_material_acceptance_summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "live_source_smoke"
    assert summary["strict_expected_enforced"] is False
    assert summary["observed"]["concrete_fck_mpa"] == 42.0
    assert summary["etabs_model_mutated"] is False


def test_strict_expected_rejects_live_value_drift(monkeypatch, tmp_path):
    source_out = tmp_path / "source"
    assert smoke.main([
        "--input", str(FIXTURE),
        "--out", str(source_out),
        "--target-component", "297",
        "--target-label", "B1",
        "--target-story", "+14.5",
        "--target-section", "B40x70",
    ]) == 0

    def fake_smoke_main(argv):
        out_dir = Path(argv[argv.index("--out") + 1])
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(source_out, out_dir)
        snapshot_path = out_dir / "feature_snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        material = next(item for item in snapshot["snapshots"] if item["component_type"] == "material")
        material["features"]["concrete_fck_mpa"]["value"] = 42.0
        material["features"]["concrete_fck_mpa"]["evidence"][0]["normalized_value"] = 42.0
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        return 0

    monkeypatch.setattr(verifier.smoke, "main", fake_smoke_main)
    monkeypatch.setattr(verifier, "_etabs_model_state", lambda: {"available": True, "model_filename": "fixture.EDB", "model_locked": True})
    with pytest.raises(AssertionError, match="concrete_fck_mpa"):
        verifier.main(["--out", str(tmp_path / "live_strict"), "--strict-expected"])


def test_material_evidence_contains_stable_source_reference_and_context():
    material = _material()
    for feature_name in (
        "component_section_name",
        "component_section_type",
        "section_concrete_material_name",
        "section_rebar_material_name",
        "concrete_fck_mpa",
        "rebar_fyk_mpa",
        "concrete_material_source_reference",
        "rebar_material_source_reference",
        "material_unit_basis",
    ):
        feature = material.features[feature_name]
        assert feature.status == FeatureValueStatus.RESOLVED
        evidence = feature.evidence[0]
        source_row = dict(evidence.source_row)
        assert source_row["source_reference"].startswith("LIVE_ETABS_DISPLAY_TABLE:")
        assert source_row["stable_row_reference"]
        assert source_row["complete_source_row"]
        assert source_row["selected_component_identity_context"]["selected_component"] == "297"
        assert source_row["selected_section_context"]["selected_section_name"] == "B40x70"
        assert source_row["selection_reason"]


def test_fck_fyk_normalization_is_deterministic_and_finite():
    material = _material()
    fck = material.features["concrete_fck_mpa"]
    fyk = material.features["rebar_fyk_mpa"]
    assert fck.value == 30.0
    assert fck.evidence[0].raw_value == 30000
    assert fck.evidence[0].normalized_value == 30.0
    assert fyk.value == 500.0
    assert fyk.evidence[0].raw_value == 500000
    assert fyk.evidence[0].normalized_value == 500.0
    assert math.isfinite(fck.value)
    assert math.isfinite(fyk.value)


def test_missing_material_source_fails_closed_with_explicit_reason():
    payload = _payload()
    payload["tables"] = [item for item in payload["tables"] if item["canonical_table_key"] != "material_concrete_data"]
    material = _material(payload)
    fck = material.features["concrete_fck_mpa"]
    ref = material.features["concrete_material_source_reference"]
    assert fck.status == FeatureValueStatus.PARTIAL
    assert fck.evidence[0].reason
    assert any(d.code.value in {"TABLE_MISSING", "MATERIAL_SOURCE_INCOMPLETE"} for d in fck.diagnostics)
    assert ref.status == FeatureValueStatus.PARTIAL
    assert ref.evidence[0].reason


def test_nonfinite_material_strength_fails_closed():
    payload = _payload()
    concrete = next(item for item in payload["tables"] if item["canonical_table_key"] == "material_concrete_data")
    concrete["rows"][0]["Fc"] = "NaN"
    material = _material(payload)
    fck = material.features["concrete_fck_mpa"]
    assert fck.status == FeatureValueStatus.PARTIAL
    assert any(d.code.value == "MATERIAL_VALUE_INVALID" for d in fck.diagnostics)


def test_no_check_result_or_engineering_verdict_emitted(tmp_path):
    out = tmp_path / "fixture_acceptance"
    verifier.main(["--input", str(FIXTURE), "--out", str(out)])
    snapshot = json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["metadata"]["check_engine_executed"] is False
    assert snapshot["metadata"]["check_result_emitted"] is False
    assert snapshot["metadata"]["live_verdict_emitted"] is False
    assert not (out / "check_results.json").exists()


def test_model_mutation_invariant_is_preserved_in_live_mode(monkeypatch, tmp_path):
    source_out = tmp_path / "source"
    assert smoke.main([
        "--input", str(FIXTURE),
        "--out", str(source_out),
        "--target-component", "297",
        "--target-label", "B1",
        "--target-story", "+14.5",
        "--target-section", "B40x70",
    ]) == 0

    def fake_smoke_main(argv):
        out_dir = Path(argv[argv.index("--out") + 1])
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(source_out, out_dir)
        return 0

    states = [
        {"available": True, "model_filename": "C:/tmp/B-BLOK_Revised.EDB", "model_locked": True},
        {"available": True, "model_filename": "C:/tmp/B-BLOK_Revised.EDB", "model_locked": True},
    ]
    monkeypatch.setattr(verifier.smoke, "main", fake_smoke_main)
    monkeypatch.setattr(verifier, "_etabs_model_state", lambda: states.pop(0))
    verifier.main(["--out", str(tmp_path / "live_acceptance")])
    assert states == []


def test_no_live_etabs_cli_flag_is_exposed_on_p1_15_verifier():
    parser = verifier._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--live-etabs"])
