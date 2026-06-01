from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    import types

    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.etabs_live_com_provider import (
    LiveEtabsBeamPayloadProvider,
    LiveEtabsComProviderError,
    is_live_etabs_com_provider_enabled,
    live_etabs_com_environment_status,
)
from tbdy_engine.design.beams.etabs_live_smoke_harness import (
    run_etabs_beamcore_smoke_from_provider,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class FakeEtabsComProvider:
    def get_beam_payload(self) -> dict[str, object]:
        payload = json.loads(
            (FIXTURES_DIR / "etabs_static_export_beam_full.json").read_text(
                encoding="utf-8-sig"
            )
        )
        assert isinstance(payload, dict)
        payload = dict(payload)
        payload["source"] = {
            "kind": "live_etabs_com_provider_fake",
            "model_name": "fake_com_provider_fixture_model",
            "beam_name": "fake_beam",
        }
        return payload


def test_r6_live_com_provider_import_is_safe_without_etabs() -> None:
    source = Path("tbdy_engine/design/beams/etabs_live_com_provider.py").read_text(
        encoding="utf-8-sig"
    )

    assert "comtypes" not in sys.modules
    assert "import com" + "types" not in source
    assert "from com" + "types" not in source

    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import tbdy_engine.design.beams.etabs_live_com_provider; print('IMPORT_OK')",
        ],
        text=True,
    )
    assert output.strip() == "IMPORT_OK"


def test_r6_live_com_provider_default_env_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TBDY_RUN_LIVE_ETABS_SMOKE", raising=False)
    monkeypatch.delenv("TBDY_LIVE_ETABS_COM_PROVIDER", raising=False)
    monkeypatch.delenv("TBDY_LIVE_ETABS_MODEL_PATH", raising=False)

    assert is_live_etabs_com_provider_enabled() is False

    status = live_etabs_com_environment_status()
    assert status["smoke_enabled"] is False
    assert status["com_provider_enabled"] is False
    assert status["model_path_set"] is False
    assert status["model_path_exists"] is False


@pytest.mark.parametrize(
    "env_values",
    (
        {
            "TBDY_LIVE_ETABS_COM_PROVIDER": "1",
            "TBDY_LIVE_ETABS_MODEL_PATH": "C:/tmp/model.edb",
        },
        {
            "TBDY_RUN_LIVE_ETABS_SMOKE": "1",
            "TBDY_LIVE_ETABS_MODEL_PATH": "C:/tmp/model.edb",
        },
        {
            "TBDY_RUN_LIVE_ETABS_SMOKE": "1",
            "TBDY_LIVE_ETABS_COM_PROVIDER": "1",
        },
    ),
)
def test_r6_live_com_provider_requires_all_explicit_env_gates(
    monkeypatch: pytest.MonkeyPatch,
    env_values: dict[str, str],
) -> None:
    monkeypatch.delenv("TBDY_RUN_LIVE_ETABS_SMOKE", raising=False)
    monkeypatch.delenv("TBDY_LIVE_ETABS_COM_PROVIDER", raising=False)
    monkeypatch.delenv("TBDY_LIVE_ETABS_MODEL_PATH", raising=False)

    for key, value in env_values.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(LiveEtabsComProviderError) as exc_info:
        LiveEtabsBeamPayloadProvider.from_env()

    assert exc_info.value.stage in {"env_gate", "model_path"}


def test_r6_fake_com_provider_routes_through_beamcore_runner_artifacts(tmp_path: Path) -> None:
    result = run_etabs_beamcore_smoke_from_provider(
        provider=FakeEtabsComProvider(),
        output_dir=tmp_path,
    )

    assert result["status"] == "OK"
    assert result["beam_core_status"] == "OK"
    assert result["package_count"] == 1
    assert result["check_count"] == 24
    assert isinstance(result["json_path"], Path)
    assert result["json_path"].exists()
    assert isinstance(result["xlsx_path"], Path)
    assert result["xlsx_path"].exists()

    assert "beam_shear_capacity_design_ve_le_vr" in result["check_types"]
    assert "beam_shear_capacity_design_ve_le_085_vmax" in result["check_types"]


def test_r6_live_com_provider_source_guard_has_no_unguarded_dependencies() -> None:
    source = Path("tbdy_engine/design/beams/etabs_live_com_provider.py").read_text(
        encoding="utf-8-sig"
    )

    forbidden = (
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
        "import com" + "types",
        "from com" + "types",
        "Sap" + "Model",
    )

    for term in forbidden:
        assert term not in source


@pytest.mark.skipif(
    not (
        os.environ.get("TBDY_RUN_LIVE_ETABS_SMOKE") == "1"
        and os.environ.get("TBDY_LIVE_ETABS_COM_PROVIDER") == "1"
        and os.environ.get("TBDY_LIVE_ETABS_MODEL_PATH")
    ),
    reason="Manual live COM provider smoke is opt-in and requires model path.",
)
def test_manual_live_etabs_com_provider_is_opt_in(tmp_path: Path) -> None:
    try:
        provider = LiveEtabsBeamPayloadProvider.from_env()
        result = run_etabs_beamcore_smoke_from_provider(
            provider=provider,
            output_dir=tmp_path,
        )
    except LiveEtabsComProviderError as exc:
        pytest.fail(f"failure_stage={exc.stage}; error={exc.message}")

    assert result["status"] == "OK"
    assert "beam_shear_capacity_design_ve_le_vr" in result["check_types"]
    assert "beam_shear_capacity_design_ve_le_085_vmax" in result["check_types"]
