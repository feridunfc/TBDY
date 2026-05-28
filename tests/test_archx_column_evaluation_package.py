from __future__ import annotations

from pathlib import Path

from tbdy_engine.archx import (
    CanonicalSnapshot,
    CheckResult,
    Column,
    Section,
    column_geometry_package_to_check_results,
    evaluate_column_geometry,
    evaluate_column_geometry_package,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"


def _snapshot(width: float | None, depth: float | None, *, section_id: str = "S1") -> CanonicalSnapshot:
    return CanonicalSnapshot(
        sections={section_id: Section(section_id=section_id, width_mm=width, depth_mm=depth)},
        beams={},
        columns={
            "C101": Column(
                element_id="C101",
                label="C101",
                story_id="5",
                section_id=section_id,
            )
        },
    )


def _step_statuses(package) -> dict[str, str]:
    return {step.step_id: step.status for step in package.outputs[0].steps}


def test_column_geometry_package_ok():
    package = evaluate_column_geometry_package(_snapshot(350, 350), "C101")
    output = package.outputs[0]

    assert package.status == "OK"
    assert package.evaluation_id == "column_geometry"
    assert package.evaluation_type == "COLUMN_GEOMETRY"
    assert len(package.outputs) == 1
    assert output.measurements["width_mm"] == 350
    assert output.measurements["depth_mm"] == 350
    assert output.measurements["min_edge_mm"] == 350
    assert output.measurements["area_mm2"] == 122500
    assert output.measurements["aspect_ratio"] == 1.0
    assert _step_statuses(package) == {
        "column_min_edge": "OK",
        "column_min_area": "OK",
        "column_aspect_ratio": "OK",
    }


def test_column_geometry_package_fail_min_edge():
    package = evaluate_column_geometry_package(_snapshot(250, 500), "C101")

    assert package.status == "FAIL"
    assert _step_statuses(package) == {
        "column_min_edge": "FAIL",
        "column_min_area": "OK",
        "column_aspect_ratio": "OK",
    }


def test_column_geometry_package_fail_aspect_ratio():
    package = evaluate_column_geometry_package(_snapshot(300, 1000), "C101")

    assert package.status == "FAIL"
    assert _step_statuses(package) == {
        "column_min_edge": "OK",
        "column_min_area": "OK",
        "column_aspect_ratio": "FAIL",
    }


def test_column_geometry_package_no_data_missing_section():
    snapshot = CanonicalSnapshot(
        sections={},
        beams={},
        columns={"C101": Column(element_id="C101", label="C101", story_id="5", section_id="UNKNOWN")},
    )

    package = evaluate_column_geometry_package(snapshot, "C101")

    assert package.status == "NO_DATA"
    assert package.evidence.evidence_type == "missing_required_input"
    assert "section" in package.evidence.missing_inputs
    assert package.outputs[0].status == "NO_DATA"
    assert "section" in package.outputs[0].evidence.missing_inputs


def test_adapter_package_to_check_result_ok():
    package = evaluate_column_geometry_package(_snapshot(350, 350), "C101")

    results = column_geometry_package_to_check_results(package)

    assert len(results) == 1
    result = results[0]
    assert result.check_id == "column_geometry"
    assert result.status == "OK"
    assert [sub.step_id for sub in result.sub_checks] == [
        "column_min_edge",
        "column_min_area",
        "column_aspect_ratio",
    ]
    assert [sub.status for sub in result.sub_checks] == ["OK", "OK", "OK"]


def test_public_evaluate_column_geometry_backward_compatible():
    result = evaluate_column_geometry(_snapshot(350, 350), "C101")

    assert isinstance(result, CheckResult)
    assert result.check_id == "column_geometry"
    assert result.check_family == "column_design"
    assert result.element_type == "COLUMN"
    assert result.element_label == "C101"
    assert result.story == "5"
    assert result.status == "OK"
    assert result.evaluation_level == "DESIGN_LEVEL"
    assert result.value is None
    assert result.limit is None
    assert result.unit == "mm"
    assert result.report_section == "columns"
    assert result.evidence.evidence_type == "canonical_model"


def test_forbidden_imports_absent_in_modified_sources():
    modified_files = [ARCHX_ROOT / "column_geometry.py", ARCHX_ROOT / "__init__.py"]
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
