"""FND-COL-4C1B exhaustive column candidate adequacy population.

This module contains no independent engineering acceptance formula.
It revalidates the current selection context, performs the canonical B2
numerical assessment using the current numerical/material authorities, applies
the sealed C1A row-decision primitives to every P8A and PMM row, and applies
the sealed C1A aggregate primitive to every candidate.

There is no candidate ranking or final reinforcement selection in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Sequence

from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionContract,
    ColumnLongitudinalSelectionInputs,
    reconcile_column_longitudinal_selection_contract,
)
from tbdy_engine.design.columns.column_pmm_assessment import (
    ColumnPmmMaterialContextBinding,
    assess_all_column_pmm_candidate_demands,
    candidate_geometry_binding_fingerprint,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    AREA_GUARD_INSUFFICIENT,
    AREA_GUARD_SATISFIED,
    CANDIDATE_ADEQUATE,
    CANDIDATE_INADEQUATE,
    CANDIDATE_UNRESOLVED,
    FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID,
    ValidatedCandidateAdequacyPolicy,
    aggregate_candidate_adequacy,
    evaluate_candidate_pmm_adequacy,
    evaluate_required_area_guard,
)
from tbdy_engine.regulatory.column_pmm_authority import (
    ValidatedPmmNumericalPolicy,
)


AUTHORITY = "FND_COL_4_CANDIDATE_ADEQUACY_POPULATION"

COMPLETE = "COMPLETE_CANDIDATE_ADEQUACY_POPULATION"
COMPLETE_WITH_UNRESOLVED = (
    "COMPLETE_WITH_UNRESOLVED_CANDIDATES"
)
BLOCKED = "BLOCKED"

BLOCK_SELECTION_CONTRACT = (
    "SELECTION_CONTRACT_NOT_CURRENT_AND_RECONCILED"
)
BLOCK_P8A_COMPONENT = "P8A_COMPONENT_POPULATION_MISMATCH"
BLOCK_PMM_ASSESSMENT = "PMM_ASSESSMENT_NOT_COMPLETE"
BLOCK_PMM_CONTEXT = "PMM_ASSESSMENT_CONTEXT_MISMATCH"
BLOCK_GEOMETRY_BINDING = (
    "PMM_CANDIDATE_GEOMETRY_BINDING_MISMATCH"
)


class ColumnCandidateAdequacyError(ValueError):
    """Malformed COL-4C1B adequacy population input."""


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnCandidateAdequacyError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return prefix + hashlib.sha256(encoded).hexdigest()


def _refs(
    values: Sequence[str],
) -> tuple[str, ...]:
    result = tuple(
        sorted(
            {
                _text(value, "provenance_ref")
                for value in values
            }
        )
    )

    if not result:
        raise ColumnCandidateAdequacyError(
            "provenance refs must be nonempty"
        )

    return result


@dataclass(frozen=True, slots=True)
class CandidateRequiredAreaAssessment:
    decision_id: str
    candidate_id: str
    candidate_geometry_fingerprint: str
    requirement_id: str
    candidate_as_mm2: Decimal
    required_as_mm2: Decimal
    margin_mm2: Decimal
    status: str
    policy_fingerprint: str
    source_refs: tuple[str, ...]
    authority: str = (
        "FND_COL_4_P8A_REQUIRED_AREA_ROW_ASSESSMENT"
    )


@dataclass(frozen=True, slots=True)
class CandidatePmmAdequacyAssessment:
    decision_id: str
    candidate_id: str
    candidate_geometry_fingerprint: str
    assessment_id: str
    state_id: str
    numerical_status: str
    utilization: float | None
    status: str
    policy_fingerprint: str
    authority: str = (
        "FND_COL_4_PMM_ADEQUACY_ROW_ASSESSMENT"
    )


@dataclass(frozen=True, slots=True)
class CandidateAdequacyAssessment:
    candidate_id: str
    candidate_geometry_fingerprint: str
    candidate_as_mm2: Decimal
    status: str
    required_area_decision_ids: tuple[str, ...]
    pmm_decision_ids: tuple[str, ...]
    area_satisfied_count: int
    area_insufficient_count: int
    pmm_ok_count: int
    pmm_fail_count: int
    pmm_unresolved_count: int
    policy_fingerprint: str
    authority: str = (
        "FND_COL_4_CANDIDATE_ADEQUACY_ASSESSMENT"
    )


@dataclass(frozen=True, slots=True)
class ColumnCandidateAdequacyPopulation:
    component_id: str
    status: str
    blockers: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    demand_state_ids: tuple[str, ...]
    expected_required_area_decision_count: int
    expected_pmm_decision_count: int
    required_area_rows: tuple[
        CandidateRequiredAreaAssessment, ...
    ]
    pmm_rows: tuple[
        CandidatePmmAdequacyAssessment, ...
    ]
    candidate_assessments: tuple[
        CandidateAdequacyAssessment, ...
    ]
    adequate_candidate_count: int
    inadequate_candidate_count: int
    unresolved_candidate_count: int
    adequacy_policy_id: str
    adequacy_policy_version: str
    adequacy_policy_fingerprint: str
    adequacy_authority_binding_ref: str
    adequacy_implementation_fingerprint: str
    numerical_policy_fingerprint: str
    material_context_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    provenance_refs: tuple[str, ...]
    authority: str = AUTHORITY

    @property
    def complete(self) -> bool:
        return self.status in {
            COMPLETE,
            COMPLETE_WITH_UNRESOLVED,
        }

    def __post_init__(self) -> None:
        candidates = tuple(self.candidate_ids)
        requirements = tuple(self.requirement_ids)
        states = tuple(self.demand_state_ids)

        if candidates != tuple(sorted(candidates)):
            raise ColumnCandidateAdequacyError(
                "candidate_ids must be canonically sorted"
            )

        if requirements != tuple(sorted(requirements)):
            raise ColumnCandidateAdequacyError(
                "requirement_ids must be canonically sorted"
            )

        if states != tuple(sorted(states)):
            raise ColumnCandidateAdequacyError(
                "demand_state_ids must be canonically sorted"
            )

        if len(candidates) != len(set(candidates)):
            raise ColumnCandidateAdequacyError(
                "candidate_ids must be unique"
            )

        if len(requirements) != len(set(requirements)):
            raise ColumnCandidateAdequacyError(
                "requirement_ids must be unique"
            )

        if len(states) != len(set(states)):
            raise ColumnCandidateAdequacyError(
                "demand_state_ids must be unique"
            )

        expected_area = (
            len(candidates) * len(requirements)
        )
        expected_pmm = len(candidates) * len(states)

        if (
            self.expected_required_area_decision_count
            != expected_area
        ):
            raise ColumnCandidateAdequacyError(
                "required-area decision cardinality mismatch"
            )

        if self.expected_pmm_decision_count != expected_pmm:
            raise ColumnCandidateAdequacyError(
                "PMM decision cardinality mismatch"
            )

        if self.complete:
            if len(self.required_area_rows) != expected_area:
                raise ColumnCandidateAdequacyError(
                    "complete adequacy population must retain "
                    "every candidate x P8A requirement row"
                )

            if len(self.pmm_rows) != expected_pmm:
                raise ColumnCandidateAdequacyError(
                    "complete adequacy population must retain "
                    "every candidate x PMM demand row"
                )

            area_pairs = {
                (row.candidate_id, row.requirement_id)
                for row in self.required_area_rows
            }

            expected_area_pairs = {
                (candidate_id, requirement_id)
                for candidate_id in candidates
                for requirement_id in requirements
            }

            if (
                len(area_pairs) != expected_area
                or area_pairs != expected_area_pairs
            ):
                raise ColumnCandidateAdequacyError(
                    "required-area row population is incomplete "
                    "or duplicated"
                )

            pmm_pairs = {
                (row.candidate_id, row.state_id)
                for row in self.pmm_rows
            }

            expected_pmm_pairs = {
                (candidate_id, state_id)
                for candidate_id in candidates
                for state_id in states
            }

            if (
                len(pmm_pairs) != expected_pmm
                or pmm_pairs != expected_pmm_pairs
            ):
                raise ColumnCandidateAdequacyError(
                    "PMM adequacy row population is incomplete "
                    "or duplicated"
                )

            if tuple(
                item.candidate_id
                for item in self.candidate_assessments
            ) != candidates:
                raise ColumnCandidateAdequacyError(
                    "candidate adequacy summaries do not exactly "
                    "cover candidate population"
                )

        elif (
            self.required_area_rows
            or self.pmm_rows
            or self.candidate_assessments
        ):
            raise ColumnCandidateAdequacyError(
                "blocked adequacy population may not publish "
                "partial decisions"
            )

        if (
            self.adequate_candidate_count
            + self.inadequate_candidate_count
            + self.unresolved_candidate_count
            != len(self.candidate_assessments)
        ):
            raise ColumnCandidateAdequacyError(
                "candidate adequacy accounting mismatch"
            )


def _component_promotion(inputs):
    matches = tuple(
        component
        for component
        in inputs.etabs_required_rebar.components
        if component.component_id == inputs.component_id
    )

    if len(matches) != 1:
        return None

    return matches[0]


def _base_provenance(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    selection_contract: ColumnLongitudinalSelectionContract,
    numerical_policy: ValidatedPmmNumericalPolicy,
    material_context: ColumnPmmMaterialContextBinding,
    adequacy_policy: ValidatedCandidateAdequacyPolicy,
    extra_refs: Sequence[str] = (),
) -> tuple[str, ...]:
    values = {
        *selection_contract.provenance_refs,
        inputs.layout_authority.authority_binding_ref,
        inputs.layout_authority.implementation_fingerprint,
        inputs.readiness_binding.readiness_ref,
        adequacy_policy.authority_binding_ref,
        adequacy_policy.implementation_fingerprint,
        adequacy_policy.policy_fingerprint,
        adequacy_policy.etabs_area_guard_review_ref,
        *adequacy_policy.source_claim_refs,
        *adequacy_policy.source_review_refs,
        numerical_policy.authority_binding_ref,
        numerical_policy.implementation_fingerprint,
        numerical_policy.policy_fingerprint,
        numerical_policy.validated_domain_ref,
        *numerical_policy.validation_evidence_refs,
        numerical_policy.review_ref,
        material_context.binding_ref,
        material_context.section_material_binding_ref,
        *extra_refs,
    }

    return _refs(tuple(values))


def _blocked_population(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    selection_contract: ColumnLongitudinalSelectionContract,
    numerical_policy: ValidatedPmmNumericalPolicy,
    material_context: ColumnPmmMaterialContextBinding,
    adequacy_policy: ValidatedCandidateAdequacyPolicy,
    blockers: Sequence[str],
) -> ColumnCandidateAdequacyPopulation:
    candidate_ids = tuple(
        sorted(
            candidate.candidate_id
            for candidate
            in inputs.layout_authority.eligible_candidates
        )
    )

    promotion = _component_promotion(inputs)

    requirement_ids = (
        ()
        if promotion is None
        else tuple(
            sorted(
                requirement.requirement_id
                for requirement in promotion.requirements
            )
        )
    )

    state_ids = tuple(
        sorted(
            state.state_id
            for state
            in inputs.readiness_binding.readiness.demand_states
        )
    )

    return ColumnCandidateAdequacyPopulation(
        component_id=inputs.component_id,
        status=BLOCKED,
        blockers=tuple(dict.fromkeys(blockers)),
        candidate_ids=candidate_ids,
        requirement_ids=requirement_ids,
        demand_state_ids=state_ids,
        expected_required_area_decision_count=(
            len(candidate_ids) * len(requirement_ids)
        ),
        expected_pmm_decision_count=(
            len(candidate_ids) * len(state_ids)
        ),
        required_area_rows=(),
        pmm_rows=(),
        candidate_assessments=(),
        adequate_candidate_count=0,
        inadequate_candidate_count=0,
        unresolved_candidate_count=0,
        adequacy_policy_id=adequacy_policy.policy_id,
        adequacy_policy_version=(
            adequacy_policy.policy_version
        ),
        adequacy_policy_fingerprint=(
            adequacy_policy.policy_fingerprint
        ),
        adequacy_authority_binding_ref=(
            adequacy_policy.authority_binding_ref
        ),
        adequacy_implementation_fingerprint=(
            adequacy_policy.implementation_fingerprint
        ),
        numerical_policy_fingerprint=(
            numerical_policy.policy_fingerprint
        ),
        material_context_ref=material_context.binding_ref,
        model_fingerprint=(
            inputs.readiness_binding.model_fingerprint
        ),
        evidence_epoch_id=(
            inputs.readiness_binding.evidence_epoch_id
        ),
        provenance_refs=_base_provenance(
            inputs=inputs,
            selection_contract=selection_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
        ),
    )


def evaluate_column_candidate_adequacy_population(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    selection_contract: ColumnLongitudinalSelectionContract,
    numerical_policy: ValidatedPmmNumericalPolicy,
    material_context: ColumnPmmMaterialContextBinding,
    adequacy_policy: ValidatedCandidateAdequacyPolicy,
) -> ColumnCandidateAdequacyPopulation:
    """Evaluate every candidate against every canonical requirement."""

    if not isinstance(
        inputs,
        ColumnLongitudinalSelectionInputs,
    ):
        raise TypeError(
            "inputs must be ColumnLongitudinalSelectionInputs"
        )

    if not isinstance(
        selection_contract,
        ColumnLongitudinalSelectionContract,
    ):
        raise TypeError(
            "selection_contract must be "
            "ColumnLongitudinalSelectionContract"
        )

    if not isinstance(
        numerical_policy,
        ValidatedPmmNumericalPolicy,
    ):
        raise TypeError(
            "numerical_policy must be "
            "ValidatedPmmNumericalPolicy"
        )

    if not isinstance(
        material_context,
        ColumnPmmMaterialContextBinding,
    ):
        raise TypeError(
            "material_context must be "
            "ColumnPmmMaterialContextBinding"
        )

    if not isinstance(
        adequacy_policy,
        ValidatedCandidateAdequacyPolicy,
    ):
        raise TypeError(
            "adequacy_policy must be "
            "ValidatedCandidateAdequacyPolicy"
        )

    if (
        adequacy_policy.authority
        != "VALIDATED_COLUMN_CANDIDATE_ADEQUACY_POLICY"
        or adequacy_policy.rule_id
        != FND_COL_4_CANDIDATE_ADEQUACY_RULE_ID.value
    ):
        raise ColumnCandidateAdequacyError(
            "unrecognized candidate adequacy policy"
        )

    fresh_contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    initial_blockers: list[str] = []

    if (
        not fresh_contract.reconciled
        or fresh_contract != selection_contract
    ):
        initial_blockers.append(
            BLOCK_SELECTION_CONTRACT
        )

    if initial_blockers:
        return _blocked_population(
            inputs=inputs,
            selection_contract=selection_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
            blockers=initial_blockers,
        )

    promotion = _component_promotion(inputs)

    if promotion is None:
        return _blocked_population(
            inputs=inputs,
            selection_contract=selection_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
            blockers=(BLOCK_P8A_COMPONENT,),
        )

    requirements = tuple(
        sorted(
            promotion.requirements,
            key=lambda item: item.requirement_id,
        )
    )

    requirement_ids = tuple(
        item.requirement_id
        for item in requirements
    )

    if (
        not promotion.promotion_complete
        or not requirements
        or requirement_ids
        != fresh_contract.etabs_requirement_ids
    ):
        return _blocked_population(
            inputs=inputs,
            selection_contract=selection_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
            blockers=(BLOCK_P8A_COMPONENT,),
        )

    candidates = tuple(
        sorted(
            inputs.layout_authority.eligible_candidates,
            key=lambda item: item.candidate_id,
        )
    )

    candidate_ids = tuple(
        candidate.candidate_id
        for candidate in candidates
    )

    if (
        not candidates
        or candidate_ids
        != fresh_contract.eligible_candidate_ids
        or len(candidate_ids) != len(set(candidate_ids))
    ):
        return _blocked_population(
            inputs=inputs,
            selection_contract=selection_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
            blockers=(BLOCK_SELECTION_CONTRACT,),
        )

    pmm = assess_all_column_pmm_candidate_demands(
        inputs=inputs,
        selection_contract=selection_contract,
        numerical_policy=numerical_policy,
        material_context=material_context,
    )

    blockers: list[str] = []

    if not pmm.enumeration_complete:
        blockers.append(BLOCK_PMM_ASSESSMENT)

    current_states = tuple(
        sorted(
            inputs.readiness_binding.readiness.demand_states,
            key=lambda state: state.state_id,
        )
    )

    state_ids = tuple(
        state.state_id
        for state in current_states
    )

    state_by_id = {
        state.state_id: state
        for state in current_states
    }

    if (
        len(state_by_id) != len(current_states)
        or pmm.component_id != inputs.component_id
        or pmm.candidate_ids != candidate_ids
        or pmm.demand_state_ids != state_ids
        or pmm.model_fingerprint
        != fresh_contract.model_fingerprint
        or pmm.evidence_epoch_id
        != fresh_contract.evidence_epoch_id
        or pmm.numerical_policy_fingerprint
        != numerical_policy.policy_fingerprint
        or pmm.numerical_policy_authority_binding_ref
        != numerical_policy.authority_binding_ref
        or pmm.material_context_ref
        != material_context.binding_ref
    ):
        blockers.append(BLOCK_PMM_CONTEXT)

    requirement = inputs.layout_authority.requirement

    expected_geometry_fingerprints = {
        candidate.candidate_id:
        candidate_geometry_binding_fingerprint(
            component_id=inputs.component_id,
            section_id=requirement.section_id,
            width_mm=requirement.width_mm,
            depth_mm=requirement.depth_mm,
            candidate=candidate,
            layout_authority_binding_ref=(
                inputs.layout_authority.authority_binding_ref
            ),
            layout_implementation_fingerprint=(
                inputs.layout_authority
                .implementation_fingerprint
            ),
            model_fingerprint=(
                fresh_contract.model_fingerprint
            ),
            evidence_epoch_id=(
                fresh_contract.evidence_epoch_id
            ),
        )
        for candidate in candidates
    }

    summary_by_candidate = {
        summary.candidate_id: summary
        for summary in pmm.candidate_assessments
    }

    if (
        set(summary_by_candidate)
        != set(candidate_ids)
        or any(
            summary_by_candidate[candidate_id]
            .candidate_geometry_fingerprint
            != expected_geometry_fingerprints[candidate_id]
            for candidate_id in candidate_ids
        )
    ):
        blockers.append(BLOCK_GEOMETRY_BINDING)

    for row in pmm.assessment_rows:
        state = state_by_id.get(row.state_id)

        if (
            row.component_id != inputs.component_id
            or state is None
            or row.candidate_id
            not in expected_geometry_fingerprints
            or row.candidate_geometry_fingerprint
            != expected_geometry_fingerprints.get(
                row.candidate_id
            )
            or row.numerical_policy_fingerprint
            != pmm.numerical_policy_fingerprint
            or row.material_context_ref
            != pmm.material_context_ref
        ):
            blockers.append(BLOCK_PMM_CONTEXT)
            break

        if (
            row.nd_compression_n
            != state.nd_compression_n
            or row.m2_nmm != state.m2_nmm
            or row.m3_nmm != state.m3_nmm
        ):
            blockers.append(BLOCK_PMM_CONTEXT)
            break

    if blockers:
        return _blocked_population(
            inputs=inputs,
            selection_contract=selection_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
            blockers=blockers,
        )

    area_rows: list[
        CandidateRequiredAreaAssessment
    ] = []

    pmm_rows: list[
        CandidatePmmAdequacyAssessment
    ] = []

    for candidate in candidates:
        geometry_fingerprint = (
            expected_geometry_fingerprints[
                candidate.candidate_id
            ]
        )

        for required in requirements:
            decision = evaluate_required_area_guard(
                policy=adequacy_policy,
                candidate_as_mm2=(
                    candidate.as_total_mm2
                ),
                required_as_mm2=(
                    required.required_as_mm2
                ),
            )

            decision_id = _stable_id(
                "candidate-area-decision:sha256:",
                {
                    "candidate_id": candidate.candidate_id,
                    "candidate_geometry_fingerprint": (
                        geometry_fingerprint
                    ),
                    "requirement_id": (
                        required.requirement_id
                    ),
                    "candidate_as_mm2": str(
                        decision.candidate_as_mm2
                    ),
                    "required_as_mm2": str(
                        decision.required_as_mm2
                    ),
                    "status": decision.status,
                    "policy_fingerprint": (
                        adequacy_policy.policy_fingerprint
                    ),
                },
            )

            area_rows.append(
                CandidateRequiredAreaAssessment(
                    decision_id=decision_id,
                    candidate_id=candidate.candidate_id,
                    candidate_geometry_fingerprint=(
                        geometry_fingerprint
                    ),
                    requirement_id=(
                        required.requirement_id
                    ),
                    candidate_as_mm2=(
                        decision.candidate_as_mm2
                    ),
                    required_as_mm2=(
                        decision.required_as_mm2
                    ),
                    margin_mm2=decision.margin_mm2,
                    status=decision.status,
                    policy_fingerprint=(
                        adequacy_policy.policy_fingerprint
                    ),
                    source_refs=_refs(
                        (
                            required.requirement_id,
                            required.source_row_id,
                            required.combo_eligibility_projection_id,
                            *required.source_refs,
                        )
                    ),
                )
            )

    for row in pmm.assessment_rows:
        decision = evaluate_candidate_pmm_adequacy(
            policy=adequacy_policy,
            component_id=inputs.component_id,
            numerically_resolved=(
                row.numerically_resolved
            ),
            utilization=(
                row.utilization
                if row.numerically_resolved
                else None
            ),
        )

        decision_id = _stable_id(
            "candidate-pmm-decision:sha256:",
            {
                "candidate_id": row.candidate_id,
                "candidate_geometry_fingerprint": (
                    row.candidate_geometry_fingerprint
                ),
                "assessment_id": row.assessment_id,
                "state_id": row.state_id,
                "numerical_status": (
                    row.numerical_status
                ),
                "utilization": row.utilization,
                "decision_status": (
                    decision.status.value
                ),
                "policy_fingerprint": (
                    adequacy_policy.policy_fingerprint
                ),
            },
        )

        pmm_rows.append(
            CandidatePmmAdequacyAssessment(
                decision_id=decision_id,
                candidate_id=row.candidate_id,
                candidate_geometry_fingerprint=(
                    row.candidate_geometry_fingerprint
                ),
                assessment_id=row.assessment_id,
                state_id=row.state_id,
                numerical_status=row.numerical_status,
                utilization=row.utilization,
                status=decision.status.value,
                policy_fingerprint=(
                    adequacy_policy.policy_fingerprint
                ),
            )
        )

    area_rows.sort(
        key=lambda row: (
            row.candidate_id,
            row.requirement_id,
        )
    )

    pmm_rows.sort(
        key=lambda row: (
            row.candidate_id,
            row.state_id,
        )
    )

    candidate_assessments: list[
        CandidateAdequacyAssessment
    ] = []

    for candidate in candidates:
        candidate_area_rows = tuple(
            row
            for row in area_rows
            if row.candidate_id
            == candidate.candidate_id
        )

        candidate_pmm_rows = tuple(
            row
            for row in pmm_rows
            if row.candidate_id
            == candidate.candidate_id
        )

        aggregate = aggregate_candidate_adequacy(
            policy=adequacy_policy,
            pmm_statuses=tuple(
                CheckStatus(row.status)
                for row in candidate_pmm_rows
            ),
            area_guard_statuses=tuple(
                row.status
                for row in candidate_area_rows
            ),
        )

        candidate_assessments.append(
            CandidateAdequacyAssessment(
                candidate_id=candidate.candidate_id,
                candidate_geometry_fingerprint=(
                    expected_geometry_fingerprints[
                        candidate.candidate_id
                    ]
                ),
                candidate_as_mm2=Decimal(
                    str(candidate.as_total_mm2)
                ),
                status=aggregate.status,
                required_area_decision_ids=tuple(
                    row.decision_id
                    for row in candidate_area_rows
                ),
                pmm_decision_ids=tuple(
                    row.decision_id
                    for row in candidate_pmm_rows
                ),
                area_satisfied_count=(
                    aggregate.area_satisfied_count
                ),
                area_insufficient_count=(
                    aggregate.area_insufficient_count
                ),
                pmm_ok_count=aggregate.pmm_ok_count,
                pmm_fail_count=aggregate.pmm_fail_count,
                pmm_unresolved_count=(
                    aggregate.pmm_unresolved_count
                ),
                policy_fingerprint=(
                    adequacy_policy.policy_fingerprint
                ),
            )
        )

    adequate_count = sum(
        item.status == CANDIDATE_ADEQUATE
        for item in candidate_assessments
    )

    inadequate_count = sum(
        item.status == CANDIDATE_INADEQUATE
        for item in candidate_assessments
    )

    unresolved_count = sum(
        item.status == CANDIDATE_UNRESOLVED
        for item in candidate_assessments
    )

    population_status = (
        COMPLETE_WITH_UNRESOLVED
        if unresolved_count > 0
        else COMPLETE
    )

    provenance = _base_provenance(
        inputs=inputs,
        selection_contract=selection_contract,
        numerical_policy=numerical_policy,
        material_context=material_context,
        adequacy_policy=adequacy_policy,
        extra_refs=(
            *pmm.provenance_refs,
            *(
                ref
                for required in requirements
                for ref in required.source_refs
            ),
        ),
    )

    return ColumnCandidateAdequacyPopulation(
        component_id=inputs.component_id,
        status=population_status,
        blockers=(),
        candidate_ids=candidate_ids,
        requirement_ids=requirement_ids,
        demand_state_ids=state_ids,
        expected_required_area_decision_count=(
            len(candidate_ids) * len(requirement_ids)
        ),
        expected_pmm_decision_count=(
            len(candidate_ids) * len(state_ids)
        ),
        required_area_rows=tuple(area_rows),
        pmm_rows=tuple(pmm_rows),
        candidate_assessments=tuple(
            candidate_assessments
        ),
        adequate_candidate_count=adequate_count,
        inadequate_candidate_count=inadequate_count,
        unresolved_candidate_count=unresolved_count,
        adequacy_policy_id=adequacy_policy.policy_id,
        adequacy_policy_version=(
            adequacy_policy.policy_version
        ),
        adequacy_policy_fingerprint=(
            adequacy_policy.policy_fingerprint
        ),
        adequacy_authority_binding_ref=(
            adequacy_policy.authority_binding_ref
        ),
        adequacy_implementation_fingerprint=(
            adequacy_policy.implementation_fingerprint
        ),
        numerical_policy_fingerprint=(
            numerical_policy.policy_fingerprint
        ),
        material_context_ref=material_context.binding_ref,
        model_fingerprint=(
            fresh_contract.model_fingerprint
        ),
        evidence_epoch_id=(
            fresh_contract.evidence_epoch_id
        ),
        provenance_refs=provenance,
    )


__all__ = [
    "AUTHORITY",
    "BLOCKED",
    "BLOCK_GEOMETRY_BINDING",
    "BLOCK_P8A_COMPONENT",
    "BLOCK_PMM_ASSESSMENT",
    "BLOCK_PMM_CONTEXT",
    "BLOCK_SELECTION_CONTRACT",
    "COMPLETE",
    "COMPLETE_WITH_UNRESOLVED",
    "CandidateAdequacyAssessment",
    "CandidatePmmAdequacyAssessment",
    "CandidateRequiredAreaAssessment",
    "ColumnCandidateAdequacyError",
    "ColumnCandidateAdequacyPopulation",
    "evaluate_column_candidate_adequacy_population",
]
