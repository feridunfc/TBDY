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
from tbdy_engine.etabs.oapi.database_tables import TableFieldMetadataFetchResult

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
    AreaStiffnessMode.F11,
    AreaStiffnessMode.F22,
    AreaStiffnessMode.F12,
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

    generations = tuple(response_generations)

    if (
        base.target_property_modifiers is None
        and not generations
    ):
        return base

    if generations:
        if not isinstance(
            gross_evidence,
            AreaGrossBasePropertyEvidence,
        ):
            raise TypeError(
                "gross_evidence is required for "
                "ShellThick strain response closure"
            )

        if gross_evidence.area_name != base.area_name:
            raise ValueError(
                "Area response gross-evidence identity mismatch"
            )

        if (
            gross_evidence.formulation
            is not AreaFormulation.SHELL_THICK
            or not gross_evidence.homogeneous_simple_property
            or not gross_evidence.gross_base_qualified
            or not gross_evidence.object_modifiers_unity
        ):
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

    if base.target_property_modifiers is None:
        # A static role/diaphragm prerequisite may have caused the
        # initial all-mode fail-closed disposition. Positive
        # same-generation response is allowed to supersede that
        # participation uncertainty, but the target still begins
        # from the exact preserved factual PropArea vector.
        target = list(
            gross_evidence.property_modifiers
        )
    else:
        target = list(
            base.target_property_modifiers
        )

    rows = []

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


# Gate 1 arithmetic only. This helper never issues an output-state binding or
# StoryStabilityIndexEvidence. CSI FAQ authorizes amplitude * modal quantity;
# base-reaction documentation demonstrates sum-before-modal-combination.
CSI_NATIVE_MODAL_AMPLITUDE_SOURCE = (
    "https://wikicsiamerica.atlassian.net/wiki/spaces/kb/pages/2006323/"
    "Response-spectrum%2Banalysis%2BFAQ"
)
CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT = (
    "CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_MULTIPLICATION_V1"
)
CSI_NATIVE_MODAL_NORMALIZATION_SOURCE = (
    "https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf"
    "#printed-pages-376-394"
)


@dataclass(frozen=True, slots=True)
class NativeModalNormalizationBinding:
    source_model_ref: str
    session_ref: str
    acquisition_ref: str
    modal_case: str
    spectrum_case: str
    source_direction: str
    database_force_unit: str
    database_length_unit: str
    normalization_ref: str

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            _text(getattr(self, name), name)
        if self.source_direction not in {"U1", "U2", "U3"}:
            raise ValueError("source_direction must be exact U1/U2/U3, not inferred global X/Y")
        if self.database_force_unit not in {"N", "kN", "tonf"} or self.database_length_unit not in {"m", "mm"}:
            raise ValueError("unsupported independently qualified database units")


@dataclass(frozen=True, slots=True)
class NativeModalAmplitude:
    mode: int
    period_s: float
    multiplier: float
    binding: NativeModalNormalizationBinding
    source_field: str
    raw_response_ref: str
    native_field_unit: str | None = None
    native_metadata_ref: str | None = None
    normalization_contract: str | None = None

    def __post_init__(self):
        if type(self.mode) is not int or self.mode <= 0:
            raise ValueError("mode must be a positive exact index")
        values = _values((self.period_s, self.multiplier), "modal amplitude")
        if values[0] <= 0:
            raise ValueError("modal period must be positive")
        expected = self.binding.source_direction + "Amp"
        if self.source_field != expected:
            raise ValueError("amplitude field must be exact U1Amp/U2Amp/U3Amp; Acc is not a multiplier")
        _text(self.raw_response_ref, "amplitude raw_response_ref")
        provenance = (self.native_field_unit, self.native_metadata_ref, self.normalization_contract)
        if any(x is not None for x in provenance):
            if self.native_field_unit != self.binding.database_length_unit:
                raise ValueError("native amplitude field unit must remain the database length unit")
            _text(self.native_metadata_ref, "native amplitude metadata ref")
            if self.normalization_contract != CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT:
                raise ValueError("unsupported native modal normalization contract")


