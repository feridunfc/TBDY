from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import pytest

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features.resolver.live_smoke import (
    C8LiveFeatureResolverSmoke,
    tables_from_probe_report,
    unit_context_from_payload,
    write_smoke_outputs,
)
from tbdy_engine.features.value import FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]
COMPLETE_FIXTURE = ROOT / "tests" / "fixtures" / "p1_14_story_base_complete_population.json"
HISTORICAL_SAMPLE_FIXTURE = ROOT / "tests" / "fixtures" / "c8_table_headers_fixture.json"


def _payload() -> dict[str, Any]:
    return json.loads(COMPLETE_FIXTURE.read_text(encoding="utf-8"))


def _resolver(payload: Mapping[str, Any] | None = None, *, preferred_output_case: str = "Crack_SeisX_UpSoil") -> C8LiveFeatureResolverSmoke:
    payload = dict(_payload() if payload is None else payload)
    bundle = load_contracts()
    return C8LiveFeatureResolverSmoke(
        bundle,
        tables_from_probe_report(payload, bundle),
        unit_context=unit_context_from_payload(payload),
        target_component="297",
        target_label="B1",
        target_story="+14.5",
        target_section="B40x70",
        preferred_output_case=preferred_output_case,
    )


def _feature(resolver: C8LiveFeatureResolverSmoke, component: str, feature_name: str):
    if component == "story":
        return resolver.build_story_snapshot().features[feature_name]
    if component == "global":
        return resolver.build_global_snapshot().features[feature_name]
    raise AssertionError(component)


def _codes(feature) -> set[str]:
    return {diagnostic.code.value for diagnostic in feature.diagnostics}


def test_story_base_source_tables_index_under_canonical_observed_and_legacy_names():
    resolver = _resolver()

    assert resolver._table("Story Drifts") is resolver._table("story_drifts")
    assert resolver._table("Story Max Over Avg Drifts") is resolver._table("story_max_over_avg_drifts")
    assert resolver._table("Base Reactions") is resolver._table("base_reactions")

    assert resolver._table("Frame Assignments - Summary") is resolver._table("frame_assignments_summary")
    assert resolver._table("frame_assignments_summary") is resolver._table("frame_assignments")
    assert resolver._table("Frame Section Property Definitions - Concrete Rectangular") is resolver._table("concrete_rectangular_frame_sections")
    assert resolver._table("concrete_rectangular_frame_sections") is resolver._table("frame_section_properties")


def test_story_drift_resolves_from_complete_population_not_sample_rows():
    resolver = _resolver(preferred_output_case="Crack_SeisX_UpSoil")
    feature = _feature(resolver, "story", "story_drift_value")

    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.value == pytest.approx(1.125)
    evidence = feature.evidence[0]
    assert evidence.actual_table_name == "Story Drifts"
    assert evidence.source_column == "Drift"
    assert evidence.output_case == "Crack_SeisX_UpSoil"
    assert evidence.source_row["row_index"] == 3
    assert evidence.source_row["reported_row_count"] == 4
    assert evidence.source_row["resolver_row_count"] == 4
    assert evidence.source_row["source_row_storage_field_used"] == "rows"
    assert evidence.source_row["complete_source_row"]["Drift"] == "0.001125"
    assert evidence.source_row["selection_reason"] == "target_story_and_preferred_output_case_match_with_required_columns"


def test_story_torsion_resolves_from_complete_population_not_sample_rows():
    resolver = _resolver(preferred_output_case="Crack_SeisY_UpSoil")
    feature = _feature(resolver, "story", "story_torsion_a1_coefficient")

    assert feature.status == FeatureValueStatus.RESOLVED
    assert feature.value == pytest.approx(1.157)
    evidence = feature.evidence[0]
    assert evidence.actual_table_name == "Story Max Over Avg Drifts"
    assert evidence.source_column == "Ratio"
    assert evidence.output_case == "Crack_SeisY_UpSoil"
    assert evidence.source_row["row_index"] == 1
    assert evidence.source_row["complete_source_row"]["Ratio"] == "1.157"


