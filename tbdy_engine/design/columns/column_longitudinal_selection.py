"""FND-COL-4C2B canonical column longitudinal-rebar selection.

This module performs no independent structural-capacity calculation.

It:
- rebuilds the current COL-4A selection contract;
- rebuilds the complete COL-4C1B candidate-adequacy population;
- rejects any unresolved candidate before optimization;
- binds the reviewed COL-4C2A ranking authority;
- ranks every proven-adequate candidate;
- emits the rank-one exact FND1 geometry candidate.

The legacy VS6 first-eligible selector is intentionally not imported.
Legacy production cutover is deferred to COL-4D.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Sequence

from tbdy_engine.design.columns.column_candidate_adequacy import (
    CANDIDATE_ADEQUATE,
    CandidateAdequacyAssessment,
    ColumnCandidateAdequacyPopulation,
    evaluate_column_candidate_adequacy_population,
)
from tbdy_engine.design.columns.column_longitudinal_ranking_authority import (
    ColumnLongitudinalRankingAuthorityError,
    ColumnLongitudinalRankingCandidate,
    ColumnLongitudinalRankingKey,
    ValidatedColumnLongitudinalRankingPolicy,
    authorize_column_longitudinal_ranking_policy,
    ranking_key_for_candidate,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionContract,
    ColumnLongitudinalSelectionInputs,
    reconcile_column_longitudinal_selection_contract,
)
from tbdy_engine.design.columns.column_pmm_assessment import (
    ColumnPmmMaterialContextBinding,
    candidate_geometry_binding_fingerprint,
)
from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarGeometryCandidate,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    ValidatedCandidateAdequacyPolicy,
)
from tbdy_engine.regulatory.column_pmm_authority import (
    ValidatedPmmNumericalPolicy,
)


AUTHORITY = "FND_COL_4_CANONICAL_LONGITUDINAL_SELECTION"
ENGINE_SELECTED_REBAR_AUTHORITY = "ENGINE_SELECTED_REBAR"

STATUS_SELECTED = "SELECTED"
STATUS_BLOCKED_SELECTION_CONTRACT = (
    "BLOCKED_SELECTION_CONTRACT"
)
STATUS_BLOCKED_RANKING_POLICY = (
    "BLOCKED_RANKING_POLICY"
)
STATUS_BLOCKED_ADEQUACY_POPULATION = (
    "BLOCKED_ADEQUACY_POPULATION"
)
STATUS_BLOCKED_UNRESOLVED_CANDIDATES = (
    "BLOCKED_UNRESOLVED_CANDIDATES"
)
STATUS_NO_ADEQUATE_CANDIDATE = (
    "NO_ADEQUATE_CANDIDATE"
)
STATUS_BLOCKED_GEOMETRY_BINDING = (
    "BLOCKED_GEOMETRY_BINDING"
)

BLOCK_SELECTION_CONTRACT = (
    "SELECTION_CONTRACT_NOT_RECONCILED"
)
BLOCK_RANKING_POLICY = (
    "RANKING_POLICY_NOT_REVIEWED"
)
BLOCK_ADEQUACY_POPULATION = (
    "CANDIDATE_ADEQUACY_POPULATION_NOT_COMPLETE"
)
BLOCK_UNRESOLVED_CANDIDATES = (
    "UNRESOLVED_CANDIDATES_PREVENT_OPTIMIZATION"
)
BLOCK_NO_ADEQUATE_CANDIDATE = (
    "NO_PROVEN_ADEQUATE_CANDIDATE"
)
BLOCK_GEOMETRY_BINDING = (
    "ADEQUATE_CANDIDATE_GEOMETRY_BINDING_MISMATCH"
)


class ColumnLongitudinalCanonicalSelectionError(
    ValueError
):
    """Malformed canonical longitudinal-selection artifact."""


def _text(
    value: object,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnLongitudinalCanonicalSelectionError(
            f"{label} must be a nonblank canonical string"
        )

    return value


def _stable_id(
    prefix: str,
    payload: object,
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return (
        prefix
        + hashlib.sha256(encoded).hexdigest()
    )


def _refs(
    values: Sequence[str],
) -> tuple[str, ...]:
    refs = tuple(
        sorted(
            {
                _text(value, "provenance_ref")
                for value in values
            }
        )
    )

    if not refs:
        raise ColumnLongitudinalCanonicalSelectionError(
            "provenance_refs must be nonempty"
        )

    return refs


def _adequacy_ref(
    assessment: CandidateAdequacyAssessment,
) -> str:
    return _stable_id(
        "candidate-adequacy:sha256:",
        {
            "candidate_id": assessment.candidate_id,
            "candidate_geometry_fingerprint": (
                assessment.candidate_geometry_fingerprint
            ),
            "candidate_as_mm2": str(
                assessment.candidate_as_mm2
            ),
            "status": assessment.status,
            "required_area_decision_ids": list(
                assessment.required_area_decision_ids
            ),
            "pmm_decision_ids": list(
                assessment.pmm_decision_ids
            ),
            "policy_fingerprint": (
                assessment.policy_fingerprint
            ),
        },
    )


@dataclass(frozen=True, slots=True)
class ColumnCandidateRankingAssessment:
    candidate_id: str
    candidate_geometry_fingerprint: str
    candidate_adequacy_ref: str
    rank: int
    ranking_key: ColumnLongitudinalRankingKey
    ranking_policy_fingerprint: str
    authority: str = (
        "FND_COL_4_REVIEWED_CANDIDATE_RANKING"
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.rank, bool)
            or not isinstance(self.rank, int)
            or self.rank <= 0
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "rank must be a positive integer"
                )
            )

        if (
            self.ranking_key.stable_candidate_id
            != self.candidate_id
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "ranking key candidate identity mismatch"
                )
            )


@dataclass(frozen=True, slots=True)
class CanonicalEngineSelectedRebar:
    selected_rebar_ref: str
    component_id: str
    candidate_id: str
    candidate_geometry_fingerprint: str
    candidate_adequacy_ref: str
    selected_candidate: ColumnRebarGeometryCandidate
    as_total_mm2: Decimal
    rank: int
    ranking_key: ColumnLongitudinalRankingKey
    required_area_decision_ids: tuple[str, ...]
    pmm_decision_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    demand_state_ids: tuple[str, ...]
    ranking_policy_id: str
    ranking_policy_version: str
    ranking_policy_fingerprint: str
    ranking_policy_review_ref: str
    adequacy_policy_fingerprint: str
    numerical_policy_fingerprint: str
    material_context_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    provenance_refs: tuple[str, ...]
    authority: str = ENGINE_SELECTED_REBAR_AUTHORITY

    def __post_init__(self) -> None:
        if self.rank != 1:
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "selected reinforcement must have rank 1"
                )
            )

        if (
            self.selected_candidate.candidate_id
            != self.candidate_id
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "selected candidate identity mismatch"
                )
            )

        if (
            Decimal(
                str(
                    self.selected_candidate
                    .as_total_mm2
                )
            )
            != self.as_total_mm2
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "selected candidate As mismatch"
                )
            )

        if (
            self.ranking_key.stable_candidate_id
            != self.candidate_id
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "selected ranking key identity mismatch"
                )
            )

        if (
            not self.required_area_decision_ids
            or not self.pmm_decision_ids
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "selected rebar requires complete "
                    "area and PMM decision provenance"
                )
            )

        if (
            self.authority
            != ENGINE_SELECTED_REBAR_AUTHORITY
        ):
            raise (
                ColumnLongitudinalCanonicalSelectionError(
                    "invalid selected-rebar authority"
                )
            )


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalCanonicalSelectionResult:
    component_id: str
    status: str
    blockers: tuple[str, ...]
    selection_contract: (
        ColumnLongitudinalSelectionContract | None
    )
    adequacy_population: (
        ColumnCandidateAdequacyPopulation | None
    )
    ranking_policy: (
        ValidatedColumnLongitudinalRankingPolicy | None
    )
    ranking_rows: tuple[
        ColumnCandidateRankingAssessment, ...
    ]
    selected_rebar: CanonicalEngineSelectedRebar | None
    authority: str = AUTHORITY

    @property
    def selected(self) -> bool:
        return (
            self.status == STATUS_SELECTED
            and self.selected_rebar is not None
        )

    def __post_init__(self) -> None:
        if self.status == STATUS_SELECTED:
            if self.blockers:
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "selected result may not carry blockers"
                    )
                )

            if (
                self.selection_contract is None
                or not self.selection_contract.reconciled
                or self.adequacy_population is None
                or not self.adequacy_population.complete
                or self.ranking_policy is None
                or self.selected_rebar is None
            ):
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "selected result is missing "
                        "canonical authority inputs"
                    )
                )

            if (
                self.adequacy_population
                .unresolved_candidate_count
                != 0
            ):
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "selection forbidden with "
                        "unresolved candidates"
                    )
                )

            if (
                len(self.ranking_rows)
                != self.adequacy_population
                .adequate_candidate_count
            ):
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "every adequate candidate "
                        "must be ranked exactly once"
                    )
                )

            ranks = tuple(
                row.rank
                for row in self.ranking_rows
            )

            if ranks != tuple(
                range(
                    1,
                    len(self.ranking_rows) + 1,
                )
            ):
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "ranking rows must have "
                        "contiguous canonical ranks"
                    )
                )

            if (
                not self.ranking_rows
                or self.ranking_rows[0].candidate_id
                != self.selected_rebar.candidate_id
            ):
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "selected candidate must be rank one"
                    )
                )

        else:
            if self.selected_rebar is not None:
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "non-selected result may not "
                        "publish selected reinforcement"
                    )
                )

            if self.ranking_rows:
                raise (
                    ColumnLongitudinalCanonicalSelectionError(
                        "blocked/non-selected result may "
                        "not publish partial ranking"
                    )
                )


def _blocked(
    *,
    component_id: str,
    status: str,
    blocker: str,
    selection_contract: (
        ColumnLongitudinalSelectionContract | None
    ) = None,
    adequacy_population: (
        ColumnCandidateAdequacyPopulation | None
    ) = None,
    ranking_policy: (
        ValidatedColumnLongitudinalRankingPolicy | None
    ) = None,
) -> ColumnLongitudinalCanonicalSelectionResult:
    return ColumnLongitudinalCanonicalSelectionResult(
        component_id=component_id,
        status=status,
        blockers=(blocker,),
        selection_contract=selection_contract,
        adequacy_population=adequacy_population,
        ranking_policy=ranking_policy,
        ranking_rows=(),
        selected_rebar=None,
    )


def select_canonical_column_longitudinal_rebar(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    numerical_policy: ValidatedPmmNumericalPolicy,
    material_context: ColumnPmmMaterialContextBinding,
    adequacy_policy: ValidatedCandidateAdequacyPolicy,
) -> ColumnLongitudinalCanonicalSelectionResult:
    """Select rank-one reinforcement only from complete proven adequacy."""

    if not isinstance(
        inputs,
        ColumnLongitudinalSelectionInputs,
    ):
        raise TypeError(
            "inputs must be "
            "ColumnLongitudinalSelectionInputs"
        )

    fresh_contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    if not fresh_contract.reconciled:
        return _blocked(
            component_id=inputs.component_id,
            status=(
                STATUS_BLOCKED_SELECTION_CONTRACT
            ),
            blocker=BLOCK_SELECTION_CONTRACT,
            selection_contract=fresh_contract,
        )

    try:
        ranking_policy = (
            authorize_column_longitudinal_ranking_policy(
                inputs.policy
            )
        )
    except ColumnLongitudinalRankingAuthorityError:
        return _blocked(
            component_id=inputs.component_id,
            status=STATUS_BLOCKED_RANKING_POLICY,
            blocker=BLOCK_RANKING_POLICY,
            selection_contract=fresh_contract,
        )

    adequacy = (
        evaluate_column_candidate_adequacy_population(
            inputs=inputs,
            selection_contract=fresh_contract,
            numerical_policy=numerical_policy,
            material_context=material_context,
            adequacy_policy=adequacy_policy,
        )
    )

    if not adequacy.complete:
        return _blocked(
            component_id=inputs.component_id,
            status=STATUS_BLOCKED_ADEQUACY_POPULATION,
            blocker=BLOCK_ADEQUACY_POPULATION,
            selection_contract=fresh_contract,
            adequacy_population=adequacy,
            ranking_policy=ranking_policy,
        )

    if adequacy.unresolved_candidate_count != 0:
        return _blocked(
            component_id=inputs.component_id,
            status=(
                STATUS_BLOCKED_UNRESOLVED_CANDIDATES
            ),
            blocker=BLOCK_UNRESOLVED_CANDIDATES,
            selection_contract=fresh_contract,
            adequacy_population=adequacy,
            ranking_policy=ranking_policy,
        )

    adequate = tuple(
        item
        for item in adequacy.candidate_assessments
        if item.status == CANDIDATE_ADEQUATE
    )

    if not adequate:
        return _blocked(
            component_id=inputs.component_id,
            status=STATUS_NO_ADEQUATE_CANDIDATE,
            blocker=BLOCK_NO_ADEQUATE_CANDIDATE,
            selection_contract=fresh_contract,
            adequacy_population=adequacy,
            ranking_policy=ranking_policy,
        )

    candidates = {
        candidate.candidate_id: candidate
        for candidate
        in inputs.layout_authority.eligible_candidates
    }

    if len(candidates) != len(
        inputs.layout_authority.eligible_candidates
    ):
        return _blocked(
            component_id=inputs.component_id,
            status=STATUS_BLOCKED_GEOMETRY_BINDING,
            blocker=BLOCK_GEOMETRY_BINDING,
            selection_contract=fresh_contract,
            adequacy_population=adequacy,
            ranking_policy=ranking_policy,
        )

    requirement = inputs.layout_authority.requirement

    ranked_payload: list[
        tuple[
            ColumnLongitudinalRankingKey,
            CandidateAdequacyAssessment,
            ColumnRebarGeometryCandidate,
            str,
        ]
    ] = []

    for assessment in adequate:
        candidate = candidates.get(
            assessment.candidate_id
        )

        if candidate is None:
            return _blocked(
                component_id=inputs.component_id,
                status=STATUS_BLOCKED_GEOMETRY_BINDING,
                blocker=BLOCK_GEOMETRY_BINDING,
                selection_contract=fresh_contract,
                adequacy_population=adequacy,
                ranking_policy=ranking_policy,
            )

        geometry_fingerprint = (
            candidate_geometry_binding_fingerprint(
                component_id=inputs.component_id,
                section_id=requirement.section_id,
                width_mm=requirement.width_mm,
                depth_mm=requirement.depth_mm,
                candidate=candidate,
                layout_authority_binding_ref=(
                    inputs.layout_authority
                    .authority_binding_ref
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
        )

        if (
            geometry_fingerprint
            != assessment
            .candidate_geometry_fingerprint
            or Decimal(
                str(candidate.as_total_mm2)
            )
            != assessment.candidate_as_mm2
        ):
            return _blocked(
                component_id=inputs.component_id,
                status=STATUS_BLOCKED_GEOMETRY_BINDING,
                blocker=BLOCK_GEOMETRY_BINDING,
                selection_contract=fresh_contract,
                adequacy_population=adequacy,
                ranking_policy=ranking_policy,
            )

        ranking_candidate = (
            ColumnLongitudinalRankingCandidate(
                candidate_id=candidate.candidate_id,
                as_total_mm2=(
                    assessment.candidate_as_mm2
                ),
                bar_count=candidate.bar_count,
                bar_diameter_mm=Decimal(
                    str(candidate.bar_diameter_mm)
                ),
            )
        )

        key = ranking_key_for_candidate(
            policy=ranking_policy,
            candidate=ranking_candidate,
        )

        ranked_payload.append(
            (
                key,
                assessment,
                candidate,
                geometry_fingerprint,
            )
        )

    ranked_payload.sort(
        key=lambda item: item[0]
    )

    ranking_rows = tuple(
        ColumnCandidateRankingAssessment(
            candidate_id=assessment.candidate_id,
            candidate_geometry_fingerprint=(
                geometry_fingerprint
            ),
            candidate_adequacy_ref=(
                _adequacy_ref(assessment)
            ),
            rank=index,
            ranking_key=key,
            ranking_policy_fingerprint=(
                ranking_policy.policy_fingerprint
            ),
        )
        for index, (
            key,
            assessment,
            _candidate,
            geometry_fingerprint,
        ) in enumerate(
            ranked_payload,
            start=1,
        )
    )

    (
        selected_key,
        selected_assessment,
        selected_candidate,
        selected_geometry_fingerprint,
    ) = ranked_payload[0]

    selected_adequacy_ref = _adequacy_ref(
        selected_assessment
    )

    selected_ref = _stable_id(
        "engine-selected-rebar:sha256:",
        {
            "component_id": inputs.component_id,
            "candidate_id": (
                selected_candidate.candidate_id
            ),
            "candidate_geometry_fingerprint": (
                selected_geometry_fingerprint
            ),
            "candidate_adequacy_ref": (
                selected_adequacy_ref
            ),
            "ranking_key": {
                "total_as_mm2": str(
                    selected_key.total_as_mm2
                ),
                "bar_count": (
                    selected_key.bar_count
                ),
                "bar_diameter_mm": str(
                    selected_key.bar_diameter_mm
                ),
                "stable_candidate_id": (
                    selected_key
                    .stable_candidate_id
                ),
            },
            "ranking_policy_fingerprint": (
                ranking_policy.policy_fingerprint
            ),
            "adequacy_policy_fingerprint": (
                adequacy.adequacy_policy_fingerprint
            ),
            "numerical_policy_fingerprint": (
                adequacy.numerical_policy_fingerprint
            ),
            "material_context_ref": (
                adequacy.material_context_ref
            ),
            "requirement_ids": list(
                adequacy.requirement_ids
            ),
            "demand_state_ids": list(
                adequacy.demand_state_ids
            ),
            "required_area_decision_ids": list(
                selected_assessment
                .required_area_decision_ids
            ),
            "pmm_decision_ids": list(
                selected_assessment
                .pmm_decision_ids
            ),
            "model_fingerprint": (
                adequacy.model_fingerprint
            ),
            "evidence_epoch_id": (
                adequacy.evidence_epoch_id
            ),
        },
    )

    provenance = _refs(
        (
            *fresh_contract.provenance_refs,
            *adequacy.provenance_refs,
            ranking_policy.input_review_ref,
            ranking_policy.binding_review_ref,
            ranking_policy.policy_fingerprint,
            selected_adequacy_ref,
            *selected_assessment
            .required_area_decision_ids,
            *selected_assessment.pmm_decision_ids,
        )
    )

    selected_rebar = CanonicalEngineSelectedRebar(
        selected_rebar_ref=selected_ref,
        component_id=inputs.component_id,
        candidate_id=selected_candidate.candidate_id,
        candidate_geometry_fingerprint=(
            selected_geometry_fingerprint
        ),
        candidate_adequacy_ref=(
            selected_adequacy_ref
        ),
        selected_candidate=selected_candidate,
        as_total_mm2=(
            selected_assessment.candidate_as_mm2
        ),
        rank=1,
        ranking_key=selected_key,
        required_area_decision_ids=(
            selected_assessment
            .required_area_decision_ids
        ),
        pmm_decision_ids=(
            selected_assessment.pmm_decision_ids
        ),
        requirement_ids=adequacy.requirement_ids,
        demand_state_ids=adequacy.demand_state_ids,
        ranking_policy_id=ranking_policy.policy_id,
        ranking_policy_version=(
            ranking_policy.policy_version
        ),
        ranking_policy_fingerprint=(
            ranking_policy.policy_fingerprint
        ),
        ranking_policy_review_ref=(
            ranking_policy.binding_review_ref
        ),
        adequacy_policy_fingerprint=(
            adequacy.adequacy_policy_fingerprint
        ),
        numerical_policy_fingerprint=(
            adequacy.numerical_policy_fingerprint
        ),
        material_context_ref=(
            adequacy.material_context_ref
        ),
        model_fingerprint=adequacy.model_fingerprint,
        evidence_epoch_id=adequacy.evidence_epoch_id,
        provenance_refs=provenance,
    )

    return ColumnLongitudinalCanonicalSelectionResult(
        component_id=inputs.component_id,
        status=STATUS_SELECTED,
        blockers=(),
        selection_contract=fresh_contract,
        adequacy_population=adequacy,
        ranking_policy=ranking_policy,
        ranking_rows=ranking_rows,
        selected_rebar=selected_rebar,
    )


__all__ = [
    "AUTHORITY",
    "BLOCK_ADEQUACY_POPULATION",
    "BLOCK_GEOMETRY_BINDING",
    "BLOCK_NO_ADEQUATE_CANDIDATE",
    "BLOCK_RANKING_POLICY",
    "BLOCK_SELECTION_CONTRACT",
    "BLOCK_UNRESOLVED_CANDIDATES",
    "CanonicalEngineSelectedRebar",
    "ColumnCandidateRankingAssessment",
    "ColumnLongitudinalCanonicalSelectionError",
    "ColumnLongitudinalCanonicalSelectionResult",
    "ENGINE_SELECTED_REBAR_AUTHORITY",
    "STATUS_BLOCKED_ADEQUACY_POPULATION",
    "STATUS_BLOCKED_GEOMETRY_BINDING",
    "STATUS_BLOCKED_RANKING_POLICY",
    "STATUS_BLOCKED_SELECTION_CONTRACT",
    "STATUS_BLOCKED_UNRESOLVED_CANDIDATES",
    "STATUS_NO_ADEQUATE_CANDIDATE",
    "STATUS_SELECTED",
    "select_canonical_column_longitudinal_rebar",
]
