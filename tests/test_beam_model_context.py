from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from tbdy_engine.design.beams import BeamModelContext, build_beam_model_context, validate_beam_model_context


OLD_AMBIGUOUS_FIELDS = {"bw", "h", "d", "Ln", "fck", "Vd", "Md", "axial"}


def _canonical_input(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
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
    return values


def _valid_context(**overrides: object) -> BeamModelContext:
    return BeamModelContext(**_canonical_input(**overrides))


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
        "left_top_as_cm2",
        "left_bottom_as_cm2",
        "right_top_as_cm2",
        "right_bottom_as_cm2",
        "Md_mid_pos_kNm",
        "Md_right_neg_kNm",
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


def test_build_beam_model_context_from_full_canonical_input() -> None:
    ctx = build_beam_model_context(
        _canonical_input(
            left_top_as_cm2=7.5,
            left_bottom_as_cm2=4.2,
            right_top_as_cm2=7.1,
            right_bottom_as_cm2=4.0,
            Md_mid_pos_kNm=180.0,
            Md_right_neg_kNm=210.0,
            source={
                "source_table": "canonical_beam_input",
                "source_row": 4,
                "source_columns": ("beam_id", "bw_mm"),
                "origin": "unit_test",
            },
        )
    )

    assert isinstance(ctx, BeamModelContext)
    assert ctx.beam_id == "B1"
    assert ctx.section_name == "B300x600"
    assert ctx.bw_mm == 300.0
    assert ctx.fcd_mpa == 20.0
    assert ctx.Vd_left_kN == 120.0
    assert ctx.Md_mid_pos_kNm == 180.0
    assert ctx.right_bottom_as_cm2 == 4.0
    assert ctx.source == {
        "source_table": "canonical_beam_input",
        "source_row": 4,
        "source_columns": ("beam_id", "bw_mm"),
        "origin": "unit_test",
    }
    assert validate_beam_model_context(ctx) == ()


def test_build_beam_model_context_accepts_numeric_strings_and_converts() -> None:
    ctx = build_beam_model_context(
        _canonical_input(
            bw_mm="300",
            h_mm="600.0",
            stirrup_legs="4",
            Vd_left_kN="120.5",
            top_required_area_cm2="8.25",
        )
    )

    assert ctx.bw_mm == 300.0
    assert ctx.h_mm == 600.0
    assert ctx.stirrup_legs == 4
    assert ctx.Vd_left_kN == 120.5
    assert ctx.top_required_area_cm2 == 8.25
    assert validate_beam_model_context(ctx) == ()


def test_build_beam_model_context_tracks_missing_required_inputs_without_guessing() -> None:
    data = _canonical_input()
    for key in ("bw_mm", "fcd_mpa", "Vd_left_kN", "stirrup_legs"):
        data.pop(key)
    ctx = build_beam_model_context(data)

    assert ctx.bw_mm == 0.0
    assert ctx.fcd_mpa == 0.0
    assert ctx.Vd_left_kN == 0.0
    assert ctx.stirrup_legs == 0
    assert {"bw_mm", "fcd_mpa", "Vd_left_kN", "stirrup_legs"}.issubset(set(ctx.missing_inputs))
    assert {"bw_mm", "fcd_mpa", "stirrup_legs"}.issubset(set(validate_beam_model_context(ctx)))


def test_build_beam_model_context_allows_optional_reinforcement_absent() -> None:
    data = _canonical_input()
    for key in (
        "top_required_area_cm2",
        "bottom_required_area_cm2",
        "top_selected_area_cm2",
        "bottom_selected_area_cm2",
    ):
        data.pop(key)
    ctx = build_beam_model_context(data)

    assert ctx.top_required_area_cm2 is None
    assert ctx.bottom_required_area_cm2 is None
    assert ctx.top_selected_area_cm2 is None
    assert ctx.bottom_selected_area_cm2 is None
    assert validate_beam_model_context(ctx) == ()


def test_build_beam_model_context_sanitizes_source() -> None:
    ctx = build_beam_model_context(
        _canonical_input(
            source={
                "source_table": "canonical",
                "source_row": 2,
                "source_columns": ["beam_id"],
                "origin": "unit_test",
                "raw_row": {"too": "large"},
                "runtime_catalog": "forbidden",
                "diagnostic_trace": "forbidden",
            }
        )
    )

    assert ctx.source == {
        "source_table": "canonical",
        "source_row": 2,
        "source_columns": ["beam_id"],
        "origin": "unit_test",
    }


def test_build_beam_model_context_does_not_compute_derived_values() -> None:
    ctx = build_beam_model_context(
        _canonical_input(
            fck_mpa=30.0,
            fcd_mpa=None,
            h_mm=600.0,
            cover_mm=40.0,
            d_mm=None,
            Ln_mm=None,
        )
    )

    assert ctx.fcd_mpa == 0.0
    assert ctx.d_mm == 0.0
    assert ctx.Ln_mm == 0.0
    assert {"fcd_mpa", "d_mm", "Ln_mm"}.issubset(set(ctx.missing_inputs))
    assert {"fcd_mpa", "d_mm", "Ln_mm"}.issubset(set(validate_beam_model_context(ctx)))


def test_build_beam_model_context_ignores_old_ambiguous_input_keys() -> None:
    ctx = build_beam_model_context(
        {
            "beam_id": "B1",
            "story": "S1",
            "section_name": "B300x600",
            "bw": 300.0,
            "h": 600.0,
            "Ln": 3000.0,
            "fck": 30.0,
            "Vd": 120.0,
            "Md": 240.0,
            "stirrup_legs": 2,
            "stirrup_diameter_mm": 10.0,
            "stirrup_spacing_mm": 100.0,
        }
    )

    assert ctx.bw_mm == 0.0
    assert ctx.h_mm == 0.0
    assert ctx.Ln_mm == 0.0
    assert ctx.fck_mpa == 0.0
    assert ctx.Vd_left_kN == 0.0
    assert ctx.Md_left_neg_kNm == 0.0
    assert OLD_AMBIGUOUS_FIELDS.isdisjoint(set(ctx.missing_inputs))
    assert {"bw_mm", "h_mm", "Ln_mm", "fck_mpa", "Vd_left_kN", "Md_left_neg_kNm"}.issubset(set(ctx.missing_inputs))


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
