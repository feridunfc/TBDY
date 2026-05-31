from __future__ import annotations

import pathlib
from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from tbdy_engine.design.beams.context import BeamModelContext
from tbdy_engine.design.beams.core_check import (
    CoreCheck,
    geometry_check_to_core_check,
    shear_check_to_core_check,
)
from tbdy_engine.design.beams.calculators.geometry import TBDYGeometryCalculator
from tbdy_engine.design.beams.calculators.shear import TBDYShearCalculator


def _ctx() -> BeamModelContext:
    return BeamModelContext(
        beam_id="B175",
        story="+14.50",
        section_name="B60x60",
        bw_mm=600.0,
        h_mm=600.0,
        d_mm=550.0,
        cover_mm=40.0,
        Ln_mm=4600.0,
        fck_mpa=30.0,
        fcd_mpa=20.0,
        fctd_mpa=1.27,
        fyk_mpa=420.0,
        fyd_mpa=365.0,
        fywd_mpa=365.0,
        Vd_left_kN=90.0,
        Ve_left_kN=107.2,
        Md_left_neg_kNm=108.7,
        Md_mid_pos_kNm=84.8,
        Md_right_neg_kNm=92.4,
        axial_kN=0.0,
        stirrup_legs=2,
        stirrup_diameter_mm=10.0,
        stirrup_spacing_mm=100.0,
        longitudinal_bar_diameter_mm=16.0,
    )


def test_core_check_is_frozen_dataclass() -> None:
    assert is_dataclass(CoreCheck)
    assert CoreCheck.__dataclass_params__.frozen is True

    check = CoreCheck(
        id="B175:geometry:beam_geometry_min_width",
        component="B175",
        check_type="geometry",
        name="beam_geometry_min_width",
        status="OK",
        demand=600.0,
        capacity=250.0,
        ratio=2.4,
        unit="mm",
        code_ref="TBDY",
        evidence={},
        message="ok",
    )

    with pytest.raises(FrozenInstanceError):
        check.status = "FAIL"  # type: ignore[misc]


def test_geometry_check_to_core_check_maps_fields_and_preserves_evidence() -> None:
    ctx = _ctx()
    geometry_check = TBDYGeometryCalculator().calculate(ctx).checks[0]
    original_evidence = dict(geometry_check.evidence)

    core_check = geometry_check_to_core_check(
        beam_id=ctx.beam_id,
        story=ctx.story,
        section_name=ctx.section_name,
        check=geometry_check,
    )

    assert core_check.id == "B175:geometry:beam_geometry_min_width"
    assert core_check.component == "B175"
    assert core_check.check_type == "geometry"
    assert core_check.name == geometry_check.name
    assert core_check.status == geometry_check.status
    assert core_check.demand == geometry_check.demand
    assert core_check.capacity == geometry_check.capacity
    assert core_check.ratio == geometry_check.ratio
    assert core_check.unit == geometry_check.unit
    assert core_check.code_ref == geometry_check.code_ref
    assert core_check.message == geometry_check.message
    assert core_check.evidence["story"] == "+14.50"
    assert core_check.evidence["section_name"] == "B60x60"
    assert geometry_check.evidence == original_evidence


def test_shear_check_to_core_check_maps_fields_and_preserves_evidence() -> None:
    ctx = _ctx()
    shear_check = TBDYShearCalculator().calculate(ctx).checks[0]
    original_evidence = dict(shear_check.evidence)

    core_check = shear_check_to_core_check(
        beam_id=ctx.beam_id,
        story=ctx.story,
        section_name=ctx.section_name,
        check=shear_check,
    )

    assert core_check.id == "B175:shear:beam_shear_ve_le_vr"
    assert core_check.component == "B175"
    assert core_check.check_type == "shear"
    assert core_check.name == shear_check.name
    assert core_check.status == shear_check.status
    assert core_check.demand == shear_check.demand
    assert core_check.capacity == shear_check.capacity
    assert core_check.ratio == shear_check.ratio
    assert core_check.unit == shear_check.unit
    assert core_check.code_ref == shear_check.code_ref
    assert core_check.message == shear_check.message
    assert core_check.evidence["story"] == "+14.50"
    assert core_check.evidence["section_name"] == "B60x60"
    assert shear_check.evidence == original_evidence


