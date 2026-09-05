from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_analysis_execution as subject
from tbdy_engine.etabs.oapi.analysis_execution import (
    CaseStatusPopulationFact,
    DeleteAnalysisResultsFact,
    RunAnalysisFact,
    RunCaseFlagSetFact,
    RunCaseFlagSnapshotFact,
)
from tbdy_engine.etabs.safety import AnalysisReadiness
from tbdy_engine.integration.etabs_analysis_lineage import build_analysis_state_identity
from tbdy_engine.integration.etabs_analysis_state_revalidation import (
    AnalysisStateRevalidationError,
)


class _FakeContext:
    def __init__(self) -> None:
        self.source_model_identity = SimpleNamespace(
            source_model_ref="source-model-ref:test",
            normalized_model_reference=r"C:\tmp\source.edb",
        )
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:test"
        self.session_provenance_ref = "session-provenance:test"


class _FakeOwnedScratch:
    def __init__(self, source_identity) -> None:
        self.source_model_identity = source_identity
        self.scratch_path = r"C:\tmp\source.tbdy-b4s-test.edb"
        self.ownership_proof_ref = "owned-scratch:test"
        snapshot = SimpleNamespace(
            canonical_absolute_path=r"C:\tmp\source.edb",
            exists=True,
            file_size_bytes=1234,
            sha256_content_digest="a" * 64,
            mtime_ns=1,
        )
        self.source_pre = snapshot
        self.source_post = snapshot


class _FakeEstablishedState:
    def __init__(self, context, owned) -> None:
        self.analysis_state_identity = build_analysis_state_identity(
            source_model_ref=context.source_model_identity.source_model_ref,
            execution_state_ref="derived-state-established:test",
            state_basis_refs=(
                owned.ownership_proof_ref,
                "requested-state:test",
                "mutation-manifest:test",
            ),
            provenance_refs=("b4b:test",),
        )
        self.mutation_manifest = SimpleNamespace(
            ownership_proof_ref=owned.ownership_proof_ref,
            manifest_ref="mutation-manifest:test",
        )
        self.requested_manifest = SimpleNamespace(manifest_ref="requested-state:test")


