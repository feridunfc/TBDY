from __future__ import annotations

import threading
from dataclasses import FrozenInstanceError

import pytest

from etabs_gateway.contracts import GatewayState, HealthStatus
from etabs_gateway.errors import (
    ETABSNotRunningError,
    ETABSSessionCloseError,
    ETABSSessionStateError,
    ETABSVersionReadError,
)
from etabs_gateway.session import ETABSGatewaySession
from etabs_gateway.worker import WorkerState


class FakePythonCOM:
    COINIT_APARTMENTTHREADED = 2

    def __init__(
        self,
        *,
        finalize_error: BaseException | None = None,
    ) -> None:
        self.finalize_error = finalize_error
        self.initialize_threads: list[int] = []
        self.finalize_threads: list[int] = []

    def CoInitializeEx(self, flags: int) -> None:
        assert flags == self.COINIT_APARTMENTTHREADED
        self.initialize_threads.append(threading.get_ident())

    def CoUninitialize(self) -> None:
        self.finalize_threads.append(threading.get_ident())
        if self.finalize_error is not None:
            raise self.finalize_error


class FakeModelAPI:
    def __init__(
        self,
        *,
        version: object = ("23.0.0", 1200, 0),
    ) -> None:
        self.version = version
        self.calls: list[tuple[str, int]] = []

    def _record(self, name: str) -> None:
        self.calls.append((name, threading.get_ident()))

    def GetVersion(self) -> object:
        self._record("GetVersion")
        return self.version

    def GetModelFilename(self, include_path: bool) -> object:
        assert include_path is True
        self._record("GetModelFilename")
        return (r"C:\models\session.edb", 0)

    def GetModelIsLocked(self) -> object:
        self._record("GetModelIsLocked")
        return (True, 0)

    def GetPresentUnits(self) -> object:
        self._record("GetPresentUnits")
        return (6, 0)


class FakeApplication:
    def __init__(self, model_api: object) -> None:
        self.SapModel = model_api


