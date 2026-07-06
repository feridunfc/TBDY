from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import tools.run_live_model_product_report as product_cli
from tbdy_engine.product_reports.combined_verdict import build_combined_product_scope_verdict

FIXTURE = Path("tests/fixtures/p2_3_scope_material_combined_verdict_fixture.json")


def _run_fixture(tmp_path: Path, fixture: Path = FIXTURE) -> Path:
    out = tmp_path / "product_out"
    rc = product_cli.main(["--input", str(fixture), "--out", str(out)])
    assert rc == 0
    return out


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_object_scope_ledger_row_count_equals_source_frame_assignment_count(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "object_scope_summary.json")
    ledger = _read_json(out / "object_scope_ledger.json")
    assert summary["source_frame_assignment_row_count"] == 9
    assert summary["object_scope_ledger_row_count"] == 9
    assert len(ledger) == summary["source_frame_assignment_row_count"]
    assert summary["object_scope_reconciled"] is True


def test_object_scope_buckets_reconcile_to_source_total(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "object_scope_summary.json")
    bucket_total = (
        summary["checked_concrete_beam_object_count"]
        + summary["checked_concrete_column_object_count"]
        + summary["unsupported_beam_object_count"]
        + summary["unsupported_column_object_count"]
        + summary["excluded_brace_object_count"]
        + summary["excluded_null_object_count"]
        + summary["excluded_other_object_count"]
        + summary["malformed_or_missing_evidence_object_count"]
    )
    assert bucket_total == summary["source_frame_assignment_row_count"]
    assert summary["object_scope_bucket_counts_reconciled"] is True


def test_every_ledger_row_has_stable_source_reference_or_row_index(tmp_path: Path):
    ledger = _read_json(_run_fixture(tmp_path) / "object_scope_ledger.json")
    for row in ledger:
        assert isinstance(row["source_row_index"], int)
        assert row["stable_source_reference"]
        assert row["object_id"] or (row["object_label"] and row["story"] and row["section"])


def test_checked_concrete_object_counts_reconcile_with_existing_summary_counts(tmp_path: Path):
    out = _run_fixture(tmp_path)
    object_summary = _read_json(out / "object_scope_summary.json")
    product_summary = _read_json(out / "product_summary.json")
    assert object_summary["checked_concrete_beam_object_count"] == product_summary["concrete_beam_object_count"] == 3
    assert object_summary["checked_concrete_column_object_count"] == product_summary["concrete_column_object_count"] == 2


def test_unsupported_beam_brace_and_null_buckets_are_explicit(tmp_path: Path):
    ledger = _read_json(_run_fixture(tmp_path) / "object_scope_ledger.json")
    by_label = {row["object_label"]: row for row in ledger}
    assert by_label["B290"]["section"] == "HE160A"
    assert by_label["B290"]["scope_bucket"] == "UNSUPPORTED_BEAM"
    assert by_label["B290"]["scope_status"] == "OUT_OF_SCOPE"
    assert by_label["BR1"]["scope_bucket"] == "EXCLUDED_BRACE"
    assert by_label["BR1"]["scope_status"] == "EXCLUDED"
    assert by_label["N1"]["scope_bucket"] == "EXCLUDED_NULL_ASSIGNMENT"
    assert by_label["N1"]["scope_status"] == "EXCLUDED"


def test_material_evidence_includes_all_checked_concrete_sections(tmp_path: Path):
    out = _run_fixture(tmp_path)
    material = _read_json(out / "material_evidence.json")
    summary = _read_json(out / "material_summary.json")
    sections = {(row["element_type"], row["section"]) for row in material}
    assert sections == {("Beam", "B40x70"), ("Beam", "B60x70"), ("Column", "C40x80")}
    assert summary["checked_concrete_section_count"] == 3
    assert summary["material_evidence_row_count"] == 3
    assert summary["material_evidence_reconciled"] is True
    assert summary["material_evidence_status"] == "RESOLVED"


