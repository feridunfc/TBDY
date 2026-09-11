"""Source-bound response-mode closure for the existing TS500 Eq.7.13 authority.

This subordinate analysis-basis helper resolves only mode participation that the
static geometry/role projection deliberately leaves unknown. It consumes exact
local generalized-result populations and factual constitutive/section/modifier
evidence. It never acquires ETABS facts and never changes an already-resolved
static disposition.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Mapping, Sequence

from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierReadFact,
    AreaModifierSurface,
)
from tbdy_engine.etabs.oapi.eq713_response_results import AreaStrainShellResponseRow
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
)
from tbdy_engine.etabs.oapi.frame_section_mechanics import FrameSectionMechanicsFact
from tbdy_engine.etabs.oapi.material_properties import IsotropicMaterialPropertiesFact

from .eq713_frame_mechanics import (
    FrameEq713MechanicsError,
    FrameModeParticipationClassification,
    FrameModeParticipationEvidence,
)
from .eq713_uncracked_analysis_state import (
    AreaEq713TargetDisposition,
    AreaFormulation,
    AreaGrossBasePropertyEvidence,
    AreaStiffnessMode,
    ContributorDisposition,
    FrameStiffnessMode,
    ModeDisposition,
)

EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT = "TS500_EQ713_MEMBER_RESPONSE_MECHANICS_V1"
P4B_SHELL_THICK_STRAIN_DERIVATION_CONTRACT = (
    "P4B_HOMOGENEOUS_SIMPLE_SHELL_THICK_STRAIN_PARTICIPATION_V1"
)
P4B_SHELL_THICK_SOURCE_REF = "CSI_ANALYSIS_REFERENCE_CHAPTER_X_SHELL_ELEMENT"

_AREA_SLOT = {
    AreaStiffnessMode.F11: 0,
    AreaStiffnessMode.F22: 1,
    AreaStiffnessMode.F12: 2,
    AreaStiffnessMode.M11: 3,
    AreaStiffnessMode.M22: 4,
    AreaStiffnessMode.M12: 5,
    AreaStiffnessMode.V13: 6,
    AreaStiffnessMode.V23: 7,
}
_RESPONSE_AREA_MODES = {
    AreaStiffnessMode.M11,
    AreaStiffnessMode.M22,
    AreaStiffnessMode.M12,
    AreaStiffnessMode.V13,
    AreaStiffnessMode.V23,
}
_AREA_E_MODES = {
    AreaStiffnessMode.F11,
    AreaStiffnessMode.F22,
    AreaStiffnessMode.M11,
    AreaStiffnessMode.M22,
}
_AREA_G_MODES = {
    AreaStiffnessMode.F12,
    AreaStiffnessMode.M12,
    AreaStiffnessMode.V13,
    AreaStiffnessMode.V23,
}
_FRAME_SECTION_ATTRIBUTE = {
    FrameStiffnessMode.AXIAL: "area",
    FrameStiffnessMode.SHEAR_2: "shear_area_2",
    FrameStiffnessMode.SHEAR_3: "shear_area_3",
    FrameStiffnessMode.TORSION: "torsional_constant",
    FrameStiffnessMode.FLEXURE_2: "inertia_22",
    FrameStiffnessMode.FLEXURE_3: "inertia_33",
}
_FRAME_MODIFIER_ATTRIBUTE = {
    FrameStiffnessMode.AXIAL: "area",
    FrameStiffnessMode.SHEAR_2: "shear_area_local_2",
    FrameStiffnessMode.SHEAR_3: "shear_area_local_3",
    FrameStiffnessMode.TORSION: "torsional_constant",
    FrameStiffnessMode.FLEXURE_2: "inertia_local_2",
    FrameStiffnessMode.FLEXURE_3: "inertia_local_3",
}
_FRAME_E_MODES = {
    FrameStiffnessMode.AXIAL,
    FrameStiffnessMode.FLEXURE_2,
    FrameStiffnessMode.FLEXURE_3,
}
_FRAME_G_MODES = {
    FrameStiffnessMode.SHEAR_2,
    FrameStiffnessMode.SHEAR_3,
    FrameStiffnessMode.TORSION,
}


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not result:
        raise ValueError("source_refs must not be empty")
    return result


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _values(values: Sequence[object], label: str) -> tuple[float, ...]:
    result = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label}[{index}] must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{label}[{index}] must be finite")
        result.append(number)
    return tuple(result)


def _response_truth(
    *,
    values: Sequence[object],
    effective_modifier: object,
) -> tuple[bool | None, str]:
    """Response evidence is positive-only and can never prove ``False``."""
    observed = _values(values, "response_values")
    effective = _decimal(effective_modifier, "effective_modifier")
    if not observed:
        return None, "exact response population is empty"
    if effective <= 0:
        return None, "associated stiffness is non-positive; response evidence cannot prove participation"
    if any(value != 0.0 for value in observed):
        return True, "exact local generalized-result population contains nonzero response with positive associated stiffness"
    return None, "exact local generalized-result population is identically zero; response evidence cannot prove non-participation"


def _positive_finite_product(values: Sequence[object]) -> float | None:
    product = 1.0
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            return None
        number = float(value)
        if not math.isfinite(number) or number <= 0.0:
            return None
        product *= number
        if not math.isfinite(product) or product <= 0.0:
            return None
    return product


def _beam_associated_stiffness(
    *,
    mode: FrameStiffnessMode,
    section_mechanics: FrameSectionMechanicsFact | None,
    material_properties: IsotropicMaterialPropertiesFact | None,
    property_modifiers: FrameModifierReadFact | None,
    object_modifiers: FrameModifierReadFact | None,
) -> tuple[float | None, str]:
    if (
        section_mechanics is None
        or material_properties is None
        or property_modifiers is None
        or object_modifiers is None
    ):
        return None, "complete section/material/property-modifier/object-modifier facts are required"
    if not (
        section_mechanics.success
        and material_properties.success
        and property_modifiers.success
        and object_modifiers.success
    ):
        return None, "one or more required ETABS factual reads did not succeed"
    if property_modifiers.surface is not FrameModifierSurface.FRAME_SECTION_PROPERTY:
        return None, "property modifier evidence is not a Frame section-property fact"
    if object_modifiers.surface is not FrameModifierSurface.FRAME_OBJECT:
        return None, "object modifier evidence is not a Frame-object fact"
    if property_modifiers.target_name != section_mechanics.section_name:
        return None, "Frame section mechanics and property modifier identities do not match"

    section_value = getattr(section_mechanics, _FRAME_SECTION_ATTRIBUTE[mode])
    modifier_attribute = _FRAME_MODIFIER_ATTRIBUTE[mode]
    property_modifier = getattr(property_modifiers.modifiers, modifier_attribute)
    object_modifier = getattr(object_modifiers.modifiers, modifier_attribute)
    if mode in _FRAME_E_MODES:
        modulus = material_properties.modulus_of_elasticity
    elif mode in _FRAME_G_MODES:
        modulus = material_properties.shear_modulus
    else:  # pragma: no cover - exhaustive FrameStiffnessMode guard
        return None, "unsupported Frame response mode"

    stiffness = _positive_finite_product(
        (section_value, modulus, property_modifier, object_modifier)
    )
    if stiffness is None:
        return None, "conjugate section quantity, E/G, and both modifier slots must be positive finite"
    return stiffness, "positive finite conjugate ETABS stiffness is established"


def _frame_fact_refs(
    *,
    section_mechanics: FrameSectionMechanicsFact | None,
    material_properties: IsotropicMaterialPropertiesFact | None,
    property_modifiers: FrameModifierReadFact | None,
    object_modifiers: FrameModifierReadFact | None,
) -> tuple[str, ...]:
    refs: list[str] = []
    for fact in (
        section_mechanics,
        material_properties,
        property_modifiers,
        object_modifiers,
    ):
        if fact is not None:
            refs.append(fact.evidence_ref)
    return tuple(refs)


@dataclass(frozen=True, slots=True)
class ResponseModeResolution:
    participates: bool | None
    reason: str


@dataclass(frozen=True, slots=True)
class AreaShellThickResponseGeneration:
    """One B5 shell-strain population bound to its same-generation B4B readback."""

    strain_rows: tuple[AreaStrainShellResponseRow, ...]
    property_modifiers: AreaModifierReadFact
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        rows = tuple(self.strain_rows)
        if any(not isinstance(row, AreaStrainShellResponseRow) for row in rows):
            raise TypeError("strain_rows must contain AreaStrainShellResponseRow")
        if not isinstance(self.property_modifiers, AreaModifierReadFact):
            raise TypeError("property_modifiers must be AreaModifierReadFact")
        if self.property_modifiers.surface is not AreaModifierSurface.AREA_PROPERTY:
            raise ValueError("ShellThick generation requires AREA_PROPERTY modifier readback")
        object.__setattr__(self, "strain_rows", rows)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


def _area_shell_thick_values_by_mode(
    rows: Sequence[AreaStrainShellResponseRow],
) -> dict[AreaStiffnessMode, tuple[float, ...]]:
    """Approved P4B engineering derivation for homogeneous simple ShellThick only."""
    typed = tuple(rows)
    if any(not isinstance(row, AreaStrainShellResponseRow) for row in typed):
        raise TypeError("rows must contain AreaStrainShellResponseRow")
    return {
        AreaStiffnessMode.F11: tuple((row.e11_top + row.e11_bottom) / 2.0 for row in typed),
        AreaStiffnessMode.F22: tuple((row.e22_top + row.e22_bottom) / 2.0 for row in typed),
        AreaStiffnessMode.F12: tuple((row.g12_top + row.g12_bottom) / 2.0 for row in typed),
        AreaStiffnessMode.M11: tuple(row.e11_top - row.e11_bottom for row in typed),
        AreaStiffnessMode.M22: tuple(row.e22_top - row.e22_bottom for row in typed),
        AreaStiffnessMode.M12: tuple(row.g12_top - row.g12_bottom for row in typed),
        AreaStiffnessMode.V13: tuple(row.g13_avg for row in typed),
        AreaStiffnessMode.V23: tuple(row.g23_avg for row in typed),
    }


def _area_associated_stiffness(
    *,
    mode: AreaStiffnessMode,
    gross_evidence: AreaGrossBasePropertyEvidence,
    shell_thickness: object,
    property_modifiers: AreaModifierReadFact,
) -> tuple[float | None, str]:
    if gross_evidence.formulation is not AreaFormulation.SHELL_THICK:
        return None, "response strain closure is bounded to SHELL_THICK"
    if not gross_evidence.homogeneous_simple_property:
        return None, "response strain closure is bounded to homogeneous simple shell properties"
    if not gross_evidence.gross_base_qualified or gross_evidence.material_basis is None:
        return None, "qualified gross homogeneous shell material/geometry basis is required"
    if not gross_evidence.object_modifiers_unity:
        return None, "AreaObj modifier vector must remain composition-neutral unity"
    if not property_modifiers.success:
        return None, "same-generation PropArea modifier readback did not succeed"
    if property_modifiers.surface is not AreaModifierSurface.AREA_PROPERTY:
        return None, "same-generation modifier fact is not AREA_PROPERTY"
    if property_modifiers.target_name != gross_evidence.property_name:
        return None, "same-generation PropArea modifier identity does not match shell property"

    thickness = _positive_finite_product((shell_thickness,))
    if thickness is None:
        return None, "simple shell thickness must be positive finite"
    modifier = property_modifiers.modifiers.as_tuple()[_AREA_SLOT[mode]]
    if mode in _AREA_E_MODES:
        modulus = gross_evidence.material_basis.factual_ec_mpa
    elif mode in _AREA_G_MODES:
        modulus = gross_evidence.material_basis.factual_gc_mpa
    else:  # pragma: no cover
        return None, "unsupported Area response mode"
    stiffness = _positive_finite_product((modulus, thickness, modifier))
    if stiffness is None:
        return None, "required E/G, thickness, and PropArea modifier slot must be positive finite"
    return stiffness, "positive finite homogeneous ShellThick conjugate stiffness is established"


def classify_frame_response_participation(
    *,
    base: FrameModeParticipationClassification,
    values_by_mode: Mapping[FrameStiffnessMode, Sequence[object]],
    effective_modifiers: Mapping[FrameStiffnessMode, object] | None = None,
    source_refs: Sequence[str],
    member_role: str | None = None,
    section_mechanics: FrameSectionMechanicsFact | None = None,
    material_properties: IsotropicMaterialPropertiesFact | None = None,
    property_modifiers: FrameModifierReadFact | None = None,
    object_modifiers: FrameModifierReadFact | None = None,
) -> FrameModeParticipationClassification:
    """Resolve unresolved BEAM modes only from response plus conjugate stiffness.

    ``effective_modifiers`` is retained as a compatibility input for existing
    callers, but modifier-only evidence is intentionally insufficient for this
    BEAM positive-participation proof. Full section/material/property/object
    facts are required.
    """
    if not isinstance(base, FrameModeParticipationClassification):
        raise TypeError("base must be FrameModeParticipationClassification")
    _ = effective_modifiers
    fact_refs = _frame_fact_refs(
        section_mechanics=section_mechanics,
        material_properties=material_properties,
        property_modifiers=property_modifiers,
        object_modifiers=object_modifiers,
    )
    refs = _refs(
        (
            *base.source_refs,
            *source_refs,
            *fact_refs,
            EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT,
        )
    )
    rows = []
    for row in base.mode_evidence:
        if row.participates is not None:
            rows.append(row)
            continue
        if member_role != "BEAM":
            rows.append(
                FrameModeParticipationEvidence(
                    row.mode,
                    None,
                    "response-based constitutive closure is bounded to unresolved BEAM modes",
                    refs,
                )
            )
            continue
        if row.mode not in values_by_mode:
            rows.append(
                FrameModeParticipationEvidence(
                    row.mode,
                    None,
                    "member-level response evidence is absent for unresolved Frame mode",
                    refs,
                )
            )
            continue
        stiffness, stiffness_reason = _beam_associated_stiffness(
            mode=row.mode,
            section_mechanics=section_mechanics,
            material_properties=material_properties,
            property_modifiers=property_modifiers,
            object_modifiers=object_modifiers,
        )
        if stiffness is None:
            rows.append(FrameModeParticipationEvidence(row.mode, None, stiffness_reason, refs))
            continue
        participates, reason = _response_truth(
            values=values_by_mode[row.mode],
            effective_modifier=stiffness,
        )
        rows.append(FrameModeParticipationEvidence(row.mode, participates, reason, refs))
    try:
        return FrameModeParticipationClassification(base.component_uid, tuple(rows), refs)
    except FrameEq713MechanicsError:
        raise


def resolve_area_response_modes(
    *,
    base: AreaEq713TargetDisposition,
    values_by_mode: Mapping[AreaStiffnessMode, Sequence[object]] | None = None,
    effective_modifiers: Mapping[AreaStiffnessMode, object] | None = None,
    source_refs: Sequence[str],
    gross_evidence: AreaGrossBasePropertyEvidence | None = None,
    shell_thickness: object | None = None,
    response_generations: Sequence[AreaShellThickResponseGeneration] = (),
) -> AreaEq713TargetDisposition:
    """Resolve blocked ShellThick modes by positive-only response evidence.

    P4B production uses ``response_generations``. Each generation binds raw
    AreaStrainShell rows to its own B4B PropArea ``after`` readback; the approved
    top/bottom membrane/bending and transverse-shear derivation is performed
    here, never in the CSI ABI/provider layer. The older values/modifier inputs
    remain a compatibility seam for existing tests/callers.
    """
    if not isinstance(base, AreaEq713TargetDisposition):
        raise TypeError("base must be AreaEq713TargetDisposition")
    if base.target_property_modifiers is None:
        return base
    refs = _refs(
        (
            *base.source_refs,
            *source_refs,
            EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT,
            P4B_SHELL_THICK_STRAIN_DERIVATION_CONTRACT,
            P4B_SHELL_THICK_SOURCE_REF,
        )
    )
    target = list(base.target_property_modifiers)
    rows = []
    generations = tuple(response_generations)

    if generations:
        if not isinstance(gross_evidence, AreaGrossBasePropertyEvidence):
            raise TypeError("gross_evidence is required for ShellThick strain response closure")
        if gross_evidence.area_name != base.area_name:
            raise ValueError("Area response gross-evidence identity mismatch")
        if gross_evidence.formulation is not AreaFormulation.SHELL_THICK:
            raise ValueError("Area strain response closure is bounded to SHELL_THICK")
        if not gross_evidence.homogeneous_simple_property:
            raise ValueError("Area strain response closure is bounded to homogeneous simple properties")

    for row in base.mode_dispositions:
        if (
            row.disposition is not ContributorDisposition.BLOCKED_UNSUPPORTED
            or row.mode not in _RESPONSE_AREA_MODES
        ):
            rows.append(row)
            continue

        participates: bool | None = None
        reason = "qualified ShellThick response evidence is absent"
        if generations:
            observed_any = False
            for generation in generations:
                stiffness, stiffness_reason = _area_associated_stiffness(
                    mode=row.mode,
                    gross_evidence=gross_evidence,
                    shell_thickness=shell_thickness,
                    property_modifiers=generation.property_modifiers,
                )
                if stiffness is None:
                    reason = stiffness_reason
                    continue
                values = _area_shell_thick_values_by_mode(generation.strain_rows)[row.mode]
                if values:
                    observed_any = True
                generation_participates, generation_reason = _response_truth(
                    values=values,
                    effective_modifier=stiffness,
                )
                reason = generation_reason
                if generation_participates is True:
                    participates = True
                    break
            if participates is not True and not observed_any:
                reason = "qualified AreaStrainShell population is empty or stiffness is invalid"
        else:
            legacy_values = values_by_mode or {}
            legacy_modifiers = effective_modifiers or {}
            if row.mode in legacy_values and row.mode in legacy_modifiers:
                participates, reason = _response_truth(
                    values=legacy_values[row.mode],
                    effective_modifier=legacy_modifiers[row.mode],
                )

        if participates is True:
            target[_AREA_SLOT[row.mode]] = Decimal("1")
            disposition = ContributorDisposition.TARGETED_UNCRACKED
        else:
            disposition = ContributorDisposition.BLOCKED_UNSUPPORTED
        rows.append(ModeDisposition(row.mode, disposition, reason, refs))

    blocked = tuple(
        dict.fromkeys(
            row.reason
            for row in rows
            if row.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED
        )
    )
    return AreaEq713TargetDisposition(
        area_name=base.area_name,
        mode_dispositions=tuple(rows),
        target_property_modifiers=tuple(target),
        blocked_reasons=blocked,
        source_refs=refs,
        audit_limitations=base.audit_limitations,
    )


__all__ = [
    "AreaShellThickResponseGeneration",
    "EQ713_MEMBER_RESPONSE_MECHANICS_CONTRACT",
    "P4B_SHELL_THICK_SOURCE_REF",
    "P4B_SHELL_THICK_STRAIN_DERIVATION_CONTRACT",
    "ResponseModeResolution",
    "_area_shell_thick_values_by_mode",
    "classify_frame_response_participation",
    "resolve_area_response_modes",
]
