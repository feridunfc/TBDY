from decimal import Decimal

from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaCategory,
    AreaFormulation,
    AreaGrossBasePropertyEvidence,
    AreaStiffnessMode,
    ContributorDisposition,
    Eq713PopulationDisposition,
    FrameStiffnessMode,
    WallRole,
    audit_frame_eq713_modes,
    build_area_eq713_target,
    build_concrete_uncracked_material_basis,
)


UNITY10 = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
UNITY8 = (1, 1, 1, 1, 1, 1, 1, 1)


def _material_ok():
    return build_concrete_uncracked_material_basis(
        material_name="C35_TS500",
        fck_mpa=35,
        factual_ec_mpa=33000,
        factual_gc_mpa=13200,
        source_refs=("ETABS:MATERIAL:C35_TS500",),
    )


def _area(**overrides):
    values = dict(
        area_name="A1",
        property_name="Slab",
        category=AreaCategory.FLOOR,
        formulation=AreaFormulation.SHELL_THICK,
        is_concrete=True,
        gross_geometry_proven=True,
        thickness_proven=True,
        homogeneous_simple_property=True,
        material_overwrite_qualified=True,
        thickness_overwrite_qualified=True,
        property_modifiers=(0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 1, 1, 1, 1),
        object_modifiers=UNITY10,
        material_basis=_material_ok(),
        semi_rigid_diaphragm_participation=True,
        wall_role=None,
        default_wall_local_axes_proven=None,
        plate_participation=False,
        transverse_shear_participation=False,
        source_refs=("ETABS:AREA:A1",),
    )
    values.update(overrides)
    return AreaGrossBasePropertyEvidence.build(**values)


def test_ts500_material_basis_requires_both_ec_and_gc_exactly():
    ok = _material_ok()
    assert ok.qualified
    assert ok.required_ec_mpa == Decimal("33000")
    assert ok.required_gc_mpa == Decimal("13200.00")

    live_c35 = build_concrete_uncracked_material_basis(
        material_name="C35/45",
        fck_mpa=35,
        factual_ec_mpa="38123.781155801",
        factual_gc_mpa="15884.908814917",
        source_refs=("ETABS:MATERIAL:C35/45",),
    )
    assert not live_c35.qualified
    assert live_c35.ec_status.value == "MISMATCH"
    assert live_c35.gc_status.value == "MISMATCH"


def test_floor_shellthick_targets_only_in_plane_when_plate_and_transverse_shear_excluded():
    result = build_area_eq713_target(_area())
    assert result.qualified
    assert result.target_property_modifiers == (
        Decimal("1"), Decimal("1"), Decimal("1"),
        Decimal("0.25"), Decimal("0.25"), Decimal("0.25"),
        Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"),
    )
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    assert by_mode[AreaStiffnessMode.F11] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.F22] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.F12] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.M11] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert by_mode[AreaStiffnessMode.V13] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert result.target_property_modifiers[8:] == (Decimal("1"), Decimal("1"))


def test_floor_shellthick_unknown_plate_participation_fails_closed_without_mutation_target():
    result = build_area_eq713_target(_area(plate_participation=None))
    assert not result.qualified
    assert result.target_property_modifiers is None
    assert any("plate participation" in reason for reason in result.blocked_reasons)


def test_floor_membrane_has_no_plate_or_transverse_shear_target():
    result = build_area_eq713_target(
        _area(
            formulation=AreaFormulation.MEMBRANE,
            property_modifiers=(0.5, 0.5, 0.5, 0.9, 0.8, 0.7, 0.6, 0.5, 1, 1),
            plate_participation=None,
            transverse_shear_participation=None,
        )
    )
    assert result.qualified
    assert result.target_property_modifiers[:3] == (Decimal("1"),) * 3
    assert result.target_property_modifiers[3:] == (
        Decimal("0.9"), Decimal("0.8"), Decimal("0.7"),
        Decimal("0.6"), Decimal("0.5"), Decimal("1"), Decimal("1"),
    )
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    assert by_mode[AreaStiffnessMode.M11] is ContributorDisposition.PROVEN_NOT_APPLICABLE
    assert by_mode[AreaStiffnessMode.V23] is ContributorDisposition.PROVEN_NOT_APPLICABLE