def test_shear_spacing_8_longitudinal_diameter_core_check_preserves_evidence() -> None:
    ctx = _ctx()
    shear_checks = TBDYShearCalculator().calculate(ctx).checks
    shear_check = {
        check.name: check for check in shear_checks
    }["beam_shear_spacing_le_8_longitudinal_diameter"]
    original_evidence = dict(shear_check.evidence)

    core_check = shear_check_to_core_check(
        beam_id=ctx.beam_id,
        story=ctx.story,
        section_name=ctx.section_name,
        check=shear_check,
    )

    assert core_check.id == "B175:shear:beam_shear_spacing_le_8_longitudinal_diameter"
    assert core_check.component == "B175"
    assert core_check.check_type == "shear"
    assert core_check.evidence["story"] == "+14.50"
    assert core_check.evidence["section_name"] == "B60x60"
    assert core_check.evidence["stirrup_spacing_mm"] == 100.0
    assert core_check.evidence["longitudinal_bar_diameter_mm"] == 16.0
    assert core_check.evidence["limit_mm"] == 128.0
    assert shear_check.evidence == original_evidence


def test_core_check_source_guard_has_no_forbidden_imports() -> None:
    source = pathlib.Path("tbdy_engine/design/beams/core_check.py").read_text(encoding="utf-8")
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

def test_n6_flexure_core_check_preserves_area_and_rho_evidence() -> None:
    from tbdy_engine.design.beams.context import BeamModelContext
    from tbdy_engine.design.beams.calculators.flexure import TBDYFlexureCalculator
    from tbdy_engine.design.beams.core_check import flexure_check_to_core_check

    ctx = BeamModelContext(
        beam_id="B175",
        story="+14.50",
        section_name="B60x60",
        bw_mm=600.0,
        h_mm=600.0,
        d_mm=550.0,
        cover_mm=40.0,
        Ln_mm=4600.0,
        fck_mpa=30.0,
        fcd_mpa=20.0,
        fctd_mpa=1.27,
        fyk_mpa=420.0,
        fyd_mpa=365.0,
        fywd_mpa=365.0,
        Vd_left_kN=90.0,
        Ve_left_kN=107.2,
        Md_left_neg_kNm=108.7,
        Md_mid_pos_kNm=84.8,
        Md_right_neg_kNm=92.4,
        axial_kN=0.0,
        stirrup_legs=2,
        stirrup_diameter_mm=10.0,
        stirrup_spacing_mm=100.0,
        longitudinal_bar_diameter_mm=16.0,
        top_required_area_cm2=8.0,
        top_selected_area_cm2=10.0,
        bottom_required_area_cm2=6.0,
        bottom_selected_area_cm2=10.0,
        missing_inputs=(),
        source={"origin": "n6_unit_test"},
    )

    result = TBDYFlexureCalculator().calculate(ctx)
    checks = {check.name: check for check in result.checks}

    for name in (
        "beam_flexure_top_area_provided_ge_required",
        "beam_flexure_top_rho_ge_rho_min",
        "beam_flexure_top_rho_le_rho_max",
    ):
        original = checks[name]
        core = flexure_check_to_core_check(
            beam_id=ctx.beam_id,
            story=ctx.story,
            section_name=ctx.section_name,
            check=original,
        )

        assert core.name == original.name
        assert core.status == original.status
        assert core.demand == original.demand
        assert core.capacity == original.capacity
        assert core.ratio == original.ratio
        assert core.unit == original.unit
        assert core.code_ref == original.code_ref
        assert core.evidence["story"] == "+14.50"
        assert core.evidence["section_name"] == "B60x60"
        assert core.evidence["consolidated_flexure_evidence"] is True
        assert "required_area_source" in core.evidence
        assert "rho" in core.evidence
        assert "formula" in core.evidence

