from tbdy_engine.analysis_basis.eq713_frame_mechanics import (
    FrameMechanicsEvidence,
    build_frame_eq713_modifier_target,
    classify_frame_eq713_participation,
)
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    ContributorDisposition,
    FrameStiffnessMode,
    audit_frame_eq713_modes,
    build_concrete_uncracked_material_basis,
)


def _material():
    return build_concrete_uncracked_material_basis(
        material_name="C35",
        fck_mpa=35,
        factual_ec_mpa=33000,
        factual_gc_mpa=13200,
        source_refs=("material:C35",),
    )


def _vertical():
    return FrameMechanicsEvidence(
        component_uid="C1",
        member_role="COLUMN",
        member_axis_vector=(0.0, 0.0, 3.0),
        supported_end_condition=True,
        local_axis_explicit=True,
        local_axis_angle_degrees=0.0,
        source_refs=("strict-topology:C1", "release:C1:none"),
    )


def test_vertical_column_classifier_is_mode_specific_not_all_true():
    result = classify_frame_eq713_participation(_vertical())
    mapping = result.as_mapping()
    assert mapping == {
        FrameStiffnessMode.AXIAL: False,
        FrameStiffnessMode.SHEAR_2: True,
        FrameStiffnessMode.SHEAR_3: True,
        FrameStiffnessMode.TORSION: False,
        FrameStiffnessMode.FLEXURE_2: True,
        FrameStiffnessMode.FLEXURE_3: True,
    }
    assert result.resolved is True
    assert all(row.reason for row in result.mode_evidence)


def test_nonvertical_or_beam_mechanics_remain_unknown_and_audit_fails_closed():
    evidence = FrameMechanicsEvidence(
        component_uid="B1",
        member_role="BEAM",
        member_axis_vector=(3.0, 0.0, 0.0),
        supported_end_condition=True,
        local_axis_explicit=False,
        local_axis_angle_degrees=None,
        source_refs=("strict-topology:B1", "release:B1:none"),
    )
    classification = classify_frame_eq713_participation(evidence)
    assert all(value is None for value in classification.as_mapping().values())
    audit = audit_frame_eq713_modes(
        component_uid="B1",
        property_modifiers=(0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0),
        object_modifiers=(1.0,) * 8,
        participation=classification.as_mapping(),
        material_basis=_material(),
        source_refs=classification.source_refs,
    )
    assert audit.qualified is False
    assert all(row.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED for row in audit.mode_dispositions)


def test_target_normalizes_only_targeted_modes_and_preserves_mass_weight():
    classification = classify_frame_eq713_participation(_vertical())
    audit = audit_frame_eq713_modes(
        component_uid="C1",
        property_modifiers=(0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.2, 1.3),
        object_modifiers=(1.0,) * 8,
        participation=classification.as_mapping(),
        material_basis=_material(),
        source_refs=classification.source_refs,
    )
    target = build_frame_eq713_modifier_target(
        current_modifiers=(0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.2, 1.3),
        disposition=audit,
    )
    assert tuple(float(value) for value in target.target_modifiers) == (
        0.41, 1.0, 1.0, 0.74, 1.0, 1.0, 1.2, 1.3
    )
    assert target.preserved_modes == (FrameStiffnessMode.AXIAL, FrameStiffnessMode.TORSION)
