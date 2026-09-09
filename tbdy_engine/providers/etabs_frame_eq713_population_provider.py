"""Bounded factual Frame population for COLUMN-R1 PUBLIC-A5.

This provider composes existing factual owners only.  It does not decide
TS500 Eq.7.13 participation.  In particular ``FrameObj.GetReleases`` is used
only to prove the supported end-condition slice; absence of releases is never
promoted here to participation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
    get_frame_modifiers_from_session,
)
from tbdy_engine.etabs.oapi.frame_releases import (
    FrameReleaseFact,
    get_frame_releases_from_session,
)
from tbdy_engine.etabs.oapi.material_properties import (
    IsotropicMaterialPropertiesFact,
    get_isotropic_material_properties_from_session,
)
from tbdy_engine.etabs.oapi.object_model import read_frame_names_from_session
from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    FrameFlexuralBaseFact,
    _stress_to_mpa,
    capture_frame_flexural_base_fact,
)

NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT = "NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT"
FRAME_END_CONDITION_UNSUPPORTED = "FRAME_END_CONDITION_UNSUPPORTED"


class EtabsFrameEq713PopulationError(RuntimeError):
    """Raised when the supported exact Frame factual population cannot be bound."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsFrameEq713PopulationError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not refs:
        raise EtabsFrameEq713PopulationError("source_refs must not be empty")
    return refs


def _no_release_or_partial_fixity(fact: FrameReleaseFact) -> bool:
    return (
        fact.success
        and not any(fact.i_end_released)
        and not any(fact.j_end_released)
        and all(value == 0.0 for value in fact.i_end_partial_fixity)
        and all(value == 0.0 for value in fact.j_end_partial_fixity)
    )


def _role_map(topology: StrictColumnTopologyBundle) -> dict[str, str]:
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")
    roles: dict[str, str] = {}

    def bind(name: str, role: str) -> None:
        previous = roles.get(name)
        if previous is not None and previous != role:
            raise EtabsFrameEq713PopulationError(
                f"Frame {name!r} has contradictory strict-topology member roles: {previous}/{role}"
            )
        roles[name] = role

    for column in topology.columns:
        bind(column.unique_name, "COLUMN")
        for beam in (*column.beams_at_bottom, *column.beams_at_top):
            if not beam.is_supported_rc_beam:
                raise EtabsFrameEq713PopulationError(
                    f"Frame {beam.beam_unique_name!r} is outside supported rectangular RC Frame population"
                )
            bind(beam.beam_unique_name, "BEAM")
    return roles


@dataclass(frozen=True, slots=True)
class FrameEq713FactualFact:
    frame_name: str
    member_role: str
    base_fact: FrameFlexuralBaseFact
    property_modifiers: FrameModifierReadFact
    object_modifiers: FrameModifierReadFact
    releases: FrameReleaseFact
    isotropic_material: IsotropicMaterialPropertiesFact
    factual_ec_mpa: Decimal
    factual_gc_mpa: Decimal
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        name = _text(self.frame_name, "frame_name")
        object.__setattr__(self, "frame_name", name)
        if self.member_role not in {"COLUMN", "BEAM"}:
            raise EtabsFrameEq713PopulationError("member_role must be COLUMN or BEAM")
        if not isinstance(self.base_fact, FrameFlexuralBaseFact):
            raise TypeError("base_fact must be FrameFlexuralBaseFact")
        if self.base_fact.component_unique_name != name:
            raise EtabsFrameEq713PopulationError("Frame base fact identity mismatch")
        if not isinstance(self.property_modifiers, FrameModifierReadFact):
            raise TypeError("property_modifiers must be FrameModifierReadFact")
        if (
            self.property_modifiers.surface is not FrameModifierSurface.FRAME_SECTION_PROPERTY
            or self.property_modifiers.target_name != self.base_fact.assigned_section_name
            or not self.property_modifiers.success
        ):
            raise EtabsFrameEq713PopulationError("Frame property modifier fact is not exact/successful")
        if not isinstance(self.object_modifiers, FrameModifierReadFact):
            raise TypeError("object_modifiers must be FrameModifierReadFact")
        if (
            self.object_modifiers.surface is not FrameModifierSurface.FRAME_OBJECT
            or self.object_modifiers.target_name != name
            or not self.object_modifiers.success
        ):
            raise EtabsFrameEq713PopulationError("Frame object modifier fact is not exact/successful")
        if not isinstance(self.releases, FrameReleaseFact):
            raise TypeError("releases must be FrameReleaseFact")
        if self.releases.frame_name != name or not self.releases.success:
            raise EtabsFrameEq713PopulationError("Frame release fact is not exact/successful")
        if not isinstance(self.isotropic_material, IsotropicMaterialPropertiesFact):
            raise TypeError("isotropic_material must be IsotropicMaterialPropertiesFact")
        if (
            self.isotropic_material.material_name != self.base_fact.material_name
            or not self.isotropic_material.success
        ):
            raise EtabsFrameEq713PopulationError("Frame isotropic material fact is not exact/successful")
        if self.factual_ec_mpa <= 0 or self.factual_gc_mpa <= 0:
            raise EtabsFrameEq713PopulationError("GetMPIsotropic E/G must be positive in MPa")
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def end_condition_status(self) -> str:
        return (
            NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT
            if _no_release_or_partial_fixity(self.releases)
            else FRAME_END_CONDITION_UNSUPPORTED
        )

    @property
    def supported_end_condition(self) -> bool:
        return self.end_condition_status == NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT


