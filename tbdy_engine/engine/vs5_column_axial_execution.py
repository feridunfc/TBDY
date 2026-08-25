"""Package-level production execution authority for bounded live VS5 column axial checks.

The CLI is intentionally excluded from orchestration. This module owns attach,
model identity verification, factual acquisition, reviewed-context construction,
and delegation to the existing regulatory VS5 program. It does not own code
limits or PASS/FAIL formulas.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tbdy_engine.checks.column_axial_selection import (
    ReviewedColumnNdmLoadBinding,
    Ts498ReductionPolicyState,
)
from tbdy_engine.etabs.safety import EtabsSessionIdentity, read_session_identity
from tbdy_engine.features.etabs_column_axial_evidence import (
    ColumnAxialEvidenceError,
    LiveColumnAxialEvidenceBundle,
    capture_live_column_axial_evidence,
)
from tbdy_engine.features.etabs_com_attach import ATTACH_STATUS_ATTACHED, attach_to_running_etabs
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.regulatory.vs5_column_axial_program import (
    CombinedColumnAxialStatus,
    ReviewedVs5ColumnAxialContext,
    VS5ColumnAxialRun,
    run_vs5_column_axial_population,
)

STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH = "BLOCKED_BY_LIVE_ETABS_ATTACH"
STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH = "BLOCKED_MODEL_IDENTITY_MISMATCH"
STATUS_BLOCKED_COLUMN_AXIAL_FACTUAL_ACQUISITION = "BLOCKED_COLUMN_AXIAL_FACTUAL_ACQUISITION"
STATUS_BLOCKED_REVIEWED_CONTEXT = "BLOCKED_REVIEWED_CONTEXT"
STATUS_COMPLETE = "COMPLETE"

FACTUAL_NOT_ACQUIRED = "NOT_ACQUIRED"
FACTUAL_BLOCKED = "BLOCKED"
FACTUAL_PROVEN = "PROVEN"

_SAFETY_PAYLOAD: Mapping[str, object] = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "output_selection_mutation": "REVERSIBLE_TRANSACTION_ONLY",
}


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _texts(values: Sequence[str], label: str, *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    result = tuple(_text(item, label) for item in values)
    if require_nonempty and not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique values")
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _float_map(value: object, label: str) -> dict[str, float]:
    mapping = _mapping(value, label)
    result: dict[str, float] = {}
    for key, raw in mapping.items():
        name = _text(str(key), f"{label}.key")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"{label}[{name}] must be numeric")
        result[name] = float(raw)
    return result


def _nested_float_map(value: object, label: str) -> dict[str, dict[str, float]]:
    mapping = _mapping(value, label)
    return {
        _text(str(key), f"{label}.key"): _float_map(raw, f"{label}[{key}]")
        for key, raw in mapping.items()
    }


def _context_from_mapping(payload: Mapping[str, Any]) -> ReviewedVs5ColumnAxialContext:
    ndm_raw = _mapping(payload.get("ndm_binding"), "reviewed_context.ndm_binding")
    binding = ReviewedColumnNdmLoadBinding(
        binding_id=_text(ndm_raw.get("binding_id"), "ndm_binding.binding_id"),
        version=_text(ndm_raw.get("version"), "ndm_binding.version"),
        final_combination_ids=_texts(tuple(ndm_raw.get("final_combination_ids", ())), "ndm_binding.final_combination_ids"),
        g_case_ids=_texts(tuple(ndm_raw.get("g_case_ids", ())), "ndm_binding.g_case_ids", require_nonempty=False),
        q_case_ids=_texts(tuple(ndm_raw.get("q_case_ids", ())), "ndm_binding.q_case_ids", require_nonempty=False),
        s_case_ids=_texts(tuple(ndm_raw.get("s_case_ids", ())), "ndm_binding.s_case_ids", require_nonempty=False),
        horizontal_e_case_ids=_texts(tuple(ndm_raw.get("horizontal_e_case_ids", ())), "ndm_binding.horizontal_e_case_ids", require_nonempty=False),
        vertical_e_case_ids=_texts(tuple(ndm_raw.get("vertical_e_case_ids", ())), "ndm_binding.vertical_e_case_ids", require_nonempty=False),
        baseline_coefficients_by_combination=_nested_float_map(
            ndm_raw.get("baseline_coefficients_by_combination", {}),
            "ndm_binding.baseline_coefficients_by_combination",
        ),
        required_fixed_coefficients_by_combination=_nested_float_map(
            ndm_raw.get("required_fixed_coefficients_by_combination", {}),
            "ndm_binding.required_fixed_coefficients_by_combination",
        ),
        final_case_type=_text(ndm_raw.get("final_case_type", "Combination"), "ndm_binding.final_case_type"),
        allowed_final_step_types=tuple(ndm_raw.get("allowed_final_step_types", ("Max", "Min"))),
        static_case_type=_text(ndm_raw.get("static_case_type", "LinStatic"), "ndm_binding.static_case_type"),
        review_refs=_texts(tuple(ndm_raw.get("review_refs", ())), "ndm_binding.review_refs", require_nonempty=False),
    )
    high_ductility = payload.get("tbdy_7312_high_ductility_applies")
    if high_ductility is not None and type(high_ductility) is not bool:
        raise TypeError("tbdy_7312_high_ductility_applies must be bool or null")
    return ReviewedVs5ColumnAxialContext(
        ndm_binding=binding,
        tbdy_7312_high_ductility_applies=high_ductility,
        ts498_reduction_state=Ts498ReductionPolicyState(
            _text(payload.get("ts498_reduction_state"), "ts498_reduction_state")
        ),
        q_target_coefficients=_float_map(payload.get("q_target_coefficients", {}), "q_target_coefficients"),
        s_target_coefficients=_float_map(payload.get("s_target_coefficients", {}), "s_target_coefficients"),
        linear_superposition_reviewed=payload.get("linear_superposition_reviewed"),
        compression_sign=int(payload.get("compression_sign")),
        ndm_regulatory_authority_ids=_texts(
            tuple(payload.get("ndm_regulatory_authority_ids", ())),
            "ndm_regulatory_authority_ids",
        ),
        ndm_review_refs=_texts(tuple(payload.get("ndm_review_refs", ())), "ndm_review_refs"),
        ts500_combination_ids=_texts(tuple(payload.get("ts500_combination_ids", ())), "ts500_combination_ids"),
        ts500_gamma_mc=float(payload.get("ts500_gamma_mc")),
        ts500_review_refs=_texts(tuple(payload.get("ts500_review_refs", ())), "ts500_review_refs"),
    )


@dataclass(frozen=True, slots=True)
class VS5ColumnAxialExecutionRequest:
    expected_model_fingerprint: str
    output_names: tuple[str, ...]
    reviewed_context: ReviewedVs5ColumnAxialContext
    reviewed_force_unit: str
    reviewed_length_unit: str
    reviewed_concrete_fc_unit: str
    factual_review_refs: tuple[str, ...]
    factual_provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.expected_model_fingerprint, "expected_model_fingerprint")
        object.__setattr__(self, "output_names", _texts(self.output_names, "output_name"))
        if not isinstance(self.reviewed_context, ReviewedVs5ColumnAxialContext):
            raise TypeError("reviewed_context must be ReviewedVs5ColumnAxialContext")
        for name in ("reviewed_force_unit", "reviewed_length_unit", "reviewed_concrete_fc_unit"):
            _text(getattr(self, name), name)
        object.__setattr__(self, "factual_review_refs", _texts(self.factual_review_refs, "factual_review_ref"))
        object.__setattr__(self, "factual_provenance_refs", _texts(self.factual_provenance_refs, "factual_provenance_ref"))


@dataclass(frozen=True, slots=True)
class VS5ColumnAxialExecutionResult:
    status: str
    factual_acquisition_status: str
    exit_code: int
    attach_attempts: tuple[Mapping[str, object], ...] = ()
    identity: EtabsSessionIdentity | None = None
    expected_model_fingerprint: str | None = None
    observed_model_fingerprint: str | None = None
    observed_model_path: str | None = None
    evidence_bundle: LiveColumnAxialEvidenceBundle | None = None
    column_runs: tuple[VS5ColumnAxialRun, ...] = ()
    message: str | None = None

    @property
    def factual_evidence_payload(self) -> dict[str, object] | None:
        return None if self.evidence_bundle is None else self.evidence_bundle.as_dict()

    def as_product_dict(self) -> dict[str, object]:
        if self.status == STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH:
            return {"status": self.status, "attempts": [dict(item) for item in self.attach_attempts]}
        if self.status == STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH:
            return {
                "status": self.status,
                "expected_model_fingerprint": self.expected_model_fingerprint,
                "observed_model_fingerprint": self.observed_model_fingerprint,
                "observed_model_path": self.observed_model_path,
            }
        if self.status in {STATUS_BLOCKED_COLUMN_AXIAL_FACTUAL_ACQUISITION, STATUS_BLOCKED_REVIEWED_CONTEXT}:
            return {
                "status": self.status,
                "FACTUAL_COLUMN_AXIAL_ACQUISITION": self.factual_acquisition_status,
                "message": self.message,
                "model_fingerprint": self.observed_model_fingerprint,
                "observed_model_path": self.observed_model_path,
            }
        if self.identity is None or self.evidence_bundle is None:
            raise RuntimeError("completed VS5 execution result is missing factual payload")
        counts = {status.value: 0 for status in CombinedColumnAxialStatus}
        for run in self.column_runs:
            counts[run.combined_status.value] += 1
        if counts[CombinedColumnAxialStatus.FAIL.value] > 0:
            overall = "FAIL"
        elif counts[CombinedColumnAxialStatus.BLOCKED.value] > 0:
            overall = "BLOCKED"
        elif counts[CombinedColumnAxialStatus.NO_DATA.value] > 0:
            overall = "NO_DATA"
        elif counts[CombinedColumnAxialStatus.INCOMPLETE.value] > 0:
            overall = "INCOMPLETE"
        else:
            overall = "PASS"
        return {
            "status": STATUS_COMPLETE,
            "FACTUAL_COLUMN_AXIAL_ACQUISITION": FACTUAL_PROVEN,
            "overall_dual_code_status": overall,
            "column_count": len(self.column_runs),
            "status_counts": counts,
            "model_identity": {
                "model_fingerprint": self.observed_model_fingerprint,
                "observed_model_path": self.identity.model_full_path,
                "program_name": self.identity.program_name,
                "program_version": self.identity.program_version,
                "program_api_version": self.identity.program_api_version,
                "database_units": self.identity.units.database_units,
                "present_units": self.identity.units.present_units,
            },
            "evidence_epoch_id": self.evidence_bundle.evidence_epoch_id,
            "columns": [run.as_dict() for run in self.column_runs],
            "safety": dict(_SAFETY_PAYLOAD),
        }


def build_vs5_column_axial_execution_request(
    *,
    expected_model_fingerprint: str,
    output_names: Sequence[str],
    reviewed_context: Mapping[str, Any],
    reviewed_force_unit: str,
    reviewed_length_unit: str,
    reviewed_concrete_fc_unit: str,
    factual_review_refs: Sequence[str],
    factual_provenance_refs: Sequence[str],
) -> VS5ColumnAxialExecutionRequest:
    """Build the immutable production request from reviewed primitive input."""
    return VS5ColumnAxialExecutionRequest(
        expected_model_fingerprint=expected_model_fingerprint,
        output_names=tuple(output_names),
        reviewed_context=_context_from_mapping(reviewed_context),
        reviewed_force_unit=reviewed_force_unit,
        reviewed_length_unit=reviewed_length_unit,
        reviewed_concrete_fc_unit=reviewed_concrete_fc_unit,
        factual_review_refs=tuple(factual_review_refs),
        factual_provenance_refs=tuple(factual_provenance_refs),
    )


def execute_live_vs5_column_axial(request: VS5ColumnAxialExecutionRequest) -> VS5ColumnAxialExecutionResult:
    if not isinstance(request, VS5ColumnAxialExecutionRequest):
        raise TypeError("request must be VS5ColumnAxialExecutionRequest")
    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        return VS5ColumnAxialExecutionResult(
            status=STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH,
            factual_acquisition_status=FACTUAL_NOT_ACQUIRED,
            exit_code=3,
            attach_attempts=tuple(item.as_dict() for item in attach.attempts),
        )
    identity = read_session_identity(
        attach.etabs_object,
        attach.sap_model,
        attach_strategy=attach.strategy,
    )
    observed = model_fingerprint_from_path(identity.model_full_path)
    if observed != request.expected_model_fingerprint:
        return VS5ColumnAxialExecutionResult(
            status=STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH,
            factual_acquisition_status=FACTUAL_NOT_ACQUIRED,
            exit_code=2,
            identity=identity,
            expected_model_fingerprint=request.expected_model_fingerprint,
            observed_model_fingerprint=observed,
            observed_model_path=identity.model_full_path,
        )
    try:
        evidence = capture_live_column_axial_evidence(
            database_tables=attach.sap_model.DatabaseTables,
            model_fingerprint=observed,
            output_names=request.output_names,
            reviewed_force_unit=request.reviewed_force_unit,
            reviewed_length_unit=request.reviewed_length_unit,
            reviewed_concrete_fc_unit=request.reviewed_concrete_fc_unit,
            review_refs=request.factual_review_refs,
            provenance_refs=request.factual_provenance_refs,
        )
    except (ColumnAxialEvidenceError, TypeError, ValueError) as exc:
        return VS5ColumnAxialExecutionResult(
            status=STATUS_BLOCKED_COLUMN_AXIAL_FACTUAL_ACQUISITION,
            factual_acquisition_status=FACTUAL_BLOCKED,
            exit_code=4,
            identity=identity,
            expected_model_fingerprint=request.expected_model_fingerprint,
            observed_model_fingerprint=observed,
            observed_model_path=identity.model_full_path,
            message=str(exc),
        )
    try:
        runs = run_vs5_column_axial_population(evidence=evidence, reviewed=request.reviewed_context)
    except (TypeError, ValueError) as exc:
        return VS5ColumnAxialExecutionResult(
            status=STATUS_BLOCKED_REVIEWED_CONTEXT,
            factual_acquisition_status=FACTUAL_PROVEN,
            exit_code=5,
            identity=identity,
            expected_model_fingerprint=request.expected_model_fingerprint,
            observed_model_fingerprint=observed,
            observed_model_path=identity.model_full_path,
            evidence_bundle=evidence,
            message=str(exc),
        )
    return VS5ColumnAxialExecutionResult(
        status=STATUS_COMPLETE,
        factual_acquisition_status=FACTUAL_PROVEN,
        exit_code=0,
        identity=identity,
        expected_model_fingerprint=request.expected_model_fingerprint,
        observed_model_fingerprint=observed,
        observed_model_path=identity.model_full_path,
        evidence_bundle=evidence,
        column_runs=tuple(runs),
    )


__all__ = [
    "STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH",
    "STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH",
    "STATUS_BLOCKED_COLUMN_AXIAL_FACTUAL_ACQUISITION",
    "STATUS_BLOCKED_REVIEWED_CONTEXT",
    "STATUS_COMPLETE",
    "FACTUAL_NOT_ACQUIRED",
    "FACTUAL_BLOCKED",
    "FACTUAL_PROVEN",
    "VS5ColumnAxialExecutionRequest",
    "VS5ColumnAxialExecutionResult",
    "build_vs5_column_axial_execution_request",
    "execute_live_vs5_column_axial",
]
