from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

import tbdy_engine.providers.etabs_frame_eq713_population_provider as subject
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierSurface,
    FrameModifierVector,
)


class _Context:
    def __init__(self):
        self.verified_session = object()
        self.source_model_identity = object()
        self.session_provenance_ref = "session:batch"


class _Scratch:
    def __init__(self, source):
        self.source_model_identity = source
        self.ownership_proof_ref = "scratch:batch"


class _ManyTopology:
    def __init__(self):
        beams = tuple(
            SimpleNamespace(
                beam_unique_name=name,
                is_supported_rc_beam=True,
            )
            for name in ("B1", "B2", "B3")
        )
        self.columns = (
            SimpleNamespace(
                unique_name="C1",
                beams_at_bottom=(),
                beams_at_top=beams,
            ),
        )


@dataclass(frozen=True)
class _Base:
    component_unique_name: str
    assigned_section_name: str = "SAME_SECTION"
    material_name: str = "C35"
    present_force_unit: int = 4
    present_length_unit: int = 6
    source_refs: tuple[str, ...] = ("base:ref",)
    evidence_ref: str = "base:evidence"


@dataclass(frozen=True)
class _Section:
    section_name: str
    success: bool = True
    evidence_ref: str = "section:evidence"


@dataclass(frozen=True)
class _Modifier:
    surface: FrameModifierSurface
    target_name: str
    success: bool = True
    evidence_ref: str = "modifier:evidence"
    modifiers: FrameModifierVector = FrameModifierVector.from_sequence((1.0,) * 8)


@dataclass(frozen=True)
class _Release:
    frame_name: str
    success: bool = True
    evidence_ref: str = "release:evidence"
    i_end_released: tuple[bool, ...] = (False,) * 6
    j_end_released: tuple[bool, ...] = (False,) * 6
    i_end_partial_fixity: tuple[float, ...] = (0.0,) * 6
    j_end_partial_fixity: tuple[float, ...] = (0.0,) * 6


@dataclass(frozen=True)
class _Material:
    material_name: str
    success: bool = True
    evidence_ref: str = "material:evidence"
    modulus_of_elasticity: float = 33_000.0
    shear_modulus: float = 13_200.0



def _beam_mechanics(name: str):
    return subject.FrameEq713BeamMechanicsFact(
        frame_name=name,
        member_role="BEAM",
        story="Story1",
        label=f"LBL-{name}",
        point_i_unique_name=f"{name}-I",
        point_j_unique_name=f"{name}-J",
        point_i_coord_m=(0.0, 0.0, 0.0),
        point_j_coord_m=(1.0, 0.0, 0.0),
        member_axis_vector=(1.0, 0.0, 0.0),
        local_axis_explicit=False,
        local_axis_angle_degrees=None,
        source_refs=(f"beam-mechanics:{name}",),
    )


def test_population_captures_one_base_snapshot_and_binds_many_supported_frames(
    monkeypatch,
):
    context = _Context()
    scratch = _Scratch(context.source_model_identity)
    topology = _ManyTopology()
    snapshot = object()
    snapshot_calls = []
    bind_calls = []

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _Context)
    monkeypatch.setattr(subject, "OwnedScratchContext", _Scratch)
    monkeypatch.setattr(subject, "StrictColumnTopologyBundle", _ManyTopology)
    monkeypatch.setattr(subject, "FrameFlexuralBaseFact", _Base)
    monkeypatch.setattr(subject, "FrameSectionMechanicsFact", _Section)
    monkeypatch.setattr(subject, "FrameModifierReadFact", _Modifier)
    monkeypatch.setattr(subject, "FrameReleaseFact", _Release)
    monkeypatch.setattr(subject, "IsotropicMaterialPropertiesFact", _Material)

    monkeypatch.setattr(
        subject,
        "read_frame_names_from_session",
        lambda _session: (("C1", "B1", "B2", "B3"), object()),
    )

    def capture_snapshot(*, context, owned_scratch):
        snapshot_calls.append((context, owned_scratch))
        return snapshot

    monkeypatch.setattr(
        subject,
        "capture_frame_flexural_base_snapshot",
        capture_snapshot,
    )
    monkeypatch.setattr(
        subject,
        "_capture_frame_scope_partition",
        lambda _context, _snapshot, _topology, _expected: (
            ("B1", "B2", "B3", "C1"),
            (),
        ),
    )
    monkeypatch.setattr(
        subject,
        "_capture_supported_beam_mechanics",
        lambda _context, _scratch, _supported: {
            name: _beam_mechanics(name)
            for name in ("B1", "B2", "B3")
        },
    )

    def bind_base(bound_snapshot, frame_name):
        assert bound_snapshot is snapshot
        bind_calls.append(frame_name)
        return _Base(frame_name)

    monkeypatch.setattr(
        subject,
        "bind_frame_flexural_base_fact_from_snapshot",
        bind_base,
    )
    monkeypatch.setattr(
        subject,
        "get_frame_section_mechanics_from_session",
        lambda _session, *, section_name: _Section(section_name),
    )
    monkeypatch.setattr(
        subject,
        "get_frame_modifiers_from_session",
        lambda _session, *, surface, target_name: _Modifier(surface, target_name),
    )
    monkeypatch.setattr(
        subject,
        "get_frame_releases_from_session",
        lambda _session, *, frame_name: _Release(frame_name),
    )
    monkeypatch.setattr(
        subject,
        "get_isotropic_material_properties_from_session",
        lambda _session, *, material_name: _Material(material_name),
    )
    monkeypatch.setattr(
        subject,
        "_stress_to_mpa",
        lambda value, *_args: Decimal(str(value)),
    )

    population = subject.capture_frame_eq713_factual_population(
        context,
        scratch,
        topology,
    )

    assert snapshot_calls == [(context, scratch)]
    assert bind_calls == ["B1", "B2", "B3", "C1"]
    assert tuple(row.frame_name for row in population.supported_rows) == (
        "B1",
        "B2",
        "B3",
        "C1",
    )
    assert population.out_of_slice_rows == ()
    assert population.expected_frame_names == ("B1", "B2", "B3", "C1")

    beam = next(row for row in population.supported_rows if row.frame_name == "B1")
    assert beam.member_role == "BEAM"
    assert beam.base_fact.component_unique_name == "B1"
    assert beam.section_mechanics.section_name == beam.base_fact.assigned_section_name
    assert beam.property_modifiers.success is True
    assert beam.object_modifiers.success is True
    assert beam.releases.frame_name == "B1"
    assert beam.releases.success is True
    assert beam.isotropic_material.material_name == beam.base_fact.material_name
    assert beam.isotropic_material.success is True
    assert beam.beam_mechanics.frame_name == "B1"
