from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    import types

    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.etabs_single_beam_frameforce_runner import (
    _normalize_frame_force_rows,
    SingleBeamFrameForceError,
    extract_frameforce_envelope,
    run_live_etabs_single_beam_frameforce,
    run_live_etabs_single_beam_frameforce_from_env,
)


class FakeSetup:
    def __init__(self) -> None:
        self.selected: list[str] = []

    def DeselectAllCasesAndCombosForOutput(self) -> int:
        return 0

    def SetComboSelectedForOutput(self, name: str) -> int:
        self.selected.append(name)
        return 0


class FakeResults:
    def __init__(self, *, empty: bool = False) -> None:
        self.Setup = FakeSetup()
        self.empty = empty
        self.current_combo_index = 0

    def FrameForce(self, beam_name: str, item_type: int = 0) -> list[dict[str, float]]:
        if self.empty:
            return []
        combo = self.Setup.selected[-1] if self.Setup.selected else "G+Q"
        if combo == "G+Q":
            return [
                {"station": 0.0, "P": 5.0, "V2": 90.0, "M3": -100.0},
                {"station": 2500.0, "P": 7.0, "V2": 50.0, "M3": 80.0},
                {"station": 5000.0, "P": 4.0, "V2": -70.0, "M3": -95.0},
            ]
        return [
            {"station": 0.0, "P": 12.0, "V2": -110.0, "M3": -130.0},
            {"station": 2500.0, "P": 8.0, "V2": 55.0, "M3": 95.0},
            {"station": 5000.0, "P": 6.0, "V2": -75.0, "M3": -125.0},
        ]


class FakeFrameObj:
    def GetLabelFromName(self, name: str) -> tuple[int, str, str]:
        if name != "B1":
            return (1, "", "")
        return (0, "B1", "Story1")

    def GetSection(self, name: str) -> tuple[int, str, str]:
        if name != "B1":
            return (1, "", "")
        return (0, "B60x60", "")


class FakeFile:
    def GetModelFilename(self) -> str:
        return "fake_single_beam_model.edb"


class FakeSapModel:
    def __init__(self, *, empty_results: bool = False) -> None:
        self.FrameObj = FakeFrameObj()
        self.File = FakeFile()
        self.Results = FakeResults(empty=empty_results)


def _set_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "TBDY_LIVE_ETABS_FORCE_UNIT": "kN",
        "TBDY_LIVE_ETABS_MOMENT_UNIT": "kNm",
        "TBDY_LIVE_ETABS_LENGTH_UNIT": "mm",
        "TBDY_LIVE_ETABS_BW_MM": "600",
        "TBDY_LIVE_ETABS_H_MM": "600",
        "TBDY_LIVE_ETABS_D_MM": "550",
        "TBDY_LIVE_ETABS_COVER_MM": "40",
        "TBDY_LIVE_ETABS_LN_MM": "5000",
        "TBDY_LIVE_ETABS_FCK_MPA": "30",
        "TBDY_LIVE_ETABS_FCD_MPA": "20",
        "TBDY_LIVE_ETABS_FCTD_MPA": "1.27",
        "TBDY_LIVE_ETABS_FYK_MPA": "420",
        "TBDY_LIVE_ETABS_FYD_MPA": "365",
        "TBDY_LIVE_ETABS_FYWD_MPA": "365",
        "TBDY_LIVE_ETABS_STIRRUP_LEGS": "2",
        "TBDY_LIVE_ETABS_STIRRUP_DIAMETER_MM": "10",
        "TBDY_LIVE_ETABS_STIRRUP_SPACING_MM": "100",
        "TBDY_LIVE_ETABS_LONGITUDINAL_BAR_DIAMETER_MM": "16",
        "TBDY_LIVE_ETABS_TOP_SELECTED_AREA_CM2": "10",
        "TBDY_LIVE_ETABS_BOTTOM_SELECTED_AREA_CM2": "10",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_r7a_import_safe_without_etabs() -> None:
    source = Path("tbdy_engine/design/beams/etabs_single_beam_frameforce_runner.py").read_text(encoding="utf-8-sig")
    assert "import com" + "types" not in source
    assert "from com" + "types" not in source


