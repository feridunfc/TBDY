from __future__ import annotations

import threading

import pytest

from etabs_gateway.errors import (
    ETABSCallError,
    ETABSThreadViolationError,
    ETABSTimeoutError,
    ETABSWorkerClosedError,
    ETABSWorkerStartError,
)
from etabs_gateway.worker import DedicatedSTAWorker, WorkerState


def test_initializer_task_and_finalizer_share_worker_thread() -> None:
    observed: dict[str, int] = {}

    def initializer() -> None:
        observed["initializer"] = threading.get_ident()

    def finalizer() -> None:
        observed["finalizer"] = threading.get_ident()

    worker = DedicatedSTAWorker(
        initializer=initializer,
        finalizer=finalizer,
    )
    caller_thread = threading.get_ident()

    task_thread = worker.call(
        threading.get_ident,
        operation="thread_identity",
    )
    worker.close()

    assert task_thread != caller_thread
    assert observed == {
        "initializer": task_thread,
        "finalizer": task_thread,
    }
    assert worker.state is WorkerState.CLOSED


def test_submit_returns_future_and_serializes_work() -> None:
    worker = DedicatedSTAWorker()
    order: list[int] = []

    first = worker.submit(lambda: order.append(1) or 10)
    second = worker.submit(lambda: order.append(2) or 20)

    assert first.result(timeout=1.0) == 10
    assert second.result(timeout=1.0) == 20
    assert order == [1, 2]

    worker.close()


def test_assert_worker_thread_passes_inside_and_fails_outside() -> None:
    worker = DedicatedSTAWorker()

    with pytest.raises(ETABSThreadViolationError):
        worker.assert_worker_thread()

    assert worker.call(
        lambda: worker.assert_worker_thread() or "ok",
        operation="thread_assertion",
    ) == "ok"

    worker.close()


def test_generic_task_exception_is_wrapped_with_operation_context() -> None:
    worker = DedicatedSTAWorker()

    def fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ETABSCallError) as caught:
        worker.call(fail, operation="failing_operation")

    assert caught.value.operation == "failing_operation"
    assert caught.value.details["exception_type"] == "ValueError"
    assert caught.value.details["exception_message"] == "boom"

    worker.close()


def test_initializer_failure_rejects_start_and_future_work() -> None:
    def fail_initializer() -> None:
        raise RuntimeError("init failed")

    worker = DedicatedSTAWorker(initializer=fail_initializer)

    with pytest.raises(ETABSWorkerStartError) as caught:
        worker.start()

    assert caught.value.details["exception_type"] == "RuntimeError"
    assert worker.state is WorkerState.FAILED

    with pytest.raises(ETABSWorkerStartError):
        worker.call(lambda: None)

    worker.close()
    assert worker.state is WorkerState.CLOSED


def test_close_is_idempotent_and_rejects_future_work() -> None:
    worker = DedicatedSTAWorker()
    assert worker.call(lambda: 7) == 7

    worker.close()
    worker.close()

    with pytest.raises(ETABSWorkerClosedError):
        worker.call(lambda: 8)


def test_queued_timeout_cancels_task_before_execution_and_worker_survives() -> None:
    worker = DedicatedSTAWorker()
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    timed_out_task_executed = threading.Event()

    def blocker() -> str:
        blocker_started.set()
        assert release_blocker.wait(1.0)
        return "released"

    first = worker.submit(blocker, operation="blocker")
    assert blocker_started.wait(1.0)

    with pytest.raises(ETABSTimeoutError) as caught:
        worker.call(
            lambda: timed_out_task_executed.set(),
            operation="queued_timeout",
            timeout_seconds=0.02,
        )

    assert caught.value.details["cancelled_before_start"] is True

    release_blocker.set()
    assert first.result(timeout=1.0) == "released"
    assert timed_out_task_executed.is_set() is False
    assert worker.call(lambda: 42) == 42

    worker.close()


