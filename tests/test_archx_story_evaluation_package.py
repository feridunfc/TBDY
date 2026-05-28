from __future__ import annotations

from pathlib import Path

from tbdy_engine.archx import (
    CanonicalSnapshot,
    CheckResult,
    DesignBasis,
    Story,
    evaluate_story_drift,
    evaluate_story_drift_package,
    story_drift_package_to_check_results,
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


def _step_statuses(package) -> dict[str, str]:
    return {step.step_id: step.status for step in package.outputs[0].steps}


def test_story_drift_package_ok():
    package = evaluate_story_drift_package(_snapshot(height_mm=3000, drift_max_mm=30, drift_limit=0.02), "S1")
    output = package.outputs[0]

    assert package.status == "OK"
    assert package.evaluation_id == "story_drift"
    assert package.evaluation_type == "STORY_DRIFT"
    assert len(package.outputs) == 1
    assert output.measurements["height_mm"] == 3000
    assert output.measurements["drift_max_mm"] == 30
    assert output.measurements["drift_limit"] == 0.02
    assert output.measurements["drift_ratio"] == 0.01
    assert output.measurements["usage_ratio"] == 0.5
    assert _step_statuses(package) == {"story_drift_ratio": "OK"}


def test_story_drift_package_fail():
    package = evaluate_story_drift_package(_snapshot(height_mm=3000, drift_max_mm=75, drift_limit=0.02), "S1")
    output = package.outputs[0]

    assert package.status == "FAIL"
    assert output.measurements["drift_ratio"] == 0.025
    assert output.measurements["usage_ratio"] == 1.25
    assert _step_statuses(package) == {"story_drift_ratio": "FAIL"}


def test_story_drift_package_boundary_ok():
    package = evaluate_story_drift_package(_snapshot(height_mm=3000, drift_max_mm=60, drift_limit=0.02), "S1")
    output = package.outputs[0]

    assert package.status == "OK"
    assert output.measurements["drift_ratio"] == 0.02
    assert output.measurements["usage_ratio"] == 1.0


def test_story_drift_package_no_data_missing_story():
    package = evaluate_story_drift_package(_snapshot(), "UNKNOWN")

    assert package.status == "NO_DATA"
    assert package.evidence.evidence_type == "missing_required_input"
    assert "story" in package.evidence.missing_inputs
    assert package.outputs[0].status == "NO_DATA"


def test_story_drift_package_no_data_missing_design_basis():
    package = evaluate_story_drift_package(_snapshot(with_design_basis=False), "S1")

    assert package.status == "NO_DATA"
    assert "design_basis" in package.evidence.missing_inputs


def test_story_drift_package_no_data_missing_drift_limit():
    package = evaluate_story_drift_package(_snapshot(drift_limit=None), "S1")

    assert package.status == "NO_DATA"
    assert "design_basis.drift_limit" in package.evidence.missing_inputs


def test_story_drift_package_no_data_zero_height():
    package = evaluate_story_drift_package(_snapshot(height_mm=0), "S1")

    assert package.status == "NO_DATA"
    assert "story.height_mm" in package.evidence.missing_inputs
    assert "Invalid input: story.height_mm must be greater than zero." in package.diagnostics


def test_adapter_package_to_check_result_ok():
    package = evaluate_story_drift_package(_snapshot(height_mm=3000, drift_max_mm=30, drift_limit=0.02), "S1")

    results = story_drift_package_to_check_results(package)

    assert len(results) == 1
    result = results[0]
    assert result.check_id == "story_drift"
    assert result.status == "OK"
    assert result.ratio == 0.5
    assert [sub.step_id for sub in result.sub_checks] == ["story_drift_ratio"]
    assert [sub.status for sub in result.sub_checks] == ["OK"]


def test_public_evaluate_story_drift_backward_compatible():
    result = evaluate_story_drift(_snapshot(height_mm=3000, drift_max_mm=30, drift_limit=0.02), "S1")

    assert isinstance(result, CheckResult)
    assert result.check_id == "story_drift"
    assert result.check_family == "global_check"
    assert result.element_type == "STORY"
    assert result.element_label == "S1"
    assert result.story == "S1"
    assert result.status == "OK"
    assert result.evaluation_level == "DESIGN_LEVEL"
    assert result.value == 0.01
    assert result.limit == 0.02
    assert result.unit == "ratio"
    assert result.report_section == "global"
    assert result.evidence.evidence_type == "canonical_model"


def test_forbidden_imports_absent_in_modified_sources():
    modified_files = [ARCHX_ROOT / "story_drift.py", ARCHX_ROOT / "__init__.py"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in modified_files)
    forbidden = (
        "tbdy_engine.etabs",
        "tbdy_engine.table_engine",
        "tbdy_engine.runner_v2",
        "tbdy_engine.adapters",
        "tbdy_engine.reports",
        "tbdy_engine.contracts",
        "win32com",
        "CheckAdapter",
    )

    for item in forbidden:
        assert item not in source
    assert "ev" + "al(" not in source
    assert "ex" + "ec(" not in source
