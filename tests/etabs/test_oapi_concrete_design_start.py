from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.concrete_design as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    def __init__(self) -> None:
        self._gateway_session = object()


class _DesignConcrete:
    def __init__(self, raw) -> None:
        self.raw = raw
        self.calls = 0

    def StartDesign(self):
        self.calls += 1
        if isinstance(self.raw, BaseException):
            raise self.raw
        return self.raw


@pytest.fixture
def transport(monkeypatch):
    calls = []
    model = SimpleNamespace(DesignConcrete=_DesignConcrete(0))

    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def execute(
        gateway_session,
        callback,
        *,
        operation,
        timeout_seconds,
        _transport_key,
    ):
        calls.append(
            (
                gateway_session,
                operation,
                timeout_seconds,
                _transport_key,
            )
        )
        return callback(model)

    monkeypatch.setattr(subject, "_execute_bounded_model_mutation", execute)
    return model, calls


def test_start_design_uses_bounded_mutation_once_and_returns_exact_fact(
    transport,
) -> None:
    model, calls = transport
    session = _FakeSession()

    fact = subject.start_concrete_design_from_session(
        session,
        timeout_seconds=12.5,
    )

    assert fact.return_code == 0
    assert fact.success is True
    assert model.DesignConcrete.calls == 1
    assert calls == [
        (
            session._gateway_session,
            "oapi_design_concrete_start_design",
            12.5,
            subject._B4T_MUTATION_TRANSPORT_KEY,
        )
    ]


def test_start_design_nonzero_return_is_preserved_as_failed_fact(transport) -> None:
    model, _calls = transport
    model.DesignConcrete.raw = 7

    fact = subject.start_concrete_design_from_session(_FakeSession())

    assert fact.return_code == 7
    assert fact.success is False
    assert model.DesignConcrete.calls == 1


def test_start_design_accepts_single_integer_tuple_return_shape(transport) -> None:
    model, _calls = transport
    model.DesignConcrete.raw = (0,)

    fact = subject.start_concrete_design_from_session(_FakeSession())

    assert fact.return_code == 0
    assert fact.success is True


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        (),
        (0, 1),
        (False, True),
        "0",
    ],
)
def test_start_design_rejects_unsupported_return_code_shapes(transport, raw) -> None:
    model, _calls = transport
    model.DesignConcrete.raw = raw

    with pytest.raises(EtabsOAPIError, match="unsupported return-code ABI shape"):
        subject.start_concrete_design_from_session(_FakeSession())


def test_start_design_unavailable_method_fails_closed(transport) -> None:
    model, _calls = transport
    model.DesignConcrete = SimpleNamespace()

    with pytest.raises(EtabsOAPIError, match="StartDesign is unavailable"):
        subject.start_concrete_design_from_session(_FakeSession())


def test_start_design_requires_verified_session_type(monkeypatch) -> None:
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    with pytest.raises(TypeError, match="EtabsVerifiedSession"):
        subject.start_concrete_design_from_session(object())


@pytest.mark.parametrize("timeout", [0.0, -1.0])
def test_start_design_rejects_nonpositive_timeout(monkeypatch, timeout) -> None:
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    with pytest.raises(ValueError, match="greater than zero"):
        subject.start_concrete_design_from_session(
            _FakeSession(),
            timeout_seconds=timeout,
        )
