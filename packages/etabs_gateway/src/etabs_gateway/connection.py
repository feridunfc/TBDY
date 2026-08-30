"""Single-owner read-only attachment to an already-running ETABS application.

The gateway owns every production COM discovery strategy. All platform loading,
PID-aware attachment, generic fallback, SapModel acquisition, and later bounded
reads execute on ``DedicatedSTAWorker``. Raw COM references remain private and
are never returned by the public gateway contract.
"""
from __future__ import annotations

import importlib
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

from .contracts import AttachMode, ConnectionRequest, ETABSGatewayContext, ETABSAttachment, utc_now
from .context_reader import read_gateway_context
from .errors import ETABSAttachError, ETABSModelUnavailableError, ETABSNotRunningError
from .worker import DedicatedSTAWorker

DEFAULT_ETABS_PROG_IDS: tuple[str, ...] = (
    "CSI.ETABS.API.ETABSObject",
    "CSI.ETABS.API.ETABSObject.1",
)
HELPER_PROG_ID = "ETABSv1.Helper"

STRATEGY_HELPER_GET_OBJECT_PROCESS = "comtypes_create_helper_get_object_process"
STRATEGY_WIN32_GET_ACTIVE_OBJECT = "win32com_get_active_object_etabs_api_object"
STRATEGY_COMTYPES_GET_ACTIVE_OBJECT = "comtypes_get_active_object_etabs_api_object"
STRATEGY_HELPER_GET_OBJECT = "comtypes_create_helper_get_object"

T = TypeVar("T")
RuntimeLoader = Callable[[], object]
BoundedRead = Callable[[object, object], T]


class _ActiveObjectRuntime(Protocol):
    def GetActiveObject(self, prog_id: str) -> object: ...


@dataclass(frozen=True, slots=True)
class _AttachAttempt:
    strategy: str
    status: str
    message: str
    prog_id: str | None = None
    pid: int | None = None
    exception_type: str | None = None
    hresult: str | None = None

    def as_dict(self) -> dict[str, object | None]:
        return {
            "strategy": self.strategy,
            "status": self.status,
            "message": self.message,
            "prog_id": self.prog_id,
            "pid": self.pid,
            "exception_type": self.exception_type,
            "hresult": self.hresult,
        }


def _load_win32com_client() -> object:
    return importlib.import_module("win32com.client")


def _load_comtypes_client() -> object:
    return importlib.import_module("comtypes.client")


