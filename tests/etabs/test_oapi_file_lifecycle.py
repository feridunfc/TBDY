from __future__ import annotations

from pathlib import Path

import pytest

import tbdy_engine.etabs.oapi.file_lifecycle as subject


class _FakeVerifiedSession:
    def __init__(self) -> None:
        self._gateway_session = object()


class _FakeFile:
    def __init__(self, response: object) -> None:
        self.response = response
        self.paths: list[str] = []

    def OpenFile(self, path: str):
        self.paths.append(path)
        return self.response


class _FakeSap:
    def __init__(self, response: object) -> None:
        self.File = _FakeFile(response)


def _patch_verified_session_type(monkeypatch):
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeVerifiedSession)


def _patch_transport(monkeypatch, sap: _FakeSap, capture: dict[str, object] | None = None):
    record = {} if capture is None else capture

    def fake_transport(
        gateway_session,
        function,
        *,
        operation,
        timeout_seconds,
        _transport_key,
    ):
        record["gateway_session"] = gateway_session
        record["operation"] = operation
        record["timeout_seconds"] = timeout_seconds
        record["transport_key"] = _transport_key
        return function(sap)

    monkeypatch.setattr(subject, "_execute_bounded_model_mutation", fake_transport)
    return record


def test_typed_open_file_factual_success_uses_b4t_transport(monkeypatch, tmp_path: Path):
    _patch_verified_session_type(monkeypatch)
    session = _FakeVerifiedSession()
    sap = _FakeSap(0)
    record = _patch_transport(monkeypatch, sap)
    requested = tmp_path / "scratch.edb"

    fact = subject.open_file_from_session(session, requested, timeout_seconds=4.0)

    expected = subject._canonical_absolute_path(requested, label="expected")
    assert fact.canonical_requested_path == expected
    assert fact.return_code == 0
    assert fact.success is True
    assert sap.File.paths == [expected]
    assert record["gateway_session"] is session._gateway_session
    assert record["operation"] == "oapi_file_open_exact_path"
    assert record["timeout_seconds"] == 4.0
    assert record["transport_key"] is subject._B4T_MUTATION_TRANSPORT_KEY


def test_typed_open_file_nonzero_is_factual_not_owned_semantics(monkeypatch, tmp_path: Path):
    _patch_verified_session_type(monkeypatch)
    session = _FakeVerifiedSession()
    sap = _FakeSap(7)
    _patch_transport(monkeypatch, sap)

    fact = subject.open_file_from_session(session, tmp_path / "scratch.edb")

    assert fact.return_code == 7
    assert fact.success is False
    assert not hasattr(fact, "owned")
    assert not hasattr(fact, "verified_scratch")


@pytest.mark.parametrize(
    "response",
    [
        (0,),
        [0],
        {"return_code": 0},
        True,
        None,
        "0",
    ],
)
def test_unknown_open_file_abi_shape_fails_closed(monkeypatch, tmp_path: Path, response):
    _patch_verified_session_type(monkeypatch)
    session = _FakeVerifiedSession()
    sap = _FakeSap(response)
    _patch_transport(monkeypatch, sap)

    with pytest.raises(subject.FileLifecycleABIError, match="unsupported factual ABI shape"):
        subject.open_file_from_session(session, tmp_path / "scratch.edb")


@pytest.mark.parametrize("escape_kind", ["raw_sapmodel", "raw_application", "child_capability"])
def test_raw_owner_or_capability_return_cannot_cross_typed_oapi_boundary(
    monkeypatch,
    tmp_path: Path,
    escape_kind: str,
):
    _patch_verified_session_type(monkeypatch)
    session = _FakeVerifiedSession()
    sap = _FakeSap(0)
    raw_application = object()
    child_capability = object()
    if escape_kind == "raw_sapmodel":
        sap.File.response = sap
    elif escape_kind == "raw_application":
        sap.File.response = raw_application
    else:
        sap.File.response = child_capability
    _patch_transport(monkeypatch, sap)

    with pytest.raises(subject.FileLifecycleABIError, match="unsupported factual ABI shape"):
        subject.open_file_from_session(session, tmp_path / "scratch.edb")


def test_open_file_rejects_relative_or_blank_path_before_transport(monkeypatch):
    _patch_verified_session_type(monkeypatch)
    session = _FakeVerifiedSession()
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("transport must not run")

    monkeypatch.setattr(subject, "_execute_bounded_model_mutation", fail_if_called)

    with pytest.raises(ValueError):
        subject.open_file_from_session(session, "relative.edb")
    with pytest.raises(ValueError):
        subject.open_file_from_session(session, " ")

    assert called is False


def test_public_oapi_surface_contains_no_generic_mutation_callback():
    assert subject.__all__ == [
        "FileLifecycleABIError",
        "OPEN_FILE_FACT_CONTRACT",
        "OpenFileFact",
        "open_file_from_session",
    ]
    assert "_execute_bounded_model_mutation" not in subject.__all__
    assert "_B4T_MUTATION_TRANSPORT_KEY" not in subject.__all__
