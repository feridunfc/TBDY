from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_frame_eq713_population_provider as subject
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierSurface, FrameModifierVector


class _Context:
    def __init__(self):
        self.verified_session = object()
        self.source_model_identity = object()
        self.session_provenance_ref = "session:verified"


class _Scratch:
    def __init__(self, source):
        self.source_model_identity = source
        self.ownership_proof_ref = "scratch:owned"


class _Topology:
    def __init__(self):
        beam = SimpleNamespace(beam_unique_name="B1", is_supported_rc_beam=True)
        self.columns = (SimpleNamespace(unique_name="C1", beams_at_bottom=(), beams_at_top=(beam,)),)


@dataclass(frozen=True)
class _Base:
    component_unique_name: str
    assigned_section_name: str = "SAME_SECTION"
    material_name: str = "C35"
    present_force_unit: str = "kN"
    present_length_unit: str = "m"
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


class _ScopeTopology:
    def __init__(self):
        b1 = SimpleNamespace(
            beam_unique_name="B1",
            is_supported_rc_beam=True,
        )
        steel = SimpleNamespace(
            beam_unique_name="STEEL1",
            is_supported_rc_beam=False,
        )
        self.columns = (
            SimpleNamespace(
                unique_name="C1",
                beams_at_bottom=(),
                beams_at_top=(b1, steel),
            ),
        )



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


def _scope_fact(name: str):
    return subject.FrameEq713ScopeFact(
        frame_name=name,
        assigned_section_name=f"SEC-{name}",
        shape="Steel I/Wide Flange",
        material_name="S355",
        member_role=None,
        scope_status=subject.FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
        reason=f"scope blocked for {name}",
        source_refs=(f"scope:{name}",),
    )


