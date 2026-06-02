from __future__ import annotations

from pathlib import Path

import apps.streamlit_beam_design_app as app
from tbdy_engine.design.beams import streamlit_etabs_ui_adapter as adapter


class FakeFile:
    def GetModelFilename(self) -> str:
        return r"C:\Projects\Model.edb"


class FakeOpenModel:
    File = FakeFile()

    def GetPresentUnits(self) -> int:
        return 6

    def GetDatabaseUnits(self) -> int:
        return 6


def test_app_import_ok() -> None:
    assert app is not None


def test_adapter_import_ok() -> None:
    assert adapter is not None


def test_get_etabs_connection_snapshot_offline_safe(monkeypatch) -> None:
    def fail_attach() -> object:
        raise RuntimeError("etabs_attach: fake")

    monkeypatch.setattr(adapter, "attach_to_open_etabs", fail_attach)
    snapshot = adapter.get_etabs_connection_snapshot()

    assert snapshot["online"] is False
    assert snapshot["status"] == "OFFLINE"
    assert "etabs_attach" in str(snapshot["error"])


def test_fake_etabs_snapshot_includes_model_path_name_and_units() -> None:
    snapshot = adapter.get_etabs_connection_snapshot(sap_model=FakeOpenModel())

    assert snapshot["online"] is True
    assert snapshot["status"] == "ONLINE"
    assert snapshot["model_name"].endswith("Model.edb")
    assert snapshot["model_path"].endswith("Model.edb")
    assert snapshot["present_units"]["force"] == "kN"
    assert snapshot["database_units"]["raw"] == 6


def test_sidebar_source_contains_required_sections() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    assert "ETABS units" in source
    assert "Provided reinforcement for verification" in source
    assert "Engine calculations use canonical units: kN, kNm, mm, MPa" in source
    assert "ETABS disagreement is diagnostic only" in source
    assert "Claim boundaries" in source


def test_provided_reinforcement_not_labeled_design_input() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")

    assert "Provided reinforcement for verification" in source
    assert "provided reinforcement design input" not in source.lower()


def test_mode_split_tabs_visible_in_source() -> None:
    source = Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")
    for label in [
        "Connection/Input", "Demand", "Design", "Verification",
        "ETABS Crosscheck", "Reports/Evidence", "Settings/About",
    ]:
        assert label in source


def test_classifier_labels() -> None:
    assert adapter.classify_frame_object("B35", "B60x70") == "BEAM_LIKELY"
    assert adapter.classify_frame_object("KIRIS12", "X") == "BEAM_LIKELY"
    assert adapter.classify_frame_object("C5", "C60x60") == "COLUMN_LIKELY"
    assert adapter.classify_frame_object("KOLON1", "X") == "COLUMN_LIKELY"
    assert adapter.classify_frame_object("X1", "Unknown") == "UNKNOWN"


def test_filter_frame_objects_for_beam_ui_defaults_to_beams_only() -> None:
    records = [
        {"label": "B35", "section": "B60x70"},
        {"label": "C5", "section": "C60x60"},
        {"label": "X", "section": "?"},
    ]

    filtered = adapter.filter_frame_objects_for_beam_ui(records)

    assert [row["frame_classification"] for row in filtered] == ["BEAM_LIKELY"]


def test_no_engineering_formula_in_ui_source() -> None:
    combined = (
        Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")
        + "\n"
        + Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py").read_text(encoding="utf-8-sig")
    )
    forbidden = ["rho_min =", "As_required =", "Mpr =", "Ve_capacity =", "s = Asw"]
    for term in forbidden:
        assert term not in combined


def test_no_top_level_com_imports() -> None:
    source = Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py").read_text(encoding="utf-8-sig")
    top = source.split("def _safe_com_initialize", 1)[0]
    assert "import comtypes" not in top
    assert "from comtypes" not in top
    assert "import pythoncom" not in top
