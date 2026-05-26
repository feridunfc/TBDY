from __future__ import annotations

from pathlib import Path

from tbdy_engine.archx import (
    CanonicalSnapshot,
    Column,
    Section,
    build_column_workbench_cell,
    evaluate_column_geometry,
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


def _sub_statuses(result) -> dict[str, str]:
    return {sub.step_id: sub.status for sub in result.sub_checks}


def test_ok_300x500():
    result = evaluate_column_geometry(_snapshot(300, 500), "C101")

    assert result.check_id == "column_geometry"
    assert result.status == "OK"
    assert result.evaluation_level == "DESIGN_LEVEL"
    assert result.ratio == min(300 / 300, (300 * 500) / 90000, 4 / (500 / 300))
    assert result.value is None
    assert result.limit is None
    assert _sub_statuses(result) == {
        "column_min_edge": "OK",
        "column_min_area": "OK",
        "column_aspect_ratio": "OK",
    }
    assert result.evidence.evidence_type == "canonical_model"


def test_fail_min_edge_250x500():
    result = evaluate_column_geometry(_snapshot(250, 500), "C101")

    assert result.status == "FAIL"
    assert result.value is None
    assert result.limit is None
    assert _sub_statuses(result) == {
        "column_min_edge": "FAIL",
        "column_min_area": "OK",
        "column_aspect_ratio": "OK",
    }


def test_fail_area_300x250():
    result = evaluate_column_geometry(_snapshot(300, 250), "C101")

    assert result.status == "FAIL"
    assert _sub_statuses(result) == {
        "column_min_edge": "FAIL",
        "column_min_area": "FAIL",
        "column_aspect_ratio": "OK",
    }


def test_fail_aspect_ratio_300x1300():
    result = evaluate_column_geometry(_snapshot(300, 1300), "C101")

    assert result.status == "FAIL"
    assert _sub_statuses(result) == {
        "column_min_edge": "OK",
        "column_min_area": "OK",
        "column_aspect_ratio": "FAIL",
    }


def test_boundary_300x300_ok():
    result = evaluate_column_geometry(_snapshot(300, 300), "C101")

    assert result.status == "OK"
    assert result.ratio == 1.0
    assert _sub_statuses(result) == {
        "column_min_edge": "OK",
        "column_min_area": "OK",
        "column_aspect_ratio": "OK",
    }


def test_missing_column_no_data():
    result = evaluate_column_geometry(_snapshot(300, 500), "UNKNOWN")

    assert result.status == "NO_DATA"
    assert result.evaluation_level == "NO_DATA"
    assert result.evidence.evidence_type == "missing_required_input"
    assert "column" in result.evidence.missing_inputs


def test_missing_section_no_data():
    snapshot = CanonicalSnapshot(
        sections={},
        beams={},
        columns={"C101": Column(element_id="C101", label="C101", story_id="5", section_id="UNKNOWN")},
    )

    result = evaluate_column_geometry(snapshot, "C101")

    assert result.status == "NO_DATA"
    assert result.evidence.evidence_type == "missing_required_input"
    assert "section" in result.evidence.missing_inputs


def test_missing_width_no_data():
    result = evaluate_column_geometry(_snapshot(None, 500), "C101")

    assert result.status == "NO_DATA"
    assert "section.width_mm" in result.evidence.missing_inputs


def test_missing_height_no_data():
    result = evaluate_column_geometry(_snapshot(300, None), "C101")

    assert result.status == "NO_DATA"
    assert "section.depth_mm" in result.evidence.missing_inputs


def test_workbench_cell_mirrors_check_result():
    result = evaluate_column_geometry(_snapshot(300, 500), "C101")
    cell = build_column_workbench_cell(result)

    assert cell.cell_id == "column_geometry:C101:5"
    assert cell.title == "Kolon Geometri Kontrolü"
    assert cell.check_id == result.check_id
    assert cell.element_label == result.element_label
    assert cell.story == result.story
    assert cell.status == result.status
    assert cell.evaluation_level == result.evaluation_level
    assert cell.input_panel == result.evidence.source_values
    assert cell.formula_panel == [sub.formula_trace for sub in result.sub_checks]
    assert cell.result_panel == {
        "status": result.status,
        "ratio": result.ratio,
        "message": result.message,
        "action": result.action,
    }
    assert cell.evidence_panel == result.evidence


def test_no_eval_or_exec_in_archx_sources():
    source = "\n".join(path.read_text(encoding="utf-8") for path in ARCHX_ROOT.glob("*.py"))

    assert "eval(" not in source
    assert "exec(" not in source


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