def bind_database_normalized_native_modal_amplitude(
    *, mode: int, period_s: float, native_value: float,
    binding: NativeModalNormalizationBinding,
    metadata: TableFieldMetadataFetchResult,
    raw_response_ref: str,
    observed_present_force_unit: str, observed_present_length_unit: str,
) -> NativeModalAmplitude:
    """Bind CSI's native numerical multiplier in the identical-unit scope.

    CSI Analysis Reference (Rev.15), pp.376/394, defines unit-modal-mass
    normalization and multiplication of modal responses by the reported Amp.
    CSI's FAQ specifies database-unit normalization. The table's reported
    length unit is retained; Amp is not relabelled dimensionless. No spectrum
    scale, participation factor or eigenvalue is applied a second time.

    The acquisition adapter must independently verify source/session/units
    and the native modal response population. This pure binding cannot issue
    B5 lineage, CQC combination or a joint TS500 design statistic. Different
    present/database units are deliberately unsupported rather than guessed.
    """
    if not isinstance(binding, NativeModalNormalizationBinding):
        raise TypeError("typed native modal binding required")
    if not isinstance(metadata, TableFieldMetadataFetchResult):
        raise TypeError("typed native field metadata required")
    if binding.normalization_ref != CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT:
        raise ValueError("exact source-supported database normalization contract required")
    if (observed_present_force_unit, observed_present_length_unit) != (
        binding.database_force_unit, binding.database_length_unit
    ):
        raise ValueError("present/database unit mismatch: normalization conversion is not authorized")
    if metadata.table_name != "Response Spectrum Modal Info" or metadata.return_code != 0:
        raise ValueError("successful exact native amplitude table metadata required")
    if len(set(metadata.field_keys)) != len(metadata.field_keys):
        raise ValueError("duplicate native amplitude metadata field")
    field = binding.source_direction + "Amp"
    definition = metadata.field_metadata(field)
    if definition["UnitsString"] != binding.database_length_unit or not definition["Description"]:
        raise ValueError("native amplitude field unit/definition mismatch")
    if metadata.field_metadata("Period")["UnitsString"] != "sec":
        raise ValueError("native modal period unit must be sec")
    return NativeModalAmplitude(mode, period_s, native_value, binding, field,
        raw_response_ref, definition["UnitsString"], metadata.raw_response_ref,
        CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT)


@dataclass(frozen=True, slots=True)
class NativeModalColumnAxial:
    column_unique_name: str
    mode: int
    signed_p: float
    physical_length: float
    binding: NativeModalNormalizationBinding
    force_unit: str
    length_unit: str
    step_type: str
    physical_location: str
    raw_response_ref: str
    length_source_ref: str

    def __post_init__(self):
        _text(self.column_unique_name, "column_unique_name")
        _text(self.raw_response_ref, "force raw_response_ref")
        _text(self.length_source_ref, "physical length source")
        if type(self.mode) is not int or self.mode <= 0 or self.step_type != "Mode":
            raise ValueError("only signed eigen/modal Mode rows qualify; spectral Max/Min are not modes")
        vals = _values((self.signed_p, self.physical_length), "modal column")
        if vals[1] <= 0:
            raise ValueError("physical member length must be positive")
        if self.physical_location != "PHYSICAL_BOTTOM":
            raise ValueError("axial row must be bound to the physical bottom, not station inferred without topology")
        if self.force_unit != self.binding.database_force_unit or self.length_unit != self.binding.database_length_unit:
            raise ValueError("modal response and physical lengths must use the independently observed database units")


@dataclass(frozen=True, slots=True)
class NativeModalAggregateComputation:
    mode: int
    period_s: float
    r_force_per_length: float
    column_contributions: tuple[tuple[str, float], ...]
    binding: NativeModalNormalizationBinding
    source_refs: tuple[str, ...]
    # Caller-supplied source refs cannot self-issue controlled-execution lineage.
    qualified_for_stability: bool = False

    def __post_init__(self):
        if self.qualified_for_stability is not False:
            raise ValueError("Gate 1 arithmetic cannot qualify a stability result state")


