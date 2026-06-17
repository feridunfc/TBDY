from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from tbdy_engine.features.readiness import FORBIDDEN_ENGINEERING_VERDICT_TOKENS
from tbdy_engine.features.source_feature_snapshot_builder import (
    blocked_check_guardrail_report,
    build_c13_3_p0_feature_snapshot,
    fixture_source_rows,
    unit_normalization_report,
)
from tools.smoke_c13_3_p0_live_feature_snapshot import _parse_table_result

ROOT = Path(__file__).resolve().parents[2]
LOCKED_IDS = {
    "material_compliance_locked",
    "story_drift_torsion_force_locked",
    "pier_wall_force_capacity_detailing_locked",
}


def snapshot():
    return build_c13_3_p0_feature_snapshot(
        fixture_source_rows(),
        live_etabs_connected=False,
        generated_at="2026-06-17T00:00:00+00:00",
    )


def records_by_id(payload):
    return {record["feature_id"]: record for record in payload["feature_records"]}


def real_records(payload):
    return [record for record in payload["feature_records"] if record["feature_id"] not in LOCKED_IDS]


def test_feature_snapshot_root_keeps_check_unlocks_false():
    payload = snapshot()
    assert payload["sprint"] == "C13.3-P0"
    assert payload["source_contract_baseline"] == "c13.2-p5-contract-closure-source-feature-readiness"
    assert payload["safe_to_implement_checks_now"] is False
    assert payload["check_unlock_allowed"] is False
    assert payload["unit_policy_closed"] is True


def test_fixture_snapshot_is_not_guardrail_only():
    payload = snapshot()
    assert len(payload["feature_records"]) > len(LOCKED_IDS)
    assert real_records(payload)


def test_fixture_snapshot_includes_real_material_story_and_pier_records():
    payload = snapshot()
    for family in {"material_properties", "story_definitions", "pier_section_properties"}:
        matches = [
            record for record in real_records(payload)
            if record["source_family"] == family and record["raw_value"] not in (None, "")
        ]
        assert matches, family
        assert any(record["feature_status"] in {"RESOLVED", "PARTIAL"} for record in matches)


def test_every_feature_record_keeps_check_guardrails_false():
    for record in snapshot()["feature_records"]:
        assert record["check_unlock_allowed"] is False
        assert record["safe_to_use_for_check"] is False
        assert record["semantic_guardrails"]["check_unlock_allowed"] is False
        assert record["semantic_guardrails"]["safe_to_use_for_check"] is False


def test_numeric_features_have_raw_and_normalized_unit_metadata():
    numeric = [record for record in snapshot()["feature_records"] if isinstance(record["raw_value"], (int, float))]
    assert numeric
    for record in numeric:
        assert record["raw_unit"]
        assert record["normalized_unit"]
        assert record["quantity_kind"]
        assert record["conversion_provenance"]
        assert record["conversion_provenance"]["source_unit_policy"] == "ETABS_LIVE_MODEL_CONTEXT_RAW_UNCONVERTED"
        assert record["conversion_provenance"]["silent_source_contract_conversion"] is False
        assert "normalization_rule" in record["conversion_provenance"]
        assert "factor" in record["conversion_provenance"]
        assert record["conversion_provenance"]["check_engine_unlock"] is False


def test_unit_normalization_report_counts_numeric_fixture_features():
    report = unit_normalization_report(snapshot())
    assert report["numeric_feature_count"] > 0
    assert report["all_numeric_have_units"] is True
    assert report["all_numeric_have_quantity_kind"] is True
    assert report["all_numeric_have_conversion_provenance"] is True
    assert report["raw_values_preserved"] is True


def test_raw_values_are_not_overwritten_by_normalized_values():
    for record in snapshot()["feature_records"]:
        assert record["evidence"]["raw_value"] == record["raw_value"]
        assert "normalized_value" in record
        assert "raw_value" in record


def test_story_elevation_is_derived_not_direct():
    derived = [record for record in snapshot()["feature_records"] if record["feature_name"] == "story_derived_elevation"]
    assert derived
    for record in derived:
        assert record["derived"] is True
        policy = record["derivation_policy"]
        assert policy["derived_elevation_supported"] is True
        assert policy["elevation_is_direct_column"] is False
        assert policy["base_elevation_column"] == "BSElev"
        assert record["readiness_status"] == "READY_DERIVED_SOURCE"


def test_pier_geometry_does_not_require_literal_section_column():
    pier_width = records_by_id(snapshot())["pier_width::+3.0:P1"]
    guard = pier_width["semantic_guardrails"]
    assert guard["direct_section_geometry_present"] is True
    assert guard["section_name_column_required"] is False
    assert guard["section_name_column_present"] is False
    assert guard["material_present"] is True


