from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from tbdy_engine.design.beams import BeamModelContext, validate_beam_model_context


OLD_AMBIGUOUS_FIELDS = {"bw", "h", "d", "Ln", "fck", "Vd", "Md", "axial"}


def _valid_context(**overrides: object) -> BeamModelContext:
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
        "top_required_area_cm2": None,
        "bottom_required_area_cm2": None,
        "top_selected_area_cm2": None,
        "bottom_selected_area_cm2": None,
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
        ctx.bw_mm = 250.0  # type: ignore[misc]

    assert not hasattr(ctx, "calculate")
    assert not hasattr(ctx, "to_check_result")
    assert validate_beam_model_context(ctx) == ()


def test_beam_model_context_requires_unit_suffixed_fields_and_removes_old_names() -> None:
    names = {field.name for field in fields(BeamModelContext)}
    assert OLD_AMBIGUOUS_FIELDS.isdisjoint(names)
    assert {
        "section_name",
        "bw_mm",
        "h_mm",
        "d_mm",
        "cover_mm",
        "Ln_mm",
        "fck_mpa",
        "fcd_mpa",
        "fctd_mpa",
        "fyk_mpa",
        "fyd_mpa",
        "fywd_mpa",
        "Vd_left_kN",
        "Ve_left_kN",
        "Md_left_neg_kNm",
        "axial_kN",
        "top_required_area_cm2",
        "bottom_required_area_cm2",
        "top_selected_area_cm2",
        "bottom_selected_area_cm2",
    }.issubset(names)

    with pytest.raises(TypeError):
        BeamModelContext(  # type: ignore[call-arg]
            beam_id="B1",
            story="S1",
            section="B300x600",
            bw=300.0,
            h=600.0,
            d=550.0,
            cover=40.0,
            Ln=3000.0,
            fck=30.0,
            fcd=20.0,
            fctd=1.35,
            fyk=420.0,
            fyd=365.0,
            fywd=365.0,
            Vd=120.0,
            Ve=150.0,
            Md=240.0,
            axial=0.0,
            stirrup_legs=2,
            stirrup_diameter_mm=10.0,
            stirrup_spacing_mm=100.0,
        )


def test_validate_beam_model_context_reports_invalid_unit_suffixed_inputs() -> None:
    ctx = _valid_context(
        bw_mm=0.0,
        h_mm=-1.0,
        d_mm=0.0,
        cover_mm=0.0,
        Ln_mm=0.0,
        fck_mpa=0.0,
        fcd_mpa=-1.0,
        fctd_mpa=0.0,
        fyk_mpa=0.0,
        fyd_mpa=0.0,
        fywd_mpa=0.0,
        Vd_left_kN="",
        Ve_left_kN="",
        Md_left_neg_kNm="",
        axial_kN="",
        stirrup_legs=1,
        stirrup_diameter_mm=0.0,
        stirrup_spacing_mm=0.0,
        missing_inputs=("custom_missing",),
    )

    invalid = set(validate_beam_model_context(ctx))
    assert {
        "bw_mm",
        "h_mm",
        "d_mm",
        "cover_mm",
        "Ln_mm",
        "fck_mpa",
        "fcd_mpa",
        "fctd_mpa",
        "fyk_mpa",
        "fyd_mpa",
        "fywd_mpa",
        "Vd_left_kN",
        "Ve_left_kN",
        "Md_left_neg_kNm",
        "axial_kN",
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
