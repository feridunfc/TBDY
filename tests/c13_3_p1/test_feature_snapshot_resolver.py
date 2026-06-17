from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from tbdy_engine.features.readiness import FORBIDDEN_ENGINEERING_VERDICT_TOKENS
from tbdy_engine.features.resolver_feature_snapshot import (
    blocked_check_guardrail_report,
    build_feature_snapshot_from_source_rows,
    readiness_projection_report,
    source_family_projection_report,
    summarize_snapshot,
    unit_normalization_report,
)
from tbdy_engine.features.source_feature_snapshot_builder import INTERNAL_SOURCE_TABLE_KEY, fixture_source_rows
import tools.smoke_c13_3_p1_feature_snapshot_resolver as smoke

ROOT = Path(__file__).resolve().parents[2]
LOCKED_IDS = {
    "material_compliance_locked",
    "story_drift_torsion_force_locked",
    "pier_wall_force_capacity_detailing_locked",
}


def snapshot():
    return build_feature_snapshot_from_source_rows(
        fixture_source_rows(),
        live_etabs_connected=True,
        model_path="C:/tmp/B-BLOK_Revised.EDB",
        etabs_version="23.2.0",
        target_family="all",
        generated_at="2026-06-17T00:00:00+00:00",
    )


def records_by_id(payload):
    return {record["feature_id"]: record for record in payload["feature_records"]}


def real_records(payload):
    return [record for record in payload["feature_records"] if record["feature_id"] not in LOCKED_IDS]


def test_resolver_snapshot_root_contract_is_stable():
    payload = snapshot()
    assert payload["sprint"] == "C13.3-P1"
    assert payload["source_contract_baseline"] == "c13.2-p5-contract-closure-source-feature-readiness"
    assert payload["generated_at"] == "2026-06-17T00:00:00+00:00"
    assert payload["live_etabs_connected"] is True
    assert payload["model_path"] == "C:/tmp/B-BLOK_Revised.EDB"
    assert payload["etabs_version"] == "23.2.0"
    assert payload["target_family"] == "all"
    assert payload["feature_records"]
    assert payload["feature_status_counts"]
    assert payload["readiness_status_counts"]
    assert payload["source_family_counts"]
    assert payload["numeric_feature_count"] > 0
    assert payload["unit_policy_closed"] is True
    assert payload["raw_values_preserved"] is True
    assert payload["safe_to_implement_checks_now"] is False
    assert payload["check_unlock_allowed"] is False


def test_fixture_snapshot_is_not_guardrail_only_and_projects_all_target_families():
    payload = snapshot()
    assert len(payload["feature_records"]) > len(LOCKED_IDS)
    assert real_records(payload)
    for family in {"material_properties", "story_definitions", "pier_section_properties"}:
        assert any(record["source_family"] == family for record in real_records(payload)), family


def test_material_story_and_pier_rows_project_to_real_records():
    payload = snapshot()
    families = {record["source_family"] for record in real_records(payload)}
    assert {"material_properties", "story_definitions", "pier_section_properties"}.issubset(families)
    assert any(record["feature_name"] == "material_e1" for record in real_records(payload))
    assert any(record["feature_name"] == "story_height" for record in real_records(payload))
    assert any(record["feature_name"] == "pier_thickness" for record in real_records(payload))


def test_stable_feature_record_contract_fields_exist_on_every_record():
    required = {
        "feature_id",
        "feature_name",
        "component_type",
        "component_id",
        "source_family",
        "source_tables",
        "source_columns",
        "readiness_status",
        "feature_status",
        "raw_value",
        "raw_unit",
        "normalized_value",
        "normalized_unit",
        "quantity_kind",
        "conversion_provenance",
        "evidence",
        "semantic_guardrails",
        "derived",
        "safe_to_use_for_check",
        "check_unlock_allowed",
        "unit_policy",
    }
    for record in snapshot()["feature_records"]:
        assert required.issubset(record), record["feature_id"]
        assert record["safe_to_use_for_check"] is False
        assert record["check_unlock_allowed"] is False
        assert record["semantic_guardrails"]["safe_to_use_for_check"] is False
        assert record["semantic_guardrails"]["check_unlock_allowed"] is False


def test_story_derived_elevation_is_marked_derived_not_direct():
    derived = [record for record in snapshot()["feature_records"] if record["feature_name"] == "story_derived_elevation"]
    assert derived
    for record in derived:
        assert record["derived"] is True
        assert record["readiness_status"] == "READY_DERIVED_SOURCE"
        assert record["derivation_policy"]["derived_elevation_supported"] is True
        assert record["derivation_policy"]["elevation_is_direct_column"] is False


