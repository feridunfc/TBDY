from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    AUTHORITY as COMBO_ELIGIBILITY_AUTHORITY,
    ColumnComboEligibilityProjection,
    ComponentReadinessBinding,
)
from tbdy_engine.design.columns.column_design_readiness import READY
from tbdy_engine.design.columns.column_design_rebar_promotion import (
    EtabsRequiredRebarComponent,
    EtabsRequiredRebarPopulation,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    ColumnLongitudinalLayoutAuthorityResult,
)

AUTHORITY = "FND_COL_4_LONGITUDINAL_SELECTION_CONTRACT"

STATUS_RECONCILED = "RECONCILED"
STATUS_BLOCKED = "BLOCKED"

BLOCK_COMPONENT_ID_MISMATCH = "COMPONENT_ID_MISMATCH"
BLOCK_LAYOUT_NOT_PROVEN = "FND_COL_1_LAYOUT_NOT_PROVEN"
BLOCK_READINESS_NOT_READY = "FND_COL_2_READINESS_NOT_READY"
BLOCK_P8A_COMPONENT_MISSING = "P8A_COMPONENT_NOT_COVERED"
BLOCK_P8A_PROMOTION_INCOMPLETE = "P8A_COMPONENT_PROMOTION_INCOMPLETE"
BLOCK_P8A_NO_REQUIREMENTS = "P8A_COMPONENT_HAS_NO_REQUIRED_REBAR_ROWS"
BLOCK_MODEL_CONTEXT_MISMATCH = "MODEL_FINGERPRINT_MISMATCH"
BLOCK_EVIDENCE_EPOCH_MISMATCH = "EVIDENCE_EPOCH_MISMATCH"
BLOCK_DESIGN_SECTION_MISMATCH = "DESIGN_SECTION_MISMATCH"
BLOCK_PROJECTION_BINDING = "P8A_PROJECTION_BINDING_MISSING_OR_AMBIGUOUS"
BLOCK_PROJECTION_IDENTITY = "P8A_PROJECTION_IDENTITY_MISMATCH"
BLOCK_PROJECTION_NOT_ELIGIBLE = "P8A_PROJECTION_NOT_ELIGIBLE"
BLOCK_PROJECTION_READINESS = "P8A_PROJECTION_READINESS_REF_MISMATCH"
BLOCK_PROJECTION_CONTEXT = "P8A_PROJECTION_CONTEXT_MISMATCH"


