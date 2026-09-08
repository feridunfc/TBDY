from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.frame_releases as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _FakeSession:
    pass


class _FrameObj:
    def __init__(self) -> None:
        self.calls = []
        self.raw = (
            [False, False, False, False, False, True],
            [False, False, False, False, True, False],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1250.0],
            [0.0, 0.0, 0.0, 0.0, 900.0, 0.0],
            0,
        )

    def GetReleases(self, name):
        self.calls.append(name)
        return self.raw


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    frame = _FrameObj()
    model = SimpleNamespace(FrameObj=frame)

    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def fake_read(_session, function, *, operation, timeout_seconds=30.0):
        assert _session is session
        assert operation == "oapi_frame_obj_get_releases"
        assert timeout_seconds > 0.0
        return function(object(), model)

    monkeypatch.setattr(subject, "_execute_verified_read", fake_read)
    return session, frame


def test_get_releases_preserves_four_exact_six_slot_vectors_without_naming_slots(runtime):
    session, frame = runtime

    fact = subject.get_frame_releases_from_session(session, frame_name="F1")

    assert frame.calls == ["F1"]
    assert fact.success is True
    assert fact.frame_name == "F1"
    assert fact.i_end_released == (False, False, False, False, False, True)
    assert fact.j_end_released == (False, False, False, False, True, False)
    assert fact.i_end_partial_fixity == (0.0, 0.0, 0.0, 0.0, 0.0, 1250.0)
    assert fact.j_end_partial_fixity == (0.0, 0.0, 0.0, 0.0, 900.0, 0.0)
    assert fact.evidence_ref.startswith(subject.FRAME_RELEASE_EVIDENCE_PREFIX)
    assert not hasattr(fact, "m2_i_released")
    assert not hasattr(fact, "m3_i_released")


def test_get_releases_preserves_nonzero_return_as_factual_failure(runtime):
    session, frame = runtime
    frame.raw = ([False] * 6, [False] * 6, [0.0] * 6, [0.0] * 6, 9)

    fact = subject.get_frame_releases_from_session(session, frame_name="F1")

    assert fact.return_code == 9
    assert fact.success is False


@pytest.mark.parametrize(
    "raw",
    [
        0,
        ([False] * 6, [False] * 6, [0.0] * 6, 0),
        ([False] * 5, [False] * 6, [0.0] * 6, [0.0] * 6, 0),
        ([False] * 6, [False] * 7, [0.0] * 6, [0.0] * 6, 0),
        ([False] * 6, [False] * 6, [0.0] * 5, [0.0] * 6, 0),
        ([False] * 6, [False] * 6, [0.0] * 6, [0.0] * 7, 0),
        ([False] * 6, [False] * 6, [0.0] * 6, [0.0] * 6, 0, 1),
    ],
)
def test_get_releases_rejects_unknown_python_abi_shapes(runtime, raw):
    session, frame = runtime
    frame.raw = raw

    with pytest.raises(EtabsOAPIError, match="ABI shape"):
        subject.get_frame_releases_from_session(session, frame_name="F1")


@pytest.mark.parametrize("bad", [0, 1, None, "False", 0.0])
def test_release_flags_require_boolean_values(runtime, bad):
    session, frame = runtime
    flags = [False] * 6
    flags[4] = bad
    frame.raw = (flags, [False] * 6, [0.0] * 6, [0.0] * 6, 0)

    with pytest.raises(EtabsOAPIError, match="boolean"):
        subject.get_frame_releases_from_session(session, frame_name="F1")


@pytest.mark.parametrize("bad", [True, "0", float("nan"), float("inf")])
def test_partial_fixity_requires_finite_numeric_values(runtime, bad):
    session, frame = runtime
    springs = [0.0] * 6
    springs[5] = bad
    frame.raw = ([False] * 6, [False] * 6, springs, [0.0] * 6, 0)

    with pytest.raises(EtabsOAPIError, match="finite numeric"):
        subject.get_frame_releases_from_session(session, frame_name="F1")


def test_get_releases_requires_verified_session_type(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    with pytest.raises(TypeError, match="EtabsVerifiedSession"):
        subject.get_frame_releases_from_session(object(), frame_name="F1")


def test_get_releases_rejects_noncanonical_name(runtime):
    session, _frame = runtime

    with pytest.raises(EtabsOAPIError, match="canonical"):
        subject.get_frame_releases_from_session(session, frame_name=" F1 ")
