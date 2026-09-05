"""Positive TS500 Eq.7.13 basis evidence for one supported frame flexural axis.

This is intentionally an item-level authority. It does not classify whether a
frame participates in the global stability system. The only supported section
slice is a prismatic rectangular RC frame section.

C0-A3-P1 closes base-state timing by requiring a canonical PRE factual capture
whose unique evidence ref is committed into the B4B AnalysisStateIdentity, then
a canonical POST factual capture performed only after a qualified B5 result is
present. Positive frame basis evidence can be issued only from exact semantic
PRE/POST continuity plus the already-qualified B4B/B5 modifier/result lineage.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from typing import Sequence

from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierSurface
from tbdy_engine.integration.etabs_analysis_execution import (
    AnalysisExecutionResult,
)
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    AnalysisStateMutationResult,
    FrameModifierMutationFact,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import (
    OwnedScratchContext,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    FrameFlexuralBaseFact,
    capture_frame_flexural_base_fact,
)
from tbdy_engine.regulatory.ts500_concrete_elastic_modulus import (
    Ts500ConcreteEcComparison,
    compare_etabs_ec_to_ts500_table_3_2,
)

FRAME_GROSS_INERTIA_CONTRACT = "RECTANGULAR_FRAME_GROSS_INERTIA_V1"
FRAME_FLEXURAL_BASE_CONTINUITY_CONTRACT = (
    "TS500_EQ7_13_FRAME_FLEXURAL_BASE_CONTINUITY_V1"
)
FRAME_FLEXURAL_BASE_CONTINUITY_REF_PREFIX = (
    "frame-flexural-base-continuity:sha256:"
)
FRAME_GROSS_FLEXURAL_BASIS_CONTRACT = (
    "TS500_EQ7_13_FRAME_GROSS_FLEXURAL_BASIS_V2"
)
FRAME_GROSS_FLEXURAL_BASIS_REF_PREFIX = (
    "frame-gross-flexural-basis:sha256:"
)

_CONTINUITY_ISSUANCE_TOKEN = object()
_GROSS_BASIS_ISSUANCE_TOKEN = object()


class FrameFlexuralAxis(StrEnum):
    LOCAL_2_M2 = "LOCAL_2_M2"
    LOCAL_3_M3 = "LOCAL_3_M3"


class FrameFlexuralBaseContinuityStatus(StrEnum):
    BASE_STATE_CONTINUITY_PROVEN = "BASE_STATE_CONTINUITY_PROVEN"


class FrameGrossFlexuralBasisError(RuntimeError):
    """Fail-closed positive-basis construction error."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FrameGrossFlexuralBasisError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(
        sorted(
            {
                str(value).strip()
                for value in values
                if isinstance(value, str) and value.strip()
            }
        )
    )
    if not result:
        raise FrameGrossFlexuralBasisError(
            "positive evidence requires source/provenance refs"
        )
    return result


def _sha_ref(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


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


def derive_rectangular_gross_inertia(
    base_fact: FrameFlexuralBaseFact,
) -> RectangularGrossInertiaEvidence:
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
        item
        for item in state.mutation_manifest.mutations
        if item.surface is surface and item.target_name == target_name
    )
    if len(matches) != 1:
        raise FrameGrossFlexuralBasisError(
            f"required {surface.value} modifier census "
            f"missing/ambiguous for {target_name!r}"
        )
    fact = matches[0]
    if not fact.setter.success or not fact.after.success:
        raise FrameGrossFlexuralBasisError(
            f"{surface.value} modifier establishment is not successful"
        )
    return fact


def _axis_modifier(
    fact: FrameModifierMutationFact,
    axis: FrameFlexuralAxis,
) -> float:
    vector = fact.after.modifiers
    if axis is FrameFlexuralAxis.LOCAL_2_M2:
        return vector.inertia_local_2
    if axis is FrameFlexuralAxis.LOCAL_3_M3:
        return vector.inertia_local_3
    raise TypeError("axis must be FrameFlexuralAxis")