def test_numeric_records_keep_raw_and_normalized_unit_metadata():
    payload = snapshot()
    numeric = [record for record in payload["feature_records"] if isinstance(record["raw_value"], (int, float))]
    assert numeric
    for record in numeric:
        assert record["raw_unit"]
        assert record["normalized_unit"]
        assert record["quantity_kind"]
        assert record["conversion_provenance"]
        assert record["evidence"]["raw_value"] == record["raw_value"]
        assert record["conversion_provenance"]["silent_source_contract_conversion"] is False
        assert record["conversion_provenance"]["check_engine_unlock"] is False


def test_unit_normalization_report_proves_numeric_metadata_is_complete():
    report = unit_normalization_report(snapshot())
    assert report["numeric_feature_count"] > 0
    assert report["all_numeric_have_units"] is True
    assert report["all_numeric_have_quantity_kind"] is True
    assert report["all_numeric_have_conversion_provenance"] is True
    assert report["raw_values_preserved"] is True
    assert report["check_unlock_allowed"] is False


def test_locked_guardrail_records_remain_and_no_engineering_verdicts_are_emitted():
    payload = snapshot()
    ids = set(records_by_id(payload))
    assert LOCKED_IDS.issubset(ids)
    report = blocked_check_guardrail_report(payload)
    assert report["blocked_or_locked_record_count"] == 3
    assert report["engineering_verdicts_emitted"] is False
    assert report["check_unlock_allowed"] is False


def test_no_engineering_verdict_strings_appear_in_feature_snapshot_outputs():
    text = json.dumps(snapshot(), sort_keys=True)
    for token in FORBIDDEN_ENGINEERING_VERDICT_TOKENS:
        assert token not in text


def test_summary_reports_are_deterministic():
    payload = snapshot()
    reports_1 = (
        summarize_snapshot(payload),
        unit_normalization_report(payload),
        readiness_projection_report(payload),
        source_family_projection_report(payload),
        blocked_check_guardrail_report(payload),
    )
    reports_2 = (
        summarize_snapshot(payload),
        unit_normalization_report(payload),
        readiness_projection_report(payload),
        source_family_projection_report(payload),
        blocked_check_guardrail_report(payload),
    )
    assert reports_1 == reports_2
    assert reports_1[0]["feature_record_count"] == len(payload["feature_records"])
    assert reports_1[3]["source_family_counts"] == payload["source_family_counts"]


def test_source_family_projection_report_counts_families():
    report = source_family_projection_report(snapshot())
    assert {"material_properties", "story_definitions", "pier_section_properties"}.issubset(set(report["projected_families"]))
    assert report["families"]["material_properties"]["feature_record_count"] > 0
    assert report["families"]["story_definitions"]["feature_record_count"] > 0
    assert report["families"]["pier_section_properties"]["feature_record_count"] > 0
    assert report["check_unlock_allowed"] is False


