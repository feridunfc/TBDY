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

    def execute(verified_session, callback, *, operation):
        calls.append((verified_session, operation))
        sap = SimpleNamespace(DesignConcrete=_DesignConcrete(False))
        return callback(object(), sap)

    monkeypatch.setattr(subject, "_execute_verified_read", execute)

    fact = subject.read_results_available_from_session(session)

    assert fact.results_available is False
    assert calls == [
        (session, "oapi_design_concrete_get_results_available")
    ]