def test_base_reactions_resolve_from_complete_population_not_sample_rows():
    resolver = _resolver(preferred_output_case="Crack_SeisX_UpSoil")
    fx = _feature(resolver, "global", "base_reaction_fx")
    fy = _feature(resolver, "global", "base_reaction_fy")

    assert fx.status == FeatureValueStatus.RESOLVED
    assert fy.status == FeatureValueStatus.RESOLVED
    assert fx.value == pytest.approx(20396.1433)
    assert fy.value == pytest.approx(5360.3225)
    assert fx.evidence[0].source_row["row_index"] == 2
    assert fx.evidence[0].source_row["complete_source_row"]["FX"] == "20396.1433"
    assert fy.evidence[0].source_row["complete_source_row"]["FY"] == "5360.3225"


def test_preferred_output_case_is_preserved_in_every_story_base_evidence_row():
    resolver = _resolver(preferred_output_case="Crack_SeisY_UpSoil")
    story = resolver.build_story_snapshot()
    global_snapshot = resolver.build_global_snapshot()
    feature_names = (
        story.features["story_drift_value"],
        story.features["story_drift_output_case"],
        story.features["story_drift_direction"],
        story.features["story_torsion_a1_coefficient"],
        global_snapshot.features["base_reaction_fx"],
        global_snapshot.features["base_reaction_fy"],
        global_snapshot.features["base_reaction_x_kN"],
        global_snapshot.features["base_reaction_y_kN"],
    )
    for feature in feature_names:
        assert feature.status == FeatureValueStatus.RESOLVED
        evidence = feature.evidence[0]
        assert evidence.output_case == "Crack_SeisY_UpSoil"
        assert evidence.source_row["output_case"] == "Crack_SeisY_UpSoil"
        assert evidence.source_row["preferred_output_case"] == "Crack_SeisY_UpSoil"


def test_unavailable_preferred_output_case_fails_closed_without_fallback():
    resolver = _resolver(preferred_output_case="Missing_Case")
    story_feature = _feature(resolver, "story", "story_drift_value")
    torsion_feature = _feature(resolver, "story", "story_torsion_a1_coefficient")
    base_feature = _feature(resolver, "global", "base_reaction_fx")

    for feature in (story_feature, torsion_feature, base_feature):
        assert feature.status == FeatureValueStatus.PARTIAL
        assert feature.value is None
        assert "STORY_BASE_OUTPUT_CASE_UNAVAILABLE" in _codes(feature)


def test_row_count_mismatch_fails_closed_for_story_base_sources():
    payload = _payload()
    for table in payload["tables"]:
        if table["actual_table_name"] in {"Story Drifts", "Story Max Over Avg Drifts", "Base Reactions"}:
            table["row_count_reported"] = len(table["rows"]) + 1
    resolver = _resolver(payload, preferred_output_case="Crack_SeisX_UpSoil")

    for component, feature_name in (
        ("story", "story_drift_value"),
        ("story", "story_torsion_a1_coefficient"),
        ("global", "base_reaction_fx"),
    ):
        feature = _feature(resolver, component, feature_name)
        assert feature.status == FeatureValueStatus.PARTIAL
        assert "STORY_BASE_SOURCE_INCOMPLETE" in _codes(feature)


def test_malformed_story_base_source_values_fail_closed():
    payload = _payload()
    for table in payload["tables"]:
        if table["actual_table_name"] == "Story Drifts":
            table["rows"][0]["Drift"] = "not_numeric"
        if table["actual_table_name"] == "Story Max Over Avg Drifts":
            table["rows"][0]["Ratio"] = "nan"
        if table["actual_table_name"] == "Base Reactions":
            table["rows"][0]["FY"] = "inf"
    resolver = _resolver(payload, preferred_output_case="Crack_SeisX_UpSoil")

    assert "STORY_BASE_VALUE_INVALID" in _codes(_feature(resolver, "story", "story_drift_value"))
    assert "STORY_BASE_VALUE_INVALID" in _codes(_feature(resolver, "story", "story_torsion_a1_coefficient"))
    assert "STORY_BASE_VALUE_INVALID" in _codes(_feature(resolver, "global", "base_reaction_fx"))


