from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.concrete_design as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError


class _DesignConcrete:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def GetCode(self):
        self.calls += 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_get_code_exact_success_tuple_emits_factual_ref() -> None:
    raw = ("CURRENT-CONCRETE-CODE", 0)
    fact = subject.decode_design_code_response(raw)

    assert fact.code_name == "CURRENT-CONCRETE-CODE"
    assert fact.raw_response is raw
    assert fact.source_api == "DesignConcrete.GetCode"
    assert fact.design_code_ref.startswith("etabs-concrete-design-code:sha256:")


def test_get_code_ref_is_deterministic_and_code_sensitive() -> None:
    first = subject.decode_design_code_response(("CODE-A", 0))
    same = subject.decode_design_code_response(("CODE-A", 0))
    changed = subject.decode_design_code_response(("CODE-B", 0))

    assert first.design_code_ref == same.design_code_ref
    assert first.design_code_ref != changed.design_code_ref


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "CODE-A",
        ["CODE-A", 0],
        ("CODE-A",),
        ("CODE-A", 0, "extra"),
        ("CODE-A", True),
        ("CODE-A", 1),
        ("", 0),
        (" CODE-A", 0),
    ],
)
def test_get_code_rejects_malformed_or_non_success_response(raw) -> None:
    with pytest.raises(EtabsOAPIError):
        subject.decode_design_code_response(raw)


def test_get_code_method_exception_is_bounded_oapi_error() -> None:
    api = _DesignConcrete(RuntimeError("boom"))
    with pytest.raises(EtabsOAPIError, match="RuntimeError: boom"):
        subject.read_design_code(api)


def test_get_code_unavailable_method_fails_closed() -> None:
    with pytest.raises(EtabsOAPIError, match="GetCode is unavailable"):
        subject.read_design_code(SimpleNamespace())


def test_session_bound_get_code_requires_verified_session() -> None:
    with pytest.raises(TypeError, match="session must be EtabsVerifiedSession"):
        subject.read_design_code_from_session(object())


def test_session_bound_get_code_uses_verified_read_boundary(monkeypatch) -> None:
    session = object()
    calls = []

    def execute(verified_session, callback, *, operation, timeout_seconds=30.0):
        calls.append((verified_session, operation, timeout_seconds))
        sap = SimpleNamespace(DesignConcrete=_DesignConcrete(("CODE-A", 0)))
        return callback(object(), sap)

    monkeypatch.setattr(subject, "_execute_verified_read", execute)

    fact = subject.read_design_code_from_session(session, timeout_seconds=8.25)

    assert fact.code_name == "CODE-A"
    assert calls == [(session, "oapi_design_concrete_get_code", 8.25)]


def test_get_code_production_source_contains_no_project_code_literal_or_raw_sapmodel_api() -> None:
    source = inspect.getsource(subject.read_design_code_from_session)
    assert "TS500" not in source
    assert "TS 500" not in source
    assert "SapModel" not in source
    assert "_execute_verified_read" in source
