"""B5 sole semantic authority for controlled ETABS analysis execution.

The supported positive path is deliberately narrow:

qualified B4B AnalysisStateMutationResult + exact OwnedScratchContext
-> predeclared exact case/result-population scope
-> factual expected column population
-> full run-flag snapshot and exact run-scope establishment
-> explicit all-case stale-result clearing on the owned scratch
-> exactly one RunAnalysis
-> every requested case FINISHED and every non-requested case still NOT_RUN
-> complete exact ``Element Forces - Columns`` population for every case
-> exact B4B causal-state revalidation
-> exact run-flag restoration
-> protected-source integrity
-> B1-owned controlled-execution issuance of QUALIFIED AnalysisResultIdentity.

A successful RunAnalysis return code or FINISHED case status alone never
qualifies results. Partial success, population incompleteness, scope
contamination, stale-result ambiguity, state drift, source drift, missing cases,
or restoration failure issues no usable AnalysisResultIdentity.
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
    DefinedAnalysisCasePopulationFact,
    EtabsRuntimeVersionFact,
    LoadCaseTypeRuntimeFact,
    DeleteAnalysisResultsFact,
    RunAnalysisFact,
    RunCaseFlagSnapshotFact,
    delete_analysis_results_from_session,
    get_case_status_population_from_session,
    get_defined_analysis_cases_from_session,
    get_etabs_runtime_version_fact_from_session,
    get_load_case_type_runtime_fact_from_session,
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
    build_analysis_result_identity,
    issue_qualified_analysis_lineage_from_controlled_execution,
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
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    COLUMN_FORCE_RESULT_POPULATION_CONTRACT,
    TABLE_COLUMN_FORCES,
    ColumnForcePopulationExpectation,
    ColumnForceResultPopulationFact,
    capture_column_force_population_expectation_from_session,
    capture_column_force_result_population_from_session,
)


ANALYSIS_EXECUTION_SCOPE_CONTRACT = "TBDY_B5_ANALYSIS_EXECUTION_SCOPE_V1"
RUNTIME_EXECUTION_SCOPE_RESOLUTION_CONTRACT = "TBDY_B5_RUNTIME_EXECUTION_SCOPE_RESOLUTION_V1"
ANALYSIS_EXECUTION_MANIFEST_CONTRACT = "TBDY_B5_ANALYSIS_EXECUTION_MANIFEST_V1"
ANALYSIS_EXECUTION_RESULT_CONTRACT = "TBDY_B5_ANALYSIS_EXECUTION_RESULT_V1"
ANALYSIS_SCOPE_REF_PREFIX = "analysis-execution-scope:sha256:"
ANALYSIS_CASE_SCOPE_REF_PREFIX = "analysis-case-result-scope:sha256:"
ANALYSIS_ATTEMPT_REF_PREFIX = "analysis-execution-attempt:"
ANALYSIS_GENERATION_REF_PREFIX = "analysis-generation:"
ANALYSIS_EXECUTION_MANIFEST_REF_PREFIX = "analysis-execution-manifest:sha256:"
ANALYSIS_EXECUTION_PROOF_REF_PREFIX = "analysis-execution-proof:sha256:"
ANALYSIS_RUNTIME_SCOPE_RESOLUTION_REF_PREFIX = "analysis-runtime-scope-resolution:sha256:"

# CSI GetCaseStatus documented integer meanings used as factual postconditions.
CSI_ANALYSIS_STATUS_NOT_RUN = 1
CSI_ANALYSIS_STATUS_FINISHED = 4

# ETABS 23.2.0 live-observed runtime compatibility profile.
#
# CSI documents the GetTypeOAPI_1 Auto parameter as 0/1. The Python runtime
# projection observed against ETABS 23.2.0 produced additional integer values
# in the corresponding slot. These values are NOT promoted to documented CSI
# Auto semantics.
#
# Live-observed ETABS 23.2.0 behavior:
#   slot 5    -> forced execution dependency
#   slot 3/10 -> case retirement during RunAnalysis
#   slot 6/7  -> surviving neutral ETABS-managed cases
#
# The compatibility meanings below are usable only for the exact live-proven
# runtime profile and every consequence is independently verified after
# RunAnalysis. Other versions or unknown undocumented values fail closed.
_SUPPORTED_RUNTIME_COMPATIBILITY_VERSION = "23.2.0"
_SUPPORTED_RUNTIME_COMPATIBILITY_INTERNAL_VERSION = 0.0

_DOCUMENTED_AUTO_SLOT_VALUES = frozenset({0, 1})
_RUNTIME_DEPENDENCY_SLOT_VALUES = frozenset({5})
_RUNTIME_RETIREMENT_SLOT_VALUES = frozenset({3, 10})
_RUNTIME_NEUTRAL_UNDOCUMENTED_SLOT_VALUES = frozenset({6, 7})


class RunFlagRestorationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    RESTORED = "RESTORED"
    RESTORED_WITH_DECLARED_RETIREMENTS = "RESTORED_WITH_DECLARED_RETIREMENTS"
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
        {
            "contract": ANALYSIS_EXECUTION_SCOPE_CONTRACT,
            "case_name": name,
            "required_result_population_contract": COLUMN_FORCE_RESULT_POPULATION_CONTRACT,
            "required_result_table": TABLE_COLUMN_FORCES,
        },
    )


@dataclass(frozen=True, slots=True)
class AnalysisExecutionScope:
    # Result cases are engineering/result-identity scope.
    case_names: tuple[str, ...]
    # Dependencies are permitted/required execution closure but do not issue
    # result_scope_refs and do not require Column Forces populations.
    execution_dependency_case_names: tuple[str, ...] = ()
    # These cases must exist before RunAnalysis, must not be enabled, and are
    # permitted to disappear only if the exact declared set disappears.
    permitted_runtime_retired_case_names: tuple[str, ...] = ()
    result_scope_refs: tuple[str, ...] = field(init=False)
    scope_ref: str = field(init=False)
    contract: str = ANALYSIS_EXECUTION_SCOPE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != ANALYSIS_EXECUTION_SCOPE_CONTRACT:
            raise AnalysisExecutionError(
                "analysis execution scope contract mismatch",
                stage="scope_contract",
            )

        result_names = tuple(
            sorted(_text(name, "case_name") for name in self.case_names)
        )
        dependency_names = tuple(
            sorted(
                _text(name, "execution_dependency_case_name")
                for name in self.execution_dependency_case_names
            )
        )
        retired_names = tuple(
            sorted(
                _text(name, "permitted_runtime_retired_case_name")
                for name in self.permitted_runtime_retired_case_names
            )
        )

        if not result_names:
            raise AnalysisExecutionError(
                "analysis execution scope requires at least one result case",
                stage="scope_contract",
            )

        for label, names in (
            ("result", result_names),
            ("execution dependency", dependency_names),
            ("permitted runtime retirement", retired_names),
        ):
            if len(set(names)) != len(names):
                raise AnalysisExecutionError(
                    f"analysis execution scope contains duplicate {label} case names",
                    stage="scope_contract",
                )

        result_set = set(result_names)
        dependency_set = set(dependency_names)
        retired_set = set(retired_names)

        overlap_result_dependency = tuple(
            sorted(result_set & dependency_set)
        )
        overlap_execution_retirement = tuple(
            sorted((result_set | dependency_set) & retired_set)
        )
        if overlap_result_dependency or overlap_execution_retirement:
            raise AnalysisExecutionError(
                "analysis execution scope roles must be pairwise disjoint",
                stage="scope_contract",
                details={
                    "result_dependency_overlap": overlap_result_dependency,
                    "execution_retirement_overlap": overlap_execution_retirement,
                },
            )

        refs = tuple(sorted(_case_scope_ref(name) for name in result_names))

        object.__setattr__(self, "case_names", result_names)
        object.__setattr__(
            self,
            "execution_dependency_case_names",
            dependency_names,
        )
        object.__setattr__(
            self,
            "permitted_runtime_retired_case_names",
            retired_names,
        )
        object.__setattr__(self, "result_scope_refs", refs)

        object.__setattr__(
            self,
            "scope_ref",
            _digest(
                ANALYSIS_SCOPE_REF_PREFIX,
                {
                    "contract": self.contract,
                    "result_case_names": list(result_names),
                    "execution_dependency_case_names": list(dependency_names),
                    "permitted_runtime_retired_case_names": list(retired_names),
                    "required_result_population_contract": COLUMN_FORCE_RESULT_POPULATION_CONTRACT,
                    "required_result_table": TABLE_COLUMN_FORCES,
                    "result_scope_refs": list(refs),
                },
            ),
        )

    @property
    def execution_case_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (
                    *self.case_names,
                    *self.execution_dependency_case_names,
                )
            )
        )

    @classmethod
    def from_case_names(
        cls,
        case_names: Sequence[str],
        *,
        execution_dependency_case_names: Sequence[str] = (),
        permitted_runtime_retired_case_names: Sequence[str] = (),
    ) -> "AnalysisExecutionScope":
        for label, values in (
            ("case_names", case_names),
            (
                "execution_dependency_case_names",
                execution_dependency_case_names,
            ),
            (
                "permitted_runtime_retired_case_names",
                permitted_runtime_retired_case_names,
            ),
        ):
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise TypeError(f"{label} must be a sequence of strings")

        return cls(
            case_names=tuple(case_names),
            execution_dependency_case_names=tuple(
                execution_dependency_case_names
            ),
            permitted_runtime_retired_case_names=tuple(
                permitted_runtime_retired_case_names
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "result_case_names": list(self.case_names),
            "execution_case_names": list(self.execution_case_names),
            "execution_dependency_case_names": list(
                self.execution_dependency_case_names
            ),
            "permitted_runtime_retired_case_names": list(
                self.permitted_runtime_retired_case_names
            ),
            "required_result_population_contract": COLUMN_FORCE_RESULT_POPULATION_CONTRACT,
            "required_result_table": TABLE_COLUMN_FORCES,
            "result_scope_refs": list(self.result_scope_refs),
            "scope_ref": self.scope_ref,
        }


@dataclass(frozen=True, slots=True)
class RuntimeExecutionScopeResolution:
    """Factual, version-bound ETABS runtime execution-scope resolution."""

    defined_case_names: tuple[str, ...]
    runtime_version: EtabsRuntimeVersionFact
    case_type_facts: tuple[LoadCaseTypeRuntimeFact, ...]
    scope: AnalysisExecutionScope
    evidence_ref: str = field(init=False)
    contract: str = RUNTIME_EXECUTION_SCOPE_RESOLUTION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != RUNTIME_EXECUTION_SCOPE_RESOLUTION_CONTRACT:
            raise AnalysisExecutionError(
                "runtime execution-scope resolution contract mismatch",
                stage="runtime_scope_contract",
            )

        defined = tuple(
            sorted(
                _text(name, "defined_case_name")
                for name in self.defined_case_names
            )
        )

        if len(set(defined)) != len(defined):
            raise AnalysisExecutionError(
                "runtime scope resolution contains duplicate defined cases",
                stage="runtime_scope_contract",
            )

        if not isinstance(
            self.runtime_version,
            EtabsRuntimeVersionFact,
        ):
            raise TypeError(
                "runtime_version must be EtabsRuntimeVersionFact"
            )

        if not self.runtime_version.success:
            raise AnalysisExecutionError(
                "runtime scope resolution requires successful ETABS version fact",
                stage="runtime_scope_contract",
            )

        facts = tuple(
            sorted(
                self.case_type_facts,
                key=lambda item: item.case_name,
            )
        )

        if any(
            not isinstance(item, LoadCaseTypeRuntimeFact)
            for item in facts
        ):
            raise TypeError(
                "case_type_facts must contain LoadCaseTypeRuntimeFact"
            )

        if any(not item.success for item in facts):
            raise AnalysisExecutionError(
                "runtime scope resolution requires successful case-type facts",
                stage="runtime_scope_contract",
            )

        fact_names = tuple(item.case_name for item in facts)

        if fact_names != defined:
            raise AnalysisExecutionError(
                "runtime scope resolution requires one exact case-type fact per defined case",
                stage="runtime_scope_contract",
                details={
                    "defined_case_names": defined,
                    "fact_case_names": fact_names,
                },
            )

        if not isinstance(self.scope, AnalysisExecutionScope):
            raise TypeError(
                "scope must be AnalysisExecutionScope"
            )

        declared = (
            set(self.scope.case_names)
            | set(self.scope.execution_dependency_case_names)
            | set(self.scope.permitted_runtime_retired_case_names)
        )

        if not declared.issubset(set(defined)):
            raise AnalysisExecutionError(
                "runtime scope contains case outside defined-case universe",
                stage="runtime_scope_contract",
            )

        object.__setattr__(
            self,
            "defined_case_names",
            defined,
        )
        object.__setattr__(
            self,
            "case_type_facts",
            facts,
        )

        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                ANALYSIS_RUNTIME_SCOPE_RESOLUTION_REF_PREFIX,
                {
                    "contract": self.contract,
                    "defined_case_names": list(defined),
                    "runtime_version_ref": (
                        self.runtime_version.evidence_ref
                    ),
                    "case_type_fact_refs": [
                        item.evidence_ref
                        for item in facts
                    ],
                    "scope_ref": self.scope.scope_ref,
                },
            ),
        )


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
    runtime_scope_resolution: RuntimeExecutionScopeResolution
    attempt: AnalysisExecutionAttempt
    active_model_path_before: str
    active_model_path_after: str
    model_locked_before: bool | None
    model_locked_after: bool | None
    source_before: PhysicalFileSnapshot
    source_after: PhysicalFileSnapshot
    defined_cases_before: DefinedAnalysisCasePopulationFact
    defined_cases_after: DefinedAnalysisCasePopulationFact
    run_flags_before: RunCaseFlagSnapshotFact
    run_flags_configured: RunCaseFlagSnapshotFact
    run_flags_restored: RunCaseFlagSnapshotFact
    run_flag_restoration_status: RunFlagRestorationStatus
    pre_case_status: CaseStatusPopulationFact
    cleared_case_status: CaseStatusPopulationFact
    delete_results: DeleteAnalysisResultsFact
    run_analysis: RunAnalysisFact
    post_case_status: CaseStatusPopulationFact
    result_population_expectation: ColumnForcePopulationExpectation
    result_populations: tuple[ColumnForceResultPopulationFact, ...]
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
        if not isinstance(
            self.runtime_scope_resolution,
            RuntimeExecutionScopeResolution,
        ):
            raise TypeError(
                "runtime_scope_resolution must be RuntimeExecutionScopeResolution"
            )
        if self.runtime_scope_resolution.scope != self.scope:
            raise AnalysisExecutionError(
                "manifest scope does not match factual runtime scope resolution",
                stage="manifest_contract",
            )
        if not isinstance(self.attempt, AnalysisExecutionAttempt):
            raise TypeError("attempt must be AnalysisExecutionAttempt")
        if not isinstance(self.result_population_expectation, ColumnForcePopulationExpectation):
            raise TypeError(
                "result_population_expectation must be ColumnForcePopulationExpectation"
            )
        populations = tuple(self.result_populations)
        if not populations or any(
            not isinstance(item, ColumnForceResultPopulationFact) for item in populations
        ):
            raise TypeError(
                "result_populations must contain ColumnForceResultPopulationFact"
            )
        population_cases = tuple(sorted(item.case_name for item in populations))
        if population_cases != self.scope.case_names:
            raise AnalysisExecutionError(
                "positive execution manifest requires one exact result population per requested case",
                stage="manifest_contract",
            )
        if any(
            item.expectation_ref != self.result_population_expectation.evidence_ref
            for item in populations
        ):
            raise AnalysisExecutionError(
                "result populations do not bind the manifest expectation",
                stage="manifest_contract",
            )
        object.__setattr__(
            self,
            "result_populations",
            tuple(sorted(populations, key=lambda item: item.case_name)),
        )
        if not self.run_analysis.success:
            raise AnalysisExecutionError(
                "positive execution manifest requires RunAnalysis success",
                stage="manifest_contract",
            )
        pre_defined = set(self.defined_cases_before.case_names)
        post_defined = set(self.defined_cases_after.case_names)
        declared_retired = set(
            self.scope.permitted_runtime_retired_case_names
        )
        actual_retired = pre_defined - post_defined
        added_cases = post_defined - pre_defined

        if added_cases or actual_retired != declared_retired:
            raise AnalysisExecutionError(
                "positive execution manifest requires exact declared case-universe transition",
                stage="manifest_contract",
                details={
                    "actual_retired": tuple(sorted(actual_retired)),
                    "declared_retired": tuple(sorted(declared_retired)),
                    "added_cases": tuple(sorted(added_cases)),
                },
            )

        expected_restored = tuple(
            (name, run)
            for name, run in self.run_flags_before.case_flags
            if name in post_defined
        )
        if self.run_flags_restored.case_flags != expected_restored:
            raise AnalysisExecutionError(
                "positive execution manifest requires exact surviving run-flag restoration",
                stage="manifest_contract",
            )

        expected_restoration_status = (
            RunFlagRestorationStatus.RESTORED_WITH_DECLARED_RETIREMENTS
            if declared_retired
            else RunFlagRestorationStatus.RESTORED
        )
        if self.run_flag_restoration_status is not expected_restoration_status:
            raise AnalysisExecutionError(
                "positive execution manifest restoration status does not match case-universe transition",
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
                    "runtime_scope_resolution_ref": (
                        self.runtime_scope_resolution.evidence_ref
                    ),
                    "runtime_version_ref": (
                        self.runtime_scope_resolution.runtime_version.evidence_ref
                    ),
                    "result_scope_refs": list(self.scope.result_scope_refs),
                    "attempt_ref": self.attempt.attempt_ref,
                    "generation_ref": self.attempt.generation_ref,
                    "active_model_path_before": self.active_model_path_before,
                    "active_model_path_after": self.active_model_path_after,
                    "model_locked_before": self.model_locked_before,
                    "model_locked_after": self.model_locked_after,
                    "source_before_sha256": self.source_before.sha256_content_digest,
                    "source_after_sha256": self.source_after.sha256_content_digest,
                    "defined_cases_before_ref": self.defined_cases_before.evidence_ref,
                    "defined_cases_after_ref": self.defined_cases_after.evidence_ref,
                    "run_flag_restoration_status": self.run_flag_restoration_status.value,
                    "run_flags_before": list(self.run_flags_before.case_flags),
                    "run_flags_configured": list(self.run_flags_configured.case_flags),
                    "run_flags_restored": list(self.run_flags_restored.case_flags),
                    "pre_case_status": list(self.pre_case_status.case_statuses),
                    "cleared_case_status": list(self.cleared_case_status.case_statuses),
                    "delete_results_ref": self.delete_results.evidence_ref,
                    "run_analysis_ref": self.run_analysis.evidence_ref,
                    "post_case_status": list(self.post_case_status.case_statuses),
                    "result_population_expectation_ref": self.result_population_expectation.evidence_ref,
                    "result_populations": [
                        {
                            "case_name": item.case_name,
                            "evidence_ref": item.evidence_ref,
                            "row_count": item.row_count,
                        }
                        for item in self.result_populations
                    ],
                    "state_comparison_ref": self.state_revalidation.comparison.comparison_ref,
                    "current_analysis_state_ref": self.state_revalidation.current_analysis_state.identity_ref,
                },
            ),
        )

    @property
    def result_population_refs(self) -> tuple[str, ...]:
        return tuple(item.evidence_ref for item in self.result_populations)

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
                "runtime_scope_resolution_ref": (
                    self.runtime_scope_resolution.evidence_ref
                ),
                "runtime_version_ref": (
                    self.runtime_scope_resolution.runtime_version.evidence_ref
                ),
                "result_scope_refs": list(self.scope.result_scope_refs),
                "result_population_expectation_ref": self.result_population_expectation.evidence_ref,
                "result_population_refs": list(self.result_population_refs),
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
        if self.analysis_result_identity.result_scope_refs != self.manifest.scope.result_scope_refs:
            raise AnalysisExecutionError(
                "analysis-result identity does not match the exact manifest scope",
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
    permitted_runtime_retired_case_names: Sequence[str] = (),
    require_exact_retirements: bool = False,
) -> tuple[RunFlagRestorationStatus, RunCaseFlagSnapshotFact | None]:
    """Restore the pre-run flags projected onto the surviving case universe."""
    try:
        identity = reread_verified_session_identity(
            context.verified_session,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        return RunFlagRestorationStatus.BLOCKED_UNSAFE, None

    if (
        _canonical_path(identity.model_full_path)
        != _canonical_path(owned_scratch.scratch_path)
    ):
        return RunFlagRestorationStatus.BLOCKED_UNSAFE, None

    if not snapshot.case_names:
        return RunFlagRestorationStatus.FAILED, None

    try:
        current = get_run_case_flags_from_session(
            context.verified_session,
            timeout_seconds=timeout_seconds,
        )
        if not current.success or not current.case_names:
            return RunFlagRestorationStatus.FAILED, current

        before_names = set(snapshot.case_names)
        current_names = set(current.case_names)
        permitted_retired = set(
            permitted_runtime_retired_case_names
        )

        added = current_names - before_names
        retired = before_names - current_names

        if added:
            return RunFlagRestorationStatus.FAILED, current

        if require_exact_retirements:
            if retired != permitted_retired:
                return RunFlagRestorationStatus.FAILED, current
        elif not retired.issubset(permitted_retired):
            return RunFlagRestorationStatus.FAILED, current

        anchor = current.case_names[0]

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
            if name not in current_names or not run:
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

        expected = tuple(
            (name, run)
            for name, run in snapshot.case_flags
            if name in current_names
        )

        if not restored.success or restored.case_flags != expected:
            return RunFlagRestorationStatus.FAILED, restored

        if retired:
            return (
                RunFlagRestorationStatus.RESTORED_WITH_DECLARED_RETIREMENTS,
                restored,
            )
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
    permitted_runtime_retired_case_names: Sequence[str] = (),
    details: Mapping[str, object] | None = None,
    cause: BaseException | None = None,
) -> None:
    restoration, _ = _restore_run_flags(
        context=context,
        owned_scratch=owned_scratch,
        snapshot=run_flags_before,
        timeout_seconds=timeout_seconds,
        permitted_runtime_retired_case_names=(
            permitted_runtime_retired_case_names
        ),
        require_exact_retirements=False,
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


def _require_exact_case_universe(
    *,
    run_flags: RunCaseFlagSnapshotFact,
    statuses: CaseStatusPopulationFact,
    defined_cases: DefinedAnalysisCasePopulationFact,
    stage: str,
    attempt: AnalysisExecutionAttempt,
) -> None:
    flag_cases = set(run_flags.case_names)
    status_cases = set(statuses.as_mapping())
    defined = set(defined_cases.case_names)

    if flag_cases == status_cases == defined:
        return

    raise AnalysisExecutionError(
        "defined-case, run-flag, and case-status populations do not reconcile exactly",
        stage=stage,
        attempt_ref=attempt.attempt_ref,
        generation_ref=attempt.generation_ref,
        details={
            "defined_not_in_flags": tuple(sorted(defined - flag_cases)),
            "flags_not_defined": tuple(sorted(flag_cases - defined)),
            "defined_not_in_status": tuple(sorted(defined - status_cases)),
            "status_not_defined": tuple(sorted(status_cases - defined)),
            "flags_not_in_status": tuple(sorted(flag_cases - status_cases)),
            "status_not_in_flags": tuple(sorted(status_cases - flag_cases)),
        },
    )


def _resolve_runtime_execution_scope(
    *,
    context: TrustedLiveAcquisitionContext,
    requested_case_names: Sequence[str],
    defined_cases: DefinedAnalysisCasePopulationFact,
    timeout_seconds: float,
    attempt: AnalysisExecutionAttempt,
) -> RuntimeExecutionScopeResolution:
    """Resolve execution closure from version-bound factual ETABS data."""

    requested = tuple(
        sorted(
            _text(name, "case_name")
            for name in requested_case_names
        )
    )
    requested_set = set(requested)

    try:
        runtime_version = (
            get_etabs_runtime_version_fact_from_session(
                context.verified_session,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        raise AnalysisExecutionError(
            "ETABS runtime version could not be established",
            stage="runtime_scope_resolution",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        ) from exc

    if not runtime_version.success:
        raise AnalysisExecutionError(
            "ETABS runtime version getter returned nonzero",
            stage="runtime_scope_resolution",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
            details={
                "return_code": runtime_version.return_code,
            },
        )

    supported_profile = (
        runtime_version.program_version
        == _SUPPORTED_RUNTIME_COMPATIBILITY_VERSION
        and runtime_version.internal_version_number
        == _SUPPORTED_RUNTIME_COMPATIBILITY_INTERNAL_VERSION
    )

    dependencies: list[str] = []
    retirements: list[str] = []
    runtime_facts: list[LoadCaseTypeRuntimeFact] = []

    for case_name in defined_cases.case_names:
        try:
            fact = get_load_case_type_runtime_fact_from_session(
                context.verified_session,
                case_name=case_name,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise AnalysisExecutionError(
                "ETABS runtime case-type facts could not be established",
                stage="runtime_scope_resolution",
                attempt_ref=attempt.attempt_ref,
                generation_ref=attempt.generation_ref,
                details={"case_name": case_name},
            ) from exc

        if not fact.success:
            raise AnalysisExecutionError(
                "ETABS runtime case-type fact returned nonzero",
                stage="runtime_scope_resolution",
                attempt_ref=attempt.attempt_ref,
                generation_ref=attempt.generation_ref,
                details={
                    "case_name": case_name,
                    "return_code": fact.return_code,
                },
            )

        runtime_facts.append(fact)

        slot = fact.runtime_auto_slot_value

        if slot in _DOCUMENTED_AUTO_SLOT_VALUES:
            continue

        if not supported_profile:
            raise AnalysisExecutionError(
                "undocumented GetTypeOAPI_1 runtime slot value is not qualified for this ETABS runtime profile",
                stage="runtime_scope_resolution",
                attempt_ref=attempt.attempt_ref,
                generation_ref=attempt.generation_ref,
                details={
                    "case_name": case_name,
                    "program_version": (
                        runtime_version.program_version
                    ),
                    "internal_version_number": (
                        runtime_version.internal_version_number
                    ),
                    "runtime_auto_slot_value": slot,
                },
            )

        if slot in _RUNTIME_DEPENDENCY_SLOT_VALUES:
            if case_name not in requested_set:
                dependencies.append(case_name)
            continue

        if slot in _RUNTIME_RETIREMENT_SLOT_VALUES:
            if case_name not in requested_set:
                retirements.append(case_name)
            continue

        if slot in _RUNTIME_NEUTRAL_UNDOCUMENTED_SLOT_VALUES:
            continue

        raise AnalysisExecutionError(
            "unclassified undocumented GetTypeOAPI_1 runtime slot value",
            stage="runtime_scope_resolution",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
            details={
                "case_name": case_name,
                "program_version": (
                    runtime_version.program_version
                ),
                "internal_version_number": (
                    runtime_version.internal_version_number
                ),
                "runtime_auto_slot_value": slot,
            },
        )

    scope = AnalysisExecutionScope.from_case_names(
        requested,
        execution_dependency_case_names=tuple(dependencies),
        permitted_runtime_retired_case_names=tuple(retirements),
    )

    return RuntimeExecutionScopeResolution(
        defined_case_names=defined_cases.case_names,
        runtime_version=runtime_version,
        case_type_facts=tuple(runtime_facts),
        scope=scope,
    )


def execute_controlled_analysis(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    established_state: AnalysisStateMutationResult,
    requested_case_names: Sequence[str],
    timeout_seconds: float = 300.0,
) -> AnalysisExecutionResult:
    """Execute and causally qualify one exact analysis/result generation."""
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

    # Public input carries engineering intent only. Runtime dependency /
    # retirement authority is resolved internally from factual ETABS state.
    scope = AnalysisExecutionScope.from_case_names(
        requested_case_names,
    )
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

    try:
        population_expectation = capture_column_force_population_expectation_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
    except Exception as exc:
        raise AnalysisExecutionError(
            "required factual column population could not be established before execution",
            stage="result_population_expectation",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
        ) from exc

    defined_cases_before = get_defined_analysis_cases_from_session(
        context.verified_session,
        timeout_seconds=timeout,
    )
    if (
        not defined_cases_before.success
        or not defined_cases_before.case_names
    ):
        raise AnalysisExecutionError(
            "LoadCases.GetNameList could not establish the pre-execution case universe",
            stage="defined_case_snapshot",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
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

    _require_exact_case_universe(
        run_flags=run_flags_before,
        statuses=pre_status,
        defined_cases=defined_cases_before,
        stage="pre_case_universe",
        attempt=attempt,
    )

    # Caller input is engineering intent. Reconcile that intent against the
    # factual pre-run defined-case universe before deriving any ETABS-managed
    # execution dependency or retirement semantics. This preserves the public
    # scope-reconciliation contract and prevents runtime compatibility logic
    # from becoming an authority for an invalid caller request.
    available_cases = set(defined_cases_before.case_names)

    missing_requested_cases = tuple(
        sorted(set(scope.case_names) - available_cases)
    )
    if missing_requested_cases:
        raise AnalysisExecutionError(
            "requested analysis scope contains cases absent from the defined ETABS case universe",
            stage="scope_reconciliation",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
            details={
                "missing_cases": missing_requested_cases,
            },
        )

    runtime_scope_resolution = _resolve_runtime_execution_scope(
        context=context,
        requested_case_names=scope.case_names,
        defined_cases=defined_cases_before,
        timeout_seconds=timeout,
        attempt=attempt,
    )
    scope = runtime_scope_resolution.scope

    # Runtime-derived dependencies/retirements must themselves remain bounded
    # to the same factual pre-run case universe.
    declared_runtime_cases = (
        set(scope.execution_dependency_case_names)
        | set(scope.permitted_runtime_retired_case_names)
    )
    missing_runtime_cases = tuple(
        sorted(declared_runtime_cases - available_cases)
    )
    if missing_runtime_cases:
        raise AnalysisExecutionError(
            "runtime-resolved execution scope contains cases absent from the defined ETABS case universe",
            stage="runtime_scope_contract",
            attempt_ref=attempt.attempt_ref,
            generation_ref=attempt.generation_ref,
            details={
                "missing_runtime_cases": missing_runtime_cases,
            },
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={"return_code": all_off.return_code},
            )
        for case_name in scope.execution_case_names:
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
        execution_set = set(scope.execution_case_names)
        expected_flags = tuple(
            sorted(
                (name, name in execution_set)
                for name in run_flags_before.case_names
            )
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={
                    "expected": expected_flags,
                    "actual": run_flags_configured.case_flags,
                },
            )

        # Frozen B5 freshness policy: purge every prior analysis result on the
        # owned scratch before executing the new generation. Existing rows or
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
            )
        try:
            _require_exact_case_universe(
                run_flags=run_flags_before,
                statuses=cleared_status,
                defined_cases=defined_cases_before,
                stage="stale_result_clear_verify",
                attempt=attempt,
            )
        except AnalysisExecutionError as exc:
            _raise_after_run_scope_mutation(
                message=str(exc),
                stage=exc.stage,
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details=exc.details,
                cause=exc,
            )
        uncleared = tuple(
            sorted(
                (name, status)
                for name, status in cleared_status.case_statuses
                if status != CSI_ANALYSIS_STATUS_NOT_RUN
            )
        )
        if uncleared:
            _raise_after_run_scope_mutation(
                message="all-case result clearing did not leave the full case population NOT_RUN",
                stage="stale_result_clear_verify",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={"uncleared_cases": uncleared},
            )
        for case_name in scope.execution_case_names:
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={"return_code": run_fact.return_code},
            )

        defined_cases_after = get_defined_analysis_cases_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
        post_run_flags = get_run_case_flags_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )
        post_status = get_case_status_population_from_session(
            context.verified_session,
            timeout_seconds=timeout,
        )

        if (
            not defined_cases_after.success
            or not post_run_flags.success
            or not post_status.success
        ):
            _raise_after_run_scope_mutation(
                message="post-run ETABS case universe could not be established",
                stage="post_case_universe",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={
                    "defined_return_code": defined_cases_after.return_code,
                    "run_flags_return_code": post_run_flags.return_code,
                    "status_return_code": post_status.return_code,
                },
            )

        try:
            _require_exact_case_universe(
                run_flags=post_run_flags,
                statuses=post_status,
                defined_cases=defined_cases_after,
                stage="post_case_universe",
                attempt=attempt,
            )
        except AnalysisExecutionError as exc:
            _raise_after_run_scope_mutation(
                message=str(exc),
                stage=exc.stage,
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details=exc.details,
                cause=exc,
            )

        pre_defined_set = set(defined_cases_before.case_names)
        post_defined_set = set(defined_cases_after.case_names)
        actual_retired = pre_defined_set - post_defined_set
        added_cases = post_defined_set - pre_defined_set
        declared_retired = set(
            scope.permitted_runtime_retired_case_names
        )

        if added_cases or actual_retired != declared_retired:
            _raise_after_run_scope_mutation(
                message="RunAnalysis changed the defined case universe outside the exact predeclared retirement contract",
                stage="post_case_universe_transition",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={
                    "actual_retired": tuple(sorted(actual_retired)),
                    "declared_retired": tuple(sorted(declared_retired)),
                    "added_cases": tuple(sorted(added_cases)),
                },
            )

        post_map = post_status.as_mapping()
        contaminated = tuple(
            sorted(
                (name, status)
                for name, status in post_map.items()
                if name not in execution_set and status != CSI_ANALYSIS_STATUS_NOT_RUN
            )
        )
        if contaminated:
            _raise_after_run_scope_mutation(
                message="non-execution cases changed state during exact-scope execution",
                stage="post_case_scope_contamination",
                attempt=attempt,
                context=context,
                owned_scratch=owned_scratch,
                run_flags_before=run_flags_before,
                timeout_seconds=timeout,
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
                details={"contaminated_cases": contaminated},
            )
        for case_name in scope.execution_case_names:
            readiness = read_verified_analysis_readiness(
                context.verified_session,
                case_name,
                timeout_seconds=timeout,
            )
            if readiness.readiness is not AnalysisReadiness.ANALYSIS_FINISHED:
                _raise_after_run_scope_mutation(
                    message="predeclared execution closure did not finish completely",
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
            if post_map.get(case_name) != CSI_ANALYSIS_STATUS_FINISHED:
                _raise_after_run_scope_mutation(
                    message="requested case status did not reconcile to FINISHED",
                    stage="post_case_readiness",
                    attempt=attempt,
                    context=context,
                    owned_scratch=owned_scratch,
                    run_flags_before=run_flags_before,
                    timeout_seconds=timeout,
                    details={
                        "case_name": case_name,
                        "status_code": post_map.get(case_name),
                    },
                )

        result_populations: list[ColumnForceResultPopulationFact] = []
        for case_name in scope.case_names:
            try:
                population = capture_column_force_result_population_from_session(
                    context.verified_session,
                    case_name=case_name,
                    expectation=population_expectation,
                    timeout_seconds=timeout,
                )
            except Exception as exc:
                _raise_after_run_scope_mutation(
                    message="required post-run result population did not qualify",
                    stage="result_population_acquisition",
                    attempt=attempt,
                    context=context,
                    owned_scratch=owned_scratch,
                    run_flags_before=run_flags_before,
                    timeout_seconds=timeout,
                    details={"case_name": case_name, "error": str(exc)},
                    cause=exc,
                )
            result_populations.append(population)

        # Result acquisition uses reversible display-selection transactions. Only
        # after every required population is complete do we re-prove that the
        # structural causal state is still the exact B4B state.
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
            permitted_runtime_retired_case_names=(
                scope.permitted_runtime_retired_case_names
            ),
            require_exact_retirements=True,
        )
        expected_restoration_status = (
            RunFlagRestorationStatus.RESTORED_WITH_DECLARED_RETIREMENTS
            if scope.permitted_runtime_retired_case_names
            else RunFlagRestorationStatus.RESTORED
        )
        if (
            restoration_status is not expected_restoration_status
            or run_flags_restored is None
        ):
            raise AnalysisExecutionError(
                "post-run surviving run-case flags could not be restored exactly",
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
                restoration_status=restoration_status,
            )

        manifest = AnalysisExecutionManifest(
            source_model_ref=context.source_model_identity.source_model_ref,
            ownership_proof_ref=owned_scratch.ownership_proof_ref,
            analysis_state_ref=established_state.analysis_state_identity.identity_ref,
            scope=scope,
            runtime_scope_resolution=runtime_scope_resolution,
            attempt=attempt,
            active_model_path_before=identity_before.model_full_path,
            active_model_path_after=identity_after.model_full_path,
            model_locked_before=identity_before.model_locked,
            model_locked_after=identity_after.model_locked,
            source_before=source_before,
            source_after=source_after,
            defined_cases_before=defined_cases_before,
            defined_cases_after=defined_cases_after,
            run_flags_before=run_flags_before,
            run_flags_configured=run_flags_configured,
            run_flags_restored=run_flags_restored,
            run_flag_restoration_status=restoration_status,
            pre_case_status=pre_status,
            cleared_case_status=cleared_status,
            delete_results=delete_fact,
            run_analysis=run_fact,
            post_case_status=post_status,
            result_population_expectation=population_expectation,
            result_populations=tuple(result_populations),
            state_revalidation=state_revalidation,
        )

        population_provenance = (
            population_expectation.evidence_ref,
            *manifest.result_population_refs,
        )
        analysis_result = build_analysis_result_identity(
            source_model_ref=context.source_model_identity.source_model_ref,
            parent_analysis_state_ref=established_state.analysis_state_identity.identity_ref,
            analysis_generation_ref=attempt.generation_ref,
            result_scope_refs=scope.result_scope_refs,
            provenance_refs=(
                manifest.manifest_ref,
                scope.scope_ref,
                runtime_scope_resolution.evidence_ref,
                runtime_scope_resolution.runtime_version.evidence_ref,
                run_fact.evidence_ref,
                post_status.evidence_ref,
                *population_provenance,
            ),
        )
        qualification = issue_qualified_analysis_lineage_from_controlled_execution(
            analysis_state=established_state.analysis_state_identity,
            analysis_result=analysis_result,
            execution_proof_ref=manifest.execution_proof_ref,
            execution_provenance_refs=(
                manifest.manifest_ref,
                scope.scope_ref,
                runtime_scope_resolution.evidence_ref,
                runtime_scope_resolution.runtime_version.evidence_ref,
                run_fact.evidence_ref,
                post_status.evidence_ref,
                state_revalidation.comparison.comparison_ref,
                owned_scratch.ownership_proof_ref,
                *population_provenance,
            ),
            qualification_provenance_refs=(
                manifest.manifest_ref,
                manifest.execution_proof_ref,
                scope.scope_ref,
                runtime_scope_resolution.evidence_ref,
                runtime_scope_resolution.runtime_version.evidence_ref,
                *population_provenance,
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
                permitted_runtime_retired_case_names=(
                    scope.permitted_runtime_retired_case_names
                ),
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
    "RUNTIME_EXECUTION_SCOPE_RESOLUTION_CONTRACT",
    "AnalysisExecutionAttempt",
    "AnalysisExecutionError",
    "AnalysisExecutionManifest",
    "AnalysisExecutionResult",
    "AnalysisExecutionScope",
    "RunFlagRestorationStatus",
    "RuntimeExecutionScopeResolution",
    "execute_controlled_analysis",
]
