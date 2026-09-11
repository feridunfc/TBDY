from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

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


def test_section_mechanics_is_cached_by_exact_assigned_section(monkeypatch):
    context = _Context()
    scratch = _Scratch(context.source_model_identity)
    topology = _Topology()
    section_calls = []

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _Context)
    monkeypatch.setattr(subject, "OwnedScratchContext", _Scratch)
    monkeypatch.setattr(subject, "StrictColumnTopologyBundle", _Topology)
    monkeypatch.setattr(subject, "FrameFlexuralBaseFact", _Base)
    monkeypatch.setattr(subject, "FrameSectionMechanicsFact", _Section)
    monkeypatch.setattr(subject, "FrameModifierReadFact", _Modifier)
    monkeypatch.setattr(subject, "FrameReleaseFact", _Release)
    monkeypatch.setattr(subject, "IsotropicMaterialPropertiesFact", _Material)
    monkeypatch.setattr(subject, "read_frame_names_from_session", lambda _session: (("C1", "B1"), object()))
    monkeypatch.setattr(
        subject,
        "capture_frame_flexural_base_fact",
        lambda _context, _scratch, *, component_unique_name: _Base(component_unique_name),
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

    assert section_calls == ["SAME_SECTION"]
    assert population.expected_frame_names == ("B1", "C1")
    assert all(row.section_mechanics.section_name == row.base_fact.assigned_section_name for row in population.rows)
    assert all(row.section_mechanics.evidence_ref in row.source_refs for row in population.rows)
