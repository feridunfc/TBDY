from __future__ import annotations

from pathlib import Path

from tbdy_engine.archx import (
    CanonicalSnapshot,
    DesignBasis,
    Story,
    build_story_workbench_cell,
    evaluate_story_drift,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"


def _snapshot(
    *,
    height_mm: float | None = 3000,
    drift_max_mm: float | None = 30,
    drift_limit: float | None = 0.02,
    with_design_basis: bool = True,
) -> CanonicalSnapshot:
    return CanonicalSnapshot(
        sections={},
        beams={},
        columns={},
        stories={"S1": Story(story_id="S1", height_mm=height_mm, drift_max_mm=drift_max_mm)},
        design_basis=DesignBasis(drift_limit=drift_limit) if with_design_basis else None,
    )


def _sub_statuses(result) -> dict[str, str]:
    return {sub.step_id: sub.status for sub in result.sub_checks}


def test_ok_case_and_workbench_cell():
    result = evaluate_story_drift(_snapshot(height_mm=3000, drift_max_mm=30, drift_limit=0.02), "S1")
    cell = build_story_workbench_cell(result)

    assert result.check_id == "story_drift"
    assert result.check_family == "global_check"
    assert result.element_type == "STORY"
    assert result.status == "OK"
    assert result.evaluation_level == "DESIGN_LEVEL"
    assert result.value == 0.01
    assert result.limit == 0.02
    assert result.ratio == 0.5
    assert _sub_statuses(result) == {"story_drift_ratio": "OK"}
    assert result.evidence.evidence_type == "canonical_model"
    assert cell.status == "OK"
    assert cell.input_panel == result.evidence.source_values
    assert cell.formula_panel == [sub.formula_trace for sub in result.sub_checks]
    assert cell.result_panel["value"] == result.value
    assert cell.result_panel["limit"] == result.limit


def test_fail_case():
    result = evaluate_story_drift(_snapshot(height_mm=3000, drift_max_mm=75, drift_limit=0.02), "S1")

    assert result.status == "FAIL"
    assert result.value == 0.025
    assert result.limit == 0.02
    assert result.ratio == 1.25
    assert _sub_statuses(result) == {"story_drift_ratio": "FAIL"}
    assert result.message == "Göreli kat ötelemesi sınırı aşılmış."


def test_boundary_case_is_ok():
    result = evaluate_story_drift(_snapshot(height_mm=3000, drift_max_mm=60, drift_limit=0.02), "S1")

    assert result.status == "OK"
    assert result.value == 0.02
    assert result.limit == 0.02
    assert result.ratio == 1.0
    assert _sub_statuses(result) == {"story_drift_ratio": "OK"}


def test_missing_story_returns_no_data():
    result = evaluate_story_drift(_snapshot(), "UNKNOWN")

    assert result.status == "NO_DATA"
    assert result.evaluation_level == "NO_DATA"
    assert result.evidence.evidence_type == "missing_required_input"
    assert "story" in result.evidence.missing_inputs


def test_missing_design_basis_returns_no_data():
    result = evaluate_story_drift(_snapshot(with_design_basis=False), "S1")

    assert result.status == "NO_DATA"
    assert result.evidence.evidence_type == "missing_required_input"
    assert "design_basis" in result.evidence.missing_inputs


def test_missing_height_returns_no_data():
    result = evaluate_story_drift(_snapshot(height_mm=None, drift_max_mm=30, drift_limit=0.02), "S1")

    assert result.status == "NO_DATA"
    assert "story.height_mm" in result.evidence.missing_inputs


def test_missing_drift_returns_no_data():
    result = evaluate_story_drift(_snapshot(height_mm=3000, drift_max_mm=None, drift_limit=0.02), "S1")

    assert result.status == "NO_DATA"
    assert "story.drift_max_mm" in result.evidence.missing_inputs


def test_missing_drift_limit_returns_no_data():
    result = evaluate_story_drift(_snapshot(height_mm=3000, drift_max_mm=30, drift_limit=None), "S1")

    assert result.status == "NO_DATA"
    assert "design_basis.drift_limit" in result.evidence.missing_inputs


def test_invalid_zero_height_returns_no_data_with_note():
    result = evaluate_story_drift(_snapshot(height_mm=0, drift_max_mm=30, drift_limit=0.02), "S1")

    assert result.status == "NO_DATA"
    assert "story.height_mm" in result.evidence.missing_inputs
    assert result.evidence.notes == ["Invalid input: story.height_mm must be greater than zero."]


def test_no_dynamic_code_execution_in_archx_sources():
    source = "\n".join(path.read_text(encoding="utf-8") for path in ARCHX_ROOT.glob("*.py"))

    assert "ev" + "al(" not in source
    assert "ex" + "ec(" not in source


def test_archx_import_isolation():
    forbidden_imports = (
        "tbdy_engine.runner_v2",
        "tbdy_engine.adapters",
        "tbdy_engine.reports",
        "tbdy_engine.contracts",
        "tbdy_engine.etabs",
        "tbdy_engine.design",
        "tbdy_engine.runtime",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in ARCHX_ROOT.glob("*.py"))

    for forbidden in forbidden_imports:
        assert forbidden not in source
