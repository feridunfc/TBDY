"""Fail-closed causal analysis-lineage contracts.

This module owns identity/qualification vocabulary only.  It does not read or
mutate ETABS, run analysis, materialize regulatory inputs, or make engineering
decisions.

A naked ``AnalysisStateIdentity`` or ``AnalysisResultIdentity`` is not trusted
engineering input.  Trust is represented only by a factory-created
``AnalysisLineageQualification``.  B1 intentionally exposes no public positive
issuer because the current read-only ETABS surface cannot prove which analysis
execution generated pre-existing results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Mapping, Sequence


ANALYSIS_STATE_IDENTITY_CONTRACT = "TBDY_ANALYSIS_STATE_IDENTITY_V1"
ANALYSIS_RESULT_IDENTITY_CONTRACT = "TBDY_ANALYSIS_RESULT_IDENTITY_V1"
ANALYSIS_LINEAGE_QUALIFICATION_CONTRACT = "TBDY_ANALYSIS_LINEAGE_QUALIFICATION_V1"
_VERIFIED_EXECUTION_PROOF_CONTRACT = "TBDY_VERIFIED_ANALYSIS_EXECUTION_CAUSAL_PROOF_V1"

ANALYSIS_STATE_REF_PREFIX = "analysis-state:sha256:"
ANALYSIS_RESULT_REF_PREFIX = "analysis-result:sha256:"
ANALYSIS_LINEAGE_REF_PREFIX = "analysis-lineage-qualification:sha256:"

_QUALIFICATION_FACTORY_TOKEN = object()
_EXECUTION_PROOF_FACTORY_TOKEN = object()


class AnalysisLineageError(ValueError):
    pass


class AnalysisLineageQualificationError(AnalysisLineageError):
    pass


class AnalysisLineageQualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AnalysisLineageError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    result = tuple(sorted({_text(item, label) for item in values}))
    if required and not result:
        raise AnalysisLineageError(f"{label} must be nonempty")
    return result


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha_ref(prefix: str, payload: Mapping[str, object]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _sha_identity(value: str, prefix: str, label: str) -> str:
    value = _text(value, label)
    if not value.startswith(prefix):
        raise AnalysisLineageError(f"{label} must use {prefix}<sha256> form")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise AnalysisLineageError(f"{label} must contain a lowercase sha256 digest")
    return value


def _state_ref(
    source_model_ref: str,
    execution_state_ref: str,
    state_basis_refs: Sequence[str],
) -> str:
    return _sha_ref(
        ANALYSIS_STATE_REF_PREFIX,
        {
            "contract": ANALYSIS_STATE_IDENTITY_CONTRACT,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "execution_state_ref": _text(execution_state_ref, "execution_state_ref"),
            "state_basis_refs": list(_refs(state_basis_refs, "state_basis_ref", required=True)),
        },
    )


def _result_ref(
    source_model_ref: str,
    parent_analysis_state_ref: str,
    analysis_generation_ref: str,
    result_scope_refs: Sequence[str],
) -> str:
    return _sha_ref(
        ANALYSIS_RESULT_REF_PREFIX,
        {
            "contract": ANALYSIS_RESULT_IDENTITY_CONTRACT,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "parent_analysis_state_ref": _sha_identity(
                parent_analysis_state_ref,
                ANALYSIS_STATE_REF_PREFIX,
                "parent_analysis_state_ref",
            ),
            "analysis_generation_ref": _text(analysis_generation_ref, "analysis_generation_ref"),
            "result_scope_refs": list(_refs(result_scope_refs, "result_scope_ref", required=True)),
        },
    )


@dataclass(frozen=True, slots=True)
class AnalysisStateIdentity:
    """Exact analysis-affecting state identity, not proof of result freshness.

    ``source_model_ref`` preserves root provenance. ``execution_state_ref`` is
    deliberately separate so B4 may later bind a derived state without changing
    SourceModelIdentity semantics. EvidenceEpoch is not an identity field.
    """

    identity_ref: str
    source_model_ref: str
    execution_state_ref: str
    state_basis_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    contract: str = ANALYSIS_STATE_IDENTITY_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "identity_ref",
            _sha_identity(self.identity_ref, ANALYSIS_STATE_REF_PREFIX, "identity_ref"),
        )
        object.__setattr__(self, "source_model_ref", _text(self.source_model_ref, "source_model_ref"))
        object.__setattr__(self, "execution_state_ref", _text(self.execution_state_ref, "execution_state_ref"))
        object.__setattr__(self, "state_basis_refs", _refs(self.state_basis_refs, "state_basis_ref", required=True))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))
        if self.contract != ANALYSIS_STATE_IDENTITY_CONTRACT:
            raise AnalysisLineageError("analysis-state identity contract mismatch")
        if self.identity_ref != _state_ref(
            self.source_model_ref,
            self.execution_state_ref,
            self.state_basis_refs,
        ):
            raise AnalysisLineageError("analysis-state identity_ref does not match identity fields")

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "identity_ref": self.identity_ref,
            "source_model_ref": self.source_model_ref,
            "execution_state_ref": self.execution_state_ref,
            "state_basis_refs": list(self.state_basis_refs),
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class AnalysisResultIdentity:
    """One result generation parented by exactly one AnalysisStateIdentity.

    The object is deliberately not self-authenticating.  Its generation field
    becomes trusted only when a later controlled-analysis issuer proves the
    causal execution.  Row hashes, acquisition ids and case status cannot do so.
    """

    identity_ref: str
    source_model_ref: str
    parent_analysis_state_ref: str
    analysis_generation_ref: str
    result_scope_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    contract: str = ANALYSIS_RESULT_IDENTITY_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity_ref", _sha_identity(self.identity_ref, ANALYSIS_RESULT_REF_PREFIX, "identity_ref"))
        object.__setattr__(self, "source_model_ref", _text(self.source_model_ref, "source_model_ref"))
        object.__setattr__(
            self,
            "parent_analysis_state_ref",
            _sha_identity(
                self.parent_analysis_state_ref,
                ANALYSIS_STATE_REF_PREFIX,
                "parent_analysis_state_ref",
            ),
        )
        object.__setattr__(self, "analysis_generation_ref", _text(self.analysis_generation_ref, "analysis_generation_ref"))
        object.__setattr__(self, "result_scope_refs", _refs(self.result_scope_refs, "result_scope_ref", required=True))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))
        if self.contract != ANALYSIS_RESULT_IDENTITY_CONTRACT:
            raise AnalysisLineageError("analysis-result identity contract mismatch")
        if self.identity_ref != _result_ref(
            self.source_model_ref,
            self.parent_analysis_state_ref,
            self.analysis_generation_ref,
            self.result_scope_refs,
        ):
            raise AnalysisLineageError("analysis-result identity_ref does not match identity fields")

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "identity_ref": self.identity_ref,
            "source_model_ref": self.source_model_ref,
            "parent_analysis_state_ref": self.parent_analysis_state_ref,
            "analysis_generation_ref": self.analysis_generation_ref,
            "result_scope_refs": list(self.result_scope_refs),
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class _VerifiedAnalysisExecutionProof:
    """Private proof shape reserved for a future controlled RunAnalysis issuer."""

    proof_ref: str
    source_model_ref: str
    execution_state_ref: str
    analysis_state_ref: str
    analysis_result_ref: str
    analysis_generation_ref: str
    provenance_refs: tuple[str, ...]
    contract: str

    def __init__(
        self,
        *,
        _token: object = None,
        proof_ref: str,
        source_model_ref: str,
        execution_state_ref: str,
        analysis_state_ref: str,
        analysis_result_ref: str,
        analysis_generation_ref: str,
        provenance_refs: tuple[str, ...],
        contract: str = _VERIFIED_EXECUTION_PROOF_CONTRACT,
    ) -> None:
        if _token is not _EXECUTION_PROOF_FACTORY_TOKEN:
            raise TypeError("verified analysis-execution proof is issuer-created only")
        if contract != _VERIFIED_EXECUTION_PROOF_CONTRACT:
            raise AnalysisLineageError("analysis-execution proof contract mismatch")
        object.__setattr__(self, "proof_ref", _text(proof_ref, "proof_ref"))
        object.__setattr__(self, "source_model_ref", _text(source_model_ref, "source_model_ref"))
        object.__setattr__(self, "execution_state_ref", _text(execution_state_ref, "execution_state_ref"))
        object.__setattr__(self, "analysis_state_ref", _sha_identity(analysis_state_ref, ANALYSIS_STATE_REF_PREFIX, "analysis_state_ref"))
        object.__setattr__(self, "analysis_result_ref", _sha_identity(analysis_result_ref, ANALYSIS_RESULT_REF_PREFIX, "analysis_result_ref"))
        object.__setattr__(self, "analysis_generation_ref", _text(analysis_generation_ref, "analysis_generation_ref"))
        object.__setattr__(self, "provenance_refs", _refs(provenance_refs, "proof_provenance_ref", required=True))
        object.__setattr__(self, "contract", contract)


def _qualification_ref(
    status: AnalysisLineageQualificationStatus,
    source_model_ref: str,
    analysis_state: AnalysisStateIdentity | None,
    analysis_result: AnalysisResultIdentity | None,
    qualification_provenance_refs: Sequence[str],
    capture_provenance_refs: Sequence[str],
    blockers: Sequence[str],
) -> str:
    return _sha_ref(
        ANALYSIS_LINEAGE_REF_PREFIX,
        {
            "contract": ANALYSIS_LINEAGE_QUALIFICATION_CONTRACT,
            "status": status.value,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "analysis_state_ref": None if analysis_state is None else analysis_state.identity_ref,
            "analysis_result_ref": None if analysis_result is None else analysis_result.identity_ref,
            # Capture/EvidenceEpoch refs are provenance only; they do not define
            # AnalysisStateIdentity or AnalysisResultIdentity sameness.
            "qualification_provenance_refs": list(_refs(qualification_provenance_refs, "qualification_provenance_ref", required=True)),
            "capture_provenance_refs": list(_refs(capture_provenance_refs, "capture_provenance_ref")),
            "blockers": list(_refs(blockers, "blocker")),
        },
    )


@dataclass(frozen=True, slots=True, init=False)
class AnalysisLineageQualification:
    """Factory-owned trust decision; the only B1 artifact exposing qualified results."""

    status: AnalysisLineageQualificationStatus
    source_model_ref: str
    analysis_state: AnalysisStateIdentity | None
    analysis_result: AnalysisResultIdentity | None
    qualification_ref: str
    qualification_provenance_refs: tuple[str, ...]
    capture_provenance_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    contract: str

    def __init__(
        self,
        *,
        _token: object = None,
        status: AnalysisLineageQualificationStatus,
        source_model_ref: str,
        analysis_state: AnalysisStateIdentity | None,
        analysis_result: AnalysisResultIdentity | None,
        qualification_ref: str,
        qualification_provenance_refs: tuple[str, ...],
        capture_provenance_refs: tuple[str, ...],
        blockers: tuple[str, ...],
        contract: str = ANALYSIS_LINEAGE_QUALIFICATION_CONTRACT,
    ) -> None:
        if _token is not _QUALIFICATION_FACTORY_TOKEN:
            raise TypeError(
                "AnalysisLineageQualification is factory-created only; "
                "use build_unqualified_analysis_lineage or a future verified-execution issuer"
            )
        if not isinstance(status, AnalysisLineageQualificationStatus):
            raise TypeError("status must be AnalysisLineageQualificationStatus")
        if contract != ANALYSIS_LINEAGE_QUALIFICATION_CONTRACT:
            raise AnalysisLineageError("analysis-lineage qualification contract mismatch")
        source_model_ref = _text(source_model_ref, "source_model_ref")
        qrefs = _refs(qualification_provenance_refs, "qualification_provenance_ref", required=True)
        crefs = _refs(capture_provenance_refs, "capture_provenance_ref")
        blockers = _refs(blockers, "blocker")

        if status is AnalysisLineageQualificationStatus.QUALIFIED:
            if not isinstance(analysis_state, AnalysisStateIdentity):
                raise AnalysisLineageQualificationError("QUALIFIED requires AnalysisStateIdentity")
            if not isinstance(analysis_result, AnalysisResultIdentity):
                raise AnalysisLineageQualificationError("QUALIFIED requires AnalysisResultIdentity")
            if blockers:
                raise AnalysisLineageQualificationError("QUALIFIED cannot contain blockers")
            if analysis_state.source_model_ref != source_model_ref or analysis_result.source_model_ref != source_model_ref:
                raise AnalysisLineageQualificationError("qualified source/root lineage mismatch")
            if analysis_result.parent_analysis_state_ref != analysis_state.identity_ref:
                raise AnalysisLineageQualificationError("analysis result parent state mismatch")
        else:
            if analysis_result is not None:
                raise AnalysisLineageQualificationError("UNQUALIFIED must not expose AnalysisResultIdentity")
            if not blockers:
                raise AnalysisLineageQualificationError("UNQUALIFIED requires at least one blocker")
            if analysis_state is not None and not isinstance(analysis_state, AnalysisStateIdentity):
                raise TypeError("analysis_state must be AnalysisStateIdentity or None")
            if analysis_state is not None and analysis_state.source_model_ref != source_model_ref:
                raise AnalysisLineageQualificationError("unqualified source/root lineage mismatch")

        expected = _qualification_ref(status, source_model_ref, analysis_state, analysis_result, qrefs, crefs, blockers)
        if qualification_ref != expected:
            raise AnalysisLineageError("qualification_ref does not match qualification fields")

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source_model_ref", source_model_ref)
        object.__setattr__(self, "analysis_state", analysis_state)
        object.__setattr__(self, "analysis_result", analysis_result)
        object.__setattr__(self, "qualification_ref", qualification_ref)
        object.__setattr__(self, "qualification_provenance_refs", qrefs)
        object.__setattr__(self, "capture_provenance_refs", crefs)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "contract", contract)

    @property
    def qualified(self) -> bool:
        return self.status is AnalysisLineageQualificationStatus.QUALIFIED

    def require_qualified_result(self) -> AnalysisResultIdentity:
        if not self.qualified or self.analysis_result is None:
            raise AnalysisLineageQualificationError("analysis result lineage is not qualified")
        return self.analysis_result

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "status": self.status.value,
            "source_model_ref": self.source_model_ref,
            "analysis_state": None if self.analysis_state is None else self.analysis_state.as_dict(),
            "analysis_result": None if self.analysis_result is None else self.analysis_result.as_dict(),
            "qualification_ref": self.qualification_ref,
            "qualification_provenance_refs": list(self.qualification_provenance_refs),
            "capture_provenance_refs": list(self.capture_provenance_refs),
            "blockers": list(self.blockers),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


def build_analysis_state_identity(
    *,
    source_model_ref: str,
    execution_state_ref: str,
    state_basis_refs: Sequence[str],
    provenance_refs: Sequence[str] = (),
) -> AnalysisStateIdentity:
    """Build a deterministic naked state identity; it grants no result trust."""
    basis = _refs(state_basis_refs, "state_basis_ref", required=True)
    return AnalysisStateIdentity(
        identity_ref=_state_ref(source_model_ref, execution_state_ref, basis),
        source_model_ref=source_model_ref,
        execution_state_ref=execution_state_ref,
        state_basis_refs=basis,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def build_analysis_result_identity(
    *,
    source_model_ref: str,
    parent_analysis_state_ref: str,
    analysis_generation_ref: str,
    result_scope_refs: Sequence[str],
    provenance_refs: Sequence[str] = (),
) -> AnalysisResultIdentity:
    """Build a deterministic naked result identity; it does not prove causation."""
    scopes = _refs(result_scope_refs, "result_scope_ref", required=True)
    return AnalysisResultIdentity(
        identity_ref=_result_ref(
            source_model_ref,
            parent_analysis_state_ref,
            analysis_generation_ref,
            scopes,
        ),
        source_model_ref=source_model_ref,
        parent_analysis_state_ref=parent_analysis_state_ref,
        analysis_generation_ref=analysis_generation_ref,
        result_scope_refs=scopes,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def build_unqualified_analysis_lineage(
    *,
    source_model_ref: str,
    blockers: Sequence[str],
    qualification_provenance_refs: Sequence[str],
    analysis_state: AnalysisStateIdentity | None = None,
    capture_provenance_refs: Sequence[str] = (),
) -> AnalysisLineageQualification:
    """Return a fail-closed qualification with no usable result identity."""
    if analysis_state is not None and not isinstance(analysis_state, AnalysisStateIdentity):
        raise TypeError("analysis_state must be AnalysisStateIdentity or None")
    blockers = _refs(blockers, "blocker", required=True)
    qrefs = _refs(qualification_provenance_refs, "qualification_provenance_ref", required=True)
    crefs = _refs(capture_provenance_refs, "capture_provenance_ref")
    status = AnalysisLineageQualificationStatus.UNQUALIFIED
    return AnalysisLineageQualification(
        _token=_QUALIFICATION_FACTORY_TOKEN,
        status=status,
        source_model_ref=source_model_ref,
        analysis_state=analysis_state,
        analysis_result=None,
        qualification_ref=_qualification_ref(status, source_model_ref, analysis_state, None, qrefs, crefs, blockers),
        qualification_provenance_refs=qrefs,
        capture_provenance_refs=crefs,
        blockers=blockers,
    )


def _build_qualified_analysis_lineage(
    *,
    _token: object,
    analysis_state: AnalysisStateIdentity,
    analysis_result: AnalysisResultIdentity,
    execution_proof: _VerifiedAnalysisExecutionProof,
    qualification_provenance_refs: Sequence[str],
    capture_provenance_refs: Sequence[str] = (),
) -> AnalysisLineageQualification:
    """Private primitive reserved for a future verified controlled-analysis issuer."""
    if _token is not _QUALIFICATION_FACTORY_TOKEN:
        raise TypeError("qualified analysis lineage is issuer-created only")
    if not isinstance(analysis_state, AnalysisStateIdentity):
        raise TypeError("analysis_state must be AnalysisStateIdentity")
    if not isinstance(analysis_result, AnalysisResultIdentity):
        raise TypeError("analysis_result must be AnalysisResultIdentity")
    if not isinstance(execution_proof, _VerifiedAnalysisExecutionProof):
        raise TypeError("execution_proof must be a verified causal execution proof")

    if analysis_result.parent_analysis_state_ref != analysis_state.identity_ref:
        raise AnalysisLineageQualificationError("analysis result parent state mismatch")
    if analysis_state.source_model_ref != analysis_result.source_model_ref:
        raise AnalysisLineageQualificationError("analysis state/result source root mismatch")
    if execution_proof.source_model_ref != analysis_state.source_model_ref:
        raise AnalysisLineageQualificationError("execution proof source root mismatch")
    if execution_proof.execution_state_ref != analysis_state.execution_state_ref:
        raise AnalysisLineageQualificationError("execution proof state binding mismatch")
    if execution_proof.analysis_state_ref != analysis_state.identity_ref:
        raise AnalysisLineageQualificationError("execution proof analysis-state identity mismatch")
    if execution_proof.analysis_result_ref != analysis_result.identity_ref:
        raise AnalysisLineageQualificationError("execution proof analysis-result identity mismatch")
    if execution_proof.analysis_generation_ref != analysis_result.analysis_generation_ref:
        raise AnalysisLineageQualificationError("execution proof analysis-generation mismatch")

    qrefs = _refs(
        (*qualification_provenance_refs, execution_proof.proof_ref, *execution_proof.provenance_refs),
        "qualification_provenance_ref",
        required=True,
    )
    crefs = _refs(capture_provenance_refs, "capture_provenance_ref")
    status = AnalysisLineageQualificationStatus.QUALIFIED
    return AnalysisLineageQualification(
        _token=_QUALIFICATION_FACTORY_TOKEN,
        status=status,
        source_model_ref=analysis_state.source_model_ref,
        analysis_state=analysis_state,
        analysis_result=analysis_result,
        qualification_ref=_qualification_ref(status, analysis_state.source_model_ref, analysis_state, analysis_result, qrefs, crefs, ()),
        qualification_provenance_refs=qrefs,
        capture_provenance_refs=crefs,
        blockers=(),
    )


__all__ = [
    "ANALYSIS_LINEAGE_QUALIFICATION_CONTRACT",
    "ANALYSIS_RESULT_IDENTITY_CONTRACT",
    "ANALYSIS_STATE_IDENTITY_CONTRACT",
    "AnalysisLineageError",
    "AnalysisLineageQualification",
    "AnalysisLineageQualificationError",
    "AnalysisLineageQualificationStatus",
    "AnalysisResultIdentity",
    "AnalysisStateIdentity",
    "build_analysis_result_identity",
    "build_analysis_state_identity",
    "build_unqualified_analysis_lineage",
]
