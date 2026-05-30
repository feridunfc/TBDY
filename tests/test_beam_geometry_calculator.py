from __future__ import annotations

import pytest

from tbdy_engine.design.beams import BeamModelContext, GeometryCheck, GeometryResult, TBDYGeometryCalculator


def _ctx(**overrides: object) -> BeamModelContext:
    values = {
        "beam_id": "B1",
        "story": "S1",
        "section": "B300x600",
        "bw": 300.0,
        "h": 600.0,
        "d": 550.0,
        "cover": 40.0,
        "Ln": 3000.0,
        "fck": 30.0,
        "fcd": 20.0,
        "fctd": 1.35,
        "fyk": 420.0,
        "fyd": 365.0,
        "fywd": 365.0,
        "Vd": 120.0,
        "Ve": 150.0,
        "Md": 240.0,
        "axial": 0.0,
        "stirrup_legs": 2,
        "stirrup_diameter_mm": 10.0,
        "stirrup_spacing_mm": 100.0,
        "missing_inputs": (),
        "source": {"origin": "unit_test"},
    }
    values.update(overrides)
    return BeamModelContext(**values)


def test_geometry_calculator_returns_deterministic_ok_checks() -> None:
    result = TBDYGeometryCalculator().calculate(_ctx())

    assert isinstance(result, GeometryResult)
    assert result.status == "OK"
    assert len(result.checks) == 4
    assert all(isinstance(check, GeometryCheck) for check in result.checks)
    assert [check.name for check in result.checks] == [
        "beam_geometry_min_width",
        "beam_geometry_min_depth",
        "beam_geometry_span_depth_ratio",
        "beam_geometry_depth_width_ratio",
    ]
    assert [check.status for check in result.checks] == ["OK", "OK", "OK", "OK"]


def test_geometry_calculator_evidence_contains_values_limits_and_formulas() -> None:
    checks = {check.name: check for check in TBDYGeometryCalculator().calculate(_ctx()).checks}

    width = checks["beam_geometry_min_width"]
    assert width.demand == 300.0
    assert width.capacity == 250.0
    assert width.ratio == pytest.approx(300.0 / 250.0)
    assert width.unit == "mm"
    assert width.evidence == {"bw": 300.0, "limit": 250.0, "ratio": pytest.approx(300.0 / 250.0), "formula": "bw >= 250 mm"}

    span = checks["beam_geometry_span_depth_ratio"]
    assert span.demand == pytest.approx(5.0)
    assert span.capacity == 4.0
    assert span.ratio == pytest.approx(5.0 / 4.0)
    assert span.evidence["Ln"] == 3000.0
    assert span.evidence["h"] == 600.0
    assert span.evidence["Ln_over_h"] == pytest.approx(5.0)
    assert span.evidence["formula"] == "Ln / h >= 4"


def test_geometry_calculator_reports_failures_without_side_effects() -> None:
    result = TBDYGeometryCalculator().calculate(_ctx(bw=200.0, h=900.0, Ln=2000.0))

    assert result.status == "FAIL"
    statuses = {check.name: check.status for check in result.checks}
    assert statuses["beam_geometry_min_width"] == "FAIL"
    assert statuses["beam_geometry_min_depth"] == "OK"
    assert statuses["beam_geometry_span_depth_ratio"] == "FAIL"
    assert statuses["beam_geometry_depth_width_ratio"] == "FAIL"

    depth_width = {check.name: check for check in result.checks}["beam_geometry_depth_width_ratio"]
    assert depth_width.demand == pytest.approx(900.0 / 200.0)
    assert depth_width.capacity == 3.5
    assert depth_width.evidence["formula"] == "h / bw <= 3.5"


def test_geometry_calculator_source_guard_has_no_etabs_report_adapter_runner_imports() -> None:
    import pathlib

    source = pathlib.Path("tbdy_engine/design/beams/calculators/geometry.py").read_text(encoding="utf-8")
    forbidden = [
        "tbdy_engine.etabs",
        "tbdy_engine.reports",
        "tbdy_engine.adapters",
        "tbdy_engine.runner_v2",
        "tbdy_engine.archx",
        "ReportingFacade",
        "CheckAdapter",
        "CheckResult",
        "read_etabs_table_on_demand",
    ]
    for text in forbidden:
        assert text not in source
