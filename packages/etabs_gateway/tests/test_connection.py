from __future__ import annotations

import importlib
import threading
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from etabs_gateway.connection import ReadOnlyETABSConnection
from etabs_gateway.contracts import ConnectionRequest
from etabs_gateway.errors import (
    ETABSAttachError,
    ETABSModelUnavailableError,
    ETABSNotRunningError,
)
from etabs_gateway.worker import DedicatedSTAWorker, WorkerState


class FakeApplication:
    def __init__(
        self,
        model_api: object | None,
        *,
        model_error: BaseException | None = None,
    ) -> None:
        self._model_api = model_api
        self._model_error = model_error
        self.model_reads: list[int] = []

    @property
    def SapModel(self) -> object | None:
        self.model_reads.append(threading.get_ident())
        if self._model_error is not None:
            raise self._model_error
        return self._model_api


class FakeActiveObjectRuntime:
    def __init__(self, outcomes: dict[str, object | BaseException]) -> None:
        self._outcomes = outcomes
        self.calls: list[tuple[str, int]] = []

    def GetActiveObject(self, prog_id: str) -> object:
        self.calls.append((prog_id, threading.get_ident()))
        outcome = self._outcomes[prog_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def worker() -> DedicatedSTAWorker:
    active_worker = DedicatedSTAWorker()
    try:
        yield active_worker
    finally:
        active_worker.close(timeout_seconds=1.0)


def test_default_runtime_loader_is_lazy(
    monkeypatch: pytest.MonkeyPatch,
    worker: DedicatedSTAWorker,
) -> None:
    application = FakeApplication(object())
    runtime = FakeActiveObjectRuntime(
        {"CSI.ETABS.API.ETABSObject": application}
    )
    imported: list[str] = []

    def fake_import(name: str) -> Any:
        imported.append(name)
        return runtime

    monkeypatch.setattr(importlib, "import_module", fake_import)

    connection = ReadOnlyETABSConnection(worker)
    assert imported == []

    attachment = connection.attach()

    assert imported == ["win32com.client"]
    assert attachment.prog_id == "CSI.ETABS.API.ETABSObject"
    connection.detach()


def test_successful_attach_runs_discovery_and_model_acquisition_on_worker(
    worker: DedicatedSTAWorker,
) -> None:
    caller_thread = threading.get_ident()
    application = FakeApplication(object())
    runtime = FakeActiveObjectRuntime({"ETABS.TEST": application})
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )

    attachment = connection.attach()

    assert attachment.worker_thread_id != caller_thread
    assert runtime.calls == [
        ("ETABS.TEST", attachment.worker_thread_id)
    ]
    assert application.model_reads == [attachment.worker_thread_id]
    assert connection.attached is True
    assert connection.attachment == attachment
    assert not hasattr(attachment, "application")
    assert not hasattr(attachment, "model_api")

    with pytest.raises(FrozenInstanceError):
        attachment.prog_id = "changed"  # type: ignore[misc]

    connection.detach()


def test_attach_falls_through_ordered_prog_id_candidates(
    worker: DedicatedSTAWorker,
) -> None:
    application = FakeApplication(object())
    runtime = FakeActiveObjectRuntime(
        {
            "ETABS.MISSING": RuntimeError("not registered"),
            "ETABS.RUNNING": application,
        }
    )
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.MISSING", "ETABS.RUNNING"),
    )

    attachment = connection.attach()

    assert attachment.prog_id == "ETABS.RUNNING"
    assert [prog_id for prog_id, _ in runtime.calls] == [
        "ETABS.MISSING",
        "ETABS.RUNNING",
    ]
    connection.detach()


def test_all_discovery_failures_map_to_not_running(
    worker: DedicatedSTAWorker,
) -> None:
    runtime = FakeActiveObjectRuntime(
        {
            "ETABS.ONE": RuntimeError("missing one"),
            "ETABS.TWO": LookupError("missing two"),
        }
    )
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.ONE", "ETABS.TWO"),
    )

    with pytest.raises(ETABSNotRunningError) as caught:
        connection.attach()

    assert caught.value.details["stage"] == "active_object_discovery"
    assert caught.value.details["attempted_prog_ids"] == [
        "ETABS.ONE",
        "ETABS.TWO",
    ]
    assert [
        attempt["exception_type"]
        for attempt in caught.value.details["attempts"]
    ] == ["RuntimeError", "LookupError"]
    assert connection.attached is False