def test_sample_only_story_base_sources_fail_closed():
    payload = json.loads(HISTORICAL_SAMPLE_FIXTURE.read_text(encoding="utf-8"))
    resolver = _resolver(payload, preferred_output_case="Crack_SeisY_UpSoil")
    story = resolver.build_story_snapshot()
    global_snapshot = resolver.build_global_snapshot()

    for feature in (
        story.features["story_drift_value"],
        story.features["story_torsion_a1_coefficient"],
        global_snapshot.features["base_reaction_fx"],
        global_snapshot.features["base_reaction_fy"],
    ):
        assert feature.status == FeatureValueStatus.PARTIAL
        assert feature.value is None
        assert "STORY_BASE_SOURCE_INCOMPLETE" in _codes(feature)


def test_product_source_tables_include_story_base_without_table_missing(tmp_path):
    resolver = _resolver(preferred_output_case="Crack_SeisX_UpSoil")
    outputs = resolver.build_all()
    report = outputs.product_report_source_tables

    for key, actual in {
        "story_drifts": "Story Drifts",
        "story_max_over_avg_drifts": "Story Max Over Avg Drifts",
        "base_reactions": "Base Reactions",
        "frame_assignments": "Frame Assignments - Summary",
        "frame_section_properties": "Frame Section Property Definitions - Concrete Rectangular",
    }.items():
        table = report["tables"][key]
        assert table["actual_table_name"] == actual
        assert table["row_count"] > 0
        assert table["raw_table_diagnostics"]["parser_status"] != "TABLE_MISSING"

    write_smoke_outputs(tmp_path, outputs)
    written = json.loads((tmp_path / "product_report_source_tables.json").read_text(encoding="utf-8"))
    assert "story_drifts" in written["tables"]
    assert written["tables"]["base_reactions"]["row_count"] == 4


