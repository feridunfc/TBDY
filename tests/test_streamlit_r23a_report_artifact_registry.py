from __future__ import annotations

from pathlib import Path

import apps.streamlit_beam_design_app as app


def test_r23a_report_artifact_registry_lists_known_reports(tmp_path: Path) -> None:
    rows = app._report_artifact_registry(tmp_path)

    reports = {row["report"] for row in rows}

    assert "Live Story Beam Batch Summary" in reports
    assert "Offline Demo Bundle" in reports
    assert "ETABS Raw Signed Evidence" in reports
    assert "ETABS Design Crosscheck" in reports
    assert "PDF Report" in reports


def test_r23a_report_artifact_registry_marks_existing_files(tmp_path: Path) -> None:
    (tmp_path / "story_beam_batch_summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "story_beam_batch_summary.md").write_text("# summary", encoding="utf-8")

    rows = app._report_artifact_registry(tmp_path)
    live = next(row for row in rows if row["kind"] == "live_etabs_story_batch")

    assert live["status"] == "AVAILABLE"
    assert live["available"] is True
    assert live["json_exists"] is True
    assert live["markdown_exists"] is True
    assert live["xlsx_exists"] is False


def test_r23a_etabs_design_crosscheck_artifacts_are_registered(tmp_path: Path) -> None:
    rows = app._report_artifact_registry(tmp_path)
    crosscheck = next(row for row in rows if row["kind"] == "etabs_design_crosscheck")

    assert crosscheck["json"].endswith("etabs_design_crosscheck.json")
    assert crosscheck["markdown"].endswith("etabs_design_crosscheck.md")
    assert crosscheck["xlsx"].endswith("etabs_design_crosscheck.xlsx")
    assert crosscheck["sheet"] == "ETABS_Design_Crosscheck"
    assert "does not validate BeamCore" in crosscheck["claim_boundary"]


def test_r23a_raw_signed_evidence_sheet_registered(tmp_path: Path) -> None:
    rows = app._report_artifact_registry(tmp_path)
    raw = next(row for row in rows if row["kind"] == "etabs_raw_signed_evidence")

    assert raw["sheet"] == "ETABS_Raw_Evidence"
    assert raw["xlsx"].endswith(str(Path("300") / "engine_report.xlsx"))
    assert "Raw signed ETABS" in raw["claim_boundary"]


def test_r23a_pdf_report_is_coming_soon(tmp_path: Path) -> None:
    rows = app._report_artifact_registry(tmp_path)
    pdf = next(row for row in rows if row["kind"] == "pdf_report")

    assert pdf["status"] == "COMING_SOON"
    assert pdf["available"] is False
    assert pdf["pdf"].endswith("beam_design_report.pdf")
    assert "PDF Report — coming soon" in pdf["claim_boundary"]


def test_r23a_source_contract_terms_present() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    required = [
        "Report Artifact Registry",
        "R23A registry only",
        "Does not generate reports, run ETABS, or calculate engineering formulas",
        "ETABS_Design_Crosscheck",
        "ETABS_Raw_Evidence",
        "PDF Report — coming soon",
    ]

    for text in required:
        assert text in source
