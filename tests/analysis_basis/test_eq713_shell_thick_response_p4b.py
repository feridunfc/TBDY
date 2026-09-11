from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    AreaShellThickResponseGeneration,
    _area_shell_thick_values_by_mode,
    resolve_area_response_modes,
)
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaCategory,
    AreaFormulation,
    AreaGrossBasePropertyEvidence,
    AreaStiffnessMode,
    ContributorDisposition,
    build_area_eq713_target,
    build_concrete_uncracked_material_basis,
)
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSurface,
    AreaModifierVector,
)
from tbdy_engine.etabs.oapi.eq713_response_results import AreaStrainShellResponseRow


def _material():
    return build_concrete_uncracked_material_basis(
        material_name="C35",
        fck_mpa=35,
        factual_ec_mpa=33000,
        factual_gc_mpa=13200,
        source_refs=("ETABS:MATERIAL:C35",),
    )


def _evidence(**overrides):
    values = dict(
        area_name="A1",
        property_name="SLAB-THICK",
        category=AreaCategory.FLOOR,
        formulation=AreaFormulation.SHELL_THICK,
        is_concrete=True,
        gross_geometry_proven=True,
        thickness_proven=True,
        homogeneous_simple_property=True,
        material_overwrite_qualified=True,
        thickness_overwrite_qualified=True,
        property_modifiers=(0.25, 0.25, 0.25, 0.30, 0.30, 0.30, 0.40, 0.40, 1.0, 1.0),
        object_modifiers=(1.0,) * 10,
        material_basis=_material(),
        semi_rigid_diaphragm_participation=True,
        wall_role=None,
        default_wall_local_axes_proven=None,
        plate_participation=None,
        transverse_shear_participation=None,
        source_refs=("ETABS:AREA:A1",),
    )
    values.update(overrides)
    return AreaGrossBasePropertyEvidence.build(**values)


def _row(**overrides):
    values = dict(
        object_name="A1",
        element_name="E1",
        point_element_name="P1",
        load_case="EQX",
        step_type="",
        step_number=0.0,
        e11_top=3.0,
        e22_top=5.0,
        g12_top=7.0,
        emax_top=0.0,
        emin_top=0.0,
        eangle_top=0.0,
        evm_top=0.0,
        e11_bottom=1.0,
        e22_bottom=1.0,
        g12_bottom=1.0,
        emax_bottom=0.0,
        emin_bottom=0.0,
        eangle_bottom=0.0,
        evm_bottom=0.0,
        g13_avg=11.0,
        g23_avg=13.0,
        gmax_avg=0.0,
        gangle_avg=0.0,
    )
    values.update(overrides)
    return AreaStrainShellResponseRow(**values)


def _modifiers(values=(1.0,) * 10):
    return AreaModifierReadFact(
        surface=AreaModifierSurface.AREA_PROPERTY,
        target_name="SLAB-THICK",
        modifiers=AreaModifierVector.from_sequence(values),
        return_code=0,
    )


def _generation(*rows, modifiers=None):
    return AreaShellThickResponseGeneration(
        strain_rows=tuple(rows),
        property_modifiers=modifiers or _modifiers(),
        source_refs=("B5:RESULT:G1", "B4B:AREA:AFTER:G1"),
    )


def test_approved_shell_thick_derivation_maps_all_eight_modes() -> None:
    values = _area_shell_thick_values_by_mode((_row(),))
    assert values[AreaStiffnessMode.F11] == (2.0,)
    assert values[AreaStiffnessMode.F22] == (3.0,)
    assert values[AreaStiffnessMode.F12] == (4.0,)
    assert values[AreaStiffnessMode.M11] == (2.0,)
    assert values[AreaStiffnessMode.M22] == (4.0,)
    assert values[AreaStiffnessMode.M12] == (6.0,)
    assert values[AreaStiffnessMode.V13] == (11.0,)
    assert values[AreaStiffnessMode.V23] == (13.0,)