def test_runtime_load_failure_is_typed(
    worker: DedicatedSTAWorker,
) -> None:
    def fail_load() -> object:
        raise ImportError("win32com unavailable")

    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=fail_load,
    )

    with pytest.raises(ETABSAttachError) as caught:
        connection.attach()

    assert caught.value.details["stage"] == "runtime_load"
    assert caught.value.details["exception_type"] == "ImportError"
    assert worker.state is WorkerState.RUNNING


def test_invalid_runtime_contract_is_typed(
    worker: DedicatedSTAWorker,
) -> None:
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: object(),
    )

    with pytest.raises(ETABSAttachError) as caught:
        connection.attach()

    assert caught.value.details["stage"] == "runtime_validation"
    assert caught.value.details["missing_callable"] == "GetActiveObject"


def test_missing_model_api_is_typed(
    worker: DedicatedSTAWorker,
) -> None:
    runtime = FakeActiveObjectRuntime(
        {"ETABS.TEST": FakeApplication(None)}
    )
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )

    with pytest.raises(ETABSModelUnavailableError) as caught:
        connection.attach()

    assert caught.value.details["stage"] == "model_api_acquisition"
    assert connection.attached is False


def test_model_api_property_failure_is_typed(
    worker: DedicatedSTAWorker,
) -> None:
    application = FakeApplication(
        object(),
        model_error=RuntimeError("model access failed"),
    )
    runtime = FakeActiveObjectRuntime({"ETABS.TEST": application})
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )

    with pytest.raises(ETABSModelUnavailableError) as caught:
        connection.attach()

    assert caught.value.details["exception_type"] == "RuntimeError"
    assert caught.value.details["exception_message"] == "model access failed"


def test_target_process_selection_is_rejected_before_worker_start(
    worker: DedicatedSTAWorker,
) -> None:
    runtime_loaded = False

    def load_runtime() -> object:
        nonlocal runtime_loaded
        runtime_loaded = True
        return object()

    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=load_runtime,
    )

    with pytest.raises(ETABSAttachError) as caught:
        connection.attach(
            ConnectionRequest(target_process_id=1234)
        )

    assert caught.value.details["stage"] == "request_validation"
    assert caught.value.details["target_process_id"] == 1234
    assert runtime_loaded is False
    assert worker.state is WorkerState.NEW


def test_duplicate_attach_is_rejected_without_second_discovery(
    worker: DedicatedSTAWorker,
) -> None:
    application = FakeApplication(object())
    runtime = FakeActiveObjectRuntime({"ETABS.TEST": application})
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )

    connection.attach()

    with pytest.raises(ETABSAttachError) as caught:
        connection.attach()

    assert caught.value.details["stage"] == "state_validation"
    assert len(runtime.calls) == 1
    connection.detach()


def test_detach_is_idempotent_and_allows_reattach(
    worker: DedicatedSTAWorker,
) -> None:
    application = FakeApplication(object())
    runtime = FakeActiveObjectRuntime({"ETABS.TEST": application})
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )

    first = connection.attach()
    assert connection.detach() is True
    assert connection.detach() is False
    assert connection.attached is False
    assert connection.attachment is None

    second = connection.attach()
    assert second.prog_id == first.prog_id
    assert len(runtime.calls) == 2
    connection.detach()


def test_context_manager_attaches_and_detaches(
    worker: DedicatedSTAWorker,
) -> None:
    runtime = FakeActiveObjectRuntime(
        {"ETABS.TEST": FakeApplication(object())}
    )
    connection = ReadOnlyETABSConnection(
        worker,
        runtime_loader=lambda: runtime,
        prog_ids=("ETABS.TEST",),
    )

    with connection as active:
        assert active is connection
        assert active.attached is True

    assert connection.attached is False
