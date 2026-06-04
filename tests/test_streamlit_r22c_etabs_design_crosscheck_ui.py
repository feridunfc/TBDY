from pathlib import Path

SOURCE = Path("apps/streamlit_beam_design_app.py")


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8-sig")


def test_r22c_etabs_design_crosscheck_ui_terms_present() -> None:
    source = _source()

    required = [
        "ETABS Concrete Design Output Crosscheck",
        "Diagnostic comparison only",
        "End-I",
        "Middle",
        "End-J",
        "As Top",
        "As Bot",
        "ETABS design output does not validate BeamCore",
    ]

    for text in required:
        assert text in source


def test_r22c_does_not_claim_validation() -> None:
    source = _source()

    forbidden = [
        "ETABS design validates BeamCore",
        "ETABS validation passed",
        "TBDY compliance proven by ETABS design output",
    ]

    for text in forbidden:
        assert text not in source
