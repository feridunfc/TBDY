from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.eq713_response_cases as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    pass


class _StaticLinear:
    def __init__(self, loads):
        self.loads = loads
        self.calls = []

    def GetLoads(self, name):
        self.calls.append(name)
        return self.loads[name]


class _ResponseSpectrum:
    def GetLoads(self, name):
        assert name == "modal-not-an-axis-name"
        return (1, ("U1",), ("SPEC",), (1.0,), ("Global",), (0.0,), 0)


class _LoadCases:
    def __init__(self, loads):
        self.StaticLinear = _StaticLinear(loads)
        self.ResponseSpectrum = _ResponseSpectrum()

    def GetTypeOAPI_1(self, name):
        if name == "gravity-leaf":
            return (1, 0, 1, 0, 0, 0)
        if name == "modal-not-an-axis-name":
            return (4, 0, 5, 0, 0, 0)
        return (1, 0, 5, 0, 0, 0)


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    loads = {
        "quake-alpha": (1, ("Load",), ("PATTERN_X",), (1.0,), 0),
        "quake-beta": (1, ("Load",), ("PATTERN_Y",), (1.0,), 0),
        "quake-mixed": (
            2,
            ("Load", "Load"),
            ("PATTERN_X", "DEAD_PATTERN"),
            (1.0, 1.0),
            0,
        ),
    }
    load_cases = _LoadCases(loads)
    model = SimpleNamespace(LoadCases=load_cases)
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def verified_read(_session, function, *, operation, timeout_seconds=30.0):
        assert _session is session
        assert operation == "eq713_horizontal_response_case_scope"
        return function(object(), model)

    monkeypatch.setattr(subject, "_execute_verified_read", verified_read)
    return session, load_cases


def test_load_pattern_cases_use_exact_tsc2018_flags_and_ignore_gravity_names(runtime):
    session, load_cases = runtime
    scope = subject.qualify_eq713_horizontal_case_scope_from_session(
        session,
        candidate_case_names=(
            "gravity-leaf",
            "quake-alpha",
            "quake-beta",
            "modal-not-an-axis-name",
        ),
        tsc2018_pattern_directions={
            "PATTERN_X": (True, False),
            "PATTERN_Y": (False, True),
        },
        direction_source_refs=("session:verified", "tsc2018:table"),
    )

    assert "gravity-leaf" not in scope.case_names
    assert {fact.case_name for fact in scope.cases if fact.case_type == "LINEAR_STATIC"} == {
        "quake-alpha",
        "quake-beta",
    }
    assert any(fact.case_type == "RESPONSE_SPECTRUM" for fact in scope.cases)
    by_name = {fact.case_name: fact for fact in scope.cases}
    assert by_name["quake-alpha"].direction_vectors_xy == ((1.0, 0.0),)
    assert by_name["quake-beta"].direction_vectors_xy == ((0.0, 1.0),)
    assert load_cases.StaticLinear.calls == ["quake-alpha", "quake-beta"]
    assert "session:verified" in scope.source_refs


def test_unqualified_or_gravity_mixed_load_pattern_case_fails_closed(runtime):
    session, _load_cases = runtime
    with pytest.raises(EtabsOAPIError, match="no exact TSC-2018 direction fact"):
        subject.qualify_eq713_horizontal_case_scope_from_session(
            session,
            candidate_case_names=("quake-alpha", "quake-mixed", "quake-beta"),
            tsc2018_pattern_directions={
                "PATTERN_X": (True, False),
                "PATTERN_Y": (False, True),
            },
        )


def test_case_names_are_not_used_as_direction_inference(runtime):
    session, _load_cases = runtime
    scope = subject.qualify_eq713_horizontal_case_scope_from_session(
        session,
        candidate_case_names=("quake-alpha", "quake-beta"),
        tsc2018_pattern_directions={
            "PATTERN_X": (False, True),
            "PATTERN_Y": (True, False),
        },
    )
    by_name = {fact.case_name: fact for fact in scope.cases}
    assert by_name["quake-alpha"].direction_vectors_xy == ((0.0, 1.0),)
    assert by_name["quake-beta"].direction_vectors_xy == ((1.0, 0.0),)
