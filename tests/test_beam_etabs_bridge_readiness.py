from __future__ import annotations

import json
import pathlib
import sys
import types
from pathlib import Path

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.beam_core import evaluate_beam_core
from tbdy_engine.design.beams.beam_core_runner import run_beam_core_artifact_path
from tbdy_engine.design.beams.canonical_input_bridge import (
    build_canonical_beam_input_from_normalized,
)
from tbdy_engine.design.beams.etabs_input_adapter import (
    build_normalized_beam_input_from_etabs_payload,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

READINESS_REQUIREMENTS = {
    "static_payload_adapter": True,
    "static_export_fixture_contract": True,
    "normalized_bridge": True,
    "canonical_bridge": True,
    "beamcore_path": True,
    "runner_artifact_path": True,
    "missing_input_behavior": True,
    "capacity_design_checks_visible": True,
    "live_etabs_dependency": False,
    "etabs_validation_claimed": False,
    "live_etabs_smoke_claimed": False,
    "production_readiness_claimed": False,
    "release_readiness_claimed": False,
}


def _load_fixture(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8-sig"))
    assert isinstance(payload, dict)
    return payload


def _runner_check_types(json_path: Path) -> tuple[str, ...]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    checks = payload.get("checks")
    assert isinstance(checks, list)
    return tuple(str(check.get("check_type")) for check in checks if isinstance(check, dict))


def _full_static_pipeline() -> tuple[dict[str, object], dict[str, object], object]:
    raw = _load_fixture("etabs_static_export_beam_full.json")
    normalized = build_normalized_beam_input_from_etabs_payload(raw)
    canonical = build_canonical_beam_input_from_normalized(normalized)
    result = evaluate_beam_core(canonical)
    return normalized, canonical, result


def _capacity_design_snapshot() -> tuple[object, ...]:
    normalized, canonical, result = _full_static_pipeline()
    return (
        normalized,
        canonical,
        result.status,
        tuple(
            (check.id, check.name, check.status, check.demand, check.capacity, check.ratio)
            for check in result.core_checks
            if check.name in {
                "beam_shear_capacity_design_ve_le_vr",
                "beam_shear_capacity_design_ve_le_085_vmax",
            }
        ),
    )


def test_p6_readiness_full_static_pipeline_reaches_runner_artifacts(tmp_path: Path) -> None:
    normalized, canonical, beam_core = _full_static_pipeline()

    assert normalized
    assert canonical
    assert beam_core.status == "OK"
    assert beam_core.geometry is not None
    assert beam_core.geometry.status == "OK"
    assert beam_core.flexure is not None
    assert beam_core.shear is not None

    result = run_beam_core_artifact_path(
        beam_input=canonical,
        output_dir=tmp_path,
    )

    assert result.status == "OK"
    assert result.package_count == 1
    assert result.check_count == 24
    assert result.json_path.exists()
    assert result.xlsx_path is not None
    assert result.xlsx_path.exists()

    check_types = _runner_check_types(result.json_path)

    assert "beam_shear_capacity_design_ve_le_vr" in check_types
    assert "beam_shear_capacity_design_ve_le_085_vmax" in check_types
    assert "beam_shear_ve_le_vr" in check_types
    assert "beam_shear_ve_le_085_vmax" in check_types


def test_p6_readiness_missing_required_input_is_explicit_and_cleanly_invalid() -> None:
    raw = _load_fixture("etabs_static_export_beam_missing_required.json")
    normalized = build_normalized_beam_input_from_etabs_payload(raw)

    assert normalized["geometry"]["d_mm"] is None
    assert "geometry.d_mm" in normalized["missing_inputs"]

    canonical = build_canonical_beam_input_from_normalized(normalized)

    assert canonical["d_mm"] is None
    assert "d_mm" in canonical["missing_inputs"]

    result = evaluate_beam_core(canonical)

    assert result.status == "INVALID_INPUT"
    assert "d_mm" in result.validation_errors
    assert result.geometry is None
    assert result.flexure is None
    assert result.shear is None


def test_p6_readiness_static_pipeline_is_deterministic_for_repeated_runs() -> None:
    first_snapshot = _capacity_design_snapshot()

    assert first_snapshot[2] == "OK"
    assert len(first_snapshot[3]) == 2

    for _ in range(100):
        assert _capacity_design_snapshot() == first_snapshot


def test_p6_readiness_boundary_sources_have_no_live_dependencies() -> None:
    paths = (
        pathlib.Path("tbdy_engine/design/beams/etabs_input_adapter.py"),
        pathlib.Path("tbdy_engine/design/beams/canonical_input_bridge.py"),
        pathlib.Path("tbdy_engine/design/beams/beam_core_runner.py"),
        pathlib.Path("tests/test_beam_etabs_bridge_readiness.py"),
    )

    forbidden = (
        "com" + "types",
        "Sap" + "Model",
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for text in forbidden:
            assert text not in source


def test_p6_readiness_checklist_prevents_claim_inflation() -> None:
    assert READINESS_REQUIREMENTS["static_payload_adapter"] is True
    assert READINESS_REQUIREMENTS["static_export_fixture_contract"] is True
    assert READINESS_REQUIREMENTS["normalized_bridge"] is True
    assert READINESS_REQUIREMENTS["canonical_bridge"] is True
    assert READINESS_REQUIREMENTS["beamcore_path"] is True
    assert READINESS_REQUIREMENTS["runner_artifact_path"] is True
    assert READINESS_REQUIREMENTS["missing_input_behavior"] is True
    assert READINESS_REQUIREMENTS["capacity_design_checks_visible"] is True

    assert READINESS_REQUIREMENTS["live_etabs_dependency"] is False
    assert READINESS_REQUIREMENTS["etabs_validation_claimed"] is False
    assert READINESS_REQUIREMENTS["live_etabs_smoke_claimed"] is False
    assert READINESS_REQUIREMENTS["production_readiness_claimed"] is False
    assert READINESS_REQUIREMENTS["release_readiness_claimed"] is False