def test_r7a_default_manual_test_env_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "TBDY_RUN_LIVE_ETABS_SMOKE",
        "TBDY_LIVE_ETABS_COM_PROVIDER",
        "TBDY_LIVE_ETABS_USE_OPEN_MODEL",
        "TBDY_LIVE_ETABS_BEAM_NAME",
        "TBDY_LIVE_ETABS_COMBOS",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        run_live_etabs_single_beam_frameforce_from_env()

    assert exc_info.value.stage == "env_gate"


def test_r7a_envelope_rules_with_fake_frameforce_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_overrides(monkeypatch)

    envelope = extract_frameforce_envelope(sap_model=FakeSapModel(), beam_name="B1", combos=["G+Q", "EX"])

    assert envelope["Vd_left_kN"].value == 110.0
    assert envelope["Vd_left_kN"].combo == "EX"
    assert envelope["Ve_left_kN"].value == 110.0
    assert envelope["Md_left_neg_kNm"].value == 130.0
    assert envelope["Md_left_neg_kNm"].combo == "EX"
    assert envelope["Md_mid_pos_kNm"].value == 95.0
    assert envelope["Md_right_neg_kNm"].value == 125.0
    assert envelope["axial_kN"].value == 12.0
    assert envelope["axial_kN"].station == 0.0


def test_r7a_empty_frameforce_rows_fail_with_force_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_overrides(monkeypatch)

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        extract_frameforce_envelope(sap_model=FakeSapModel(empty_results=True), beam_name="B1", combos=["G+Q"])

    assert exc_info.value.stage == "force_extract"


