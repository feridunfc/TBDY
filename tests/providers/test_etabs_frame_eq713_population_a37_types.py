from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_frame_eq713_population_provider as subject
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierSurface,
    FrameModifierVector,
)


def test_frame_assignments_summary_is_captured_once_for_exact_type_denominator(
    monkeypatch,
):
    calls = []

    def capture(_session, table):
        calls.append(table)
        return (
            {"UniqueName": "1", "FrameType": "Column"},
            {"UniqueName": "2", "FrameType": "Brace"},
        )

    monkeypatch.setattr(subject, "_capture_full_rows", capture)
    context = SimpleNamespace(
        verified_session=object(),
        session_provenance_ref="session:a37",
    )

    facts = subject._capture_frame_object_type_facts(context, ("1", "2"))

    assert calls == [subject.TABLE_FRAME_ASSIGNMENTS_SUMMARY]
    assert tuple(item.frame_name for item in facts) == ("1", "2")
    assert tuple(item.normalized_frame_type for item in facts) == (
        "COLUMN",
        "BRACE",
    )


def test_object_type_unique_name_join_is_deterministic_and_preserves_raw_type():
    facts = subject._build_frame_object_type_facts(
        expected_frame_names=("20", "10"),
        summary_rows=(
            {"UniqueName": "20", "ObjectType": "Brace"},
            {"UniqueName": "10", "Frame Type": "Null"},
        ),
        source_refs=("session:a37",),
    )

    assert tuple(item.frame_name for item in facts) == ("10", "20")
    assert facts[0].raw_frame_type == "Null"
    assert facts[0].normalized_frame_type == "NULL"
    assert facts[1].raw_frame_type == "Brace"
    assert facts[1].normalized_frame_type == "BRACE"


def test_duplicate_object_type_identity_fails_closed():
    with pytest.raises(subject.EtabsFrameEq713PopulationError, match="duplicate"):
        subject._build_frame_object_type_facts(
            expected_frame_names=("1",),
            summary_rows=(
                {"UniqueName": "1", "FrameType": "Null"},
                {"UniqueName": "1", "FrameType": "Null"},
            ),
            source_refs=("session:a37",),
        )


def test_missing_expected_object_type_identity_is_explicitly_unresolved():
    facts = subject._build_frame_object_type_facts(
        expected_frame_names=("1", "2"),
        summary_rows=({"UniqueName": "1", "FrameType": "Column"},),
        source_refs=("session:a37",),
    )

    by_name = {item.frame_name: item for item in facts}
    assert by_name["2"].resolution is (
        subject.FrameEq713ObjectTypeResolution.UNRESOLVED
    )
    assert by_name["2"].raw_frame_type is None
    assert "no exact" in by_name["2"].resolution_reason


def test_object_type_orphan_identity_fails_closed():
    with pytest.raises(
        subject.EtabsFrameEq713PopulationError,
        match="absent from FrameObj.GetNameList",
    ):
        subject._build_frame_object_type_facts(
            expected_frame_names=("1",),
            summary_rows=(
                {"UniqueName": "1", "FrameType": "Column"},
                {"UniqueName": "ORPHAN", "FrameType": "Brace"},
            ),
            source_refs=("session:a37",),
        )


def _scope(name: str, *, status, section=None, shape=None, material=None, role=None):
    return subject.FrameEq713ScopeFact(
        frame_name=name,
        assigned_section_name=section,
        shape=shape,
        material_name=material,
        member_role=role,
        scope_status=status,
        reason=f"scope:{name}",
        source_refs=(f"scope:{name}",),
    )


def _type(name: str, raw: str):
    return subject.FrameEq713ObjectTypeFact(
        frame_name=name,
        raw_frame_type=raw,
        normalized_frame_type=raw.upper(),
        resolution=subject.FrameEq713ObjectTypeResolution.RESOLVED,
        source_table=subject.TABLE_FRAME_ASSIGNMENTS_SUMMARY,
        source_column="FrameType",
        source_row={"UniqueName": name, "FrameType": raw},
        join_identity=name,
        resolution_reason="resolved",
        source_refs=(f"type:{name}",),
    )


def test_998_equivalent_type_and_factual_denominators_remain_exact():
    supported = tuple(
        SimpleNamespace(frame_name=f"RC-{index:03d}")
        for index in range(918)
    )
    residual = tuple(
        _scope(
            f"RES-{index:03d}",
            status=subject.FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED,
        )
        for index in range(72)
    )
    steel = tuple(
        _scope(
            f"STEEL-{index:03d}",
            status=subject.FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL,
            section="HE160A",
            shape="Steel I/Wide Flange",
            material="S355",
            role="BEAM",
        )
        for index in range(8)
    )
    expected = tuple(item.frame_name for item in (*supported, *residual, *steel))
    type_facts = tuple(
        _type(name, "Null" if name.startswith("RES-") else "Beam")
        for name in expected
    )

    population = subject.FrameEq713FactualPopulation(
        expected_frame_names=expected,
        rows=supported,
        out_of_slice_rows=(*residual, *steel),
        object_type_facts=type_facts,
        source_refs=("population:a37",),
    )

    assert len(population.expected_frame_names) == 998
    assert len(population.supported_rows) == 918
    assert len(population.out_of_slice_rows) == 80
    assert len(population.object_type_facts) == 998


@dataclass(frozen=True)
class _Section:
    section_name: str
    success: bool = True
    evidence_ref: str = "section:steel"


@dataclass(frozen=True)
class _Modifier:
    surface: FrameModifierSurface
    target_name: str
    success: bool = True
    evidence_ref: str = "modifier:steel"
    modifiers: FrameModifierVector = FrameModifierVector.from_sequence((1.0,) * 8)


@dataclass(frozen=True)
class _Release:
    frame_name: str
    success: bool = True
    evidence_ref: str = "release:steel"


@dataclass(frozen=True)
class _Material:
    material_name: str
    success: bool = True
    evidence_ref: str = "material:S355"
    modulus_of_elasticity: float = 200_000_000.0
    shear_modulus: float = 76_923_000.0


def test_steel_residual_fact_uses_generic_elastic_owners_and_no_concrete_basis(
    monkeypatch,
):
    monkeypatch.setattr(subject, "FrameSectionMechanicsFact", _Section)
    monkeypatch.setattr(subject, "FrameModifierReadFact", _Modifier)
    monkeypatch.setattr(subject, "FrameReleaseFact", _Release)
    monkeypatch.setattr(subject, "IsotropicMaterialPropertiesFact", _Material)

    fact = subject.FrameEq713ResidualStructuralFact(
        frame_name="760",
        assigned_section_name="HE160A",
        shape="Steel I/Wide Flange",
        material_name="S355",
        member_role="BEAM",
        section_mechanics=_Section("HE160A"),
        property_modifiers=_Modifier(
            FrameModifierSurface.FRAME_SECTION_PROPERTY,
            "HE160A",
        ),
        object_modifiers=_Modifier(
            FrameModifierSurface.FRAME_OBJECT,
            "760",
        ),
        releases=_Release("760"),
        isotropic_material=_Material("S355"),
        beam_mechanics=None,
        source_refs=("steel:760",),
    )

    assert fact.isotropic_material.modulus_of_elasticity > 0
    assert fact.isotropic_material.shear_modulus > 0
    assert fact.section_mechanics.section_name == "HE160A"
    assert not hasattr(fact, "concrete_fck_mpa")
    assert not hasattr(fact, "material_basis")