def test_no_checkresult_or_engineering_verdict_is_emitted_for_story_base_source_resolution(tmp_path):
    outputs = _resolver().build_all()
    write_smoke_outputs(tmp_path, outputs)

    snapshot = json.loads((tmp_path / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["metadata"]["check_engine_executed"] is False
    assert snapshot["metadata"]["check_result_emitted"] is False
    assert snapshot["metadata"]["live_verdict_emitted"] is False
    assert not (tmp_path / "check_results.json").exists()
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "CheckResult" not in text
        assert '"engineering_verdict"' not in text


def test_complete_fixture_identity_states_it_is_not_full_live_evidence():
    payload = _payload()
    metadata = payload["metadata"]
    assert metadata["complete_fixture_population"] is True
    assert metadata["not_full_live_etabs_population"] is True


def _acceptance_feature(value: float, case_name: str, source_column: str) -> dict[str, Any]:
    return {
        "status": "RESOLVED",
        "value": value,
        "evidence": [
            {
                "output_case": case_name,
                "source_column": source_column,
                "source_row": {
                    "row_index": 1,
                    "reported_row_count": 16,
                    "resolver_row_count": 16,
                    "selection_reason": "target_story_and_preferred_output_case_match_with_required_columns",
                    "complete_source_row": {"OutputCase": case_name, source_column: str(value)},
                },
            }
        ],
    }


def _write_acceptance_snapshot(out_dir: Path, case_name: str, *, y_story_drift_value: float) -> None:
    story_drift = 1.125 if case_name == "Crack_SeisX_UpSoil" else y_story_drift_value
    torsion = 1.069 if case_name == "Crack_SeisX_UpSoil" else 1.157
    fx = 20396.1433 if case_name == "Crack_SeisX_UpSoil" else 12979.0527
    fy = 5360.3225 if case_name == "Crack_SeisX_UpSoil" else 12890.0006
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
        },
        "snapshots": [
            {
                "component_type": "story",
                "features": {
                    "story_drift_value": _acceptance_feature(story_drift, case_name, "Drift"),
                    "story_torsion_a1_coefficient": _acceptance_feature(torsion, case_name, "Ratio"),
                },
            },
            {
                "component_type": "global",
                "features": {
                    "base_reaction_fx": _acceptance_feature(fx, case_name, "FX"),
                    "base_reaction_fy": _acceptance_feature(fy, case_name, "FY"),
                },
            },
        ],
    }
    (out_dir / "feature_snapshot.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _patch_acceptance_smoke(monkeypatch: pytest.MonkeyPatch, *, y_story_drift_value: float) -> list[list[str]]:
    from tools import verify_p1_14_story_base_live_acceptance as verifier

    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(list(argv))
        out_dir = Path(argv[argv.index("--out") + 1])
        case_name = argv[argv.index("--preferred-output-case") + 1]
        _write_acceptance_snapshot(out_dir, case_name, y_story_drift_value=y_story_drift_value)
        return 0

    monkeypatch.setattr(verifier.smoke, "main", fake_main)
    monkeypatch.setattr(
        verifier,
        "_etabs_model_state",
        lambda: {"available": True, "model_filename": r"C:\tmp\B-BLOK_Revised.EDB", "model_locked": True},
    )
    return calls


def test_acceptance_cli_fixture_mode_enforces_immutable_expected_values(tmp_path, monkeypatch):
    from tools import verify_p1_14_story_base_live_acceptance as verifier

    _patch_acceptance_smoke(monkeypatch, y_story_drift_value=1.629)
    with pytest.raises(AssertionError, match="Crack_SeisY_UpSoil.story_drift_value"):
        verifier.main(["--input", str(COMPLETE_FIXTURE), "--out", str(tmp_path)])


def test_acceptance_cli_live_mode_allows_current_traceable_values_without_strict_expected(tmp_path, monkeypatch):
    from tools import verify_p1_14_story_base_live_acceptance as verifier

    calls = _patch_acceptance_smoke(monkeypatch, y_story_drift_value=1.629)
    assert verifier.main(["--out", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "p1_14_live_story_base_acceptance_summary.json").read_text(encoding="utf-8"))

    assert summary["mode"] == "live_source_evidence_smoke"
    assert summary["strict_expected_enforced"] is False
    assert summary["results"]["Crack_SeisY_UpSoil"]["story_drift_value"] == pytest.approx(1.629)
    assert summary["check_result_emitted"] is False
    assert summary["engineering_verdict_emitted"] is False
    assert summary["etabs_model_mutated"] is False
    assert calls
    assert all("--live-etabs" in call for call in calls)
    assert all("--input" not in call for call in calls)


def test_acceptance_cli_strict_expected_rejects_live_value_mismatch(tmp_path, monkeypatch):
    from tools import verify_p1_14_story_base_live_acceptance as verifier

    _patch_acceptance_smoke(monkeypatch, y_story_drift_value=1.629)
    with pytest.raises(AssertionError, match="expected 0.534, observed 1.629"):
        verifier.main(["--strict-expected", "--out", str(tmp_path)])


def test_acceptance_cli_expected_json_override_enforces_custom_live_values(tmp_path, monkeypatch):
    from tools import verify_p1_14_story_base_live_acceptance as verifier

    expected_json = tmp_path / "expected.json"
    expected_json.write_text(
        json.dumps(
            {
                "Crack_SeisY_UpSoil": {
                    "story_drift_value": 1.629,
                    "story_torsion_a1_coefficient": 1.157,
                    "base_reaction_fx": 12979.0527,
                    "base_reaction_fy": 12890.0006,
                }
            }
        ),
        encoding="utf-8",
    )
    _patch_acceptance_smoke(monkeypatch, y_story_drift_value=1.629)
    assert verifier.main(["--expected-json", str(expected_json), "--out", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "p1_14_live_story_base_acceptance_summary.json").read_text(encoding="utf-8"))
    assert summary["strict_expected_enforced"] is True
    assert tuple(summary["results"]) == ("Crack_SeisY_UpSoil",)


def test_acceptance_cli_does_not_document_or_accept_live_etabs_flag():
    from tools import verify_p1_14_story_base_live_acceptance as verifier

    help_text = verifier._build_parser().format_help()
    assert "--live-etabs" not in help_text
    with pytest.raises(SystemExit):
        verifier.main(["--live-etabs"])