@dataclass(frozen=True, slots=True)
class FrameEq713FactualPopulation:
    expected_frame_names: tuple[str, ...]
    rows: tuple[FrameEq713FactualFact, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = tuple(sorted(_text(name, "expected_frame_name") for name in self.expected_frame_names))
        if len(expected) != len(set(expected)):
            raise EtabsFrameEq713PopulationError("duplicate expected Frame identity")
        rows = tuple(sorted(self.rows, key=lambda item: item.frame_name))
        names = tuple(row.frame_name for row in rows)
        if names != expected:
            raise EtabsFrameEq713PopulationError(
                "captured Frame population does not exactly match FrameObj.GetNameList"
            )
        object.__setattr__(self, "expected_frame_names", expected)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


def capture_frame_eq713_factual_population(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    topology: StrictColumnTopologyBundle,
) -> FrameEq713FactualPopulation:
    """Capture every exact supported RC Frame with independent end/material facts."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if owned_scratch.source_model_identity != context.source_model_identity:
        raise EtabsFrameEq713PopulationError("owned scratch/context source identity mismatch")

    names, _raw_names = read_frame_names_from_session(context.verified_session)
    expected = tuple(sorted(names))
    roles = _role_map(topology)
    if tuple(sorted(roles)) != expected:
        missing = tuple(sorted(set(expected) - set(roles)))
        extra = tuple(sorted(set(roles) - set(expected)))
        raise EtabsFrameEq713PopulationError(
            "strict topology does not account for exact FrameObj population; "
            f"missing={missing!r}; extra={extra!r}"
        )

    material_cache: dict[str, IsotropicMaterialPropertiesFact] = {}
    property_modifier_cache: dict[str, FrameModifierReadFact] = {}
    rows: list[FrameEq713FactualFact] = []
    population_refs: list[str] = [
        f"CSI:FrameObj.GetNameList:COUNT:{len(expected)}",
        context.session_provenance_ref,
        owned_scratch.ownership_proof_ref,
    ]

    for name in expected:
        base = capture_frame_flexural_base_fact(
            context,
            owned_scratch,
            component_unique_name=name,
        )
        section = base.assigned_section_name
        prop = property_modifier_cache.get(section)
        if prop is None:
            prop = get_frame_modifiers_from_session(
                context.verified_session,
                surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_name=section,
            )
            property_modifier_cache[section] = prop
        obj = get_frame_modifiers_from_session(
            context.verified_session,
            surface=FrameModifierSurface.FRAME_OBJECT,
            target_name=name,
        )
        releases = get_frame_releases_from_session(
            context.verified_session,
            frame_name=name,
        )
        material = material_cache.get(base.material_name)
        if material is None:
            material = get_isotropic_material_properties_from_session(
                context.verified_session,
                material_name=base.material_name,
            )
            material_cache[base.material_name] = material
        if not material.success:
            raise EtabsFrameEq713PopulationError(
                f"PropMaterial.GetMPIsotropic failed for {base.material_name!r}"
            )
        ec_mpa = _stress_to_mpa(
            material.modulus_of_elasticity,
            base.present_force_unit,
            base.present_length_unit,
            "PropMaterial.GetMPIsotropic.E",
        )
        gc_mpa = _stress_to_mpa(
            material.shear_modulus,
            base.present_force_unit,
            base.present_length_unit,
            "PropMaterial.GetMPIsotropic.G",
        )
        refs = (
            *base.source_refs,
            base.evidence_ref,
            prop.evidence_ref,
            obj.evidence_ref,
            releases.evidence_ref,
            material.evidence_ref,
        )
        row = FrameEq713FactualFact(
            frame_name=name,
            member_role=roles[name],
            base_fact=base,
            property_modifiers=prop,
            object_modifiers=obj,
            releases=releases,
            isotropic_material=material,
            factual_ec_mpa=ec_mpa,
            factual_gc_mpa=gc_mpa,
            source_refs=tuple(refs),
        )
        rows.append(row)
        population_refs.extend(row.source_refs)

    return FrameEq713FactualPopulation(
        expected_frame_names=expected,
        rows=tuple(rows),
        source_refs=tuple(dict.fromkeys(population_refs)),
    )


__all__ = [
    "EtabsFrameEq713PopulationError",
    "FRAME_END_CONDITION_UNSUPPORTED",
    "FrameEq713FactualFact",
    "FrameEq713FactualPopulation",
    "NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT",
    "capture_frame_eq713_factual_population",
]
