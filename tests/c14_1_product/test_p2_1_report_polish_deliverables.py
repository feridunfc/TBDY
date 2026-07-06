from __future__ import annotations

import json
from pathlib import Path

import tools.run_live_model_product_report as product_cli
from tbdy_engine.product_reports.c13_1_report import EXECUTIVE_SUMMARY_FIELDS, HEAVY_SUMMARY_KEYS

FIXTURE = Path("tests/fixtures/p2_0_c13_1_product_report_fixture.json")


def _run_fixture(tmp_path: Path) -> Path:
    out = tmp_path / "product_out"
    rc = product_cli.main(["--input", str(FIXTURE), "--out", str(out)])
    assert rc == 0
    return out


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p2_1_product_command_writes_stable_deliverable_set(tmp_path: Path):
    out = _run_fixture(tmp_path)
    expected = {
        "product_report.json",
        "product_report.md",
        "product_summary.json",
        "product_evidence.json",
        "product_report_source_tables.json",
        "product_slice_manifest.json",
        "product_report.html",
    }
    assert expected.issubset({path.name for path in out.iterdir()})


def test_product_summary_json_is_concise_and_has_no_heavy_detail_keys(tmp_path: Path):
    out = _run_fixture(tmp_path)
    summary = _read_json(out / "product_summary.json")
    for field in EXECUTIVE_SUMMARY_FIELDS:
        assert field in summary
    assert "metadata" in summary
    for heavy_key in HEAVY_SUMMARY_KEYS:
        assert heavy_key not in summary
    assert "beam_section_type_results" not in summary
    assert "column_section_type_results" not in summary
    assert "modal_mass_summary" not in summary
    assert "modal_mass_full_table_rows" not in summary


def test_product_evidence_json_contains_moved_diagnostics(tmp_path: Path):
    out = _run_fixture(tmp_path)
    evidence = _read_json(out / "product_evidence.json")
    assert evidence["beam_section_type_results"]
    assert evidence["column_section_type_results"]
    assert evidence["beam_section_detail_rows"]
    assert evidence["column_section_detail_rows"]
    assert evidence["modal_mass_summary"]["modal_ux_status"] == "OK"
    assert evidence["modal_mass_final_verdict_rows"]
    assert "source_references" in evidence
    assert "beam_section_type_results" in evidence["moved_from_product_summary"]


def test_markdown_heading_is_ascii_and_has_no_broken_encoding_sequence(tmp_path: Path):
    out = _run_fixture(tmp_path)
    text = (out / "product_report.md").read_text(encoding="utf-8")
    assert "â€”" not in text
    assert text.startswith("# TBDY Minimal Live Product Report - C13.1")
    assert "TBDY Minimal Live Product Report — C13.1" not in text


def test_html_deliverable_contains_human_review_sections(tmp_path: Path):
    out = _run_fixture(tmp_path)
    html = (out / "product_report.html").read_text(encoding="utf-8")
    assert "<h1>TBDY Minimal Live Product Report - C13.1</h1>" in html
    assert "Executive Summary" in html
    assert "Concrete Beam Section Geometry Checks" in html
    assert "Unsupported / Out-of-Scope Beam Sections" in html
    assert "Concrete Column Section Geometry Checks" in html
    assert "Modal Mass Final Verdict" in html
    assert "Guardrails" in html
    assert "Boundary Notes" in html
    assert "cdn" not in html.casefold()
    assert "http://" not in html.casefold()
    assert "https://" not in html.casefold()


def test_json_deliverables_are_deterministic_between_runs(tmp_path: Path):
    out_a = _run_fixture(tmp_path / "a")
    out_b = _run_fixture(tmp_path / "b")
    for name in ("product_report.json", "product_summary.json", "product_evidence.json"):
        assert (out_a / name).read_text(encoding="utf-8") == (out_b / name).read_text(encoding="utf-8")


def test_no_mutation_or_analysis_design_indicators_are_introduced(tmp_path: Path):
    out = _run_fixture(tmp_path)
    report = _read_json(out / "product_report.json")
    metadata = report["metadata"]
    assert metadata["etabs_model_mutated"] is False
    assert metadata["analysis_run"] is False
    assert metadata["design_run"] is False
    assert metadata["check_engine_executed"] is False
    assert metadata["check_result_emitted"] is True
    assert report["guardrails"] == {
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
    }


def test_live_command_mode_remains_cli_compatible_without_calling_etabs(tmp_path: Path, monkeypatch):
    def fake_prepare_live_input(args, out_dir: Path, prepared_dir: Path) -> None:
        product_cli._prepare_fixture_input(FIXTURE, prepared_dir)

    monkeypatch.setattr(product_cli, "_prepare_live_input", fake_prepare_live_input)
    out = tmp_path / "live_compat_out"
    rc = product_cli.main(["--live-etabs", "--out", str(out)])
    assert rc == 0
    report = _read_json(out / "product_report.json")
    assert report["executive_summary"]["report_product_passed"] is True
    assert (out / "product_evidence.json").is_file()
    assert (out / "product_report.html").is_file()
