from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tbdy_engine.archx import (
    Beam,
    CanonicalSnapshot,
    Column,
    DesignBasis,
    Section,
    Story,
    build_column_workbench_cell,
    build_story_workbench_cell,
    build_workbench_bundle,
    build_workbench_cell,
    evaluate_beam_geometry,
    evaluate_column_geometry,
    evaluate_story_drift,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHX_ROOT = ROOT / "tbdy_engine" / "archx"


def _snapshot() -> CanonicalSnapshot:
    return CanonicalSnapshot(
        sections={
            "BSEC": Section(section_id="BSEC", width_mm=300, depth_mm=500),
            "CSEC": Section(section_id="CSEC", width_mm=400, depth_mm=400),
        },
        beams={"B101": Beam(element_id="B101", label="B101", story_id="5", section_id="BSEC")},
        columns={"C101": Column(element_id="C101", label="C101", story_id="5", section_id="CSEC")},
        stories={"S1": Story(story_id="S1", height_mm=3000, drift_max_mm=75)},
        design_basis=DesignBasis(drift_limit=0.02),
    )


def _results_and_cells():
    snapshot = _snapshot()
    beam_result = evaluate_beam_geometry(snapshot, "B101")
    column_result = evaluate_column_geometry(snapshot, "C101")
    story_result = evaluate_story_drift(snapshot, "S1")
    return [
        beam_result,
        column_result,
        story_result,
    ], [
        build_workbench_cell(beam_result),
        build_column_workbench_cell(column_result),
        build_story_workbench_cell(story_result),
    ]


def test_bundle_summary_with_beam_column_and_story_results():
    results, cells = _results_and_cells()

    bundle = build_workbench_bundle(results, cells, run_id="wb-1-test")

    assert bundle["bundle_version"] == "ARCH-X-WB-1"
    assert bundle["run_id"] == "wb-1-test"
    assert bundle["check_count"] == 3
    assert bundle["cell_count"] == 3
    assert bundle["summary"]["total"] == 3
    assert bundle["summary"]["by_status"]["OK"] == 2
    assert bundle["summary"]["by_status"]["FAIL"] == 1
    assert set(bundle["summary"]["by_check_id"]) == {"beam_geometry", "column_geometry", "story_drift"}
    assert bundle["summary"]["by_report_section"] == {"beams": 1, "columns": 1, "global": 1}
    assert bundle["index"]["by_check_id"]["beam_geometry"] == ["beam_geometry:B101:5"]
    assert bundle["index"]["by_report_section"]["global"] == ["story_drift:S1:S1"]


def test_bundle_is_json_serializable():
    results, cells = _results_and_cells()

    bundle = build_workbench_bundle(results, cells)

    json.dumps(bundle)


def test_bundle_has_deterministic_ordering_for_shuffled_inputs():
    results, cells = _results_and_cells()

    bundle = build_workbench_bundle(
        [results[2], results[0], results[1]],
        [cells[2], cells[0], cells[1]],
    )

    assert [item["check_id"] for item in bundle["check_results"]] == [
        "beam_geometry",
        "column_geometry",
        "story_drift",
    ]
    assert [item["cell_id"] for item in bundle["workbench_cells"]] == [
        "beam_geometry:B101:5",
        "column_geometry:C101:5",
        "story_drift:S1:S1",
    ]


def test_missing_workbench_cell_raises_value_error():
    results, cells = _results_and_cells()

    with pytest.raises(ValueError, match="Missing WorkbenchCell"):
        build_workbench_bundle(results, cells[:-1])


def test_bundle_does_not_recalculate_or_mutate_results():
    results, cells = _results_and_cells()
    original_beam_result = results[0]
    provided_beam_result = replace(original_beam_result, status="WARNING")
    provided_beam_cell = replace(cells[0], status="WARNING")

    bundle = build_workbench_bundle(
        [provided_beam_result, results[1], results[2]],
        [provided_beam_cell, cells[1], cells[2]],
    )

    assert original_beam_result.status == "OK"
    assert bundle["check_results"][0]["status"] == "WARNING"
    assert bundle["workbench_cells"][0]["status"] == "WARNING"
    assert bundle["summary"]["by_status"]["WARNING"] == 1


def test_workbench_bundle_source_does_not_call_existing_checks():
    source = (ARCHX_ROOT / "workbench_bundle.py").read_text(encoding="utf-8")

    assert "evaluate_" not in source


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
        "CheckAdapter",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in ARCHX_ROOT.glob("*.py"))

    for forbidden in forbidden_imports:
        assert forbidden not in source