def test_r7a_missing_unit_declaration_fails_with_force_units(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_overrides(monkeypatch)
    monkeypatch.delenv("TBDY_LIVE_ETABS_FORCE_UNIT", raising=False)

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        extract_frameforce_envelope(sap_model=FakeSapModel(), beam_name="B1", combos=["G+Q"])

    assert exc_info.value.stage == "force_units"


def test_r7a_fake_frameforce_actions_route_to_beamcore_and_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    result = run_live_etabs_single_beam_frameforce(
        beam_name="B1",
        combos=["G+Q", "EX"],
        output_dir=tmp_path,
        sap_model=FakeSapModel(),
    )

    assert result["status"] == "OK"
    assert result["actions_source"] == "etabs_results"
    assert result["beam_core_status"] == "OK"
    assert result["check_count"] == 24
    assert result["json_path"].exists()
    assert result["md_path"].exists()

    summary = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert summary["actions_source"] == "etabs_results"
    assert summary["source_metadata"] if "source_metadata" in summary else True
    assert summary["capacity_design_checks"]["beam_shear_capacity_design_ve_le_vr"] == "executed"
    assert summary["capacity_design_checks"]["beam_shear_capacity_design_ve_le_085_vmax"] == "executed"


def test_r7a_report_wording(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    result = run_live_etabs_single_beam_frameforce(
        beam_name="B1",
        combos=["G+Q", "EX"],
        output_dir=tmp_path,
        sap_model=FakeSapModel(),
    )

    text = result["md_path"].read_text(encoding="utf-8")
    assert "BeamCore checks executed" in text
    assert "ACTIONS_SOURCE = ETABS_RESULTS" in text
    assert "beam designed" not in text.lower()
    assert "etabs validated" not in text.lower()
    assert "production ready" not in text.lower()
    assert "code compliance proven" not in text.lower()


def test_r7a_selected_beam_missing_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        run_live_etabs_single_beam_frameforce(
            beam_name="NO_SUCH_BEAM",
            combos=["G+Q"],
            output_dir=tmp_path,
            sap_model=FakeSapModel(),
        )

    assert exc_info.value.stage == "selected_beam_lookup"


def test_r7a_missing_design_override_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)
    monkeypatch.delenv("TBDY_LIVE_ETABS_D_MM", raising=False)

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        run_live_etabs_single_beam_frameforce(
            beam_name="B1",
            combos=["G+Q"],
            output_dir=tmp_path,
            sap_model=FakeSapModel(),
        )

    assert exc_info.value.stage == "geometry_extract"


def test_r7a_boundary_guard_has_no_forbidden_dependencies() -> None:
    source = Path("tbdy_engine/design/beams/etabs_single_beam_frameforce_runner.py").read_text(encoding="utf-8-sig")
    forbidden = (
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
        "import com" + "types",
        "from com" + "types",
    )
    for term in forbidden:
        assert term not in source


@pytest.mark.skipif(
    not (
        os.environ.get("TBDY_RUN_LIVE_ETABS_SMOKE") == "1"
        and os.environ.get("TBDY_LIVE_ETABS_COM_PROVIDER") == "1"
        and os.environ.get("TBDY_LIVE_ETABS_USE_OPEN_MODEL") == "1"
        and os.environ.get("TBDY_LIVE_ETABS_BEAM_NAME")
        and os.environ.get("TBDY_LIVE_ETABS_COMBOS")
    ),
    reason="Manual live ETABS single beam FrameForce bridge is opt-in.",
)
def test_manual_live_etabs_single_beam_frameforce_is_opt_in() -> None:
    try:
        result = run_live_etabs_single_beam_frameforce_from_env()
    except SingleBeamFrameForceError as exc:
        pytest.fail(f"failure_stage={exc.stage}; error={exc}")

    assert result["status"] == "OK"
    assert result["actions_source"] == "etabs_results"
    assert result["beam_core_status"] in {"OK", "FAIL", "NO_DATA"}
    assert result["json_path"].exists()
    assert result["md_path"].exists()

def test_r7a_normalizes_real_etabs_com_frameforce_shape() -> None:
    raw = [
        3,
        ("1", "1", "1"),
        (0, 2500, 5000),
        ("1", "1", "1"),
        (0, 2500, 5000),
        ("Grav_Ult",) * 3,
        ("Max",) * 3,
        (0, 0, 0),
        (1, 2, 3),
        (10, 20, -30),
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
        (-100, 50, -80),
        0,
    ]

    rows = _normalize_frame_force_rows(raw)

    assert rows[0]["station"] == 0.0
    assert rows[0]["p"] == 1.0
    assert rows[0]["v2"] == 10.0
    assert rows[0]["m3"] == -100.0
    assert rows[0]["load_case"] == "Grav_Ult"
    assert rows[1]["station"] == 2500.0
    assert rows[1]["p"] == 2.0
    assert rows[1]["v2"] == 20.0
    assert rows[1]["m3"] == 50.0
    assert rows[2]["station"] == 5000.0
    assert rows[2]["p"] == 3.0
    assert rows[2]["v2"] == -30.0
    assert rows[2]["m3"] == -80.0


def test_r7a_zero_real_etabs_com_frameforce_rows_fail_with_force_extract() -> None:
    raw = [0, (), (), (), (), (), (), (), (), (), (), (), (), (), 0]

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        _normalize_frame_force_rows(raw)

    assert exc_info.value.stage == "force_extract"
    assert "FrameForce returned zero rows" in exc_info.value.message


def test_r7a_combo_selection_nonzero_return_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_overrides(monkeypatch)

    class NonzeroSetup(FakeSetup):
        def SetComboSelectedForOutput(self, name: str) -> int:
            return 9

    class NonzeroResults(FakeResults):
        def __init__(self) -> None:
            super().__init__()
            self.Setup = NonzeroSetup()

    class NonzeroSapModel(FakeSapModel):
        def __init__(self) -> None:
            super().__init__()
            self.Results = NonzeroResults()

    with pytest.raises(SingleBeamFrameForceError) as exc_info:
        extract_frameforce_envelope(sap_model=NonzeroSapModel(), beam_name="B1", combos=["G+Q"])

    assert exc_info.value.stage == "force_extract"
    assert "combo selection failed" in exc_info.value.message