class FakeRuntime:
    def __init__(
        self,
        application: object | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.application = application
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def GetActiveObject(self, prog_id: str) -> object:
        self.calls.append((prog_id, threading.get_ident()))
        if self.error is not None:
            raise self.error
        assert self.application is not None
        return self.application


def build_session(
    *,
    model: FakeModelAPI | None = None,
    runtime_error: BaseException | None = None,
    finalize_error: BaseException | None = None,
) -> tuple[ETABSGatewaySession, FakePythonCOM, FakeRuntime, FakeModelAPI]:
    resolved_model = model or FakeModelAPI()
    pythoncom = FakePythonCOM(finalize_error=finalize_error)
    runtime = FakeRuntime(
        FakeApplication(resolved_model),
        error=runtime_error,
    )
    session = ETABSGatewaySession(
        com_module_loader=lambda: pythoncom,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )
    return session, pythoncom, runtime, resolved_model


def test_construction_is_offline_safe_and_lazy() -> None:
    session, pythoncom, runtime, _ = build_session()

    assert session.state is GatewayState.NEW
    assert session.worker_state is WorkerState.NEW
    assert session.context is None
    assert pythoncom.initialize_threads == []
    assert runtime.calls == []

    assert session.close() is True
    assert session.close() is False


def test_start_orchestrates_attach_context_and_health() -> None:
    session, pythoncom, runtime, model = build_session()
    caller_thread = threading.get_ident()

    try:
        context = session.start()
        health = session.health()

        assert session.state is GatewayState.READY
        assert session.worker_state is WorkerState.RUNNING
        assert context.model.model_name == "session.edb"
        assert context.model.units is not None
        assert context.model.units.present_units_code == 6

        worker_threads = {thread_id for _, thread_id in model.calls}
        assert worker_threads == {context.attachment.worker_thread_id}
        assert context.attachment.worker_thread_id != caller_thread
        assert runtime.calls == [
            ("ETABS.TEST", context.attachment.worker_thread_id)
        ]
        assert pythoncom.initialize_threads == [
            context.attachment.worker_thread_id
        ]

        assert health.status is HealthStatus.HEALTHY
        assert health.state is GatewayState.READY
        assert health.application == context.application
        assert health.model == context.model
        assert [event.code for event in health.diagnostics.events] == [
            "ETABS_SESSION_STARTING",
            "ETABS_SESSION_READY",
        ]
    finally:
        session.close()


def test_public_session_does_not_expose_raw_com_references() -> None:
    session, _, _, _ = build_session()

    try:
        context = session.start()

        assert not hasattr(session, "application")
        assert not hasattr(session, "model_api")
        assert not hasattr(context, "application_object")
        assert not hasattr(context, "model_api")

        with pytest.raises(FrozenInstanceError):
            context.application.version = "changed"  # type: ignore[misc]
    finally:
        session.close()


def test_duplicate_start_is_rejected_without_second_attach() -> None:
    session, _, runtime, _ = build_session()

    try:
        session.start()

        with pytest.raises(ETABSSessionStateError) as caught:
            session.start()

        assert caught.value.details["state"] == "READY"
        assert len(runtime.calls) == 1
    finally:
        session.close()


def test_attach_failure_marks_failed_and_closes_worker() -> None:
    session, pythoncom, _, _ = build_session(
        runtime_error=RuntimeError("no running ETABS"),
    )

    with pytest.raises(ETABSNotRunningError):
        session.start()

    health = session.health()
    assert session.state is GatewayState.FAILED
    assert session.worker_state is WorkerState.CLOSED
    assert health.status is HealthStatus.UNAVAILABLE
    assert health.diagnostics.completed_at_utc is not None
    assert health.diagnostics.events[-1].code == (
        "ETABS_SESSION_START_FAILED"
    )
    assert pythoncom.finalize_threads == pythoncom.initialize_threads


def test_context_failure_marks_failed_and_releases_components() -> None:
    model = FakeModelAPI(version=("", 1200, 0))
    session, pythoncom, _, _ = build_session(model=model)

    with pytest.raises(ETABSVersionReadError):
        session.start()

    assert session.state is GatewayState.FAILED
    assert session.worker_state is WorkerState.CLOSED
    assert pythoncom.finalize_threads == pythoncom.initialize_threads


def test_close_after_ready_is_idempotent_and_same_thread_finalized() -> None:
    session, pythoncom, _, _ = build_session()
    context = session.start()

    assert session.close() is True
    assert session.close() is False

    assert session.state is GatewayState.CLOSED
    assert session.worker_state is WorkerState.CLOSED
    assert pythoncom.finalize_threads == [
        context.attachment.worker_thread_id
    ]

    health = session.health()
    assert health.status is HealthStatus.UNAVAILABLE
    assert health.diagnostics.events[-1].code == (
        "ETABS_SESSION_CLOSED"
    )


def test_finalizer_failure_is_typed_but_session_becomes_closed() -> None:
    session, _, _, _ = build_session(
        finalize_error=RuntimeError("finalizer failed"),
    )
    session.start()

    with pytest.raises(ETABSSessionCloseError) as caught:
        session.close()

    assert session.state is GatewayState.CLOSED
    assert session.worker_state is WorkerState.CLOSED
    failures = caught.value.details["failures"]
    assert failures[0]["component"] == "worker_close"
    assert failures[0]["operation"] == "worker_finalize"


def test_context_manager_starts_and_closes() -> None:
    session, _, _, _ = build_session()

    with session as active:
        assert active is session
        assert active.state is GatewayState.READY
        assert active.context is not None

    assert session.state is GatewayState.CLOSED


def test_failed_session_can_be_closed_idempotently() -> None:
    session, _, _, _ = build_session(
        runtime_error=RuntimeError("offline"),
    )

    with pytest.raises(ETABSNotRunningError):
        session.start()

    assert session.close() is True
    assert session.close() is False
    assert session.state is GatewayState.CLOSED
