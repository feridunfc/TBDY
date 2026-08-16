"""Ndm-only result-selection authority for the first production result slice.

This module derives a requested Ndm engineering demand from immutable factual
Pier Forces evidence plus exact reviewed binding/policy truth. It never owns
regulatory capacity, ratios, applicability, PASS/FAIL, or ETABS acquisition.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.features.result_evidence import PIER_FORCE_IDENTITY_FIELDS, ResultRowEvidenceBundle

_NDM = "Ndm"
_N = "N"
_KN = "kN"
_TBDY_EQ_4_11_S_TARGET = 0.2


class NdmAvailability(StrEnum):
    RESOLVED = "RESOLVED"
    BLOCKED = "BLOCKED"
    NO_DATA = "NO_DATA"


def _nonblank(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    return value.strip()


def _frozen_float_map(values: Mapping[str, Any]) -> Mapping[str, float]:
    out: dict[str, float] = {}
    for key, value in dict(values or {}).items():
        name = _nonblank("coefficient identity", str(key))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Coefficient for {name} must be numeric")
        out[name] = float(value)
    return MappingProxyType(out)


def _frozen_nested_float_map(values: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Mapping[str, float]]:
    return MappingProxyType({str(key): _frozen_float_map(item) for key, item in dict(values or {}).items()})


def _tuple_text(name: str, values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(_nonblank(name, item) for item in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} values must be unique")
    return normalized


def _identity(row: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((field, row.get(field)) for field in PIER_FORCE_IDENTITY_FIELDS)


def _identity_sort_key(identity: tuple[tuple[str, Any], ...]) -> tuple[str, ...]:
    return tuple("<NONE>" if value is None else str(value) for _, value in identity)


def _row_sort_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return _identity_sort_key(_identity(row))


@dataclass(frozen=True, slots=True)
class EngineeringQuantityRequest:
    """Ndm-only engineering quantity request; not a generic request framework."""

    request_id: str
    component_id: str
    story: str
    pier: str
    quantity: str = _NDM
    canonical_unit: str = _N

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _nonblank("request_id", self.request_id))
        object.__setattr__(self, "component_id", _nonblank("component_id", self.component_id))
        object.__setattr__(self, "story", _nonblank("story", self.story))
        object.__setattr__(self, "pier", _nonblank("pier", self.pier))
        if self.quantity != _NDM:
            raise ValueError("B2 EngineeringQuantityRequest supports Ndm only")
        if self.canonical_unit != _N:
            raise ValueError("B2 Ndm canonical output unit must be N")


@dataclass(frozen=True, slots=True)
class ReviewedNdmLoadBinding:
    """Exact reviewed final-combination and constituent-case identity binding."""

    binding_id: str
    version: str
    final_combination_ids: tuple[str, ...]
    g_case_ids: tuple[str, ...]
    q_case_ids: tuple[str, ...]
    s_case_ids: tuple[str, ...]
    horizontal_e_case_ids: tuple[str, ...]
    vertical_e_case_ids: tuple[str, ...]
    baseline_coefficients_by_combination: Mapping[str, Mapping[str, float]]
    required_fixed_coefficients_by_combination: Mapping[str, Mapping[str, float]]
    final_case_type: str = "Combination"
    allowed_final_step_types: tuple[str, ...] = ("Max", "Min")
    allowed_locations: tuple[str, ...] = ("Top", "Bottom")
    static_case_type: str = "LinStatic"
    review_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", _nonblank("binding_id", self.binding_id))
        object.__setattr__(self, "version", _nonblank("binding version", self.version))
        for field_name in (
            "final_combination_ids", "g_case_ids", "q_case_ids", "s_case_ids",
            "horizontal_e_case_ids", "vertical_e_case_ids", "allowed_final_step_types", "allowed_locations",
        ):
            object.__setattr__(self, field_name, _tuple_text(field_name, getattr(self, field_name)))
        if not self.final_combination_ids:
            raise ValueError("ReviewedNdmLoadBinding requires at least one final combination")
        if not self.allowed_final_step_types or not self.allowed_locations:
            raise ValueError("ReviewedNdmLoadBinding requires explicit StepType and Location sets")
        groups = (
            self.g_case_ids, self.q_case_ids, self.s_case_ids,
            self.horizontal_e_case_ids, self.vertical_e_case_ids,
        )
        all_case_ids = tuple(item for group in groups for item in group)
        if len(all_case_ids) != len(set(all_case_ids)):
            raise ValueError("Reviewed Ndm G/Q/S/E case identity groups must be disjoint")
        baseline = _frozen_nested_float_map(self.baseline_coefficients_by_combination)
        fixed = _frozen_nested_float_map(self.required_fixed_coefficients_by_combination)
        if set(baseline) != set(self.final_combination_ids):
            raise ValueError("Baseline coefficient map must cover exactly the reviewed final combinations")
        if set(fixed) != set(self.final_combination_ids):
            raise ValueError("Fixed coefficient map must cover exactly the reviewed final combinations")
        expected_all = set(all_case_ids)
        expected_fixed = set((*self.g_case_ids, *self.horizontal_e_case_ids, *self.vertical_e_case_ids))
        for combo in self.final_combination_ids:
            if set(baseline[combo]) != expected_all:
                raise ValueError(f"Baseline coefficients for {combo} must cover the exact reviewed G/Q/S/E inventory")
            if set(fixed[combo]) != expected_fixed:
                raise ValueError(f"Fixed coefficients for {combo} must cover exactly reviewed G/E identities")
        object.__setattr__(self, "baseline_coefficients_by_combination", baseline)
        object.__setattr__(self, "required_fixed_coefficients_by_combination", fixed)
        object.__setattr__(self, "final_case_type", _nonblank("final_case_type", self.final_case_type))
        object.__setattr__(self, "static_case_type", _nonblank("static_case_type", self.static_case_type))
        object.__setattr__(self, "review_refs", tuple(str(item) for item in self.review_refs))


@dataclass(frozen=True, slots=True)
class ReviewedNdmPolicy:
    """Reviewed Ndm-only policy truth, including the manual TS498 decision boundary."""

    policy_id: str
    version: str
    ts498_decision: str
    q_target_coefficients: Mapping[str, float]
    s_target_coefficients: Mapping[str, float]
    unequal_q_interpretation_reviewed: bool
    linear_superposition_reviewed: bool
    regulatory_authority_ids: tuple[str, ...]
    review_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _nonblank("policy_id", self.policy_id))
        object.__setattr__(self, "version", _nonblank("policy version", self.version))
        if self.ts498_decision not in {"NOT_APPLICABLE", "RESOLVED", "UNRESOLVED"}:
            raise ValueError("ts498_decision must be NOT_APPLICABLE, RESOLVED, or UNRESOLVED")
        if not isinstance(self.unequal_q_interpretation_reviewed, bool):
            raise TypeError("unequal_q_interpretation_reviewed must be bool")
        if not isinstance(self.linear_superposition_reviewed, bool):
            raise TypeError("linear_superposition_reviewed must be bool")
        object.__setattr__(self, "q_target_coefficients", _frozen_float_map(self.q_target_coefficients))
        object.__setattr__(self, "s_target_coefficients", _frozen_float_map(self.s_target_coefficients))
        authority = tuple(_nonblank("regulatory_authority_id", item) for item in self.regulatory_authority_ids)
        if not authority:
            raise ValueError("ReviewedNdmPolicy requires regulatory authority IDs")
        object.__setattr__(self, "regulatory_authority_ids", authority)
        object.__setattr__(self, "review_refs", tuple(str(item) for item in self.review_refs))


@dataclass(frozen=True, slots=True)
class CorrectionTrace:
    case_id: str
    source_row_identity: tuple[tuple[str, Any], ...]
    raw_p: float
    source_unit: str
    canonical_p_n: float
    baseline_coefficient: float
    target_coefficient: float
    delta_coefficient: float
    delta_p_n: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_row_identity": dict(self.source_row_identity),
            "raw_p": self.raw_p,
            "source_unit": self.source_unit,
            "canonical_p_n": self.canonical_p_n,
            "baseline_coefficient": self.baseline_coefficient,
            "target_coefficient": self.target_coefficient,
            "delta_coefficient": self.delta_coefficient,
            "delta_p_n": self.delta_p_n,
        }


@dataclass(frozen=True, slots=True)
class NdmCandidateTrace:
    source_row_identity: tuple[tuple[str, Any], ...]
    final_combination_id: str
    story: str
    pier: str
    location: str
    step_type: Any
    step_number: Any
    raw_p: float
    source_unit: str
    canonical_p_n: float
    q_corrections: tuple[CorrectionTrace, ...]
    s_corrections: tuple[CorrectionTrace, ...]
    adjusted_p_n: float
    canonical_compression_n: float
    accepted: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_row_identity": dict(self.source_row_identity),
            "final_combination_id": self.final_combination_id,
            "Story": self.story,
            "Pier": self.pier,
            "Location": self.location,
            "StepType": self.step_type,
            "StepNumber": self.step_number,
            "raw_P": self.raw_p,
            "source_unit": self.source_unit,
            "canonical_P_N": self.canonical_p_n,
            "q_corrections": [item.as_dict() for item in self.q_corrections],
            "s_corrections": [item.as_dict() for item in self.s_corrections],
            "adjusted_P_N": self.adjusted_p_n,
            "canonical_compression_N": self.canonical_compression_n,
            "accepted": self.accepted,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SelectionTrace:
    request_id: str
    policy_id: str | None
    policy_version: str | None
    binding_id: str | None
    binding_version: str | None
    regulatory_authority_ids: tuple[str, ...]
    full_evidence: bool
    linear_superposition_reviewed: bool | None
    source_table: str | None
    source_unit: str | None
    candidate_rows: tuple[NdmCandidateTrace, ...] = ()
    governing_value_n: float | None = None
    governing_row_identities: tuple[tuple[tuple[str, Any], ...], ...] = ()
    availability: NdmAvailability = NdmAvailability.BLOCKED
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "binding_id": self.binding_id,
            "binding_version": self.binding_version,
            "regulatory_authority_ids": list(self.regulatory_authority_ids),
            "full_evidence": self.full_evidence,
            "linear_superposition_reviewed": self.linear_superposition_reviewed,
            "source_table": self.source_table,
            "source_unit": self.source_unit,
            "candidate_rows": [row.as_dict() for row in self.candidate_rows],
            "governing_value_n": self.governing_value_n,
            "governing_row_identities": [dict(identity) for identity in self.governing_row_identities],
            "availability": self.availability.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ResolvedNdmDemand:
    availability: NdmAvailability
    ndm_n: float | None
    unit: str
    trace: SelectionTrace
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.unit != _N:
            raise ValueError("Ndm demand output unit must be N")
        if self.availability == NdmAvailability.RESOLVED:
            if isinstance(self.ndm_n, bool) or not isinstance(self.ndm_n, (int, float)) or float(self.ndm_n) < 0:
                raise ValueError("Resolved Ndm demand requires non-negative ndm_n")
        elif self.ndm_n is not None:
            raise ValueError("Unresolved Ndm demand must not carry a numeric value")


def _trace(
    request: EngineeringQuantityRequest,
    *, binding: ReviewedNdmLoadBinding | None,
    policy: ReviewedNdmPolicy | None,
    bundle: ResultRowEvidenceBundle | None,
    availability: NdmAvailability,
    reason: str | None,
    source_unit: str | None = None,
    candidate_rows: Sequence[NdmCandidateTrace] = (),
    governing_value_n: float | None = None,
    governing_row_identities: Sequence[tuple[tuple[str, Any], ...]] = (),
) -> SelectionTrace:
    return SelectionTrace(
        request_id=request.request_id,
        policy_id=None if policy is None else policy.policy_id,
        policy_version=None if policy is None else policy.version,
        binding_id=None if binding is None else binding.binding_id,
        binding_version=None if binding is None else binding.version,
        regulatory_authority_ids=() if policy is None else policy.regulatory_authority_ids,
        full_evidence=bool(bundle is not None and bundle.is_full_capture),
        linear_superposition_reviewed=None if policy is None else policy.linear_superposition_reviewed,
        source_table=None if bundle is None else bundle.actual_table_name,
        source_unit=source_unit,
        candidate_rows=tuple(candidate_rows),
        governing_value_n=governing_value_n,
        governing_row_identities=tuple(governing_row_identities),
        availability=availability,
        reason=reason,
    )


def _result(
    request: EngineeringQuantityRequest,
    *, binding: ReviewedNdmLoadBinding | None,
    policy: ReviewedNdmPolicy | None,
    bundle: ResultRowEvidenceBundle | None,
    availability: NdmAvailability,
    reason: str | None,
    source_unit: str | None = None,
    candidate_rows: Sequence[NdmCandidateTrace] = (),
    governing_value_n: float | None = None,
    governing_row_identities: Sequence[tuple[tuple[str, Any], ...]] = (),
) -> ResolvedNdmDemand:
    trace = _trace(
        request, binding=binding, policy=policy, bundle=bundle,
        availability=availability, reason=reason, source_unit=source_unit,
        candidate_rows=candidate_rows, governing_value_n=governing_value_n,
        governing_row_identities=governing_row_identities,
    )
    provenance = tuple(
        item for item in (
            None if binding is None else f"binding:{binding.binding_id}@{binding.version}",
            None if policy is None else f"policy:{policy.policy_id}@{policy.version}",
            None if bundle is None else f"source:{bundle.actual_table_name}",
        ) if item is not None
    )
    return ResolvedNdmDemand(
        availability=availability,
        ndm_n=governing_value_n if availability == NdmAvailability.RESOLVED else None,
        unit=_N,
        trace=trace,
        provenance=provenance,
    )


def _force_unit(bundle: ResultRowEvidenceBundle) -> tuple[str | None, str | None]:
    declared = []
    for key in ("force_unit", "P"):
        value = bundle.units.get(key)
        if value not in (None, ""):
            declared.append(str(value).strip())
    if not declared:
        return None, "Pier Forces source force unit is missing"
    if len(set(declared)) != 1:
        return None, "Pier Forces source force-unit metadata is conflicting"
    unit = declared[0]
    if unit not in {_N, _KN}:
        return None, f"Unsupported Pier Forces source force unit: {unit}"
    return unit, None


def _to_n(value: Any, unit: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Pier Forces P must be numeric")
    number = float(value)
    return number if unit == _N else number * 1000.0


def _check_duplicate_identities(rows: Sequence[Mapping[str, Any]]) -> str | None:
    seen: dict[tuple[tuple[str, Any], ...], Mapping[str, Any]] = {}
    for row in rows:
        identity = _identity(row)
        prior = seen.get(identity)
        if prior is None:
            seen[identity] = row
            continue
        if dict(prior) != dict(row):
            return "Conflicting duplicate Pier Forces source row identity"
        return "Duplicate Pier Forces source row identity is ambiguous and is not silently deduplicated"
    return None


def _binding_policy_reason(binding: ReviewedNdmLoadBinding, policy: ReviewedNdmPolicy) -> str | None:
    if policy.ts498_decision == "UNRESOLVED":
        return "TS498 live-load reduction authority is unresolved"
    if set(policy.q_target_coefficients) != set(binding.q_case_ids):
        return "Reviewed Q target coefficients do not cover the exact bound Q identities"
    if set(policy.s_target_coefficients) != set(binding.s_case_ids):
        return "Reviewed S target coefficients do not cover the exact bound S identities"
    if len(set(policy.q_target_coefficients.values())) > 1 and not policy.unequal_q_interpretation_reviewed:
        return "Unequal Q target coefficients lack an explicit reviewed interpretation"
    if any(value != _TBDY_EQ_4_11_S_TARGET for value in policy.s_target_coefficients.values()):
        return "Reviewed S target coefficient must equal TBDY Eq.4.11 value 0.2"
    fixed_ids = (*binding.g_case_ids, *binding.horizontal_e_case_ids, *binding.vertical_e_case_ids)
    for combo in binding.final_combination_ids:
        baseline = binding.baseline_coefficients_by_combination[combo]
        target = binding.required_fixed_coefficients_by_combination[combo]
        for case_id in fixed_ids:
            if baseline[case_id] != target[case_id]:
                return f"Reviewed G/E coefficient mismatch for final combination {combo}, case {case_id}"
        correction_needed = any(
            baseline[case_id] != policy.q_target_coefficients[case_id]
            for case_id in binding.q_case_ids
        ) or any(
            baseline[case_id] != policy.s_target_coefficients[case_id]
            for case_id in binding.s_case_ids
        )
        if correction_needed and not policy.linear_superposition_reviewed:
            return "Q/S correction requires explicit reviewed linear-superposition authority"
    return None


def _static_row(
    rows: Sequence[Mapping[str, Any]], *, story: str, pier: str, location: str,
    case_id: str, binding: ReviewedNdmLoadBinding,
) -> Mapping[str, Any] | None:
    matches = [
        row for row in rows
        if row.get("Story") == story
        and row.get("Pier") == pier
        and row.get("Location") == location
        and row.get("OutputCase") == case_id
        and row.get("CaseType") == binding.static_case_type
        and row.get("StepType") is None
        and row.get("StepNumber") is None
    ]
    if len(matches) > 1:
        raise ValueError(f"Multiple exact static correction rows found for {case_id}")
    return matches[0] if matches else None


def select_ndm_demand(
    request: EngineeringQuantityRequest,
    pier_forces: ResultRowEvidenceBundle | None,
    binding: ReviewedNdmLoadBinding | None,
    policy: ReviewedNdmPolicy | None,
) -> ResolvedNdmDemand:
    """Select Ndm from exact reviewed final-combination rows, fail closed otherwise."""
    if not isinstance(request, EngineeringQuantityRequest):
        raise TypeError("select_ndm_demand requires EngineeringQuantityRequest")
    if binding is None:
        return _result(request, binding=None, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason="Reviewed Ndm load binding is missing")
    if not isinstance(binding, ReviewedNdmLoadBinding):
        return _result(request, binding=None, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason="Reviewed Ndm load binding has invalid type")
    if policy is None:
        return _result(request, binding=binding, policy=None, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason="Reviewed Ndm policy is missing")
    if not isinstance(policy, ReviewedNdmPolicy):
        return _result(request, binding=binding, policy=None, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason="Reviewed Ndm policy has invalid type")
    if pier_forces is None or not isinstance(pier_forces, ResultRowEvidenceBundle):
        return _result(request, binding=binding, policy=policy, bundle=None,
                       availability=NdmAvailability.BLOCKED, reason="Canonical Pier Forces evidence is unavailable")
    if pier_forces.table_key != "pier_forces":
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason="Ndm selector requires the canonical pier_forces source")
    if not pier_forces.is_full_capture:
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason="Ndm requires runtime FULL Pier Forces evidence")
    source_unit, unit_reason = _force_unit(pier_forces)
    if unit_reason is not None or source_unit is None:
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason=unit_reason, source_unit=source_unit)
    policy_reason = _binding_policy_reason(binding, policy)
    if policy_reason is not None:
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason=policy_reason, source_unit=source_unit)

    rows = tuple(sorted(pier_forces.rows, key=_row_sort_key))
    duplicate_reason = _check_duplicate_identities(rows)
    if duplicate_reason is not None:
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.BLOCKED, reason=duplicate_reason, source_unit=source_unit)

    component_rows = tuple(
        row for row in rows
        if row.get("Story") == request.story and row.get("Pier") == request.pier
    )
    bound_final_rows = tuple(row for row in component_rows if row.get("OutputCase") in binding.final_combination_ids)
    if not bound_final_rows:
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.NO_DATA,
                       reason="FULL Pier Forces lookup found no exact reviewed final-combination row for the requested component",
                       source_unit=source_unit)

    candidates: list[NdmCandidateTrace] = []
    accepted: list[NdmCandidateTrace] = []
    for row in bound_final_rows:
        combo = str(row.get("OutputCase"))
        identity = _identity(row)
        semantic_reason = None
        if row.get("CaseType") != binding.final_case_type:
            semantic_reason = "BOUND_FINAL_CASE_TYPE_MISMATCH"
        elif row.get("StepType") not in binding.allowed_final_step_types:
            semantic_reason = "BOUND_FINAL_STEP_TYPE_NOT_REVIEWED"
        elif row.get("StepNumber") is not None:
            semantic_reason = "BOUND_FINAL_STEP_NUMBER_SEMANTICS_MISMATCH"
        elif row.get("Location") not in binding.allowed_locations:
            semantic_reason = "BOUND_FINAL_LOCATION_NOT_REVIEWED"
        if semantic_reason is not None:
            try:
                raw_p = float(row.get("P"))
                canonical = _to_n(row.get("P"), source_unit)
            except (TypeError, ValueError):
                raw_p = 0.0
                canonical = 0.0
            rejected = NdmCandidateTrace(
                source_row_identity=identity, final_combination_id=combo,
                story=str(row.get("Story")), pier=str(row.get("Pier")), location=str(row.get("Location")),
                step_type=row.get("StepType"), step_number=row.get("StepNumber"),
                raw_p=raw_p, source_unit=source_unit, canonical_p_n=canonical,
                q_corrections=(), s_corrections=(), adjusted_p_n=canonical,
                canonical_compression_n=max(0.0, -canonical), accepted=False, reason=semantic_reason,
            )
            candidates.append(rejected)
            return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                           availability=NdmAvailability.BLOCKED,
                           reason=f"Reviewed final-combination row semantics mismatch: {semantic_reason}",
                           source_unit=source_unit, candidate_rows=candidates)

        try:
            raw_p = float(row.get("P"))
            canonical_p_n = _to_n(row.get("P"), source_unit)
        except (TypeError, ValueError):
            return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                           availability=NdmAvailability.BLOCKED,
                           reason="Reviewed final-combination P is missing or non-numeric",
                           source_unit=source_unit, candidate_rows=candidates)
        adjusted = canonical_p_n
        q_traces: list[CorrectionTrace] = []
        s_traces: list[CorrectionTrace] = []
        for family, case_ids, targets, output in (
            ("Q", binding.q_case_ids, policy.q_target_coefficients, q_traces),
            ("S", binding.s_case_ids, policy.s_target_coefficients, s_traces),
        ):
            baseline_map = binding.baseline_coefficients_by_combination[combo]
            for case_id in case_ids:
                baseline_coefficient = baseline_map[case_id]
                target_coefficient = targets[case_id]
                delta_coefficient = target_coefficient - baseline_coefficient
                if delta_coefficient == 0.0:
                    continue
                try:
                    correction_row = _static_row(
                        component_rows, story=request.story, pier=request.pier,
                        location=str(row.get("Location")), case_id=case_id, binding=binding,
                    )
                except ValueError as exc:
                    return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                                   availability=NdmAvailability.BLOCKED, reason=str(exc),
                                   source_unit=source_unit, candidate_rows=candidates)
                if correction_row is None:
                    return _result(
                        request, binding=binding, policy=policy, bundle=pier_forces,
                        availability=NdmAvailability.NO_DATA,
                        reason=f"FULL Pier Forces lookup found no exact required {family} correction row for {case_id}",
                        source_unit=source_unit, candidate_rows=candidates,
                    )
                try:
                    correction_raw = float(correction_row.get("P"))
                    correction_n = _to_n(correction_row.get("P"), source_unit)
                except (TypeError, ValueError):
                    return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                                   availability=NdmAvailability.BLOCKED,
                                   reason=f"Static correction P is non-numeric for {case_id}",
                                   source_unit=source_unit, candidate_rows=candidates)
                delta_p = delta_coefficient * correction_n
                adjusted += delta_p
                output.append(CorrectionTrace(
                    case_id=case_id,
                    source_row_identity=_identity(correction_row),
                    raw_p=correction_raw,
                    source_unit=source_unit,
                    canonical_p_n=correction_n,
                    baseline_coefficient=baseline_coefficient,
                    target_coefficient=target_coefficient,
                    delta_coefficient=delta_coefficient,
                    delta_p_n=delta_p,
                ))
        compression = max(0.0, -adjusted)
        candidate = NdmCandidateTrace(
            source_row_identity=identity,
            final_combination_id=combo,
            story=request.story,
            pier=request.pier,
            location=str(row.get("Location")),
            step_type=row.get("StepType"),
            step_number=row.get("StepNumber"),
            raw_p=raw_p,
            source_unit=source_unit,
            canonical_p_n=canonical_p_n,
            q_corrections=tuple(q_traces),
            s_corrections=tuple(s_traces),
            adjusted_p_n=adjusted,
            canonical_compression_n=compression,
            accepted=True,
            reason="EXACT_REVIEWED_FINAL_COMBINATION_ROW",
        )
        candidates.append(candidate)
        accepted.append(candidate)

    if not accepted:
        return _result(request, binding=binding, policy=policy, bundle=pier_forces,
                       availability=NdmAvailability.NO_DATA, reason="No admissible reviewed Ndm candidate row",
                       source_unit=source_unit, candidate_rows=candidates)
    governing = max(item.canonical_compression_n for item in accepted)
    governing_ids = tuple(
        item.source_row_identity for item in accepted if item.canonical_compression_n == governing
    )
    governing_ids = tuple(sorted(governing_ids, key=_identity_sort_key))
    return _result(
        request, binding=binding, policy=policy, bundle=pier_forces,
        availability=NdmAvailability.RESOLVED, reason=None, source_unit=source_unit,
        candidate_rows=candidates, governing_value_n=governing,
        governing_row_identities=governing_ids,
    )


__all__ = [
    "CorrectionTrace", "EngineeringQuantityRequest", "NdmAvailability", "NdmCandidateTrace",
    "ResolvedNdmDemand", "ReviewedNdmLoadBinding", "ReviewedNdmPolicy", "SelectionTrace",
    "select_ndm_demand",
]
