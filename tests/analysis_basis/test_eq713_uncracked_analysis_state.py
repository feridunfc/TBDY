from decimal import Decimal

from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    COLUMN_R1_MATERIAL_CONSTITUTIVE_LIMITATION,
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


def _live_c35():
    return build_concrete_uncracked_material_basis(
        material_name="C35/45",
        fck_mpa=35,
        factual_ec_mpa="34000",
        factual_gc_mpa="14166.66667",
        source_refs=("ETABS:MATERIAL:C35/45",),
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


def test_ts500_exact_material_match_is_retained_as_audit_fact():
    exact = _material_ok()
    assert exact.qualified
    assert exact.column_r1_eligible
    assert exact.exact_ts500_match
    assert exact.required_ec_mpa == Decimal("33000")
    assert exact.required_gc_mpa == Decimal("13200.00")
    assert exact.audit_limitations == ()


def test_live_c35_mismatch_is_held_audit_limitation_not_column_r1_blocker():
    live_c35 = _live_c35()
    assert live_c35.qualified
    assert live_c35.column_r1_eligible
    assert not live_c35.exact_ts500_match
    assert live_c35.required_ec_mpa == Decimal("33000")
    assert live_c35.required_gc_mpa == Decimal("13200.00")
    assert live_c35.ec_status.value == "MISMATCH"
    assert live_c35.gc_status.value == "MISMATCH"
    assert live_c35.audit_limitations == (
        COLUMN_R1_MATERIAL_CONSTITUTIVE_LIMITATION,
    )


def test_exact_live_c30_mismatch_is_also_audit_only_for_column_r1():
    live_c30 = build_concrete_uncracked_material_basis(
        material_name="C30/37",
        fck_mpa=30,
        factual_ec_mpa="33000",
        factual_gc_mpa="13750",
        source_refs=("ETABS:MATERIAL:C30/37",),
    )
    assert live_c30.qualified
    assert live_c30.column_r1_eligible
    assert not live_c30.exact_ts500_match
    assert live_c30.required_ec_mpa == Decimal("32000")
    assert live_c30.required_gc_mpa == Decimal("12800.00")
    assert live_c30.audit_limitations == (
        COLUMN_R1_MATERIAL_CONSTITUTIVE_LIMITATION,
    )


def test_floor_shellthick_targets_only_in_plane_when_plate_and_transverse_shear_excluded():
    result = build_area_eq713_target(_area())
    assert result.qualified
    assert result.target_property_modifiers == (
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
        Decimal("0.25"),
        Decimal("0.25"),
        Decimal("0.25"),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
        Decimal("1"),
    )
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    assert by_mode[AreaStiffnessMode.F11] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.F22] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.F12] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.M11] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert by_mode[AreaStiffnessMode.V13] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert result.target_property_modifiers[8:] == (Decimal("1"), Decimal("1"))


def test_floor_shellthick_unknown_plate_participation_blocks_only_those_modes_and_preserves_proven_target():
    result = build_area_eq713_target(_area(plate_participation=None))
    assert not result.qualified
    assert result.target_property_modifiers is not None
    assert result.target_property_modifiers[:3] == (Decimal("1"),) * 3
    assert result.target_property_modifiers[3:6] == (Decimal("0.25"),) * 3
    assert result.target_property_modifiers[8:] == (Decimal("1"), Decimal("1"))
    by_mode = {row.mode: row.disposition for row in result.mode_dispositions}
    assert by_mode[AreaStiffnessMode.F11] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[AreaStiffnessMode.M11] is ContributorDisposition.BLOCKED_UNSUPPORTED
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
        Decimal("0.9"),
        Decimal("0.8"),
        Decimal("0.7"),
        Decimal("0.6"),
        Decimal("0.5"),
        Decimal("1"),
        Decimal("1"),
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


def test_live_material_mismatch_does_not_block_modifier_target_generation():
    result = build_area_eq713_target(_area(material_basis=_live_c35()))
    assert result.qualified
    assert result.target_property_modifiers[:3] == (Decimal("1"),) * 3
    assert COLUMN_R1_MATERIAL_CONSTITUTIVE_LIMITATION in result.audit_limitations


def test_non_physical_preserved_material_basis_still_fails_closed():
    material = build_concrete_uncracked_material_basis(
        material_name="C35/45",
        fck_mpa=35,
        factual_ec_mpa="0",
        factual_gc_mpa="14166.66667",
        source_refs=("ETABS:MATERIAL:C35/45",),
    )
    result = build_area_eq713_target(_area(material_basis=material))
    assert not result.qualified
    assert result.target_property_modifiers is None
    assert any("physically qualified" in reason for reason in result.blocked_reasons)


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
        material_basis=_live_c35(),
        source_refs=("ETABS:FRAME:C1",),
    )
    assert not audit.qualified
    by_mode = {row.mode: row.disposition for row in audit.mode_dispositions}
    assert by_mode[FrameStiffnessMode.FLEXURE_2] is ContributorDisposition.TARGETED_UNCRACKED
    assert by_mode[FrameStiffnessMode.AXIAL] is ContributorDisposition.PROVEN_NON_PARTICIPATING_MODE
    assert by_mode[FrameStiffnessMode.SHEAR_2] is ContributorDisposition.BLOCKED_UNSUPPORTED
    assert COLUMN_R1_MATERIAL_CONSTITUTIVE_LIMITATION in audit.audit_limitations


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


def test_population_surfaces_material_limitation_without_using_it_as_blocker():
    area = build_area_eq713_target(
        _area(formulation=AreaFormulation.MEMBRANE, material_basis=_live_c35())
    )
    population = Eq713PopulationDisposition(area_rows=(area,), frame_rows=())
    assert population.positive
    assert population.audit_limitations == (
        COLUMN_R1_MATERIAL_CONSTITUTIVE_LIMITATION,
    )
