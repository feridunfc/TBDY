from __future__ import annotations

from dataclasses import is_dataclass

from tbdy_engine.design.beams import BeamModelContext, GeometryCoreResult, evaluate_beam_geometry_core


def _valid_input(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "beam_id": "B175",
        "story": "+14.50",
        "section_name": "B60x60",
        "bw_mm": 600.0,
        "h_mm": 600.0,
        "d_mm": 550.0,
        "cover_mm": 40.0,
        "Ln_mm": 4600.0,
        "fck_mpa": 30.0,
        "fcd_mpa": 20.0,
        "fctd_mpa": 1.27,
        "fyk_mpa": 420.0,
        "fyd_mpa": 365.0,
        "fywd_mpa": 365.0,
        "Vd_left_kN": 90.0,
        "Ve_left_kN": 107.2,
        "Md_left_neg_kNm": 108.7,
        "Md_mid_pos_kNm": 84.8,
        "Md_right_neg_kNm": 92.4,
        "axial_kN": 0.0,
        "stirrup_legs": 2,
        "stirrup_diameter_mm": 10.0,
        "stirrup_spacing_mm": 100.0,
        "source": {
            "origin": "unit_test",
            "source_table": "canonical_fixture",
            "source_row": 1,
        },
    }
    data.update(overrides)
    return data


def test_valid_canonical_input_produces_geometry_core_result() -> None:
    result = evaluate_beam_geometry_core(_valid_input())

    assert is_dataclass(GeometryCoreResult)
    assert GeometryCoreResult.__dataclass_params__.frozen is True
    assert isinstance(result, GeometryCoreResult)
    assert result.status == "OK"
    assert result.validation_errors == ()
    assert result.geometry is not None
    assert len(result.geometry.checks) == 4
    assert isinstance(result.context, BeamModelContext)
    assert result.context.beam_id == "B175"
    assert result.context.story == "+14.50"
    assert result.context.section_name == "B60x60"
    assert result.context.bw_mm == 600.0
    assert result.context.h_mm == 600.0
    assert result.context.Ln_mm == 4600.0
    assert result.context.source == {
        "origin": "unit_test",
        "source_table": "canonical_fixture",
        "source_row": 1,
    }


def test_invalid_canonical_input_returns_validation_errors_without_geometry() -> None:
    data = _valid_input(bw_mm=0.0, fcd_mpa=None, stirrup_legs=1)
    data.pop("Ln_mm")

    result = evaluate_beam_geometry_core(data)

    assert result.status == "INVALID_INPUT"
    assert result.geometry is None
    assert {"bw_mm", "fcd_mpa", "Ln_mm", "stirrup_legs"}.issubset(set(result.validation_errors))
    assert result.context.bw_mm == 0.0
    assert result.context.fcd_mpa == 0.0
    assert result.context.Ln_mm == 0.0


def test_valid_input_with_failing_geometry_returns_fail() -> None:
    result = evaluate_beam_geometry_core(_valid_input(bw_mm=200.0, h_mm=900.0, Ln_mm=2000.0))

    assert result.status == "FAIL"
    assert result.validation_errors == ()
    assert result.geometry is not None
    assert any(check.status == "FAIL" for check in result.geometry.checks)
    statuses = {check.name: check.status for check in result.geometry.checks}
    assert statuses["beam_geometry_min_width"] == "FAIL"
    assert statuses["beam_geometry_span_depth_ratio"] == "FAIL"
    assert statuses["beam_geometry_depth_width_ratio"] == "FAIL"


def test_geometry_core_source_guard_has_no_runtime_or_report_imports() -> None:
    import pathlib

    source = pathlib.Path("tbdy_engine/design/beams/geometry_core.py").read_text(encoding="utf-8")
    forbidden = [
        "tbdy_engine.etabs",
        "tbdy_engine.reports",
        "tbdy_engine.adapters",
        "tbdy_engine.runner_v2",
        "tbdy_engine.archx",
        "tbdy_engine.runtime",
        "tbdy_engine.contracts",
        "CheckResult",
        "BeamEvaluationPackage",
        "ReportingFacade",
        "CheckAdapter",
        "read_etabs_table_on_demand",
    ]
    for text in forbidden:
        assert text not in source