def _require_b4b_b5_lineage(
    *,
    owned_scratch: OwnedScratchContext,
    pre_fact: FrameFlexuralBaseFact,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> tuple[object, object, object, object]:
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(pre_fact, FrameFlexuralBaseFact):
        raise TypeError("pre_fact must be FrameFlexuralBaseFact")
    if not isinstance(established_state, AnalysisStateMutationResult):
        raise TypeError(
            "established_state must be AnalysisStateMutationResult"
        )
    if not isinstance(execution_result, AnalysisExecutionResult):
        raise TypeError("execution_result must be AnalysisExecutionResult")

    state = established_state.analysis_state_identity
    result = execution_result.analysis_result_identity
    qualification = execution_result.qualification
    manifest = execution_result.manifest

    if (
        not qualification.qualified
        or qualification.analysis_state != state
        or qualification.analysis_result != result
    ):
        raise FrameGrossFlexuralBasisError(
            "B5 analysis result is not qualified for the supplied B4B state"
        )
    if result.parent_analysis_state_ref != state.identity_ref:
        raise FrameGrossFlexuralBasisError(
            "analysis result is parented by a different AnalysisStateIdentity"
        )
    if not manifest.state_revalidation.matched_exact:
        raise FrameGrossFlexuralBasisError(
            "B5 did not exactly revalidate the causal analysis state"
        )
    if (
        manifest.state_revalidation.current_analysis_state.identity_ref
        != state.identity_ref
    ):
        raise FrameGrossFlexuralBasisError(
            "post-analysis state identity differs from the supplied B4B state"
        )

    if (
        established_state.mutation_manifest.ownership_proof_ref
        != owned_scratch.ownership_proof_ref
    ):
        raise FrameGrossFlexuralBasisError(
            "B4B state belongs to a different owned scratch"
        )
    if manifest.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise FrameGrossFlexuralBasisError(
            "B5 result belongs to a different owned scratch"
        )
    if pre_fact.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise FrameGrossFlexuralBasisError(
            "PRE base-model factual evidence belongs to "
            "a different owned scratch"
        )

    source_ref = owned_scratch.source_model_identity.source_model_ref
    if any(
        value != source_ref
        for value in (
            pre_fact.source_model_ref,
            state.source_model_ref,
            result.source_model_ref,
            manifest.source_model_ref,
        )
    ):
        raise FrameGrossFlexuralBasisError(
            "source-model lineage mismatch"
        )

    state_basis_refs = tuple(
        getattr(state, "state_basis_refs", ()) or ()
    )
    if pre_fact.evidence_ref not in state_basis_refs:
        raise FrameGrossFlexuralBasisError(
            "PRE frame-base capture is not committed into "
            "the B4B AnalysisStateIdentity"
        )
    current_basis_refs = tuple(
        getattr(
            manifest.state_revalidation.current_analysis_state,
            "state_basis_refs",
            (),
        )
        or ()
    )
    if pre_fact.evidence_ref not in current_basis_refs:
        raise FrameGrossFlexuralBasisError(
            "B5 post-analysis revalidation lost the PRE "
            "frame-base state-basis commitment"
        )

    return state, result, qualification, manifest


_CONTINUITY_FIELDS = (
    "component_unique_name",
    "assigned_section_name",
    "material_name",
    "section_semantics",
    "t2_mm",
    "t3_mm",
    "concrete_fck_mpa",
    "etabs_ec_mpa",
    "source_model_ref",
    "ownership_proof_ref",
)


def _semantic_mismatches(
    pre_fact: FrameFlexuralBaseFact,
    post_fact: FrameFlexuralBaseFact,
) -> tuple[str, ...]:
    return tuple(
        field_name
        for field_name in _CONTINUITY_FIELDS
        if getattr(pre_fact, field_name) != getattr(post_fact, field_name)
    )


@dataclass(frozen=True, slots=True, init=False)
class FrameFlexuralBaseContinuityEvidence:
    """Positive PRE/POST semantic continuity bound to one B4B/B5 generation."""

    pre_fact: FrameFlexuralBaseFact
    post_fact: FrameFlexuralBaseFact
    semantic_state_ref: str
    parent_analysis_state_ref: str
    parent_analysis_result_ref: str
    ownership_proof_ref: str
    source_model_ref: str
    status: FrameFlexuralBaseContinuityStatus
    source_refs: tuple[str, ...]
    evidence_ref: str
    contract: str

    def __init__(
        self,
        *,
        _issuance_token: object = None,
        pre_fact: FrameFlexuralBaseFact,
        post_fact: FrameFlexuralBaseFact,
        semantic_state_ref: str,
        parent_analysis_state_ref: str,
        parent_analysis_result_ref: str,
        ownership_proof_ref: str,
        source_model_ref: str,
        source_refs: tuple[str, ...],
        contract: str = FRAME_FLEXURAL_BASE_CONTINUITY_CONTRACT,
    ) -> None:
        if _issuance_token is not _CONTINUITY_ISSUANCE_TOKEN:
            raise TypeError(
                "FrameFlexuralBaseContinuityEvidence is factory-created only; "
                "use capture_frame_flexural_base_continuity_evidence"
            )
        if contract != FRAME_FLEXURAL_BASE_CONTINUITY_CONTRACT:
            raise FrameGrossFlexuralBasisError(
                "frame flexural base continuity contract mismatch"
            )
        if not isinstance(pre_fact, FrameFlexuralBaseFact):
            raise TypeError("pre_fact must be FrameFlexuralBaseFact")
        if not isinstance(post_fact, FrameFlexuralBaseFact):
            raise TypeError("post_fact must be FrameFlexuralBaseFact")
        if pre_fact.semantic_state_ref != post_fact.semantic_state_ref:
            raise FrameGrossFlexuralBasisError(
                "positive continuity requires exact semantic PRE/POST equality"
            )
        if semantic_state_ref != pre_fact.semantic_state_ref:
            raise FrameGrossFlexuralBasisError(
                "continuity semantic_state_ref does not match snapshots"
            )

        object.__setattr__(self, "pre_fact", pre_fact)
        object.__setattr__(self, "post_fact", post_fact)
        object.__setattr__(
            self,
            "semantic_state_ref",
            _text(semantic_state_ref, "semantic_state_ref"),
        )
        object.__setattr__(
            self,
            "parent_analysis_state_ref",
            _text(parent_analysis_state_ref, "parent_analysis_state_ref"),
        )
        object.__setattr__(
            self,
            "parent_analysis_result_ref",
            _text(parent_analysis_result_ref, "parent_analysis_result_ref"),
        )
        object.__setattr__(
            self,
            "ownership_proof_ref",
            _text(ownership_proof_ref, "ownership_proof_ref"),
        )
        object.__setattr__(
            self,
            "source_model_ref",
            _text(source_model_ref, "source_model_ref"),
        )
        object.__setattr__(
            self,
            "status",
            FrameFlexuralBaseContinuityStatus.BASE_STATE_CONTINUITY_PROVEN,
        )
        normalized_refs = _refs(source_refs)
        object.__setattr__(self, "source_refs", normalized_refs)
        object.__setattr__(self, "contract", contract)

        object.__setattr__(
            self,
            "evidence_ref",
            _sha_ref(
                FRAME_FLEXURAL_BASE_CONTINUITY_REF_PREFIX,
                {
                    "contract": contract,
                    "status": self.status.value,
                    "pre_fact_ref": pre_fact.evidence_ref,
                    "post_fact_ref": post_fact.evidence_ref,
                    "semantic_state_ref": semantic_state_ref,
                    "parent_analysis_state_ref": parent_analysis_state_ref,
                    "parent_analysis_result_ref": parent_analysis_result_ref,
                    "ownership_proof_ref": ownership_proof_ref,
                    "source_model_ref": source_model_ref,
                    "source_refs": list(normalized_refs),
                },
            ),
        )


def _build_continuity_from_facts(
    *,
    owned_scratch: OwnedScratchContext,
    pre_fact: FrameFlexuralBaseFact,
    post_fact: FrameFlexuralBaseFact,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> FrameFlexuralBaseContinuityEvidence:
    """Private deterministic seam used by the production POST capture and tests."""
    state, result, qualification, manifest = _require_b4b_b5_lineage(
        owned_scratch=owned_scratch,
        pre_fact=pre_fact,
        established_state=established_state,
        execution_result=execution_result,
    )
    if not isinstance(post_fact, FrameFlexuralBaseFact):
        raise TypeError("post_fact must be FrameFlexuralBaseFact")

    source_ref = owned_scratch.source_model_identity.source_model_ref
    if post_fact.source_model_ref != source_ref:
        raise FrameGrossFlexuralBasisError(
            "POST frame-base source_model_ref differs from "
            "the qualified analysis lineage"
        )
    if post_fact.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise FrameGrossFlexuralBasisError(
            "POST frame-base ownership_proof_ref differs from "
            "the qualified owned scratch"
        )

    mismatches = _semantic_mismatches(pre_fact, post_fact)
    if mismatches:
        raise FrameGrossFlexuralBasisError(
            "frame base PRE/POST semantic continuity mismatch: "
            + ", ".join(mismatches)
        )
    if pre_fact.semantic_state_ref != post_fact.semantic_state_ref:
        raise FrameGrossFlexuralBasisError(
            "frame base PRE/POST semantic-state digest mismatch"
        )

    refs = (
        *pre_fact.source_refs,
        *post_fact.source_refs,
        pre_fact.capture_event_ref,
        post_fact.capture_event_ref,
        pre_fact.evidence_ref,
        post_fact.evidence_ref,
        pre_fact.semantic_state_ref,
        state.identity_ref,
        manifest.state_revalidation.comparison.comparison_ref,
        manifest.manifest_ref,
        result.identity_ref,
        qualification.qualification_ref,
        owned_scratch.ownership_proof_ref,
    )
    return FrameFlexuralBaseContinuityEvidence(
        _issuance_token=_CONTINUITY_ISSUANCE_TOKEN,
        pre_fact=pre_fact,
        post_fact=post_fact,
        semantic_state_ref=pre_fact.semantic_state_ref,
        parent_analysis_state_ref=state.identity_ref,
        parent_analysis_result_ref=result.identity_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        source_model_ref=source_ref,
        source_refs=_refs(refs),
    )


def capture_frame_flexural_base_continuity_evidence(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    pre_fact: FrameFlexuralBaseFact,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> FrameFlexuralBaseContinuityEvidence:
    """Capture POST only after exact B4B/B5 lineage and PRE commitment exist.

    This function never runs analysis and never mutates ETABS. The caller/C0
    orchestration owns sequencing of PRE capture -> B4B -> B5 -> this call.
    """
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if context.source_model_identity != owned_scratch.source_model_identity:
        raise FrameGrossFlexuralBasisError(
            "context/owned-scratch source-model binding mismatch"
        )

    # Validate the already-existing B4B/B5 generation before POST acquisition.
    _require_b4b_b5_lineage(
        owned_scratch=owned_scratch,
        pre_fact=pre_fact,
        established_state=established_state,
        execution_result=execution_result,
    )

    # POST is canonical provider-issued runtime truth, not caller input.
    post_fact = capture_frame_flexural_base_fact(
        context=context,
        owned_scratch=owned_scratch,
        component_unique_name=pre_fact.component_unique_name,
    )
    return _build_continuity_from_facts(
        owned_scratch=owned_scratch,
        pre_fact=pre_fact,
        post_fact=post_fact,
        established_state=established_state,
        execution_result=execution_result,
    )


@dataclass(frozen=True, slots=True, init=False)
class FrameGrossFlexuralBasisEvidence:
    component_unique_name: str
    axis: FrameFlexuralAxis
    assigned_section_name: str
    assigned_material_name: str
    base_state_continuity: FrameFlexuralBaseContinuityEvidence
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
    evidence_ref: str
    contract: str

    def __init__(
        self,
        *,
        _issuance_token: object = None,
        component_unique_name: str,
        axis: FrameFlexuralAxis,
        assigned_section_name: str,
        assigned_material_name: str,
        base_state_continuity: FrameFlexuralBaseContinuityEvidence,
        gross_inertia: RectangularGrossInertiaEvidence,
        gross_i_axis_mm4: Decimal,
        factual_etabs_ec_mpa: Decimal,
        ts500_ec_comparison: Ts500ConcreteEcComparison,
        property_modifier_ref: str,
        object_modifier_ref: str,
        property_axis_modifier: float,
        object_axis_modifier: float,
        parent_analysis_state_ref: str,
        parent_analysis_result_ref: str,
        ownership_proof_ref: str,
        source_model_ref: str,
        source_refs: tuple[str, ...],
        contract: str = FRAME_GROSS_FLEXURAL_BASIS_CONTRACT,
    ) -> None:
        if _issuance_token is not _GROSS_BASIS_ISSUANCE_TOKEN:
            raise TypeError(
                "FrameGrossFlexuralBasisEvidence is factory-created only; "
                "use build_frame_gross_flexural_basis_evidence"
            )
        if contract != FRAME_GROSS_FLEXURAL_BASIS_CONTRACT:
            raise FrameGrossFlexuralBasisError(
                "frame gross flexural basis contract mismatch"
            )
        if not isinstance(axis, FrameFlexuralAxis):
            raise TypeError("axis must be FrameFlexuralAxis")
        if not isinstance(
            base_state_continuity,
            FrameFlexuralBaseContinuityEvidence,
        ):
            raise TypeError(
                "base_state_continuity must be "
                "FrameFlexuralBaseContinuityEvidence"
            )
        if (
            base_state_continuity.status
            is not FrameFlexuralBaseContinuityStatus.BASE_STATE_CONTINUITY_PROVEN
        ):
            raise FrameGrossFlexuralBasisError(
                "positive frame basis requires proven base-state continuity"
            )
        if not ts500_ec_comparison.positive:
            raise FrameGrossFlexuralBasisError(
                "positive frame basis requires exact TS500 Ec MATCH"
            )
        if property_axis_modifier != 1.0 or object_axis_modifier != 1.0:
            raise FrameGrossFlexuralBasisError(
                "positive frame basis requires unit property "
                "and object flexural modifiers"
            )
        if gross_i_axis_mm4 <= 0 or factual_etabs_ec_mpa <= 0:
            raise FrameGrossFlexuralBasisError(
                "positive frame basis requires positive gross I and Ec"
            )

        object.__setattr__(
            self,
            "component_unique_name",
            _text(component_unique_name, "component_unique_name"),
        )
        object.__setattr__(self, "axis", axis)
        object.__setattr__(
            self,
            "assigned_section_name",
            _text(assigned_section_name, "assigned_section_name"),
        )
        object.__setattr__(
            self,
            "assigned_material_name",
            _text(assigned_material_name, "assigned_material_name"),
        )
        object.__setattr__(
            self,
            "base_state_continuity",
            base_state_continuity,
        )
        object.__setattr__(self, "gross_inertia", gross_inertia)
        object.__setattr__(self, "gross_i_axis_mm4", gross_i_axis_mm4)
        object.__setattr__(
            self,
            "factual_etabs_ec_mpa",
            factual_etabs_ec_mpa,
        )
        object.__setattr__(
            self,
            "ts500_ec_comparison",
            ts500_ec_comparison,
        )
        object.__setattr__(
            self,
            "property_modifier_ref",
            _text(property_modifier_ref, "property_modifier_ref"),
        )
        object.__setattr__(
            self,
            "object_modifier_ref",
            _text(object_modifier_ref, "object_modifier_ref"),
        )
        object.__setattr__(
            self,
            "property_axis_modifier",
            property_axis_modifier,
        )
        object.__setattr__(
            self,
            "object_axis_modifier",
            object_axis_modifier,
        )
        object.__setattr__(
            self,
            "parent_analysis_state_ref",
            _text(parent_analysis_state_ref, "parent_analysis_state_ref"),
        )
        object.__setattr__(
            self,
            "parent_analysis_result_ref",
            _text(parent_analysis_result_ref, "parent_analysis_result_ref"),
        )
        object.__setattr__(
            self,
            "ownership_proof_ref",
            _text(ownership_proof_ref, "ownership_proof_ref"),
        )
        object.__setattr__(
            self,
            "source_model_ref",
            _text(source_model_ref, "source_model_ref"),
        )
        normalized_refs = _refs(source_refs)
        object.__setattr__(self, "source_refs", normalized_refs)
        object.__setattr__(self, "contract", contract)

        object.__setattr__(
            self,
            "evidence_ref",
            _sha_ref(
                FRAME_GROSS_FLEXURAL_BASIS_REF_PREFIX,
                {
                    "contract": contract,
                    "component_unique_name": self.component_unique_name,
                    "axis": axis.value,
                    "assigned_section_name": self.assigned_section_name,
                    "assigned_material_name": self.assigned_material_name,
                    "base_state_continuity_ref": (
                        base_state_continuity.evidence_ref
                    ),
                    "gross_i_axis_mm4": str(gross_i_axis_mm4),
                    "factual_etabs_ec_mpa": str(factual_etabs_ec_mpa),
                    "required_ts500_ec_mpa": str(
                        ts500_ec_comparison.required_ts500_ec_mpa
                    ),
                    "property_modifier_ref": property_modifier_ref,
                    "object_modifier_ref": object_modifier_ref,
                    "parent_analysis_state_ref": parent_analysis_state_ref,
                    "parent_analysis_result_ref": parent_analysis_result_ref,
                    "ownership_proof_ref": ownership_proof_ref,
                    "source_model_ref": source_model_ref,
                    "source_refs": list(normalized_refs),
                },
            ),
        )


def _build_from_continuity(
    *,
    owned_scratch: OwnedScratchContext,
    continuity: FrameFlexuralBaseContinuityEvidence,
    axis: FrameFlexuralAxis,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> FrameGrossFlexuralBasisEvidence:
    """Internal deterministic composer; production input requires continuity."""
    if not isinstance(continuity, FrameFlexuralBaseContinuityEvidence):
        raise TypeError(
            "continuity must be FrameFlexuralBaseContinuityEvidence"
        )
    if not isinstance(axis, FrameFlexuralAxis):
        raise TypeError("axis must be FrameFlexuralAxis")

    pre_fact = continuity.pre_fact
    state, result, qualification, manifest = _require_b4b_b5_lineage(
        owned_scratch=owned_scratch,
        pre_fact=pre_fact,
        established_state=established_state,
        execution_result=execution_result,
    )

    if continuity.parent_analysis_state_ref != state.identity_ref:
        raise FrameGrossFlexuralBasisError(
            "base-state continuity belongs to a different AnalysisStateIdentity"
        )
    if continuity.parent_analysis_result_ref != result.identity_ref:
        raise FrameGrossFlexuralBasisError(
            "base-state continuity belongs to a different AnalysisResultIdentity"
        )
    if (
        continuity.ownership_proof_ref
        != owned_scratch.ownership_proof_ref
    ):
        raise FrameGrossFlexuralBasisError(
            "base-state continuity belongs to a different owned scratch"
        )
    source_ref = owned_scratch.source_model_identity.source_model_ref
    if continuity.source_model_ref != source_ref:
        raise FrameGrossFlexuralBasisError(
            "base-state continuity belongs to a different source model"
        )

    property_fact = _mutation(
        established_state,
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name=pre_fact.assigned_section_name,
    )
    object_fact = _mutation(
        established_state,
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name=pre_fact.component_unique_name,
    )
    property_value = _axis_modifier(property_fact, axis)
    object_value = _axis_modifier(object_fact, axis)
    if property_value != 1.0:
        raise FrameGrossFlexuralBasisError(
            "frame-section-property flexural modifier is non-unit"
        )
    if object_value != 1.0:
        raise FrameGrossFlexuralBasisError(
            "frame-object flexural modifier is non-unit"
        )

    ec = compare_etabs_ec_to_ts500_table_3_2(
        concrete_fck_mpa=pre_fact.concrete_fck_mpa,
        factual_etabs_ec_mpa=pre_fact.etabs_ec_mpa,
    )
    if not ec.positive:
        raise FrameGrossFlexuralBasisError(
            "ETABS Ec is not an exact TS500 Table 3.2 match: "
            f"{ec.status.value}"
        )

    gross = derive_rectangular_gross_inertia(pre_fact)
    gross_axis = gross.for_axis(axis)

    refs = (
        *continuity.source_refs,
        continuity.evidence_ref,
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
        _issuance_token=_GROSS_BASIS_ISSUANCE_TOKEN,
        component_unique_name=pre_fact.component_unique_name,
        axis=axis,
        assigned_section_name=pre_fact.assigned_section_name,
        assigned_material_name=pre_fact.material_name,
        base_state_continuity=continuity,
        gross_inertia=gross,
        gross_i_axis_mm4=gross_axis,
        factual_etabs_ec_mpa=pre_fact.etabs_ec_mpa,
        ts500_ec_comparison=ec,
        property_modifier_ref=property_fact.after.evidence_ref,
        object_modifier_ref=object_fact.after.evidence_ref,
        property_axis_modifier=property_value,
        object_axis_modifier=object_value,
        parent_analysis_state_ref=state.identity_ref,
        parent_analysis_result_ref=result.identity_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        source_model_ref=source_ref,
        source_refs=_refs(refs),
    )


def build_frame_gross_flexural_basis_evidence(
    *,
    owned_scratch: OwnedScratchContext,
    continuity: FrameFlexuralBaseContinuityEvidence,
    axis: FrameFlexuralAxis,
    established_state: AnalysisStateMutationResult,
    execution_result: AnalysisExecutionResult,
) -> FrameGrossFlexuralBasisEvidence:
    """Issue one supported item/axis basis from proven PRE/POST continuity."""
    return _build_from_continuity(
        owned_scratch=owned_scratch,
        continuity=continuity,
        axis=axis,
        established_state=established_state,
        execution_result=execution_result,
    )


__all__ = [
    "FRAME_FLEXURAL_BASE_CONTINUITY_CONTRACT",
    "FRAME_GROSS_FLEXURAL_BASIS_CONTRACT",
    "FRAME_GROSS_INERTIA_CONTRACT",
    "FrameFlexuralAxis",
    "FrameFlexuralBaseContinuityEvidence",
    "FrameFlexuralBaseContinuityStatus",
    "FrameGrossFlexuralBasisError",
    "FrameGrossFlexuralBasisEvidence",
    "RectangularGrossInertiaEvidence",
    "build_frame_gross_flexural_basis_evidence",
    "capture_frame_flexural_base_continuity_evidence",
    "derive_rectangular_gross_inertia",
]
