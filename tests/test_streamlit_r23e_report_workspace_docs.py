from pathlib import Path

DOC = Path("docs/streamlit_beam_design_ui.md")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8-sig")


def test_r23e_docs_include_report_workspace_terms() -> None:
    text = _doc()

    required = [
        "R23 Report Workspace",
        "Report Actions",
        "Report Artifact Registry",
        "ETABS Raw Signed Evidence",
        "ETABS Design Crosscheck",
        "PDF Report — coming soon",
    ]

    for item in required:
        assert item in text


def test_r23e_docs_include_artifact_formats() -> None:
    text = _doc()

    required = [
        "etabs_design_crosscheck.json",
        "etabs_design_crosscheck.md",
        "etabs_design_crosscheck.xlsx",
        "ETABS_Design_Crosscheck",
        "ETABS_Raw_Evidence",
    ]

    for item in required:
        assert item in text


def test_r23e_docs_preserve_claim_boundaries() -> None:
    text = _doc()

    required = [
        "Diagnostic UI only",
        "Not ETABS validation",
        "Not design-engine validation",
        "Not TBDY compliance proof",
        "Not production-ready",
        "Engineering review required",
    ]

    for item in required:
        assert item in text


def test_r23e_docs_do_not_claim_validation() -> None:
    text = _doc()

    forbidden = [
        "ETABS validation passed",
        "TBDY compliance proven",
        "production-ready deliverable",
    ]

    for item in forbidden:
        assert item not in text