@pytest.fixture
def harness(monkeypatch):
    context = _FakeContext()
    owned = _FakeOwnedScratch(context.source_model_identity)
    established = _FakeEstablishedState(context, owned)

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(subject, "OwnedScratchContext", _FakeOwnedScratch)
    monkeypatch.setattr(subject, "AnalysisStateMutationResult", _FakeEstablishedState)

    state = {
        "path": owned.scratch_path,
        "locked": False,
        "run_flags": {"DEAD": True, "MODAL": False, "EX": True},
        "statuses": {"DEAD": 4, "MODAL": 4, "EX": 4},
        "run_return": 0,
        "run_exception": None,
        "unfinished_cases": set(),
        "revalidation_error": None,
        "set_fail_on_call": None,
        "set_calls": 0,
        "delete_calls": 0,
        "run_calls": 0,
        "source_digest": "a" * 64,
    }

    def identity(_session, *, timeout_seconds=30.0):
        return SimpleNamespace(
            model_full_path=state["path"],
            model_locked=state["locked"],
        )

    monkeypatch.setattr(subject, "reread_verified_session_identity", identity)

    def source_snapshot(_path):
        return SimpleNamespace(
            canonical_absolute_path=r"C:\tmp\source.edb",
            exists=True,
            file_size_bytes=1234,
            sha256_content_digest=state["source_digest"],
            mtime_ns=1,
        )

    monkeypatch.setattr(subject, "capture_physical_file_snapshot", source_snapshot)

    def flags_fact(_session, *, timeout_seconds=30.0):
        return RunCaseFlagSnapshotFact(
            case_flags=tuple(state["run_flags"].items()),
            return_code=0,
        )

    def set_flag(
        _session,
        *,
        case_name,
        run,
        all_cases=False,
        timeout_seconds=30.0,
    ):
        state["set_calls"] += 1
        if state["set_fail_on_call"] == state["set_calls"]:
            return RunCaseFlagSetFact(
                case_name=case_name,
                run=run,
                all_cases=all_cases,
                return_code=9,
            )
        if all_cases:
            for name in tuple(state["run_flags"]):
                state["run_flags"][name] = run
        else:
            state["run_flags"][case_name] = run
        return RunCaseFlagSetFact(
            case_name=case_name,
            run=run,
            all_cases=all_cases,
            return_code=0,
        )

    def delete_results(
        _session,
        *,
        case_name,
        all_cases=False,
        timeout_seconds=30.0,
    ):
        state["delete_calls"] += 1
        if all_cases:
            for name in tuple(state["statuses"]):
                state["statuses"][name] = 1
        else:
            state["statuses"][case_name] = 1
        return DeleteAnalysisResultsFact(
            case_name=case_name,
            all_cases=all_cases,
            return_code=0,
        )

    def status_fact(_session, *, timeout_seconds=30.0):
        return CaseStatusPopulationFact(
            case_statuses=tuple(state["statuses"].items()),
            return_code=0,
        )

    def readiness(_session, case_name, *, timeout_seconds=30.0):
        code = state["statuses"].get(case_name)
        mapping = {
            1: AnalysisReadiness.ANALYSIS_NOT_RUN,
            2: AnalysisReadiness.ANALYSIS_COULD_NOT_START,
            3: AnalysisReadiness.ANALYSIS_INCOMPLETE,
            4: AnalysisReadiness.ANALYSIS_FINISHED,
        }
        return SimpleNamespace(
            case_name=case_name,
            readiness=mapping.get(code, AnalysisReadiness.ANALYSIS_UNKNOWN),
            etabs_status_code=code,
        )

    def run_analysis(_session, *, timeout_seconds=300.0):
        state["run_calls"] += 1
        if state["run_exception"] is not None:
            raise state["run_exception"]
        ret = state["run_return"]
        if ret == 0:
            for name, enabled in state["run_flags"].items():
                if enabled:
                    state["statuses"][name] = (
                        3 if name in state["unfinished_cases"] else 4
                    )
        return RunAnalysisFact(return_code=ret)

    comparison = SimpleNamespace(
        comparison_ref="derived-state-comparison:test",
        matched=True,
        exact_causal_family_population=True,
    )

    def revalidate(**kwargs):
        if state["revalidation_error"] is not None:
            raise state["revalidation_error"]
        return SimpleNamespace(
            matched_exact=True,
            comparison=comparison,
            current_analysis_state=established.analysis_state_identity,
        )

    monkeypatch.setattr(subject, "get_run_case_flags_from_session", flags_fact)
    monkeypatch.setattr(subject, "set_run_case_flag_from_session", set_flag)
    monkeypatch.setattr(subject, "delete_analysis_results_from_session", delete_results)
    monkeypatch.setattr(subject, "get_case_status_population_from_session", status_fact)
    monkeypatch.setattr(subject, "read_verified_analysis_readiness", readiness)
    monkeypatch.setattr(subject, "run_analysis_from_session", run_analysis)
    monkeypatch.setattr(subject, "revalidate_frame_modifier_analysis_state", revalidate)

    return SimpleNamespace(
        context=context,
        owned=owned,
        established=established,
        state=state,
    )


