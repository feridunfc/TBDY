from __future__ import annotations

import pytest

from tbdy_engine.design.beams import BeamModelContext, GeometryCheck, GeometryResult, TBDYGeometryCalculator


def _ctx(**overrides: object) -> BeamModelContext:
    values = {
        "beam_id": "B1",
        "story": "S1",
        "section_name": "B300x600",
        "bw_mm": 300.0,
        "h_mm": 600.0,
        "d_mm": 550.0,
        "cover_mm": 40.0,
        "Ln_mm": 3000.0,
        "fck_mpa": 30.0,
        "fcd_mpa": 20.0,
        "fctd_mpa": 1.35,
        "fyk_mpa": 420.0,
        "fyd_mpa": 365.0,
        "fywd_mpa": 365.0,
        "Vd_left_kN": 120.0,
        "Ve_left_kN": 150.0,
        "Md_left_neg_kNm": 240.0,
        "axial_kN": 0.0,
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


def test_geometry_calculator_evidence_contains_unit_suffixed_values_limits_and_formulas() -> None:
    checks = {check.name: check for check in TBDYGeometryCalculator().calculate(_ctx()).checks}

    width = checks["beam_geometry_min_width"]
    assert width.demand == 300.0
    assert width.capacity == 250.0
    assert width.ratio == pytest.approx(300.0 / 250.0)
    assert width.unit == "mm"
    assert width.evidence == {
        "bw_mm": 300.0,
        "limit": 250.0,
        "computed_ratio": pytest.approx(300.0 / 250.0),
        "formula": "bw_mm >= 250 mm",
    }
    assert "bw" not in width.evidence
    assert "ratio" not in width.evidence

    span = checks["beam_geometry_span_depth_ratio"]
    assert span.demand == pytest.approx(5.0)
    assert span.capacity == 4.0
    assert span.ratio == pytest.approx(5.0 / 4.0)
    assert span.evidence["Ln_mm"] == 3000.0
    assert span.evidence["h_mm"] == 600.0
    assert span.evidence["Ln_over_h"] == pytest.approx(5.0)
    assert span.evidence["computed_ratio"] == pytest.approx(5.0 / 4.0)
    assert span.evidence["formula"] == "Ln_mm / h_mm >= 4"
    assert "Ln" not in span.evidence
    assert "h" not in span.evidence
    assert "ratio" not in span.evidence


def test_geometry_calculator_reports_failures_without_side_effects() -> None:
    result = TBDYGeometryCalculator().calculate(_ctx(bw_mm=200.0, h_mm=900.0, Ln_mm=2000.0))

    assert result.status == "FAIL"
    statuses = {check.name: check.status for check in result.checks}
    assert statuses["beam_geometry_min_width"] == "FAIL"
    assert statuses["beam_geometry_min_depth"] == "OK"
    assert statuses["beam_geometry_span_depth_ratio"] == "FAIL"
    assert statuses["beam_geometry_depth_width_ratio"] == "FAIL"

    depth_width = {check.name: check for check in result.checks}["beam_geometry_depth_width_ratio"]
    assert depth_width.demand == pytest.approx(900.0 / 200.0)
    assert depth_width.capacity == 3.5
    assert depth_width.evidence["h_mm"] == 900.0
    assert depth_width.evidence["bw_mm"] == 200.0
    assert depth_width.evidence["computed_ratio"] == pytest.approx((900.0 / 200.0) / 3.5)
    assert depth_width.evidence["formula"] == "h_mm / bw_mm <= 3.5"


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
