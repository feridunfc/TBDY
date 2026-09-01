"""Fail-closed causal concrete-design lineage contracts.

This module is the single B2 design-lineage authority layered above the
existing B1 analysis-lineage contract.  It defines deterministic design-state
and design-result identities plus qualification vocabulary.  It performs no
analysis or design execution, factual acquisition, engineering selection, or
reporting.

A naked ``DesignStateIdentity`` or ``DesignResultIdentity`` is not trusted
engineering input.  Positive qualification is reserved for a private proof
seam that a future controlled-design lifecycle owner may use only after
establishing the complete causal execution proof.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Mapping, Sequence

from tbdy_engine.integration.etabs_analysis_lineage import (
    AnalysisLineageQualification,
    AnalysisLineageQualificationError,
    AnalysisResultIdentity,
)


DESIGN_STATE_IDENTITY_CONTRACT = "TBDY_DESIGN_STATE_IDENTITY_V1"
DESIGN_RESULT_IDENTITY_CONTRACT = "TBDY_DESIGN_RESULT_IDENTITY_V1"
DESIGN_LINEAGE_QUALIFICATION_CONTRACT = "TBDY_DESIGN_LINEAGE_QUALIFICATION_V1"
_VERIFIED_DESIGN_EXECUTION_PROOF_CONTRACT = "TBDY_VERIFIED_DESIGN_EXECUTION_CAUSAL_PROOF_V1"

DESIGN_STATE_REF_PREFIX = "design-state:sha256:"
DESIGN_RESULT_REF_PREFIX = "design-result:sha256:"
DESIGN_LINEAGE_REF_PREFIX = "design-lineage-qualification:sha256:"
_DESIGN_EXECUTION_PROOF_REF_PREFIX = "design-execution-proof:sha256:"

_DESIGN_QUALIFICATION_FACTORY_TOKEN = object()
_DESIGN_EXECUTION_PROOF_FACTORY_TOKEN = object()


class DesignLineageError(ValueError):
    pass


class DesignLineageQualificationError(DesignLineageError):
    pass


class DesignLineageQualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise DesignLineageError(f"{label} must be a nonblank canonical string")
    return value


def _refs(
    values: Sequence[str],
    label: str,
    *,
    required: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    refs = tuple(sorted({_text(item, label) for item in values}))
    if required and not refs:
        raise DesignLineageError(f"{label} must be nonempty")
    return refs


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
        raise DesignLineageError(f"{label} must use {prefix}<sha256> form")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise DesignLineageError(f"{label} must contain a lowercase sha256 digest")
    return value


def _analysis_result_from_qualified(
    analysis_lineage: AnalysisLineageQualification,
) -> AnalysisResultIdentity:
    if not isinstance(analysis_lineage, AnalysisLineageQualification):
        raise TypeError("analysis_lineage must be AnalysisLineageQualification")
    try:
        result = analysis_lineage.require_qualified_result()
    except AnalysisLineageQualificationError as exc:
        raise DesignLineageQualificationError(
            "design lineage requires a QUALIFIED parent AnalysisResultIdentity"
        ) from exc
    if not isinstance(result, AnalysisResultIdentity):
        raise DesignLineageQualificationError(
            "qualified analysis lineage did not expose AnalysisResultIdentity"
        )
    return result


def _design_state_ref(
    *,
    source_model_ref: str,
    parent_analysis_result_ref: str,
    design_code_ref: str,
    design_domain_ref: str,
    design_procedure_ref: str,
    selected_design_combo_population_ref: str,
    combo_definition_population_refs: Sequence[str],
    combo_grain_binding_refs: Sequence[str],
    design_component_population_refs: Sequence[str],
    design_option_refs: Sequence[str],
    state_basis_refs: Sequence[str],
) -> str:
    """Return the semantic causal design-state identity.

    Analysis qualification, model-fingerprint, EvidenceEpoch, and observation
    provenance deliberately do not participate in state sameness.  They remain
    binding evidence that positive design-lineage qualification must verify.
    """
    return _sha_ref(
        DESIGN_STATE_REF_PREFIX,
        {
            "contract": DESIGN_STATE_IDENTITY_CONTRACT,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "parent_analysis_result_ref": _text(
                parent_analysis_result_ref,
                "parent_analysis_result_ref",
            ),
            "design_code_ref": _text(design_code_ref, "design_code_ref"),
            "design_domain_ref": _text(design_domain_ref, "design_domain_ref"),
            "design_procedure_ref": _text(
                design_procedure_ref,
                "design_procedure_ref",
            ),
            "selected_design_combo_population_ref": _text(
                selected_design_combo_population_ref,
                "selected_design_combo_population_ref",
            ),
            "combo_definition_population_refs": list(
                _refs(
                    combo_definition_population_refs,
                    "combo_definition_population_ref",
                    required=True,
                )
            ),
            "combo_grain_binding_refs": list(
                _refs(
                    combo_grain_binding_refs,
                    "combo_grain_binding_ref",
                    required=True,
                )
            ),
            "design_component_population_refs": list(
                _refs(
                    design_component_population_refs,
                    "design_component_population_ref",
                    required=True,
                )
            ),
            "design_option_refs": list(
                _refs(design_option_refs, "design_option_ref")
            ),
            "state_basis_refs": list(
                _refs(state_basis_refs, "state_basis_ref", required=True)
            ),
        },
    )


@dataclass(frozen=True, slots=True)
class DesignStateIdentity:
    """Semantic design state plus non-identity qualification/binding evidence."""

    identity_ref: str
    source_model_ref: str
    parent_analysis_result_ref: str
    analysis_lineage_qualification_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    design_code_ref: str
    design_domain_ref: str
    design_procedure_ref: str
    selected_design_combo_population_ref: str
    combo_definition_population_refs: tuple[str, ...]
    combo_grain_binding_refs: tuple[str, ...]
    design_component_population_refs: tuple[str, ...]
    design_option_refs: tuple[str, ...] = field(default_factory=tuple)
    state_basis_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    contract: str = DESIGN_STATE_IDENTITY_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "identity_ref",
            _sha_identity(self.identity_ref, DESIGN_STATE_REF_PREFIX, "identity_ref"),
        )
        for name in (
            "source_model_ref",
            "parent_analysis_result_ref",
            "analysis_lineage_qualification_ref",
            "model_fingerprint",
            "evidence_epoch_id",
            "design_code_ref",
            "design_domain_ref",
            "design_procedure_ref",
            "selected_design_combo_population_ref",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self,
            "combo_definition_population_refs",
            _refs(
                self.combo_definition_population_refs,
                "combo_definition_population_ref",
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "combo_grain_binding_refs",
            _refs(
                self.combo_grain_binding_refs,
                "combo_grain_binding_ref",
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "design_component_population_refs",
            _refs(
                self.design_component_population_refs,
                "design_component_population_ref",
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "design_option_refs",
            _refs(self.design_option_refs, "design_option_ref"),
        )
        object.__setattr__(
            self,
            "state_basis_refs",
            _refs(self.state_basis_refs, "state_basis_ref", required=True),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs(self.provenance_refs, "provenance_ref"),
        )
        if self.contract != DESIGN_STATE_IDENTITY_CONTRACT:
            raise DesignLineageError("design-state identity contract mismatch")
        expected = _design_state_ref(
            source_model_ref=self.source_model_ref,
            parent_analysis_result_ref=self.parent_analysis_result_ref,
            design_code_ref=self.design_code_ref,
            design_domain_ref=self.design_domain_ref,
            design_procedure_ref=self.design_procedure_ref,
            selected_design_combo_population_ref=self.selected_design_combo_population_ref,
            combo_definition_population_refs=self.combo_definition_population_refs,
            combo_grain_binding_refs=self.combo_grain_binding_refs,
            design_component_population_refs=self.design_component_population_refs,
            design_option_refs=self.design_option_refs,
            state_basis_refs=self.state_basis_refs,
        )
        if self.identity_ref != expected:
            raise DesignLineageError(
                "design-state identity_ref does not match identity fields"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "identity_ref": self.identity_ref,
            "source_model_ref": self.source_model_ref,
            "parent_analysis_result_ref": self.parent_analysis_result_ref,
            "analysis_lineage_qualification_ref": self.analysis_lineage_qualification_ref,
            "model_fingerprint": self.model_fingerprint,
            "evidence_epoch_id": self.evidence_epoch_id,
            "design_code_ref": self.design_code_ref,
            "design_domain_ref": self.design_domain_ref,
            "design_procedure_ref": self.design_procedure_ref,
            "selected_design_combo_population_ref": self.selected_design_combo_population_ref,
            "combo_definition_population_refs": list(
                self.combo_definition_population_refs
            ),
            "combo_grain_binding_refs": list(self.combo_grain_binding_refs),
            "design_component_population_refs": list(
                self.design_component_population_refs
            ),
            "design_option_refs": list(self.design_option_refs),
            "state_basis_refs": list(self.state_basis_refs),
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


def build_design_state_identity(
    *,
    analysis_lineage: AnalysisLineageQualification,
    model_fingerprint: str,
    evidence_epoch_id: str,
    design_code_ref: str,
    design_domain_ref: str,
    design_procedure_ref: str,
    selected_design_combo_population_ref: str,
    combo_definition_population_refs: Sequence[str],
    combo_grain_binding_refs: Sequence[str],
    design_component_population_refs: Sequence[str],
    state_basis_refs: Sequence[str],
    design_option_refs: Sequence[str] = (),
    provenance_refs: Sequence[str] = (),
) -> DesignStateIdentity:
    """Build semantic state while retaining non-identity qualification evidence.

    The returned identity is deterministic but is not a positive design-result
    qualification. Exact P8A/W7 combo-grain bindings are consumed as opaque,
    already-reviewed references and are never inferred or broadcast here.
    Analysis qualification, model fingerprint, and EvidenceEpoch are retained
    only as later qualification/binding evidence and do not define state
    identity.
    """
    parent_result = _analysis_result_from_qualified(analysis_lineage)
    kwargs = {
        "source_model_ref": parent_result.source_model_ref,
        "parent_analysis_result_ref": parent_result.identity_ref,
        "analysis_lineage_qualification_ref": analysis_lineage.qualification_ref,
        "model_fingerprint": _text(model_fingerprint, "model_fingerprint"),
        "evidence_epoch_id": _text(evidence_epoch_id, "evidence_epoch_id"),
        "design_code_ref": _text(design_code_ref, "design_code_ref"),
        "design_domain_ref": _text(design_domain_ref, "design_domain_ref"),
        "design_procedure_ref": _text(
            design_procedure_ref,
            "design_procedure_ref",
        ),
        "selected_design_combo_population_ref": _text(
            selected_design_combo_population_ref,
            "selected_design_combo_population_ref",
        ),
        "combo_definition_population_refs": _refs(
            combo_definition_population_refs,
            "combo_definition_population_ref",
            required=True,
        ),
        "combo_grain_binding_refs": _refs(
            combo_grain_binding_refs,
            "combo_grain_binding_ref",
            required=True,
        ),
        "design_component_population_refs": _refs(
            design_component_population_refs,
            "design_component_population_ref",
            required=True,
        ),
        "design_option_refs": _refs(design_option_refs, "design_option_ref"),
        "state_basis_refs": _refs(
            state_basis_refs,
            "state_basis_ref",
            required=True,
        ),
    }
    identity_ref = _design_state_ref(
        source_model_ref=kwargs["source_model_ref"],
        parent_analysis_result_ref=kwargs["parent_analysis_result_ref"],
        design_code_ref=kwargs["design_code_ref"],
        design_domain_ref=kwargs["design_domain_ref"],
        design_procedure_ref=kwargs["design_procedure_ref"],
        selected_design_combo_population_ref=kwargs[
            "selected_design_combo_population_ref"
        ],
        combo_definition_population_refs=kwargs["combo_definition_population_refs"],
        combo_grain_binding_refs=kwargs["combo_grain_binding_refs"],
        design_component_population_refs=kwargs["design_component_population_refs"],
        design_option_refs=kwargs["design_option_refs"],
        state_basis_refs=kwargs["state_basis_refs"],
    )
    return DesignStateIdentity(
        identity_ref=identity_ref,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
        **kwargs,
    )


def _design_result_ref(
    *,
    source_model_ref: str,
    parent_design_state_ref: str,
    parent_analysis_result_ref: str,
    design_generation_ref: str,
    result_scope_refs: Sequence[str],
) -> str:
    return _sha_ref(
        DESIGN_RESULT_REF_PREFIX,
        {
            "contract": DESIGN_RESULT_IDENTITY_CONTRACT,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "parent_design_state_ref": _sha_identity(
                parent_design_state_ref,
                DESIGN_STATE_REF_PREFIX,
                "parent_design_state_ref",
            ),
            "parent_analysis_result_ref": _text(
                parent_analysis_result_ref,
                "parent_analysis_result_ref",
            ),
            "design_generation_ref": _text(
                design_generation_ref,
                "design_generation_ref",
            ),
            "result_scope_refs": list(
                _refs(result_scope_refs, "result_scope_ref", required=True)
            ),
        },
    )


@dataclass(frozen=True, slots=True)
class DesignResultIdentity:
    """One candidate design-result generation; existence does not prove causation."""

    identity_ref: str
    source_model_ref: str
    parent_design_state_ref: str
    parent_analysis_result_ref: str
    design_generation_ref: str
    result_scope_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)
    contract: str = DESIGN_RESULT_IDENTITY_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "identity_ref",
            _sha_identity(self.identity_ref, DESIGN_RESULT_REF_PREFIX, "identity_ref"),
        )
        object.__setattr__(
            self,
            "source_model_ref",
            _text(self.source_model_ref, "source_model_ref"),
        )
        object.__setattr__(
            self,
            "parent_design_state_ref",
            _sha_identity(
                self.parent_design_state_ref,
                DESIGN_STATE_REF_PREFIX,
                "parent_design_state_ref",
            ),
        )
        object.__setattr__(
            self,
            "parent_analysis_result_ref",
            _text(self.parent_analysis_result_ref, "parent_analysis_result_ref"),
        )
        object.__setattr__(
            self,
            "design_generation_ref",
            _text(self.design_generation_ref, "design_generation_ref"),
        )
        object.__setattr__(
            self,
            "result_scope_refs",
            _refs(self.result_scope_refs, "result_scope_ref", required=True),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs(self.provenance_refs, "provenance_ref"),
        )
        if self.contract != DESIGN_RESULT_IDENTITY_CONTRACT:
            raise DesignLineageError("design-result identity contract mismatch")
        expected = _design_result_ref(
            source_model_ref=self.source_model_ref,
            parent_design_state_ref=self.parent_design_state_ref,
            parent_analysis_result_ref=self.parent_analysis_result_ref,
            design_generation_ref=self.design_generation_ref,
            result_scope_refs=self.result_scope_refs,
        )
        if self.identity_ref != expected:
            raise DesignLineageError(
                "design-result identity_ref does not match identity fields"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "identity_ref": self.identity_ref,
            "source_model_ref": self.source_model_ref,
            "parent_design_state_ref": self.parent_design_state_ref,
            "parent_analysis_result_ref": self.parent_analysis_result_ref,
            "design_generation_ref": self.design_generation_ref,
            "result_scope_refs": list(self.result_scope_refs),
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


def build_design_result_identity(
    *,
    design_state: DesignStateIdentity,
    design_generation_ref: str,
    result_scope_refs: Sequence[str],
    provenance_refs: Sequence[str] = (),
) -> DesignResultIdentity:
    """Build a naked candidate result identity; it grants no design-result trust."""
    if not isinstance(design_state, DesignStateIdentity):
        raise TypeError("design_state must be DesignStateIdentity")
    scopes = _refs(result_scope_refs, "result_scope_ref", required=True)
    generation = _text(design_generation_ref, "design_generation_ref")
    return DesignResultIdentity(
        identity_ref=_design_result_ref(
            source_model_ref=design_state.source_model_ref,
            parent_design_state_ref=design_state.identity_ref,
            parent_analysis_result_ref=design_state.parent_analysis_result_ref,
            design_generation_ref=generation,
            result_scope_refs=scopes,
        ),
        source_model_ref=design_state.source_model_ref,
        parent_design_state_ref=design_state.identity_ref,
        parent_analysis_result_ref=design_state.parent_analysis_result_ref,
        design_generation_ref=generation,
        result_scope_refs=scopes,
        provenance_refs=_refs(provenance_refs, "provenance_ref"),
    )


def _design_execution_proof_ref(
    *,
    source_model_ref: str,
    parent_analysis_result_ref: str,
    analysis_lineage_qualification_ref: str,
    model_fingerprint: str,
    evidence_epoch_id: str,
    design_state_ref: str,
    design_result_ref: str,
    design_attempt_ref: str,
    design_generation_ref: str,
    requested_result_scope_refs: Sequence[str],
    reconciled_result_scope_refs: Sequence[str],
    combo_grain_binding_refs: Sequence[str],
    provenance_refs: Sequence[str],
) -> str:
    return _sha_ref(
        _DESIGN_EXECUTION_PROOF_REF_PREFIX,
        {
            "contract": _VERIFIED_DESIGN_EXECUTION_PROOF_CONTRACT,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "parent_analysis_result_ref": _text(
                parent_analysis_result_ref,
                "parent_analysis_result_ref",
            ),
            "analysis_lineage_qualification_ref": _text(
                analysis_lineage_qualification_ref,
                "analysis_lineage_qualification_ref",
            ),
            "model_fingerprint": _text(model_fingerprint, "model_fingerprint"),
            "evidence_epoch_id": _text(evidence_epoch_id, "evidence_epoch_id"),
            "design_state_ref": _sha_identity(
                design_state_ref,
                DESIGN_STATE_REF_PREFIX,
                "design_state_ref",
            ),
            "design_result_ref": _sha_identity(
                design_result_ref,
                DESIGN_RESULT_REF_PREFIX,
                "design_result_ref",
            ),
            "design_attempt_ref": _text(design_attempt_ref, "design_attempt_ref"),
            "design_generation_ref": _text(
                design_generation_ref,
                "design_generation_ref",
            ),
            "requested_result_scope_refs": list(
                _refs(
                    requested_result_scope_refs,
                    "requested_result_scope_ref",
                    required=True,
                )
            ),
            "reconciled_result_scope_refs": list(
                _refs(
                    reconciled_result_scope_refs,
                    "reconciled_result_scope_ref",
                    required=True,
                )
            ),
            "combo_grain_binding_refs": list(
                _refs(
                    combo_grain_binding_refs,
                    "combo_grain_binding_ref",
                    required=True,
                )
            ),
            "provenance_refs": list(
                _refs(provenance_refs, "proof_provenance_ref", required=True)
            ),
        },
    )


@dataclass(frozen=True, slots=True, init=False)
class _VerifiedDesignExecutionProof:
    """Private complete-attempt proof shape reserved for the future B6 issuer."""

    proof_ref: str
    source_model_ref: str
    parent_analysis_result_ref: str
    analysis_lineage_qualification_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    design_state_ref: str
    design_result_ref: str
    design_attempt_ref: str
    design_generation_ref: str
    requested_result_scope_refs: tuple[str, ...]
    reconciled_result_scope_refs: tuple[str, ...]
    combo_grain_binding_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    contract: str

    def __init__(
        self,
        *,
        _token: object = None,
        proof_ref: str,
        source_model_ref: str,
        parent_analysis_result_ref: str,
        analysis_lineage_qualification_ref: str,
        model_fingerprint: str,
        evidence_epoch_id: str,
        design_state_ref: str,
        design_result_ref: str,
        design_attempt_ref: str,
        design_generation_ref: str,
        requested_result_scope_refs: tuple[str, ...],
        reconciled_result_scope_refs: tuple[str, ...],
        combo_grain_binding_refs: tuple[str, ...],
        provenance_refs: tuple[str, ...],
        contract: str = _VERIFIED_DESIGN_EXECUTION_PROOF_CONTRACT,
    ) -> None:
        if _token is not _DESIGN_EXECUTION_PROOF_FACTORY_TOKEN:
            raise TypeError("verified design-execution proof is issuer-created only")
        if contract != _VERIFIED_DESIGN_EXECUTION_PROOF_CONTRACT:
            raise DesignLineageError("design-execution proof contract mismatch")
        requested = _refs(
            requested_result_scope_refs,
            "requested_result_scope_ref",
            required=True,
        )
        reconciled = _refs(
            reconciled_result_scope_refs,
            "reconciled_result_scope_ref",
            required=True,
        )
        if reconciled != requested:
            raise DesignLineageQualificationError(
                "partial or failed design scope cannot create verified execution proof"
            )
        combo_refs = _refs(
            combo_grain_binding_refs,
            "combo_grain_binding_ref",
            required=True,
        )
        refs = _refs(provenance_refs, "proof_provenance_ref", required=True)
        values = {
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "parent_analysis_result_ref": _text(
                parent_analysis_result_ref,
                "parent_analysis_result_ref",
            ),
            "analysis_lineage_qualification_ref": _text(
                analysis_lineage_qualification_ref,
                "analysis_lineage_qualification_ref",
            ),
            "model_fingerprint": _text(model_fingerprint, "model_fingerprint"),
            "evidence_epoch_id": _text(evidence_epoch_id, "evidence_epoch_id"),
            "design_state_ref": _sha_identity(
                design_state_ref,
                DESIGN_STATE_REF_PREFIX,
                "design_state_ref",
            ),
            "design_result_ref": _sha_identity(
                design_result_ref,
                DESIGN_RESULT_REF_PREFIX,
                "design_result_ref",
            ),
            "design_attempt_ref": _text(design_attempt_ref, "design_attempt_ref"),
            "design_generation_ref": _text(
                design_generation_ref,
                "design_generation_ref",
            ),
            "requested_result_scope_refs": requested,
            "reconciled_result_scope_refs": reconciled,
            "combo_grain_binding_refs": combo_refs,
            "provenance_refs": refs,
        }
        expected = _design_execution_proof_ref(**values)
        if proof_ref != expected:
            raise DesignLineageError(
                "design-execution proof_ref does not match proof fields"
            )
        object.__setattr__(self, "proof_ref", proof_ref)
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "contract", contract)


def _qualification_ref(
    *,
    status: DesignLineageQualificationStatus,
    source_model_ref: str,
    parent_analysis_lineage: AnalysisLineageQualification | None,
    design_state: DesignStateIdentity | None,
    design_result: DesignResultIdentity | None,
    qualification_provenance_refs: Sequence[str],
    capture_provenance_refs: Sequence[str],
    blockers: Sequence[str],
) -> str:
    parent_result_ref = None
    parent_qualification_ref = None
    if parent_analysis_lineage is not None:
        parent_qualification_ref = parent_analysis_lineage.qualification_ref
        if parent_analysis_lineage.qualified:
            parent_result_ref = parent_analysis_lineage.require_qualified_result().identity_ref
    return _sha_ref(
        DESIGN_LINEAGE_REF_PREFIX,
        {
            "contract": DESIGN_LINEAGE_QUALIFICATION_CONTRACT,
            "status": status.value,
            "source_model_ref": _text(source_model_ref, "source_model_ref"),
            "parent_analysis_lineage_ref": parent_qualification_ref,
            "parent_analysis_result_ref": parent_result_ref,
            "design_state_ref": None if design_state is None else design_state.identity_ref,
            "design_result_ref": None if design_result is None else design_result.identity_ref,
            "qualification_provenance_refs": list(
                _refs(
                    qualification_provenance_refs,
                    "qualification_provenance_ref",
                    required=True,
                )
            ),
            "capture_provenance_refs": list(
                _refs(capture_provenance_refs, "capture_provenance_ref")
            ),
            "blockers": list(_refs(blockers, "blocker")),
        },
    )


@dataclass(frozen=True, slots=True, init=False)
class DesignLineageQualification:
    """Factory-owned design-lineage trust decision."""

    status: DesignLineageQualificationStatus
    source_model_ref: str
    parent_analysis_lineage: AnalysisLineageQualification | None
    design_state: DesignStateIdentity | None
    design_result: DesignResultIdentity | None
    qualification_ref: str
    qualification_provenance_refs: tuple[str, ...]
    capture_provenance_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    contract: str

    def __init__(
        self,
        *,
        _token: object = None,
        status: DesignLineageQualificationStatus,
        source_model_ref: str,
        parent_analysis_lineage: AnalysisLineageQualification | None,
        design_state: DesignStateIdentity | None,
        design_result: DesignResultIdentity | None,
        qualification_ref: str,
        qualification_provenance_refs: tuple[str, ...],
        capture_provenance_refs: tuple[str, ...],
        blockers: tuple[str, ...],
        contract: str = DESIGN_LINEAGE_QUALIFICATION_CONTRACT,
    ) -> None:
        if _token is not _DESIGN_QUALIFICATION_FACTORY_TOKEN:
            raise TypeError(
                "DesignLineageQualification is factory-created only; "
                "use build_unqualified_design_lineage or a future verified-design issuer"
            )
        if not isinstance(status, DesignLineageQualificationStatus):
            raise TypeError("status must be DesignLineageQualificationStatus")
        if contract != DESIGN_LINEAGE_QUALIFICATION_CONTRACT:
            raise DesignLineageError("design-lineage qualification contract mismatch")
        source_model_ref = _text(source_model_ref, "source_model_ref")
        qrefs = _refs(
            qualification_provenance_refs,
            "qualification_provenance_ref",
            required=True,
        )
        crefs = _refs(capture_provenance_refs, "capture_provenance_ref")
        blockers = _refs(blockers, "blocker")

        if status is DesignLineageQualificationStatus.QUALIFIED:
            if not isinstance(parent_analysis_lineage, AnalysisLineageQualification):
                raise DesignLineageQualificationError(
                    "QUALIFIED requires parent AnalysisLineageQualification"
                )
            parent_result = _analysis_result_from_qualified(parent_analysis_lineage)
            if not isinstance(design_state, DesignStateIdentity):
                raise DesignLineageQualificationError(
                    "QUALIFIED requires DesignStateIdentity"
                )
            if not isinstance(design_result, DesignResultIdentity):
                raise DesignLineageQualificationError(
                    "QUALIFIED requires DesignResultIdentity"
                )
            if blockers:
                raise DesignLineageQualificationError(
                    "QUALIFIED cannot contain blockers"
                )
            if (
                parent_result.source_model_ref != source_model_ref
                or design_state.source_model_ref != source_model_ref
                or design_result.source_model_ref != source_model_ref
            ):
                raise DesignLineageQualificationError(
                    "qualified design lineage source/root mismatch"
                )
            if (
                design_state.parent_analysis_result_ref != parent_result.identity_ref
                or design_result.parent_analysis_result_ref != parent_result.identity_ref
            ):
                raise DesignLineageQualificationError(
                    "qualified design lineage parent analysis-result mismatch"
                )
            if (
                design_state.analysis_lineage_qualification_ref
                != parent_analysis_lineage.qualification_ref
            ):
                raise DesignLineageQualificationError(
                    "qualified design state parent analysis-lineage mismatch"
                )
            if design_result.parent_design_state_ref != design_state.identity_ref:
                raise DesignLineageQualificationError(
                    "qualified design result parent state mismatch"
                )
        else:
            if design_result is not None:
                raise DesignLineageQualificationError(
                    "UNQUALIFIED must not expose DesignResultIdentity"
                )
            if not blockers:
                raise DesignLineageQualificationError(
                    "UNQUALIFIED requires at least one blocker"
                )
            if design_state is not None and not isinstance(
                design_state,
                DesignStateIdentity,
            ):
                raise TypeError("design_state must be DesignStateIdentity or None")
            if design_state is not None and design_state.source_model_ref != source_model_ref:
                raise DesignLineageQualificationError(
                    "unqualified design state source/root mismatch"
                )
            if parent_analysis_lineage is not None and not isinstance(
                parent_analysis_lineage,
                AnalysisLineageQualification,
            ):
                raise TypeError(
                    "parent_analysis_lineage must be AnalysisLineageQualification or None"
                )

        expected = _qualification_ref(
            status=status,
            source_model_ref=source_model_ref,
            parent_analysis_lineage=parent_analysis_lineage,
            design_state=design_state,
            design_result=design_result,
            qualification_provenance_refs=qrefs,
            capture_provenance_refs=crefs,
            blockers=blockers,
        )
        if qualification_ref != expected:
            raise DesignLineageError(
                "qualification_ref does not match qualification fields"
            )

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source_model_ref", source_model_ref)
        object.__setattr__(
            self,
            "parent_analysis_lineage",
            parent_analysis_lineage,
        )
        object.__setattr__(self, "design_state", design_state)
        object.__setattr__(self, "design_result", design_result)
        object.__setattr__(self, "qualification_ref", qualification_ref)
        object.__setattr__(self, "qualification_provenance_refs", qrefs)
        object.__setattr__(self, "capture_provenance_refs", crefs)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "contract", contract)

    @property
    def qualified(self) -> bool:
        return self.status is DesignLineageQualificationStatus.QUALIFIED

    def require_qualified_result(self) -> DesignResultIdentity:
        if not self.qualified or self.design_result is None:
            raise DesignLineageQualificationError(
                "design result lineage is not qualified"
            )
        return self.design_result

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "status": self.status.value,
            "source_model_ref": self.source_model_ref,
            "parent_analysis_lineage": (
                None
                if self.parent_analysis_lineage is None
                else self.parent_analysis_lineage.as_dict()
            ),
            "design_state": (
                None if self.design_state is None else self.design_state.as_dict()
            ),
            "design_result": (
                None if self.design_result is None else self.design_result.as_dict()
            ),
            "qualification_ref": self.qualification_ref,
            "qualification_provenance_refs": list(
                self.qualification_provenance_refs
            ),
            "capture_provenance_refs": list(self.capture_provenance_refs),
            "blockers": list(self.blockers),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


def build_unqualified_design_lineage(
    *,
    source_model_ref: str,
    blockers: Sequence[str],
    qualification_provenance_refs: Sequence[str],
    parent_analysis_lineage: AnalysisLineageQualification | None = None,
    design_state: DesignStateIdentity | None = None,
    capture_provenance_refs: Sequence[str] = (),
) -> DesignLineageQualification:
    """Return a fail-closed design qualification with no usable result identity."""
    source_model_ref = _text(source_model_ref, "source_model_ref")
    if parent_analysis_lineage is not None and not isinstance(
        parent_analysis_lineage,
        AnalysisLineageQualification,
    ):
        raise TypeError(
            "parent_analysis_lineage must be AnalysisLineageQualification or None"
        )
    if design_state is not None and not isinstance(design_state, DesignStateIdentity):
        raise TypeError("design_state must be DesignStateIdentity or None")
    if design_state is not None:
        if parent_analysis_lineage is None:
            raise DesignLineageQualificationError(
                "design_state requires its parent analysis lineage"
            )
        parent_result = _analysis_result_from_qualified(parent_analysis_lineage)
        if (
            design_state.source_model_ref != source_model_ref
            or parent_result.source_model_ref != source_model_ref
            or design_state.parent_analysis_result_ref != parent_result.identity_ref
            or design_state.analysis_lineage_qualification_ref
            != parent_analysis_lineage.qualification_ref
        ):
            raise DesignLineageQualificationError(
                "unqualified design-state parent lineage mismatch"
            )
    blockers = _refs(blockers, "blocker", required=True)
    qrefs = _refs(
        qualification_provenance_refs,
        "qualification_provenance_ref",
        required=True,
    )
    crefs = _refs(capture_provenance_refs, "capture_provenance_ref")
    status = DesignLineageQualificationStatus.UNQUALIFIED
    return DesignLineageQualification(
        _token=_DESIGN_QUALIFICATION_FACTORY_TOKEN,
        status=status,
        source_model_ref=source_model_ref,
        parent_analysis_lineage=parent_analysis_lineage,
        design_state=design_state,
        design_result=None,
        qualification_ref=_qualification_ref(
            status=status,
            source_model_ref=source_model_ref,
            parent_analysis_lineage=parent_analysis_lineage,
            design_state=design_state,
            design_result=None,
            qualification_provenance_refs=qrefs,
            capture_provenance_refs=crefs,
            blockers=blockers,
        ),
        qualification_provenance_refs=qrefs,
        capture_provenance_refs=crefs,
        blockers=blockers,
    )


def _build_qualified_design_lineage(
    *,
    _token: object,
    parent_analysis_lineage: AnalysisLineageQualification,
    design_state: DesignStateIdentity,
    design_result: DesignResultIdentity,
    execution_proof: _VerifiedDesignExecutionProof,
    qualification_provenance_refs: Sequence[str],
    capture_provenance_refs: Sequence[str] = (),
) -> DesignLineageQualification:
    """Private primitive reserved for a future verified controlled-design issuer."""
    if _token is not _DESIGN_QUALIFICATION_FACTORY_TOKEN:
        raise TypeError("qualified design lineage is issuer-created only")
    if not isinstance(parent_analysis_lineage, AnalysisLineageQualification):
        raise TypeError(
            "parent_analysis_lineage must be AnalysisLineageQualification"
        )
    parent_result = _analysis_result_from_qualified(parent_analysis_lineage)
    if not isinstance(design_state, DesignStateIdentity):
        raise TypeError("design_state must be DesignStateIdentity")
    if not isinstance(design_result, DesignResultIdentity):
        raise TypeError("design_result must be DesignResultIdentity")
    if not isinstance(execution_proof, _VerifiedDesignExecutionProof):
        raise TypeError(
            "execution_proof must be a verified causal design-execution proof"
        )

    if design_state.source_model_ref != parent_result.source_model_ref:
        raise DesignLineageQualificationError(
            "design state source root does not match parent analysis result"
        )
    if design_state.parent_analysis_result_ref != parent_result.identity_ref:
        raise DesignLineageQualificationError(
            "design state parent AnalysisResultIdentity mismatch"
        )
    if (
        design_state.analysis_lineage_qualification_ref
        != parent_analysis_lineage.qualification_ref
    ):
        raise DesignLineageQualificationError(
            "design state parent analysis qualification mismatch"
        )
    if design_result.source_model_ref != design_state.source_model_ref:
        raise DesignLineageQualificationError(
            "design result source root mismatch"
        )
    if design_result.parent_design_state_ref != design_state.identity_ref:
        raise DesignLineageQualificationError(
            "design result parent state mismatch"
        )
    if (
        design_result.parent_analysis_result_ref
        != design_state.parent_analysis_result_ref
    ):
        raise DesignLineageQualificationError(
            "design result parent analysis-result mismatch"
        )

    checks = (
        (
            execution_proof.source_model_ref,
            design_state.source_model_ref,
            "execution proof source root mismatch",
        ),
        (
            execution_proof.parent_analysis_result_ref,
            parent_result.identity_ref,
            "execution proof parent AnalysisResultIdentity mismatch",
        ),
        (
            execution_proof.analysis_lineage_qualification_ref,
            parent_analysis_lineage.qualification_ref,
            "execution proof parent analysis qualification mismatch",
        ),
        (
            execution_proof.model_fingerprint,
            design_state.model_fingerprint,
            "execution proof model fingerprint mismatch",
        ),
        (
            execution_proof.evidence_epoch_id,
            design_state.evidence_epoch_id,
            "execution proof EvidenceEpoch mismatch",
        ),
        (
            execution_proof.design_state_ref,
            design_state.identity_ref,
            "execution proof design-state identity mismatch",
        ),
        (
            execution_proof.design_result_ref,
            design_result.identity_ref,
            "execution proof design-result identity mismatch",
        ),
        (
            execution_proof.design_generation_ref,
            design_result.design_generation_ref,
            "execution proof design-generation mismatch",
        ),
        (
            execution_proof.requested_result_scope_refs,
            design_result.result_scope_refs,
            "execution proof requested result scope mismatch",
        ),
        (
            execution_proof.reconciled_result_scope_refs,
            design_result.result_scope_refs,
            "execution proof result-population reconciliation mismatch",
        ),
        (
            execution_proof.combo_grain_binding_refs,
            design_state.combo_grain_binding_refs,
            "execution proof exact combo-grain binding mismatch",
        ),
    )
    for actual, expected, message in checks:
        if actual != expected:
            raise DesignLineageQualificationError(message)

    qrefs = _refs(
        (
            *qualification_provenance_refs,
            execution_proof.proof_ref,
            *execution_proof.provenance_refs,
        ),
        "qualification_provenance_ref",
        required=True,
    )
    crefs = _refs(capture_provenance_refs, "capture_provenance_ref")
    status = DesignLineageQualificationStatus.QUALIFIED
    return DesignLineageQualification(
        _token=_DESIGN_QUALIFICATION_FACTORY_TOKEN,
        status=status,
        source_model_ref=design_state.source_model_ref,
        parent_analysis_lineage=parent_analysis_lineage,
        design_state=design_state,
        design_result=design_result,
        qualification_ref=_qualification_ref(
            status=status,
            source_model_ref=design_state.source_model_ref,
            parent_analysis_lineage=parent_analysis_lineage,
            design_state=design_state,
            design_result=design_result,
            qualification_provenance_refs=qrefs,
            capture_provenance_refs=crefs,
            blockers=(),
        ),
        qualification_provenance_refs=qrefs,
        capture_provenance_refs=crefs,
        blockers=(),
    )


__all__ = [
    "DESIGN_LINEAGE_QUALIFICATION_CONTRACT",
    "DESIGN_RESULT_IDENTITY_CONTRACT",
    "DESIGN_STATE_IDENTITY_CONTRACT",
    "DesignLineageError",
    "DesignLineageQualification",
    "DesignLineageQualificationError",
    "DesignLineageQualificationStatus",
    "DesignResultIdentity",
    "DesignStateIdentity",
    "build_design_result_identity",
    "build_design_state_identity",
    "build_unqualified_design_lineage",
]
