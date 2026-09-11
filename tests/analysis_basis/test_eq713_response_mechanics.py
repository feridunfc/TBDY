from __future__ import annotations

from dataclasses import replace

import pytest

from tbdy_engine.analysis_basis.eq713_frame_mechanics import (
    FrameModeParticipationClassification,
    FrameModeParticipationEvidence,
)
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    _response_truth,
    classify_frame_response_participation,
)
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import FrameStiffnessMode
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.etabs.oapi.frame_section_mechanics import (
    FrameSectionMechanicsFact,
    _decode_get_sect_props,
)
from tbdy_engine.etabs.oapi.material_properties import IsotropicMaterialPropertiesFact


def _base() -> FrameModeParticipationClassification:
    refs = ("TEST:STATIC_BEAM_UNRESOLVED",)
    return FrameModeParticipationClassification(
        "FRAME:B1",
        tuple(
            FrameModeParticipationEvidence(mode, None, "unresolved BEAM mode", refs)
            for mode in FrameStiffnessMode
        ),
        refs,
    )


def _section() -> FrameSectionMechanicsFact:
    return FrameSectionMechanicsFact(
        section_name="B300X500",
        area=0.15,
        shear_area_2=0.12,
        shear_area_3=0.11,
        torsional_constant=0.002,
        inertia_22=0.003125,
        inertia_33=0.001125,
        return_code=0,
    )


def _material() -> IsotropicMaterialPropertiesFact:
    return IsotropicMaterialPropertiesFact(
        material_name="C30",
        modulus_of_elasticity=30_000_000.0,
        poisson_ratio=0.2,
        thermal_coefficient=1.0e-5,
        shear_modulus=12_500_000.0,
        temperature=0.0,
        return_code=0,
    )


def _modifiers(
    *,
    surface: FrameModifierSurface,
    target_name: str,
    vector: FrameModifierVector | None = None,
) -> FrameModifierReadFact:
    return FrameModifierReadFact(
        surface=surface,
        target_name=target_name,
        modifiers=vector
        or FrameModifierVector(
            area=1.0,
            shear_area_local_2=1.0,
            shear_area_local_3=1.0,
            torsional_constant=1.0,
            inertia_local_2=1.0,
            inertia_local_3=1.0,
            mass=1.0,
            weight=1.0,
        ),
        return_code=0,
    )


def _classify(
    *,
    values_by_mode: dict[FrameStiffnessMode, tuple[float, ...]],
    section: FrameSectionMechanicsFact | None = None,
    material: IsotropicMaterialPropertiesFact | None = None,
    property_modifiers: FrameModifierReadFact | None = None,
    object_modifiers: FrameModifierReadFact | None = None,
) -> FrameModeParticipationClassification:
    section = section or _section()
    material = material or _material()
    property_modifiers = property_modifiers or _modifiers(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name=section.section_name,
    )
    object_modifiers = object_modifiers or _modifiers(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="B1",
    )
    return classify_frame_response_participation(
        base=_base(),
        values_by_mode=values_by_mode,
        source_refs=("TEST:FRAME_FORCE",),
        member_role="BEAM",
        section_mechanics=section,
        material_properties=material,
        property_modifiers=property_modifiers,
        object_modifiers=object_modifiers,
    )


@pytest.mark.parametrize(
    ("mode", "generalized_force"),
    (
        (FrameStiffnessMode.AXIAL, 10.0),
        (FrameStiffnessMode.SHEAR_2, 11.0),
        (FrameStiffnessMode.SHEAR_3, 12.0),
        (FrameStiffnessMode.TORSION, 13.0),
        (FrameStiffnessMode.FLEXURE_2, 14.0),
        (FrameStiffnessMode.FLEXURE_3, 15.0),
    ),
)
def test_nonzero_conjugate_force_with_positive_finite_stiffness_proves_true(
    mode: FrameStiffnessMode,
    generalized_force: float,
) -> None:
    result = _classify(values_by_mode={mode: (generalized_force,)})
    assert result.as_mapping()[mode] is True


def test_zero_generalized_response_is_unknown_and_no_response_mode_is_false() -> None:
    result = _classify(
        values_by_mode={mode: (0.0, -0.0) for mode in FrameStiffnessMode}
    )
    assert all(value is None for value in result.as_mapping().values())
    assert all(value is not False for value in result.as_mapping().values())


def test_response_truth_zero_is_unknown_never_false() -> None:
    participates, _reason = _response_truth(values=(0.0, 0.0), effective_modifier=1.0)
    assert participates is None


def test_nonzero_force_without_complete_stiffness_facts_is_unknown() -> None:
    result = classify_frame_response_participation(
        base=_base(),
        values_by_mode={FrameStiffnessMode.AXIAL: (10.0,)},
        source_refs=("TEST:FRAME_FORCE",),
        member_role="BEAM",
    )
    assert result.as_mapping()[FrameStiffnessMode.AXIAL] is None


