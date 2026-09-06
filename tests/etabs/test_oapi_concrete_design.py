from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.concrete_design as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _DesignConcrete:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def GetResultsAvailable(self):
        self.calls += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


def test_get_results_available_true_is_direct_boolean_fact() -> None:
    api = _DesignConcrete(True)

    fact = subject.read_results_available(api)

    assert fact.results_available is True
    assert fact.raw_response is True
    assert fact.source_api == "DesignConcrete.GetResultsAvailable"
    assert api.calls == 1


def test_get_results_available_false_is_direct_boolean_fact() -> None:
    fact = subject.decode_results_available_response(False)
    assert fact.results_available is False
    assert fact.raw_response is False


@pytest.mark.parametrize(
    "raw",
    [
        0,
        1,
        None,
        "False",
        (False, 0),
        [True, 0],
    ],
)
def test_get_results_available_rejects_invented_return_code_shapes(raw) -> None:
    with pytest.raises(EtabsOAPIError, match="direct Boolean"):
        subject.decode_results_available_response(raw)


def test_get_results_available_unavailable_method_fails_closed() -> None:
    with pytest.raises(EtabsOAPIError, match="GetResultsAvailable is unavailable"):
        subject.read_results_available(SimpleNamespace())


def test_get_results_available_exception_is_bounded_oapi_error() -> None:
    api = _DesignConcrete(RuntimeError("boom"))

    with pytest.raises(EtabsOAPIError, match="RuntimeError: boom"):
        subject.read_results_available(api)


def test_session_bound_get_results_available_uses_verified_read_boundary(
    monkeypatch,
) -> None:
    session = object()
    calls = []

    def execute(verified_session, callback, *, operation, timeout_seconds=30.0):
        calls.append((verified_session, operation, timeout_seconds))
        sap = SimpleNamespace(DesignConcrete=_DesignConcrete(False))
        return callback(object(), sap)

    monkeypatch.setattr(subject, "_execute_verified_read", execute)

    fact = subject.read_results_available_from_session(
        session,
        timeout_seconds=7.25,
    )

    assert fact.results_available is False
    assert calls == [
        (session, "oapi_design_concrete_get_results_available", 7.25)
    ]


def test_session_bound_summary_result_read_propagates_timeout(monkeypatch) -> None:
    session = object()
    calls = []
    sentinel = object()

    def execute(verified_session, callback, *, operation, timeout_seconds=30.0):
        calls.append((verified_session, operation, timeout_seconds))
        return callback(object(), SimpleNamespace(DesignConcrete=object()))

    monkeypatch.setattr(subject, "_execute_verified_read", execute)
    monkeypatch.setattr(
        subject,
        "read_summary_results_column",
        lambda _design_concrete, frame_name: sentinel if frame_name == "10" else None,
    )

    fact = subject.read_summary_results_column_from_session(
        session,
        "10",
        timeout_seconds=9.5,
    )

    assert fact is sentinel
    assert calls == [
        (session, "oapi_design_concrete_get_summary_results_column", 9.5)
    ]
