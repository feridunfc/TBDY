from __future__ import annotations

from dataclasses import dataclass
import threading

import pytest

import etabs_gateway.connection as connection_module
from etabs_gateway import ETABSGatewaySession
from etabs_gateway.errors import ETABSCallError, ETABSSessionStateError
from etabs_gateway.mutation_transport import (
    _B4T_MUTATION_TRANSPORT_KEY,
    _execute_bounded_model_mutation,
)


class _PythonCOM:
    COINIT_APARTMENTTHREADED = 2

    def CoInitializeEx(self, flags: int) -> None:
        assert flags == self.COINIT_APARTMENTTHREADED

    def CoUninitialize(self) -> None:
        return None


class _Model:
    def __init__(self) -> None:
        self.mutation_count = 0

    def GetVersion(self):
        return ("23.0.0", 1200, 0)

    def GetModelFilename(self, include_path: bool):
        assert include_path is True
        return (r"C:\models\b4t-disposable.edb", 0)

    def GetModelIsLocked(self):
        return (False, 0)

    def GetPresentUnits(self):
        return (6, 0)


class _Application:
    def __init__(self, model: _Model) -> None:
        self.SapModel = model


class _Runtime:
    def __init__(self, application: _Application) -> None:
        self.application = application
        self.calls: list[str] = []

    def GetActiveObject(self, prog_id: str):
        self.calls.append(prog_id)
        return self.application


class _ChildCOMProxy:
    pass


@dataclass(frozen=True, slots=True)
class _MutationFact:
    return_code: int
    worker_thread_id: int
    mutation_count: int
    raw_response: tuple[object, ...]


@dataclass(slots=True)
class _MutableFact:
    return_code: int


@pytest.fixture
def started_session():
    model = _Model()
    application = _Application(model)
    runtime = _Runtime(application)
    session = ETABSGatewaySession(
        com_module_loader=lambda: _PythonCOM(),
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
        worker_name="b4t-fake-sta",
    )
    session.start()
    try:
        yield session, application, model, runtime
    finally:
        session.close(timeout_seconds=1.0)


def _run(session: ETABSGatewaySession, function, *, operation: str = "b4t_test"):
    return _execute_bounded_model_mutation(
        session,
        function,
        operation=operation,
        timeout_seconds=1.0,
        _transport_key=_B4T_MUTATION_TRANSPORT_KEY,
    )


def test_mutation_executes_on_existing_dedicated_sta_and_returns_factual_value(started_session):
    session, _application, model, _runtime = started_session
    caller_thread = threading.get_ident()

    def mutate(model_api):
        model_api.mutation_count += 1
        return _MutationFact(
            return_code=0,
            worker_thread_id=threading.get_ident(),
            mutation_count=model_api.mutation_count,
            raw_response=(0, "mocked-set"),
        )

    fact = _run(session, mutate)

    assert fact.return_code == 0
    assert fact.mutation_count == 1
    assert model.mutation_count == 1
    assert fact.worker_thread_id == session.context.attachment.worker_thread_id
    assert fact.worker_thread_id != caller_thread


def test_private_capability_key_is_required_before_mutation_can_execute(started_session):
    session, _application, model, _runtime = started_session

    with pytest.raises(TypeError, match="private to trusted ETABS boundaries"):
        _execute_bounded_model_mutation(
            session,
            lambda model_api: setattr(model_api, "mutation_count", 999),
            operation="missing_key",
        )

    assert model.mutation_count == 0


def test_raw_sapmodel_cannot_escape_mutation_result(started_session):
    session, _application, _model, _runtime = started_session

    with pytest.raises(ETABSCallError) as caught:
        _run(session, lambda model_api: model_api, operation="raw_model_escape")

    assert caught.value.details["stage"] == "raw_owner_reference_escape"
    assert caught.value.details["path"] == "$"


def test_raw_application_cannot_escape_mutation_result(started_session):
    session, application, _model, _runtime = started_session

    with pytest.raises(ETABSCallError) as caught:
        _run(session, lambda _model_api: application, operation="raw_app_escape")

    assert caught.value.details["stage"] == "raw_owner_reference_escape"


def test_arbitrary_com_like_child_object_cannot_escape_nested_result(started_session):
    session, _application, _model, _runtime = started_session
    child = _ChildCOMProxy()

    with pytest.raises(ETABSCallError) as caught:
        _run(
            session,
            lambda _model_api: {"ret": 0, "child": ("nested", child)},
            operation="child_com_escape",
        )

    assert caught.value.details["stage"] == "unsafe_result_type"
    assert caught.value.details["result_type"] == "_ChildCOMProxy"


def test_mutable_or_arbitrary_result_objects_are_rejected(started_session):
    session, _application, _model, _runtime = started_session

    with pytest.raises(ETABSCallError) as mutable:
        _run(session, lambda _model_api: _MutableFact(0), operation="mutable_fact")
    assert mutable.value.details["stage"] == "mutable_dataclass_result"

    with pytest.raises(ETABSCallError) as arbitrary:
        _run(session, lambda _model_api: object(), operation="arbitrary_object")
    assert arbitrary.value.details["stage"] == "unsafe_result_type"


def test_session_must_be_ready_before_private_mutation_transport_runs():
    session = ETABSGatewaySession(
        com_module_loader=lambda: _PythonCOM(),
        runtime_loader=lambda: _Runtime(_Application(_Model())),
        prog_ids=("ETABS.TEST",),
    )
    try:
        with pytest.raises(ETABSSessionStateError, match="require a ready gateway session"):
            _run(session, lambda _model_api: 0, operation="not_ready")
    finally:
        session.close(timeout_seconds=1.0)


def test_fake_dependency_universe_remains_closed_for_mutation_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_loader_hits: list[str] = []

    def poison_win32():
        default_loader_hits.append("win32com.client")
        raise AssertionError("default win32com must remain unreachable")

    def poison_comtypes():
        default_loader_hits.append("comtypes.client")
        raise AssertionError("default comtypes must remain unreachable")

    monkeypatch.setattr(connection_module, "_load_win32com_client", poison_win32)
    monkeypatch.setattr(connection_module, "_load_comtypes_client", poison_comtypes)

    model = _Model()
    runtime = _Runtime(_Application(model))
    session = ETABSGatewaySession(
        com_module_loader=lambda: _PythonCOM(),
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
        worker_name="b4t-closed-fake-sta",
    )
    session.start()
    try:
        assert _run(session, lambda model_api: (0, model_api.mutation_count)) == (0, 0)
        assert runtime.calls == ["ETABS.TEST"]
        assert default_loader_hits == []
    finally:
        session.close(timeout_seconds=1.0)
