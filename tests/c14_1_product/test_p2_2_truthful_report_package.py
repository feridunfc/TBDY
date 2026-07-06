from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import tools.run_live_model_product_report as product_cli

FIXTURE = Path("tests/fixtures/p2_0_c13_1_product_report_fixture.json")


def _run_fixture(tmp_path: Path) -> Path:
    out = tmp_path / "product_out"
    rc = product_cli.main(["--input", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    return out


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_unsupported_objects_force_pass_with_exclusions_not_clean_model_pass(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "product_summary.json")
    assert summary["checked_scope_status"] == "PASS"
    assert summary["unsupported_object_count_total"] == 2
    assert summary["excluded_frame_object_count_total"] == 2
    assert summary["model_scope_status"] == "PASS_WITH_EXCLUSIONS"
    assert summary["model_scope_status"] != "PASS"


def test_full_tbdy_compliance_status_is_never_evaluated(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "product_summary.json")
    report = _read_json(out / "product_report.json")
    manifest = _read_json(out / "package_manifest.json")
    assert summary["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert report["executive_summary"]["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert report["scope_manifest"]["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert manifest["truth_status_summary"]["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_product_summary_contains_truthful_scope_fields(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "product_summary.json")
    required = {
        "checked_scope_status",
        "model_scope_status",
        "full_tbdy_compliance_status",
        "unsupported_object_count_total",
        "excluded_frame_object_count_total",
        "frame_assignment_type_counts",
    }
    assert required.issubset(summary)
    assert summary["frame_assignment_type_counts"] == {
        "Beam": 4,
        "Column": 3,
        "Brace": 0,
        "Null": 0,
        "Other": 0,
    }
    assert summary["source_frame_assignment_row_count"] == 7
    assert summary["frame_assignment_type_counts_reconciled"] is True


def test_model_scope_is_fail_when_checked_scope_fails(tmp_path: Path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = deepcopy(payload)
    payload["tables"]["frame_assignments"]["rows"].append(
        {"Story": "+1.00", "Label": "B_BAD", "UniqueName": "999", "Type": "Beam", "Length": "3.0", "AnalysisSect": "B20x90", "DesignSect": "B20x90"}
    )
    payload["tables"]["frame_section_properties"]["rows"].append({"Name": "B20x90", "t2": "0.2", "t3": "0.9"})
    fixture = tmp_path / "bad_fixture.json"
    fixture.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    out = tmp_path / "bad_out"
    rc = product_cli.main(["--input", str(fixture), "--out", str(out)])
    assert rc == 0
    summary = _read_json(out / "product_summary.json")
    assert summary["checked_scope_status"] == "FAIL"
    assert summary["model_scope_status"] == "FAIL"
    assert summary["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_package_manifest_and_zip_are_produced_with_matching_hashes(tmp_path: Path):
    out = _run_fixture(tmp_path)
    manifest_path = out / "package_manifest.json"
    package_path = out / "product_report_package.zip"
    assert manifest_path.is_file()
    assert package_path.is_file()
    manifest = _read_json(manifest_path)
    assert manifest["sprint_id"] == "P2.2_TRUTHFUL_REPORT_PACKAGE_SCOPE_MANIFEST"
    assert manifest["guardrail_metadata"] == {
        "no_etabs_mutation": True,
        "no_analysis_run": True,
        "no_design_run": True,
        "no_excel_production_input": True,
        "no_check_engine_execution": True,
    }
    for entry in manifest["files"]:
        path = out / entry["path"]
        assert path.is_file(), entry
        assert entry["sha256"] == _sha256(path)
        assert entry["size_bytes"] == path.stat().st_size
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
    assert {
        "product_report.json",
        "product_report.md",
        "product_summary.json",
        "product_evidence.json",
        "product_report_source_tables.json",
        "product_slice_manifest.json",
        "product_report.html",
        "README.md",
        "package_manifest.json",
    }.issubset(names)


def test_markdown_and_html_top_sections_are_truthful(tmp_path: Path):
    out = _run_fixture(tmp_path)
    md = (out / "product_report.md").read_text(encoding="utf-8")
    html = (out / "product_report.html").read_text(encoding="utf-8")
    for text in (md, html):
        assert "NOT full TBDY compliance" in text
        assert "full_tbdy_compliance_status" in text
        assert "NOT_EVALUATED" in text
        assert "checked_scope_status" in text
        assert "model_scope_status" in text
    assert "â€”" not in md
    assert "TBDY Minimal Live Product Report - C13.1" in md


def test_readme_explains_scope_and_legacy_booleans(tmp_path: Path):
    out = _run_fixture(tmp_path)
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "This package is NOT full TBDY compliance." in readme
    assert "full_tbdy_compliance_status: NOT_EVALUATED" in readme
    assert "product_slice_passed" in readme
    assert "report_product_passed" in readme