def test_positive_execution_qualifies_exact_predeclared_scope_and_restores_flags(harness):
    before = dict(harness.state["run_flags"])

    result = subject.execute_controlled_analysis(
        context=harness.context,
        owned_scratch=harness.owned,
        established_state=harness.established,
        requested_case_names=("MODAL", "EX"),
    )

    assert result.qualification.qualified is True
    assert result.analysis_result_identity.parent_analysis_state_ref == (
        harness.established.analysis_state_identity.identity_ref
    )
    assert result.analysis_result_identity.analysis_generation_ref.startswith(
        subject.ANALYSIS_GENERATION_REF_PREFIX
    )
    assert result.analysis_result_identity.result_scope_refs == (
        result.manifest.scope.result_scope_refs
    )
    assert result.manifest.scope.case_names == ("EX", "MODAL")
    assert result.manifest.run_analysis.return_code == 0
    assert harness.state["run_calls"] == 1
    assert harness.state["delete_calls"] == 1
    assert harness.state["run_flags"] == before
    assert result.manifest.run_flags_before.case_flags == result.manifest.run_flags_restored.case_flags
    assert result.execution_proof_ref == result.manifest.execution_proof_ref


def test_scope_identity_is_deterministic_and_runtime_generation_is_not_part_of_scope():
    left = subject.AnalysisExecutionScope.from_case_names(("MODAL", "EX"))
    right = subject.AnalysisExecutionScope.from_case_names(("EX", "MODAL"))

    assert left.scope_ref == right.scope_ref
    assert left.result_scope_refs == right.result_scope_refs


def test_duplicate_requested_case_is_rejected_before_execution(harness):
    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX", "EX"),
        )

    assert exc.value.stage == "scope_contract"
    assert harness.state["run_calls"] == 0


def test_naked_analysis_state_identity_cannot_be_substituted_for_b4b_result(harness):
    with pytest.raises(TypeError, match="naked AnalysisStateIdentity"):
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established.analysis_state_identity,
            requested_case_names=("EX",),
        )
    assert harness.state["run_calls"] == 0


def test_wrong_source_fails_before_run_scope_mutation(harness):
    harness.established.analysis_state_identity = build_analysis_state_identity(
        source_model_ref="source-model-ref:wrong",
        execution_state_ref="derived-state-established:test",
        state_basis_refs=("basis:test",),
    )

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX",),
        )

    assert exc.value.stage == "source_binding"
    assert harness.state["set_calls"] == 0
    assert harness.state["run_calls"] == 0


def test_missing_requested_case_fails_before_any_run_analysis(harness):
    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("DOES_NOT_EXIST",),
        )

    assert exc.value.stage == "scope_reconciliation"
    assert harness.state["run_calls"] == 0


def test_preexisting_finished_rows_are_explicitly_cleared_before_run(harness):
    assert all(value == 4 for value in harness.state["statuses"].values())

    result = subject.execute_controlled_analysis(
        context=harness.context,
        owned_scratch=harness.owned,
        established_state=harness.established,
        requested_case_names=("EX",),
    )

    assert result.manifest.pre_case_status.as_mapping()["EX"] == 4
    assert result.manifest.cleared_case_status.as_mapping()["EX"] == 1
    assert result.manifest.post_case_status.as_mapping()["EX"] == 4
    assert harness.state["delete_calls"] == 1


def test_run_analysis_nonzero_yields_no_result_and_restores_run_flags(harness):
    before = dict(harness.state["run_flags"])
    harness.state["run_return"] = 7

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX", "MODAL"),
        )

    assert exc.value.stage == "run_analysis_nonzero"
    assert exc.value.restoration_status is subject.RunFlagRestorationStatus.RESTORED
    assert harness.state["run_flags"] == before
    assert harness.state["run_calls"] == 1


def test_run_analysis_exception_yields_no_result_and_restores_run_flags(harness):
    before = dict(harness.state["run_flags"])
    harness.state["run_exception"] = RuntimeError("simulated analysis failure")

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX",),
        )

    assert exc.value.stage == "run_analysis_exception"
    assert exc.value.restoration_status is subject.RunFlagRestorationStatus.RESTORED
    assert harness.state["run_flags"] == before
    assert harness.state["run_calls"] == 1


