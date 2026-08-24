"""VS5 reviewed demand-selection authority for RC column axial checks.

This module selects only engineering demand quantities from immutable factual
column-force evidence. It owns no capacity, code limit, applicability, or
PASS/FAIL decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.features.etabs_column_axial_evidence import (
    COLUMN_FORCE_IDENTITY_FIELDS,
    ColumnForceEvidenceBundle,
    LiveColumnAxialEvidenceBundle,
)

_NDM = "Ndm"
_ND = "Nd"
_KN = "kN"
_TBDY_S_TARGET = 0.2


class ColumnDemandAvailability(StrEnum):
    RESOLVED = "RESOLVED"
    BLOCKED = "BLOCKED"
    NO_DATA = "NO_DATA"


class Ts498ReductionPolicyState(StrEnum):
    NO_REDUCTION = "NO_REDUCTION"
    REVIEWED_REDUCTION = "REVIEWED_REDUCTION"
    UNRESOLVED = "UNRESOLVED"


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _float(value: Any, label: str) -> float:
    if isinstance(value, bool) or value is None:
        raise TypeError(f"{label} must be a finite decimal scalar")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        if not value or value != value.strip():
            raise ValueError(f"{label} decimal text must be nonblank and unpadded")
        try:
            decimal = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{label} decimal text is invalid") from exc
        if not decimal.is_finite():
            raise ValueError(f"{label} must be finite")
        result = float(decimal)
    else:
        raise TypeError(f"{label} must be numeric")
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _float_map(values: Mapping[str, Any], label: str) -> Mapping[str, float]:
    out: dict[str, float] = {}
    for key, value in dict(values or {}).items():
        name = _text(str(key), label)
        out[name] = _float(value, f"{label}[{name}]")
    return MappingProxyType(out)


def _nested_float_map(
    values: Mapping[str, Mapping[str, Any]], label: str
) -> Mapping[str, Mapping[str, float]]:
    return MappingProxyType(
        {str(key): _float_map(item, f"{label}[{key}]") for key, item in dict(values or {}).items()}
    )


def _texts(values: Sequence[str], label: str, *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    result = tuple(_text(item, label) for item in values)
    if require_nonempty and not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique values")
    return result


def _identity(row: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((field, row.get(field)) for field in COLUMN_FORCE_IDENTITY_FIELDS)


def _row_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple("<NONE>" if row.get(field) is None else str(row.get(field)) for field in COLUMN_FORCE_IDENTITY_FIELDS)


@dataclass(frozen=True, slots=True)
class ReviewedColumnNdmLoadBinding:
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
    allowed_final_step_types: tuple[str | None, ...] = ("Max", "Min")
    static_case_type: str = "LinStatic"
    review_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", _text(self.binding_id, "binding_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        for name in (
            "final_combination_ids",
            "g_case_ids",
            "q_case_ids",
            "s_case_ids",
            "horizontal_e_case_ids",
            "vertical_e_case_ids",
        ):
            object.__setattr__(self, name, _texts(getattr(self, name), name, require_nonempty=name == "final_combination_ids"))
        step_types = tuple(self.allowed_final_step_types)
        if not step_types or any(item is not None and not isinstance(item, str) for item in step_types):
            raise ValueError("allowed_final_step_types must be a nonempty tuple of string/None values")
        object.__setattr__(self, "allowed_final_step_types", step_types)
        object.__setattr__(self, "final_case_type", _text(self.final_case_type, "final_case_type"))
        object.__setattr__(self, "static_case_type", _text(self.static_case_type, "static_case_type"))
        groups = (
            self.g_case_ids,
            self.q_case_ids,
            self.s_case_ids,
            self.horizontal_e_case_ids,
            self.vertical_e_case_ids,
        )
        all_cases = tuple(item for group in groups for item in group)
        if len(all_cases) != len(set(all_cases)):
            raise ValueError("Reviewed Ndm G/Q/S/E case identity groups must be disjoint")
        baseline = _nested_float_map(self.baseline_coefficients_by_combination, "baseline_coefficients")
        fixed = _nested_float_map(self.required_fixed_coefficients_by_combination, "fixed_coefficients")
        if set(baseline) != set(self.final_combination_ids):
            raise ValueError("baseline coefficients must cover exactly final_combination_ids")
        if set(fixed) != set(self.final_combination_ids):
            raise ValueError("fixed coefficients must cover exactly final_combination_ids")
        expected_all = set(all_cases)
        expected_fixed = set((*self.g_case_ids, *self.horizontal_e_case_ids, *self.vertical_e_case_ids))
        for combo in self.final_combination_ids:
            if set(baseline[combo]) != expected_all:
                raise ValueError(f"baseline coefficients for {combo} do not cover exact reviewed inventory")
            if set(fixed[combo]) != expected_fixed:
                raise ValueError(f"fixed coefficients for {combo} do not cover exact reviewed G/E inventory")
        object.__setattr__(self, "baseline_coefficients_by_combination", baseline)
        object.__setattr__(self, "required_fixed_coefficients_by_combination", fixed)
        object.__setattr__(self, "review_refs", tuple(_text(item, "review_ref") for item in self.review_refs))


@dataclass(frozen=True, slots=True)
class ReviewedColumnNdmPolicy:
    policy_id: str
    version: str
    target_unique_name: str
    ts498_reduction_state: Ts498ReductionPolicyState | str
    q_target_coefficients: Mapping[str, float]
    s_target_coefficients: Mapping[str, float]
    linear_superposition_reviewed: bool
    compression_sign: int
    regulatory_authority_ids: tuple[str, ...]
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "target_unique_name", _text(self.target_unique_name, "target_unique_name"))
        object.__setattr__(self, "ts498_reduction_state", Ts498ReductionPolicyState(self.ts498_reduction_state))
        object.__setattr__(self, "q_target_coefficients", _float_map(self.q_target_coefficients, "q_target_coefficients"))
        object.__setattr__(self, "s_target_coefficients", _float_map(self.s_target_coefficients, "s_target_coefficients"))
        if type(self.linear_superposition_reviewed) is not bool:
            raise TypeError("linear_superposition_reviewed must be bool")
        if self.compression_sign not in {-1, 1}:
            raise ValueError("compression_sign must be -1 or +1")
        authority = _texts(self.regulatory_authority_ids, "regulatory_authority_id")
        refs = _texts(self.review_refs, "review_ref")
        object.__setattr__(self, "regulatory_authority_ids", authority)
        object.__setattr__(self, "review_refs", refs)


@dataclass(frozen=True, slots=True)
class ReviewedTs500ColumnDemandPolicy:
    policy_id: str
    version: str
    target_unique_name: str
    combination_ids: tuple[str, ...]
    compression_sign: int
    final_case_type: str = "Combination"
    allowed_step_types: tuple[str | None, ...] = (None, "Max", "Min")
    review_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "target_unique_name", _text(self.target_unique_name, "target_unique_name"))
        object.__setattr__(self, "combination_ids", _texts(self.combination_ids, "combination_id"))
        if self.compression_sign not in {-1, 1}:
            raise ValueError("compression_sign must be -1 or +1")
        object.__setattr__(self, "final_case_type", _text(self.final_case_type, "final_case_type"))
        steps = tuple(self.allowed_step_types)
        if not steps or any(item is not None and not isinstance(item, str) for item in steps):
            raise ValueError("allowed_step_types must be a nonempty tuple of string/None values")
        object.__setattr__(self, "allowed_step_types", steps)
        object.__setattr__(self, "review_refs", _texts(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ColumnDemandCandidate:
    source_row_identity: tuple[tuple[str, Any], ...]
    output_case: str
    raw_p_kn: float
    adjusted_p_kn: float
    compression_kn: float
    corrections: tuple[Mapping[str, object], ...]
    accepted: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_row_identity": dict(self.source_row_identity),
            "output_case": self.output_case,
            "raw_p_kn": self.raw_p_kn,
            "adjusted_p_kn": self.adjusted_p_kn,
            "compression_kn": self.compression_kn,
            "corrections": [dict(item) for item in self.corrections],
            "accepted": self.accepted,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ResolvedColumnDemand:
    quantity: str
    availability: ColumnDemandAvailability
    demand_kn: float | None
    unit: str
    governing_row_identity: tuple[tuple[str, Any], ...] | None
    candidates: tuple[ColumnDemandCandidate, ...]
    provenance: tuple[str, ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.quantity not in {_NDM, _ND}:
            raise ValueError("quantity must be Ndm or Nd")
        if self.unit != _KN:
            raise ValueError("VS5 column demand unit must be kN")
        if self.availability is ColumnDemandAvailability.RESOLVED:
            if self.demand_kn is None or self.demand_kn < 0.0 or not math.isfinite(self.demand_kn):
                raise ValueError("resolved demand requires finite non-negative demand_kn")
            if self.governing_row_identity is None:
                raise ValueError("resolved demand requires governing row identity")
        elif self.demand_kn is not None:
            raise ValueError("unresolved demand must not carry demand_kn")

    def as_dict(self) -> dict[str, object]:
        return {
            "quantity": self.quantity,
            "availability": self.availability.value,
            "demand_kn": self.demand_kn,
            "unit": self.unit,
            "governing_row_identity": (
                None if self.governing_row_identity is None else dict(self.governing_row_identity)
            ),
            "candidates": [item.as_dict() for item in self.candidates],
            "provenance": list(self.provenance),
            "reason": self.reason,
        }


def _blocked(quantity: str, reason: str, provenance: Sequence[str] = ()) -> ResolvedColumnDemand:
    return ResolvedColumnDemand(
        quantity=quantity,
        availability=ColumnDemandAvailability.BLOCKED,
        demand_kn=None,
        unit=_KN,
        governing_row_identity=None,
        candidates=(),
        provenance=tuple(provenance),
        reason=reason,
    )


def _no_data(quantity: str, reason: str, provenance: Sequence[str] = ()) -> ResolvedColumnDemand:
    return ResolvedColumnDemand(
        quantity=quantity,
        availability=ColumnDemandAvailability.NO_DATA,
        demand_kn=None,
        unit=_KN,
        governing_row_identity=None,
        candidates=(),
        provenance=tuple(provenance),
        reason=reason,
    )


def _component_rows(
    forces: ColumnForceEvidenceBundle, unique_name: str
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        sorted(
            (row for row in forces.rows if str(row.get("UniqueName")) == unique_name),
            key=_row_key,
        )
    )


def _static_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    final_row: Mapping[str, Any],
    case_id: str,
    static_case_type: str,
) -> Mapping[str, Any] | None:
    matches = [
        row
        for row in rows
        if row.get("Story") == final_row.get("Story")
        and row.get("UniqueName") == final_row.get("UniqueName")
        and row.get("Column") == final_row.get("Column")
        and row.get("Station") == final_row.get("Station")
        and row.get("Element") == final_row.get("Element")
        and row.get("ElemStation") == final_row.get("ElemStation")
        and row.get("OutputCase") == case_id
        and row.get("CaseType") == static_case_type
        and row.get("StepType") is None
        and row.get("StepNumber") is None
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple exact static correction rows found for {case_id}")
    return matches[0] if matches else None


def _combo_coefficients(
    evidence: LiveColumnAxialEvidenceBundle, combo_name: str
) -> Mapping[str, float]:
    rows = [
        row
        for row in evidence.load_combination_rows
        if str(row.get("Name") or "") == combo_name
    ]
    if not rows:
        raise ValueError(f"reviewed combination not found in factual Load Combination Definitions: {combo_name}")
    out: dict[str, float] = {}
    for row in rows:
        load_name = _text(row.get("LoadName"), f"{combo_name}.LoadName")
        if load_name in out:
            raise ValueError(f"duplicate LoadName in factual combination definition: {combo_name}/{load_name}")
        out[load_name] = _float(row.get("SF"), f"{combo_name}/{load_name}.SF")
    return MappingProxyType(out)


def validate_column_ndm_binding(
    evidence: LiveColumnAxialEvidenceBundle,
    binding: ReviewedColumnNdmLoadBinding,
    policy: ReviewedColumnNdmPolicy,
) -> str | None:
    if policy.ts498_reduction_state is Ts498ReductionPolicyState.UNRESOLVED:
        return "TS498 reduction policy is unresolved"
    if set(policy.q_target_coefficients) != set(binding.q_case_ids):
        return "Reviewed Q target coefficients do not cover exact bound Q identities"
    if set(policy.s_target_coefficients) != set(binding.s_case_ids):
        return "Reviewed S target coefficients do not cover exact bound S identities"
    if any(value != _TBDY_S_TARGET for value in policy.s_target_coefficients.values()):
        return "Reviewed S target coefficient must equal TBDY Eq.4.11 value 0.2"
    if policy.ts498_reduction_state is Ts498ReductionPolicyState.NO_REDUCTION:
        if any(value != 1.0 for value in policy.q_target_coefficients.values()):
            return "NO_REDUCTION TS498 policy requires q target coefficient 1.0"
    all_bound = set(
        (
            *binding.g_case_ids,
            *binding.q_case_ids,
            *binding.s_case_ids,
            *binding.horizontal_e_case_ids,
            *binding.vertical_e_case_ids,
        )
    )
    fixed_ids = set((*binding.g_case_ids, *binding.horizontal_e_case_ids, *binding.vertical_e_case_ids))
    for combo in binding.final_combination_ids:
        factual = _combo_coefficients(evidence, combo)
        baseline = binding.baseline_coefficients_by_combination[combo]
        if set(baseline) != all_bound:
            return f"reviewed baseline inventory mismatch for {combo}"
        for case_id, coefficient in baseline.items():
            if case_id not in factual or factual[case_id] != coefficient:
                return f"factual/reviewed baseline coefficient mismatch for {combo}/{case_id}"
        fixed = binding.required_fixed_coefficients_by_combination[combo]
        for case_id in fixed_ids:
            if baseline[case_id] != fixed[case_id]:
                return f"reviewed fixed G/E coefficient mismatch for {combo}/{case_id}"
        correction_needed = any(
            baseline[case_id] != policy.q_target_coefficients[case_id]
            for case_id in binding.q_case_ids
        ) or any(
            baseline[case_id] != policy.s_target_coefficients[case_id]
            for case_id in binding.s_case_ids
        )
        if correction_needed and not policy.linear_superposition_reviewed:
            return "Q/S coefficient correction requires reviewed linear-superposition authority"
    pattern_types = {
        str(row.get("Name")): str(row.get("Type"))
        for row in evidence.load_pattern_rows
        if row.get("Name") is not None
    }
    for case_id in binding.q_case_ids:
        if pattern_types.get(case_id) != "Live":
            return f"reviewed Q case is not factual Load Pattern Type=Live: {case_id}"
    for case_id in binding.s_case_ids:
        if pattern_types.get(case_id) != "Snow":
            return f"reviewed S case is not factual Load Pattern Type=Snow: {case_id}"
    return None


def select_tbdy_column_ndm(
    evidence: LiveColumnAxialEvidenceBundle,
    binding: ReviewedColumnNdmLoadBinding,
    policy: ReviewedColumnNdmPolicy,
) -> ResolvedColumnDemand:
    if not isinstance(evidence, LiveColumnAxialEvidenceBundle):
        raise TypeError("select_tbdy_column_ndm requires LiveColumnAxialEvidenceBundle")
    if not isinstance(binding, ReviewedColumnNdmLoadBinding):
        raise TypeError("binding must be ReviewedColumnNdmLoadBinding")
    if not isinstance(policy, ReviewedColumnNdmPolicy):
        raise TypeError("policy must be ReviewedColumnNdmPolicy")
    try:
        evidence.column(policy.target_unique_name)
    except KeyError:
        return _no_data(_NDM, "Reviewed target column is not present in factual column population")
    reason = validate_column_ndm_binding(evidence, binding, policy)
    provenance = (
        f"evidence_epoch:{evidence.evidence_epoch_id}",
        f"binding:{binding.binding_id}@{binding.version}",
        f"policy:{policy.policy_id}@{policy.version}",
        *policy.regulatory_authority_ids,
        *binding.review_refs,
        *policy.review_refs,
    )
    if reason is not None:
        return _blocked(_NDM, reason, provenance)
    rows = _component_rows(evidence.forces, policy.target_unique_name)
    final_rows = tuple(
        row for row in rows if row.get("OutputCase") in binding.final_combination_ids
    )
    if not final_rows:
        return _no_data(_NDM, "No exact reviewed Ndm final-combination row for target column", provenance)

    candidates: list[ColumnDemandCandidate] = []
    accepted: list[ColumnDemandCandidate] = []
    for row in final_rows:
        combo = str(row.get("OutputCase"))
        semantic_reason = None
        if row.get("CaseType") != binding.final_case_type:
            semantic_reason = "BOUND_FINAL_CASE_TYPE_MISMATCH"
        elif row.get("StepType") not in binding.allowed_final_step_types:
            semantic_reason = "BOUND_FINAL_STEP_TYPE_NOT_REVIEWED"
        elif row.get("StepNumber") is not None:
            semantic_reason = "BOUND_FINAL_STEP_NUMBER_NOT_REVIEWED"
        raw_p = _float(row.get("P"), "column force P")
        adjusted = raw_p
        corrections: list[Mapping[str, object]] = []
        if semantic_reason is None:
            baseline = binding.baseline_coefficients_by_combination[combo]
            for case_id in (*binding.q_case_ids, *binding.s_case_ids):
                target = (
                    policy.q_target_coefficients[case_id]
                    if case_id in binding.q_case_ids
                    else policy.s_target_coefficients[case_id]
                )
                delta = target - baseline[case_id]
                if delta == 0.0:
                    continue
                source = _static_row(
                    rows,
                    final_row=row,
                    case_id=case_id,
                    static_case_type=binding.static_case_type,
                )
                if source is None:
                    semantic_reason = f"MISSING_EXACT_STATIC_CORRECTION_ROW:{case_id}"
                    break
                source_p = _float(source.get("P"), f"{case_id}.P")
                delta_p = delta * source_p
                adjusted += delta_p
                corrections.append(
                    MappingProxyType(
                        {
                            "case_id": case_id,
                            "source_row_identity": dict(_identity(source)),
                            "baseline_coefficient": baseline[case_id],
                            "target_coefficient": target,
                            "delta_coefficient": delta,
                            "source_p_kn": source_p,
                            "delta_p_kn": delta_p,
                        }
                    )
                )
        compression = max(0.0, policy.compression_sign * adjusted)
        candidate = ColumnDemandCandidate(
            source_row_identity=_identity(row),
            output_case=combo,
            raw_p_kn=raw_p,
            adjusted_p_kn=adjusted,
            compression_kn=compression,
            corrections=tuple(corrections),
            accepted=semantic_reason is None,
            reason="ACCEPTED" if semantic_reason is None else semantic_reason,
        )
        candidates.append(candidate)
        if candidate.accepted:
            accepted.append(candidate)

    if not accepted:
        return _blocked(_NDM, "No reviewed Ndm candidate survived semantic validation", provenance)
    governing = max(
        accepted,
        key=lambda item: (item.compression_kn, tuple(str(v) for _, v in item.source_row_identity)),
    )
    return ResolvedColumnDemand(
        quantity=_NDM,
        availability=ColumnDemandAvailability.RESOLVED,
        demand_kn=governing.compression_kn,
        unit=_KN,
        governing_row_identity=governing.source_row_identity,
        candidates=tuple(candidates),
        provenance=provenance,
        reason=None,
    )


def validate_ts500_column_policy(
    evidence: LiveColumnAxialEvidenceBundle,
    policy: ReviewedTs500ColumnDemandPolicy,
) -> str | None:
    factual_combo_names = {
        str(row.get("Name"))
        for row in evidence.load_combination_rows
        if row.get("Name") is not None
    }
    missing = tuple(name for name in policy.combination_ids if name not in factual_combo_names)
    if missing:
        return "Reviewed TS500 ULS combination(s) missing from factual definitions: " + ",".join(missing)
    return None


def select_ts500_column_nd(
    evidence: LiveColumnAxialEvidenceBundle,
    policy: ReviewedTs500ColumnDemandPolicy,
) -> ResolvedColumnDemand:
    if not isinstance(evidence, LiveColumnAxialEvidenceBundle):
        raise TypeError("select_ts500_column_nd requires LiveColumnAxialEvidenceBundle")
    if not isinstance(policy, ReviewedTs500ColumnDemandPolicy):
        raise TypeError("policy must be ReviewedTs500ColumnDemandPolicy")
    try:
        evidence.column(policy.target_unique_name)
    except KeyError:
        return _no_data(_ND, "Reviewed target column is not present in factual column population")
    provenance = (
        f"evidence_epoch:{evidence.evidence_epoch_id}",
        f"policy:{policy.policy_id}@{policy.version}",
        *policy.review_refs,
    )
    reason = validate_ts500_column_policy(evidence, policy)
    if reason is not None:
        return _blocked(_ND, reason, provenance)
    rows = _component_rows(evidence.forces, policy.target_unique_name)
    final_rows = tuple(row for row in rows if row.get("OutputCase") in policy.combination_ids)
    if not final_rows:
        return _no_data(_ND, "No exact reviewed TS500 ULS row for target column", provenance)

    candidates: list[ColumnDemandCandidate] = []
    accepted: list[ColumnDemandCandidate] = []
    for row in final_rows:
        semantic_reason = None
        if row.get("CaseType") != policy.final_case_type:
            semantic_reason = "BOUND_FINAL_CASE_TYPE_MISMATCH"
        elif row.get("StepType") not in policy.allowed_step_types:
            semantic_reason = "BOUND_FINAL_STEP_TYPE_NOT_REVIEWED"
        elif row.get("StepNumber") is not None:
            semantic_reason = "BOUND_FINAL_STEP_NUMBER_NOT_REVIEWED"
        raw_p = _float(row.get("P"), "column force P")
        compression = max(0.0, policy.compression_sign * raw_p)
        candidate = ColumnDemandCandidate(
            source_row_identity=_identity(row),
            output_case=str(row.get("OutputCase")),
            raw_p_kn=raw_p,
            adjusted_p_kn=raw_p,
            compression_kn=compression,
            corrections=(),
            accepted=semantic_reason is None,
            reason="ACCEPTED" if semantic_reason is None else semantic_reason,
        )
        candidates.append(candidate)
        if candidate.accepted:
            accepted.append(candidate)
    if not accepted:
        return _blocked(_ND, "No reviewed TS500 ULS candidate survived semantic validation", provenance)
    governing = max(
        accepted,
        key=lambda item: (item.compression_kn, tuple(str(v) for _, v in item.source_row_identity)),
    )
    return ResolvedColumnDemand(
        quantity=_ND,
        availability=ColumnDemandAvailability.RESOLVED,
        demand_kn=governing.compression_kn,
        unit=_KN,
        governing_row_identity=governing.source_row_identity,
        candidates=tuple(candidates),
        provenance=provenance,
        reason=None,
    )


__all__ = [
    "ColumnDemandAvailability",
    "Ts498ReductionPolicyState",
    "ReviewedColumnNdmLoadBinding",
    "ReviewedColumnNdmPolicy",
    "ReviewedTs500ColumnDemandPolicy",
    "ColumnDemandCandidate",
    "ResolvedColumnDemand",
    "validate_column_ndm_binding",
    "select_tbdy_column_ndm",
    "validate_ts500_column_policy",
    "select_ts500_column_nd",
]