def test_section_mechanics_is_cached_by_exact_assigned_section(monkeypatch):
    context = _Context()
    scratch = _Scratch(context.source_model_identity)
    topology = _Topology()
    section_calls = []
    snapshot = object()
    snapshot_calls = []
    bind_calls = []

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _Context)
    monkeypatch.setattr(subject, "OwnedScratchContext", _Scratch)
    monkeypatch.setattr(subject, "StrictColumnTopologyBundle", _Topology)
    monkeypatch.setattr(subject, "FrameFlexuralBaseFact", _Base)
    monkeypatch.setattr(subject, "FrameSectionMechanicsFact", _Section)
    monkeypatch.setattr(subject, "FrameModifierReadFact", _Modifier)
    monkeypatch.setattr(subject, "FrameReleaseFact", _Release)
    monkeypatch.setattr(subject, "IsotropicMaterialPropertiesFact", _Material)
    monkeypatch.setattr(subject, "read_frame_names_from_session", lambda _session: (("C1", "B1"), object()))
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
            ("B1", "C1"),
            (),
        ),
    )
    monkeypatch.setattr(
        subject,
        "_capture_supported_beam_mechanics",
        lambda _context, _scratch, _supported: {
            "B1": _beam_mechanics("B1"),
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

    def section_fact(_session, *, section_name):
        section_calls.append(section_name)
        return _Section(section_name)

    monkeypatch.setattr(subject, "get_frame_section_mechanics_from_session", section_fact)
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
    monkeypatch.setattr(subject, "_stress_to_mpa", lambda value, *_args: Decimal(str(value)))

    population = subject.capture_frame_eq713_factual_population(context, scratch, topology)

    assert snapshot_calls == [(context, scratch)]
    assert bind_calls == ["B1", "C1"]
    assert section_calls == ["SAME_SECTION"]
    assert population.expected_frame_names == ("B1", "C1")
    assert population.supported_rows == population.rows
    assert population.out_of_slice_rows == ()
    assert all(row.section_mechanics.section_name == row.base_fact.assigned_section_name for row in population.rows)
    assert all(row.section_mechanics.evidence_ref in row.source_refs for row in population.rows)


def test_full_frame_scope_partitions_supported_and_out_of_slice_without_disappearing(
    monkeypatch,
):
    topology = _ScopeTopology()
    monkeypatch.setattr(subject, "StrictColumnTopologyBundle", _ScopeTopology)

    assignment_rows = (
        {"UniqueName": "C1", "SectProp": "CSEC"},
        {"UniqueName": "B1", "SectProp": "BSEC"},
        {"UniqueName": "STEEL1", "SectProp": "HE160A"},
        {"UniqueName": "OTHER1", "SectProp": "OTHERSEC"},
    )
    summary_rows = (
        {"Name": "CSEC", "Shape": "Concrete Rectangular", "Material": "C35"},
        {"Name": "BSEC", "Shape": "Concrete Rectangular", "Material": "C35"},
        {"Name": "HE160A", "Shape": "Steel I/Wide Flange", "Material": "S355"},
        {"Name": "OTHERSEC", "Shape": "Concrete Rectangular", "Material": "C35"},
    )
    rectangular_rows = (
        {"Name": "CSEC"},
        {"Name": "BSEC"},
        {"Name": "OTHERSEC"},
    )
    concrete_rows = ({"Material": "C35"},)

    supported, out_of_slice = subject._build_frame_scope_partition(
        expected_frame_names=("C1", "B1", "STEEL1", "OTHER1"),
        topology=topology,
        column_connectivity_rows=({"UniqueName": "C1"},),
        beam_connectivity_rows=(
            {"UniqueName": "B1"},
            {"UniqueName": "STEEL1"},
            {"UniqueName": "OTHER1"},
        ),
        assignment_rows=assignment_rows,
        section_summary_rows=summary_rows,
        rectangular_rows=rectangular_rows,
        concrete_rows=concrete_rows,
        source_refs=("session:verified", "scratch:owned"),
    )

    assert supported == ("B1", "C1", "OTHER1")
    assert tuple(row.frame_name for row in out_of_slice) == ("STEEL1",)
    by_name = {row.frame_name: row for row in out_of_slice}
    assert by_name["STEEL1"].member_role == "BEAM"
    assert by_name["STEEL1"].assigned_section_name == "HE160A"
    assert by_name["STEEL1"].shape == "Steel I/Wide Flange"
    assert by_name["STEEL1"].material_name == "S355"
    assert by_name["STEEL1"].scope_status is (
        subject.FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL
    )
    assert all(not hasattr(row, "base_fact") for row in out_of_slice)

    population = subject.FrameEq713FactualPopulation(
        expected_frame_names=("C1", "B1", "STEEL1", "OTHER1"),
        rows=(
            SimpleNamespace(frame_name="C1"),
            SimpleNamespace(frame_name="B1"),
            SimpleNamespace(frame_name="OTHER1"),
        ),
        out_of_slice_rows=out_of_slice,
        source_refs=("population:exact",),
    )
    assert population.expected_frame_names == (
        "B1",
        "C1",
        "OTHER1",
        "STEEL1",
    )
    assert tuple(row.frame_name for row in population.supported_rows) == (
        "B1",
        "C1",
        "OTHER1",
    )
    assert tuple(row.frame_name for row in population.out_of_slice_rows) == (
        "STEEL1",
    )


def test_capture_only_materializes_supported_rows_and_preserves_out_of_slice(
    monkeypatch,
):
    context = _Context()
    scratch = _Scratch(context.source_model_identity)
    topology = _Topology()
    out_of_slice = (
        subject.FrameEq713ScopeFact(
            frame_name="OTHER1",
            assigned_section_name="OTHERSEC",
            shape="Concrete Rectangular",
            material_name="C35",
            member_role=None,
            scope_status=subject.FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
            reason="OTHER1 role unresolved",
            source_refs=("scope:OTHER1",),
        ),
        subject.FrameEq713ScopeFact(
            frame_name="STEEL1",
            assigned_section_name="HE160A",
            shape="Steel I/Wide Flange",
            material_name="S355",
            member_role="BEAM",
            scope_status=(
                subject.FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL
            ),
            reason="STEEL1 outside RC slice",
            source_refs=("scope:STEEL1",),
        ),
    )
    base_calls = []
    snapshot = object()
    snapshot_calls = []

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _Context)
    monkeypatch.setattr(subject, "OwnedScratchContext", _Scratch)
    monkeypatch.setattr(subject, "StrictColumnTopologyBundle", _Topology)
    monkeypatch.setattr(subject, "FrameFlexuralBaseFact", _Base)
    monkeypatch.setattr(subject, "FrameSectionMechanicsFact", _Section)
    monkeypatch.setattr(subject, "FrameModifierReadFact", _Modifier)
    monkeypatch.setattr(subject, "FrameReleaseFact", _Release)
    monkeypatch.setattr(subject, "IsotropicMaterialPropertiesFact", _Material)
    monkeypatch.setattr(
        subject,
        "read_frame_names_from_session",
        lambda _session: (("C1", "B1", "STEEL1", "OTHER1"), object()),
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
            ("B1", "C1"),
            out_of_slice,
        ),
    )
    monkeypatch.setattr(
        subject,
        "_capture_supported_beam_mechanics",
        lambda _context, _scratch, _supported: {
            "B1": _beam_mechanics("B1"),
        },
    )

    def bind_base(bound_snapshot, frame_name):
        assert bound_snapshot is snapshot
        base_calls.append(frame_name)
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
    assert base_calls == ["B1", "C1"]
    assert tuple(row.frame_name for row in population.supported_rows) == (
        "B1",
        "C1",
    )
    assert tuple(row.frame_name for row in population.out_of_slice_rows) == (
        "OTHER1",
        "STEEL1",
    )
    assert population.expected_frame_names == (
        "B1",
        "C1",
        "OTHER1",
        "STEEL1",
    )


@pytest.mark.parametrize(
    ("expected", "supported", "out_of_slice", "match"),
    (
        (
            ("A", "B"),
            (SimpleNamespace(frame_name="A"),),
            (_scope_fact("B"), _scope_fact("B")),
            "duplicate out-of-slice",
        ),
        (
            ("A", "B"),
            (SimpleNamespace(frame_name="A"),),
            (),
            "missing=.*B",
        ),
        (
            ("A",),
            (SimpleNamespace(frame_name="A"),),
            (_scope_fact("ORPHAN"),),
            "orphan=.*ORPHAN",
        ),
    ),
)
def test_frame_population_partition_invariants_fail_closed(
    expected,
    supported,
    out_of_slice,
    match,
):
    with pytest.raises(subject.EtabsFrameEq713PopulationError, match=match):
        subject.FrameEq713FactualPopulation(
            expected_frame_names=expected,
            rows=supported,
            out_of_slice_rows=out_of_slice,
            source_refs=("population:exact",),
        )
