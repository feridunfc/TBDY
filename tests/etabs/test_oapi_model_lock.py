from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.model_lock as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    def __init__(self) -> None:
        self._gateway_session = object()


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    state = {"raw": 0, "calls": []}
    model = SimpleNamespace()

    def set_locked(value):
        state["calls"].append(value)
        return state["raw"]

    model.SetModelIsLocked = set_locked

    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def fake_mutation(
        gateway_session,
        function,
        *,
        operation,
        timeout_seconds=30.0,
        _transport_key=None,
    ):
        assert gateway_session is session._gateway_session
        assert operation == "oapi_set_model_is_locked"
        assert timeout_seconds > 0
        assert _transport_key is subject._B4T_MUTATION_TRANSPORT_KEY
        return function(model)

    monkeypatch.setattr(
        subject,
        "_execute_bounded_model_mutation",
        fake_mutation,
    )
    return session, state


def test_unlock_uses_existing_bounded_transport_and_preserves_return(runtime):
    session, state = runtime

    fact = subject.set_model_lock_from_session(
        session,
        locked=False,
    )

    assert fact.requested_locked is False
    assert fact.return_code == 0
    assert fact.success is True
    assert state["calls"] == [False]
    assert fact.evidence_ref.startswith(
        subject.MODEL_LOCK_EVIDENCE_PREFIX
    )


def test_nonzero_return_is_factual_failure(runtime):
    session, state = runtime
    state["raw"] = 7

    fact = subject.set_model_lock_from_session(
        session,
        locked=False,
    )

    assert fact.return_code == 7
    assert fact.success is False


def test_reflected_single_return_code_shape_is_accepted(runtime):
    session, state = runtime
    state["raw"] = (0,)

    fact = subject.set_model_lock_from_session(
        session,
        locked=False,
    )

    assert fact.success is True


@pytest.mark.parametrize("raw", [None, (), (0, 1), ("bad", 0)])
def test_ambiguous_return_shape_fails_closed(runtime, raw):
    session, state = runtime
    state["raw"] = raw

    with pytest.raises(EtabsOAPIError):
        subject.set_model_lock_from_session(
            session,
            locked=False,
        )