def test_unresolved_material_does_not_silently_pass(tmp_path: Path):
    payload = deepcopy(_read_json(FIXTURE))
    # Remove one concrete material row while leaving the section material name in place.
    payload["tables"]["material_concrete_data"]["rows"] = [
        row for row in payload["tables"]["material_concrete_data"]["rows"] if row["Material"] != "C35"
    ]
    fixture = tmp_path / "missing_material.json"
    fixture.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    out = _run_fixture(tmp_path, fixture)
    material_summary = _read_json(out / "material_summary.json")
    product_summary = _read_json(out / "product_summary.json")
    assert material_summary["material_evidence_status"] == "PARTIAL"
    assert product_summary["combined_product_scope_status"] == "PARTIAL_EVIDENCE"
    assert product_summary["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_unsupported_or_excluded_sections_do_not_appear_as_resolved_material(tmp_path: Path):
    material = _read_json(_run_fixture(tmp_path) / "material_evidence.json")
    resolved_sections = {row["section"] for row in material if row["material_status"] == "RESOLVED"}
    assert "HE160A" not in resolved_sections
    assert "STEEL_COL" not in resolved_sections
    assert "BRACE_SEC" not in resolved_sections


def test_fck_value_is_numeric_and_unit_explicit_when_resolved(tmp_path: Path):
    material = _read_json(_run_fixture(tmp_path) / "material_evidence.json")
    for row in material:
        assert row["material_status"] == "RESOLVED"
        assert isinstance(row["fck_value_mpa"], (int, float))
        assert row["fck_source_unit"] == "MPa"
        assert row["fck_adequacy_status"] == "NOT_EVALUATED"


def test_combined_product_scope_status_precedence_rules():
    base_report = {
        "metadata": {"etabs_model_mutated": False, "analysis_run": False, "design_run": False, "check_engine_executed": False},
        "guardrails": {"excel_production_path_used": False, "streamlit_ui_used": False, "legacy_runtime_used": False, "rebar_flexure_shear_capacity_unlocked": False},
    }
    executive = {"checked_scope_status": "PASS", "unsupported_object_count_total": 1, "excluded_frame_object_count_total": 2}
    obj = {"unsupported_object_count_total": 1, "excluded_frame_object_count_total": 2}
    assert build_combined_product_scope_verdict(report=base_report, executive_summary=executive, material_summary={"material_evidence_status": "RESOLVED"}, object_scope_summary=obj)["combined_product_scope_status"] == "PASS_WITH_EXCLUSIONS"
    assert build_combined_product_scope_verdict(report=base_report, executive_summary=executive, material_summary={"material_evidence_status": "PARTIAL"}, object_scope_summary=obj)["combined_product_scope_status"] == "PARTIAL_EVIDENCE"
    no_data_verdict = build_combined_product_scope_verdict(
        report=base_report,
        executive_summary={"checked_scope_status": "NO_DATA"},
        material_summary={"material_evidence_status": "RESOLVED"},
        object_scope_summary={},
    )
    assert no_data_verdict["geometry_product_status"] == "NO_DATA"
    assert no_data_verdict["combined_product_scope_status"] == "PARTIAL_EVIDENCE"
    assert no_data_verdict["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert "required geometry/modal evidence is missing" in no_data_verdict["combined_product_scope_reason"]
    assert build_combined_product_scope_verdict(report=base_report, executive_summary={"checked_scope_status": "FAIL"}, material_summary={"material_evidence_status": "RESOLVED"}, object_scope_summary={})["combined_product_scope_status"] == "FAIL"
    unsafe_report = deepcopy(base_report)
    unsafe_report["metadata"]["analysis_run"] = True
    assert build_combined_product_scope_verdict(report=unsafe_report, executive_summary=executive, material_summary={"material_evidence_status": "RESOLVED"}, object_scope_summary=obj)["combined_product_scope_status"] == "FAIL"


def test_full_tbdy_compliance_status_remains_not_evaluated_and_banned_strings_absent(tmp_path: Path):
    out = _run_fixture(tmp_path)
    for name in ("product_report.json", "product_summary.json", "material_summary.json", "package_manifest.json"):
        text = (out / name).read_text(encoding="utf-8")
        assert "NOT_EVALUATED" in text
        assert "FULL_TBDY_PASS" not in text
        assert "FULL_TBDY_COMPLIANT" not in text
        assert "TBDY_PASS" not in text
        assert "FULL_COMPLIANCE_PASS" not in text
    assert _read_json(out / "product_summary.json")["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    forbidden = '\"combined_product_scope_status\": \"NO_DATA\"'
    for name in ("product_summary.json", "product_report.json", "package_manifest.json"):
        assert forbidden not in (out / name).read_text(encoding="utf-8")


def test_package_manifest_includes_new_artifacts_with_hash_and_size(tmp_path: Path):
    out = _run_fixture(tmp_path)
    manifest = _read_json(out / "package_manifest.json")
    by_path = {entry["path"]: entry for entry in manifest["files"]}
    for name in ("object_scope_ledger.json", "object_scope_summary.json", "material_evidence.json", "material_summary.json"):
        assert name in by_path
        assert by_path[name]["sha256"] == _sha256(out / name)
        assert by_path[name]["size_bytes"] == (out / name).stat().st_size
    with zipfile.ZipFile(out / "product_report_package.zip") as archive:
        names = set(archive.namelist())
    assert {"object_scope_ledger.json", "object_scope_summary.json", "material_evidence.json", "material_summary.json"}.issubset(names)


def test_markdown_and_html_include_p2_3_summaries_without_full_ledger(tmp_path: Path):
    out = _run_fixture(tmp_path)
    md = (out / "product_report.md").read_text(encoding="utf-8")
    html = (out / "product_report.html").read_text(encoding="utf-8")
    for text in (md, html):
        assert "Object Scope Ledger Summary" in text
        assert "Unsupported and Excluded Object Samples" in text
        assert "Concrete Material Evidence Summary" in text
        assert "Combined Product Scope Verdict" in text
        assert "Full object_scope_ledger.json is intentionally not rendered" in text
        assert "CHECKED_CONCRETE_BEAM" not in text
    assert len(md) < (out / "object_scope_ledger.json").stat().st_size * 4


def test_product_slice_manifest_uses_explicit_p2_3_semantics(tmp_path: Path):
    manifest = _read_json(_run_fixture(tmp_path) / "product_slice_manifest.json")
    assert "sprint" not in manifest
    assert manifest["product_slice_id"] == "C13.1_MINIMAL_LIVE_PRODUCT_REPORT"
    assert manifest["product_slice_origin_sprint_id"] == "P2.0_C13_1_LIVE_PRODUCT_REPORT_PARITY"
    assert manifest["report_package_sprint_id"] == "P2.3_SCOPE_MATERIAL_COMBINED_VERDICT"
    assert manifest["truth_model_version"] == "P2.3_TRUTH_MODEL_V1"
    assert manifest["full_tbdy_compliance_status"] == "NOT_EVALUATED"