def aggregate_native_modal_column_axial(
    *, amplitude: NativeModalAmplitude,
    columns: Sequence[NativeModalColumnAxial],
    expected_complete_story_columns: Sequence[str],
) -> NativeModalAggregateComputation:
    """R_n = amplitude_n * sum(-P_eigen,j,n / l_j), before any modal norm.

    The caller must bind the complete factual Column denominator, physical
    station and source-qualified lengths. Signs, tension and cancellation are
    retained. This is a pure computation, not a live source qualification.
    A source-bound adapter and the exact current B5 issuer remain required.
    """
    if not isinstance(amplitude, NativeModalAmplitude):
        raise TypeError("amplitude must be NativeModalAmplitude")
    expected = tuple(_text(x, "expected Column") for x in expected_complete_story_columns)
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("complete story Column denominator must be nonempty and unique")
    rows = tuple(columns)
    if any(not isinstance(x, NativeModalColumnAxial) for x in rows):
        raise TypeError("columns must contain NativeModalColumnAxial")
    names = tuple(x.column_unique_name for x in rows)
    if len(set(names)) != len(names) or set(names) != set(expected):
        raise ValueError("missing/extra/duplicate Column in complete-story modal denominator")
    contributions = []
    refs = [CSI_NATIVE_MODAL_AMPLITUDE_SOURCE, amplitude.raw_response_ref]
    for row in sorted(rows, key=lambda r: r.column_unique_name):
        if row.binding != amplitude.binding or row.mode != amplitude.mode:
            raise ValueError("source/session/acquisition/modal normalization/case/direction/mode mismatch")
        contribution = -row.signed_p * amplitude.multiplier / row.physical_length
        if not math.isfinite(contribution):
            raise ValueError("nonfinite modal contribution")
        contributions.append((row.column_unique_name, contribution))
        refs.extend((row.raw_response_ref, row.length_source_ref))
    total = math.fsum(x[1] for x in contributions)
    if not math.isfinite(total):
        raise ValueError("nonfinite complete-story modal aggregate")
    return NativeModalAggregateComputation(amplitude.mode, amplitude.period_s, total,
        tuple(contributions), amplitude.binding, tuple(dict.fromkeys(refs)))


def srss_native_modal_aggregates(
    modes: Sequence[NativeModalAggregateComputation], *, source_modal_method: str,
) -> float:
    """SRSS of physical aggregates; never substitute SRSS for observed CQC.

    Mode completeness, actual native method/rigid-response settings and B5
    lineage must be independently qualified by the eventual adapter. A numeric
    return from this helper is not a regulatory stability statistic.
    """
    rows = tuple(modes)
    if source_modal_method != "SRSS":
        raise ValueError("native method is not SRSS; no CQC/damping/rigid-response inference permitted")
    if not rows or any(not isinstance(x, NativeModalAggregateComputation) for x in rows):
        raise ValueError("nonempty modal aggregate population required")
    if len({x.mode for x in rows}) != len(rows) or any(x.binding != rows[0].binding for x in rows):
        raise ValueError("duplicate mode or modal basis drift")
    return math.hypot(*(x.r_force_per_length for x in rows))


@dataclass(frozen=True, slots=True)
class NativeModalScalarResponse:
    mode: int
    value: float
    binding: NativeModalNormalizationBinding
    quantity: str
    source_unit: str
    physical_grain_ref: str
    raw_response_refs: tuple[str, ...]
    step_type: str = "Mode"

    def __post_init__(self):
        if type(self.mode) is not int or self.mode <= 0 or self.step_type != "Mode":
            raise ValueError("scalar must be an exact signed modal response, not a spectrum extremum")
        _values((self.value,), "modal scalar")
        expected_unit = {"PHYSICAL_TOP_MINUS_BOTTOM_TRANSLATION": self.binding.database_length_unit,
                         "STORY_BOTTOM_SHEAR": self.binding.database_force_unit}.get(self.quantity)
        if expected_unit is None or self.source_unit != expected_unit:
            raise ValueError("exact physical response quantity and database-normalized unit required")
        _text(self.physical_grain_ref, "physical_grain_ref")
        _refs(self.raw_response_refs)
        if self.quantity == "PHYSICAL_TOP_MINUS_BOTTOM_TRANSLATION" and len(set(self.raw_response_refs)) != 2:
            raise ValueError("physical top-minus-bottom requires two independent endpoint source rows")


def native_modal_scalar_contribution(
    *, amplitude: NativeModalAmplitude, response: NativeModalScalarResponse,
) -> float:
    """Scale an already bound signed physical linear response by native Amp.

    Translation must be top-bottom before scaling/combination; shear must be
    the exact signed storey bottom cut. Neither scalar is promoted to a joint
    TS500 statistic, global direction or concurrent time state by this helper.
    """
    if not isinstance(amplitude, NativeModalAmplitude) or not isinstance(response, NativeModalScalarResponse):
        raise TypeError("typed native amplitude and modal scalar required")
    if response.binding != amplitude.binding or response.mode != amplitude.mode:
        raise ValueError("source/session/normalization/case/direction/mode mismatch")
    product = amplitude.multiplier * response.value
    if not math.isfinite(product):
        raise ValueError("nonfinite native modal scalar contribution")
    return product
