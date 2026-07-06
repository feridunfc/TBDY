from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import tools.run_live_model_product_report as product_cli

FIXTURE = Path("tests/fixtures/p2_3_scope_material_combined_verdict_fixture.json")


def _run_fixture(tmp_path: Path) -> Path:
    out = tmp_path / "product_out"
    rc = product_cli.main(["--input", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    return out


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p2_6_formal_check_artifacts_exist_and_are_packaged(tmp_path: Path):
    out = _run_fixture(tmp_path)
    required = {
        "check_catalog.json",
        "check_limit_contract.json",
        "check_results_concrete_beam_min_geometry.json",
        "check_results_concrete_column_min_geometry.json",
        "check_results_modal_mass_participation.json",
        "check_results_summary.json",
        "check_results_concrete_material_min_strength.json",
        "check_results_story_drift.json",
        "check_results_torsional_irregularity_a1.json",
        "blocked_checks.json",
    }
    for name in required:
        assert (out / name).is_file(), name

    manifest = _read_json(out / "package_manifest.json")
    by_path = {entry["path"]: entry for entry in manifest["files"]}
    for name in required:
        assert name in by_path
        assert by_path[name]["sha256"] == _sha256(out / name)
        assert by_path[name]["size_bytes"] == (out / name).stat().st_size

    with zipfile.ZipFile(out / "product_report_package.zip") as archive:
        assert required.issubset(set(archive.namelist()))


def test_check_limit_contract_freezes_existing_product_limits(tmp_path: Path):
    contract = _read_json(_run_fixture(tmp_path) / "check_limit_contract.json")
    by_id = {row["check_id"]: row for row in contract["contracts"]}
    assert by_id["CONCRETE_BEAM_MIN_GEOMETRY"]["limits"] == {
        "max_h_over_bw": 3.5,
        "min_depth_mm": 300.0,
        "min_width_mm": 250.0,
    }
    assert by_id["CONCRETE_COLUMN_MIN_GEOMETRY"]["limits"] == {
        "min_area_mm2": 75000.0,
        "min_aspect_ratio": 0.4,
        "min_dimension_mm": 300.0,
    }
    assert by_id["MODAL_MASS_PARTICIPATION"]["limits"] == {"modal_mass_threshold": 0.95}
    assert contract["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert {row["code_clause_status"] for row in contract["contracts"]} == {"PENDING_CLAUSE_BINDING"}


def test_beam_and_column_object_check_results_are_object_level(tmp_path: Path):
    out = _run_fixture(tmp_path)
    beam = _read_json(out / "check_results_concrete_beam_min_geometry.json")
    column = _read_json(out / "check_results_concrete_column_min_geometry.json")

    assert beam["summary"]["status"] == "PASS"
    assert beam["summary"]["input_status"] == "RESOLVED"
    assert beam["summary"]["checked_object_count"] == 3
    assert beam["summary"]["pass_count"] == 3
    assert beam["summary"]["fail_count"] == 0
    assert beam["summary"]["unsupported_count"] == 1
    assert len(beam["results"]) == 3

    assert column["summary"]["status"] == "PASS"
    assert column["summary"]["input_status"] == "RESOLVED"
    assert column["summary"]["checked_object_count"] == 2
    assert column["summary"]["pass_count"] == 2
    assert column["summary"]["unsupported_count"] == 1
    assert len(column["results"]) == 2

    result = beam["results"][0]
    assert result["schema_version"] == "check_result.v1"
    assert result["artifact_type"] == "OBJECT_CHECK_RESULT"
    assert result["scope"]["scope_status"] == "CHECKED"
    assert result["input"]["input_status"] == "RESOLVED"
    assert result["status"] == "PASS"
    assert result["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert {row["subcheck_id"] for row in result["subchecks"]} == {
        "beam_min_width",
        "beam_min_depth",
        "beam_depth_width_ratio",
    }


def test_modal_mass_check_result_is_model_level(tmp_path: Path):
    modal = _read_json(_run_fixture(tmp_path) / "check_results_modal_mass_participation.json")
    assert modal["summary"]["status"] == "PASS"
    assert modal["summary"]["input_status"] == "RESOLVED"
    result = modal["result"]
    assert result["artifact_type"] == "MODEL_CHECK_RESULT"
    assert result["check_id"] == "MODAL_MASS_PARTICIPATION"
    assert result["status"] == "PASS"
    assert result["input"]["input_status"] == "RESOLVED"
    assert result["values"]["ux"] == 0.9999
    assert result["values"]["uy"] == 0.9999
    assert result["limits"] == {"modal_mass_threshold": 0.95}
    assert result["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_check_results_summary_and_blocked_checks_are_truthful(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "check_results_summary.json")
    blocked = _read_json(out / "blocked_checks.json")
    assert summary["full_tbdy_compliance_status"] == "NOT_EVALUATED"
    assert summary["summary"]["blocked_count"] == 4
    assert summary["summary"]["total_formal_checks"] == 6
    assert summary["summary"]["pass_count"] >= 4
    assert summary["summary"]["fail_count"] >= 0
    assert [row["check_id"] for row in summary["check_results"]][:3] == [
        "CONCRETE_BEAM_MIN_GEOMETRY",
        "CONCRETE_COLUMN_MIN_GEOMETRY",
        "MODAL_MASS_PARTICIPATION",
    ]
    assert {row["check_id"] for row in summary["check_results"]} >= {
        "CONCRETE_MATERIAL_MIN_STRENGTH",
        "STORY_DRIFT",
        "TORSIONAL_IRREGULARITY_A1",
    }
    assert len(blocked["blocked_checks"]) == 4
    assert {row["input_status"] for row in blocked["blocked_checks"]} == {"BLOCKED_INPUT"}
    assert {row["status"] for row in blocked["blocked_checks"]} == {"BLOCKED"}


def test_report_lists_formal_check_results_without_full_tbdy_claim(tmp_path: Path):
    out = _run_fixture(tmp_path)
    md = (out / "product_report.md").read_text(encoding="utf-8")
    html = (out / "product_report.html").read_text(encoding="utf-8")
    for text in (md, html):
        assert "Formal Check Results" in text
        assert "Blocked Checks" in text
        assert "CONCRETE_BEAM_MIN_GEOMETRY" in text
        assert "CONCRETE_COLUMN_MIN_GEOMETRY" in text
        assert "MODAL_MASS_PARTICIPATION" in text
        assert "Full TBDY compliance remains NOT_EVALUATED" in text
        assert "FULL_TBDY_PASS" not in text
        assert "FULL_TBDY_COMPLIANT" not in text
        assert "TBDY_PASS" not in text


def test_no_forbidden_scope_or_engineering_claims(tmp_path: Path):
    out = _run_fixture(tmp_path)
    for name in (
        "product_report.json",
        "product_summary.json",
        "check_results_summary.json",
        "check_results_concrete_beam_min_geometry.json",
        "check_results_concrete_column_min_geometry.json",
        "check_results_modal_mass_participation.json",
        "blocked_checks.json",
    ):
        text = (out / name).read_text(encoding="utf-8")
        assert "FULL_TBDY_PASS" not in text
        assert "FULL_TBDY_COMPLIANT" not in text
        assert "TBDY_PASS" not in text
        assert "FULL_COMPLIANCE_PASS" not in text
    report = _read_json(out / "product_report.json")
    assert report["metadata"]["check_engine_executed"] is False
    assert report["metadata"]["etabs_model_mutated"] is False
    assert report["metadata"]["analysis_run"] is False
    assert report["metadata"]["design_run"] is False
