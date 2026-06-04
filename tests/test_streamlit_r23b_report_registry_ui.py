from __future__ import annotations

from pathlib import Path

import apps.streamlit_beam_design_app as app


def test_r23b_report_registry_summary_counts_statuses(tmp_path: Path) -> None:
    (tmp_path / "story_beam_batch_summary.json").write_text("{}", encoding="utf-8")
    rows = app._report_artifact_registry(tmp_path)

    summary = app._report_registry_summary(rows)

    assert summary["AVAILABLE"] >= 1
    assert summary["MISSING"] >= 1
    assert summary["COMING_SOON"] == 1


def test_r23b_report_registry_display_rows_are_compact(tmp_path: Path) -> None:
    rows = app._report_artifact_registry(tmp_path)
    display_rows = app._report_registry_display_rows(rows)

    assert len(display_rows) == len(rows)

    first = display_rows[0]
    assert set(first) == {
        "status",
        "report",
        "kind",
        "available",
        "json_exists",
        "markdown_exists",
        "xlsx_exists",
        "pdf_exists",
        "sheet",
        "claim_boundary",
        "json",
        "markdown",
        "xlsx",
        "pdf",
    }


def test_r23b_status_badges() -> None:
    assert app._report_registry_status_badge("AVAILABLE") == "AVAILABLE"
    assert app._report_registry_status_badge("COMING_SOON") == "COMING_SOON"
    assert app._report_registry_status_badge("MISSING") == "MISSING"
    assert app._report_registry_status_badge("OTHER") == "MISSING"


def test_r23b_source_contract_terms_present() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    required = [
        "_report_registry_summary",
        "_report_registry_display_rows",
        "_report_registry_status_badge",
        "registry_summary",
        "Report Artifact Registry",
    ]

    for text in required:
        assert text in source
