from __future__ import annotations

from types import SimpleNamespace

import tbdy_engine.application.column_public_a5 as a5
from tbdy_engine.analysis_basis.eq713_frame_mechanics import (
    classify_frame_eq713_participation,
)
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    audit_frame_eq713_modes,
    build_concrete_uncracked_material_basis,
)
from tbdy_engine.providers.etabs_frame_eq713_population_provider import (
    FrameEq713BeamMechanicsFact,
)


def test_full_model_beam_mechanics_no_longer_requires_column_joint_attachment():
    beam = FrameEq713BeamMechanicsFact(
        frame_name="B200",
        member_role="BEAM",
        story="Story1",
        label="B200",
        point_i_unique_name="P1",
        point_j_unique_name="P2",
        point_i_coord_m=(0.0, 0.0, 0.0),
        point_j_coord_m=(5.0, 2.0, 0.0),
        member_axis_vector=(5.0, 2.0, 0.0),
        local_axis_explicit=True,
        local_axis_angle_degrees=12.0,
        source_refs=("beam-mechanics:B200",),
    )
    row = SimpleNamespace(
        frame_name="B200",
        member_role="BEAM",
        beam_mechanics=beam,
        supported_end_condition=True,
        source_refs=("frame-row:B200",),
    )
    topology_without_beam_attachment = SimpleNamespace(columns=())

    mechanics = a5._frame_mechanics_evidence(
        row,
        topology_without_beam_attachment,
    )

    assert mechanics.component_uid == "B200"
    assert mechanics.member_role == "BEAM"
    assert mechanics.member_axis_vector == (5.0, 2.0, 0.0)
    assert mechanics.local_axis_explicit is True
    assert mechanics.local_axis_angle_degrees == 12.0

    classification = classify_frame_eq713_participation(mechanics)
    assert classification.resolved is False
    assert all(
        item.participates is None
        for item in classification.mode_evidence
    )


def test_newly_supported_beam_enters_existing_response_probe_scope():
    beam = FrameEq713BeamMechanicsFact(
        frame_name="B200",
        member_role="BEAM",
        story="Story1",
        label="B200",
        point_i_unique_name="P1",
        point_j_unique_name="P2",
        point_i_coord_m=(0.0, 0.0, 0.0),
        point_j_coord_m=(5.0, 0.0, 0.0),
        member_axis_vector=(5.0, 0.0, 0.0),
        local_axis_explicit=False,
        local_axis_angle_degrees=None,
        source_refs=("beam-mechanics:B200",),
    )
    row = SimpleNamespace(
        frame_name="B200",
        member_role="BEAM",
        beam_mechanics=beam,
        supported_end_condition=True,
        source_refs=("frame-row:B200",),
    )
    mechanics = a5._frame_mechanics_evidence(
        row,
        SimpleNamespace(columns=()),
    )
    classification = classify_frame_eq713_participation(mechanics)
    material = build_concrete_uncracked_material_basis(
        material_name="C35",
        fck_mpa=35.0,
        factual_ec_mpa=33000.0,
        factual_gc_mpa=13200.0,
        source_refs=("material:C35",),
    )
    disposition = audit_frame_eq713_modes(
        component_uid="B200",
        property_modifiers=(1.0,) * 8,
        object_modifiers=(1.0,) * 8,
        participation=classification.as_mapping(),
        material_basis=material,
        source_refs=("frame-row:B200",),
    )
    whole = SimpleNamespace(
        frame_rows=(disposition,),
        area_rows=(),
    )
    population = SimpleNamespace(rows=(row,))

    scope = a5._response_probe_scope(
        whole,
        population,
        (),
    )

    assert scope is not None
    frame_names, area_names, unresolved_count = scope
    assert frame_names == ("B200",)
    assert area_names == ()
    assert unresolved_count == len(disposition.mode_dispositions)
