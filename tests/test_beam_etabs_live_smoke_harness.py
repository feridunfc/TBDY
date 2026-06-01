from __future__ import annotations

import json
import pathlib
import sys
import types
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.etabs_live_smoke_harness import (
    is_live_etabs_smoke_enabled,
    run_etabs_beamcore_smoke_from_provider,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class StaticPayloadProvider:
    def __init__(self, fixture_name: str) -> None:
        self.fixture_name = fixture_name

    def get_beam_payload(self) -> dict[str, object]:
        payload = json.loads((FIXTURES_DIR / self.fixture_name).read_text(encoding="utf-8-sig"))
        assert isinstance(payload, dict)
        return payload


class RaisingPayloadProvider:
    def get_beam_payload(self) -> dict[str, object]:
        raise RuntimeError("static provider payload unavailable")


def _summary(result: dict[str, object]) -> tuple[object, ...]:
    return (
        result["status"],
        result["package_count"],
        result["check_count"],
        tuple(result["capacity_design_check_types"]),
        tuple(
            check_type
            for check_type in result["check_types"]
            if check_type in {
                "beam_shear_capacity_design_ve_le_vr",
                "beam_shear_capacity_design_ve_le_085_vmax",
            }
        ),
    )


def test_r1_live_smoke_harness_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TBDY_RUN_LIVE_ETABS_SMOKE", raising=False)

    assert is_live_etabs_smoke_enabled() is False


def test_r1_live_smoke_harness_env_gate_enables_only_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TBDY_RUN_LIVE_ETABS_SMOKE", "0")
    assert is_live_etabs_smoke_enabled() is False

    monkeypatch.setenv("TBDY_RUN_LIVE_ETABS_SMOKE", "true")
    assert is_live_etabs_smoke_enabled() is False

    monkeypatch.setenv("TBDY_RUN_LIVE_ETABS_SMOKE", "1")
    assert is_live_etabs_smoke_enabled() is True


def test_r1_static_provider_routes_payload_to_beamcore_runner_artifacts(tmp_path: Path) -> None:
    provider = StaticPayloadProvider("etabs_static_export_beam_full.json")

    result = run_etabs_beamcore_smoke_from_provider(
        provider=provider,
        output_dir=tmp_path,
    )

    assert result["status"] == "OK"
    assert result["beam_core_status"] == "OK"
    assert result["package_count"] == 1
    assert result["check_count"] == 24

    json_path = result["json_path"]
    xlsx_path = result["xlsx_path"]

    assert isinstance(json_path, Path)
    assert json_path.exists()
    assert isinstance(xlsx_path, Path)
    assert xlsx_path.exists()

    assert "beam_shear_capacity_design_ve_le_vr" in result["check_types"]
    assert "beam_shear_capacity_design_ve_le_085_vmax" in result["check_types"]
    assert result["capacity_design_check_types"] == (
        "beam_shear_capacity_design_ve_le_vr",
        "beam_shear_capacity_design_ve_le_085_vmax",
    )

    normalized = result["normalized"]
    canonical = result["canonical"]

    assert normalized["id"] == "B-P5-STATIC-EXPORT"
    assert canonical["beam_id"] == "B-P5-STATIC-EXPORT"


def test_r1_missing_payload_provider_error_is_explicit(tmp_path: Path) -> None:
    provider = RaisingPayloadProvider()

    with pytest.raises(RuntimeError, match="static provider payload unavailable"):
        run_etabs_beamcore_smoke_from_provider(
            provider=provider,
            output_dir=tmp_path,
        )


def test_r1_static_provider_smoke_is_deterministic(tmp_path: Path) -> None:
    provider = StaticPayloadProvider("etabs_static_export_beam_full.json")

    first = run_etabs_beamcore_smoke_from_provider(
        provider=provider,
        output_dir=tmp_path / "first",
    )
    first_summary = _summary(first)

    assert first_summary[0] == "OK"

    for index in range(20):
        current = run_etabs_beamcore_smoke_from_provider(
            provider=provider,
            output_dir=tmp_path / f"run_{index}",
        )
        assert _summary(current) == first_summary
        assert current["normalized"] == first["normalized"]
        assert current["canonical"] == first["canonical"]


def test_r1_harness_import_boundary_has_no_live_dependency_terms() -> None:
    harness_source = pathlib.Path("tbdy_engine/design/beams/etabs_live_smoke_harness.py").read_text(encoding="utf-8")
    test_source = pathlib.Path("tests/test_beam_etabs_live_smoke_harness.py").read_text(encoding="utf-8")

    forbidden = (
        "com" + "types",
        "Sap" + "Model",
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
    )

    for source in (harness_source, test_source):
        for text in forbidden:
            assert text not in source


@pytest.mark.skipif(
    not is_live_etabs_smoke_enabled(),
    reason="Manual live ETABS smoke is opt-in via TBDY_RUN_LIVE_ETABS_SMOKE=1.",
)
def test_manual_live_etabs_smoke_is_opt_in() -> None:
    pytest.skip("Manual live provider is intentionally not implemented in R1.")