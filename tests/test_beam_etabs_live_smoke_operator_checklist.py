from __future__ import annotations

import pathlib
import sys
import types
from pathlib import Path

if "tbdy_engine" not in sys.modules:
    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.etabs_live_smoke_harness import (
    is_live_etabs_smoke_enabled,
)

CHECKLIST_PATH = Path("docs/beam_core_live_etabs_smoke_checklist.md")

def _checklist_text() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8-sig")

def test_r1_5_operator_checklist_exists() -> None:
    assert CHECKLIST_PATH.exists()
    assert CHECKLIST_PATH.is_file()

def test_r1_5_operator_checklist_contains_required_terms() -> None:
    text = _checklist_text()
    required_terms = (
        "TBDY_RUN_LIVE_ETABS_SMOKE=1",
        "TBDY_LIVE_ETABS_MODEL_PATH",
        "core-reset-beam-design-kernel",
        "engine_report.json",
        "engine_report.xlsx",
        "BeamCoreResult",
        "beam_shear_capacity_design_ve_le_vr",
        "beam_shear_capacity_design_ve_le_085_vmax",
        "LIVE_ETABS_SMOKE = MANUALLY_OBSERVED_FOR_SELECTED_MODEL",
        "ETABS_VALIDATED = TRUE",
        "PRODUCTION_READY = TRUE",
        "RELEASE_READY = TRUE",
        "FULL_CODE_COMPLIANCE_CERTIFIED = TRUE",
        "Manual live smoke success alone does not permit merge to main",
        "Manual live smoke success alone does not permit production release",
    )
    for term in required_terms:
        assert term in text

def test_r1_5_operator_checklist_claim_boundaries_are_explicit() -> None:
    text = _checklist_text()
    assert "Allowed after a successful manual smoke on one selected model" in text
    assert "Forbidden even after one successful manual smoke" in text
    assert "ETABS_VALIDATED = TRUE" in text
    assert "PRODUCTION_READY = TRUE" in text
    assert "RELEASE_READY = TRUE" in text
    assert "FULL_CODE_COMPLIANCE_CERTIFIED = TRUE" in text

def test_r1_5_live_smoke_still_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("TBDY_RUN_LIVE_ETABS_SMOKE", raising=False)
    assert is_live_etabs_smoke_enabled() is False

def test_r1_5_operator_checklist_test_source_has_no_live_dependency_imports() -> None:
    source = pathlib.Path("tests/test_beam_etabs_live_smoke_operator_checklist.py").read_text(encoding="utf-8")
    forbidden = (
        "import com" + "types",
        "from com" + "types",
        "Sap" + "Model",
        "read_" + "etabs" + "_table_on_demand",
    )
    for term in forbidden:
        assert term not in source
