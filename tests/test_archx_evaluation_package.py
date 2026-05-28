from __future__ import annotations

from pathlib import Path

from tbdy_engine.archx import (
    Beam,
    CanonicalSnapshot,
    CheckResult,
    Section,
    beam_geometry_package_to_check_results,
    build_workbench_bundle,
    build_workbench_cell,
    evaluate_beam_geometry,
    evaluate_beam_geometry_package,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"


def _snapshot(width: float | None, depth: float | None, *, section_id: str = "S1") -> CanonicalSnapshot:
    return CanonicalSnapshot(
        sections={section_id: Section(section_id=section_id, width_mm=width, depth_mm=depth)},
        beams={
            "B101": Beam(
                element_id="B101",
                label="B101",
                story_id="5",
                section_id=section_id,
            )
        },
    )


def _step_statuses(package) -> dict[str, str]:
    return {step.step_id: step.status for step in package.outputs[0].steps}


def test_beam_geometry_package_ok():
    package = evaluate_beam_geometry_package(_snapshot(300, 500), "B101")
    output = package.outputs[0]

    assert package.status == "OK"
    assert package.evaluation_id == "beam_geometry"
    assert package.evaluation_type == "BEAM_GEOMETRY"
    assert len(package.outputs) == 1
    assert output.measurements["width_mm"] == 300
    assert output.measurements["depth_mm"] == 500
    assert output.measurements["width_ratio"] == 300 / 250
    assert output.measurements["depth_ratio"] == 500 / 300
    assert _step_statuses(package) == {"beam_width_min": "OK", "beam_height_min": "OK"}


def test_beam_geometry_package_fail_width():
    package = evaluate_beam_geometry_package(_snapshot(200, 500), "B101")

    assert package.status == "FAIL"
    assert _step_statuses(package) == {"beam_width_min": "FAIL", "beam_height_min": "OK"}


def test_beam_geometry_package_no_data_missing_section():
    snapshot = CanonicalSnapshot(
        sections={},
        beams={"B101": Beam(element_id="B101", label="B101", story_id="5", section_id="UNKNOWN")},
    )

    package = evaluate_beam_geometry_package(snapshot, "B101")

    assert package.status == "NO_DATA"
    assert package.evidence.evidence_type == "missing_required_input"
    assert "section" in package.evidence.missing_inputs
    assert package.outputs[0].status == "NO_DATA"
    assert "section" in package.outputs[0].evidence.missing_inputs


def test_adapter_package_to_check_result_ok():
    package = evaluate_beam_geometry_package(_snapshot(300, 500), "B101")

    results = beam_geometry_package_to_check_results(package)

    assert len(results) == 1
    result = results[0]
    assert result.check_id == "beam_geometry"
    assert result.status == "OK"
    assert result.ratio == min(300 / 250, 500 / 300)
    assert [sub.step_id for sub in result.sub_checks] == ["beam_width_min", "beam_height_min"]
    assert [sub.status for sub in result.sub_checks] == ["OK", "OK"]


def test_public_evaluate_beam_geometry_backward_compatible():
    result = evaluate_beam_geometry(_snapshot(300, 500), "B101")

    assert isinstance(result, CheckResult)
    assert result.check_id == "beam_geometry"
    assert result.check_family == "beam_design"
    assert result.element_type == "BEAM"
    assert result.element_label == "B101"
    assert result.story == "5"
    assert result.status == "OK"
    assert result.evaluation_level == "DESIGN_LEVEL"
    assert result.value is None
    assert result.limit is None
    assert result.unit == "mm"
    assert result.report_section == "beams"
    assert result.evidence.evidence_type == "canonical_model"


def test_workbench_bundle_still_works_with_beam_result():
    result = evaluate_beam_geometry(_snapshot(300, 500), "B101")
    cell = build_workbench_cell(result)

    bundle = build_workbench_bundle([result], [cell], run_id="core-1-test")

    assert bundle["bundle_version"] == "ARCH-X-WB-1"
    assert bundle["summary"]["total"] == 1
    assert bundle["summary"]["by_status"]["OK"] == 1
    assert bundle["index"]["by_check_id"] == {"beam_geometry": ["beam_geometry:B101:5"]}


def test_forbidden_imports_absent_in_modified_sources():
    modified_files = [
        ARCHX_ROOT / "evaluation.py",
        ARCHX_ROOT / "beam_geometry.py",
        ARCHX_ROOT / "__init__.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in modified_files)
    forbidden = (
        "tbdy_engine.etabs",
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