def test_locked_guardrail_records_remain():
    ids = set(records_by_id(snapshot()))
    assert LOCKED_IDS.issubset(ids)
    report = blocked_check_guardrail_report(snapshot())
    assert report["blocked_or_locked_record_count"] == 3
    assert report["engineering_verdicts_emitted"] is False


def test_material_compliance_remains_locked():
    locked = records_by_id(snapshot())["material_compliance_locked"]
    assert locked["feature_status"] == "LOCKED_CHECK_NOT_ALLOWED"
    assert locked["readiness_status"] == "LOCKED_CHECK_NOT_ALLOWED"
    assert locked["check_unlock_allowed"] is False


def test_drift_torsion_story_force_concepts_remain_locked_or_semantic_review():
    record = records_by_id(snapshot())["story_drift_torsion_force_locked"]
    assert record["feature_status"] in {"LOCKED_CHECK_NOT_ALLOWED", "BLOCKED_SEMANTIC_REVIEW"}
    assert record["readiness_status"] in {"LOCKED_CHECK_NOT_ALLOWED", "BLOCKED_SEMANTIC_REVIEW"}


def test_pier_wall_force_capacity_detailing_remains_locked_or_semantic_review():
    record = records_by_id(snapshot())["pier_wall_force_capacity_detailing_locked"]
    assert record["feature_status"] in {"LOCKED_CHECK_NOT_ALLOWED", "BLOCKED_SEMANTIC_REVIEW"}
    assert record["readiness_status"] in {"LOCKED_CHECK_NOT_ALLOWED", "BLOCKED_SEMANTIC_REVIEW"}


def test_table_parser_handles_flat_all_string_etabs_table_data():
    result = (0, 2, ["Material", "E1", "G12"], ["C30", "32000", "13333", "B420C", "200000", "76923"])
    rows, columns = _parse_table_result(result, max_rows=25)
    assert columns == ["Material", "E1", "G12"]
    assert rows == [
        {"Material": "C30", "E1": "32000", "G12": "13333"},
        {"Material": "B420C", "E1": "200000", "G12": "76923"},
    ]


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_no_check_engine_imports_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/source_feature_snapshot_builder.py",
        ROOT / "tools/smoke_c13_3_p0_live_feature_snapshot.py",
    ]
    for path in touched:
        assert "tbdy_engine.checks.engine" not in _imports_for(path)


def test_no_report_renderer_imports_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/source_feature_snapshot_builder.py",
        ROOT / "tools/smoke_c13_3_p0_live_feature_snapshot.py",
    ]
    forbidden = {"tbdy_engine.reporting", "tbdy_engine.report", "report_renderer"}
    for path in touched:
        assert not forbidden.intersection(_imports_for(path))


def test_no_excel_production_path_is_introduced():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "tbdy_engine/features/source_feature_snapshot_builder.py",
            ROOT / "tools/smoke_c13_3_p0_live_feature_snapshot.py",
        ]
    ).casefold()
    assert "read_excel" not in text
    assert "openpyxl" not in text
    assert "excel_production_input: true" not in text


def test_unsupported_or_out_of_scope_rows_do_not_become_engineering_failures():
    statuses = {record["feature_status"] for record in snapshot()["feature_records"]}
    assert "FAIL" not in statuses
    assert "CHECK_FAIL" not in statuses


def test_no_engineering_verdict_strings_appear_in_feature_snapshot_outputs():
    text = json.dumps(snapshot(), sort_keys=True)
    for token in FORBIDDEN_ENGINEERING_VERDICT_TOKENS:
        assert token not in text


def test_live_smoke_tool_no_live_mode_does_not_fake_values(tmp_path):
    out = tmp_path / "c13_3_p0"
    result = subprocess.run(
        [sys.executable, "tools/smoke_c13_3_p0_live_feature_snapshot.py", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    connection = json.loads((out / "connection_report.json").read_text(encoding="utf-8"))
    assert connection["live_etabs_requested"] is False
    assert connection["live_etabs_connected"] is False
    assert connection["feature_values_faked"] is False
    payload = json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert payload["live_etabs_connected"] is False
    assert payload["check_unlock_allowed"] is False
    assert payload["safe_to_implement_checks_now"] is False
    assert not [
        record for record in payload["feature_records"]
        if record["source_family"] in {"material_properties", "story_definitions", "pier_section_properties"}
        and record["feature_status"] == "RESOLVED"
    ]
    debug = json.loads((out / "source_table_projection_debug_report.json").read_text(encoding="utf-8"))
    assert debug["source_tables"] == []
    assert debug["check_unlock_allowed"] is False


def test_feature_status_counts_are_deterministic_in_fixture_mode():
    first = snapshot()["feature_status_counts"]
    second = snapshot()["feature_status_counts"]
    assert first == second
    assert first["RESOLVED"] > 0
    assert first["LOCKED_CHECK_NOT_ALLOWED"] == 1
    assert first["BLOCKED_SEMANTIC_REVIEW"] == 2
