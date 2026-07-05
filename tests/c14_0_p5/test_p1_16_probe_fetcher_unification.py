from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.features import source_tables
from tbdy_engine.features.resolver.live_smoke import C8LiveFeatureResolverSmoke, tables_from_probe_report, unit_context_from_payload
from tbdy_engine.features.value import FeatureValueStatus

P1_14_FIXTURE = Path("tests/fixtures/p1_14_story_base_complete_population.json")
P1_15_FIXTURE = Path("tests/fixtures/p1_15_material_design_basis_complete_population.json")


def _payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolver(path: Path, *, preferred_output_case: str = "Crack_SeisY_UpSoil") -> C8LiveFeatureResolverSmoke:
    payload = _payload(path)
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


def test_shared_source_reference_builder_is_deterministic_for_same_table_and_row():
    resolver = _resolver(P1_14_FIXTURE, preferred_output_case="Crack_SeisX_UpSoil")
    table = resolver._table("story_drifts")
    row = table.rows[3]

    first = source_tables.stable_row_reference("story_drifts", table, row)
    second = source_tables.stable_row_reference("story_drifts", table, dict(row))

    assert first == second == "story_drifts|actual=Story Drifts|row_index=3"


def test_table_fetch_evidence_shape_is_stable_for_complete_story_table():
    resolver = _resolver(P1_14_FIXTURE, preferred_output_case="Crack_SeisX_UpSoil")
    table = resolver._table("base_reactions")
    evidence = source_tables.table_fetch_evidence("base_reactions", table)

    assert evidence == {
        "table_key": "base_reactions",
        "actual_table_name": "Base Reactions",
        "source_kind": "C8_1_PROBE_FIXTURE",
        "columns": list(table.columns),
        "row_count": 4,
        "reported_row_count": 4,
        "parser_status": "UNKNOWN",
        "raw_table_diagnostics": source_tables.raw_table_diagnostics_from_table(table),
    }


def test_story_base_evidence_uses_shared_source_row_shape():
    resolver = _resolver(P1_14_FIXTURE, preferred_output_case="Crack_SeisY_UpSoil")
    story = resolver.build_story_snapshot()
    feature = story.features["story_drift_value"]

    assert feature.status == FeatureValueStatus.RESOLVED
    source_row = dict(feature.evidence[0].source_row)
    assert source_row["actual_table_name"] == "Story Drifts"
    assert source_row["source_kind"] == "C8_1_PROBE_FIXTURE"
    assert source_row["source_table"] == "story_drifts"
    assert source_row["stable_row_reference"] == "story_drifts|actual=Story Drifts|row_index=1"
    assert source_row["output_case"] == "Crack_SeisY_UpSoil"
    assert source_row["story"] == "+14.5"
    assert source_row["direction"] in {"X", "Y"}
    assert source_row["resolver_row_count"] == 4
    assert source_row["reported_row_count"] == 4
    assert source_row["complete_source_row"]["Drift"] == "0.000534"


def test_material_source_evidence_uses_shared_source_row_shape():
    resolver = _resolver(P1_15_FIXTURE)
    material = resolver.build_material_snapshot()
    feature = material.features["concrete_fck_mpa"]

    assert feature.status == FeatureValueStatus.RESOLVED
    source_row = dict(feature.evidence[0].source_row)
    assert source_row["actual_table_name"] == "Material Properties - Concrete Data"
    assert source_row["source_kind"] == "C8_1_PROBE_FIXTURE"
    assert source_row["source_table"] == "material_concrete_data"
    assert source_row["source_reference"].startswith("LIVE_ETABS_DISPLAY_TABLE:Material Properties - Concrete Data:row=0")
    assert source_row["stable_row_reference"] == {
        "table_key": "material_concrete_data",
        "actual_table_name": "Material Properties - Concrete Data",
        "row_index": 0,
        "material": "C30/37",
    }
    assert source_row["selected_component_identity_context"]["selected_component"] == "297"
    assert source_row["selected_section_context"]["selected_section_name"] == "B40x70"
    assert source_row["complete_source_row"]["Material"] == "C30/37"


def test_fixture_replay_paths_do_not_require_live_etabs():
    story_resolver = _resolver(P1_14_FIXTURE, preferred_output_case="Crack_SeisX_UpSoil")
    material_resolver = _resolver(P1_15_FIXTURE)

    assert story_resolver.build_story_snapshot().features["story_torsion_a1_coefficient"].status == FeatureValueStatus.RESOLVED
    assert story_resolver.build_global_snapshot().features["base_reaction_fx"].status == FeatureValueStatus.RESOLVED
    assert material_resolver.build_material_snapshot().features["concrete_fck_mpa"].status == FeatureValueStatus.RESOLVED


def test_unified_evidence_does_not_introduce_checkresult_or_engineering_verdict_fields():
    payloads = []
    story = _resolver(P1_14_FIXTURE, preferred_output_case="Crack_SeisX_UpSoil").build_all()
    material = _resolver(P1_15_FIXTURE).build_all()
    payloads.extend([story.feature_resolution_report, story.evidence_report, material.feature_resolution_report, material.evidence_report])
    from tbdy_engine.json_safe import to_jsonable
    text = json.dumps(to_jsonable(payloads), sort_keys=True)

    assert "CheckResult" not in text
    assert "engineering_verdict" not in text
    assert "pass_rule" not in text
    assert "utilization" not in text
