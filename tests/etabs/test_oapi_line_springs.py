from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.line_springs as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    pass


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    state = {
        "raw": [0, (), 0],
        "calls": 0,
    }

    class PropLineSpring:
        def GetNameList(self):
            state["calls"] += 1
            return state["raw"]

    sap = SimpleNamespace(
        PropLineSpring=PropLineSpring(),
    )

    monkeypatch.setattr(
        subject,
        "EtabsVerifiedSession",
        _FakeSession,
    )

    def execute(
        _session,
        function,
        *,
        operation,
        timeout_seconds,
    ):
        assert _session is session
        assert operation == "oapi_prop_line_spring_get_name_list"
        assert timeout_seconds > 0.0
        return function(None, sap)

    monkeypatch.setattr(
        subject,
        "_execute_verified_read",
        execute,
    )

    return session, state


def test_empty_property_universe_is_positive_factual_empty(runtime):
    session, state = runtime

    fact = (
        subject.read_line_spring_property_universe_from_session(
            session,
        )
    )

    assert state["calls"] == 1
    assert fact.return_code == 0
    assert fact.reported_count == 0
    assert fact.property_names == ()
    assert fact.success is True
    assert fact.proven_empty is True
    assert fact.evidence_ref.startswith(
        subject.LINE_SPRING_PROPERTY_UNIVERSE_EVIDENCE_PREFIX
    )


def test_defined_property_universe_is_preserved_exactly(runtime):
    session, state = runtime
    state["raw"] = [
        2,
        ("LS-1", "LS-2"),
        0,
    ]

    fact = (
        subject.read_line_spring_property_universe_from_session(
            session,
        )
    )

    assert fact.property_names == (
        "LS-1",
        "LS-2",
    )
    assert fact.success is True
    assert fact.proven_empty is False


def test_nonzero_return_never_becomes_proven_empty(runtime):
    session, state = runtime
    state["raw"] = [0, (), 7]

    fact = (
        subject.read_line_spring_property_universe_from_session(
            session,
        )
    )

    assert fact.return_code == 7
    assert fact.success is False
    assert fact.proven_empty is False


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        (0, ()),
        (1, (), 0),
        (2, ("LS-1", "LS-1"), 0),
        ("0", (), 0),
        (0, (), "0"),
    ),
)
def test_malformed_get_name_list_fails_closed(runtime, raw):
    session, state = runtime
    state["raw"] = raw

    with pytest.raises(EtabsOAPIError):
        subject.read_line_spring_property_universe_from_session(
            session,
        )
