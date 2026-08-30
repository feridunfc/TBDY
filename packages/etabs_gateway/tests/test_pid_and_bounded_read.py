from __future__ import annotations

import threading

import pytest

from etabs_gateway.connection import (
    STRATEGY_HELPER_GET_OBJECT_PROCESS,
    STRATEGY_WIN32_GET_ACTIVE_OBJECT,
    ReadOnlyETABSConnection,
)
from etabs_gateway.contracts import ConnectionRequest
from etabs_gateway.errors import ETABSAttachError
from etabs_gateway.worker import DedicatedSTAWorker


class Application:
    def __init__(self, model: object) -> None:
        self.SapModel = model


class Helper:
    def __init__(self, application: Application | None, *, expose_pid: bool = True) -> None:
        self.application = application
        self.calls: list[tuple[str, int, int]] = []
        if not expose_pid:
            self.GetObjectProcess = None  # type: ignore[assignment]

    def GetObjectProcess(self, prog_id: str, pid: int) -> Application:
        self.calls.append((prog_id, pid, threading.get_ident()))
        if self.application is None:
            raise RuntimeError("requested process unavailable")
        return self.application


class ComtypesClient:
    def __init__(self, helper: Helper) -> None:
        self.helper = helper
        self.create_calls: list[tuple[str, int]] = []

    def CreateObject(self, prog_id: str) -> Helper:
        self.create_calls.append((prog_id, threading.get_ident()))
        return self.helper


class ActiveRuntime:
    def __init__(self, application: Application) -> None:
        self.application = application
        self.calls: list[tuple[str, int]] = []

    def GetActiveObject(self, prog_id: str) -> Application:
        self.calls.append((prog_id, threading.get_ident()))
        return self.application


def _worker() -> DedicatedSTAWorker:
    return DedicatedSTAWorker()


def test_pid_attach_uses_helper_get_object_process_on_worker() -> None:
    worker = _worker()
    try:
        model = object()
        helper = Helper(Application(model))
        client = ComtypesClient(helper)
        connection = ReadOnlyETABSConnection(
            worker,
            comtypes_loader=lambda: client,
            prog_ids=("ETABS.TEST",),
        )
        attachment = connection.attach(ConnectionRequest(target_process_id=4321))
        diagnostics = connection.attach_diagnostics

        assert diagnostics["strategy"] == STRATEGY_HELPER_GET_OBJECT_PROCESS
        assert diagnostics["process_id"] == 4321
        assert helper.calls == [("ETABS.TEST", 4321, attachment.worker_thread_id)]
        assert client.create_calls[0][1] == attachment.worker_thread_id
        connection.detach()
    finally:
        worker.close(timeout_seconds=1.0)


def test_pid_failure_is_hard_when_exact_process_is_required() -> None:
    worker = _worker()
    try:
        helper = Helper(None)
        connection = ReadOnlyETABSConnection(
            worker,
            comtypes_loader=lambda: ComtypesClient(helper),
            prog_ids=("ETABS.TEST",),
        )
        with pytest.raises(ETABSAttachError) as caught:
            connection.attach(ConnectionRequest(target_process_id=9876))
        assert caught.value.details["stage"] == "pid_attach"
        assert caught.value.details["target_process_id"] == 9876
        assert connection.attached is False
    finally:
        worker.close(timeout_seconds=1.0)


def test_pid_unsupported_uses_bounded_generic_fallback() -> None:
    worker = _worker()
    try:
        application = Application(object())
        helper = Helper(application, expose_pid=False)
        runtime = ActiveRuntime(application)
        connection = ReadOnlyETABSConnection(
            worker,
            runtime_loader=lambda: runtime,
            comtypes_loader=lambda: ComtypesClient(helper),
            prog_ids=("ETABS.TEST",),
        )
        attachment = connection.attach(ConnectionRequest(target_process_id=2468))
        diagnostics = connection.attach_diagnostics

        assert diagnostics["strategy"] == STRATEGY_WIN32_GET_ACTIVE_OBJECT
        assert diagnostics["process_id"] is None
        assert runtime.calls == [("ETABS.TEST", attachment.worker_thread_id)]
        connection.detach()
    finally:
        worker.close(timeout_seconds=1.0)


def test_explicit_compatibility_opt_in_allows_fallback_after_pid_failure() -> None:
    worker = _worker()
    try:
        application = Application(object())
        helper = Helper(None)
        runtime = ActiveRuntime(application)
        connection = ReadOnlyETABSConnection(
            worker,
            runtime_loader=lambda: runtime,
            comtypes_loader=lambda: ComtypesClient(helper),
            prog_ids=("ETABS.TEST",),
        )
        attachment = connection.attach(
            ConnectionRequest(
                target_process_id=1357,
                require_exact_process_match=False,
            )
        )
        assert connection.attach_diagnostics["strategy"] == STRATEGY_WIN32_GET_ACTIVE_OBJECT
        assert runtime.calls == [("ETABS.TEST", attachment.worker_thread_id)]
        connection.detach()
    finally:
        worker.close(timeout_seconds=1.0)


def test_bounded_read_runs_on_owner_thread_and_does_not_return_owner_refs() -> None:
    worker = _worker()
    try:
        model = object()
        application = Application(model)
        runtime = ActiveRuntime(application)
        connection = ReadOnlyETABSConnection(
            worker,
            runtime_loader=lambda: runtime,
            prog_ids=("ETABS.TEST",),
        )
        attachment = connection.attach()
        observed = connection.execute_bounded_read(
            lambda app, sap: (threading.get_ident(), app is application, sap is model),
            operation="test_bounded_read",
        )
        assert observed == (attachment.worker_thread_id, True, True)

        with pytest.raises(ETABSAttachError) as caught:
            connection.execute_bounded_read(
                lambda _app, sap: sap,
                operation="test_raw_escape",
            )
        assert caught.value.details["stage"] == "raw_reference_escape"
        connection.detach()
    finally:
        worker.close(timeout_seconds=1.0)
