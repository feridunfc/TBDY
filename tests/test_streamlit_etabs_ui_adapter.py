from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    import types

    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.streamlit_etabs_ui_adapter import (
    run_story_beam_checks_from_ui,
    DEFAULT_DESIGN_INPUTS,
    build_design_overrides_from_ui,
    choose_default_combos,
    filter_selected_beams,
    get_etabs_status,
    list_available_combos,
    list_available_stories,
    list_story_beams,
)


class FakeFrameObj:
    def GetNameList(self) -> tuple[int, tuple[str, ...], int]:
        return (4, ("1", "2", "3", "4"), 0)

    def GetLabelFromName(self, name: str) -> list[object]:
        mapping = {
            "1": ["B35", "+9.00", 0],
            "2": ["B22", "+9.00", 0],
            "3": ["B39", "+6.00", 0],
            "4": ["B97", "+9.00", 0],
        }
        return mapping[name]

    def GetSection(self, name: str) -> list[object]:
        return ["B60x70", "", 0]


class FakeRespCombo:
    def GetNameList(self) -> list[object]:
        return [2, ("Grav_Ult", "Cap_SeisX"), 0]


class FakeLoadCases:
    def GetNameList(self) -> list[object]:
        return [1, ("Dead",), 0]


class FakeFile:
    def GetModelFilename(self) -> str:
        return "fake_ui_model.edb"


class FakeSapModel:
    def __init__(self) -> None:
        self.FrameObj = FakeFrameObj()
        self.RespCombo = FakeRespCombo()
        self.LoadCases = FakeLoadCases()
        self.File = FakeFile()


def test_list_stories_from_fake_frame_objects() -> None:
    assert list_available_stories(FakeSapModel()) == ["+6.00", "+9.00"]


def test_list_combos_from_fake_response_combo() -> None:
    assert list_available_combos(FakeSapModel()) == ["Grav_Ult", "Cap_SeisX"]


def test_list_beams_on_selected_story() -> None:
    beams = list_story_beams(FakeSapModel(), "+9.00")

    assert [beam["object_name"] for beam in beams] == ["1", "2", "4"]
    assert [beam["label"] for beam in beams] == ["B35", "B22", "B97"]
    assert all(beam["section"] == "B60x70" for beam in beams)


def test_build_env_override_dict_from_defaults() -> None:
    overrides = build_design_overrides_from_ui(DEFAULT_DESIGN_INPUTS)

    assert overrides["TBDY_LIVE_ETABS_BW_MM"] == "600"
    assert overrides["TBDY_LIVE_ETABS_FORCE_UNIT"] == "kN"
    assert overrides["TBDY_LIVE_ETABS_TOP_SELECTED_AREA_CM2"] == "10"


def test_selected_beams_filter() -> None:
    beams = list_story_beams(FakeSapModel(), "+9.00")

    selected = filter_selected_beams(beams, ["2", "4"])

    assert [beam["object_name"] for beam in selected] == ["2", "4"]


def test_choose_default_combos_prefers_known_names() -> None:
    assert choose_default_combos(["A", "Grav_Ult", "Cap_SeisX"]) == ["Grav_Ult", "Cap_SeisX"]
    assert choose_default_combos(["A", "B", "C"]) == ["A", "B"]


def test_offline_status_returns_offline_on_attach_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import tbdy_engine.design.beams.streamlit_etabs_ui_adapter as adapter

    def fail_attach() -> object:
        raise RuntimeError("etabs_attach: fake failure")

    monkeypatch.setattr(adapter, "attach_to_open_etabs", fail_attach)

    status = get_etabs_status()

    assert status["status"] == "OFFLINE"
    assert status["stage"] == "etabs_attach"

def test_ui_single_combo_uses_single_beam_path_without_requiring_r7b_combo_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import tbdy_engine.design.beams.streamlit_etabs_ui_adapter as adapter

    calls: list[dict[str, object]] = []

    def fake_single_runner(*, beam_name: str, combos: list[str], output_dir: Path, sap_model: object) -> dict[str, object]:
        calls.append({"beam_name": beam_name, "combos": combos, "output_dir": output_dir})
        return {
            "beam_core_status": "OK",
            "check_count": 24,
            "summary": {
                "actions": {
                    "Vd_left_kN": 1,
                    "Ve_left_kN": 1,
                    "Md_left_neg_kNm": 1,
                    "Md_mid_pos_kNm": 1,
                    "Md_right_neg_kNm": 1,
                    "axial_kN": 0,
                },
                "governing": {"Ve_left_kN": {"combo": combos[0], "station": 0.0}},
                "capacity_design_checks": {
                    "beam_shear_capacity_design_ve_le_vr": "executed",
                    "beam_shear_capacity_design_ve_le_085_vmax": "executed",
                },
                "artifact_paths": {
                    "json": str(output_dir / "engine_report.json"),
                    "xlsx": str(output_dir / "engine_report.xlsx"),
                },
            },
        }

    def fail_batch_runner(**kwargs: object) -> dict[str, object]:
        raise AssertionError("R7B batch runner should not be used for single-combo UI runs")

    monkeypatch.setattr(adapter, "run_live_etabs_single_beam_frameforce", fake_single_runner)
    monkeypatch.setattr(adapter, "run_live_etabs_story_beam_batch", fail_batch_runner)

    result = run_story_beam_checks_from_ui(
        sap_model=FakeSapModel(),
        story="+9.00",
        combos=["Grav_Ult"],
        selected_object_names=["1", "2"],
        design_values=DEFAULT_DESIGN_INPUTS,
        output_dir=tmp_path,
        max_beams=10,
    )

    assert result["status"] == "OK"
    assert result["run_mode"] == "SINGLE_COMBO_FRAMEFORCE_CHECKS_EXECUTED"
    assert result["selected_combos_count"] == 1
    assert result["summary"]["action_envelope_selection"] == "single_combo_no_multi_combo_envelope"
    assert result["summary"]["failures"] == []
    assert [call["beam_name"] for call in calls] == ["1", "2"]
    assert result["json_path"].exists()
    assert result["md_path"].exists()


def test_ui_multi_combo_still_uses_r7b_batch_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import tbdy_engine.design.beams.streamlit_etabs_ui_adapter as adapter

    calls: list[dict[str, object]] = []

    def fake_batch_runner(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {
            "status": "OK",
            "selected_story": kwargs["story"],
            "selected_combos": kwargs["combos"],
            "actions_source": "etabs_results",
            "beam_count_discovered": 2,
            "beam_count_processed": 2,
            "beam_count_failed": 0,
            "summary": {"beams": []},
        }

    def fail_single_runner(**kwargs: object) -> dict[str, object]:
        raise AssertionError("R7A single runner should not be used for multi-combo UI runs")

    monkeypatch.setattr(adapter, "run_live_etabs_story_beam_batch", fake_batch_runner)
    monkeypatch.setattr(adapter, "run_live_etabs_single_beam_frameforce", fail_single_runner)

    result = run_story_beam_checks_from_ui(
        sap_model=FakeSapModel(),
        story="+9.00",
        combos=["Grav_Ult", "Cap_SeisX"],
        selected_object_names=["1", "2"],
        design_values=DEFAULT_DESIGN_INPUTS,
        output_dir=tmp_path,
        max_beams=10,
    )

    assert result["status"] == "OK"
    assert calls
    assert calls[0]["combos"] == ["Grav_Ult", "Cap_SeisX"]

