"""FND-COL-4B2 exhaustive rectangular-column PMM numerical assessment.

This module is orchestration over already-authorized inputs:

- reconciled FND-COL-4 longitudinal-selection context;
- FND-COL-1 regulatorily eligible rectangular layouts;
- FND-COL-2 canonical concurrent demand states;
- FND-COL-4B1 source-bound PMM kernel and numerical policy;
- explicit reviewed material context.

It evaluates every candidate x every canonical demand state exactly once.

It deliberately does NOT:
- decide PMM compliance;
- compare utilization with an acceptance limit;
- classify a candidate as suitable/eligible for selection;
- rank candidates;
- emit canonical selected-rebar authority;
- acquire ETABS evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Sequence

from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionContract,
    ColumnLongitudinalSelectionInputs,
)
from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarGeometryCandidate,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.section_capacity import (
    ColumnSectionMaterial,
    build_interaction_envelope_at_axial_force,
    radial_moment_capacity,
)
from tbdy_engine.regulatory.column_pmm_authority import (
    FND_COL_4_PMM_RULE_ID,
    ValidatedPmmNumericalPolicy,
)


AUTHORITY = "FND_COL_4_PMM_NUMERICAL_ASSESSMENT"

COMPLETE = "COMPLETE_NUMERICAL_ASSESSMENT"
COMPLETE_WITH_UNRESOLVED = (
    "COMPLETE_WITH_UNRESOLVED_NUMERICAL_CAPACITY"
)

BLOCKED_SELECTION_CONTRACT = "SELECTION_CONTRACT_NOT_RECONCILED"
BLOCKED_MATERIAL_CONTEXT = "PMM_MATERIAL_CONTEXT_MISMATCH"
BLOCKED_NUMERICAL_POLICY_DOMAIN = "PMM_NUMERICAL_POLICY_DOMAIN_UNSUPPORTED"

ROW_PROVEN = "PROVEN_NUMERICAL_CAPACITY"
ROW_PROVEN_ZERO_MOMENT = "PROVEN_ZERO_MOMENT_NUMERICAL_STATE"
ROW_OUTSIDE_AXIAL = "OUTSIDE_AXIAL_CAPACITY"
ROW_RADIAL_UNRESOLVED = "RADIAL_CAPACITY_UNRESOLVED"

MATERIAL_BINDING_KIND = "REVIEWED_PMM_MATERIAL_CONTEXT"


class ColumnPmmAssessmentError(ValueError):
    """Malformed COL-4B2 numerical-assessment input."""


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnPmmAssessmentError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _refs(
    values: Sequence[str],
    label: str,
) -> tuple[str, ...]:
    result = tuple(
        sorted({_text(value, label) for value in values})
    )
    if not result:
        raise ColumnPmmAssessmentError(
            f"{label} must be nonempty"
        )
    return result


def _float(value: object, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnPmmAssessmentError(
            f"{label} must be finite numeric"
        )
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnPmmAssessmentError(
            f"{label} must be finite numeric"
        ) from exc
    if not math.isfinite(result):
        raise ColumnPmmAssessmentError(
            f"{label} must be finite"
        )
    return result


def _canonical_float(value: float) -> str:
    result = _float(value, "fingerprint numeric value")
    if result == 0.0:
        return "0"
    return format(result, ".17g")


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def candidate_geometry_binding_fingerprint(
    *,
    component_id: str,
    section_id: str,
    width_mm: float,
    depth_mm: float,
    candidate: ColumnRebarGeometryCandidate,
    layout_authority_binding_ref: str,
    layout_implementation_fingerprint: str,
    model_fingerprint: str,
    evidence_epoch_id: str,
) -> str:
    """Bind the exact FND-COL-1 geometry consumed by PMM assessment."""

    if not isinstance(
        candidate,
        ColumnRebarGeometryCandidate,
    ):
        raise TypeError(
            "candidate must be ColumnRebarGeometryCandidate"
        )

    payload = {
        "component_id": _text(
            component_id,
            "component_id",
        ),
        "section_id": _text(
            section_id,
            "section_id",
        ),
        "width_mm": _canonical_float(width_mm),
        "depth_mm": _canonical_float(depth_mm),
        "layout_authority_binding_ref": _text(
            layout_authority_binding_ref,
            "layout_authority_binding_ref",
        ),
        "layout_implementation_fingerprint": _text(
            layout_implementation_fingerprint,
            "layout_implementation_fingerprint",
        ),
        "model_fingerprint": _text(
            model_fingerprint,
            "model_fingerprint",
        ),
        "evidence_epoch_id": _text(
            evidence_epoch_id,
            "evidence_epoch_id",
        ),
        "candidate": {
            "candidate_id": _text(
                candidate.candidate_id,
                "candidate_id",
            ),
            "bar_diameter_mm": _canonical_float(
                candidate.bar_diameter_mm
            ),
            "n_bars_dir2": candidate.n_bars_dir2,
            "n_bars_dir3": candidate.n_bars_dir3,
            "as_total_mm2": _canonical_float(
                candidate.as_total_mm2
            ),
            "rho": _canonical_float(candidate.rho),
            "min_clear_spacing_mm": _canonical_float(
                candidate.min_clear_spacing_mm
            ),
            "bars": [
                {
                    "index": bar.index,
                    "x2_mm": _canonical_float(bar.x2_mm),
                    "x3_mm": _canonical_float(bar.x3_mm),
                    "diameter_mm": _canonical_float(
                        bar.diameter_mm
                    ),
                    "area_mm2": _canonical_float(
                        bar.area_mm2
                    ),
                }
                for bar in candidate.bars
            ],
        },
    }

    return _stable_id(
        "candidate-geometry-binding:sha256:",
        payload,
    )


@dataclass(frozen=True, slots=True)
class ColumnPmmMaterialContextBinding:
    """Reviewed material context, not a regulatory-strength derivation.

    ``fck`` may originate from factual ETABS material evidence. ``fcd`` and
    ``fyd`` remain explicitly reviewed project/design-basis values in this cut.
    COL-4B2 does not derive them and does not silently default them.
    """

    component_id: str
    section_id: str
    material_name: str
    material: ColumnSectionMaterial
    model_fingerprint: str
    evidence_epoch_id: str
    section_material_binding_ref: str
    concrete_strength_source_refs: tuple[str, ...]
    concrete_design_strength_review_refs: tuple[str, ...]
    steel_design_strength_review_refs: tuple[str, ...]
    binding_ref: str = ""
    binding_kind: str = MATERIAL_BINDING_KIND

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "section_id",
            "material_name",
            "model_fingerprint",
            "evidence_epoch_id",
            "section_material_binding_ref",
        ):
            object.__setattr__(
                self,
                name,
                _text(getattr(self, name), name),
            )

        if not isinstance(
            self.material,
            ColumnSectionMaterial,
        ):
            raise TypeError(
                "material must be ColumnSectionMaterial"
            )

        object.__setattr__(
            self,
            "concrete_strength_source_refs",
            _refs(
                self.concrete_strength_source_refs,
                "concrete_strength_source_ref",
            ),
        )
        object.__setattr__(
            self,
            "concrete_design_strength_review_refs",
            _refs(
                self.concrete_design_strength_review_refs,
                "concrete_design_strength_review_ref",
            ),
        )
        object.__setattr__(
            self,
            "steel_design_strength_review_refs",
            _refs(
                self.steel_design_strength_review_refs,
                "steel_design_strength_review_ref",
            ),
        )

        if self.binding_kind != MATERIAL_BINDING_KIND:
            raise ColumnPmmAssessmentError(
                "material binding kind mismatch"
            )

        payload = {
            "component_id": self.component_id,
            "section_id": self.section_id,
            "material_name": self.material_name,
            "fck_mpa": _canonical_float(
                self.material.fck_mpa
            ),
            "fcd_mpa": _canonical_float(
                self.material.fcd_mpa
            ),
            "fyd_mpa": _canonical_float(
                self.material.fyd_mpa
            ),
            "k1": _canonical_float(
                float(self.material.k1)
            ),
            "es_mpa": _canonical_float(
                self.material.es_mpa
            ),
            "epsilon_cu": _canonical_float(
                self.material.epsilon_cu
            ),
            "model_fingerprint": self.model_fingerprint,
            "evidence_epoch_id": self.evidence_epoch_id,
            "section_material_binding_ref": (
                self.section_material_binding_ref
            ),
            "concrete_strength_source_refs": list(
                self.concrete_strength_source_refs
            ),
            "concrete_design_strength_review_refs": list(
                self.concrete_design_strength_review_refs
            ),
            "steel_design_strength_review_refs": list(
                self.steel_design_strength_review_refs
            ),
        }

        expected = _stable_id(
            "pmm-material-context:sha256:",
            payload,
        )

        if self.binding_ref not in ("", expected):
            raise ColumnPmmAssessmentError(
                "material binding_ref does not match "
                "deterministic material context"
            )

        object.__setattr__(
            self,
            "binding_ref",
            expected,
        )


@dataclass(frozen=True, slots=True)
class CandidatePmmDemandAssessment:
    assessment_id: str
    component_id: str
    candidate_id: str
    candidate_geometry_fingerprint: str
    state_id: str
    nd_compression_n: float
    m2_nmm: float
    m3_nmm: float
    moment_magnitude_nmm: float
    envelope_status: str
    radial_status: str | None
    radial_capacity_nmm: float | None
    utilization: float | None
    numerical_status: str
    numerical_policy_fingerprint: str
    material_context_ref: str
    authority: str = AUTHORITY

    def __post_init__(self) -> None:
        fingerprint = _text(
            self.candidate_geometry_fingerprint,
            "candidate_geometry_fingerprint",
        )
        if not fingerprint.startswith(
            "candidate-geometry-binding:sha256:"
        ):
            raise ColumnPmmAssessmentError(
                "candidate geometry fingerprint has "
                "unexpected authority namespace"
            )
        object.__setattr__(
            self,
            "candidate_geometry_fingerprint",
            fingerprint,
        )

    @property
    def numerically_resolved(self) -> bool:
        return self.numerical_status in {
            ROW_PROVEN,
            ROW_PROVEN_ZERO_MOMENT,
        }


@dataclass(frozen=True, slots=True)
class CandidatePmmAssessment:
    candidate_id: str
    candidate_geometry_fingerprint: str
    demand_state_ids: tuple[str, ...]
    assessment_ids: tuple[str, ...]
    expected_demand_count: int
    produced_demand_count: int
    resolved_count: int
    unresolved_count: int

    def __post_init__(self) -> None:
        fingerprint = _text(
            self.candidate_geometry_fingerprint,
            "candidate_geometry_fingerprint",
        )
        if not fingerprint.startswith(
            "candidate-geometry-binding:sha256:"
        ):
            raise ColumnPmmAssessmentError(
                "candidate summary geometry fingerprint has "
                "unexpected authority namespace"
            )
        object.__setattr__(
            self,
            "candidate_geometry_fingerprint",
            fingerprint,
        )

        demand_ids = tuple(self.demand_state_ids)
        assessment_ids = tuple(self.assessment_ids)

        if len(demand_ids) != len(set(demand_ids)):
            raise ColumnPmmAssessmentError(
                "candidate summary demand ids must be unique"
            )

        if len(assessment_ids) != len(set(assessment_ids)):
            raise ColumnPmmAssessmentError(
                "candidate summary assessment ids must be unique"
            )

        if (
            self.expected_demand_count
            != len(demand_ids)
            or self.produced_demand_count
            != len(assessment_ids)
            or self.produced_demand_count
            != self.expected_demand_count
        ):
            raise ColumnPmmAssessmentError(
                "candidate PMM assessment accounting mismatch"
            )

        if (
            self.resolved_count
            + self.unresolved_count
            != self.produced_demand_count
        ):
            raise ColumnPmmAssessmentError(
                "candidate PMM resolution accounting mismatch"
            )


@dataclass(frozen=True, slots=True)
class ColumnPmmAssessmentPopulation:
    component_id: str
    status: str
    blockers: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    demand_state_ids: tuple[str, ...]
    expected_assessment_count: int
    assessment_rows: tuple[CandidatePmmDemandAssessment, ...]
    candidate_assessments: tuple[CandidatePmmAssessment, ...]
    resolved_row_count: int
    unresolved_row_count: int
    numerical_policy_id: str
    numerical_policy_version: str
    numerical_policy_fingerprint: str
    numerical_policy_authority_binding_ref: str
    material_context_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    provenance_refs: tuple[str, ...]
    authority: str = AUTHORITY

    @property
    def enumeration_complete(self) -> bool:
        return self.status in {
            COMPLETE,
            COMPLETE_WITH_UNRESOLVED,
        }

    def __post_init__(self) -> None:
        candidate_ids = tuple(self.candidate_ids)
        state_ids = tuple(self.demand_state_ids)
        rows = tuple(self.assessment_rows)
        summaries = tuple(self.candidate_assessments)

        if candidate_ids != tuple(sorted(candidate_ids)):
            raise ColumnPmmAssessmentError(
                "candidate_ids must be canonically sorted"
            )
        if state_ids != tuple(sorted(state_ids)):
            raise ColumnPmmAssessmentError(
                "demand_state_ids must be canonically sorted"
            )
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ColumnPmmAssessmentError(
                "candidate_ids must be unique"
            )
        if len(state_ids) != len(set(state_ids)):
            raise ColumnPmmAssessmentError(
                "demand_state_ids must be unique"
            )

        expected = len(candidate_ids) * len(state_ids)

        if self.expected_assessment_count != expected:
            raise ColumnPmmAssessmentError(
                "expected candidate x demand cardinality mismatch"
            )

        if self.enumeration_complete:
            if len(rows) != expected:
                raise ColumnPmmAssessmentError(
                    "complete PMM population must contain every "
                    "candidate x demand pair"
                )

            pairs = tuple(
                (row.candidate_id, row.state_id)
                for row in rows
            )

            if len(pairs) != len(set(pairs)):
                raise ColumnPmmAssessmentError(
                    "candidate x demand pair emitted more than once"
                )

            expected_pairs = {
                (candidate_id, state_id)
                for candidate_id in candidate_ids
                for state_id in state_ids
            }

            if set(pairs) != expected_pairs:
                raise ColumnPmmAssessmentError(
                    "PMM assessment pair population is incomplete"
                )

            if tuple(
                summary.candidate_id
                for summary in summaries
            ) != candidate_ids:
                raise ColumnPmmAssessmentError(
                    "candidate summaries do not exactly cover "
                    "candidate population"
                )

            summary_fingerprints = {
                summary.candidate_id:
                summary.candidate_geometry_fingerprint
                for summary in summaries
            }

            if any(
                row.candidate_geometry_fingerprint
                != summary_fingerprints.get(
                    row.candidate_id
                )
                for row in rows
            ):
                raise ColumnPmmAssessmentError(
                    "PMM row candidate geometry binding "
                    "does not match candidate summary"
                )

        elif rows or summaries:
            raise ColumnPmmAssessmentError(
                "blocked PMM population may not contain partial "
                "numerical assessments"
            )

        if (
            self.resolved_row_count
            + self.unresolved_row_count
            != len(rows)
        ):
            raise ColumnPmmAssessmentError(
                "population PMM resolution accounting mismatch"
            )


def _population_refs(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    policy: ValidatedPmmNumericalPolicy,
    material: ColumnPmmMaterialContextBinding,
) -> tuple[str, ...]:
    values = {
        inputs.layout_authority.authority_binding_ref,
        inputs.layout_authority.implementation_fingerprint,
        inputs.readiness_binding.readiness_ref,
        *inputs.readiness_binding.provenance_refs,
        *inputs.readiness_binding.readiness.source_refs,
        policy.authority_binding_ref,
        policy.implementation_fingerprint,
        policy.policy_fingerprint,
        policy.validated_domain_ref,
        *policy.validation_evidence_refs,
        policy.review_ref,
        *policy.source_claim_refs,
        *policy.source_review_refs,
        material.binding_ref,
        material.section_material_binding_ref,
        *material.concrete_strength_source_refs,
        *material.concrete_design_strength_review_refs,
        *material.steel_design_strength_review_refs,
    }

    return tuple(sorted(values))


def _blocked_population(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    policy: ValidatedPmmNumericalPolicy,
    material: ColumnPmmMaterialContextBinding,
    blockers: Sequence[str],
) -> ColumnPmmAssessmentPopulation:
    candidate_ids = tuple(
        sorted(
            candidate.candidate_id
            for candidate
            in inputs.layout_authority.eligible_candidates
        )
    )

    state_ids = tuple(
        sorted(
            state.state_id
            for state
            in inputs.readiness_binding.readiness.demand_states
        )
    )

    return ColumnPmmAssessmentPopulation(
        component_id=inputs.component_id,
        status="BLOCKED",
        blockers=tuple(dict.fromkeys(blockers)),
        candidate_ids=candidate_ids,
        demand_state_ids=state_ids,
        expected_assessment_count=(
            len(candidate_ids) * len(state_ids)
        ),
        assessment_rows=(),
        candidate_assessments=(),
        resolved_row_count=0,
        unresolved_row_count=0,
        numerical_policy_id=policy.policy_id,
        numerical_policy_version=policy.policy_version,
        numerical_policy_fingerprint=(
            policy.policy_fingerprint
        ),
        numerical_policy_authority_binding_ref=(
            policy.authority_binding_ref
        ),
        material_context_ref=material.binding_ref,
        model_fingerprint=(
            inputs.readiness_binding.model_fingerprint
        ),
        evidence_epoch_id=(
            inputs.readiness_binding.evidence_epoch_id
        ),
        provenance_refs=_population_refs(
            inputs=inputs,
            policy=policy,
            material=material,
        ),
    )



def assess_all_column_pmm_candidate_demands(
    *,
    inputs: ColumnLongitudinalSelectionInputs,
    selection_contract: ColumnLongitudinalSelectionContract,
    numerical_policy: ValidatedPmmNumericalPolicy,
    material_context: ColumnPmmMaterialContextBinding,
) -> ColumnPmmAssessmentPopulation:
    """Numerically assess every canonical candidate x demand pair exactly once."""

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

    if (
        numerical_policy.authority
        != "VALIDATED_PMM_NUMERICAL_POLICY"
        or numerical_policy.rule_id
        != FND_COL_4_PMM_RULE_ID.value
    ):
        raise ColumnPmmAssessmentError(
            "unrecognized PMM numerical-policy authority"
        )

    blockers: list[str] = []

    if (
        not selection_contract.reconciled
        or selection_contract.component_id
        != inputs.component_id
    ):
        blockers.append(
            BLOCKED_SELECTION_CONTRACT
        )

    requirement = inputs.layout_authority.requirement
    readiness_binding = inputs.readiness_binding

    candidate_ids = tuple(
        sorted(
            candidate.candidate_id
            for candidate
            in inputs.layout_authority.eligible_candidates
        )
    )

    if (
        candidate_ids
        != selection_contract.eligible_candidate_ids
    ):
        blockers.append(
            BLOCKED_SELECTION_CONTRACT
        )

    if (
        material_context.component_id
        != inputs.component_id
        or material_context.section_id
        != requirement.section_id
        or material_context.model_fingerprint
        != selection_contract.model_fingerprint
        or material_context.evidence_epoch_id
        != selection_contract.evidence_epoch_id
        or material_context.model_fingerprint
        != readiness_binding.model_fingerprint
        or material_context.evidence_epoch_id
        != readiness_binding.evidence_epoch_id
    ):
        blockers.append(
            BLOCKED_MATERIAL_CONTEXT
        )

    if (
        material_context.material.fck_mpa
        not in numerical_policy.supported_fck_mpa
    ):
        blockers.append(
            BLOCKED_NUMERICAL_POLICY_DOMAIN
        )

    states = tuple(
        sorted(
            readiness_binding.readiness.demand_states,
            key=lambda state: state.state_id,
        )
    )

    if not states:
        raise ColumnPmmAssessmentError(
            "canonical readiness contains no demand states"
        )

    if any(
        state.component_id != inputs.component_id
        for state in states
    ):
        raise ColumnPmmAssessmentError(
            "canonical demand population contains another "
            "component_id"
        )

    state_ids = tuple(
        state.state_id
        for state in states
    )

    if len(state_ids) != len(set(state_ids)):
        raise ColumnPmmAssessmentError(
            "canonical demand state ids must be unique"
        )

    candidates = tuple(
        sorted(
            inputs.layout_authority.eligible_candidates,
            key=lambda candidate: candidate.candidate_id,
        )
    )

    if not candidates:
        raise ColumnPmmAssessmentError(
            "reconciled selection context has no "
            "regulatorily eligible candidates"
        )

    if blockers:
        return _blocked_population(
            inputs=inputs,
            policy=numerical_policy,
            material=material_context,
            blockers=blockers,
        )

    width_mm = requirement.width_mm
    depth_mm = requirement.depth_mm

    candidate_geometry_fingerprints = {
        candidate.candidate_id:
        candidate_geometry_binding_fingerprint(
            component_id=inputs.component_id,
            section_id=requirement.section_id,
            width_mm=width_mm,
            depth_mm=depth_mm,
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
                readiness_binding.model_fingerprint
            ),
            evidence_epoch_id=(
                readiness_binding.evidence_epoch_id
            ),
        )
        for candidate in candidates
    }

    rows: list[CandidatePmmDemandAssessment] = []

    for candidate in candidates:
        for state in states:
            envelope = (
                build_interaction_envelope_at_axial_force(
                    width_mm=width_mm,
                    depth_mm=depth_mm,
                    bars=candidate.bars,
                    material=material_context.material,
                    target_n_compression_n=(
                        state.nd_compression_n
                    ),
                    angle_count=numerical_policy.angle_count,
                    axial_tolerance_n=(
                        numerical_policy.axial_tolerance_n
                    ),
                )
            )

            moment_magnitude = math.hypot(
                state.m2_nmm,
                state.m3_nmm,
            )

            radial_status: str | None = None
            capacity: float | None = None
            utilization: float | None = None

            if envelope.status != "PROVEN":
                numerical_status = ROW_OUTSIDE_AXIAL

            elif moment_magnitude <= 1e-12:
                numerical_status = ROW_PROVEN_ZERO_MOMENT
                utilization = 0.0

            else:
                radial = radial_moment_capacity(
                    envelope,
                    demand_m2_nmm=state.m2_nmm,
                    demand_m3_nmm=state.m3_nmm,
                )

                radial_status = radial.status

                if (
                    radial.status == "PROVEN"
                    and math.isfinite(
                        float(radial.capacity_nmm)
                    )
                    and radial.capacity_nmm > 0.0
                ):
                    capacity = float(
                        radial.capacity_nmm
                    )
                    utilization = (
                        moment_magnitude / capacity
                    )
                    numerical_status = ROW_PROVEN
                else:
                    numerical_status = (
                        ROW_RADIAL_UNRESOLVED
                    )

            assessment_id = _stable_id(
                "pmm-assessment:sha256:",
                {
                    "component_id": inputs.component_id,
                    "candidate_id": (
                        candidate.candidate_id
                    ),
                    "candidate_geometry_fingerprint": (
                        candidate_geometry_fingerprints[
                            candidate.candidate_id
                        ]
                    ),
                    "state_id": state.state_id,
                    "nd_compression_n": _canonical_float(
                        state.nd_compression_n
                    ),
                    "m2_nmm": _canonical_float(
                        state.m2_nmm
                    ),
                    "m3_nmm": _canonical_float(
                        state.m3_nmm
                    ),
                    "numerical_policy_fingerprint": (
                        numerical_policy.policy_fingerprint
                    ),
                    "material_context_ref": (
                        material_context.binding_ref
                    ),
                },
            )

            rows.append(
                CandidatePmmDemandAssessment(
                    assessment_id=assessment_id,
                    component_id=inputs.component_id,
                    candidate_id=candidate.candidate_id,
                    candidate_geometry_fingerprint=(
                        candidate_geometry_fingerprints[
                            candidate.candidate_id
                        ]
                    ),
                    state_id=state.state_id,
                    nd_compression_n=(
                        state.nd_compression_n
                    ),
                    m2_nmm=state.m2_nmm,
                    m3_nmm=state.m3_nmm,
                    moment_magnitude_nmm=(
                        moment_magnitude
                    ),
                    envelope_status=envelope.status,
                    radial_status=radial_status,
                    radial_capacity_nmm=capacity,
                    utilization=utilization,
                    numerical_status=numerical_status,
                    numerical_policy_fingerprint=(
                        numerical_policy.policy_fingerprint
                    ),
                    material_context_ref=(
                        material_context.binding_ref
                    ),
                )
            )

    rows.sort(
        key=lambda row: (
            row.candidate_id,
            row.state_id,
        )
    )

    summaries: list[CandidatePmmAssessment] = []

    for candidate in candidates:
        candidate_rows = tuple(
            row
            for row in rows
            if row.candidate_id
            == candidate.candidate_id
        )

        resolved_count = sum(
            row.numerically_resolved
            for row in candidate_rows
        )

        summaries.append(
            CandidatePmmAssessment(
                candidate_id=candidate.candidate_id,
                candidate_geometry_fingerprint=(
                    candidate_geometry_fingerprints[
                        candidate.candidate_id
                    ]
                ),
                demand_state_ids=tuple(
                    row.state_id
                    for row in candidate_rows
                ),
                assessment_ids=tuple(
                    row.assessment_id
                    for row in candidate_rows
                ),
                expected_demand_count=len(states),
                produced_demand_count=(
                    len(candidate_rows)
                ),
                resolved_count=resolved_count,
                unresolved_count=(
                    len(candidate_rows)
                    - resolved_count
                ),
            )
        )

    resolved_rows = sum(
        row.numerically_resolved
        for row in rows
    )
    unresolved_rows = len(rows) - resolved_rows

    status = (
        COMPLETE
        if unresolved_rows == 0
        else COMPLETE_WITH_UNRESOLVED
    )

    return ColumnPmmAssessmentPopulation(
        component_id=inputs.component_id,
        status=status,
        blockers=(),
        candidate_ids=tuple(
            candidate.candidate_id
            for candidate in candidates
        ),
        demand_state_ids=state_ids,
        expected_assessment_count=(
            len(candidates) * len(states)
        ),
        assessment_rows=tuple(rows),
        candidate_assessments=tuple(summaries),
        resolved_row_count=resolved_rows,
        unresolved_row_count=unresolved_rows,
        numerical_policy_id=(
            numerical_policy.policy_id
        ),
        numerical_policy_version=(
            numerical_policy.policy_version
        ),
        numerical_policy_fingerprint=(
            numerical_policy.policy_fingerprint
        ),
        numerical_policy_authority_binding_ref=(
            numerical_policy.authority_binding_ref
        ),
        material_context_ref=(
            material_context.binding_ref
        ),
        model_fingerprint=(
            readiness_binding.model_fingerprint
        ),
        evidence_epoch_id=(
            readiness_binding.evidence_epoch_id
        ),
        provenance_refs=_population_refs(
            inputs=inputs,
            policy=numerical_policy,
            material=material_context,
        ),
    )


__all__ = [
    "AUTHORITY",
    "BLOCKED_MATERIAL_CONTEXT",
    "BLOCKED_NUMERICAL_POLICY_DOMAIN",
    "BLOCKED_SELECTION_CONTRACT",
    "COMPLETE",
    "COMPLETE_WITH_UNRESOLVED",
    "CandidatePmmAssessment",
    "CandidatePmmDemandAssessment",
    "ColumnPmmAssessmentError",
    "ColumnPmmAssessmentPopulation",
    "ColumnPmmMaterialContextBinding",
    "MATERIAL_BINDING_KIND",
    "ROW_OUTSIDE_AXIAL",
    "ROW_PROVEN",
    "ROW_PROVEN_ZERO_MOMENT",
    "ROW_RADIAL_UNRESOLVED",
    "assess_all_column_pmm_candidate_demands",
    "candidate_geometry_binding_fingerprint",
]
