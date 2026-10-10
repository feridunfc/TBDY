"""Qualified native-property fixtures for offline PUBLIC-A5 acquisitions."""
from dataclasses import replace

from tbdy_engine.etabs.oapi.contracts import SourceUnitProvenance
from tbdy_engine.etabs.oapi.frame_section_mechanics import (
    FrameSectionMechanicsFact, FRAME_SECTION_MECHANICS_SOURCE_CALL,
    FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF,
    FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_VERSION,
)
from tbdy_engine.etabs.oapi.material_properties import (
    IsotropicMaterialPropertiesFact, ISOTROPIC_SOURCE_AUTHORITY_REF,
    ISOTROPIC_SOURCE_AUTHORITY_VERSION,
)


def qualify(fact, capture="property-capture:pre"):
    section = isinstance(fact, FrameSectionMechanicsFact)
    call = FRAME_SECTION_MECHANICS_SOURCE_CALL if section else "SapModel.PropMaterial.GetMPIsotropic"
    name = fact.section_name if section else fact.material_name
    fact = replace(fact, source_model_ref="model:protected", session_ref="session:offline",
                   capture_ref=capture, unit_observation="verified-native-unit-state")
    bindings = tuple(SourceUnitProvenance(
        source_call=call, subject_key=name, output_key=key,
        dimension="L4" if section else "F/L2",
        source_unit="m4" if section else "N/m2",
        authority_ref=FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF if section else ISOTROPIC_SOURCE_AUTHORITY_REF,
        authority_version=FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_VERSION if section else ISOTROPIC_SOURCE_AUTHORITY_VERSION,
        authority_kind="REVIEWED_PROPERTY_SOURCE_SEMANTICS",
        source_model_ref=fact.source_model_ref, session_ref=fact.session_ref,
        capture_ref=capture, raw_response_ref=fact.raw_response_ref, return_code=0,
        unit_state_before="verified-native-unit-state", unit_state_after="verified-native-unit-state",
        qualification="QUALIFIED", reason="OFFLINE_NATIVE_SOURCE_FIXTURE",
    ) for key in (("I22", "I33") if section else ("E", "G")))
    return replace(fact, unit_provenance=bindings)


def section_fact(name="C50x80", capture="property-capture:pre"):
    raw = (.4, .3, .3, .006, .0083, .0213, 1., 2., 3., 4., 5., 6., 0)
    return qualify(FrameSectionMechanicsFact(
        name, *raw[:6], return_code=0, raw_response=raw,
    ), capture)


def material_fact(name="C35", capture="property-capture:pre"):
    raw = (33000., .2, 1.e-5, 13200., 0)
    return qualify(IsotropicMaterialPropertiesFact(
        name, *raw[:4], temperature=0., return_code=0, raw_response=raw,
    ), capture)


def fresh_capture(fact, capture):
    return replace(fact, capture_ref=capture, unit_provenance=tuple(
        replace(binding, capture_ref=capture) for binding in fact.unit_provenance
    ))
