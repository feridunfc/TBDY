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

from tbdy_engine.design.beams.etabs_story_beam_batch_runner import (
    _frame_label_and_story,
    _frame_names,
    StoryBeamBatchError,
    discover_story_beams,
    run_live_etabs_story_beam_batch,
    run_live_etabs_story_beam_batch_from_env,
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
    def __init__(self, *, empty_for: set[str] | None = None) -> None:
        self.Setup = FakeSetup()
        self.empty_for = empty_for or set()

    def FrameForce(self, beam_name: str, item_type: int = 0) -> list[dict[str, float]]:
        combo = self.Setup.selected[-1] if self.Setup.selected else "G+Q"
        if beam_name in self.empty_for:
            return []
        beam_factor = {"B1": 1.0, "B2": 0.9, "B3": 0.8, "B4": 0.7}.get(beam_name, 0.6)
        combo_factor = 1.0 if combo == "G+Q" else 1.25
        scale = beam_factor * combo_factor
        return [
            {"station": 0.0, "P": 5.0 * scale, "V2": 90.0 * scale, "M3": -100.0 * scale},
            {"station": 2500.0, "P": 7.0 * scale, "V2": 50.0 * scale, "M3": 80.0 * scale},
            {"station": 5000.0, "P": 4.0 * scale, "V2": -70.0 * scale, "M3": -95.0 * scale},
        ]


class FakeFrameObj:
    def __init__(self, story_map: dict[str, str] | None = None) -> None:
        self.story_map = story_map or {
            "B1": "+9.00",
            "B2": "+9.00",
            "B3": "+9.00",
            "B4": "+9.00",
            "B5": "+6.00",
        }

    def GetNameList(self) -> tuple[int, list[str]]:
        return (0, list(self.story_map.keys()))

    def GetLabelFromName(self, name: str) -> tuple[int, str, str]:
        return (0, f"LABEL_{name}", self.story_map.get(name, ""))

    def GetSection(self, name: str) -> tuple[int, str, str]:
        return (0, "B60x60", "")


class FakeFile:
    def GetModelFilename(self) -> str:
        return "fake_story_batch_model.edb"


class FakeSapModel:
    def __init__(self, *, story_map: dict[str, str] | None = None, empty_for: set[str] | None = None) -> None:
        self.FrameObj = FakeFrameObj(story_map=story_map)
        self.File = FakeFile()
        self.Results = FakeResults(empty_for=empty_for)


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


def test_r7b_import_safe_without_etabs() -> None:
    source = Path("tbdy_engine/design/beams/etabs_story_beam_batch_runner.py").read_text(encoding="utf-8-sig")
    assert "import com" + "types" not in source
    assert "from com" + "types" not in source


def test_r7b_default_manual_env_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "TBDY_RUN_LIVE_ETABS_SMOKE",
        "TBDY_LIVE_ETABS_COM_PROVIDER",
        "TBDY_LIVE_ETABS_USE_OPEN_MODEL",
        "TBDY_LIVE_ETABS_STORY",
        "TBDY_LIVE_ETABS_COMBOS",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(StoryBeamBatchError) as exc_info:
        run_live_etabs_story_beam_batch_from_env()

    assert exc_info.value.stage == "env_gate"


def test_r7b_story_filtering_fake_sapmodel() -> None:
    beams = discover_story_beams(sap_model=FakeSapModel(), story="+9.00")

    assert [beam["object_name"] for beam in beams] == ["B1", "B2", "B3", "B4"]
    assert all(beam["story"] == "+9.00" for beam in beams)


def test_r7b_minimum_beam_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)
    sap_model = FakeSapModel(story_map={"B1": "+9.00", "B2": "+6.00"})

    with pytest.raises(StoryBeamBatchError) as exc_info:
        run_live_etabs_story_beam_batch(story="+9.00", combos=["G+Q", "EX"], output_dir=tmp_path, sap_model=sap_model)

    assert exc_info.value.stage == "story_beam_discovery"