class ReadOnlyETABSConnection:
    """Attach to one running ETABS instance while retaining raw COM privately."""

    def __init__(
        self,
        worker: DedicatedSTAWorker,
        *,
        runtime_loader: RuntimeLoader | None = None,
        comtypes_loader: RuntimeLoader | None = None,
        prog_ids: Sequence[str] = DEFAULT_ETABS_PROG_IDS,
    ) -> None:
        cleaned_prog_ids = tuple(
            prog_id.strip()
            for prog_id in prog_ids
            if isinstance(prog_id, str) and prog_id.strip()
        )
        if not cleaned_prog_ids:
            raise ValueError("At least one non-empty ETABS ProgID is required.")
        if len(set(cleaned_prog_ids)) != len(cleaned_prog_ids):
            raise ValueError("ETABS ProgIDs must be unique.")

        self._worker = worker
        self._runtime_loader = runtime_loader or _load_win32com_client
        self._runtime_loader_is_custom = runtime_loader is not None
        self._comtypes_loader = comtypes_loader or _load_comtypes_client
        self._comtypes_loader_is_custom = comtypes_loader is not None
        self._prog_ids = cleaned_prog_ids
        self._state_lock = threading.RLock()

        self._application: object | None = None
        self._model_api: object | None = None
        self._attachment: ETABSAttachment | None = None
        self._attach_strategy: str | None = None
        self._attached_process_id: int | None = None
        self._attach_attempts: tuple[_AttachAttempt, ...] = ()

    @property
    def attached(self) -> bool:
        with self._state_lock:
            return self._attachment is not None

    @property
    def attachment(self) -> ETABSAttachment | None:
        with self._state_lock:
            return self._attachment

    @property
    def prog_ids(self) -> tuple[str, ...]:
        return self._prog_ids

    @property
    def attach_diagnostics(self) -> Mapping[str, object]:
        """Return factual diagnostics without exposing any COM reference."""
        with self._state_lock:
            return {
                "strategy": self._attach_strategy,
                "process_id": self._attached_process_id,
                "attempts": tuple(attempt.as_dict() for attempt in self._attach_attempts),
            }

    def attach(self, request: ConnectionRequest | None = None) -> ETABSAttachment:
        resolved_request = request or ConnectionRequest()
        self._validate_request(resolved_request)
        return self._worker.call(
            lambda: self._attach_on_worker(resolved_request),
            operation="etabs_attach",
            timeout_seconds=resolved_request.timeout_seconds,
        )

    def read_context(self, *, timeout_seconds: float = 10.0) -> ETABSGatewayContext:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        return self._worker.call(
            self._read_context_on_worker,
            operation="etabs_context_read",
            timeout_seconds=timeout_seconds,
        )

    def execute_bounded_read(
        self,
        function: BoundedRead[T],
        *,
        operation: str,
        timeout_seconds: float = 30.0,
    ) -> T:
        """Execute one trusted factual read on the owning STA thread.

        Only the safety and ``tbdy_engine.etabs.oapi`` layers may consume this
        capability. The callback receives private COM references only during the
        worker call; the application or SapModel owner references may not be
        returned.
        """
        if not callable(function):
            raise TypeError("function must be callable.")
        if not operation.strip():
            raise ValueError("operation must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        return self._worker.call(
            lambda: self._execute_bounded_read_on_worker(function, operation),
            operation=operation,
            timeout_seconds=timeout_seconds,
        )

    def detach(self, *, timeout_seconds: float = 5.0) -> bool:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        with self._state_lock:
            if self._attachment is None:
                return False
        return self._worker.call(
            self._detach_on_worker,
            operation="etabs_detach",
            timeout_seconds=timeout_seconds,
        )

    def close(self, *, timeout_seconds: float = 5.0) -> bool:
        return self.detach(timeout_seconds=timeout_seconds)

    def __enter__(self) -> "ReadOnlyETABSConnection":
        self.attach()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.detach()

    def _attach_on_worker(self, request: ConnectionRequest) -> ETABSAttachment:
        self._worker.assert_worker_thread()
        with self._state_lock:
            if self._attachment is not None:
                raise ETABSAttachError(
                    "The connection is already attached to ETABS.",
                    operation="etabs_attach",
                    details={"stage": "state_validation", "prog_id": self._attachment.prog_id},
                )

        attempts: list[_AttachAttempt] = []
        candidate: tuple[object, object, str, str, int | None] | None = None

        if request.target_process_id is not None:
            candidate, pid_attempts, pid_unsupported = self._try_pid_attach(
                request.target_process_id
            )
            attempts.extend(pid_attempts)
            if candidate is None and request.require_exact_process_match and not pid_unsupported:
                self._remember_failed_attempts(attempts)
                raise ETABSAttachError(
                    "PID-specific ETABS attach failed and generic fallback is disabled.",
                    operation="etabs_attach",
                    details={
                        "stage": "pid_attach",
                        "target_process_id": request.target_process_id,
                        "attempts": [attempt.as_dict() for attempt in attempts],
                    },
                )

        if candidate is None:
            generic_candidate, generic_attempts = self._try_generic_attach()
            candidate = generic_candidate
            attempts.extend(generic_attempts)

        if candidate is None:
            self._remember_failed_attempts(attempts)
            raise ETABSNotRunningError(
                "No running ETABS application could be attached.",
                operation="etabs_attach",
                details={
                    "stage": "active_object_discovery",
                    "attempted_prog_ids": list(self._prog_ids),
                    "target_process_id": request.target_process_id,
                    "attempts": [attempt.as_dict() for attempt in attempts],
                },
            )

        application, model_api, prog_id, strategy, process_id = candidate
        attachment = ETABSAttachment(
            prog_id=prog_id,
            attach_mode=request.attach_mode,
            attached_at_utc=utc_now(),
            worker_thread_id=threading.get_ident(),
        )
        with self._state_lock:
            self._application = application
            self._model_api = model_api
            self._attachment = attachment
            self._attach_strategy = strategy
            self._attached_process_id = process_id
            self._attach_attempts = tuple(attempts)
        return attachment

    def _try_pid_attach(self, pid: int):
        strategy = STRATEGY_HELPER_GET_OBJECT_PROCESS
        attempts: list[_AttachAttempt] = []
        try:
            client = self._comtypes_loader()
        except BaseException as exc:
            attempts.append(self._attempt_from_exception(strategy, exc, pid=pid))
            return None, attempts, False

        try:
            create_object = getattr(client, "CreateObject")
            if not callable(create_object):
                raise AttributeError("CreateObject is not callable")
            helper = create_object(HELPER_PROG_ID)
        except BaseException as exc:
            attempts.append(self._attempt_from_exception(strategy, exc, prog_id=HELPER_PROG_ID, pid=pid))
            return None, attempts, False

        try:
            get_object_process = getattr(helper, "GetObjectProcess")
        except BaseException as exc:
            attempts.append(self._attempt_from_exception(strategy, exc, prog_id=HELPER_PROG_ID, pid=pid))
            return None, attempts, isinstance(exc, AttributeError)
        if not callable(get_object_process):
            attempts.append(
                _AttachAttempt(
                    strategy=strategy,
                    status="FAILED",
                    message="ETABS helper does not expose callable GetObjectProcess.",
                    prog_id=HELPER_PROG_ID,
                    pid=pid,
                    exception_type="AttributeError",
                )
            )
            return None, attempts, True

        for prog_id in self._prog_ids:
            try:
                application = get_object_process(prog_id, pid)
                model_api = self._read_model_api(application, prog_id)
            except ETABSModelUnavailableError:
                raise
            except BaseException as exc:
                attempts.append(self._attempt_from_exception(strategy, exc, prog_id=prog_id, pid=pid))
                continue
            attempts.append(
                _AttachAttempt(
                    strategy=strategy,
                    status="SUCCESS",
                    message="Attached to the requested ETABS process.",
                    prog_id=prog_id,
                    pid=pid,
                )
            )
            return (application, model_api, prog_id, strategy, pid), attempts, False
        return None, attempts, False

    def _try_generic_attach(self):
        attempts: list[_AttachAttempt] = []
        candidate, direct_attempts = self._try_active_object_runtime(
            loader=self._runtime_loader,
            strategy=STRATEGY_WIN32_GET_ACTIVE_OBJECT,
            strict_loader=self._runtime_loader_is_custom,
        )
        attempts.extend(direct_attempts)
        if candidate is not None:
            return candidate, attempts
        if self._runtime_loader_is_custom:
            return None, attempts

        candidate, comtypes_attempts = self._try_active_object_runtime(
            loader=self._comtypes_loader,
            strategy=STRATEGY_COMTYPES_GET_ACTIVE_OBJECT,
            strict_loader=False,
        )
        attempts.extend(comtypes_attempts)
        if candidate is not None:
            return candidate, attempts

        candidate, helper_attempts = self._try_helper_get_object()
        attempts.extend(helper_attempts)
        return candidate, attempts

    def _try_active_object_runtime(self, *, loader: RuntimeLoader, strategy: str, strict_loader: bool):
        attempts: list[_AttachAttempt] = []
        try:
            runtime = loader()
        except BaseException as exc:
            if strict_loader:
                raise ETABSAttachError(
                    "The Windows active-object runtime could not be loaded.",
                    operation="etabs_attach",
                    details={
                        "stage": "runtime_load",
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                ) from exc
            attempts.append(self._attempt_from_exception(strategy, exc))
            return None, attempts

        get_active_object = getattr(runtime, "GetActiveObject", None)
        if not callable(get_active_object):
            if strict_loader:
                raise ETABSAttachError(
                    "The active-object runtime does not expose GetActiveObject.",
                    operation="etabs_attach",
                    details={"stage": "runtime_validation", "missing_callable": "GetActiveObject"},
                )
            attempts.append(
                _AttachAttempt(
                    strategy=strategy,
                    status="FAILED",
                    message="Runtime does not expose callable GetActiveObject.",
                    exception_type="AttributeError",
                )
            )
            return None, attempts

        for prog_id in self._prog_ids:
            try:
                application = cast(_ActiveObjectRuntime, runtime).GetActiveObject(prog_id)
                model_api = self._read_model_api(application, prog_id)
            except ETABSModelUnavailableError:
                raise
            except BaseException as exc:
                attempts.append(self._attempt_from_exception(strategy, exc, prog_id=prog_id))
                continue
            attempts.append(
                _AttachAttempt(
                    strategy=strategy,
                    status="SUCCESS",
                    message="Attached to running ETABS active object.",
                    prog_id=prog_id,
                )
            )
            return (application, model_api, prog_id, strategy, None), attempts
        return None, attempts

    def _try_helper_get_object(self):
        strategy = STRATEGY_HELPER_GET_OBJECT
        attempts: list[_AttachAttempt] = []
        try:
            client = self._comtypes_loader()
            create_object = getattr(client, "CreateObject")
            if not callable(create_object):
                raise AttributeError("CreateObject is not callable")
            helper = create_object(HELPER_PROG_ID)
            get_object = getattr(helper, "GetObject")
            if not callable(get_object):
                raise AttributeError("GetObject is not callable")
        except BaseException as exc:
            attempts.append(self._attempt_from_exception(strategy, exc, prog_id=HELPER_PROG_ID))
            return None, attempts

        for prog_id in self._prog_ids:
            try:
                application = get_object(prog_id)
                model_api = self._read_model_api(application, prog_id)
            except ETABSModelUnavailableError:
                raise
            except BaseException as exc:
                attempts.append(self._attempt_from_exception(strategy, exc, prog_id=prog_id))
                continue
            attempts.append(
                _AttachAttempt(
                    strategy=strategy,
                    status="SUCCESS",
                    message="Attached through ETABS helper GetObject.",
                    prog_id=prog_id,
                )
            )
            return (application, model_api, prog_id, strategy, None), attempts
        return None, attempts

    def _read_context_on_worker(self) -> ETABSGatewayContext:
        self._worker.assert_worker_thread()
        with self._state_lock:
            attachment = self._attachment
            model_api = self._model_api
        if attachment is None or model_api is None:
            raise ETABSAttachError(
                "ETABS context cannot be read before attachment.",
                operation="etabs_context_read",
                details={"stage": "connection_state"},
            )
        return read_gateway_context(model_api=model_api, attachment=attachment)

    def _execute_bounded_read_on_worker(self, function: BoundedRead[T], operation: str) -> T:
        self._worker.assert_worker_thread()
        with self._state_lock:
            application = self._application
            model_api = self._model_api
            attachment = self._attachment
        if attachment is None or application is None or model_api is None:
            raise ETABSAttachError(
                "Bounded ETABS read requires an attached gateway session.",
                operation=operation,
                details={"stage": "connection_state"},
            )
        result = function(application, model_api)
        if result is application or result is model_api:
            raise ETABSAttachError(
                "Bounded ETABS reads may not return raw owner COM references.",
                operation=operation,
                details={"stage": "raw_reference_escape"},
            )
        return result

    def _detach_on_worker(self) -> bool:
        self._worker.assert_worker_thread()
        with self._state_lock:
            if self._attachment is None:
                return False
            self._model_api = None
            self._application = None
            self._attachment = None
            self._attach_strategy = None
            self._attached_process_id = None
            self._attach_attempts = ()
            return True

    def _remember_failed_attempts(self, attempts: Sequence[_AttachAttempt]) -> None:
        with self._state_lock:
            self._attach_strategy = None
            self._attached_process_id = None
            self._attach_attempts = tuple(attempts)

    @staticmethod
    def _read_model_api(application: object, prog_id: str) -> object:
        if application is None:
            raise ETABSModelUnavailableError(
                "The attached ETABS application returned no object.",
                operation="etabs_attach",
                details={"stage": "model_api_acquisition", "prog_id": prog_id},
            )
        try:
            model_api = getattr(application, "SapModel")
        except BaseException as exc:
            raise ETABSModelUnavailableError(
                "The attached ETABS application did not expose its model API.",
                operation="etabs_attach",
                details={
                    "stage": "model_api_acquisition",
                    "prog_id": prog_id,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            ) from exc
        if model_api is None:
            raise ETABSModelUnavailableError(
                "The attached ETABS application returned no model API.",
                operation="etabs_attach",
                details={"stage": "model_api_acquisition", "prog_id": prog_id},
            )
        return model_api

    @staticmethod
    def _attempt_from_exception(
        strategy: str,
        exc: BaseException,
        *,
        prog_id: str | None = None,
        pid: int | None = None,
    ) -> _AttachAttempt:
        hresult = getattr(exc, "hresult", None)
        if hresult is None:
            args = getattr(exc, "args", ())
            if args and isinstance(args[0], int):
                hresult = args[0]
        return _AttachAttempt(
            strategy=strategy,
            status="FAILED",
            message=str(exc) or type(exc).__name__,
            prog_id=prog_id,
            pid=pid,
            exception_type=type(exc).__name__,
            hresult=None if hresult is None else str(hresult),
        )

    def _validate_request(self, request: ConnectionRequest) -> None:
        if request.attach_mode is not AttachMode.RUNNING_INSTANCE:
            raise ETABSAttachError(
                "Only running-instance attachment is supported.",
                operation="etabs_attach",
                details={"stage": "request_validation", "attach_mode": request.attach_mode.value},
            )
        if (
            request.target_process_id is not None
            and self._runtime_loader_is_custom
            and not self._comtypes_loader_is_custom
        ):
            raise ETABSAttachError(
                "PID-specific attach with an injected active-object runtime also requires an injected comtypes runtime.",
                operation="etabs_attach",
                details={
                    "stage": "request_validation",
                    "target_process_id": request.target_process_id,
                    "missing_runtime": "comtypes_loader",
                },
            )


__all__ = [
    "DEFAULT_ETABS_PROG_IDS",
    "HELPER_PROG_ID",
    "STRATEGY_COMTYPES_GET_ACTIVE_OBJECT",
    "STRATEGY_HELPER_GET_OBJECT",
    "STRATEGY_HELPER_GET_OBJECT_PROCESS",
    "STRATEGY_WIN32_GET_ACTIVE_OBJECT",
    "ReadOnlyETABSConnection",
]
