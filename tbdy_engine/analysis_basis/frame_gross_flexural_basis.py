"""Positive TS500 Eq.7.13 basis evidence for one supported frame flexural axis.

This is intentionally an item-level authority.  It does not classify whether a
frame participates in the global stability system.  The only supported section
slice is a prismatic rectangular RC frame section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from typing import Sequence

from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierSurface
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.integration.etabs_analysis_state_mutation import AnalysisStateMutationResult, FrameModifierMutationFact
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.providers.etabs_frame_flexural_base_provider import FrameFlexuralBaseFact, capture_frame_flexural_base_fact
from tbdy_engine.regulatory.ts500_concrete_elastic_modulus import Ts500ConcreteEcComparison, compare_etabs_ec_to_ts500_table_3_2

FRAME_GROSS_INERTIA_CONTRACT = "RECTANGULAR_FRAME_GROSS_INERTIA_V1"
FRAME_GROSS_FLEXURAL_BASIS_CONTRACT = "TS500_EQ7_13_FRAME_GROSS_FLEXURAL_BASIS_V1"
FRAME_GROSS_FLEXURAL_BASIS_REF_PREFIX = "frame-gross-flexural-basis:sha256:"


class FrameFlexuralAxis(StrEnum):
    LOCAL_2_M2 = "LOCAL_2_M2"
    LOCAL_3_M3 = "LOCAL_3_M3"


class FrameGrossFlexuralBasisError(RuntimeError):
    """Fail-closed positive-basis construction error."""


@dataclass(frozen=True, slots=True)
class RectangularGrossInertiaEvidence:
    section_name: str
    t2_mm: Decimal
    t3_mm: Decimal
    i22_mm4: Decimal
    i33_mm4: Decimal
    source_ref: str
    contract: str = FRAME_GROSS_INERTIA_CONTRACT

    def for_axis(self, axis: FrameFlexuralAxis) -> Decimal:
        if axis is FrameFlexuralAxis.LOCAL_2_M2:
            return self.i22_mm4
        if axis is FrameFlexuralAxis.LOCAL_3_M3:
            return self.i33_mm4
        raise TypeError("unsupported frame flexural axis")


def derive_rectangular_gross_inertia(base_fact: FrameFlexuralBaseFact) -> RectangularGrossInertiaEvidence:
    """Derive geometric gross inertia only; no transformed/cracked inertia."""
    if not isinstance(base_fact, FrameFlexuralBaseFact):
        raise TypeError("base_fact must be FrameFlexuralBaseFact")
    b = base_fact.t2_mm
    h = base_fact.t3_mm
    twelve = Decimal("12")
    # ETABS GetRectangle defines T3 as section depth and T2 as section width.
    # I22 integrates distance in local-3; I33 integrates distance in local-2.
    i22 = b * h**3 / twelve
    i33 = h * b**3 / twelve
    rectangle_ref = base_fact.source_refs[1]
    return RectangularGrossInertiaEvidence(
        section_name=base_fact.assigned_section_name,
        t2_mm=b,
        t3_mm=h,
        i22_mm4=i22,
        i33_mm4=i33,
        source_ref=rectangle_ref,
    )


def _mutation(
    state: AnalysisStateMutationResult,
    *,
    surface: FrameModifierSurface,
    target_name: str,
) -> FrameModifierMutationFact:
    matches = tuple(
        item for item in state.mutation_manifest.mutations
        if item.surface is surface and item.target_name == target_name
    )
    if len(matches) != 1:
        raise FrameGrossFlexuralBasisError(
            f"required {surface.value} modifier census missing/ambiguous for {target_name!r}"
        )
    fact = matches[0]
    if not fact.setter.success or not fact.after.success:
        raise FrameGrossFlexuralBasisError(f"{surface.value} modifier establishment is not successful")
    return fact


def _axis_modifier(fact: FrameModifierMutationFact, axis: FrameFlexuralAxis) -> float:
    vector = fact.after.modifiers
    if axis is FrameFlexuralAxis.LOCAL_2_M2:
        return vector.inertia_local_2
    if axis is FrameFlexuralAxis.LOCAL_3_M3:
        return vector.inertia_local_3
    raise TypeError("axis must be FrameFlexuralAxis")


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(sorted({str(value).strip() for value in values if isinstance(value, str) and value.strip()}))
    if not result:
        raise FrameGrossFlexuralBasisError("positive evidence requires source/provenance refs")
    return result


@dataclass(frozen=True, slots=True)
class FrameGrossFlexuralBasisEvidence:
    component_unique_name: str
    axis: FrameFlexuralAxis
    assigned_section_name: str
    assigned_material_name: str
    gross_inertia: RectangularGrossInertiaEvidence
    gross_i_axis_mm4: Decimal
    factual_etabs_ec_mpa: Decimal
    ts500_ec_comparison: Ts500ConcreteEcComparison
    property_modifier_ref: str
    object_modifier_ref: str
    property_axis_modifier: float
    object_axis_modifier: float
    parent_analysis_state_ref: str
    parent_analysis_result_ref: str
    ownership_proof_ref: str
    source_model_ref: str
    source_refs: tuple[str, ...]
    evidence_ref: str = field(init=False)
    contract: str = FRAME_GROSS_FLEXURAL_BASIS_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.axis, FrameFlexuralAxis):
            raise TypeError("axis must be FrameFlexuralAxis")
        if not self.ts500_ec_comparison.positive:
            raise FrameGrossFlexuralBasisError("positive frame basis requires exact TS500 Ec MATCH")
        if self.property_axis_modifier != 1.0 or self.object_axis_modifier != 1.0:
            raise FrameGrossFlexuralBasisError("positive frame basis requires unit property and object flexural modifiers")
        if self.gross_i_axis_mm4 <= 0 or self.factual_etabs_ec_mpa <= 0:
            raise FrameGrossFlexuralBasisError("positive frame basis requires positive gross I and Ec")
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        payload = {
            "contract": self.contract,
            "component_unique_name": self.component_unique_name,
            "axis": self.axis.value,
            "assigned_section_name": self.assigned_section_name,
            "assigned_material_name": self.assigned_material_name,
            "gross_i_axis_mm4": str(self.gross_i_axis_mm4),
            "factual_etabs_ec_mpa": str(self.factual_etabs_ec_mpa),
            "required_ts500_ec_mpa": str(self.ts500_ec_comparison.required_ts500_ec_mpa),
            "property_modifier_ref": self.property_modifier_ref,
            "object_modifier_ref": self.object_modifier_ref,
            "parent_analysis_state_ref": self.parent_analysis_state_ref,
            "parent_analysis_result_ref": self.parent_analysis_result_ref,
            "ownership_proof_ref": self.ownership_proof_ref,
            "source_model_ref": self.source_model_ref,
            "source_refs": list(self.source_refs),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        object.__setattr__(self, "evidence_ref", FRAME_GROSS_FLEXURAL_BASIS_REF_PREFIX + hashlib.sha256(encoded).hexdigest())


def _build_from_fact(
    *,
    owned_scratch: OwnedScratchContext,
    base_fact: FrameFlexuralBaseFact,
    axis: FrameFlexuralAxis,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> FrameGrossFlexuralBasisEvidence:
    """Internal deterministic composer; live public path acquires base_fact itself."""
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(base_fact, FrameFlexuralBaseFact):
        raise TypeError("base_fact must be FrameFlexuralBaseFact")
    if not isinstance(axis, FrameFlexuralAxis):
        raise TypeError("axis must be FrameFlexuralAxis")
    if not isinstance(established_state, AnalysisStateMutationResult):
        raise TypeError("established_state must be AnalysisStateMutationResult")
    if not isinstance(execution_result, AnalysisExecutionResult):
        raise TypeError("execution_result must be AnalysisExecutionResult")

    state = established_state.analysis_state_identity
    result = execution_result.analysis_result_identity
    qualification = execution_result.qualification
    manifest = execution_result.manifest

    if not qualification.qualified or qualification.analysis_state != state or qualification.analysis_result != result:
        raise FrameGrossFlexuralBasisError("B5 analysis result is not qualified for the supplied B4B state")
    if result.parent_analysis_state_ref != state.identity_ref:
        raise FrameGrossFlexuralBasisError("analysis result is parented by a different AnalysisStateIdentity")
    if not manifest.state_revalidation.matched_exact:
        raise FrameGrossFlexuralBasisError("B5 did not exactly revalidate the causal analysis state")
    if manifest.state_revalidation.current_analysis_state.identity_ref != state.identity_ref:
        raise FrameGrossFlexuralBasisError("post-analysis state identity differs from the supplied B4B state")
    if established_state.mutation_manifest.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise FrameGrossFlexuralBasisError("B4B state belongs to a different owned scratch")
    if manifest.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise FrameGrossFlexuralBasisError("B5 result belongs to a different owned scratch")
    if base_fact.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise FrameGrossFlexuralBasisError("base-model factual evidence belongs to a different owned scratch")
    source_ref = owned_scratch.source_model_identity.source_model_ref
    if any(value != source_ref for value in (base_fact.source_model_ref, state.source_model_ref, result.source_model_ref, manifest.source_model_ref)):
        raise FrameGrossFlexuralBasisError("source-model lineage mismatch")

    property_fact = _mutation(
        established_state,
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name=base_fact.assigned_section_name,
    )
    object_fact = _mutation(
        established_state,
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name=base_fact.component_unique_name,
    )
    property_value = _axis_modifier(property_fact, axis)
    object_value = _axis_modifier(object_fact, axis)
    if property_value != 1.0:
        raise FrameGrossFlexuralBasisError("frame-section-property flexural modifier is non-unit")
    if object_value != 1.0:
        raise FrameGrossFlexuralBasisError("frame-object flexural modifier is non-unit")

    ec = compare_etabs_ec_to_ts500_table_3_2(
        concrete_fck_mpa=base_fact.concrete_fck_mpa,
        factual_etabs_ec_mpa=base_fact.etabs_ec_mpa,
    )
    if not ec.positive:
        raise FrameGrossFlexuralBasisError(f"ETABS Ec is not an exact TS500 Table 3.2 match: {ec.status.value}")

    gross = derive_rectangular_gross_inertia(base_fact)
    gross_axis = gross.for_axis(axis)
    refs = (
        *base_fact.source_refs,
        base_fact.evidence_ref,
        gross.source_ref,
        *ec.source_refs,
        property_fact.after.evidence_ref,
        object_fact.after.evidence_ref,
        established_state.mutation_manifest.manifest_ref,
        state.identity_ref,
        manifest.state_revalidation.comparison.comparison_ref,
        manifest.manifest_ref,
        result.identity_ref,
        qualification.qualification_ref,
        owned_scratch.ownership_proof_ref,
    )
    return FrameGrossFlexuralBasisEvidence(
        component_unique_name=base_fact.component_unique_name,
        axis=axis,
        assigned_section_name=base_fact.assigned_section_name,
        assigned_material_name=base_fact.material_name,
        gross_inertia=gross,
        gross_i_axis_mm4=gross_axis,
        factual_etabs_ec_mpa=base_fact.etabs_ec_mpa,
        ts500_ec_comparison=ec,
        property_modifier_ref=property_fact.after.evidence_ref,
        object_modifier_ref=object_fact.after.evidence_ref,
        property_axis_modifier=property_value,
        object_axis_modifier=object_value,
        parent_analysis_state_ref=state.identity_ref,
        parent_analysis_result_ref=result.identity_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        source_model_ref=source_ref,
        source_refs=refs,
    )


def capture_frame_gross_flexural_basis_evidence(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    component_unique_name: str,
    axis: FrameFlexuralAxis,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> FrameGrossFlexuralBasisEvidence:
    """Public positive path: factual Ec/geometry are always live-captured, never caller supplied."""
    base_fact = capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=owned_scratch,
        component_unique_name=component_unique_name,
    )
    return _build_from_fact(
        owned_scratch=owned_scratch,
        base_fact=base_fact,
        axis=axis,
        established_state=established_state,
        execution_result=execution_result,
    )


__all__ = [
    "FRAME_GROSS_FLEXURAL_BASIS_CONTRACT",
    "FRAME_GROSS_INERTIA_CONTRACT",
    "FrameFlexuralAxis",
    "FrameGrossFlexuralBasisError",
    "FrameGrossFlexuralBasisEvidence",
    "RectangularGrossInertiaEvidence",
    "capture_frame_gross_flexural_basis_evidence",
    "derive_rectangular_gross_inertia",
]
