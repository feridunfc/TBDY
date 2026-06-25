"""Deterministic lifecycle orchestration for the typed ETABS gateway.

The session owns the COM apartment, dedicated worker, and read-only connection.
Construction is offline-safe: platform modules are still loaded lazily only
when ``start`` is called.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from .com_apartment import ModuleLoader, WindowsCOMApartment
from .connection import (
    DEFAULT_ETABS_PROG_IDS,
    ReadOnlyETABSConnection,
    RuntimeLoader,
)
from .contracts import (
    ConnectionDiagnostics,
    ConnectionRequest,
    DiagnosticEvent,
    ETABSGatewayContext,
    GatewayHealth,
    GatewayState,
    HealthStatus,
    utc_now,
)
from .diagnostics import error_event, info_event
from .errors import (
    ETABSGatewayError,
    ETABSSessionCloseError,
    ETABSSessionStateError,
)
from .worker import DedicatedSTAWorker, WorkerState


class ETABSGatewaySession:
    """Own and orchestrate one read-only ETABS gateway session."""

    def __init__(
        self,
        *,
        com_module_loader: ModuleLoader | None = None,
        runtime_loader: RuntimeLoader | None = None,
        prog_ids: Sequence[str] = DEFAULT_ETABS_PROG_IDS,
        worker_name: str = "etabs-gateway-sta",
    ) -> None:
        self._lock = threading.RLock()
        self._created_at_utc = utc_now()
        self._started_at_utc = None
        self._completed_at_utc = None
        self._state = GatewayState.NEW
        self._context: ETABSGatewayContext | None = None
        self._events: list[DiagnosticEvent] = []

        self._apartment = WindowsCOMApartment(
            module_loader=com_module_loader,
        )
        self._worker = DedicatedSTAWorker(
            initializer=self._apartment.initialize,
            finalizer=self._apartment.finalize,
            thread_name=worker_name,
        )
        self._connection = ReadOnlyETABSConnection(
            self._worker,
            runtime_loader=runtime_loader,
            prog_ids=prog_ids,
        )

    @property
    def state(self) -> GatewayState:
        with self._lock:
            return self._state

    @property
    def worker_state(self) -> WorkerState:
        return self._worker.state

    @property
    def context(self) -> ETABSGatewayContext | None:
        with self._lock:
            return self._context

    def start(
        self,
        request: ConnectionRequest | None = None,
        *,
        context_timeout_seconds: float | None = None,
    ) -> ETABSGatewayContext:
        resolved_request = request or ConnectionRequest()
        context_timeout = (
            resolved_request.timeout_seconds
            if context_timeout_seconds is None
            else float(context_timeout_seconds)
        )
        if context_timeout <= 0:
            raise ValueError(
                "context_timeout_seconds must be greater than zero."
            )

        with self._lock:
            if self._state is not GatewayState.NEW:
                raise ETABSSessionStateError(
                    "The gateway session can be started only once.",
                    operation="session_start",
                    details={"state": self._state.value},
                )

            self._state = GatewayState.STARTING
            self._started_at_utc = utc_now()
            self._events.append(
                info_event(
                    "ETABS_SESSION_STARTING",
                    "The ETABS gateway session is starting.",
                    operation="session_start",
                )
            )

        try:
            attachment = self._connection.attach(resolved_request)
            context = self._connection.read_context(
                timeout_seconds=context_timeout,
            )
        except BaseException as exc:
            cleanup_failures = self._cleanup_components()

            with self._lock:
                self._state = GatewayState.FAILED
                self._completed_at_utc = utc_now()
                self._events.append(
                    error_event(
                        "ETABS_SESSION_START_FAILED",
                        "The ETABS gateway session failed to start.",
                        operation="session_start",
                        details={
                            "exception_type": type(exc).__name__,
                            "exception_message": str(exc),
                            "cleanup_failures": cleanup_failures,
                        },
                    )
                )
            raise

        if context.attachment != attachment:
            cleanup_failures = self._cleanup_components()
            error = ETABSSessionStateError(
                "Attachment identity changed during session startup.",
                operation="session_start",
                details={
                    "stage": "attachment_identity",
                    "cleanup_failures": cleanup_failures,
                },
            )
            with self._lock:
                self._state = GatewayState.FAILED
                self._completed_at_utc = utc_now()
                self._events.append(
                    error_event(
                        error.code,
                        str(error),
                        operation=error.operation,
                        details=error.details,
                    )
                )
            raise error

        with self._lock:
            self._context = context
            self._state = GatewayState.READY
            self._events.append(
                info_event(
                    "ETABS_SESSION_READY",
                    "The ETABS gateway session is ready.",
                    operation="session_start",
                    details={
                        "prog_id": attachment.prog_id,
                        "worker_thread_id": attachment.worker_thread_id,
                    },
                )
            )
            return context

    def health(self) -> GatewayHealth:
        with self._lock:
            state = self._state
            context = self._context
            started_at = self._started_at_utc or self._created_at_utc
            completed_at = self._completed_at_utc
            events = tuple(self._events)

        if state is GatewayState.READY and context is not None:
            status = HealthStatus.HEALTHY
        elif state in {
            GatewayState.NEW,
            GatewayState.STARTING,
            GatewayState.CLOSING,
        }:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNAVAILABLE

        return GatewayHealth(
            status=status,
            state=state,
            application=(
                context.application if context is not None else None
            ),
            model=context.model if context is not None else None,
            diagnostics=ConnectionDiagnostics(
                state=state,
                started_at_utc=started_at,
                completed_at_utc=completed_at,
                events=events,
            ),
        )

    def close(self, *, timeout_seconds: float = 5.0) -> bool:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        with self._lock:
            if self._state is GatewayState.CLOSED:
                return False

            self._state = GatewayState.CLOSING
            self._events.append(
                info_event(
                    "ETABS_SESSION_CLOSING",
                    "The ETABS gateway session is closing.",
                    operation="session_close",
                )
            )

        failures = self._cleanup_components(timeout_seconds=timeout_seconds)

        with self._lock:
            self._state = GatewayState.CLOSED
            self._completed_at_utc = utc_now()

            if failures:
                self._events.append(
                    error_event(
                        "ETABS_SESSION_CLOSE_FAILED",
                        "The ETABS gateway session closed with failures.",
                        operation="session_close",
                        details={"failures": failures},
                    )
                )
            else:
                self._events.append(
                    info_event(
                        "ETABS_SESSION_CLOSED",
                        "The ETABS gateway session is closed.",
                        operation="session_close",
                    )
                )

        if failures:
            raise ETABSSessionCloseError(
                "The ETABS gateway session closed with component failures.",
                operation="session_close",
                details={"failures": failures},
            )

        return True

    def __enter__(self) -> ETABSGatewaySession:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        self.close()

    def _cleanup_components(
        self,
        *,
        timeout_seconds: float = 5.0,
    ) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []

        try:
            if self._connection.attached:
                self._connection.detach(
                    timeout_seconds=timeout_seconds,
                )
        except BaseException as exc:
            failures.append(
                self._failure_record("connection_detach", exc)
            )

        try:
            self._worker.close(timeout_seconds=timeout_seconds)
        except BaseException as exc:
            failures.append(
                self._failure_record("worker_close", exc)
            )

        return failures

    @staticmethod
    def _failure_record(
        component: str,
        exc: BaseException,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "component": component,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }
        if isinstance(exc, ETABSGatewayError):
            record["code"] = exc.code
            record["operation"] = exc.operation
            record["details"] = dict(exc.details)
        return record


__all__ = ["ETABSGatewaySession"]