def test_r7b_two_combo_envelope_batch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    result = run_live_etabs_story_beam_batch(
        story="+9.00",
        combos=["G+Q", "EX"],
        output_dir=tmp_path,
        sap_model=FakeSapModel(),
    )

    assert result["status"] == "OK"
    assert result["beam_count_discovered"] == 4
    assert result["beam_count_processed"] == 4
    assert result["actions_source"] == "etabs_results"
    assert result["json_path"].exists()
    assert result["md_path"].exists()

    summary = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert summary["actions_source"] == "etabs_results"
    assert len(summary["beams"]) >= 3
    for beam in summary["beams"]:
        assert beam["BeamCore checks executed"] is True
        assert beam["capacity_design_check_statuses"]["beam_shear_capacity_design_ve_le_vr"] == "executed"
        assert beam["capacity_design_check_statuses"]["beam_shear_capacity_design_ve_le_085_vmax"] == "executed"
        assert beam["governing"]["Ve_left_kN"]["combo"] in {"G+Q", "EX"}


def test_r7b_partial_beam_failure_still_passes_if_minimum_processed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    result = run_live_etabs_story_beam_batch(
        story="+9.00",
        combos=["G+Q", "EX"],
        output_dir=tmp_path,
        sap_model=FakeSapModel(empty_for={"B4"}),
        min_beams=3,
    )

    assert result["status"] == "OK"
    assert result["beam_count_processed"] == 3
    assert result["beam_count_failed"] == 1
    assert result["summary"]["failures"][0]["stage"] == "force_extract"


def test_r7b_fails_if_too_few_processed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    with pytest.raises(StoryBeamBatchError) as exc_info:
        run_live_etabs_story_beam_batch(
            story="+9.00",
            combos=["G+Q", "EX"],
            output_dir=tmp_path,
            sap_model=FakeSapModel(empty_for={"B2", "B3"}),
            min_beams=3,
        )

    assert exc_info.value.stage in {"force_extract", "batch_minimum_processed"}


def test_r7b_report_wording(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_overrides(monkeypatch)

    result = run_live_etabs_story_beam_batch(
        story="+9.00",
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


def test_r7b_boundary_guard_has_no_forbidden_dependencies() -> None:
    source = Path("tbdy_engine/design/beams/etabs_story_beam_batch_runner.py").read_text(encoding="utf-8-sig")
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
        and os.environ.get("TBDY_LIVE_ETABS_STORY")
        and os.environ.get("TBDY_LIVE_ETABS_COMBOS")
    ),
    reason="Manual live ETABS story beam batch is opt-in.",
)
def test_manual_live_etabs_story_beam_batch_is_opt_in() -> None:
    try:
        result = run_live_etabs_story_beam_batch_from_env()
    except StoryBeamBatchError as exc:
        pytest.fail(f"failure_stage={exc.stage}; error={exc}")

    assert result["status"] == "OK"
    assert result["beam_count_discovered"] >= int(os.environ.get("TBDY_LIVE_ETABS_MIN_BEAMS", "3"))
    assert result["beam_count_processed"] >= int(os.environ.get("TBDY_LIVE_ETABS_MIN_BEAMS", "3"))
    assert result["actions_source"] == "etabs_results"
    assert result["json_path"].exists()
    assert result["md_path"].exists()

class LiveShapeFrameObj:
    def GetNameList(self) -> list[object]:
        return [4, ("1", "2", "3", "4"), 0]

    def GetLabelFromName(self, name: str) -> list[object]:
        mapping = {
            "1": ["B35", "+9.00", 0],
            "2": ["B22", "+9.00", 0],
            "3": ["B39", "+9.00", 0],
            "4": ["B10", "+6.00", 0],
        }
        return mapping[name]

    def GetSection(self, name: str) -> list[object]:
        return ["B60x70", "", 0]


class LiveShapeSapModel:
    def __init__(self) -> None:
        self.FrameObj = LiveShapeFrameObj()
        self.File = FakeFile()
        self.Results = FakeResults()


def test_r7b_frame_names_supports_live_etabs_get_name_list_shape() -> None:
    assert _frame_names(LiveShapeSapModel()) == ["1", "2", "3", "4"]


def test_r7b_label_and_story_supports_live_etabs_shape() -> None:
    assert _frame_label_and_story(LiveShapeSapModel(), "1") == ("B35", "+9.00")


def test_r7b_story_filtering_supports_live_etabs_shapes() -> None:
    beams = discover_story_beams(sap_model=LiveShapeSapModel(), story="+9.00")

    assert [beam["object_name"] for beam in beams] == ["1", "2", "3"]
    assert [beam["label"] for beam in beams] == ["B35", "B22", "B39"]
    assert all(beam["story"] == "+9.00" for beam in beams)
    assert all(beam["section"] == "B60x70" for beam in beams)

