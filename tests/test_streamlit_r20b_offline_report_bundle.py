from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import apps.streamlit_beam_design_app as app


@dataclass(frozen=True)
class FakeRegion:
    region: str
    As_design_required_cm2: float
    Md_kNm: float
    status: str


@dataclass(frozen=True)
class FakeShear:
    Vc_kN: float
    Vs_required_kN: float
    Asw_required_cm2_per_m: float
    s_required_mm: float
    status: str


@dataclass(frozen=True)
class FakeDesignResult:
    beam_id: str
    label: str
    regions: list[FakeRegion]
    shear_result: FakeShear


@dataclass(frozen=True)
class FakeVerificationCheck:
    check_id: str
    status: str
    provided_value: float
    demand_value: float
    unit: str


@dataclass(frozen=True)
class FakeVerificationResult:
    checks: list[FakeVerificationCheck]


@dataclass(frozen=True)
class FakeComparisonItem:
    field: str
    status: str
    difference_percent: float
    engine_value: float
    etabs_value: float


@dataclass(frozen=True)
class FakeComparisonResult:
    items: list[FakeComparisonItem]


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}


def _source() -> str:
    return Path("apps/streamlit_beam_design_app.py").read_text(encoding="utf-8-sig")


def _install_fake_session(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.session_state["beam_demand_set"] = {
        "beam_id": "R18_DEMO_BEAM",
        "label": "R18 Demo Beam",
        "Md_left_neg_kNm": 180.0,
    }
    fake_st.session_state["beam_design_result"] = FakeDesignResult(
        beam_id="R18_DEMO_BEAM",
        label="R18 Demo Beam",
        regions=[
            FakeRegion("left_top", 12.5, 180.0, "DEMO"),
            FakeRegion("mid_bottom", 9.8, 140.0, "DEMO"),
            FakeRegion("right_top", 13.2, 190.0, "DEMO"),
        ],
        shear_result=FakeShear(82.0, 45.0, 4.2, 120.0, "DEMO"),
    )
    fake_st.session_state["beam_verification_result"] = FakeVerificationResult(
        checks=[FakeVerificationCheck("top_as", "DEMO", 15.0, 12.5, "cm2")]
    )
    fake_st.session_state["etabs_comparison_result"] = FakeComparisonResult(
        items=[FakeComparisonItem("Md_left", "DEMO", 0.0, 180.0, 180.0)]
    )
    monkeypatch.setattr(app, "st", fake_st)


def test_r20b_helper_names_exist() -> None:
    source = _source()
    for name in [
        "_json_safe",
        "_write_json",
        "_markdown_table",
        "_build_offline_demo_report_payload",
        "_write_offline_demo_report_bundle",
        "_offline_demo_report_rows",
    ]:
        assert f"def {name}" in source


def test_r20b_required_report_file_names_exist() -> None:
    source = _source()
    for filename in [
        "workspace_evidence.json",
        "beam_demand_set.json",
        "beam_design_result.json",
        "beam_verification_result.json",
        "etabs_comparison_result.json",
        "offline_demo_report.md",
        "report_manifest.json",
    ]:
        assert filename in source


def test_r20b_report_headings_and_button_exist() -> None:
    source = _source()
    assert "Flexure / Moment Design by Region" in source
    assert "Shear Design" in source
    assert "# Offline Demo Beam Report" in source
    assert "Generate Offline Demo Report Bundle" in source


def test_r20b_write_bundle_contains_flexure_shear_verification_and_crosscheck(monkeypatch, tmp_path: Path) -> None:
    _install_fake_session(monkeypatch)

    result = app._write_offline_demo_report_bundle(tmp_path)

    expected = [
        "workspace_evidence.json",
        "beam_demand_set.json",
        "beam_design_result.json",
        "beam_verification_result.json",
        "etabs_comparison_result.json",
        "offline_demo_report.md",
        "report_manifest.json",
    ]
    for filename in expected:
        assert (tmp_path / filename).exists(), filename

    design = json.loads((tmp_path / "beam_design_result.json").read_text(encoding="utf-8"))
    regions = design["Flexure / Moment Design by Region"]["regions"]
    assert regions[0]["region"] == "left_top"
    assert regions[0]["As_required_cm2"] == 12.5
    assert regions[0]["Mu_check_kNm"] == 180.0
    assert design["Shear Design"]["Vc_kN"] == 82.0
    assert design["Shear Design"]["s_required_mm"] == 120.0

    markdown = (tmp_path / "offline_demo_report.md").read_text(encoding="utf-8")
    for text in [
        "# Offline Demo Beam Report",
        "Flexure / Moment Design by Region",
        "left_top",
        "12.5",
        "180.0",
        "Shear Design",
        "82.0",
        "120.0",
        "top_as",
        "Md_left",
    ]:
        assert text in markdown

    manifest = json.loads((tmp_path / "report_manifest.json").read_text(encoding="utf-8"))
    assert manifest["formats_supported"] == ["json", "md"]
    assert result["output_dir"] == tmp_path


def test_r20b_generated_reports_split_preserved_in_source() -> None:
    source = _source()
    assert 'st.tabs(["Evidence", "Generated Reports"])' in source
    assert "Generated Reports" in source
    assert "Workspace Evidence" in source


def test_r20b_no_forbidden_ui_formulas() -> None:
    source = _source()
    for term in ["rho_min =", "As_required =", "Mpr =", "Ve_capacity =", "s = Asw"]:
        assert term not in source


def test_r20b_no_top_level_com_imports() -> None:
    source = _source()
    for term in ["import comtypes", "from comtypes", "import pythoncom", "from pythoncom"]:
        assert term not in source


def test_r20b_target_output_folder_exists_in_source() -> None:
    assert "_local/streamlit_beam_design/offline_demo" in _source()
