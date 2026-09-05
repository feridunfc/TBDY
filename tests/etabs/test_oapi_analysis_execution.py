from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.analysis_execution as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    def __init__(self) -> None:
        self._gateway_session = object()


class _Analyze:
    def __init__(self) -> None:
        self.run_flags = (2, ("DEAD", "MODAL"), (True, False), 0)
        self.case_status = (2, ("DEAD", "MODAL"), (4, 1), 0)
        self.set_ret = 0
        self.delete_ret = 0
        self.run_ret = 0
        self.set_calls: list[tuple[object, ...]] = []
        self.delete_calls: list[tuple[object, ...]] = []
        self.run_calls = 0

    def GetRunCaseFlag(self):
        return self.run_flags

    def GetCaseStatus(self):
        return self.case_status

    def SetRunCaseFlag(self, *args):
        self.set_calls.append(args)
        return self.set_ret

    def DeleteResults(self, *args):
        self.delete_calls.append(args)
        return self.delete_ret

    def RunAnalysis(self):
        self.run_calls += 1
        return self.run_ret


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    analyze = _Analyze()
    model = SimpleNamespace(Analyze=analyze)
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def fake_read(_session, function, *, operation, timeout_seconds=30.0):
        assert _session is session
        assert operation
        assert timeout_seconds > 0
        return function(object(), model)

    def fake_mutation(
        gateway_session,
        function,
        *,
        operation,
        timeout_seconds=30.0,
        _transport_key=None,
    ):
        assert gateway_session is session._gateway_session
        assert operation
        assert timeout_seconds > 0
        assert _transport_key is subject._B4T_MUTATION_TRANSPORT_KEY
        return function(model)

    monkeypatch.setattr(subject, "_execute_verified_read", fake_read)
    monkeypatch.setattr(subject, "_execute_bounded_model_mutation", fake_mutation)
    return session, analyze


def test_get_run_case_flags_uses_authoritative_count_and_canonicalizes(runtime):
    session, analyze = runtime
    analyze.run_flags = (
        2,
        ("MODAL", "DEAD", None, None),
        (False, True, None, None),
        0,
    )

    fact = subject.get_run_case_flags_from_session(session)

    assert fact.success is True
    assert fact.case_flags == (("DEAD", True), ("MODAL", False))
    assert fact.case_names == ("DEAD", "MODAL")
    assert fact.as_mapping() == {"DEAD": True, "MODAL": False}
    assert fact.evidence_ref.startswith(subject.ANALYSIS_EXECUTION_EVIDENCE_PREFIX)


def test_get_case_status_population_uses_authoritative_count(runtime):
    session, analyze = runtime
    analyze.case_status = (
        2,
        ("MODAL", "DEAD", None),
        (1, 4, None),
        0,
    )

    fact = subject.get_case_status_population_from_session(session)

    assert fact.success is True
    assert fact.case_statuses == (("DEAD", 4), ("MODAL", 1))
    assert fact.as_mapping() == {"DEAD": 4, "MODAL": 1}


@pytest.mark.parametrize(
    "raw",
    [
        0,
        (2, ("A", "B"), (True, False)),
        (2, ("A",), (True,), 0),
        (-1, (), (), 0),
        (1, ("A",), (1,), 0),
        (2, ("A", "A"), (True, False), 0),
        (1, (" A ",), (True,), 0),
        (True, ("A",), (True,), 0),
    ],
)
def test_get_run_case_flags_rejects_ambiguous_or_invalid_python_abi(runtime, raw):
    session, analyze = runtime
    analyze.run_flags = raw
    with pytest.raises(EtabsOAPIError):
        subject.get_run_case_flags_from_session(session)


@pytest.mark.parametrize(
    "raw",
    [
        (1, ("A",), (True,), 0),
        (1, ("A",), ("4",), 0),
        (2, ("A", "B"), (4,), 0),
    ],
)
def test_get_case_status_rejects_noninteger_or_incomplete_status_population(runtime, raw):
    session, analyze = runtime
    analyze.case_status = raw
    with pytest.raises(EtabsOAPIError):
        subject.get_case_status_population_from_session(session)


def test_getters_preserve_nonzero_return_as_factual_failure(runtime):
    session, analyze = runtime
    analyze.run_flags = (1, ("A",), (True,), 9)
    analyze.case_status = (1, ("A",), (4,), 8)

    flags = subject.get_run_case_flags_from_session(session)
    status = subject.get_case_status_population_from_session(session)

    assert flags.return_code == 9 and flags.success is False
    assert status.return_code == 8 and status.success is False


def test_set_run_case_flag_calls_exact_csi_signature_through_b4t(runtime):
    session, analyze = runtime

    fact = subject.set_run_case_flag_from_session(
        session,
        case_name="MODAL",
        run=True,
        all_cases=False,
    )

    assert fact.success is True
    assert analyze.set_calls == [("MODAL", True, False)]
    assert fact.case_name == "MODAL"
    assert fact.run is True
    assert fact.all_cases is False


def test_set_all_run_case_flags_uses_documented_all_boolean(runtime):
    session, analyze = runtime

    fact = subject.set_run_case_flag_from_session(
        session,
        case_name="DEAD",
        run=False,
        all_cases=True,
    )

    assert fact.success is True
    assert analyze.set_calls == [("DEAD", False, True)]


def test_delete_results_calls_exact_csi_signature_through_b4t(runtime):
    session, analyze = runtime

    fact = subject.delete_analysis_results_from_session(
        session,
        case_name="DEAD",
        all_cases=True,
    )

    assert fact.success is True
    assert analyze.delete_calls == [("DEAD", True)]


def test_run_analysis_is_one_exact_no_argument_b4t_call(runtime):
    session, analyze = runtime

    fact = subject.run_analysis_from_session(session)

    assert fact.success is True
    assert analyze.run_calls == 1


@pytest.mark.parametrize(
    ("operation", "attribute"),
    [
        ("set", "set_ret"),
        ("delete", "delete_ret"),
        ("run", "run_ret"),
    ],
)
def test_write_execution_facts_preserve_nonzero_return(runtime, operation, attribute):
    session, analyze = runtime
    setattr(analyze, attribute, 6)

    if operation == "set":
        fact = subject.set_run_case_flag_from_session(
            session, case_name="DEAD", run=True
        )
    elif operation == "delete":
        fact = subject.delete_analysis_results_from_session(
            session, case_name="DEAD", all_cases=True
        )
    else:
        fact = subject.run_analysis_from_session(session)

    assert fact.return_code == 6
    assert fact.success is False


@pytest.mark.parametrize("raw", [None, "0", (), (0, 1), (True,)])
def test_run_analysis_rejects_unknown_return_code_abi(runtime, raw):
    session, analyze = runtime
    analyze.run_ret = raw
    with pytest.raises(EtabsOAPIError, match="return-code ABI"):
        subject.run_analysis_from_session(session)
