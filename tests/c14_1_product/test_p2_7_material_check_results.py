from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import tools.run_live_model_product_report as product_cli

FIXTURE = Path("tests/fixtures/p2_3_scope_material_combined_verdict_fixture.json")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fixture(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _run(tmp_path: Path, fixture: Path = FIXTURE) -> Path:
    out = tmp_path / "out"
    assert product_cli.main(["--input", str(fixture), "--out", str(out)]) == 0
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_material_check_artifact_catalog_and_limit_contract_are_generated(tmp_path: Path):
    out = _run(tmp_path)
    assert (out / "check_results_concrete_material_min_strength.json").is_file()
    catalog = _read_json(out / "check_catalog.json")
    assert "CONCRETE_MATERIAL_MIN_STRENGTH" in {row["check_id"] for row in catalog["checks"]}
    contract = _read_json(out / "check_limit_contract.json")
    by_id = {row["check_id"]: row for row in contract["contracts"]}
    material = by_id["CONCRETE_MATERIAL_MIN_STRENGTH"]
    assert material["limits"]["min_fck_mpa"] == 25.0
    assert material["limits"]["min_concrete_class_label"] == "C25/30"
    assert material["code_clause_status"] == "PENDING_CLAUSE_BINDING"


def test_material_pass_rows_are_produced_for_fck_at_or_above_limit(tmp_path: Path):
    result = _read_json(_run(tmp_path) / "check_results_concrete_material_min_strength.json")
    assert result["summary"]["status"] == "PASS"
    assert result["summary"]["input_status"] == "RESOLVED"
    assert result["summary"]["checked_section_count"] == 3
    assert result["summary"]["pass_count"] == 3
    assert {row["status"] for row in result["results"]} == {"PASS"}
    assert all(row["full_tbdy_compliance_status"] == "NOT_EVALUATED" for row in result["results"])


def test_material_fail_row_is_produced_for_fck_below_limit(tmp_path: Path):
    payload = deepcopy(_read_json(FIXTURE))
    for row in payload["tables"]["material_concrete_data"]["rows"]:
        if row["Material"] == "C35":
            row["Fc"] = 20
    out = _run(tmp_path, _write_fixture(tmp_path, payload))
    result = _read_json(out / "check_results_concrete_material_min_strength.json")
    c35 = next(row for row in result["results"] if row["material_name"] == "C35")
    assert c35["status"] == "FAIL"
    assert c35["demand"]["fck_mpa"] == 20.0
    assert c35["comparison"]["fck_mpa"] == "20 >= 25"
    assert result["summary"]["status"] == "FAIL"


def test_missing_fck_does_not_produce_fake_pass(tmp_path: Path):
    payload = deepcopy(_read_json(FIXTURE))
    for row in payload["tables"]["material_concrete_data"]["rows"]:
        if row["Material"] == "C30":
            row.pop("Fc", None)
    out = _run(tmp_path, _write_fixture(tmp_path, payload))
    result = _read_json(out / "check_results_concrete_material_min_strength.json")
    c30_rows = [row for row in result["results"] if row["material_name"] == "C30"]
    assert c30_rows
    assert {row["status"] for row in c30_rows} == {"NO_DATA"}
    assert {row["input_status"] for row in c30_rows} <= {"NO_DATA", "PARTIAL_INPUT"}
    assert result["summary"]["pass_count"] < result["summary"]["checked_section_count"]


def test_material_check_is_in_summary_and_package_manifest(tmp_path: Path):
    out = _run(tmp_path)
    summary = _read_json(out / "check_results_summary.json")
    by_id = {row["check_id"]: row for row in summary["check_results"]}
    assert by_id["CONCRETE_MATERIAL_MIN_STRENGTH"]["result_file"] == "check_results_concrete_material_min_strength.json"
    assert summary["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    manifest = _read_json(out / "package_manifest.json")
    by_path = {row["path"]: row for row in manifest["files"]}
    name = "check_results_concrete_material_min_strength.json"
    assert by_path[name]["sha256"] == _sha(out / name)
    assert by_path[name]["size_bytes"] == (out / name).stat().st_size