def test_n7_flexure_bar_selection_core_check_preserves_evidence() -> None:
    from tbdy_engine.design.beams.context import BeamModelContext
    from tbdy_engine.design.beams.calculators.flexure import TBDYFlexureCalculator
    from tbdy_engine.design.beams.core_check import flexure_check_to_core_check

    ctx = BeamModelContext(
        beam_id="B175",
        story="+14.50",
        section_name="B60x60",
        bw_mm=600.0,
        h_mm=600.0,
        d_mm=550.0,
        cover_mm=40.0,
        Ln_mm=4600.0,
        fck_mpa=30.0,
        fcd_mpa=20.0,
        fctd_mpa=1.27,
        fyk_mpa=420.0,
        fyd_mpa=365.0,
        fywd_mpa=365.0,
        Vd_left_kN=90.0,
        Ve_left_kN=107.2,
        Md_left_neg_kNm=108.7,
        Md_mid_pos_kNm=84.8,
        Md_right_neg_kNm=92.4,
        axial_kN=0.0,
        stirrup_legs=2,
        stirrup_diameter_mm=10.0,
        stirrup_spacing_mm=100.0,
        longitudinal_bar_diameter_mm=16.0,
        top_required_area_cm2=8.0,
        top_selected_area_cm2=10.0,
        bottom_required_area_cm2=6.0,
        bottom_selected_area_cm2=10.0,
        missing_inputs=(),
        source={"origin": "n7_unit_test"},
    )

    result = TBDYFlexureCalculator().calculate(ctx)
    check = next(item for item in result.checks if item.name == "beam_flexure_top_bar_selection")

    core = flexure_check_to_core_check(
        beam_id=ctx.beam_id,
        story=ctx.story,
        section_name=ctx.section_name,
        check=check,
    )

    assert core.name == "beam_flexure_top_bar_selection"
    assert core.status == "OK"
    assert core.evidence["selected_bar_diameter_mm"] == check.evidence["selected_bar_diameter_mm"]
    assert core.evidence["selected_bar_legs"] == check.evidence["selected_bar_legs"]
    assert core.evidence["selected_bar_area_cm2"] == check.evidence["selected_bar_area_cm2"]
    assert core.evidence["prior_check_statuses"]["area_status"] == "OK"
    assert core.evidence["story"] == "+14.50"
    assert core.evidence["section_name"] == "B60x60"

def test_o1_plastic_moment_core_check_preserves_evidence() -> None:
    from tbdy_engine.design.beams.context import BeamModelContext
    from tbdy_engine.design.beams.calculators.flexure import TBDYFlexureCalculator
    from tbdy_engine.design.beams.core_check import flexure_check_to_core_check

    ctx = BeamModelContext(
        beam_id="B175",
        story="+14.50",
        section_name="B60x60",
        bw_mm=600.0,
        h_mm=600.0,
        d_mm=550.0,
        cover_mm=40.0,
        Ln_mm=4600.0,
        fck_mpa=30.0,
        fcd_mpa=20.0,
        fctd_mpa=1.27,
        fyk_mpa=420.0,
        fyd_mpa=365.0,
        fywd_mpa=365.0,
        Vd_left_kN=90.0,
        Ve_left_kN=107.2,
        Md_left_neg_kNm=108.7,
        Md_mid_pos_kNm=84.8,
        Md_right_neg_kNm=92.4,
        axial_kN=0.0,
        stirrup_legs=2,
        stirrup_diameter_mm=10.0,
        stirrup_spacing_mm=100.0,
        longitudinal_bar_diameter_mm=16.0,
        top_required_area_cm2=8.0,
        top_selected_area_cm2=10.0,
        bottom_required_area_cm2=6.0,
        bottom_selected_area_cm2=10.0,
        missing_inputs=(),
        source={"origin": "o1_unit_test"},
    )

    result = TBDYFlexureCalculator().calculate(ctx)
    check = next(
        item for item in result.checks
        if item.name == "beam_flexure_top_plastic_moment_available"
    )

    core = flexure_check_to_core_check(
        beam_id=ctx.beam_id,
        story=ctx.story,
        section_name=ctx.section_name,
        check=check,
    )

    assert core.name == "beam_flexure_top_plastic_moment_available"
    assert core.status == "OK"
    assert core.evidence["plastic_moment_kNm"] == check.evidence["plastic_moment_kNm"]
    assert core.evidence["plastic_moment_Nmm"] == check.evidence["plastic_moment_Nmm"]
    assert core.evidence["a_mm"] == check.evidence["a_mm"]
    assert core.evidence["lever_arm_mm"] == check.evidence["lever_arm_mm"]
    assert core.evidence["source_of_area"] == "top_selected_area_cm2"