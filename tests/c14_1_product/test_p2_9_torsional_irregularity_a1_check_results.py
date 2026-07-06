from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import tools.run_live_model_product_report as product_cli

FIXTURE = Path("tests/fixtures/p2_3_scope_material_combined_verdict_fixture.json")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run(tmp_path: Path, fixture: Path = FIXTURE) -> Path:
    out = tmp_path / "out"
    assert product_cli.main(["--input", str(fixture), "--out", str(out)]) == 0
    return out


def _write_fixture(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def test_torsion_artifact_catalog_limit_and_package_are_generated(tmp_path: Path):
    out = _run(tmp_path)
    assert (out / "check_results_torsional_irregularity_a1.json").is_file()
    catalog = _read_json(out / "check_catalog.json")
    assert "TORSIONAL_IRREGULARITY_A1" in {row["check_id"] for row in catalog["checks"]}
    contract = _read_json(out / "check_limit_contract.json")
    by_id = {row["check_id"]: row for row in contract["contracts"]}
    assert by_id["TORSIONAL_IRREGULARITY_A1"]["limits"]["max_torsion_irregularity_coefficient"] == 1.2
    manifest = _read_json(out / "package_manifest.json")
    assert "check_results_torsional_irregularity_a1.json" in {row["path"] for row in manifest["files"]}


def test_fixture_torsion_pass_fail_and_no_data_rows(tmp_path: Path):
    result = _read_json(_run(tmp_path) / "check_results_torsional_irregularity_a1.json")
    statuses = [row["status"] for row in result["results"]]
    assert statuses == ["PASS", "FAIL", "NO_DATA"]
    assert result["summary"]["pass_count"] == 1
    assert result["summary"]["fail_count"] == 1
    assert result["summary"]["no_data_count"] == 1
    assert result["summary"]["input_status"] == "PARTIAL_INPUT"
    assert all(row["full_tbdy_compliance_status"] == "NOT_EVALUATED" for row in result["results"])



def test_torsion_uses_case_selection_metadata_and_source_refs(tmp_path: Path):
    result = _read_json(_run(tmp_path) / "check_results_torsional_irregularity_a1.json")
    methods = [row["case_selection_method"] for row in result["results"]]
    assert methods == ["CASE_TYPE_RESPONSE_SPECTRUM", "CASE_TYPE_SEISMIC", "CASE_TYPE_RESPONSE_SPECTRUM"]
    for row in result["results"]:
        assert "case_type" in row
        assert "case_selection_method" in row
        assert row["source_refs"]["load_case_or_combo"] == row["load_case_or_combo"]
        assert row["source_refs"]["case_type"] == row["case_type"]
        assert row["source_refs"]["case_selection_method"] == row["case_selection_method"]
    diagnostics = result["diagnostics"]["selector_diagnostics"]
    assert diagnostics["case_type_metadata_available"] is True
    assert diagnostics["name_pattern_fallback_used"] is False
    assert diagnostics["selected_case_count"] == 3


def test_torsion_fallback_is_explicit_when_metadata_is_unavailable(tmp_path: Path):
    payload = deepcopy(_read_json(FIXTURE))
    for row in payload["tables"]["story_max_over_avg_drifts"]["rows"]:
        row.pop("CaseType", None)
    out = _run(tmp_path, _write_fixture(tmp_path, payload))
    result = _read_json(out / "check_results_torsional_irregularity_a1.json")
    assert result["summary"]["checked_row_count"] == 3
    assert all(row["case_selection_method"] == "NAME_PATTERN_FALLBACK" for row in result["results"])
    diagnostics = result["diagnostics"]["selector_diagnostics"]
    assert diagnostics["case_type_metadata_available"] is False
    assert diagnostics["name_pattern_fallback_used"] is True
    assert "NAME_PATTERN_FALLBACK" in diagnostics["warnings"][0]

def test_missing_torsion_source_does_not_silently_omit_check(tmp_path: Path):
    payload = deepcopy(_read_json(FIXTURE))
    payload["tables"].pop("story_max_over_avg_drifts", None)
    out = _run(tmp_path, _write_fixture(tmp_path, payload))
    result = _read_json(out / "check_results_torsional_irregularity_a1.json")
    assert result["summary"]["status"] == "BLOCKED_INPUT"
    assert result["summary"]["input_status"] == "BLOCKED_INPUT"
    summary = _read_json(out / "check_results_summary.json")
    by_id = {row["check_id"]: row for row in summary["check_results"]}
    assert by_id["TORSIONAL_IRREGULARITY_A1"]["status"] == "BLOCKED_INPUT"


def test_torsion_report_mentions_formal_check_without_full_tbdy_claim(tmp_path: Path):
    out = _run(tmp_path)
    for name in ("product_report.md", "product_report.html"):
        text = (out / name).read_text(encoding="utf-8")
        assert "TORSIONAL_IRREGULARITY_A1" in text
        assert "Full TBDY compliance remains NOT_EVALUATED" in text
        assert "FULL_TBDY_PASS" not in text