def test_live_fetch_path_uses_shared_fetcher_shape_and_projects_rows(monkeypatch):
    parsed = SimpleNamespace(
        actual_table_name="Material Properties - Basic Mechanical Properties",
        fetch_status="SUCCEEDED",
        rows=[{"Material": "C30", "Type": "Concrete", "E1": "32000"}],
        field_keys=("Material", "Type", "E1"),
        row_count_reported=1,
        return_code=0,
        debug={"parse_strategy_used": "return_plus_mutated_args_sequence_scan"},
        diagnostics=({"severity": "INFO", "code": "DISPLAY_TABLE_SIGNATURE_SELECTED"},),
    )
    shared_result = SimpleNamespace(
        parsed=parsed,
        selected_signature={"signature_name": "sig_7_list_fields_records_data", "row_count": 1},
        selected_signature_reason="first_signature_with_parsed_rows",
        signature_attempts=(
            {"signature_name": "sig_7_list_fields_records_data", "parser_status": "PARSED_ROWS", "row_count": 1},
        ),
    )
    calls = []

    def fake_fetch_display_table(database_tables, table_name, *, max_rows=None):
        calls.append({"database_tables": database_tables, "table_name": table_name, "max_rows": max_rows})
        return shared_result

    monkeypatch.setattr(smoke, "fetch_display_table", fake_fetch_display_table)
    rows, columns, diagnostics = smoke._fetch_live_table(object(), "Material Properties - Basic Mechanical Properties", 25)

    assert calls and calls[0]["table_name"] == "Material Properties - Basic Mechanical Properties"
    assert calls[0]["max_rows"] == 25
    assert rows == [{"Material": "C30", "Type": "Concrete", "E1": "32000"}]
    assert columns == ["Material", "Type", "E1"]
    assert diagnostics["selected_signature"]["signature_name"] == "sig_7_list_fields_records_data"
    assert diagnostics["selected_signature_reason"] == "first_signature_with_parsed_rows"
    assert diagnostics["signature_attempts"][0]["parser_status"] == "PARSED_ROWS"
    assert diagnostics["parser_debug"]["parse_strategy_used"] == "return_plus_mutated_args_sequence_scan"

    stamped = [dict(row, **{INTERNAL_SOURCE_TABLE_KEY: "Material Properties - Basic Mechanical Properties"}) for row in rows]
    payload = build_feature_snapshot_from_source_rows(
        {"material_properties": stamped},
        live_etabs_connected=True,
        target_family="material_properties",
        generated_at="2026-06-17T00:00:00+00:00",
    )
    report = smoke.source_table_projection_debug_report(
        generated_at="2026-06-17T00:00:00+00:00",
        debug_tables=[
            {
                "table_name": "Material Properties - Basic Mechanical Properties",
                "source_family": "material_properties",
                "fetch_status": "FETCHED",
                "row_count": 1,
                "columns": columns,
                "sample_rows": rows,
                "projected_feature_count": 0,
                "projection_status": "NOT_PROJECTED",
                "projection_blocker": None,
                "selected_signature": diagnostics["selected_signature"],
                "selected_signature_reason": diagnostics["selected_signature_reason"],
                "signature_attempts": diagnostics["signature_attempts"],
                "parser_debug": diagnostics["parser_debug"],
                "parser_diagnostics": diagnostics["parser_diagnostics"],
            }
        ],
        snapshot=payload,
    )
    table = report["source_tables"][0]
    assert table["projected_feature_count"] > 0
    assert table["projection_status"] == "PROJECTED"
    assert payload["feature_status_counts"]["RESOLVED"] > 0
    assert unit_normalization_report(payload)["numeric_feature_count"] > 0


def test_live_smoke_tool_no_live_mode_exits_2_and_does_not_fake_values(tmp_path):
    out = tmp_path / "c13_3_p1"
    result = subprocess.run(
        [sys.executable, "tools/smoke_c13_3_p1_feature_snapshot_resolver.py", "--out", str(out)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    expected = {
        "connection_report.json",
        "feature_snapshot.json",
        "feature_snapshot_summary.json",
        "unit_normalization_report.json",
        "readiness_projection_report.json",
        "blocked_check_guardrail_report.json",
        "source_family_projection_report.json",
        "source_table_projection_debug_report.json",
    }
    assert expected == {path.name for path in out.iterdir()}
    connection = json.loads((out / "connection_report.json").read_text(encoding="utf-8"))
    assert connection["connection_status"] == "NO_LIVE_REQUESTED"
    assert connection["live_etabs_connected"] is False
    assert connection["feature_values_faked"] is False
    payload = json.loads((out / "feature_snapshot.json").read_text(encoding="utf-8"))
    assert payload["sprint"] == "C13.3-P1"
    assert payload["live_etabs_connected"] is False
    assert payload["check_unlock_allowed"] is False
    assert payload["safe_to_implement_checks_now"] is False
    debug = json.loads((out / "source_table_projection_debug_report.json").read_text(encoding="utf-8"))
    assert debug["source_tables"] == []
    assert debug["check_unlock_allowed"] is False


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
        ROOT / "tbdy_engine/features/resolver_feature_snapshot.py",
        ROOT / "tools/smoke_c13_3_p1_feature_snapshot_resolver.py",
    ]
    for path in touched:
        assert "tbdy_engine.checks.engine" not in _imports_for(path)


def test_no_report_renderer_imports_are_introduced():
    touched = [
        ROOT / "tbdy_engine/features/resolver_feature_snapshot.py",
        ROOT / "tools/smoke_c13_3_p1_feature_snapshot_resolver.py",
    ]
    forbidden = {"tbdy_engine.reporting", "tbdy_engine.report", "report_renderer"}
    for path in touched:
        assert not forbidden.intersection(_imports_for(path))


def test_no_excel_production_path_is_introduced():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "tbdy_engine/features/resolver_feature_snapshot.py",
            ROOT / "tools/smoke_c13_3_p1_feature_snapshot_resolver.py",
        ]
    ).casefold()
    assert "read_excel" not in text
    assert "openpyxl" not in text
    assert "excel_production_input: true" not in text
