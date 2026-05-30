from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from tbdy_engine.design.beams import BeamModelContext, validate_beam_model_context


def _valid_context(**overrides: object) -> BeamModelContext:
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
        "top_required_area": None,
        "bottom_required_area": None,
        "top_selected_area": None,
        "bottom_selected_area": None,
        "missing_inputs": (),
        "source": {"origin": "unit_test"},
    }
    values.update(overrides)
    return BeamModelContext(**values)


def test_beam_model_context_is_frozen_input_only_dataclass() -> None:
    assert is_dataclass(BeamModelContext)
    assert BeamModelContext.__dataclass_params__.frozen is True

    ctx = _valid_context()
    with pytest.raises(FrozenInstanceError):
        ctx.bw = 250.0  # type: ignore[misc]

    assert not hasattr(ctx, "calculate")
    assert not hasattr(ctx, "to_check_result")
    assert validate_beam_model_context(ctx) == ()


def test_validate_beam_model_context_reports_invalid_inputs() -> None:
    ctx = _valid_context(
        bw=0.0,
        h=-1.0,
        d=0.0,
        cover=0.0,
        Ln=0.0,
        fck=0.0,
        fcd=-1.0,
        fctd=0.0,
        fyk=0.0,
        fyd=0.0,
        fywd=0.0,
        stirrup_legs=1,
        stirrup_diameter_mm=0.0,
        stirrup_spacing_mm=0.0,
        missing_inputs=("custom_missing",),
    )

    invalid = set(validate_beam_model_context(ctx))
    assert {
        "bw",
        "h",
        "d",
        "cover",
        "Ln",
        "fck",
        "fcd",
        "fctd",
        "fyk",
        "fyd",
        "fywd",
        "stirrup_legs",
        "stirrup_diameter_mm",
        "stirrup_spacing_mm",
        "custom_missing",
    }.issubset(invalid)


def test_beam_model_context_source_guard_has_no_runtime_imports() -> None:
    import pathlib

    source = pathlib.Path("tbdy_engine/design/beams/context.py").read_text(encoding="utf-8")
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