def test_non_concrete_membrane_is_not_blindly_normalized():
    result = build_area_eq713_target(
        _area(
            property_name="Deck1",
            formulation=AreaFormulation.MEMBRANE,
            is_concrete=False,
            material_basis=None,
            property_modifiers=UNITY10,
        )
    )
    assert result.qualified
    assert result.target_property_modifiers is None
    assert all(
        row.disposition is ContributorDisposition.PROVEN_NOT_APPLICABLE
        for row in result.mode_dispositions
    )


def test_non_unity_area_object_vector_fails_closed_without_slot_inference():
    result = build_area_eq713_target(
        _area(object_modifiers=(1, 1, 1, 0.9, 1, 1, 1, 1, 1, 1))
    )
    assert not result.qualified
    assert result.target_property_modifiers is None
    assert "non-unity AreaObj" in result.blocked_reasons[0]


def test_material_mismatch_fails_before_modifier_target_generation():
    material = build_concrete_uncracked_material_basis(
        material_name="C35/45",
        fck_mpa=35,
        factual_ec_mpa="38123.781155801",
        factual_gc_mpa="15884.908814917",
        source_refs=("ETABS:MATERIAL:C35/45",),
    )
    result = build_area_eq713_target(_area(material_basis=material))
    assert not result.qualified
    assert result.target_property_modifiers is None
    assert any("Ec/Gc" in reason for reason in result.blocked_reasons)


def test_wall_pier_targets_f22_and_f12_under_proven_default_axes_only():
    result = build_area_eq713_target(
        _area(
            category=AreaCategory.WALL,
            property_name="Wall_40cm",
            wall_role=WallRole.PIER,
            default_wall_local_axes_proven=True,
            semi_rigid_diaphragm_participation=None,
            plate_participation=False,
            transverse_shear_participation=False,
            property_modifiers=(0.5, 0.5, 0.5, 0.25, 0.25, 0.25, 1, 1, 1, 1),
        )
    )
    assert result.qualified
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    assert by_mode[AreaStiffnessMode.F22] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.F12] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.F11] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert result.target_property_modifiers[8:] == (Decimal("1"), Decimal("1"))


def test_null_has_no_shell_section_stiffness_target():
    result = build_area_eq713_target(
        _area(
            property_name="None",
            category=AreaCategory.NULL,
            formulation=AreaFormulation.OTHER,
            is_concrete=False,
            material_basis=None,
            semi_rigid_diaphragm_participation=None,
        )
    )
    assert result.qualified
    assert result.target_property_modifiers is None
    assert all(
        row.disposition is ContributorDisposition.PROVEN_NOT_APPLICABLE
        for row in result.mode_dispositions
    )


def test_frame_audit_is_mode_specific_and_unknown_modes_block():
    audit = audit_frame_eq713_modes(
        component_uid="C1",
        property_modifiers=(1, 1, 1, 1, 0.7, 0.7, 1, 1),
        object_modifiers=UNITY8,
        participation={
            FrameStiffnessMode.AXIAL: False,
            FrameStiffnessMode.SHEAR_2: None,
            FrameStiffnessMode.SHEAR_3: None,
            FrameStiffnessMode.TORSION: False,
            FrameStiffnessMode.FLEXURE_2: True,
            FrameStiffnessMode.FLEXURE_3: True,
        },
        material_basis=_material_ok(),
        source_refs=("ETABS:FRAME:C1",),
    )
    assert not audit.qualified
    by_mode = {row.mode: row.disposition for row in audit.mode_dispositions}
    assert by_mode[FrameStiffnessMode.FLEXURE_2] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[FrameStiffnessMode.AXIAL] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert by_mode[FrameStiffnessMode.SHEAR_2] is ContributorDisposition.BLOCKED_UNSUPPORTED


def test_population_positive_requires_exact_expected_equals_qualified():
    area = build_area_eq713_target(_area(formulation=AreaFormulation.MEMBRANE))
    null = build_area_eq713_target(
        _area(
            area_name="N1",
            property_name="None",
            category=AreaCategory.NULL,
            formulation=AreaFormulation.OTHER,
            is_concrete=False,
            material_basis=None,
            semi_rigid_diaphragm_participation=None,
        )
    )
    population = Eq713PopulationDisposition(area_rows=(area, null), frame_rows=())
    assert population.expected_applicable_contributors == ("AREA:A1",)
    assert population.qualified_contributors == ("AREA:A1",)
    assert population.positive