class ColumnLongitudinalSelectionContractError(ValueError):
    """Malformed COL-4A contract input."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnLongitudinalSelectionContractError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _unique_texts(
    values: Sequence[str],
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    result = tuple(_text(value, label) for value in values)
    if not allow_empty and not result:
        raise ColumnLongitudinalSelectionContractError(
            f"{label} must be nonempty"
        )
    if len(result) != len(set(result)):
        raise ColumnLongitudinalSelectionContractError(
            f"{label} must not contain duplicates"
        )
    return result


def _stable_refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_text(value, "provenance_ref") for value in values}))


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalSelectionPolicyInput:
    """Explicit policy input only.

    COL-4A does not validate or execute this policy. A later authority cut must
    bind an accepted policy id/version to executable ranking behavior.
    """

    policy_id: str
    policy_version: str
    primary_objective: str
    tie_breakers: tuple[str, ...]
    review_ref: str
    authority: str = "FND_COL_4_SELECTION_POLICY_INPUT_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "policy_version",
            _text(self.policy_version, "policy_version"),
        )
        object.__setattr__(
            self,
            "primary_objective",
            _text(self.primary_objective, "primary_objective"),
        )
        tie_breakers = _unique_texts(
            self.tie_breakers,
            "tie_breaker",
        )
        if self.primary_objective in tie_breakers:
            raise ColumnLongitudinalSelectionContractError(
                "primary_objective may not be repeated as a tie_breaker"
            )
        object.__setattr__(self, "tie_breakers", tie_breakers)
        object.__setattr__(
            self,
            "review_ref",
            _text(self.review_ref, "review_ref"),
        )


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalSelectionInputs:
    component_id: str
    layout_authority: ColumnLongitudinalLayoutAuthorityResult
    readiness_binding: ComponentReadinessBinding
    etabs_required_rebar: EtabsRequiredRebarPopulation
    combo_eligibility_projections: tuple[ColumnComboEligibilityProjection, ...]
    policy: ColumnLongitudinalSelectionPolicyInput

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _text(self.component_id, "component_id"),
        )
        if not isinstance(
            self.layout_authority,
            ColumnLongitudinalLayoutAuthorityResult,
        ):
            raise TypeError(
                "layout_authority must be ColumnLongitudinalLayoutAuthorityResult"
            )
        if not isinstance(self.readiness_binding, ComponentReadinessBinding):
            raise TypeError(
                "readiness_binding must be ComponentReadinessBinding"
            )
        if not isinstance(
            self.etabs_required_rebar,
            EtabsRequiredRebarPopulation,
        ):
            raise TypeError(
                "etabs_required_rebar must be EtabsRequiredRebarPopulation"
            )
        if not isinstance(
            self.policy,
            ColumnLongitudinalSelectionPolicyInput,
        ):
            raise TypeError(
                "policy must be ColumnLongitudinalSelectionPolicyInput"
            )

        projections = tuple(self.combo_eligibility_projections)
        if any(
            not isinstance(item, ColumnComboEligibilityProjection)
            for item in projections
        ):
            raise TypeError(
                "combo_eligibility_projections must contain "
                "ColumnComboEligibilityProjection"
            )

        object.__setattr__(
            self,
            "combo_eligibility_projections",
            tuple(sorted(projections, key=lambda item: item.projection_id)),
        )


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalSelectionContract:
    component_id: str
    status: str
    blockers: tuple[str, ...]
    eligible_candidate_ids: tuple[str, ...]
    etabs_requirement_ids: tuple[str, ...]
    combo_projection_ids: tuple[str, ...]
    model_fingerprint: str
    evidence_epoch_id: str
    readiness_ref: str
    policy_id: str
    policy_version: str
    provenance_refs: tuple[str, ...]
    authority: str = AUTHORITY

    @property
    def reconciled(self) -> bool:
        return self.status == STATUS_RECONCILED


def _component_promotion(
    population: EtabsRequiredRebarPopulation,
    component_id: str,
) -> EtabsRequiredRebarComponent | None:
    matches = tuple(
        item
        for item in population.components
        if item.component_id == component_id
    )
    if len(matches) != 1:
        return None
    return matches[0]


def reconcile_column_longitudinal_selection_contract(
    inputs: ColumnLongitudinalSelectionInputs,
) -> ColumnLongitudinalSelectionContract:
    """Reconcile existing authorities without performing engineering selection."""

    if not isinstance(inputs, ColumnLongitudinalSelectionInputs):
        raise TypeError(
            "inputs must be ColumnLongitudinalSelectionInputs"
        )

    component_id = inputs.component_id
    layout = inputs.layout_authority
    requirement = layout.requirement
    readiness_binding = inputs.readiness_binding
    readiness = readiness_binding.readiness
    promotion = inputs.etabs_required_rebar

    blockers: list[str] = []

    def block(code: str) -> None:
        if code not in blockers:
            blockers.append(code)

    if requirement.component_id != component_id:
        block(BLOCK_COMPONENT_ID_MISMATCH)

    if readiness_binding.component_id != component_id:
        block(BLOCK_COMPONENT_ID_MISMATCH)

    if layout.status != "PROVEN":
        block(BLOCK_LAYOUT_NOT_PROVEN)

    if layout.authority != "TBDY_COLUMN_LAYOUT_ELIGIBILITY":
        block(BLOCK_LAYOUT_NOT_PROVEN)

    if requirement.authority != "TBDY_MIN_REQUIRED_REBAR":
        block(BLOCK_LAYOUT_NOT_PROVEN)

    if readiness.status != READY:
        block(BLOCK_READINESS_NOT_READY)

    component_promotion = _component_promotion(
        promotion,
        component_id,
    )

    if component_promotion is None:
        block(BLOCK_P8A_COMPONENT_MISSING)
        requirements = ()
    else:
        requirements = component_promotion.requirements

        if not component_promotion.promotion_complete:
            block(BLOCK_P8A_PROMOTION_INCOMPLETE)

        if not requirements:
            block(BLOCK_P8A_NO_REQUIREMENTS)

    model_values = {
        requirement.model_identity,
        readiness_binding.model_fingerprint,
        promotion.model_fingerprint,
    }
    if len(model_values) != 1:
        block(BLOCK_MODEL_CONTEXT_MISMATCH)

    epoch_values = {
        requirement.evidence_epoch_id,
        readiness_binding.evidence_epoch_id,
        promotion.evidence_epoch_id,
    }
    if len(epoch_values) != 1:
        block(BLOCK_EVIDENCE_EPOCH_MISMATCH)

    design_sections = {
        item.design_section
        for item in requirements
    }
    if (
        len(design_sections) > 1
        or (
            design_sections
            and requirement.section_id not in design_sections
        )
    ):
        block(BLOCK_DESIGN_SECTION_MISMATCH)

    projections = inputs.combo_eligibility_projections
    projection_ids_seen: set[str] = set()
    duplicate_projection_ids: set[str] = set()

    for projection in projections:
        if projection.projection_id in projection_ids_seen:
            duplicate_projection_ids.add(projection.projection_id)
        projection_ids_seen.add(projection.projection_id)

    used_projection_ids: list[str] = []

    for required in sorted(
        requirements,
        key=lambda item: item.requirement_id,
    ):
        matches = tuple(
            projection
            for projection in projections
            if projection.projection_id
            == required.combo_eligibility_projection_id
        )

        if (
            len(matches) != 1
            or required.combo_eligibility_projection_id
            in duplicate_projection_ids
        ):
            block(BLOCK_PROJECTION_BINDING)
            continue

        projection = matches[0]
        used_projection_ids.append(projection.projection_id)

        if (
            projection.authority != COMBO_ELIGIBILITY_AUTHORITY
            or projection.component_id != component_id
            or projection.design_combo_identity
            != required.design_combo_identity
        ):
            block(BLOCK_PROJECTION_IDENTITY)

        if not projection.eligible:
            block(BLOCK_PROJECTION_NOT_ELIGIBLE)

        if (
            projection.component_readiness_ref
            != readiness_binding.readiness_ref
            or projection.component_readiness_status != READY
        ):
            block(BLOCK_PROJECTION_READINESS)

        if (
            projection.model_fingerprint
            != readiness_binding.model_fingerprint
            or projection.model_fingerprint
            != required.model_fingerprint
            or projection.evidence_epoch_id
            != readiness_binding.evidence_epoch_id
            or projection.evidence_epoch_id
            != required.evidence_epoch_id
        ):
            block(BLOCK_PROJECTION_CONTEXT)

    candidate_ids = tuple(
        sorted(
            candidate.candidate_id
            for candidate in layout.eligible_candidates
        )
    )
    requirement_ids = tuple(
        sorted(item.requirement_id for item in requirements)
    )
    projection_ids = tuple(sorted(set(used_projection_ids)))

    provenance_values: list[str] = [
        layout.authority_binding_ref,
        layout.implementation_fingerprint,
        requirement.geometry_source_ref,
        *requirement.source_claim_refs,
        *requirement.source_review_refs,
        readiness_binding.readiness_ref,
        *readiness_binding.provenance_refs,
        *readiness.source_refs,
        *promotion.source_refs,
        inputs.policy.review_ref,
    ]

    if component_promotion is not None:
        provenance_values.extend(component_promotion.source_refs)

    for required in requirements:
        provenance_values.extend(required.source_refs)

    for projection in projections:
        if projection.projection_id in projection_ids:
            provenance_values.append(projection.projection_id)
            provenance_values.extend(projection.provenance_refs)
            if projection.analysis_basis_ref is not None:
                provenance_values.append(projection.analysis_basis_ref)

    status = STATUS_RECONCILED if not blockers else STATUS_BLOCKED

    return ColumnLongitudinalSelectionContract(
        component_id=component_id,
        status=status,
        blockers=tuple(blockers),
        eligible_candidate_ids=candidate_ids,
        etabs_requirement_ids=requirement_ids,
        combo_projection_ids=projection_ids,
        model_fingerprint=readiness_binding.model_fingerprint,
        evidence_epoch_id=readiness_binding.evidence_epoch_id,
        readiness_ref=readiness_binding.readiness_ref,
        policy_id=inputs.policy.policy_id,
        policy_version=inputs.policy.policy_version,
        provenance_refs=_stable_refs(provenance_values),
    )


__all__ = [
    "AUTHORITY",
    "BLOCK_COMPONENT_ID_MISMATCH",
    "BLOCK_DESIGN_SECTION_MISMATCH",
    "BLOCK_EVIDENCE_EPOCH_MISMATCH",
    "BLOCK_LAYOUT_NOT_PROVEN",
    "BLOCK_MODEL_CONTEXT_MISMATCH",
    "BLOCK_P8A_COMPONENT_MISSING",
    "BLOCK_P8A_NO_REQUIREMENTS",
    "BLOCK_P8A_PROMOTION_INCOMPLETE",
    "BLOCK_PROJECTION_BINDING",
    "BLOCK_PROJECTION_CONTEXT",
    "BLOCK_PROJECTION_IDENTITY",
    "BLOCK_PROJECTION_NOT_ELIGIBLE",
    "BLOCK_PROJECTION_READINESS",
    "BLOCK_READINESS_NOT_READY",
    "ColumnLongitudinalSelectionContract",
    "ColumnLongitudinalSelectionContractError",
    "ColumnLongitudinalSelectionInputs",
    "ColumnLongitudinalSelectionPolicyInput",
    "STATUS_BLOCKED",
    "STATUS_RECONCILED",
    "reconcile_column_longitudinal_selection_contract",
]
