from pathlib import Path


def test_r18_offline_demo_source_contains_boundaries():
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    assert "def _load_r18_offline_demo_results" in source
    assert "Load R18 offline demo results" in source
    assert "Does not run ETABS or engineering formulas" in source
    assert "beam_design_result" in source
    assert "beam_verification_result" in source
    assert "etabs_comparison_result" in source


def test_r18_offline_demo_does_not_add_forbidden_ui_formulas():
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    forbidden = [
        "rho_min =",
        "As_required =",
        "Mpr =",
        "Ve_capacity =",
        "s = Asw",
    ]
    for term in forbidden:
        assert term not in source
