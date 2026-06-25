"""Single-thread task worker for future COM apartment ownership."""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Generic, TypeVar, cast

from .errors import (
    ETABSCallError,
    ETABSGatewayError,
    ETABSThreadViolationError,
    ETABSTimeoutError,
    ETABSWorkerClosedError,
    ETABSWorkerStartError,
)

T = TypeVar("T")


class WorkerState(str, Enum):
    NEW = "NEW"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


@dataclass(slots=True)
class _WorkItem(Generic[T]):
    operation: str
    function: Callable[[], T]
    future: Future[T]


_STOP = object()


class DedicatedSTAWorker:
    """Own one thread and serialize all submitted work on that thread.

    Apartment initialization and finalization are injected callbacks. P1.1 does
    not bind this worker to a platform-specific COM library or to ETABS.
    """

    def __init__(
        self,
        *,
        initializer: Callable[[], None] | None = None,
        finalizer: Callable[[], None] | None = None,
        thread_name: str = "etabs-gateway-sta",
        start_timeout_seconds: float = 5.0,
        default_call_timeout_seconds: float = 30.0,
        close_timeout_seconds: float = 5.0,
    ) -> None:
        if not thread_name.strip():
            raise ValueError("thread_name must not be empty.")
        for field_name, value in (
            ("start_timeout_seconds", start_timeout_seconds),
            ("default_call_timeout_seconds", default_call_timeout_seconds),
            ("close_timeout_seconds", close_timeout_seconds),
        ):
            if value <= 0:
                raise ValueError(f"{field_name} must be greater than zero.")

        self._initializer = initializer
        self._finalizer = finalizer
        self._thread_name = thread_name
        self._start_timeout_seconds = float(start_timeout_seconds)
        self._default_call_timeout_seconds = float(default_call_timeout_seconds)
        self._close_timeout_seconds = float(close_timeout_seconds)

        self._queue: queue.Queue[_WorkItem[Any] | object] = queue.Queue()
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._startup_cancelled = threading.Event()

        self._state = WorkerState.NEW
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._startup_error: BaseException | None = None
        self._finalizer_error: BaseException | None = None

    @property
    def state(self) -> WorkerState:
        with self._lock:
            return self._state

    @property
    def thread_id(self) -> int | None:
        with self._lock:
            return self._thread_id

    @property
    def is_running(self) -> bool:
        return self.state is WorkerState.RUNNING

    def start(self, *, timeout_seconds: float | None = None) -> None:
        timeout = self._validated_timeout(
            timeout_seconds,
            default=self._start_timeout_seconds,
            field_name="timeout_seconds",
        )

        with self._lock:
            if self._state is WorkerState.RUNNING:
                return
            if self._state in {WorkerState.CLOSING, WorkerState.CLOSED}:
                raise ETABSWorkerClosedError(
                    "The worker cannot be started after close has begun.",
                    operation="worker_start",
                    details={"state": self._state.value},
                )
            if self._state is WorkerState.FAILED:
                if self._startup_error is not None:
                    self._raise_start_failure()
                raise ETABSWorkerClosedError(
                    "The worker is unavailable after a runtime failure.",
                    operation="worker_start",
                    details={"state": self._state.value},
                )

            if self._state is WorkerState.NEW:
                self._state = WorkerState.STARTING
                self._thread = threading.Thread(
                    target=self._thread_main,
                    name=self._thread_name,
                    daemon=False,
                )
                self._thread.start()

        if not self._ready.wait(timeout):
            self._startup_cancelled.set()
            self._stop_requested.set()
            self._queue.put(_STOP)
            with self._lock:
                if self._state is WorkerState.STARTING:
                    self._state = WorkerState.FAILED
            raise ETABSTimeoutError(
                "Timed out while starting the dedicated worker.",
                operation="worker_start",
                details={"timeout_seconds": timeout},
            )

        with self._lock:
            if self._state is WorkerState.RUNNING:
                return
            if self._state is WorkerState.FAILED:
                self._raise_start_failure()
            if self._state in {WorkerState.CLOSING, WorkerState.CLOSED}:
                raise ETABSWorkerClosedError(
                    "The worker closed before startup completed.",
                    operation="worker_start",
                    details={"state": self._state.value},
                )
            raise ETABSWorkerStartError(
                "The worker reached an unexpected state during startup.",
                operation="worker_start",
                details={"state": self._state.value},
            )

    def submit(
        self,
        function: Callable[[], T],
        *,
        operation: str = "worker_call",
    ) -> Future[T]:
        if not callable(function):
            raise TypeError("function must be callable.")
        if not operation.strip():
            raise ValueError("operation must not be empty.")

        if self._is_worker_thread():
            # Reentrant execution is allowed only while the worker is healthy.
            # A running-task timeout may poison the worker while the timed-out
            # function is still executing on this thread.
            with self._lock:
                if self._state is not WorkerState.RUNNING:
                    self._raise_unavailable(operation)

            future: Future[T] = Future()
            try:
                future.set_result(function())
            except BaseException as exc:
                future.set_exception(exc)
            return future

        self.start()

        future = Future[T]()
        item = _WorkItem(
            operation=operation,
            function=function,
            future=future,
        )

        with self._lock:
            if self._state is not WorkerState.RUNNING:
                self._raise_unavailable(operation)
            self._queue.put(item)

        return future

    def call(
        self,
        function: Callable[[], T],
        *,
        operation: str = "worker_call",
        timeout_seconds: float | None = None,
    ) -> T:
        timeout = self._validated_timeout(
            timeout_seconds,
            default=self._default_call_timeout_seconds,
            field_name="timeout_seconds",
        )
        future = self.submit(function, operation=operation)

        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            # concurrent.futures.TimeoutError is an alias of built-in
            # TimeoutError. A completed future may therefore contain a
            # TimeoutError raised by the task itself; that is a call failure,
            # not a worker wait timeout.
            if future.done():
                raise ETABSCallError(
                    "Worker operation failed.",
                    operation=operation,
                    details={
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                ) from exc

            cancelled_before_start = future.cancel()
            if not cancelled_before_start:
                self._poison_after_running_timeout()
            raise ETABSTimeoutError(
                "Timed out while waiting for worker operation completion.",
                operation=operation,
                details={
                    "timeout_seconds": timeout,
                    "cancelled_before_start": cancelled_before_start,
                },
            ) from exc
        except ETABSGatewayError:
            raise
        except BaseException as exc:
            raise ETABSCallError(
                "Worker operation failed.",
                operation=operation,
                details={
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            ) from exc

    def assert_worker_thread(self) -> None:
        if not self._is_worker_thread():
            raise ETABSThreadViolationError(
                "The operation must run on the dedicated worker thread.",
                operation="worker_thread_assertion",
                details={
                    "expected_thread_id": self.thread_id,
                    "actual_thread_id": threading.get_ident(),
                },
            )

    def close(self, *, timeout_seconds: float | None = None) -> None:
        timeout = self._validated_timeout(
            timeout_seconds,
            default=self._close_timeout_seconds,
            field_name="timeout_seconds",
        )

        if self._is_worker_thread():
            raise ETABSThreadViolationError(
                "The worker cannot join itself during close.",
                operation="worker_close",
                details={"thread_id": threading.get_ident()},
            )

        with self._lock:
            if self._state is WorkerState.CLOSED:
                return
            if self._state is WorkerState.NEW:
                self._state = WorkerState.CLOSED
                return

            thread = self._thread
            if self._state is not WorkerState.CLOSING:
                self._state = WorkerState.CLOSING
                self._stop_requested.set()
                self._queue.put(_STOP)

        if thread is not None:
            thread.join(timeout)

        if thread is not None and thread.is_alive():
            raise ETABSTimeoutError(
                "Timed out while closing the dedicated worker.",
                operation="worker_close",
                details={"timeout_seconds": timeout},
            )

        with self._lock:
            finalizer_error = self._finalizer_error
            self._state = WorkerState.CLOSED

        if finalizer_error is not None:
            raise ETABSCallError(
                "Worker finalization failed.",
                operation="worker_finalize",
                details={
                    "exception_type": type(finalizer_error).__name__,
                    "exception_message": str(finalizer_error),
                },
            ) from finalizer_error

    def __enter__(self) -> DedicatedSTAWorker:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        self.close()

    def _thread_main(self) -> None:
        initialized = False
        with self._lock:
            self._thread_id = threading.get_ident()

        try:
            if self._initializer is not None:
                self._initializer()
            initialized = True

            with self._lock:
                if self._startup_cancelled.is_set() or self._stop_requested.is_set():
                    self._state = WorkerState.CLOSING
                else:
                    self._state = WorkerState.RUNNING
            self._ready.set()

            if self._startup_cancelled.is_set() or self._stop_requested.is_set():
                return

            while True:
                raw_item = self._queue.get()
                if raw_item is _STOP:
                    return

                item = cast(_WorkItem[Any], raw_item)
                if not item.future.set_running_or_notify_cancel():
                    continue

                try:
                    result = item.function()
                except BaseException as exc:
                    item.future.set_exception(exc)
                else:
                    item.future.set_result(result)
        except BaseException as exc:
            with self._lock:
                self._startup_error = exc
                self._state = WorkerState.FAILED
            self._ready.set()
        finally:
            if initialized and self._finalizer is not None:
                try:
                    self._finalizer()
                except BaseException as exc:
                    with self._lock:
                        self._finalizer_error = exc
                        self._state = WorkerState.FAILED

            with self._lock:
                if self._state not in {WorkerState.FAILED, WorkerState.CLOSED}:
                    self._state = (
                        WorkerState.CLOSED
                        if self._stop_requested.is_set()
                        else WorkerState.FAILED
                    )

                # Do not retain a stale OS thread identifier after exit.
                self._thread_id = None

            self._ready.set()

    def _poison_after_running_timeout(self) -> None:
        with self._lock:
            if self._state is WorkerState.RUNNING:
                self._state = WorkerState.FAILED
                self._stop_requested.set()
                self._queue.put(_STOP)

    def _is_worker_thread(self) -> bool:
        thread_id = self.thread_id
        return thread_id is not None and threading.get_ident() == thread_id

    def _raise_start_failure(self) -> None:
        error = self._startup_error
        details = {"state": self._state.value}
        if error is not None:
            details.update(
                {
                    "exception_type": type(error).__name__,
                    "exception_message": str(error),
                }
            )
        raise ETABSWorkerStartError(
            "The dedicated worker failed to start.",
            operation="worker_start",
            details=details,
        ) from error

    def _raise_unavailable(self, operation: str) -> None:
        if self._state is WorkerState.FAILED and self._startup_error is not None:
            self._raise_start_failure()
        raise ETABSWorkerClosedError(
            "The dedicated worker is not available for new work.",
            operation=operation,
            details={"state": self._state.value},
        )

    @staticmethod
    def _validated_timeout(
        value: float | None,
        *,
        default: float,
        field_name: str,
    ) -> float:
        timeout = default if value is None else float(value)
        if timeout <= 0:
            raise ValueError(f"{field_name} must be greater than zero.")
        return timeout
