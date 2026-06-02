from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_streamlit_app_import_safety() -> None:
    output = subprocess.check_output(
        [sys.executable, "-c", "import apps.streamlit_beam_design_app; print('IMPORT_OK')"],
        text=True,
    )

    assert output.strip() == "IMPORT_OK"


def test_no_top_level_comtypes_imports() -> None:
    app_source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")
    adapter_source = Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py").read_text(encoding="utf-8-sig")
    combined = app_source + "\n" + adapter_source

    assert "import com" + "types" not in combined
    assert "from com" + "types" not in combined


def test_boundary_guard_forbidden_terms() -> None:
    files = [
        Path("apps/streamlit_beam_design_app.py"),
        Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py"),
        Path("tests/test_streamlit_etabs_ui_adapter.py"),
        Path("tests/test_streamlit_beam_design_app_boundaries.py"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8-sig") for path in files)
    forbidden = (
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
    )

    for term in forbidden:
        assert term not in combined


def test_ui_wording_guard() -> None:
    text = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")
    lowered = text.lower()

    assert "run beamcore checks" in lowered
    assert "beamcore status" in lowered
    assert "etabs actions" in lowered
    assert "diagnostic output" in lowered
    assert "final design" not in lowered
    assert "design approved" not in lowered
    assert "etabs validated" not in lowered
    assert "tbdy compliant" not in lowered
    assert "production ready" not in lowered



def test_r16_no_engineering_formula_in_ui() -> None:
    from pathlib import Path

    combined = (
        Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")
        + "\n"
        + Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py").read_text(encoding="utf-8-sig")
    )
    for term in ("rho_min =", "As_required =", "Mpr =", "Ve_capacity =", "s = Asw"):
        assert term not in combined
