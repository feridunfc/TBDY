"""Fail-closed B4A derived/pre-analysis state semantics.

Representation/comparison only: no ETABS transport, mutation, analysis, design,
or result-lineage qualification. Positive factual establishment is deliberately
private and reserved for the future B4B mutation/readback authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.integration.etabs_analysis_lineage import (
    AnalysisStateIdentity,
    build_analysis_state_identity,
)

DERIVED_STATE_CONTRACT = "TBDY_DERIVED_PRE_ANALYSIS_STATE_V1"
REQUESTED_STATE_MANIFEST_CONTRACT = "TBDY_REQUESTED_DERIVED_STATE_MANIFEST_V1"
ESTABLISHED_STATE_MANIFEST_CONTRACT = "TBDY_ESTABLISHED_DERIVED_STATE_MANIFEST_V1"
DERIVED_STATE_COMPARISON_CONTRACT = "TBDY_DERIVED_STATE_COMPARISON_V1"
REQUESTED_STATE_REF_PREFIX = "derived-state-request:sha256:"
ESTABLISHED_STATE_REF_PREFIX = "derived-state-established:sha256:"
DERIVED_STATE_COMPARISON_REF_PREFIX = "derived-state-comparison:sha256:"
_ENTRY_TOKEN = object()
_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN = object()
_COMPARISON_TOKEN = object()


class DerivedStateError(ValueError):
    pass


class DerivedStateComparisonError(DerivedStateError):
    pass


class DerivedStateFamily(StrEnum):
    MASS_SOURCE = "MASS_SOURCE"
    MODAL_CASE_SETUP = "MODAL_CASE_SETUP"
    SECTION_STIFFNESS_MODIFIERS = "SECTION_STIFFNESS_MODIFIERS"
    ANALYSIS_OPTIONS = "ANALYSIS_OPTIONS"
    ANALYSIS_RUN_FLAGS = "ANALYSIS_RUN_FLAGS"
    LOAD_CASE_PARTICIPATION = "LOAD_CASE_PARTICIPATION"
    PRESENT_UNITS = "PRESENT_UNITS"
    RESULTS_SETUP_SELECTION = "RESULTS_SETUP_SELECTION"
    DATABASE_TABLES_SELECTION = "DATABASE_TABLES_SELECTION"
    DESIGN_OVERWRITES = "DESIGN_OVERWRITES"


class DerivedStateFamilyClassification(StrEnum):
    CAUSAL_DERIVED_STATE = "CAUSAL_DERIVED_STATE"
    ANALYSIS_EXECUTION_CONFIGURATION = "ANALYSIS_EXECUTION_CONFIGURATION"
    EPHEMERAL_ACQUISITION_CONFIGURATION = "EPHEMERAL_ACQUISITION_CONFIGURATION"
    REPRESENTATIONAL_CONTEXT = "REPRESENTATIONAL_CONTEXT"
    DESIGN_STATE = "DESIGN_STATE"


STATE_FAMILY_CLASSIFICATION: Mapping[DerivedStateFamily, DerivedStateFamilyClassification] = MappingProxyType({
    DerivedStateFamily.MASS_SOURCE: DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
    DerivedStateFamily.MODAL_CASE_SETUP: DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
    DerivedStateFamily.SECTION_STIFFNESS_MODIFIERS: DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
    DerivedStateFamily.ANALYSIS_OPTIONS: DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE,
    DerivedStateFamily.ANALYSIS_RUN_FLAGS: DerivedStateFamilyClassification.ANALYSIS_EXECUTION_CONFIGURATION,
    DerivedStateFamily.LOAD_CASE_PARTICIPATION: DerivedStateFamilyClassification.ANALYSIS_EXECUTION_CONFIGURATION,
    DerivedStateFamily.PRESENT_UNITS: DerivedStateFamilyClassification.REPRESENTATIONAL_CONTEXT,
    DerivedStateFamily.RESULTS_SETUP_SELECTION: DerivedStateFamilyClassification.EPHEMERAL_ACQUISITION_CONFIGURATION,
    DerivedStateFamily.DATABASE_TABLES_SELECTION: DerivedStateFamilyClassification.EPHEMERAL_ACQUISITION_CONFIGURATION,
    DerivedStateFamily.DESIGN_OVERWRITES: DerivedStateFamilyClassification.DESIGN_STATE,
})


class SequenceOrdering(StrEnum):
    ORDER_SENSITIVE = "ORDER_SENSITIVE"
    ORDER_INSENSITIVE = "ORDER_INSENSITIVE"


class DerivedStateEstablishmentStatus(StrEnum):
    ESTABLISHED = "ESTABLISHED"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    INCOMPLETE = "INCOMPLETE"


class DerivedStateComparisonStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class NormalizationContract:
    sequence_ordering: SequenceOrdering = SequenceOrdering.ORDER_SENSITIVE

    def __post_init__(self) -> None:
        if not isinstance(self.sequence_ordering, SequenceOrdering):
            raise TypeError("sequence_ordering must be SequenceOrdering")

    def as_dict(self) -> dict[str, str]:
        return {"sequence_ordering": self.sequence_ordering.value}


@dataclass(frozen=True, slots=True)
class NumericTolerance:
    absolute: float = 0.0
    relative: float = 0.0

    def __post_init__(self) -> None:
        for label, value in (("absolute", self.absolute), ("relative", self.relative)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{label} tolerance must be numeric")
            if not math.isfinite(float(value)) or float(value) < 0:
                raise DerivedStateError(f"{label} tolerance must be finite and nonnegative")
        object.__setattr__(self, "absolute", float(self.absolute))
        object.__setattr__(self, "relative", float(self.relative))

    def as_dict(self) -> dict[str, float]:
        return {"absolute": self.absolute, "relative": self.relative}


NO_NUMERIC_TOLERANCE = NumericTolerance()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DerivedStateError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    result = tuple(sorted({_text(value, label) for value in values}))
    if required and not result:
        raise DerivedStateError(f"{label} must be nonempty")
    return result


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha(prefix: str, payload: Mapping[str, object]) -> str:
    return prefix + hashlib.sha256(_json(dict(payload)).encode("utf-8")).hexdigest()


def _normalize(value: object, contract: NormalizationContract) -> object:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DerivedStateError("state values must not contain NaN or infinity")
        return value
    if isinstance(value, Enum):
        return _normalize(value.value, contract)
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = _text(raw_key, "state mapping key")
            if key in normalized:
                raise DerivedStateError(f"duplicate canonical state mapping key: {key}")
            normalized[key] = _normalize(raw_value, contract)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (tuple, list)):
        items = [_normalize(item, contract) for item in value]
        if contract.sequence_ordering is SequenceOrdering.ORDER_INSENSITIVE:
            items.sort(key=_json)
        return items
    raise DerivedStateError(
        f"unsupported state value type: {type(value).__name__}; missing/unknown state requires an explicit readback status"
    )


def _value_json(value: object, contract: NormalizationContract) -> str:
    return _json(_normalize(value, contract))


def _setter_return_only(value: object) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    keys = {str(key).strip().lower().replace("-", "_") for key in value if isinstance(key, str)}
    return len(keys) == len(value) and keys <= {"ret", "return_code", "returncode", "hresult", "status_code"}


def state_family_classification(family: DerivedStateFamily) -> DerivedStateFamilyClassification:
    if not isinstance(family, DerivedStateFamily):
        raise TypeError("family must be DerivedStateFamily")
    return STATE_FAMILY_CLASSIFICATION[family]


def _causal(family: DerivedStateFamily) -> None:
    classification = state_family_classification(family)
    if classification is not DerivedStateFamilyClassification.CAUSAL_DERIVED_STATE:
        raise DerivedStateError(
            f"{family.value} is {classification.value} and cannot enter a causal derived-state manifest"
        )


@dataclass(frozen=True, slots=True, init=False)
class RequestedDerivedState:
    family: DerivedStateFamily
    canonical_value_json: str
    normalization: NormalizationContract
    tolerance: NumericTolerance
    provenance_refs: tuple[str, ...]

    def __init__(self, *, _token=None, family, canonical_value_json, normalization, tolerance, provenance_refs):
        if _token is not _ENTRY_TOKEN:
            raise TypeError("RequestedDerivedState is factory-created only; use request_derived_state")
        _causal(family)
        json.loads(canonical_value_json)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "canonical_value_json", canonical_value_json)
        object.__setattr__(self, "normalization", normalization)
        object.__setattr__(self, "tolerance", tolerance)
        object.__setattr__(self, "provenance_refs", _refs(provenance_refs, "provenance_ref"))

    @property
    def canonical_value(self) -> object:
        return json.loads(self.canonical_value_json)

    def semantic_dict(self) -> dict[str, object]:
        return {
            "family": self.family.value,
            "canonical_value": self.canonical_value,
            "normalization": self.normalization.as_dict(),
            "tolerance": self.tolerance.as_dict(),
        }


@dataclass(frozen=True, slots=True, init=False)
class EstablishedDerivedState:
    family: DerivedStateFamily
    status: DerivedStateEstablishmentStatus
    canonical_value_json: str | None
    normalization: NormalizationContract
    evidence_refs: tuple[str, ...]
    diagnostic: str | None
    provenance_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        _token=None,
        _positive_issuer_token=None,
        family,
        status,
        canonical_value_json,
        normalization,
        evidence_refs,
        diagnostic,
        provenance_refs,
    ):
        if _token is not _ENTRY_TOKEN:
            raise TypeError("EstablishedDerivedState is factory-created only")
        _causal(family)
        if not isinstance(status, DerivedStateEstablishmentStatus):
            raise TypeError("status must be DerivedStateEstablishmentStatus")
        evidence = _refs(evidence_refs, "readback_evidence_ref")
        diagnostic = None if diagnostic is None else _text(diagnostic, "diagnostic")
        if status is DerivedStateEstablishmentStatus.ESTABLISHED:
            if _positive_issuer_token is not _POSITIVE_ESTABLISHMENT_ISSUER_TOKEN:
                raise TypeError("positive EstablishedDerivedState is issuer-created only")
            if canonical_value_json is None or not evidence:
                raise DerivedStateError("ESTABLISHED readback requires canonical value and factual readback evidence")
            json.loads(canonical_value_json)
            if diagnostic is not None:
                raise DerivedStateError("ESTABLISHED readback cannot carry a failure diagnostic")
        else:
            if _positive_issuer_token is not None:
                raise DerivedStateError("non-positive readback must not carry positive issuer authority")
            if canonical_value_json is not None:
                raise DerivedStateError(f"{status.value} readback cannot carry an established value")
            if diagnostic is None:
                raise DerivedStateError(f"{status.value} readback requires a diagnostic")
        for name, value in (
            ("family", family),
            ("status", status),
            ("canonical_value_json", canonical_value_json),
            ("normalization", normalization),
            ("evidence_refs", evidence),
            ("diagnostic", diagnostic),
            ("provenance_refs", _refs(provenance_refs, "provenance_ref")),
        ):
            object.__setattr__(self, name, value)

    @property
    def canonical_value(self) -> object | None:
        return None if self.canonical_value_json is None else json.loads(self.canonical_value_json)

    def semantic_dict(self) -> dict[str, object]:
        return {
            "family": self.family.value,
            "status": self.status.value,
            "canonical_value": self.canonical_value,
            "normalization": self.normalization.as_dict(),
        }


def request_derived_state(
    *,
    family: DerivedStateFamily,
    value: object,
    normalization: NormalizationContract = NormalizationContract(),
    tolerance: NumericTolerance = NO_NUMERIC_TOLERANCE,
    provenance_refs: Sequence[str] = (),
) -> RequestedDerivedState:
    _causal(family)
    if not isinstance(normalization, NormalizationContract) or not isinstance(tolerance, NumericTolerance):
        raise TypeError("normalization/tolerance contract type mismatch")
    return RequestedDerivedState(
        _token=_ENTRY_TOKEN,
        family=family,
        canonical_value_json=_value_json(value, normalization),
        normalization=normalization,
        tolerance=tolerance,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def _establish_derived_state_from_verified_readback(
    *,
    _issuer_token: object = None,
    family: DerivedStateFamily,
    readback_value: object,
    readback_evidence_refs: Sequence[str],
    normalization: NormalizationContract = NormalizationContract(),
    provenance_refs: Sequence[str] = (),
) -> EstablishedDerivedState:
    """Private positive primitive reserved for future B4B verified readback."""
    if _issuer_token is not _POSITIVE_ESTABLISHMENT_ISSUER_TOKEN:
        raise TypeError("positive established-state readback is issuer-created only")
    _causal(family)
    if _setter_return_only(readback_value):
        raise DerivedStateError("setter return-code-shaped data cannot establish derived state")
    if not isinstance(normalization, NormalizationContract):
        raise TypeError("normalization must be NormalizationContract")
    return EstablishedDerivedState(
        _token=_ENTRY_TOKEN,
        _positive_issuer_token=_POSITIVE_ESTABLISHMENT_ISSUER_TOKEN,
        family=family,
        status=DerivedStateEstablishmentStatus.ESTABLISHED,
        canonical_value_json=_value_json(readback_value, normalization),
        normalization=normalization,
        evidence_refs=_refs(readback_evidence_refs, "readback_evidence_ref", required=True),
        diagnostic=None,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def record_derived_state_readback_failure(
    *,
    family: DerivedStateFamily,
    status: DerivedStateEstablishmentStatus,
    diagnostic: str,
    readback_evidence_refs: Sequence[str] = (),
    normalization: NormalizationContract = NormalizationContract(),
    provenance_refs: Sequence[str] = (),
) -> EstablishedDerivedState:
    if status is DerivedStateEstablishmentStatus.ESTABLISHED:
        raise DerivedStateError("positive ESTABLISHED issuance is private to the future B4B authority")
    if not isinstance(normalization, NormalizationContract):
        raise TypeError("normalization must be NormalizationContract")
    return EstablishedDerivedState(
        _token=_ENTRY_TOKEN,
        family=family,
        status=status,
        canonical_value_json=None,
        normalization=normalization,
        evidence_refs=_refs(readback_evidence_refs, "readback_evidence_ref"),
        diagnostic=diagnostic,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def _entry_map(entries: Sequence[object], cls: type, label: str) -> dict[DerivedStateFamily, object]:
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise TypeError(f"{label} must be a sequence")
    result = {}
    for entry in entries:
        if not isinstance(entry, cls):
            raise TypeError(f"{label} entries must be {cls.__name__}")
        if entry.family in result:
            raise DerivedStateError(f"duplicate {label} family: {entry.family.value}")
        result[entry.family] = entry
    return result


@dataclass(frozen=True, slots=True)
class RequestedDerivedStateManifest:
    source_model_ref: str
    entries: tuple[RequestedDerivedState, ...]
    manifest_ref: str = field(init=False)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    contract: str = REQUESTED_STATE_MANIFEST_CONTRACT

    def __post_init__(self) -> None:
        source = _text(self.source_model_ref, "source_model_ref")
        mapping = _entry_map(self.entries, RequestedDerivedState, "requested state")
        if not mapping:
            raise DerivedStateError("requested derived-state manifest must contain at least one causal family")
        ordered = tuple(mapping[key] for key in sorted(mapping, key=lambda item: item.value))
        if self.contract != REQUESTED_STATE_MANIFEST_CONTRACT:
            raise DerivedStateError("requested derived-state manifest contract mismatch")
        payload = {
            "contract": self.contract,
            "derived_state_contract": DERIVED_STATE_CONTRACT,
            "source_model_ref": source,
            "entries": [entry.semantic_dict() for entry in ordered],
        }
        object.__setattr__(self, "source_model_ref", source)
        object.__setattr__(self, "entries", ordered)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))
        object.__setattr__(self, "manifest_ref", _sha(REQUESTED_STATE_REF_PREFIX, payload))

    @property
    def family_set(self) -> frozenset[DerivedStateFamily]:
        return frozenset(entry.family for entry in self.entries)


@dataclass(frozen=True, slots=True)
class EstablishedDerivedStateManifest:
    source_model_ref: str
    entries: tuple[EstablishedDerivedState, ...]
    manifest_ref: str = field(init=False)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    contract: str = ESTABLISHED_STATE_MANIFEST_CONTRACT

    def __post_init__(self) -> None:
        source = _text(self.source_model_ref, "source_model_ref")
        mapping = _entry_map(self.entries, EstablishedDerivedState, "established/readback state")
        ordered = tuple(mapping[key] for key in sorted(mapping, key=lambda item: item.value))
        if self.contract != ESTABLISHED_STATE_MANIFEST_CONTRACT:
            raise DerivedStateError("established derived-state manifest contract mismatch")
        payload = {
            "contract": self.contract,
            "derived_state_contract": DERIVED_STATE_CONTRACT,
            "source_model_ref": source,
            "entries": [entry.semantic_dict() for entry in ordered],
        }
        object.__setattr__(self, "source_model_ref", source)
        object.__setattr__(self, "entries", ordered)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))
        object.__setattr__(self, "manifest_ref", _sha(ESTABLISHED_STATE_REF_PREFIX, payload))

    @property
    def family_set(self) -> frozenset[DerivedStateFamily]:
        return frozenset(entry.family for entry in self.entries)

    @property
    def is_fully_established(self) -> bool:
        return bool(self.entries) and all(
            entry.status is DerivedStateEstablishmentStatus.ESTABLISHED for entry in self.entries
        )


@dataclass(frozen=True, slots=True)
class DerivedStateFamilyComparison:
    family: DerivedStateFamily
    status: DerivedStateComparisonStatus
    requested_canonical_value_json: str | None
    established_canonical_value_json: str | None
    mismatch_reason: str | None
    missing_evidence: tuple[str, ...]
    tolerance: NumericTolerance

    @property
    def requested_canonical_value(self) -> object | None:
        return None if self.requested_canonical_value_json is None else json.loads(self.requested_canonical_value_json)

    @property
    def established_canonical_value(self) -> object | None:
        return None if self.established_canonical_value_json is None else json.loads(self.established_canonical_value_json)

    def semantic_dict(self) -> dict[str, object]:
        return {
            "family": self.family.value,
            "status": self.status.value,
            "requested_canonical_value": self.requested_canonical_value,
            "established_canonical_value": self.established_canonical_value,
            "mismatch_reason": self.mismatch_reason,
            "missing_evidence": list(self.missing_evidence),
            "tolerance": self.tolerance.as_dict(),
        }


def _numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _mismatch(left: object, right: object, tolerance: NumericTolerance, path: str = "$") -> str | None:
    if _json(left) == _json(right):
        return None
    if _numeric(left) and _numeric(right):
        return None if math.isclose(
            float(left), float(right), rel_tol=tolerance.relative, abs_tol=tolerance.absolute
        ) else path
    if isinstance(left, dict) and isinstance(right, dict):
        if tuple(left) != tuple(right):
            return f"{path}.keys"
        for key in left:
            found = _mismatch(left[key], right[key], tolerance, f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return f"{path}.length"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            found = _mismatch(a, b, tolerance, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    return path


def compare_derived_state_entries(
    requested: RequestedDerivedState,
    established: EstablishedDerivedState,
) -> DerivedStateFamilyComparison:
    if not isinstance(requested, RequestedDerivedState) or not isinstance(established, EstablishedDerivedState):
        raise TypeError("requested/established entry type mismatch")
    common = dict(
        family=requested.family,
        requested_canonical_value_json=requested.canonical_value_json,
        established_canonical_value_json=established.canonical_value_json,
        missing_evidence=(),
        tolerance=requested.tolerance,
    )
    if requested.family is not established.family:
        return DerivedStateFamilyComparison(
            status=DerivedStateComparisonStatus.MISMATCH,
            mismatch_reason=f"WRONG_STATE_FAMILY:{established.family.value}",
            **common,
        )
    if requested.normalization != established.normalization:
        return DerivedStateFamilyComparison(
            status=DerivedStateComparisonStatus.MISMATCH,
            mismatch_reason="NORMALIZATION_CONTRACT_MISMATCH",
            **common,
        )
    if established.status is not DerivedStateEstablishmentStatus.ESTABLISHED:
        status = {
            DerivedStateEstablishmentStatus.UNAVAILABLE: DerivedStateComparisonStatus.UNAVAILABLE,
            DerivedStateEstablishmentStatus.UNSUPPORTED: DerivedStateComparisonStatus.UNSUPPORTED,
            DerivedStateEstablishmentStatus.INCOMPLETE: DerivedStateComparisonStatus.INCOMPLETE,
        }[established.status]
        return DerivedStateFamilyComparison(
            status=status,
            mismatch_reason=established.diagnostic,
            missing_evidence=() if established.evidence_refs else (f"readback:{requested.family.value}",),
            **{key: value for key, value in common.items() if key != "missing_evidence"},
        )
    path = _mismatch(requested.canonical_value, established.canonical_value, requested.tolerance)
    return DerivedStateFamilyComparison(
        status=DerivedStateComparisonStatus.MATCH if path is None else DerivedStateComparisonStatus.MISMATCH,
        mismatch_reason=None if path is None else f"CANONICAL_VALUE_MISMATCH:{path}",
        **common,
    )


@dataclass(frozen=True, slots=True, init=False)
class DerivedStateComparison:
    requested_manifest: RequestedDerivedStateManifest
    established_manifest: EstablishedDerivedStateManifest
    status: DerivedStateComparisonStatus
    family_results: tuple[DerivedStateFamilyComparison, ...]
    comparison_ref: str
    provenance_refs: tuple[str, ...]
    contract: str

    def __init__(
        self,
        *,
        _token=None,
        requested_manifest,
        established_manifest,
        status,
        family_results,
        comparison_ref,
        provenance_refs,
        contract=DERIVED_STATE_COMPARISON_CONTRACT,
    ):
        if _token is not _COMPARISON_TOKEN:
            raise TypeError("DerivedStateComparison is factory-created only; use compare_derived_state_manifests")
        if contract != DERIVED_STATE_COMPARISON_CONTRACT:
            raise DerivedStateError("derived-state comparison contract mismatch")
        for name, value in (
            ("requested_manifest", requested_manifest),
            ("established_manifest", established_manifest),
            ("status", status),
            ("family_results", family_results),
            ("comparison_ref", comparison_ref),
            ("provenance_refs", _refs(provenance_refs, "provenance_ref")),
            ("contract", contract),
        ):
            object.__setattr__(self, name, value)

    @property
    def matched(self) -> bool:
        return self.status is DerivedStateComparisonStatus.MATCH

    @property
    def exact_causal_family_population(self) -> bool:
        return self.requested_manifest.family_set == self.established_manifest.family_set

    def require_established_state_ref(self) -> str:
        if (
            not self.matched
            or not self.exact_causal_family_population
            or not self.established_manifest.is_fully_established
        ):
            raise DerivedStateComparisonError(
                "derived/pre-analysis state is not factually established with an exact matched causal-family population"
            )
        return self.established_manifest.manifest_ref


def _aggregate(results: Sequence[DerivedStateFamilyComparison]) -> DerivedStateComparisonStatus:
    statuses = {result.status for result in results}
    if statuses == {DerivedStateComparisonStatus.MATCH}:
        return DerivedStateComparisonStatus.MATCH
    for status in (
        DerivedStateComparisonStatus.MISMATCH,
        DerivedStateComparisonStatus.UNSUPPORTED,
        DerivedStateComparisonStatus.UNAVAILABLE,
        DerivedStateComparisonStatus.INCOMPLETE,
    ):
        if status in statuses:
            return status
    raise DerivedStateError("derived-state comparison produced no deterministic status")


def compare_derived_state_manifests(
    requested: RequestedDerivedStateManifest,
    established: EstablishedDerivedStateManifest,
    *,
    provenance_refs: Sequence[str] = (),
) -> DerivedStateComparison:
    if not isinstance(requested, RequestedDerivedStateManifest) or not isinstance(
        established, EstablishedDerivedStateManifest
    ):
        raise TypeError("requested/established manifest type mismatch")
    observed = {entry.family: entry for entry in established.entries}
    requested_by_family = {entry.family: entry for entry in requested.entries}
    results: list[DerivedStateFamilyComparison] = []

    for wanted in requested.entries:
        actual = observed.get(wanted.family)
        if actual is None:
            results.append(DerivedStateFamilyComparison(
                family=wanted.family,
                status=DerivedStateComparisonStatus.INCOMPLETE,
                requested_canonical_value_json=wanted.canonical_value_json,
                established_canonical_value_json=None,
                mismatch_reason="REQUESTED_FAMILY_READBACK_MISSING",
                missing_evidence=(f"readback:{wanted.family.value}",),
                tolerance=wanted.tolerance,
            ))
        elif requested.source_model_ref != established.source_model_ref:
            results.append(DerivedStateFamilyComparison(
                family=wanted.family,
                status=DerivedStateComparisonStatus.MISMATCH,
                requested_canonical_value_json=wanted.canonical_value_json,
                established_canonical_value_json=actual.canonical_value_json,
                mismatch_reason="SOURCE_MODEL_REF_MISMATCH",
                missing_evidence=(),
                tolerance=wanted.tolerance,
            ))
        else:
            results.append(compare_derived_state_entries(wanted, actual))

    for family in sorted(set(observed) - set(requested_by_family), key=lambda item: item.value):
        actual = observed[family]
        results.append(DerivedStateFamilyComparison(
            family=family,
            status=DerivedStateComparisonStatus.MISMATCH,
            requested_canonical_value_json=None,
            established_canonical_value_json=actual.canonical_value_json,
            mismatch_reason="UNREQUESTED_CAUSAL_FAMILY",
            missing_evidence=(),
            tolerance=NO_NUMERIC_TOLERANCE,
        ))

    family_results = tuple(results)
    status = _aggregate(family_results)
    payload = {
        "contract": DERIVED_STATE_COMPARISON_CONTRACT,
        "requested_manifest_ref": requested.manifest_ref,
        "established_manifest_ref": established.manifest_ref,
        "status": status.value,
        "exact_causal_family_population": requested.family_set == established.family_set,
        "family_results": [item.semantic_dict() for item in family_results],
    }
    return DerivedStateComparison(
        _token=_COMPARISON_TOKEN,
        requested_manifest=requested,
        established_manifest=established,
        status=status,
        family_results=family_results,
        comparison_ref=_sha(DERIVED_STATE_COMPARISON_REF_PREFIX, payload),
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def build_analysis_state_identity_from_derived_state(
    *,
    comparison: DerivedStateComparison,
    state_basis_refs: Sequence[str],
    provenance_refs: Sequence[str] = (),
) -> AnalysisStateIdentity:
    """Bind exact matched B4A state to the existing B1 execution-state seam only."""
    if not isinstance(comparison, DerivedStateComparison):
        raise TypeError("comparison must be DerivedStateComparison")
    return build_analysis_state_identity(
        source_model_ref=comparison.established_manifest.source_model_ref,
        execution_state_ref=comparison.require_established_state_ref(),
        state_basis_refs=_refs(state_basis_refs, "state_basis_ref", required=True),
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


__all__ = [
    "DERIVED_STATE_COMPARISON_CONTRACT",
    "DERIVED_STATE_CONTRACT",
    "ESTABLISHED_STATE_MANIFEST_CONTRACT",
    "REQUESTED_STATE_MANIFEST_CONTRACT",
    "DerivedStateComparison",
    "DerivedStateComparisonError",
    "DerivedStateComparisonStatus",
    "DerivedStateError",
    "DerivedStateEstablishmentStatus",
    "DerivedStateFamily",
    "DerivedStateFamilyClassification",
    "EstablishedDerivedState",
    "EstablishedDerivedStateManifest",
    "NormalizationContract",
    "NumericTolerance",
    "RequestedDerivedState",
    "RequestedDerivedStateManifest",
    "STATE_FAMILY_CLASSIFICATION",
    "SequenceOrdering",
    "build_analysis_state_identity_from_derived_state",
    "compare_derived_state_entries",
    "compare_derived_state_manifests",
    "record_derived_state_readback_failure",
    "request_derived_state",
    "state_family_classification",
]
