"""Read-only attachment to an already-running ETABS application.

All platform loading, active-object discovery, and ETABS COM member access are
executed through ``DedicatedSTAWorker``. Raw COM references remain private and
are never returned through the public gateway contract.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from .contracts import (
    AttachMode,
    ConnectionRequest,
    ETABSAttachment,
    utc_now,
)
from .errors import (
    ETABSAttachError,
    ETABSModelUnavailableError,
    ETABSNotRunningError,
)
from .worker import DedicatedSTAWorker


DEFAULT_ETABS_PROG_IDS: tuple[str, ...] = (
    "CSI.ETABS.API.ETABSObject",
)


class _ActiveObjectRuntime(Protocol):
    def GetActiveObject(self, prog_id: str) -> object: ...


RuntimeLoader = Callable[[], object]


def _load_win32com_client() -> object:
    return importlib.import_module("win32com.client")


class ReadOnlyETABSConnection:
    """Attach to one running ETABS instance without exposing COM objects."""

    def __init__(
        self,
        worker: DedicatedSTAWorker,
        *,
        runtime_loader: RuntimeLoader | None = None,
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
        self._prog_ids = cleaned_prog_ids
        self._state_lock = threading.RLock()

        self._application: object | None = None
        self._model_api: object | None = None
        self._attachment: ETABSAttachment | None = None

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

    def attach(
        self,
        request: ConnectionRequest | None = None,
    ) -> ETABSAttachment:
        resolved_request = request or ConnectionRequest()
        self._validate_request(resolved_request)

        return self._worker.call(
            lambda: self._attach_on_worker(resolved_request),
            operation="etabs_attach",
            timeout_seconds=resolved_request.timeout_seconds,
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

    def __enter__(self) -> ReadOnlyETABSConnection:
        self.attach()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        self.detach()

    def _attach_on_worker(
        self,
        request: ConnectionRequest,
    ) -> ETABSAttachment:
        self._worker.assert_worker_thread()

        with self._state_lock:
            if self._attachment is not None:
                raise ETABSAttachError(
                    "The connection is already attached to ETABS.",
                    operation="etabs_attach",
                    details={
                        "stage": "state_validation",
                        "prog_id": self._attachment.prog_id,
                    },
                )

        runtime = self._load_runtime()
        attempts: list[dict[str, Any]] = []

        for prog_id in self._prog_ids:
            try:
                application = runtime.GetActiveObject(prog_id)
            except BaseException as exc:
                attempts.append(
                    {
                        "prog_id": prog_id,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    }
                )
                continue

            if application is None:
                attempts.append(
                    {
                        "prog_id": prog_id,
                        "exception_type": "NullActiveObject",
                        "exception_message": (
                            "GetActiveObject returned None."
                        ),
                    }
                )
                continue

            model_api = self._read_model_api(application, prog_id)
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

            return attachment

        raise ETABSNotRunningError(
            "No running ETABS application could be attached.",
            operation="etabs_attach",
            details={
                "stage": "active_object_discovery",
                "attempted_prog_ids": list(self._prog_ids),
                "attempts": attempts,
            },
        )

    def _detach_on_worker(self) -> bool:
        self._worker.assert_worker_thread()

        with self._state_lock:
            if self._attachment is None:
                return False

            # Release private COM references on their owner thread.
            self._model_api = None
            self._application = None
            self._attachment = None
            return True

    def _load_runtime(self) -> _ActiveObjectRuntime:
        try:
            raw_runtime = self._runtime_loader()
        except BaseException as exc:
            raise ETABSAttachError(
                "The Windows active-object runtime could not be loaded.",
                operation="etabs_attach",
                details={
                    "stage": "runtime_load",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            ) from exc

        get_active_object = getattr(raw_runtime, "GetActiveObject", None)
        if not callable(get_active_object):
            raise ETABSAttachError(
                "The active-object runtime does not expose GetActiveObject.",
                operation="etabs_attach",
                details={
                    "stage": "runtime_validation",
                    "missing_callable": "GetActiveObject",
                },
            )

        return cast(_ActiveObjectRuntime, raw_runtime)

    @staticmethod
    def _read_model_api(
        application: object,
        prog_id: str,
    ) -> object:
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
                details={
                    "stage": "model_api_acquisition",
                    "prog_id": prog_id,
                },
            )

        return model_api

    @staticmethod
    def _validate_request(request: ConnectionRequest) -> None:
        if request.attach_mode is not AttachMode.RUNNING_INSTANCE:
            raise ETABSAttachError(
                "Only running-instance attachment is supported.",
                operation="etabs_attach",
                details={
                    "stage": "request_validation",
                    "attach_mode": request.attach_mode.value,
                },
            )

        if request.target_process_id is not None:
            raise ETABSAttachError(
                "Exact process selection is not implemented by the current "
                "active-object attachment boundary.",
                operation="etabs_attach",
                details={
                    "stage": "request_validation",
                    "target_process_id": request.target_process_id,
                    "require_exact_process_match": (
                        request.require_exact_process_match
                    ),
                },
            )


__all__ = [
    "DEFAULT_ETABS_PROG_IDS",
    "ReadOnlyETABSConnection",
]