@pytest.mark.parametrize(
    ("mode", "attribute"),
    (
        (FrameStiffnessMode.AXIAL, "area"),
        (FrameStiffnessMode.SHEAR_2, "shear_area_2"),
        (FrameStiffnessMode.SHEAR_3, "shear_area_3"),
        (FrameStiffnessMode.TORSION, "torsional_constant"),
        (FrameStiffnessMode.FLEXURE_2, "inertia_22"),
        (FrameStiffnessMode.FLEXURE_3, "inertia_33"),
    ),
)
def test_nonpositive_section_quantity_fails_closed(
    mode: FrameStiffnessMode,
    attribute: str,
) -> None:
    section = replace(_section(), **{attribute: 0.0})
    result = _classify(values_by_mode={mode: (1.0,)}, section=section)
    assert result.as_mapping()[mode] is None


@pytest.mark.parametrize(
    ("mode", "material_attribute"),
    (
        (FrameStiffnessMode.AXIAL, "modulus_of_elasticity"),
        (FrameStiffnessMode.FLEXURE_2, "modulus_of_elasticity"),
        (FrameStiffnessMode.FLEXURE_3, "modulus_of_elasticity"),
        (FrameStiffnessMode.SHEAR_2, "shear_modulus"),
        (FrameStiffnessMode.SHEAR_3, "shear_modulus"),
        (FrameStiffnessMode.TORSION, "shear_modulus"),
    ),
)
def test_nonpositive_required_modulus_fails_closed(
    mode: FrameStiffnessMode,
    material_attribute: str,
) -> None:
    material = replace(_material(), **{material_attribute: 0.0})
    result = _classify(values_by_mode={mode: (1.0,)}, material=material)
    assert result.as_mapping()[mode] is None


@pytest.mark.parametrize(
    ("mode", "modifier_attribute"),
    (
        (FrameStiffnessMode.AXIAL, "area"),
        (FrameStiffnessMode.SHEAR_2, "shear_area_local_2"),
        (FrameStiffnessMode.SHEAR_3, "shear_area_local_3"),
        (FrameStiffnessMode.TORSION, "torsional_constant"),
        (FrameStiffnessMode.FLEXURE_2, "inertia_local_2"),
        (FrameStiffnessMode.FLEXURE_3, "inertia_local_3"),
    ),
)
def test_nonpositive_property_modifier_slot_fails_closed(
    mode: FrameStiffnessMode,
    modifier_attribute: str,
) -> None:
    vector = replace(
        _modifiers(
            surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
            target_name="B300X500",
        ).modifiers,
        **{modifier_attribute: 0.0},
    )
    property_modifiers = _modifiers(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="B300X500",
        vector=vector,
    )
    result = _classify(
        values_by_mode={mode: (1.0,)},
        property_modifiers=property_modifiers,
    )
    assert result.as_mapping()[mode] is None


@pytest.mark.parametrize(
    ("mode", "modifier_attribute"),
    (
        (FrameStiffnessMode.AXIAL, "area"),
        (FrameStiffnessMode.SHEAR_2, "shear_area_local_2"),
        (FrameStiffnessMode.SHEAR_3, "shear_area_local_3"),
        (FrameStiffnessMode.TORSION, "torsional_constant"),
        (FrameStiffnessMode.FLEXURE_2, "inertia_local_2"),
        (FrameStiffnessMode.FLEXURE_3, "inertia_local_3"),
    ),
)
def test_nonpositive_object_modifier_slot_fails_closed(
    mode: FrameStiffnessMode,
    modifier_attribute: str,
) -> None:
    vector = replace(
        _modifiers(
            surface=FrameModifierSurface.FRAME_OBJECT,
            target_name="B1",
        ).modifiers,
        **{modifier_attribute: -1.0},
    )
    object_modifiers = _modifiers(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="B1",
        vector=vector,
    )
    result = _classify(
        values_by_mode={mode: (1.0,)},
        object_modifiers=object_modifiers,
    )
    assert result.as_mapping()[mode] is None


def test_frame_section_get_sect_props_decoder_captures_required_mechanics() -> None:
    decoded = _decode_get_sect_props(
        (
            0.15,
            0.12,
            0.11,
            0.002,
            0.003125,
            0.001125,
            0.01,
            0.02,
            0.03,
            0.04,
            0.05,
            0.06,
            0,
        )
    )
    assert decoded == (0.15, 0.12, 0.11, 0.002, 0.003125, 0.001125, 0)


def test_frame_section_fact_preserves_identity_success_and_evidence_ref() -> None:
    fact = _section()
    assert fact.section_name == "B300X500"
    assert fact.success is True
    assert fact.source_call == "SapModel.PropFrame.GetSectProps"
    assert fact.evidence_ref.startswith("etabs-frame-section-mechanics:sha256:")