def test_nonzero_shell_thick_plate_and_transverse_response_targets_blocked_modes() -> None:
    evidence = _evidence()
    base = build_area_eq713_target(evidence)
    assert not base.qualified
    result = resolve_area_response_modes(
        base=base,
        gross_evidence=evidence,
        shell_thickness=0.20,
        response_generations=(_generation(_row()),),
        source_refs=("QUALIFIED:STATIC:XY",),
    )
    assert result.qualified
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    for mode in AreaStiffnessMode:
        assert by_mode[mode] is ContributorDisposition.TARGETED_UNCRACKED
    assert result.target_property_modifiers == (Decimal("1"),) * 8 + (Decimal("1.0"), Decimal("1.0"))


def test_zero_shell_strain_remains_unknown_and_never_becomes_nonparticipating() -> None:
    evidence = _evidence()
    base = build_area_eq713_target(evidence)
    zero = _row(
        e11_top=0.0,
        e22_top=0.0,
        g12_top=0.0,
        e11_bottom=0.0,
        e22_bottom=0.0,
        g12_bottom=0.0,
        g13_avg=0.0,
        g23_avg=0.0,
    )
    result = resolve_area_response_modes(
        base=base,
        gross_evidence=evidence,
        shell_thickness=0.20,
        response_generations=(_generation(zero),),
        source_refs=("QUALIFIED:STATIC:XY",),
    )
    assert not result.qualified
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    for mode in (
        AreaStiffnessMode.M11,
        AreaStiffnessMode.M22,
        AreaStiffnessMode.M12,
        AreaStiffnessMode.V13,
        AreaStiffnessMode.V23,
    ):
        assert by_mode[mode] is ContributorDisposition.BLOCKED_UNSUPPORTED
        assert by_mode[mode] is not ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE


def test_nonpositive_required_property_modifier_fails_closed_for_corresponding_mode() -> None:
    evidence = _evidence()
    base = build_area_eq713_target(evidence)
    modifiers = list((1.0,) * 10)
    modifiers[3] = 0.0
    result = resolve_area_response_modes(
        base=base,
        gross_evidence=evidence,
        shell_thickness=0.20,
        response_generations=(_generation(_row(), modifiers=_modifiers(tuple(modifiers))),),
        source_refs=("QUALIFIED:STATIC:XY",),
    )
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    assert by_mode[AreaStiffnessMode.M11] is ContributorDisposition.BLOCKED_UNSUPPORTED
    assert by_mode[AreaStiffnessMode.M22] is ContributorDisposition.TARGETED_UNCRACKED


def test_nonphysical_material_or_thickness_fails_closed() -> None:
    evidence = _evidence()
    base = build_area_eq713_target(evidence)
    result = resolve_area_response_modes(
        base=base,
        gross_evidence=evidence,
        shell_thickness=0.0,
        response_generations=(_generation(_row()),),
        source_refs=("QUALIFIED:STATIC:XY",),
    )
    assert not result.qualified

    bad_material = replace(_material(), factual_gc_mpa=Decimal("0"))
    bad_evidence = _evidence(material_basis=bad_material)
    bad_base = build_area_eq713_target(bad_evidence)
    assert not bad_base.qualified


def test_derivation_is_not_promoted_to_nonhomogeneous_or_membrane_shells() -> None:
    layered_like = _evidence(homogeneous_simple_property=False)
    layered_base = build_area_eq713_target(layered_like)
    assert layered_base.target_property_modifiers is None
    assert resolve_area_response_modes(
        base=layered_base,
        gross_evidence=layered_like,
        shell_thickness=0.20,
        response_generations=(_generation(_row()),),
        source_refs=("QUALIFIED:STATIC:XY",),
    ) is layered_base

    membrane = _evidence(formulation=AreaFormulation.MEMBRANE)
    membrane_base = build_area_eq713_target(membrane)
    membrane_result = resolve_area_response_modes(
        base=membrane_base,
        gross_evidence=membrane,
        shell_thickness=0.20,
        response_generations=(_generation(_row()),),
        source_refs=("QUALIFIED:STATIC:XY",),
    )
    assert membrane_result is membrane_base
