from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tbdy_engine.archx import (
    Beam,
    CanonicalSnapshot,
    Section,
    build_workbench_cell,
    evaluate_beam_geometry,
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


def _sub_statuses(result) -> dict[str, str]:
    return {sub.step_id: sub.status for sub in result.sub_checks}


def test_ok_case_and_workbench_cell():
    result = evaluate_beam_geometry(_snapshot(300, 500), "B101")
    cell = build_workbench_cell(result)

    assert result.status == "OK"
    assert result.evaluation_level == "DESIGN_LEVEL"
    assert result.ratio == min(300 / 250, 500 / 300)
    assert result.value is None
    assert result.limit is None
    assert _sub_statuses(result) == {"beam_width_min": "OK", "beam_height_min": "OK"}
    assert result.evidence.evidence_type == "canonical_model"
    assert cell.status == "OK"


def test_fail_width():
    result = evaluate_beam_geometry(_snapshot(200, 500), "B101")

    assert result.status == "FAIL"
    assert _sub_statuses(result) == {"beam_width_min": "FAIL", "beam_height_min": "OK"}
    assert result.value is None
    assert result.limit is None


def test_fail_height():
    result = evaluate_beam_geometry(_snapshot(300, 250), "B101")

    assert result.status == "FAIL"
    assert _sub_statuses(result) == {"beam_width_min": "OK", "beam_height_min": "FAIL"}


def test_fail_both():
    result = evaluate_beam_geometry(_snapshot(200, 250), "B101")

    assert result.status == "FAIL"
    assert _sub_statuses(result) == {"beam_width_min": "FAIL", "beam_height_min": "FAIL"}


def test_boundary_case_is_ok():
    result = evaluate_beam_geometry(_snapshot(250, 300), "B101")

    assert result.status == "OK"
    assert result.ratio == 1.0
    assert _sub_statuses(result) == {"beam_width_min": "OK", "beam_height_min": "OK"}


def test_missing_beam_returns_no_data():
    result = evaluate_beam_geometry(_snapshot(300, 500), "UNKNOWN")

    assert result.status == "NO_DATA"
    assert result.evaluation_level == "NO_DATA"
    assert result.evidence.evidence_type == "missing_required_input"
    assert "beam" in result.evidence.missing_inputs


def test_missing_section_returns_no_data():
    snapshot = CanonicalSnapshot(
        sections={},
        beams={"B101": Beam(element_id="B101", label="B101", story_id="5", section_id="UNKNOWN")},
    )

    result = evaluate_beam_geometry(snapshot, "B101")

    assert result.status == "NO_DATA"
    assert result.evidence.evidence_type == "missing_required_input"
    assert "section" in result.evidence.missing_inputs


def test_missing_width_returns_no_data():
    result = evaluate_beam_geometry(_snapshot(None, 500), "B101")

    assert result.status == "NO_DATA"
    assert "section.width_mm" in result.evidence.missing_inputs


def test_missing_height_returns_no_data():
    result = evaluate_beam_geometry(_snapshot(300, None), "B101")

    assert result.status == "NO_DATA"
    assert "section.depth_mm" in result.evidence.missing_inputs


def test_workbench_cell_does_not_recalculate():
    result = evaluate_beam_geometry(_snapshot(200, 250), "B101")
    cell = build_workbench_cell(result)

    assert cell.status == result.status
    assert cell.result_panel["status"] == result.status
    assert cell.result_panel["ratio"] == result.ratio
    assert cell.result_panel["message"] == result.message
    assert cell.result_panel["action"] == result.action
    assert cell.input_panel == result.evidence.source_values
    assert cell.formula_panel == [sub.formula_trace for sub in result.sub_checks]
    assert cell.evidence_panel == result.evidence
    assert asdict(cell)["check_id"] == result.check_id


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