def test_one_unfinished_case_rejects_entire_successful_subset(harness):
    harness.state["unfinished_cases"] = {"MODAL"}

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX", "MODAL"),
        )

    assert exc.value.stage == "post_case_readiness"
    assert exc.value.details["case_name"] == "MODAL"
    assert harness.state["statuses"]["EX"] == 4
    assert harness.state["run_calls"] == 1


def test_post_run_causal_state_mismatch_rejects_result(harness):
    calls = {"n": 0}

    def fail_second_revalidation(**kwargs):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise AnalysisStateRevalidationError(
                "simulated state drift",
                stage="identity_mismatch",
            )
        return SimpleNamespace(
            matched_exact=True,
            comparison=SimpleNamespace(comparison_ref=f"comparison:{calls['n']}"),
            current_analysis_state=harness.established.analysis_state_identity,
        )

    # Revalidation occurs before scope mutation, after DeleteResults, and after run.
    subject.revalidate_frame_modifier_analysis_state = fail_second_revalidation

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX",),
        )

    assert exc.value.stage == "unexpected_execution_error"
    assert exc.value.restoration_status is subject.RunFlagRestorationStatus.RESTORED
    assert harness.state["run_calls"] == 1


def test_active_model_drift_blocks_failure_restoration(harness):
    def run_and_switch(_session, *, timeout_seconds=300.0):
        harness.state["run_calls"] += 1
        harness.state["path"] = r"C:\tmp\other.edb"
        return RunAnalysisFact(return_code=9)

    subject.run_analysis_from_session = run_and_switch

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX",),
        )

    assert exc.value.stage == "run_analysis_nonzero"
    assert exc.value.restoration_status is subject.RunFlagRestorationStatus.BLOCKED_UNSAFE


def test_run_flag_restoration_failure_rejects_otherwise_successful_execution(harness):
    # Calls: all-off + enable EX = 2; restoration all-off is call 3.
    harness.state["set_fail_on_call"] = 3

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX",),
        )

    assert exc.value.stage == "run_flag_restore"
    assert exc.value.restoration_status is subject.RunFlagRestorationStatus.FAILED
    assert harness.state["run_calls"] == 1


def test_protected_source_byte_change_rejects_qualification(harness):
    original_restore = subject._restore_run_flags

    def restore_then_change(**kwargs):
        result = original_restore(**kwargs)
        harness.state["source_digest"] = "b" * 64
        return result

    subject._restore_run_flags = restore_then_change

    with pytest.raises(subject.AnalysisExecutionError) as exc:
        subject.execute_controlled_analysis(
            context=harness.context,
            owned_scratch=harness.owned,
            established_state=harness.established,
            requested_case_names=("EX",),
        )

    assert exc.value.stage == "source_post_execution_integrity"
    assert harness.state["run_calls"] == 1


def test_retry_after_failure_gets_new_attempt_and_generation(harness):
    harness.state["run_return"] = 5
    refs = []

    for _ in range(2):
        with pytest.raises(subject.AnalysisExecutionError) as exc:
            subject.execute_controlled_analysis(
                context=harness.context,
                owned_scratch=harness.owned,
                established_state=harness.established,
                requested_case_names=("EX",),
            )
        refs.append((exc.value.attempt_ref, exc.value.generation_ref))

    assert refs[0][0] != refs[1][0]
    assert refs[0][1] != refs[1][1]
    assert all(ref and ref.startswith(subject.ANALYSIS_ATTEMPT_REF_PREFIX) for ref, _ in refs)
    assert all(gen and gen.startswith(subject.ANALYSIS_GENERATION_REF_PREFIX) for _, gen in refs)


def test_execution_api_has_no_caller_generation_parameter():
    import inspect

    params = inspect.signature(subject.execute_controlled_analysis).parameters
    assert "analysis_generation_ref" not in params
    assert "generation_ref" not in params
    assert "attempt_ref" not in params
    assert "analysis_result_identity" not in params
    assert "qualification" not in params
