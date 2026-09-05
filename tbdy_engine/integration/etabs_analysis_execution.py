"""B5 sole semantic authority for controlled ETABS analysis execution.

The supported positive path is deliberately narrow:

qualified B4B AnalysisStateMutationResult + exact OwnedScratchContext
-> predeclared analysis-case scope
-> full run-flag snapshot
-> exact requested run-scope establishment
-> explicit stale-result clearing on the owned scratch
-> exactly one RunAnalysis
-> every requested case FINISHED
-> exact B4B causal-state revalidation
-> exact run-flag restoration
-> protected-source integrity
-> existing B1 AnalysisResultIdentity/private execution proof/QUALIFIED lineage.

A successful RunAnalysis return code alone never qualifies results.  Partial
success, stale-result ambiguity, state drift, source drift, missing cases, or
restoration failure issues no usable AnalysisResultIdentity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import ntpath
import uuid
from typing import Mapping, Sequence

from tbdy_engine.etabs.oapi.analysis_execution import (
    CaseStatusPopulationFact,
    DeleteAnalysisResultsFact,
    RunAnalysisFact,
    RunCaseFlagSnapshotFact,
    delete_analysis_results_from_session,
    get_case_status_population_from_session,
    get_run_case_flags_from_session,
    run_analysis_from_session,
    set_run_case_flag_from_session,
)
from tbdy_engine.etabs.safety import (
    AnalysisReadiness,
    read_verified_analysis_readiness,
    reread_verified_session_identity,
)
from tbdy_engine.integration.etabs_analysis_lineage import (
    AnalysisLineageQualification,
    AnalysisResultIdentity,
    _EXECUTION_PROOF_FACTORY_TOKEN,
    _QUALIFICATION_FACTORY_TOKEN,
    _VerifiedAnalysisExecutionProof,
    _build_qualified_analysis_lineage,
    build_analysis_result_identity,
)
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    AnalysisStateMutationResult,
)
from tbdy_engine.integration.etabs_analysis_state_revalidation import (
    AnalysisStateRevalidationResult,
    revalidate_frame_modifier_analysis_state,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import (
    OwnedScratchContext,
    PhysicalFileSnapshot,
    capture_physical_file_snapshot,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)


ANALYSIS_EXECUTION_SCOPE_CONTRACT = "TBDY_B5_ANALYSIS_EXECUTION_SCOPE_V1"
ANALYSIS_EXECUTION_MANIFEST_CONTRACT = "TBDY_B5_ANALYSIS_EXECUTION_MANIFEST_V1"
ANALYSIS_EXECUTION_RESULT_CONTRACT = "TBDY_B5_ANALYSIS_EXECUTION_RESULT_V1"
ANALYSIS_SCOPE_REF_PREFIX = "analysis-execution-scope:sha256:"
ANALYSIS_CASE_SCOPE_REF_PREFIX = "analysis-case-result-scope:sha256:"
ANALYSIS_ATTEMPT_REF_PREFIX = "analysis-execution-attempt:"
ANALYSIS_GENERATION_REF_PREFIX = "analysis-generation:"
ANALYSIS_EXECUTION_MANIFEST_REF_PREFIX = "analysis-execution-manifest:sha256:"
ANALYSIS_EXECUTION_PROOF_REF_PREFIX = "analysis-execution-proof:sha256:"


class RunFlagRestorationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    RESTORED = "RESTORED"
    FAILED = "FAILED"
    BLOCKED_UNSAFE = "BLOCKED_UNSAFE"


class AnalysisExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str,
        attempt_ref: str | None = None,
        generation_ref: str | None = None,
        restoration_status: RunFlagRestorationStatus = RunFlagRestorationStatus.NOT_REQUIRED,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.attempt_ref = attempt_ref
        self.generation_ref = generation_ref
        self.restoration_status = restoration_status
        self.details = dict(details or {})


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AnalysisExecutionError(
            f"{label} must be a nonblank canonical string",
            stage="contract_validation",
        )
    return value


def _json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(prefix: str, payload: object) -> str:
    return prefix + hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _canonical_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(_text(value, "model_path")))


def _same_bytes(left: PhysicalFileSnapshot, right: PhysicalFileSnapshot) -> bool:
    return (
        left.exists is True
        and right.exists is True
        and left.file_size_bytes == right.file_size_bytes
        and left.sha256_content_digest == right.sha256_content_digest
    )


def _case_scope_ref(case_name: str) -> str:
    name = _text(case_name, "case_name")
    return _digest(
        ANALYSIS_CASE_SCOPE_REF_PREFIX,
        {"contract": ANALYSIS_EXECUTION_SCOPE_CONTRACT, "case_name": name},
    )


@dataclass(frozen=True, slots=True)
class AnalysisExecutionScope:
    case_names: tuple[str, ...]
    result_scope_refs: tuple[str, ...] = field(init=False)
    scope_ref: str = field(init=False)
    contract: str = ANALYSIS_EXECUTION_SCOPE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ANALYSIS_EXECUTION_SCOPE_CONTRACT:
            raise AnalysisExecutionError(
                "analysis execution scope contract mismatch",
                stage="scope_contract",
            )
        names = tuple(sorted({_text(name, "case_name") for name in self.case_names}))
        if not names:
            raise AnalysisExecutionError(
                "analysis execution scope requires at least one case",
                stage="scope_contract",
            )
        if len(names) != len(self.case_names):
            raise AnalysisExecutionError(
                "analysis execution scope contains duplicate case names",
                stage="scope_contract",
            )
        refs = tuple(_case_scope_ref(name) for name in names)
        object.__setattr__(self, "case_names", names)
        object.__setattr__(self, "result_scope_refs", refs)
        object.__setattr__(
            self,
            "scope_ref",
            _digest(
                ANALYSIS_SCOPE_REF_PREFIX,
                {
                    "contract": self.contract,
                    "case_names": list(names),
                    "result_scope_refs": list(refs),
                },
            ),
        )

    @classmethod
    def from_case_names(cls, case_names: Sequence[str]) -> "AnalysisExecutionScope":
        if isinstance(case_names, (str, bytes)) or not isinstance(case_names, Sequence):
            raise TypeError("case_names must be a sequence of strings")
        return cls(case_names=tuple(case_names))

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "case_names": list(self.case_names),
            "result_scope_refs": list(self.result_scope_refs),
            "scope_ref": self.scope_ref,
        }


@dataclass(frozen=True, slots=True)
class AnalysisExecutionAttempt:
    attempt_ref: str
    generation_ref: str

    @classmethod
    def issue(cls) -> "AnalysisExecutionAttempt":
        return cls(
            attempt_ref=ANALYSIS_ATTEMPT_REF_PREFIX + uuid.uuid4().hex,
            generation_ref=ANALYSIS_GENERATION_REF_PREFIX + uuid.uuid4().hex,
        )

    def __post_init__(self) -> None:
        attempt = _text(self.attempt_ref, "attempt_ref")
        generation = _text(self.generation_ref, "generation_ref")
        if not attempt.startswith(ANALYSIS_ATTEMPT_REF_PREFIX):
            raise AnalysisExecutionError("invalid attempt ref", stage="attempt_contract")
        if not generation.startswith(ANALYSIS_GENERATION_REF_PREFIX):
            raise AnalysisExecutionError("invalid generation ref", stage="attempt_contract")


@dataclass(frozen=True, slots=True)
class AnalysisExecutionManifest:
    source_model_ref: str
    ownership_proof_ref: str
    analysis_state_ref: str
    scope: AnalysisExecutionScope
    attempt: AnalysisExecutionAttempt
    active_model_path_before: str
    active_model_path_after: str
    model_locked_before: bool | None
    model_locked_after: bool | None
    source_before: PhysicalFileSnapshot
    source_after: PhysicalFileSnapshot
    run_flags_before: RunCaseFlagSnapshotFact
    run_flags_configured: RunCaseFlagSnapshotFact
    run_flags_restored: RunCaseFlagSnapshotFact
    pre_case_status: CaseStatusPopulationFact
    cleared_case_status: CaseStatusPopulationFact
    delete_results: DeleteAnalysisResultsFact
    run_analysis: RunAnalysisFact
    post_case_status: CaseStatusPopulationFact
    state_revalidation: AnalysisStateRevalidationResult
    manifest_ref: str = field(init=False)
    contract: str = ANALYSIS_EXECUTION_MANIFEST_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ANALYSIS_EXECUTION_MANIFEST_CONTRACT:
            raise AnalysisExecutionError(
                "analysis execution manifest contract mismatch",
                stage="manifest_contract",
            )
        for name in ("source_model_ref", "ownership_proof_ref", "analysis_state_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.scope, AnalysisExecutionScope):
            raise TypeError("scope must be AnalysisExecutionScope")
        if not isinstance(self.attempt, AnalysisExecutionAttempt):
            raise TypeError("attempt must be AnalysisExecutionAttempt")
        if not self.run_analysis.success:
            raise AnalysisExecutionError(
                "positive execution manifest requires RunAnalysis success",
                stage="manifest_contract",
            )
        if self.run_flags_before.case_flags != self.run_flags_restored.case_flags:
            raise AnalysisExecutionError(
                "positive execution manifest requires exact run-flag restoration",
                stage="manifest_contract",
            )
        if not self.state_revalidation.matched_exact:
            raise AnalysisExecutionError(
                "positive execution manifest requires exact causal-state revalidation",
                stage="manifest_contract",
            )
        object.__setattr__(
            self,
            "manifest_ref",
            _digest(
                ANALYSIS_EXECUTION_MANIFEST_REF_PREFIX,
                {
                    "contract": self.contract,
                    "source_model_ref": self.source_model_ref,
                    "ownership_proof_ref": self.ownership_proof_ref,
                    "analysis_state_ref": self.analysis_state_ref,
                    "scope_ref": self.scope.scope_ref,
                    "result_scope_refs": list(self.scope.result_scope_refs),
                    "attempt_ref": self.attempt.attempt_ref,
                    "generation_ref": self.attempt.generation_ref,
                    "active_model_path_before": self.active_model_path_before,
                    "active_model_path_after": self.active_model_path_after,
                    "model_locked_before": self.model_locked_before,
                    "model_locked_after": self.model_locked_after,
                    "source_before_sha256": self.source_before.sha256_content_digest,
                    "source_after_sha256": self.source_after.sha256_content_digest,
                    "run_flags_before": list(self.run_flags_before.case_flags),
                    "run_flags_configured": list(self.run_flags_configured.case_flags),
                    "run_flags_restored": list(self.run_flags_restored.case_flags),
                    "pre_case_status": list(self.pre_case_status.case_statuses),
                    "cleared_case_status": list(self.cleared_case_status.case_statuses),
                    "delete_results_ref": self.delete_results.evidence_ref,
                    "run_analysis_ref": self.run_analysis.evidence_ref,
                    "post_case_status": list(self.post_case_status.case_statuses),
                    "state_comparison_ref": self.state_revalidation.comparison.comparison_ref,
                    "current_analysis_state_ref": self.state_revalidation.current_analysis_state.identity_ref,
                },
            ),
        )

    @property
    def execution_proof_ref(self) -> str:
        return _digest(
            ANALYSIS_EXECUTION_PROOF_REF_PREFIX,
            {
                "contract": ANALYSIS_EXECUTION_MANIFEST_CONTRACT,
                "manifest_ref": self.manifest_ref,
                "attempt_ref": self.attempt.attempt_ref,
                "generation_ref": self.attempt.generation_ref,
                "analysis_state_ref": self.analysis_state_ref,
                "result_scope_refs": list(self.scope.result_scope_refs),
            },
        )


@dataclass(frozen=True, slots=True)
class AnalysisExecutionResult:
    manifest: AnalysisExecutionManifest
    analysis_result_identity: AnalysisResultIdentity
    qualification: AnalysisLineageQualification
    execution_proof_ref: str
    contract: str = ANALYSIS_EXECUTION_RESULT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ANALYSIS_EXECUTION_RESULT_CONTRACT:
            raise AnalysisExecutionError(
                "analysis execution result contract mismatch",
                stage="result_contract",
            )
        if not self.qualification.qualified:
            raise AnalysisExecutionError(
                "positive B5 result requires QUALIFIED analysis lineage",
                stage="result_contract",
            )
        if self.qualification.analysis_result != self.analysis_result_identity:
            raise AnalysisExecutionError(
                "qualification/result identity mismatch",
                stage="result_contract",
            )
        if self.execution_proof_ref != self.manifest.execution_proof_ref:
            raise AnalysisExecutionError(
                "execution proof ref does not match manifest",
                stage="result_contract",
            )


def _require_active_owned_scratch(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    *,
    timeout_seconds: float,
):
    identity = reread_verified_session_identity(
        context.verified_session,
        timeout_seconds=timeout_seconds,
    )
    if _canonical_path(identity.model_full_path) != _canonical_path(owned_scratch.scratch_path):
        raise AnalysisExecutionError(
            "active ETABS model is not the qualified owned scratch",
            stage="active_scratch_binding",
            details={
                "active_model_path": identity.model_full_path,
                "owned_scratch_path": owned_scratch.scratch_path,
            },
        )
    return identity


def _restore_run_flags(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    snapshot: RunCaseFlagSnapshotFact,
    timeout_seconds: float,
) -> tuple[RunFlagRestorationStatus, RunCaseFlagSnapshotFact | None]:
    try:
        identity = reread_verified_session_identity(
            context.verified_session,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        return RunFlagRestorationStatus.BLOCKED_UNSAFE, None
    if _canonical_path(identity.model_full_path) != _canonical_path(owned_scratch.scratch_path):
        return RunFlagRestorationStatus.BLOCKED_UNSAFE, None
    if not snapshot.case_names:
        return RunFlagRestorationStatus.FAILED, None

    anchor = snapshot.case_names[0]
    try:
        cleared = set_run_case_flag_from_session(
            context.verified_session,
            case_name=anchor,
            run=False,
            all_cases=True,
            timeout_seconds=timeout_seconds,
        )
        if not cleared.success:
            return RunFlagRestorationStatus.FAILED, None
        for name, run in snapshot.case_flags:
            if not run:
                continue
            fact = set_run_case_flag_from_session(
                context.verified_session,
                case_name=name,
                run=True,
                all_cases=False,
                timeout_seconds=timeout_seconds,
            )
            if not fact.success:
                return RunFlagRestorationStatus.FAILED, None
        restored = get_run_case_flags_from_session(
            context.verified_session,
            timeout_seconds=timeout_seconds,
        )
        if not restored.success or restored.case_flags != snapshot.case_flags:
            return RunFlagRestorationStatus.FAILED, restored
        return RunFlagRestorationStatus.RESTORED, restored
    except Exception:
        return RunFlagRestorationStatus.FAILED, None


def _raise_after_run_scope_mutation(
    *,
    message: str,
    stage: str,
    attempt: AnalysisExecutionAttempt,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    run_flags_before: RunCaseFlagSnapshotFact,
    timeout_seconds: float,
    details: Mapping[str, object] | None = None,
    cause: BaseException | None = None,
) -> None:
    restoration, _ = _restore_run_flags(
        context=context,
        owned_scratch=owned_scratch,
        snapshot=run_flags_before,
        timeout_seconds=timeout_seconds,
    )
    error = AnalysisExecutionError(
        message,
        stage=stage,
        attempt_ref=attempt.attempt_ref,
        generation_ref=attempt.generation_ref,
        restoration_status=restoration,
        details=details,
    )
    if cause is None:
        raise error
    raise error from cause


def execute_controlled_analysis(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    requested_case_names: Sequence[str],
    timeout_seconds: float = 300.0,
) -> AnalysisExecutionResult:
    """Execute and causally qualify one exact analysis-case generation."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if not isinstance(established_state, AnalysisStateMutationResult):
        raise TypeError(
            "established_state must be the positive B4B AnalysisStateMutationResult; "
            "a naked AnalysisStateIdentity is not accepted"
        )
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    scope = AnalysisExecutionScope.from_case_names(requested_case_names)
    attempt = AnalysisExecutionAttempt.issue()

    if owned_scratch.source_model_identity != context.source_model_identity:
        raise AnalysisExecutionError(
            "owned scratch does not belong to trusted acquisition context",
            stage="source_binding",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )
    if established_state.analysis_state_identity.source_model_ref != context.source_model_identity.source_model_ref:
        raise AnalysisExecutionError(
            "B4B AnalysisStateIdentity belongs to a different source model",
            stage="source_binding",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )
    if established_state.mutation_manifest.ownership_proof_ref != owned_scratch.ownership_proof_ref:
        raise AnalysisExecutionError(
            "B4B state is not bound to this exact owned scratch",
            stage="scratch_binding",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )

    identity_before = _require_active_owned_scratch(
        context,
        owned_scratch,
        timeout_seconds=timeout,
    )
    source_before = capture_physical_file_snapshot(
        owned_scratch.source_pre.canonical_absolute_path
    )
    if not _same_bytes(source_before, owned_scratch.source_post):
        raise AnalysisExecutionError(
            "protected source bytes do not match the B4S baseline",
            stage="source_pre_execution_integrity",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )

    # Positive B4B state must exist immediately before B5 changes run scope or
    # deletes stale result rows.
    revalidate_frame_modifier_analysis_state(
        context=context,
        owned_scratch=owned_scratch,
        established_state=established_state,
        timeout_seconds=timeout,
    )

    run_flags_before = get_run_case_flags_from_session(
        context.verified_session,
        timeout_seconds=timeout,
    )
    if not run_flags_before.success or not run_flags_before.case_names:
        raise AnalysisExecutionError(
            "Analyze.GetRunCaseFlag could not establish the pre-execution scope snapshot",
            stage="run_flag_snapshot",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )
    available_cases = set(run_flags_before.case_names)
    missing_cases = tuple(sorted(set(scope.case_names) - available_cases))
    if missing_cases:
        raise AnalysisExecutionError(
            "requested analysis scope contains cases absent from ETABS run-flag population",
            stage="scope_reconciliation",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
            details={"missing_cases": missing_cases},
        )

    pre_status = get_case_status_population_from_session(
        context.verified_session,
        timeout_seconds=timeout,
    )
    if not pre_status.success:
        raise AnalysisExecutionError(
            "pre-execution case-status population returned nonzero",
            stage="pre_case_status",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )
    if set(scope.case_names) - set(pre_status.as_mapping()):
        raise AnalysisExecutionError(
            "pre-execution case-status population is missing requested scope",
            stage="pre_case_status",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        )

    anchor = run_flags_before.case_names[0]
    run_scope_mutated = False
    try:
        all_off = set_run_case_flag_from_session(
            context.verified_session,
            case_name=anchor,
            run=False,
            all_cases=True,
            timeout_seconds=timeout,
        )
        run_scope_mutated = True
        if not all_off.success:
            _raise_after_run_scope_mutation(
                message="SetRunCaseFlag(All=True, Run=False) returned nonzero",
                stage="run_scope_all_off",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                details={"return_code": all_off.return_code},
            )
        for case_name in scope.case_names:
            selected = set_run_case_flag_from_session(
                context.verified_session,
                case_name=case_name,
                run=True,
                all_cases=False,
                timeout_seconds=timeout,
            )
            if not selected.success:
                _raise_after_run_scope_mutation(
                    message="SetRunCaseFlag for requested case returned nonzero",
                    stage="run_scope_case_enable",
                    attempt=attempt,
                    context=context,
                    owned_scratch=owned_scratch,
                    run_flags_before=run_flags_before,
                    timeout_seconds=timeout,
                    details={"case_name": case_name, "return_code": selected.return_code},
                )

        run_flags_configured = get_run_case_flags_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
        expected_flags = tuple(
            sorted((name, name in set(scope.case_names)) for name in run_flags_before.case_names)
        )
        if not run_flags_configured.success or run_flags_configured.case_flags != expected_flags:
            _raise_after_run_scope_mutation(
                message="requested analysis run scope did not verify exactly",
                stage="run_scope_verify",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                details={
                    "expected": expected_flags,
                    "actual": run_flags_configured.case_flags,
                },
            )

        # Frozen B5 freshness policy: purge every prior analysis result on the
        # owned scratch before executing the new generation.  Existing rows or
        # FINISHED flags can never qualify the new attempt.
        delete_fact = delete_analysis_results_from_session(
            context.verified_session,
            case_name=anchor,
            all_cases=True,
            timeout_seconds=timeout,
        )
        if not delete_fact.success:
            _raise_after_run_scope_mutation(
                message="Analyze.DeleteResults(All=True) returned nonzero",
                stage="stale_result_clear",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                details={"return_code": delete_fact.return_code},
            )

        cleared_status = get_case_status_population_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
        if not cleared_status.success:
            _raise_after_run_scope_mutation(
                message="case-status population could not verify stale-result clearing",
                stage="stale_result_clear_verify",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
            )
        for case_name in scope.case_names:
            readiness = read_verified_analysis_readiness(
                context.verified_session,
                case_name,
                timeout_seconds=timeout,
            )
            if readiness.readiness is not AnalysisReadiness.ANALYSIS_NOT_RUN:
                _raise_after_run_scope_mutation(
                    message="requested case retained non-NOT_RUN state after explicit result clearing",
                    stage="stale_result_clear_verify",
                    attempt=attempt,
                    context=context,
                    owned_scratch=owned_scratch,
                    run_flags_before=run_flags_before,
                    timeout_seconds=timeout,
                    details={
                        "case_name": case_name,
                        "readiness": readiness.readiness.value,
                        "status_code": readiness.etabs_status_code,
                    },
                )

        # Run-scope flags and result deletion are execution-state mechanics, not
        # permission to drift the structural AnalysisStateIdentity.
        revalidate_frame_modifier_analysis_state(
            context=context,
            owned_scratch=owned_scratch,
            established_state=established_state,
            timeout_seconds=timeout,
        )

        try:
            run_fact = run_analysis_from_session(
                context.verified_session,
                timeout_seconds=timeout,
            )
        except Exception as exc:
            _raise_after_run_scope_mutation(
                message="Analyze.RunAnalysis raised an execution/transport error",
                stage="run_analysis_exception",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                cause=exc,
            )
        if not run_fact.success:
            _raise_after_run_scope_mutation(
                message="Analyze.RunAnalysis returned nonzero",
                stage="run_analysis_nonzero",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                details={"return_code": run_fact.return_code},
            )

        post_status = get_case_status_population_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
        if not post_status.success:
            _raise_after_run_scope_mutation(
                message="post-run case-status population returned nonzero",
                stage="post_case_status",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
            )
        post_map = post_status.as_mapping()
        missing_post = tuple(sorted(set(scope.case_names) - set(post_map)))
        if missing_post:
            _raise_after_run_scope_mutation(
                message="post-run case-status population is missing requested cases",
                stage="post_case_status",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                details={"missing_cases": missing_post},
            )
        for case_name in scope.case_names:
            readiness = read_verified_analysis_readiness(
                context.verified_session,
                case_name,
                timeout_seconds=timeout,
            )
            if readiness.readiness is not AnalysisReadiness.ANALYSIS_FINISHED:
                _raise_after_run_scope_mutation(
                    message="requested analysis scope did not finish completely",
                    stage="post_case_readiness",
                    attempt=attempt,
                    context=context,
                    owned_scratch=owned_scratch,
                    run_flags_before=run_flags_before,
                    timeout_seconds=timeout,
                    details={
                        "case_name": case_name,
                        "readiness": readiness.readiness.value,
                        "status_code": readiness.etabs_status_code,
                    },
                )

        state_revalidation = revalidate_frame_modifier_analysis_state(
            context=context,
            owned_scratch=owned_scratch,
            established_state=established_state,
            timeout_seconds=timeout,
        )

        restoration_status, run_flags_restored = _restore_run_flags(
            context=context,
            owned_scratch=owned_scratch,
            snapshot=run_flags_before,
            timeout_seconds=timeout,
        )
        if restoration_status is not RunFlagRestorationStatus.RESTORED or run_flags_restored is None:
            raise AnalysisExecutionError(
                "post-run run-case flags could not be restored exactly",
                stage="run_flag_restore",
                attempt_ref=attempt.attempt_ref,
                generation_ref=attempt.generation_ref,
                restoration_status=restoration_status,
            )
        run_scope_mutated = False

        identity_after = _require_active_owned_scratch(
            context,
            owned_scratch,
            timeout_seconds=timeout,
        )
        source_after = capture_physical_file_snapshot(
            owned_scratch.source_pre.canonical_absolute_path
        )
        if not _same_bytes(source_before, source_after):
            raise AnalysisExecutionError(
                "protected source physical bytes changed during B5 execution",
                stage="source_post_execution_integrity",
                attempt_ref=attempt.attempt_ref,
                generation_ref=attempt.generation_ref,
                restoration_status=RunFlagRestorationStatus.RESTORED,
            )

        manifest = AnalysisExecutionManifest(
            source_model_ref=context.source_model_identity.source_model_ref,
            ownership_proof_ref=owned_scratch.ownership_proof_ref,
            analysis_state_ref=established_state.analysis_state_identity.identity_ref,
            scope=scope,
            attempt=attempt,
            active_model_path_before=identity_before.model_full_path,
            active_model_path_after=identity_after.model_full_path,
            model_locked_before=identity_before.model_locked,
            model_locked_after=identity_after.model_locked,
            source_before=source_before,
            source_after=source_after,
            run_flags_before=run_flags_before,
            run_flags_configured=run_flags_configured,
            run_flags_restored=run_flags_restored,
            pre_case_status=pre_status,
            cleared_case_status=cleared_status,
            delete_results=delete_fact,
            run_analysis=run_fact,
            post_case_status=post_status,
            state_revalidation=state_revalidation,
        )

        analysis_result = build_analysis_result_identity(
            source_model_ref=context.source_model_identity.source_model_ref,
            parent_analysis_state_ref=established_state.analysis_state_identity.identity_ref,
            analysis_generation_ref=attempt.generation_ref,
            result_scope_refs=scope.result_scope_refs,
            provenance_refs=(
                manifest.manifest_ref,
                scope.scope_ref,
                run_fact.evidence_ref,
                post_status.evidence_ref,
            ),
        )
        execution_proof = _VerifiedAnalysisExecutionProof(
            _token=_EXECUTION_PROOF_FACTORY_TOKEN,
            proof_ref=manifest.execution_proof_ref,
            source_model_ref=context.source_model_identity.source_model_ref,
            execution_state_ref=established_state.analysis_state_identity.execution_state_ref,
            analysis_state_ref=established_state.analysis_state_identity.identity_ref,
            analysis_result_ref=analysis_result.identity_ref,
            analysis_generation_ref=attempt.generation_ref,
            provenance_refs=(
                manifest.manifest_ref,
                scope.scope_ref,
                run_fact.evidence_ref,
                post_status.evidence_ref,
                state_revalidation.comparison.comparison_ref,
                owned_scratch.ownership_proof_ref,
            ),
        )
        qualification = _build_qualified_analysis_lineage(
            _token=_QUALIFICATION_FACTORY_TOKEN,
            analysis_state=established_state.analysis_state_identity,
            analysis_result=analysis_result,
            execution_proof=execution_proof,
            qualification_provenance_refs=(
                manifest.manifest_ref,
                manifest.execution_proof_ref,
                scope.scope_ref,
            ),
            capture_provenance_refs=(
                context.acquisition_context_ref,
                context.session_provenance_ref,
                owned_scratch.ownership_proof_ref,
            ),
        )
        return AnalysisExecutionResult(
            manifest=manifest,
            analysis_result_identity=analysis_result,
            qualification=qualification,
            execution_proof_ref=manifest.execution_proof_ref,
        )
    except AnalysisExecutionError:
        raise
    except Exception as exc:
        if run_scope_mutated:
            _raise_after_run_scope_mutation(
                message="B5 execution failed after run-scope mutation",
                stage="unexpected_execution_error",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                cause=exc,
            )
        raise AnalysisExecutionError(
            "B5 execution failed before run-scope mutation",
            stage="unexpected_pre_execution_error",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        ) from exc


__all__ = [
    "ANALYSIS_EXECUTION_MANIFEST_CONTRACT",
    "ANALYSIS_EXECUTION_RESULT_CONTRACT",
    "ANALYSIS_EXECUTION_SCOPE_CONTRACT",
    "AnalysisExecutionAttempt",
    "AnalysisExecutionError",
    "AnalysisExecutionManifest",
    "AnalysisExecutionResult",
    "AnalysisExecutionScope",
    "RunFlagRestorationStatus",
    "execute_controlled_analysis",
]