def test_running_timeout_poisons_worker_and_rejects_new_work() -> None:
    worker = DedicatedSTAWorker()
    started = threading.Event()
    release = threading.Event()

    def slow_task() -> None:
        started.set()
        assert release.wait(1.0)

    with pytest.raises(ETABSTimeoutError) as caught:
        worker.call(
            slow_task,
            operation="running_timeout",
            timeout_seconds=0.02,
        )

    assert started.is_set()
    assert caught.value.details["cancelled_before_start"] is False
    assert worker.state is WorkerState.FAILED

    with pytest.raises(ETABSWorkerClosedError):
        worker.call(lambda: None)

    release.set()
    worker.close(timeout_seconds=1.0)


def test_close_timeout_is_typed_and_later_close_can_complete() -> None:
    worker = DedicatedSTAWorker()
    started = threading.Event()
    release = threading.Event()

    def blocker() -> None:
        started.set()
        assert release.wait(1.0)

    future = worker.submit(blocker)
    assert started.wait(1.0)

    with pytest.raises(ETABSTimeoutError):
        worker.close(timeout_seconds=0.02)

    release.set()
    assert future.result(timeout=1.0) is None
    worker.close(timeout_seconds=1.0)
    assert worker.state is WorkerState.CLOSED


def test_finalizer_failure_is_reported_during_close() -> None:
    def bad_finalizer() -> None:
        raise RuntimeError("finalize failed")

    worker = DedicatedSTAWorker(finalizer=bad_finalizer)
    assert worker.call(lambda: "ok") == "ok"

    with pytest.raises(ETABSCallError) as caught:
        worker.close()

    assert caught.value.operation == "worker_finalize"
    assert caught.value.details["exception_type"] == "RuntimeError"


def test_context_manager_starts_and_closes_worker() -> None:
    worker = DedicatedSTAWorker()

    with worker as active:
        assert active.is_running
        assert active.call(lambda: 3) == 3

    assert worker.state is WorkerState.CLOSED


def test_close_from_worker_thread_is_rejected() -> None:
    worker = DedicatedSTAWorker()

    with pytest.raises(ETABSThreadViolationError):
        worker.call(worker.close, operation="close_from_worker")

    worker.close()


def test_task_timeout_error_is_call_failure_not_worker_timeout() -> None:
    worker = DedicatedSTAWorker()

    def task_timeout() -> None:
        raise TimeoutError("task-level timeout")

    with pytest.raises(ETABSCallError) as caught:
        worker.call(
            task_timeout,
            operation="task_timeout",
            timeout_seconds=1.0,
        )

    assert caught.value.operation == "task_timeout"
    assert caught.value.details["exception_type"] == "TimeoutError"
    assert caught.value.details["exception_message"] == "task-level timeout"
    assert worker.state is WorkerState.RUNNING
    assert worker.call(lambda: 9) == 9

    worker.close()


def test_start_timeout_rejects_future_work_and_can_close() -> None:
    initializer_started = threading.Event()
    release_initializer = threading.Event()

    def blocking_initializer() -> None:
        initializer_started.set()
        assert release_initializer.wait(1.0)

    worker = DedicatedSTAWorker(
        initializer=blocking_initializer,
        start_timeout_seconds=0.02,
    )

    with pytest.raises(ETABSTimeoutError):
        worker.start()

    assert initializer_started.is_set()

    with pytest.raises(ETABSWorkerClosedError):
        worker.call(lambda: None)

    release_initializer.set()
    worker.close(timeout_seconds=1.0)
    assert worker.state is WorkerState.CLOSED


def test_poisoned_worker_rejects_reentrant_work_and_clears_thread_id() -> None:
    worker = DedicatedSTAWorker()
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    observed_errors: list[type[BaseException]] = []

    def timed_out_task() -> None:
        started.set()
        assert release.wait(1.0)

        try:
            worker.call(
                lambda: "must-not-run",
                operation="reentrant_after_timeout",
            )
        except BaseException as exc:
            observed_errors.append(type(exc))
        finally:
            finished.set()

    with pytest.raises(ETABSTimeoutError):
        worker.call(
            timed_out_task,
            operation="poison_worker",
            timeout_seconds=0.02,
        )

    assert started.is_set()
    assert worker.state is WorkerState.FAILED

    release.set()
    assert finished.wait(1.0)

    worker.close(timeout_seconds=1.0)

    assert observed_errors == [ETABSWorkerClosedError]
    assert worker.state is WorkerState.CLOSED
    assert worker.thread_id is None
